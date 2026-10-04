"""Read-only ETF replay and human-readable coverage re-study report."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sqlalchemy import text

from csi500_coverage_restudy import OUT, spans
from csi500_swing import OUT as OLD_OUT, matches, save_json, snapshot
from app.db.session import SessionLocal
from app.services.quant_service import QuantService
from market_regime import evaluate_signals


def signals(frame, model, start):
    red = matches(frame, model["low"]["rules"])[0]
    blue = matches(frame, model["high"]["rules"])[0]
    return {d: "blue" if b else "red" for d, r, b in zip(frame.index, red, blue)
            if d >= start and (r or b)}


def replay(service, prices, signal_map):
    research_prices = [{"date": str(p["trade_date"]), **{k: float(p[k]) for k in ("open", "high", "low", "close")}}
                       for p in prices]
    independent = evaluate_signals(research_prices, signal_map, buy=.5, sell=1, cost=0)
    strategy = SimpleNamespace(signal_buy_color="red", signal_sell_color="blue", purple_conflict_mode="sell_first")
    pending = {research_prices[i + 1]["date"]: service._resolve_action(signal_map[p["date"]], strategy)
               for i, p in enumerate(research_prices[:-1]) if p["date"] in signal_map}
    original = service._simulate_equity_curve(filtered_prices=prices, signal_map=signal_map,
        pending_actions=pending, initial_close=prices[0]["close"], buy_ratio=.5, sell_ratio=1,
        execution_price_mode="next_open", include_signals=True)
    assert abs(independent["return_pct"] - original["cumulative_return_pct"]) < 1e-7
    assert abs(independent["mdd_pct"] - original["max_drawdown_pct"]) < 1e-7
    return {k: v for k, v in independent.items() if k not in ("points", "trades", "restricted_signals")}, independent


def main():
    frame, catalog = snapshot()
    review = json.loads((OUT / "review.json").read_text())
    selection = json.loads((OUT / "selection.json").read_text())
    old = json.loads((OLD_OUT / "report.json").read_text())
    attempts = sum(side["summary"]["trials"] + side.get("extension", {}).get("summary", {}).get("trials", 0)
                   for model in selection["models"].values() for side in model.values())
    lines = ["# 中证500按覆盖期重新研究", "", "## 结论", "",
             "原两条策略尚未改写。长历史牛、熊版本仍未找到同时通过本轮短信号、同日极端覆盖、普通波段覆盖和逆向风险检查的整套规则。",
             "期权覆盖期找到两套研究候选，但开始日期不同，不能拼成2022起的策略或收益曲线，也还没有完成筛选、副图和页面上线。",
             "这是有界搜索的结果，不是数学上的不存在证明。所有历史用于开发，不能把优化结果称为样本外验证或未来极端必定命中。", "",
             f"特征快照截至{frame.index[-1]}；本轮及定向扩展共{attempts:,}次不同规则/场景尝试，原日志和扩展日志分开留存。", "",
             "## 原规则的问题", "", "| 策略 | 颜色 | 最长连续段 | 日期 |", "|---|---|---:|---|"]
    for regime in ("bull", "bear"):
        daily = pd.read_csv(OLD_OUT / f"{regime}_daily.csv")
        for color in ("red", "blue"):
            start, end, lengths = spans(daily[color].to_numpy() & (daily.date.to_numpy() >= "2022-01-01"))
            i = int(np.argmax(lengths))
            lines.append(f"|{'牛市' if regime == 'bull' else '熊市'}|{color}|{int(lengths[i])}|{daily.date.iloc[start[i]]}至{daily.date.iloc[end[i]]}|")
    lines += ["", "只检查累计亮色比例会允许整段横跨多轮行情；新检查不强行截断曲线，只拒绝本身过长的规则。", "",
              "## 覆盖与准入", "",
              "510500期权原值从2022-09-19开始，多数滚动分位从2023-10-09起；159922多数分位从2023年末至2024年初起。",
              "159922成交额P/C目前的有效历史更晚。本轮牛市候选依赖其变动，不能宣称覆盖2024/2025牛市。",
              "长历史候选的数据须在2022前完成预热；所有候选采用自己真实可用历史。成套比较重新取低、高两端共同起点。",
              "任意同色段在2022起绘制范围最多7日，区域长度中位数最多2日；所属环境每种颜色占比最多20%；",
              "每端至少8个完整20日评价区域、2022起至少4个，普通5%波段首次信号前5至后3日覆盖至少50%。",
              "保留原计划同日极端覆盖；逆向风险检查要求先达有利5%比例不低于先达不利3%。每个替代分支必须具有自身指数的位置依据。", "",
              "## 候选与同区间交易回放", "",
              "区域方向评价只统计所属牛/熊环境；交易回放仍全日期独立运行，不以历史周期自动开关。高位方向收益不是真实做空收益。",
              "交易采用现有510500行情和原引擎，次日开盘、买50%、卖100%、卖出优先；未新增费用或滑点，未额外改变分红/复权口径。", "",
              "| 候选 | 共同起点 | 本轮收益 | 本轮最大回撤 | 旧规则同区间收益 | 旧规则同区间最大回撤 |", "|---|---|---:|---:|---:|---:|"]
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        service = QuantService(db)
        prices = service._load_etf_price_rows("510500")
        for key, model in review["models"].items():
            if not model["pair"]: continue
            era, regime = key.split("_")
            pair, start = model["pair"], model["pair"]["start_date"]
            window = [p for p in prices if start <= str(p["trade_date"]) <= frame.index[-1]]
            current_signals = signals(frame, pair, start)
            previous_signals = signals(frame, old["models"][regime], start)
            missing = sorted((set(current_signals) | set(previous_signals)) - {str(p["trade_date"]) for p in window})
            assert not missing, (key, "ETF quotation missing on signal date", missing[:10])
            result, detail = replay(service, window, current_signals)
            previous, old_detail = replay(service, window, previous_signals)
            pair["backtest"] = {"candidate": result, "old_same_window": previous,
                                "start": str(window[0]["trade_date"]), "end": str(window[-1]["trade_date"]),
                                "original_engine_parity": True, "etf_code": "510500", "costs": 0,
                                "filters_and_ui_verified": False}
            pd.DataFrame(detail["trades"]).to_csv(OUT / f"{key}_etf_trades.csv", index=False)
            pd.DataFrame(detail["points"]).to_csv(OUT / f"{key}_etf_daily.csv", index=False)
            pd.DataFrame(old_detail["trades"]).to_csv(OUT / f"{key}_old_same_window_trades.csv", index=False)
            lines.append(f"|{'期权牛市' if regime == 'bull' else '期权熊市'}|{start}|{result['return_pct']:.2f}%|{max(0.0, result['mdd_pct']):.2f}%|{previous['return_pct']:.2f}%|{max(0.0, previous['mdd_pct']):.2f}%|")
            print(key, pair["backtest"], flush=True)
        db.rollback()
    for key, model in review["models"].items():
        lines += ["", "### " + key, ""]
        if not model["pair"]:
            lines += ["没有合格整套模型，不写入策略。优质低位或高位单端不能冒充已经具有完整退出/买入能力。"]
            continue
        pair = model["pair"]
        lines += [f"共同起点{pair['start_date']}。全部参数均为历史优化，不保证未来；牛市候选当前只有单轮行情中的少量样本，熊市期权候选的主要熊市样本来自2024年。", "",
                  "| 端 | 区域数 | 首达有利5% | 首达不利3% | 20日中位逆向 | 普通波段覆盖 | 颜色占比 | 区域中位/最长 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for side in ("low", "high"):
            m = pair["effective_metrics"][side]
            lines.append(f"|{side}|{m['evaluated']}|{m['favorable_first_pct']:.2f}%|{m['adverse_first_pct']:.2f}%|{m['median_mae20']:.2f}%|{m['pivot_coverage_pct']:.2f}%|{m['formal_color_pct']:.2f}%|{m['median_region_days']:.0f}/{m['formal_max_region_days']}|")
        for side in ("low", "high"):
            lines += ["", f"{side}条件：", "```json", json.dumps(pair[side]["rules"], ensure_ascii=False, indent=2), "```", ""]
    lines += ["", "## 实施状态", "",
              "本轮只有研究文件、测试和文档变化。数据库策略46/47仍为原配置；没有重启服务、改采集任务、改中证1000、市场环境或通知，也没有提交或推送。",
              "新规则尚未发布，现有网页不会自动显示本报告候选。完整尝试见各*_attempts.jsonl及*_extension.jsonl；逐日颜色、信号区域和逐笔回放见CSV。",
              "若需要覆盖2022，必须继续研究长历史版或明确修订互相冲突的准入目标；不能用晚起期权数据补造2022的表现。"]
    review["attempt_count"] = attempts
    review["verification"] = {"source_snapshot_reused": True, "production_updated": False,
                               "original_engine_replay_verified": True, "frontend_and_filter_parity": False}
    save_json(OUT / "review.json", review)
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
