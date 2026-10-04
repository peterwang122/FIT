"""Explicit canonical-source combinations, separate from the original audit."""
import itertools
import json

import pandas as pd

from csi500_coverage_restudy import OUT, Study, base_key
from csi500_swing import condition, extreme_labels, save_json, snapshot
from csi1000_bear_swing import turning_points
from review_csi500_coverage import metadata_field


SOURCES = {
    "margin_trading_daily_data:SSE+SZSE", "Causal price+T-1 financing components",
    "futures_daily_data:numeric IC max OI", "cn_bank_liquidity_daily", "global_risk_asset_daily",
    "index_us_credit_spread_daily", "index_us_treasury_yield_daily",
}


def keys_for(catalog, era):
    for key, meta in catalog.items():
        own_option = "option-sse-510500-" in key or "option-szse-159922-" in key
        if meta["eligibility"] != "eligible" or not meta["valid_days"] or metadata_field(key): continue
        if meta["transform"] == "availability": continue
        if era == "options" and not own_option: continue
        if era == "long" and (meta["first_available_date"] or "9999") > "2022-01-01": continue
        if not (meta["source"] in SOURCES or own_option or key.startswith("csi500-dashboard-sh000905-")): continue
        if meta["transform"] == "prior-percentile" or "-change-" in key: yield key


def setups(side):
    for key in ("csi500-rsi14", "csi500-wr14", *[f"csi500-position-{n}d{suffix}" for n in (20, 60, 120) for suffix in ("", "-pct")]):
        if key == "csi500-rsi14": values = [20, 30, 40] if side == "low" else [60, 70, 80]
        elif key == "csi500-wr14": values = [80, 90, 95] if side == "low" else [5, 10, 20]
        else: values = [10, 20, 30] if side == "low" else [70, 80, 90]
        higher = (side == "low") == (key == "csi500-wr14")
        for value in values: yield condition(key, "gte" if higher else "lte", value)


def run():
    frame, catalog = snapshot()
    pivots, extremes = turning_points(frame), extreme_labels(frame)
    selection = json.loads((OUT / "selection.json").read_text())
    for side in ("low", "high"):
        outcomes = pd.read_pickle(OUT / f"{side}_outcomes.pkl")
        for era, regime in itertools.product(("long", "options"), ("bull", "bear")):
            path = OUT / f"{era}_{regime}_{side}_extension.jsonl"
            study = Study(frame, catalog, regime, side, era, outcomes, pivots, extremes, log=False)
            # Keep base trials immutable and do not count duplicates twice.
            with (OUT / f"{era}_{regime}_{side}_attempts.jsonl").open() as stream:
                study.seen.update(json.loads(line)["id"] for line in stream)
            study.stream.close()
            study.stream = path.open("w", encoding="utf-8")
            source_keys = list(keys_for(catalog, era))
            representatives = {}
            for key in source_keys:
                thresholds = [10, 20, 30, 70, 80, 90] if catalog[key]["transform"] == "prior-percentile" else [0]
                for op, threshold, location in itertools.product(("lte", "gte"), thresholds, setups(side)):
                    extra = condition(key, op, threshold)
                    for turn in (0, 1, 3, 5):
                        conditions = [location, extra]
                        if turn:
                            conditions.append(condition(f"csi500-return-{turn}d", "gte" if side == "low" else "lte", 0))
                        trial = study.evaluate([{"conditions": conditions}], "canonical-source+location+turn")
                        if trial is None or any(reason in trial["rejected"] for reason in (
                            "coverage_gaps", "long_signal_region", "median_region_too_long", "color_density",
                            "too_few_events", "too_few_formal_events")): continue
                        signature = (base_key(key), tuple(trial["missed_extremes"]))
                        old = representatives.get(signature)
                        if old is None or Study.rank(trial) < Study.rank(old): representatives[signature] = trial
            candidates = sorted(representatives.values(), key=Study.rank)
            # Retain covered and missed patterns within each physical source,
            # rather than letting one very short or unrelated index dominate.
            by_source = {}
            for trial in candidates:
                fields = [c["field"] for c in trial["rules"][0]["conditions"] if c["field"] in source_keys]
                source = catalog[fields[0]]["source"]
                signature = (source, tuple(trial["missed_extremes"]))
                by_source.setdefault(signature, trial)
            candidates = sorted(by_source.values(), key=Study.rank)[:100]
            for a, b in itertools.combinations(candidates, 2):
                fields = {base_key(c["field"]) for t in (a, b) for g in t["rules"] for c in g["conditions"]}
                if len(fields) > 3: continue
                study.evaluate(a["rules"] + b["rules"], "canonical-two-branch")
            study.stream.close()
            selection["models"][era + "_" + regime][side]["extension"] = {
                "file": path.name, "source_keys": source_keys, "summary": dict(study.summary),
                "qualified_count": len(study.survivors),
            }
            save_json(OUT / "selection.json", selection)
            print(era, regime, side, "canonical fields", len(source_keys), "trials", study.summary["trials"],
                  "qualified", len(study.survivors), flush=True)
    print("Source extension complete; no production writes", flush=True)


if __name__ == "__main__":
    run()
