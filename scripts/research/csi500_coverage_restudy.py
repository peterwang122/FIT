"""Coverage-specific re-study; only local report files are written.

Signal masks remain causal numeric rules. Duration limits are admission tests,
not an after-the-fact truncation of painted candles.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
import itertools
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from csi500_swing import condition, extreme_labels, matches, rule_id, save_json, snapshot
from csi1000_bear_swing import episodes, turning_points
from csi1000_bear_swing_v2 import all_outcomes
from app.services.csi500_swing_features import cycle_labels


OUT = Path(__file__).resolve().parents[2] / "runtime/reports/csi500_coverage_restudy"
POLICY = {
    "version": "csi500-coverage-restudy-v1",
    "all_history_is_development": True,
    "no_holdout": True,
    "cutoff": "22:30 Asia/Shanghai; next actual A-share session open",
    "eras": {
        "long": "Sources warmed up by 2022-01-01; source's entire known history is used",
        "options": "Actual 500ETF option coverage, each candidate after its own warmup; no pre-listing fallback",
    },
    "max_consecutive_days": 7,
    "max_median_consecutive_days": 2,
    "max_color_pct": 20,
    "minimum_evaluated_events": 8,
    "minimum_formal_events": 4,
    "minimum_pivot_coverage_pct": 50,
    "extremes": "Same-day hard extreme coverage remains required in the candidate's covered range",
    "pivot_window": "At most 5 sessions early or 3 late, using region onset, not a months-long region",
    "max_conditions_per_branch": 3,
    "max_branches": 2,
    "grid": {"percentile": [10, 20, 30, 70, 80, 90], "turn": [1, 3, 5]},
    "rank": "win5-first%-loss3-first%-2*medianMAE20+0.5*pivotCoverage%-0.2*color%-medianRegionDays",
    "raw_price_levels": "Excluded as timing thresholds: index rebasing and secular level are not a repeatable turning condition",
    "comparison": "Same source-covered sessions and same outcomes; absent evaluated events is not a numeric delta",
    "publication": "Diagnostic/vintage-unverified fields scanned but not eligible for deployment",
    "search": "All fields single-factor scan; bounded family/coverage representatives for price+source+turn and two-branch pairs",
    "warning": "All-history retrospective optimization, no untouched validation and no future extrema guarantee",
}


def spans(mask):
    mask = np.asarray(mask, dtype=bool)
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.flatnonzero(mask & ~np.r_[mask[1:], False])
    return starts, ends, ends - starts + 1


def base_key(key):
    import re
    return re.sub(r"(-pct|-change-[0-9]+[dm])$", "", key)


def raw_level(meta, key):
    return meta["transform"] != "prior-percentile" and "-change-" not in key and (
        meta["source"] in {"index_daily_data", "index_hk_daily_data"}
        and key.endswith("close-price"))


class Study:
    def __init__(self, frame, catalog, regime, side, era, outcomes, pivots, extremes, *, log=True):
        self.f, self.c = frame, catalog
        self.regime, self.side, self.era = regime, side, era
        self.labels = cycle_labels(frame.index)[0]
        self.own = self.labels == regime
        self.dates = frame.index.to_numpy()
        self.out = {k: outcomes[k].to_numpy() for k in outcomes}
        self.pivots = np.asarray([p["index"] for p in pivots if p["side"] == side
                                 and self.own[p["index"]]], dtype=int)
        self.extremes = [e for e in extremes if e["side"] == side
                         and (self.own[e["index"]] or regime in e.get("boundary_regimes", []))]
        self.survivors, self.seen, self.summary = [], set(), defaultdict(int)
        self.representatives = {}
        self.stream = ((OUT / f"{era}_{regime}_{side}_attempts.jsonl").open("w", encoding="utf-8")
                       if log else io.StringIO())

    def stats(self, mask, known, start):
        covered = self.dates >= start
        own = self.own & covered
        onset, ends, length = spans(mask & covered)
        indices = onset[own[onset]]
        complete = indices[self.out["complete_20d"][indices].astype(bool)]
        n = len(complete)
        first = self.out["first_touch"][complete]
        good = float((first == "favorable").mean() * 100) if n else None
        bad = float((first == "adverse").mean() * 100) if n else None
        mae = float(np.median(self.out["mae_20d"][complete].astype(float))) if n else None
        pct = float(mask[own].mean() * 100) if own.any() else None
        formal = own & (self.dates >= "2022-01-01")
        fs, fe, fl = spans(mask & (self.dates >= max(start, "2022-01-01")))
        targets = self.pivots[self.dates[self.pivots] >= start]
        distances = indices[None, :] - targets[:, None]
        pivot_hit = ((distances >= -5) & (distances <= 3)).any(axis=1)
        pc = float(pivot_hit.mean() * 100) if len(targets) else None
        formal_indices = complete[self.dates[complete] >= "2022-01-01"]
        own_lengths = length[own[onset]]
        median_length = float(np.median(own_lengths)) if len(own_lengths) else None
        return {
            "events": len(indices), "evaluated": n, "formal_evaluated": len(formal_indices),
            "color_pct": pct, "formal_color_pct": float(mask[formal].mean() * 100) if formal.any() else None,
            "known_pct": float(known[own].mean() * 100) if own.any() else 0,
            "favorable_first_pct": good, "adverse_first_pct": bad, "median_mae20": mae,
            "median_return20": float(np.median(self.out["return_20d"][complete].astype(float))) if n else None,
            "unknown_order": int((first == "unknown").sum()),
            "pivot_count": len(targets), "covered_pivots": int(pivot_hit.sum()), "pivot_coverage_pct": pc,
            "median_region_days": median_length,
            "max_region_days": int(length.max()) if len(length) else 0,
            "formal_max_region_days": int(fl.max()) if len(fl) else 0,
            "score": good - bad - 2 * mae + .5 * (pc or 0) - .2 * (pct or 0) - median_length if n else None,
        }

    def evaluate(self, rules, family, baseline=None, record=True):
        fingerprint = rule_id(rules)
        if fingerprint in self.seen:
            return None
        self.seen.add(fingerprint)
        keys = {c["field"] for g in rules for c in g["conditions"]}
        times = [self.c[k].get("first_available_date") for k in keys]
        start = max(times) if all(times) else "9999-12-31"
        mask, known = matches(self.f, rules)
        covered = self.dates >= start
        # A pre-warmup mask is not made into an earlier supplemental strategy.
        mask &= covered
        m = self.stats(mask, known, start)
        targets = [e for e in self.extremes if e["date"] >= max(start, "2022-01-01")]
        missed = [e["date"] for e in targets if not mask[e["index"]]]
        reasons = []
        if not all(self.c[k]["eligibility"] == "eligible" for k in keys):
            reasons.append("publication_or_vintage_unverified")
        if any(raw_level(self.c[k], k) for k in keys): reasons.append("secular_raw_index_level")
        if self.era == "long" and start > "2022-01-01": reasons.append("late_source")
        if self.era == "options" and not any("option-sse-510500-" in k or "option-szse-159922-" in k for k in keys):
            reasons.append("not_500etf_option")
        if len({base_key(k) for k in keys}) > 3: reasons.append("too_many_factors")
        if max(len(g["conditions"]) for g in rules) > 3: reasons.append("too_many_conditions")
        if m["known_pct"] < 95: reasons.append("coverage_gaps")
        if m["evaluated"] < POLICY["minimum_evaluated_events"]: reasons.append("too_few_events")
        if m["formal_evaluated"] < POLICY["minimum_formal_events"]: reasons.append("too_few_formal_events")
        if m["formal_max_region_days"] > POLICY["max_consecutive_days"]: reasons.append("long_signal_region")
        if (m["median_region_days"] or 0) > POLICY["max_median_consecutive_days"]: reasons.append("median_region_too_long")
        if (m["formal_color_pct"] or 0) > POLICY["max_color_pct"]: reasons.append("color_density")
        if (m["pivot_coverage_pct"] or 0) < POLICY["minimum_pivot_coverage_pct"]: reasons.append("ordinary_pivot_coverage")
        if missed: reasons.append("same_day_extreme_coverage")
        result = {"id": fingerprint, "rules": rules, "family": family, "start_date": start,
                  "metrics": m, "missed_extremes": missed, "extreme_count": len(targets), "rejected": reasons}
        if baseline is not None:
            bm, bk = matches(self.f, baseline["rules"])
            common = covered & known & bk
            x = self.stats(bm & common, bk, start)
            y = self.stats(mask & common, known, start)
            result["common_window"] = {"start": start, "baseline": x, "candidate": y,
                                       "delta_score": y["score"] - x["score"] if x["score"] is not None and y["score"] is not None else None}
        if record:
            self.stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
        self.summary["trials"] += 1
        for reason in reasons: self.summary[reason] += 1
        if not reasons:
            self.survivors.append(result)
        return result

    def bounds(self, key):
        m = self.c[key]
        if m["transform"] == "availability": return []
        if m["transform"] == "prior-percentile" or key.startswith("csi500-position-"):
            return POLICY["grid"]["percentile"]
        if key == "csi500-wr14": return [5, 10, 20, 80, 90, 95]
        if key == "csi500-rsi14": return [20, 30, 40, 50, 60, 70, 80]
        return m["candidate_thresholds"]

    def run(self):
        seeds = []
        for key in self.c:
            meta = self.c[key]
            if not meta["valid_days"] or meta["transform"] == "availability": continue
            if key not in self.f: continue
            for op, threshold in itertools.product(("lte", "gte"), self.bounds(key)):
                trial = self.evaluate([{"conditions": [condition(key, op, threshold)]}], "single")
                if trial is None or trial["metrics"]["score"] is None: continue
                timing_ok = meta["eligibility"] == "eligible" and not raw_level(meta, key)
                if self.era == "long": timing_ok &= (meta["first_available_date"] or "9999") <= "2022-01-01"
                if self.era == "options": timing_ok &= "option-sse-510500-" in key or "option-szse-159922-" in key
                if not timing_ok: continue
                # Representatives retain differing hard-extreme coverage,
                # not only a lucky best score within one source family.
                signature = (meta["family"], tuple(trial["missed_extremes"]))
                old = self.representatives.get(signature)
                if old is None or self.rank(trial) < self.rank(old): self.representatives[signature] = trial
                if meta["family"] == "price": seeds.append(trial)
        print(self.era, self.regime, self.side, "single scan", self.summary["trials"], flush=True)
        # Price-position direction is fixed a priori, not reversed to fit.
        setups = []
        for key in ("csi500-wr14", "csi500-rsi14", *[f"csi500-position-{n}d{suffix}" for n in (20, 60, 120) for suffix in ("", "-pct")]):
            high = (self.side == "low") == (key == "csi500-wr14")
            limits = [80, 90, 95] if key.endswith("wr14") and high else [5, 10, 20] if key.endswith("wr14") else ([20, 30, 40] if self.side == "low" and key.endswith("rsi14") else [60, 70, 80] if key.endswith("rsi14") else [10, 20, 30] if self.side == "low" else [70, 80, 90])
            for value in limits:
                setups.append([condition(key, "gte" if high else "lte", value)])
        extras = sorted(self.representatives.values(), key=self.rank)[:100]
        for setup in setups:
            for n in POLICY["grid"]["turn"]:
                turn = condition(f"csi500-return-{n}d", "gte" if self.side == "low" else "lte", 0)
                self.evaluate([{"conditions": setup + [turn]}], "position+turn")
            for extra in extras:
                extra_conditions = extra["rules"][0]["conditions"]
                if extra_conditions[0]["field"] == setup[0]["field"]: continue
                combo = setup + extra_conditions
                self.evaluate([{"conditions": combo}], "position+source", extra)
                for n in POLICY["grid"]["turn"]:
                    turn = condition(f"csi500-return-{n}d", "gte" if self.side == "low" else "lte", 0)
                    self.evaluate([{"conditions": combo + [turn]}], "position+source+turn", extra)
        self.stream.flush()
        # A union must meet duration/coverage again. It is not painted by
        # clipping each constituent branch after a fixed number of days.
        candidates = []
        with (OUT / f"{self.era}_{self.regime}_{self.side}_attempts.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                trial = json.loads(line)
                if any(r in trial["rejected"] for r in ("publication_or_vintage_unverified", "secular_raw_index_level", "late_source", "not_500etf_option", "coverage_gaps", "long_signal_region", "median_region_too_long", "too_many_factors", "too_many_conditions")): continue
                candidates.append(trial)
        representative = {}
        for trial in sorted(candidates, key=self.rank):
            fields = {c["field"] for g in trial["rules"] for c in g["conditions"]}
            sig = (tuple(trial["missed_extremes"]), tuple(sorted(self.c[k]["family"] for k in fields)))
            representative.setdefault(sig, trial)
        candidates = list(representative.values())[:80]
        for left, right in itertools.combinations(candidates, 2):
            if len({base_key(c["field"]) for t in (left, right) for g in t["rules"] for c in g["conditions"]}) > 3: continue
            self.evaluate(left["rules"] + right["rules"], "two-branch")
        self.stream.close()
        ranked = sorted(self.survivors, key=self.rank)
        print(self.era, self.regime, self.side, "qualified", len(ranked), "trials", self.summary["trials"], flush=True)
        save_json(OUT / f"{self.era}_{self.regime}_{self.side}_ranked.json", ranked[:50])
        return {"qualified_count": len(ranked), "summary": dict(self.summary), "ranked": ranked[:50]}

    @staticmethod
    def rank(trial):
        m = trial["metrics"]
        return (-(m["score"] if m["score"] is not None else -1000), len(trial["rejected"]),
                sum(len(g["conditions"]) for g in trial["rules"]), trial["id"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--era", choices=("long", "options", "all"), default="all")
    parser.add_argument("--regime", choices=("bull", "bear", "all"), default="all")
    parser.add_argument("--side", choices=("low", "high", "all"), default="all")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    save_json(OUT / "protocol.json", POLICY)
    frame, catalog = snapshot()
    extremes, pivots = extreme_labels(frame), turning_points(frame)
    output_path = OUT / "selection.json"
    output = json.loads(output_path.read_text()) if output_path.exists() else {
        "policy": POLICY, "as_of": frame.index[-1], "models": {}, "production_updated": False,
        "source_snapshot": "runtime/reports/csi500_swing/features.npz"}
    assert output["policy"] == POLICY and output["as_of"] == frame.index[-1], "Do not mix study versions"
    for side in (("low", "high") if args.side == "all" else (args.side,)):
        outcomes_path = OUT / f"{side}_outcomes.pkl"
        if outcomes_path.exists():
            outcomes = pd.read_pickle(outcomes_path)
            assert len(outcomes) == len(frame), "Stale outcomes cache"
        else:
            outcomes = all_outcomes(frame, side)
            outcomes.to_pickle(outcomes_path)
        for era in (("long", "options") if args.era == "all" else (args.era,)):
            for regime in (("bull", "bear") if args.regime == "all" else (args.regime,)):
                study = Study(frame, catalog, regime, side, era, outcomes, pivots, extremes)
                output["models"].setdefault(era + "_" + regime, {})[side] = study.run()
                save_json(output_path, output)
    print("Research only; saved strategies unchanged", flush=True)


if __name__ == "__main__":
    main()
