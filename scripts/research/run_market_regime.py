"""Reproduce the frozen rule comparison from local, audited input snapshots."""

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from market_regime import RULES, episodes, evaluate_signals, regime_points, rule_manifest

ROOT = Path(__file__).resolve().parents[2]


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def write_json(path, value):
    path.write_text(json.dumps(clean(value), ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")


def prices_from(path):
    frame = pd.DataFrame(json.loads(path.read_text()))
    for key in ("open", "close", "high", "low"):
        frame[key] = pd.to_numeric(frame[key])
    return frame


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--legacy-hfq", action="store_true")
    args = p.parse_args()
    inputs = args.input
    out = inputs / "legacy-hfq-study" if args.legacy_hfq else inputs
    out.mkdir(exist_ok=True)
    breadth_file = "breadth-legacy-hfq.csv" if args.legacy_hfq else "breadth-raw.csv"
    breadth = pd.read_csv(inputs / breadth_file, index_col="date")
    manifests = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                 for f in inputs.glob("sh*.json")}
    manifests[breadth_file] = hashlib.sha256((inputs / breadth_file).read_bytes()).hexdigest()
    all_points, history = {}, []
    for index in ("sh000985", "sh000852"):
        price_frame = prices_from(inputs / f"{index}.json")
        prices = price_frame.to_dict("records")
        for rule in RULES:
            points = regime_points(price_frame, breadth, rule)
            key = index + "_" + rule.name
            all_points[key] = points
            events = episodes(points, prices)
            pd.DataFrame(points).to_csv(out / f"{key}-daily.csv", index=False)
            pd.DataFrame(events).to_csv(out / f"{key}-events.csv", index=False)
            for label, start, end in (("2005-2023", "2005-01-01", "2023-12-31"),
                                      ("2024+", "2024-01-01", "9999")):
                sample = [r for r in points if start <= r["date"] <= end]
                sample_events = [e for e in events if start <= e["start"] <= end]
                complete = [e for e in sample_events if e["drawdown_20d_pct"] is not None]
                history.append({"index": index, "rule": rule.name, "period": label,
                    "days": len(sample), "states": dict(Counter(r["state"] for r in sample)),
                    "episodes": len(sample_events), "complete_20d": len(complete),
                    "drawdown_20d_below_minus5": sum(e["drawdown_20d_pct"] <= -5 for e in complete),
                    "no_drawdown3_upside5": sum(e["drawdown_20d_pct"] > -3 and e["upside_20d_pct"] >= 5 for e in complete),
                    "median_20d_drawdown_pct": np.median([e["drawdown_20d_pct"] for e in complete]) if complete else None})
            years = []
            for year in sorted({r["date"][:4] for r in points}):
                sample = [r for r in points if r["date"].startswith(year)]
                years.append({"year": year, "days": len(sample), **dict(Counter(r["state"] for r in sample))})
            pd.DataFrame(years).to_csv(out / f"{key}-years.csv", index=False)
    previous = ROOT / "runtime/research/emotion31-evaluation-20260906"
    source = ROOT / "runtime/research/emotion31-high39-comparison-20260906/inputs.json"
    data = json.loads(source.read_text())
    spec = importlib.util.spec_from_file_location("previous_eval", previous / "evaluator.py")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    reference.ALL = {r["trade_date"]: r for r in data["snapshots"]}
    prices = [{"date": str(r["trade_date"]), **{k: float(r[k]) for k in ("open", "high", "low", "close")}}
              for r in data["prices"] if str(r["trade_date"]) >= "2025-01-01"]
    if args.legacy_hfq:
        prices = [r for r in prices if r["date"] <= "2026-03-13"]
    comparison, detailed = [], {}
    for label, config, sell in (("original", data["original"], .5),
                                ("high39_half_exit", data["combined"], .5),
                                ("high39_full_exit", data["combined"], 1)):
        signals = reference.signals(config)
        for rule in [None, *RULES]:
            gate = ({r["date"]: r["buy_multiplier"] for r in all_points["sh000852_" + rule.name]}
                    if rule else None)
            for cost in (0, .001):
                name = f"{label}_{rule.name if rule else 'ungated'}_cost{cost}"
                result = evaluate_signals(prices, signals, gate, sell=sell, cost=cost)
                if rule is None:
                    expected = reference.run(config, sell=sell, cost=cost, end=prices[-1]["date"])
                    assert abs(result["return_pct"] - expected["summary"]["return_pct"]) < 1e-8
                    assert abs(result["mdd_pct"] - expected["summary"]["mdd_pct"]) < 1e-8
                for event in result["restricted_signals"]:
                    i = next(i for i, r in enumerate(prices) if r["date"] == event["signal_date"])
                    for w in (5, 10, 20):
                        future = prices[i + 1:i + w + 1]
                        event[f"next_open_to_{w}d_min_pct"] = ((min(r["low"] for r in future) / future[0]["open"] - 1) * 100
                                                                 if len(future) == w else None)
                        event[f"next_open_to_{w}d_max_pct"] = ((max(r["high"] for r in future) / future[0]["open"] - 1) * 100
                                                                 if len(future) == w else None)
                detailed[name] = result
                comparison.append({"strategy": label, "gate": rule.name if rule else "ungated", "one_way_cost": cost,
                    **{k: result[k] for k in ("return_pct", "mdd_pct", "mean_position_pct", "final_position_pct")},
                    "trades": len(result["trades"]), "restricted_red_days": len(result["restricted_signals"]),
                    "restricted_days_with_cash": sum(r["has_cash"] for r in result["restricted_signals"])})
    write_json(out / "strategy-details.json", detailed)
    pd.DataFrame(comparison).to_csv(out / "strategy-comparison.csv", index=False)
    write_json(out / "history-summary.json", history)
    write_json(out / "manifest.json", {"rules": rule_manifest(), "input_sha256": manifests,
        "strategy_inputs_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "code_sha256": hashlib.sha256((Path(__file__).parent / "market_regime.py").read_bytes()).hexdigest(),
        "breadth_kind": "legacy_hfq_observed_stocks" if args.legacy_hfq else "unadjusted_observed_stock_proxy",
        "strategy_evaluation_end": prices[-1]["date"], "production_approved": False})
    preview = {index: [{**r, **{k: row[k] for k in ("open", "high", "low")}}
                        for r, row in zip(all_points[index + "_balanced"], prices_from(inputs / f"{index}.json").to_dict("records"))
                        if r["date"] >= "2024-01-01"] for index in ("sh000852", "sh000985")}
    write_json(out / "preview-data.json", preview)
    print(pd.DataFrame(comparison).query("one_way_cost == 0").to_string(index=False))
    print(json.dumps(clean(history), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
