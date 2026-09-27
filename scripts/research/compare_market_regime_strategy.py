"""Read-only strategy replay: identical signals, execution and prices, different entry gates."""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal
from app.models.quant_strategy_config import QuantStrategyConfig
from app.services.market_regime_research import read_snapshot
from app.services.market_regime_service import _proxy_points
from app.services.market_regime_model import cycle_points, MODEL_VERSION
from app.services.quant_service import QuantService, INDEX_TO_ETF_CODE
from market_regime import evaluate_signals


def compare(prices, signals, gates, buy, sell, cost=0):
    results = []
    baseline = evaluate_signals(prices, signals, buy=buy, sell=sell, cost=cost)
    dates = {row["date"]: i for i, row in enumerate(prices)}
    for key, label, points in [("ungated", "原策略，不限制买入", None), *gates]:
        by_date = {str(p["date"]): p for p in points} if points is not None else {}
        gate = {day: p["buy_multiplier"] for day, p in by_date.items()} if points is not None else None
        result = evaluate_signals(prices, signals, gate, buy=buy, sell=sell, cost=cost)
        restricted = []
        baseline_buys = {r["signal_date"] for r in baseline["trades"] if r["side"] == "buy"}
        for row in result["restricted_signals"]:
            day = row["signal_date"]
            i = dates[day]
            if i + 1 == len(prices):
                continue
            item = {**row, "state": by_date.get(day, {}).get("state", "unavailable"),
                    "execution_date": prices[i + 1]["date"],
                    "baseline_bought": day in baseline_buys}
            for window in (5, 10, 20, 60):
                future = prices[i + 1:i + 1 + window]
                complete = len(future) == window
                entry = prices[i + 1]["open"]
                item[f"return_{window}d_pct"] = (future[-1]["close"] / entry - 1) * 100 if complete else None
                item[f"upside_{window}d_pct"] = (max(p["high"] for p in future) / entry - 1) * 100 if complete else None
                item[f"drawdown_{window}d_pct"] = (min(p["low"] for p in future) / entry - 1) * 100 if complete else None
            restricted.append(item)
        results.append({"key": key, "label": label,
            **{k: result[k] for k in ("return_pct", "mdd_pct", "mean_position_pct", "final_position_pct")},
            "missed_return_pp": baseline["return_pct"] - result["return_pct"],
            "drawdown_reduction_pp": baseline["mdd_pct"] - result["mdd_pct"],
            "buy_trades": sum(t["side"] == "buy" for t in result["trades"]),
            "restricted_count": len(restricted),
            "blocked_baseline_buys": sum(t["baseline_bought"] and t["multiplier"] == 0 for t in restricted),
            "reduced_baseline_buys": sum(t["baseline_bought"] and 0 < t["multiplier"] < 1 for t in restricted),
            "missing_gate_days": [d for d in dates if points is not None and
                (d not in by_date or by_date[d]["state"] == "unavailable")],
            "restricted_entries": restricted, "trades": result["trades"], "equity": result["points"]})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-09-24")
    parser.add_argument("--strategy-id", type=int, default=31)
    args = parser.parse_args()
    snapshot = read_snapshot()
    end = snapshot["target_date"]
    with SessionLocal() as db:
        strategy = db.get(QuantStrategyConfig, args.strategy_id)
        config = {c.name: getattr(strategy, c.name) for c in strategy.__table__.columns}
        replay = SimpleNamespace(**{**config, "start_date": date.fromisoformat(args.start)})
        quant = QuantService(db)
        price_rows, colors, pending, initial = quant._build_equity_curve_context(replay)
        price_rows = [r for r in price_rows if str(r["trade_date"]) <= end]
        prices = [{"date": str(r["trade_date"]), **{k: float(r[k]) for k in ("open", "high", "low", "close")}} for r in price_rows]
        signals = {str(day): "red" if quant._resolve_action(color, replay) == "buy" else "blue"
                   for day, color in colors.items() if quant._resolve_action(color, replay)}
        reference = quant._simulate_equity_curve(filtered_prices=price_rows, signal_map=colors,
            pending_actions=pending, initial_close=initial, buy_ratio=float(strategy.buy_position_pct),
            sell_ratio=float(strategy.sell_position_pct), execution_price_mode=strategy.execution_price_mode,
            include_signals=False)
        quality_rows = [dict(r) for r in db.execute(text("""SELECT d.trade_date,
            d.emotion_value, e.emotion_value AS original_emotion,
            d.option_turnover_pc_ratio,d.margin_financing_net_buy_sum_30d
            FROM quant_index_dashboard_daily d LEFT JOIN excel_index_emotion_daily e
            ON e.emotion_date=d.trade_date AND e.index_name=d.index_name
            WHERE d.index_code=:code AND d.trade_date BETWEEN :start AND :end
            ORDER BY d.trade_date"""), {"code": config["target_code"], "start": args.start, "end": end}).mappings()]
        missing_emotion = [str(r["trade_date"]) for r in quality_rows if r["original_emotion"] is None]
        missing_pc = [str(r["trade_date"]) for r in quality_rows if r["option_turnover_pc_ratio"] is None]
        missing_financing = [str(r["trade_date"]) for r in quality_rows if r["margin_financing_net_buy_sum_30d"] is None]
    if config["execution_price_mode"] != "next_open":
        raise ValueError("This research requires next_open execution")
    gates = [(code, label, cycle_points(snapshot, code)) for code, label in (
        ("sh000985", "新牛熊环境（全A）"), ("sh000852", "新牛熊环境（中证1000）"))]
    gates.extend(("previous_" + code, label, _proxy_points(snapshot, code)) for code, label in (
        ("sh000985", "旧暂停规则（日更全A）"), ("sh000852", "旧暂停规则（日更中证1000）")))
    legacy = json.loads((ROOT / "runtime/reports/market_regime/report.json").read_text())
    for code, label in (("sh000985", "旧页面全A口径（仅对照）"), ("sh000852", "旧页面中证1000口径（仅对照）")):
        points = legacy["series"][code]["points"]
        old = points + _proxy_points(snapshot, code, date.fromisoformat(legacy["breadth_as_of"]), SimpleNamespace(**points[-1]))
        gates.append(("legacy_" + code, label, old))
    results = compare(prices, signals, gates, float(config["buy_position_pct"]), float(config["sell_position_pct"]))
    assert abs(results[0]["return_pct"] - reference["cumulative_return_pct"]) < 1e-7
    assert abs(results[0]["mdd_pct"] - reference["max_drawdown_pct"]) < 1e-7
    report = {"model_version": MODEL_VERSION, "generated_at": datetime.now().astimezone().isoformat(), "start_date": args.start,
        "end_date": prices[-1]["date"], "strategy_id": strategy.id, "strategy_name": strategy.name,
        "saved_start_date": str(config["start_date"]), "strategy_updated_at": str(config["updated_at"]),
        "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest(),
        "execution_asset": INDEX_TO_ETF_CODE[config["target_name"]], "results": results,
        "signal_data_quality": {"missing_emotion_dates": missing_emotion,
            "missing_pc_dates": missing_pc, "missing_financing_dates": missing_financing,
            "strict_replay_complete": not (missing_emotion or missing_pc or missing_financing),
            "note": f"{len(missing_emotion)}个交易日缺少原始情绪值，现有策略引擎使用默认50；结果仅为现库复现，不是完整真实信号回测。"},
        "cost_sensitivity": compare(prices, signals, gates[:2], float(config["buy_position_pct"]), float(config["sell_position_pct"]), .001),
        "notes": ["研究起点提前到2024-09-24；不修改保存策略。使用当前规则回放历史，不是历史实盘收益。",
            "沿用策略中心ETF成交价格；红买蓝卖，紫色卖出优先，每次总资产50%，次日开盘。",
            "环境仅作研究限制新买入，不强制卖出。新模型牛市及牛市内调整100%，转弱/修复50%，熊市0%；旧模型暂停/失效0%。",
            "新模型宏观仅使用当时已留存的版本；此前日子是指数基线，不是完整宏观模型回测。",
            "主表与应用同为无手续费/滑点；另列单边0.1%成本敏感性。包括最新持仓按收盘计价。",
            "未来窗口收益与最高/最低价仅为路径说明，不可把重叠窗口或峰值涨幅相加当作错过的总收益。",
            "情绪含历史手工图像恢复数据，部分来源是估算；使用当前数据库快照，未宣称全部历史当时可得。"]}
    out = ROOT / "runtime/reports/market_regime"
    detail = out / "strategy_comparison_detail.json"
    detail.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    # The page receives a compact dated report, not every equity point on every request.
    compact = {**report, "results": [{k: v for k, v in r.items() if k not in ("equity", "trades")} for r in results]}
    compact.pop("cost_sensitivity")
    tmp = out / "strategy_comparison.tmp"
    tmp.write_text(json.dumps(compact, ensure_ascii=False, default=str))
    tmp.replace(out / "strategy_comparison.json")
    lines = ["# 情绪强化测试与市场环境对照", f"区间：{args.start} 至 {prices[-1]['date']}",
        "", "| 买入限制 | 累计收益 | 最大回撤 | 少赚百分点 | 原策略实际买入被阻止 | 半额限制 |", "|---|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['label']} | {r['return_pct']:.2f}% | {r['mdd_pct']:.2f}% | {r['missed_return_pp']:.2f} | {r['blocked_baseline_buys']} | {r['reduced_baseline_buys']} |")
    lines += ["", report["signal_data_quality"]["note"], "", *[f"- {note}" for note in report["notes"]]]
    (out / "strategy_comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
