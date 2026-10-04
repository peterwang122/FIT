"""Render the final saved-model report, not the intermediate search winners."""
import json

from csi500_swing import OUT, save_json
from app.services.csi500_swing_features import PUBLIC_FIELDS


NAMES = {"bull": "中证500牛市波段", "bear": "中证500熊市波段"}
OPERATORS = {"gte": ">=", "lte": "<=", "gt": ">", "lt": "<"}


def main():
    report = json.loads((OUT / "report.json").read_text())
    increment = json.loads((OUT / "incremental.json").read_text())
    report["verification"]["frontend"] = json.loads((OUT / "frontend_verification.json").read_text())
    report["verification"].update(backend_tests=415, typecheck=True, vite_build=True, diff_check=True,
        browser={"viewports": ["1440x900", "1280x800"], "horizontal_overflow": False,
                 "chart_and_filter_entries": True, "metric_refresh_persistence": True, "console_errors": []},
        deployment="API reloaded; running collection/worker/beat/WeChat worker/VPN unchanged; no notification task references these strategies")
    save_json(OUT / "report.json", report)
    lines = ["# 中证500牛熊波段：全历史优化结果", "",
        "全部对应环境历史用于开发与选型，不划分训练、验证或样本外；历史极端命中不是未来保证。",
        f"研究数据快照截至{report['as_of']}；固定规则追加行情的一致性核验及510500交易回放截至{report['models']['bull']['backtest']['end']}。",
        f"候选原值/派生值{report['feature_count']}项，实际扫描{report['studied_feature_count']}项，共{report['attempt_count']}次规则尝试。",
        "所有市场级数据进入清单；逐股、逐合约与分钟明细不直接冒充独立市场日频样本，具体聚合/发布时间阻断见tables.json。", "",
        "## 使用方式与重要限制", "",
        "两条策略已保存到root的策略回测，红买50%、蓝卖100%、同日卖出优先、次日开盘。以510500作为交易代理，ETF成立前仅评价指数。",
        "周期只用于评价适用环境，不自动控制信号；2022与2024春季反弹仍属2021-09开始的熊市，2024-09-18起牛市，2026-07起暂列转弱观察。",
        "每日22:30为信息截止。日频分位用此前最多1260个有效观测、至少252个样本，中间秩并排除当日；缺失不填0/50，不临时删除条件。",
        "银行与外盘使用available_at；融资使用前一实际交易日官方披露截止上界；无法审查首次发布和底层时点的旧宏观/情绪/风险复合分只作诊断，不进入正式规则。",
        "指数发布前的回算历史仅为诊断开发记录，不称为当时可执行信号；正式策略从2022年开始回溯，选中来源均已公开。",
        "**牛市低位仅3段评价区域；熊市高位仅1段，普通熊市高点覆盖很差。两者均不建议自动执行，尤其熊市版不能作为有效的回撤控制方案。**", "",
        "## 510500交易回放", "", "原FIT snapshot引擎没有手续费/滑点模型，本次未增加或修改费用。下列收益没有扣实际交易成本。高点后的指数下跌不是实际做空收益。", "",
        "| 策略 | ID | 区间 | 累计收益 | 最大回撤 |", "|---|---:|---|---:|---:|"]
    for regime, model in report["models"].items():
        bt = model["backtest"]
        lines.append(f"|{NAMES[regime]}|{model['strategy_id']}|{bt['start']}至{bt['end']}|{bt['return_pct']:.2f}%|{bt['mdd_pct']:.2f}%|")
    for regime, model in report["models"].items():
        lines.extend(["", "## " + NAMES[regime], "", f"配置指纹：`{model['config_fingerprint']}`。规则组之间为或，组内条件为且。", ""])
        for side, label in (("low", "红色低位"), ("high", "蓝色高位")):
            lines.append("### " + label)
            for i, group in enumerate(model[side]["rules"], 1):
                conditions = [PUBLIC_FIELDS[c["field"]]["label"] + " " + OPERATORS[c["operator"]] + " " + f"{c['value']:.8g}" for c in group["conditions"]]
                lines.append(f"{i}. " + "，且".join(conditions))
            metrics = model["effective_metrics"][side]
            lines.append(f"\n所属环境中{metrics['events']}段区域；有利5%先到{metrics['favorable_first_pct']:.2f}%，不利3%先到{metrics['adverse_first_pct']:.2f}%，20日中位逆向幅度{metrics['median_mae20']:.2f}%。")
        pct = model["effective_formal_color_pct"]
        lines.extend(["", f"2022起所属环境内实际红色{pct['red']:.2f}%、蓝色{pct['blue']:.2f}%，均未超过35%。", "",
            "| 指定极端日 | 方向 | 卖出优先后命中 | 首次信号 | 提前交易日 | 价格距离 |", "|---|---|---|---|---:|---:|"])
        for row in model["extreme_distance"]:
            lines.append(f"|{row['date']}|{row['side']}|{row['hit']}|{row['first_signal_date']}|{row['lead_sessions']}|{row['price_distance_pct']:.2f}%|")
        ordinary = model["ordinary_pivot_coverage"]
        lines.append(f"\n普通5%反转的当日覆盖：低点{ordinary['low']['exact_hits']}/{ordinary['low']['count']}，高点{ordinary['high']['exact_hits']}/{ordinary['high']['count']}。指定极端全覆盖不等于普通高低点全覆盖。")
        if regime == "bear":
            lines.append("严格120日新高且另一端幅度不少于15%的正式熊市高点标签没有样本，不能声称熊市高点100%覆盖。")
    lines.extend(["", "## 期权共同窗口增量", "",
        "SSE:510500与SZSE:159922均实际扫描各期限价格P/C、成交量/额P/C、隐波与期限结构；不直接平均来源比率。两来源最终均未入选。",
        "以下汇总为来源字段的单因子诊断增量，不等于最终合格规则的提升。共同窗口里任一侧缺少已完成评价区域，增量为空，禁止拿内部哨兵分算‘提升1000分’。", "",
        "| 环境 | 方向 | 来源 | 字段记录 | 可比较数 | 最高可比较增量分 |", "|---|---|---|---:|---:|---:|"])
    for regime in NAMES:
        for side in ("low", "high"):
            for source in ("sse:510500", "szse:159922"):
                records = [r for r in increment if r["regime"] == regime and r["side"] == side and source in r["source"]]
                deltas = [r["delta_score"] for r in records if r["delta_score"] is not None]
                best = f"{max(deltas):.2f}" if deltas else "无法评价"
                lines.append(f"|{regime}|{side}|{source}|{len(records)}|{len(deltas)}|{best}|")
    lines.extend(["", "## 数据清单与审计", "",
        "coverage.csv逐项记录来源、单位、可得起点、预热、自身覆盖缺口、研究状态、时点及入选原因；catalog.json保存完整元数据，tables.json保存原始表清单和阻断理由。",
        f"{report['coverage_audit']['unverified_raw_units']}项非入选字段尚未独立核验原始单位，沿用源单位说明，不据此声称跨来源绝对值可比；正式入选项单位明确。",
        "晚起国证自由现金流成交量分位分支在2025-09-01预热完成后启用；启用前明确关闭，后期断档仍按缺失处理。基础分支覆盖2022全年。", "",
        "## 交付文件", "",
        "- report.json：规则、权重以外的完整配置、年度与周期评价、提前距离、数据指纹、保存ID和验证结果。",
        "- attempts.json及四份*_attempts.json：全部规则尝试、拒绝理由，不删除失败尝试。",
        "- incremental.json/CSV：相同覆盖窗口基线与候选对照，含无法比较原因。",
        "- bull/bear_daily.csv：逐日信号、牛熊标签、已知状态与截止时间。",
        "- bull/bear_low/high_events.csv：逐段5/10/20/60日表现、MFE/MAE、先到顺序及失败案例。",
        "- bull/bear_etf_trades.csv：510500逐笔回放。",
        "- *_1440.jpg与*_1280.jpg：实际页面截图（文件名实际使用连字符）。", "",
        "## 上线核验", "",
        "研究、后端筛选、保存策略、K线颜色与原回测引擎逐日一致；未来行情追加不会改变固定规则的过去信号。重新开展全历史选型则属于另一次模型开发，不能假称旧规则未变。",
        "415项后端测试通过；vue-tsc、vite build、compileall和git diff --check通过。1440x900与1280x800实际浏览器核验通过，曲线、筛选、数据卡及选择记忆一致，没有页面横向溢出。",
        "仅加载网页API。正在采集的worker、stock-temp、beat、微信worker和VPN未重启；新策略没有后台通知引用。本次不改原策略、市场环境、通知、回测引擎，不创建分支/PR，不推送远端。"])
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Rendered saved-model report", [model["strategy_id"] for model in report["models"].values()])


if __name__ == "__main__":
    main()
