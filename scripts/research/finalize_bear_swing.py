"""Verify application parity, export ETF trades and optionally create templates."""
import argparse
from bisect import bisect_right
from datetime import date
import hashlib
import json
from types import SimpleNamespace

from csi1000_bear_swing import OUT, LABELS, ROOT, episodes, rule_mask, summarize, turning_points
from market_regime import evaluate_signals
from app.db.session import SessionLocal
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.user import User
from app.services.quant_service import QuantService
from app.services.bear_swing_features import FEATURE_FIELDS, feature_points
from sqlalchemy import text
import pandas as pd


def payload(name, model):
    return dict(name="中证1000熊市波段-" + ("基础版" if name == "basic" else "增强版"),
        notes=("研究模板，尚不建议直接实盘：样本外低点抄早风险明显；增强版高点样本少，不保证提升。"
               f"数据完整起点{model['start_date']}；红色低位机会、蓝色高位风险，22:30截止、次日开盘。"
               "基础版2018-2020开发/2021验证/2022起评价；增强版至2024开发/2025验证/2026评价。"
               "不依赖牛熊环境开关，不包含实际做空收益。报告runtime/reports/csi1000_bear_swing/report.md；"
               f"规则指纹{model['config_sha256']}"),
        strategy_engine="snapshot", strategy_type="index", sequence_mode="single_target", target_market="cn",
        target_code="sh000852", target_name="中证1000",
        indicator_params={"ma": {"periods": [5,10,20,60]}, "macd": {"fast":12,"slow":26,"signal":9},
            "kdj": {"period":9,"kSmoothing":3,"dSmoothing":3}, "wr":{"period":14}, "rsi":{"period":14},
            "boll":{"period":20,"multiplier":2}},
        blue_filter_groups=[{"conditions":model["high"]["conditions"]}],
        red_filter_groups=[{"conditions":model["low"]["conditions"]}],
        blue_filters={}, red_filters={}, blue_boll_filter={}, red_boll_filter={},
        buy_sequence_groups=[],sell_sequence_groups=[],scan_trade_config={},research_option_template=None,
        signal_buy_color="red",signal_sell_color="blue",purple_conflict_mode="sell_first",
        start_date=date.fromisoformat(model["start_date"]),scan_start_date=None,scan_end_date=None,
        buy_position_pct=.5,sell_position_pct=1,execution_price_mode="next_open")


def replay(service, strategy, snapshots, start, end):
    colors = service._build_signal_map(strategy, snapshots)
    rows = service._load_etf_price_rows("512100")
    prices = [{"date":str(r["trade_date"]), **{k:float(r[k]) for k in ("open","high","low","close")}}
              for r in rows if start <= str(r["trade_date"]) <= end]
    signals = {d: "red" if service._resolve_action(c, strategy) == "buy" else "blue"
               for d,c in colors.items() if service._resolve_action(c,strategy) and start <= d <= end}
    actual = evaluate_signals(prices, signals, buy=.5,sell=1,cost=0)
    dates = [p["date"] for p in prices]
    pending = {}
    for d,c in colors.items():
        if d < start: continue
        i = bisect_right(dates,d)-1
        if 0 <= i < len(dates)-1 and service._resolve_action(c,strategy):
            pending[dates[i+1]] = service._resolve_action(c,strategy)
    expected = service._simulate_equity_curve(filtered_prices=[dict(trade_date=date.fromisoformat(p["date"]), **{k:p[k] for k in ("open","high","low","close")}) for p in prices],
        signal_map=colors,pending_actions=pending,initial_close=prices[0]["close"],buy_ratio=.5,sell_ratio=1,
        execution_price_mode="next_open",include_signals=False)
    assert abs(actual["return_pct"] - expected["cumulative_return_pct"]) < 1e-7
    assert abs(actual["mdd_pct"] - expected["max_drawdown_pct"]) < 1e-7
    return actual


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--install",action="store_true")
    args=parser.parse_args()
    report=json.loads((OUT / "report.json").read_text())
    frame=pd.read_json(OUT / "features.json",orient="table")
    frame.index=frame.index.astype(str)
    with SessionLocal() as db:
        service=QuantService(db)
        originals = [dict(r) for r in db.execute(text("SELECT * FROM quant_strategy_configs WHERE id IN (1,31)")).mappings()]
        original_hash=hashlib.sha256(json.dumps(originals,default=str,sort_keys=True).encode()).hexdigest()
        points=feature_points(db)
        bydate={p["trade_date"]:p for p in points}
        for day,row in frame.iterrows():
            for field in FEATURE_FIELDS:
                actual=bydate[day]["values"][field]
                assert (actual is None and pd.isna(row[field])) or abs(actual-row[field])<1e-7, (day,field)
        for name,model in report["models"].items():
            data=payload(name,model)
            strategy=SimpleNamespace(**data)
            service._validate_strategy_payload(data)
            candles,snapshots=service._load_fixed_strategy_target_chart(strategy)
            actual=service._build_signal_map(strategy,snapshots)
            low=rule_mask(frame,model["low"]["conditions"])
            high=rule_mask(frame,model["high"]["conditions"])
            expected={d: "purple" if low[d] and high[d] else "red" if low[d] else "blue"
                      for d in frame.index if low[d] or high[d]}
            assert actual==expected, (name, "daily filter parity failed",set(actual.items())^set(expected.items()))
            highlights=service._build_strategy_highlight_bands(strategy,snapshots)
            assert {h["tradeDate"]:h["color"] for h in highlights}=={d:c for d,c in expected.items() if d>=model["start_date"]}
            backtest=replay(service,strategy,snapshots,model["start_date"],report["as_of"])
            model["backtest"]={k:v for k,v in backtest.items() if k not in ("points","trades")}
            pd.DataFrame(backtest["trades"]).to_csv(OUT / f"{name}_etf_trades.csv",index=False)
            model["common_backtest"]= {stage: {k:v for k,v in replay(service,strategy,snapshots,start,report["as_of"]).items() if k not in ("points","trades")}
                for stage,start in (("common_history",report["models"]["enhanced"]["start_date"]),("2026_holdout","2026-01-01"))}
            if args.install:
                root=db.query(User).filter(User.username=="root").one()
                existing=db.query(QuantStrategyConfig).filter(QuantStrategyConfig.name==data["name"],QuantStrategyConfig.owner_user_id==root.id).one_or_none()
                if existing:
                    if existing.red_filter_groups!=data["red_filter_groups"] or existing.blue_filter_groups!=data["blue_filter_groups"]:
                        raise RuntimeError("同名策略已被修改，不自动覆盖")
                    model["strategy_id"]=existing.id
                else:
                    model["strategy_id"]=service.create_strategy(data,root.id)["id"]
            print(name,model["backtest"],"id",model.get("strategy_id"),flush=True)
        # Benchmark signals: original emotion only, never the legacy default 50.
        emotions={str(r["emotion_date"]):float(r["emotion_value"]) for r in db.execute(text("SELECT emotion_date,emotion_value FROM excel_index_emotion_daily WHERE index_name='中证1000'")).mappings()}
        benchmarks={}
        for raw in originals:
            strategy=db.get(QuantStrategyConfig,raw["id"])
            _,snapshots=service._load_fixed_strategy_target_chart(strategy)
            for s in snapshots:
                s["values"]["emotion"]=emotions.get(s["trade_date"])
            colors=service._build_signal_map(strategy,snapshots)
            start=max(str(raw["start_date"]),min(emotions))
            stats={}
            for side,color in (("low","red"),("high","blue")):
                mask=pd.Series([colors.get(d) in (color,"purple") and d>=start for d in frame.index],index=frame.index)
                ev=episodes(frame,mask,side)
                labels=[p for p in turning_points(frame) if p["side"]==side]
                stats[side]=summarize(ev,start,report["as_of"],labels,frame)
                pd.DataFrame(ev).to_csv(OUT/f"benchmark_{raw['id']}_{side}.csv",index=False)
            benchmarks[str(raw["id"])]=dict(name=raw["name"],start_date=start,statistics=stats,
                note="当前规则重放；只用原始情绪，历史仍含图像估计；31号中的融资同日数值不视为严格PIT，所以只作诊断对照，不纳入选型。")
        report["benchmarks"]=benchmarks
        new_originals=[dict(r) for r in db.execute(text("SELECT * FROM quant_strategy_configs WHERE id IN (1,31)")).mappings()]
        assert original_hash==hashlib.sha256(json.dumps(new_originals,default=str,sort_keys=True).encode()).hexdigest()
        report["verification"]={"daily_filter_highlight_parity":True,"etf_engine_parity":True,"original_strategy_sha256":original_hash,"chart_filter_feature_parity":True}
    report["conclusion"]="两版低点均未达到可靠熊市抄底标准；增强版2026高点2次较精确但覆盖低、样本不足。保留研究模板，不推荐直接替代原策略，不因名称升级做实盘推荐。"
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
    summary=["\n## 交易回测与结论",report["conclusion"],"", "| 模型 | 区间 | ETF累计收益 | 最大回撤 |", "|---|---|---:|---:|"]
    for name,m in report["models"].items():
        for stage,result in [("各自起点",m["backtest"]),*m["common_backtest"].items()]:
            summary.append(f"|{name}|{stage}|{result['return_pct']:.2f}%|{result['mdd_pct']:.2f}%|")
    summary += ["", "ETF 512100，红买50%蓝卖100%、次日开盘、冲突卖出优先；无手续费滑点。高点方向统计不等于实际做空收益。",
        "研究脚本、保存策略筛选、K线高亮逐日一致；ETF独立重放与现有引擎收益/回撤一致。", "", "## 原策略同类事件对照"]
    for key,b in benchmarks.items():
        summary += [f"- {b['name']}（ID{key}），{b['start_date']}起：" + json.dumps(b["statistics"],ensure_ascii=False),b["note"]]
    path=OUT/"report.md"
    text_before=path.read_text().split("\n## 交易回测与结论")[0]
    path.write_text(text_before+"\n".join(summary)+"\n")


if __name__=="__main__":main()
