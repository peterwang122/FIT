"""All-history CSI500 bull/bear search; source reads never mutate the DB."""
import argparse
from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import itertools
import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal
from app.services.csi500_swing_features import VERSION, cycle_labels, load_research_features
from csi1000_bear_swing import episodes, turning_points
from csi1000_bear_swing_v2 import all_outcomes

OUT = ROOT / "runtime/reports/csi500_swing"
POLICY = {
    "version": "csi500-all-history-v2", "all_history_is_development": True,
    "no_holdout": True, "cutoff": "22:30 Asia/Shanghai; next A-share session open",
    "labels": "User-approved major cycles; 2022 rally stays bear; 2026-07+ unclassified observation",
    "extremes": "5% confirmed close reversal mapped to intraday extreme; 120-session record and >=15% from opposite extreme; cycle anchors also included",
    "coverage_start": "2022-01-01", "max_color_day_pct": 35,
    "color_cap_scope": "Formal retrospective range 2022 onward, each strategy's own approved regime; no dilution by pre-2022 sessions",
    "max_independent_factors": 3, "max_or_branches": 2,
    "grid": {"percentiles": [10, 20, 30, 70, 80, 90], "wr": [5, 10, 20, 80, 90, 95],
             "rsi": [20, 25, 30, 35, 40, 45, 55, 60, 65, 70, 75, 80], "turn_sessions": [1, 3, 5]},
    "raw_grid": "Source-observation quantiles 10/20/30/70/80/90 calibrated once on all development observations; monthly repetitions never calibrate thresholds",
    "rank": "favorable5_first_pct - adverse3_first_pct - 2*median_MAE20 - 0.1*color_day_pct; ties fewer conditions then fingerprint",
    "beam": "Exhaustive single-factor scans; <=40 family representatives per price setup; <=80 selective representatives (coverage pattern+family) for two-branch OR; all trials retained",
    "early_late": "Long-history branch + explicit supplementary branch; late data never filled or made required before availability",
    "warning": "Retrospective optimization, NOT untouched out-of-sample evidence; historical coverage is not a future guarantee",
}


def save_json(path, value):
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2,
                  default=lambda v: v.item() if hasattr(v, "item") else str(v), allow_nan=False)


def save_snapshot(resume=False):
    from sqlalchemy import text
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        frame, catalog, tables = load_research_features(db, OUT / "source_cache", resume=resume)
        db.rollback()
    np.savez_compressed(OUT / "features.npz", values=frame.to_numpy(dtype=float), columns=np.asarray(frame.columns, dtype=str), dates=np.asarray(frame.index, dtype=str))
    save_json(OUT / "catalog.json", {k: asdict(v) for k, v in catalog.items()})
    save_json(OUT / "tables.json", tables)
    print("snapshot", frame.shape, "features", len(catalog), "as_of", frame.index[-1], flush=True)


def snapshot():
    with np.load(OUT / "features.npz", allow_pickle=False) as data:
        frame = pd.DataFrame(data["values"], index=data["dates"], columns=data["columns"])
    return frame, json.loads((OUT / "catalog.json").read_text())


def condition(field, op, value):
    return {"type": "numeric", "field": field, "operator": op, "value": float(value)}


def rule_id(rule):
    return sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()[:16]


def matches(frame, groups):
    matched = np.zeros(len(frame), bool)
    known_false = np.ones(len(frame), bool)
    for group in groups:
        hit, false = np.ones(len(frame), bool), np.zeros(len(frame), bool)
        for c in group["conditions"]:
            values = frame[c["field"]].to_numpy()
            present = np.isfinite(values)
            compare = values >= c["value"] if c["operator"] == "gte" else values <= c["value"]
            hit &= present & compare
            false |= present & ~compare
        matched |= hit
        known_false &= false
    return matched, matched | known_false


def extreme_labels(frame):
    result = []
    for pivot in turning_points(frame):
        side = pivot["side"]
        a, end = max(0, pivot["index"] - 5), pivot["confirmed_index"] + 1
        values = frame.low.to_numpy() if side == "low" else frame.high.to_numpy()
        i = a + int(np.argmin(values[a:end]) if side == "low" else np.argmax(values[a:end]))
        if i < 119:
            continue
        prior = frame.iloc[i - 119:i + 1]
        record = frame.low.iloc[i] <= prior.low.min() if side == "low" else frame.high.iloc[i] >= prior.high.max()
        change = (1 - frame.low.iloc[i] / prior.high.max()) * 100 if side == "low" else (frame.high.iloc[i] / prior.low.min() - 1) * 100
        if record and change >= 15:
            result.append({"index": i, "date": frame.index[i], "side": side, "price": float(values[i]), "opposite_move_pct": float(change), "confirmed_date": frame.index[pivot["confirmed_index"]], "kind": "120d-extreme"})
    _, pivots = cycle_labels(frame.index)
    for anchor, label in pivots[1:]:
        if anchor > "2026-06-30":
            continue
        positions = np.flatnonzero(frame.index >= anchor)
        if not len(positions):
            continue
        i = int(positions[0]); a, end = max(0, i - 3), min(len(frame), i + 4)
        side = "low" if label == "bull" else "high"
        values = frame.low.to_numpy() if side == "low" else frame.high.to_numpy()
        j = a + int(np.argmin(values[a:end]) if side == "low" else np.argmax(values[a:end]))
        result.append({"index": j, "date": frame.index[j], "side": side, "price": float(values[j]), "confirmed_date": anchor, "kind": "cycle-anchor", "boundary_regimes": ["bull", "bear"]})
    end_positions = np.flatnonzero(frame.index >= "2026-06-30")
    if len(end_positions):
        i = int(end_positions[0]); a, end = max(0, i - 3), min(len(frame), i + 4)
        j = a + int(np.argmax(frame.high.iloc[a:end].to_numpy()))
        result.append({"index": j, "date": frame.index[j], "side": "high", "price": float(frame.high.iloc[j]),
                       "confirmed_date": "2026-06-30", "kind": "cycle-end-anchor", "boundary_regimes": ["bull"]})
    return sorted({(r["index"], r["side"]): r for r in result}.values(), key=lambda r: (r["index"], r["side"]))


class Search:
    def __init__(self, frame, catalog, regime, side, extremes):
        self.f, self.catalog, self.regime, self.side = frame, catalog, regime, side
        labels, _ = cycle_labels(frame.index)
        self.inside = labels == regime
        self.labels = labels
        self.targets = [r["index"] for r in extremes if r["side"] == side and r["date"] >= POLICY["coverage_start"]
                        and (labels[r["index"]] == regime or regime in r.get("boundary_regimes", []))]
        out = all_outcomes(frame, side)
        self.out = {c: out[c].to_numpy() for c in out}
        self.attempts = []
        self.cache = {}
        self.masks = OrderedDict()

    def mask(self, rules):
        key = rule_id(rules)
        if key not in self.masks:
            self.masks[key] = matches(self.f, rules)
            if len(self.masks) > 512:
                self.masks.popitem(last=False)
        else:
            self.masks.move_to_end(key)
        return self.masks[key]

    def metrics(self, mask, inside=None):
        inside = self.inside if inside is None else inside
        indices = np.flatnonzero(mask & ~np.r_[False, mask[:-1]] & inside)
        complete = indices[np.asarray(self.out["complete_20d"][indices], dtype=bool)]
        n = len(complete)
        day_pct = 100 * float(mask[inside].mean()) if inside.any() else 0
        first = self.out["first_touch"][complete]
        good = 100 * float((first == "favorable").mean()) if n else None
        bad = 100 * float((first == "adverse").mean()) if n else None
        mae = float(np.median(self.out["mae_20d"][complete].astype(float))) if n else None
        return {"events": len(indices), "evaluated": n, "pending": len(indices) - n, "color_day_pct": day_pct,
                "favorable_first_pct": good, "adverse_first_pct": bad, "median_mae20": mae,
                "unknown_order": int((first == "unknown").sum()),
                "score": good - bad - 2 * mae - .1 * day_pct if n else -1000.0}

    def evaluate(self, rules, family, *, diagnostic=False, comparison=None):
        if family != "single":
            prepared = []
            for group in rules:
                conditions = list(group["conditions"])
                existing = {c["field"] for c in conditions}
                for field in list(existing):
                    meta = self.catalog[field]
                    gate = field + "-available"
                    if meta["transform"] != "availability" and gate in self.catalog and gate not in existing:
                        conditions.append(condition(gate, "gte", 1))
                prepared.append({"conditions": conditions})
            rules = prepared
        key = rule_id(rules)
        if key in self.cache:
            return self.cache[key]
        mask, known = self.mask(rules)
        fields = [c["field"] for g in rules for c in g["conditions"]]
        eligible = not diagnostic and all(self.catalog[k]["eligibility"] == "eligible" for k in fields)
        covered = sum(bool(mask[i]) for i in self.targets)
        metrics = self.metrics(mask, self.inside & known)
        formal_inside = self.inside & (self.f.index >= POLICY["coverage_start"])
        formal = self.metrics(mask, formal_inside & known)
        formal_color_pct = float(mask[formal_inside].mean()) * 100 if formal_inside.any() else 0
        post2022 = (self.f.index >= POLICY["coverage_start"]) & (self.f.index <= "2022-12-31")
        rejected = []
        if not eligible: rejected.append("publication_or_vintage_unverified")
        if covered != len(self.targets): rejected.append("extreme_coverage")
        if formal_color_pct > 35: rejected.append("color_days")
        if not metrics["evaluated"]: rejected.append("no_complete_outcomes")
        if not formal["evaluated"]: rejected.append("no_formal_complete_outcomes")
        # Unknown red/blue days cannot silently become no signal.
        if not known[post2022].all(): rejected.append("2022_missing")
        if family != "single":
            numeric_fields = [k for k in set(fields) if self.catalog[k]["transform"] != "availability"]
            factors = {re.sub(r"(-pct|-change-[0-9]+[dm])$", "", k) for k in numeric_fields}
            if len(factors) > 3:
                rejected.append("too_many_independent_factors")
            for a, b in itertools.combinations(numeric_fields, 2):
                if self.catalog[a]["family"] == self.catalog[b]["family"]: continue
                x, y = self.f[a].to_numpy(), self.f[b].to_numpy()
                common = np.isfinite(x) & np.isfinite(y)
                if common.sum() >= 100 and np.std(x[common]) and np.std(y[common]):
                    if abs(np.corrcoef(x[common], y[common])[0, 1]) >= .9:
                        rejected.append("highly_correlated_factors")
                        break
        trial = {"id": key, "regime": self.regime, "side": self.side, "family": family,
                 "rules": rules, "metrics": metrics, "covered": covered, "targets": len(self.targets),
                 "formal_metrics": {**formal, "color_day_pct": formal_color_pct},
                 "known_2022_pct": float(known[post2022].mean()) * 100,
                 "rejected": rejected, "diagnostic": not eligible}
        if comparison:
            baseline, baseline_known = self.mask(comparison)
            overlap = self.inside & known & baseline_known
            base_fields = {c["field"] for g in comparison for c in g["conditions"]}
            for field in set(fields) - base_fields:
                if self.catalog[field]["transform"] != "availability":
                    overlap &= self.f[field].notna().to_numpy()
            old, new = self.metrics(baseline, overlap), self.metrics(mask, overlap)
            trial["common_window"] = {"days": int(overlap.sum()), "baseline": old, "candidate": new,
                                      "delta_score": new["score"] - old["score"]}
        self.attempts.append(trial)
        self.cache[key] = trial
        return trial

    def thresholds(self, key):
        if key == "csi500-rsi14": return POLICY["grid"]["rsi"]
        if key == "csi500-wr14": return POLICY["grid"]["wr"]
        if self.catalog[key]["transform"] == "prior-percentile" or key.startswith("csi500-position-"):
            return POLICY["grid"]["percentiles"]
        return self.catalog[key]["candidate_thresholds"]

    def run(self):
        singleton, long, price = [], [], []
        for key in self.catalog:
            if not self.catalog[key]["valid_days"] or self.catalog[key]["transform"] == "availability":
                continue
            for op, threshold in itertools.product(("lte", "gte"), self.thresholds(key)):
                trial = self.evaluate([{"conditions": [condition(key, op, threshold)]}], "single")
                singleton.append(trial)
                if not trial["rejected"]:
                    long.append(trial)
                    if self.catalog[key]["family"] == "price": price.append(trial)
        print(self.regime, self.side, "singletons", len(singleton), "qualified", len(long), flush=True)
        # Every field/source receives a scan even when short or diagnostic.
        # Bounded family representatives avoid an uncontrolled Cartesian grid.
        reps = {}
        for t in sorted(singleton, key=lambda t: -t["metrics"]["score"]):
            key = t["rules"][0]["conditions"][0]["field"]
            if self.catalog[key]["eligibility"] == "eligible": reps.setdefault(self.catalog[key]["family"], t)
        extras = list(reps.values())[:40]
        price_setups = [t for t in singleton if not t["diagnostic"] and self.catalog[t["rules"][0]["conditions"][0]["field"]]["family"] == "price"]
        setups = sorted(price_setups, key=lambda t: -t["metrics"]["score"])[:20]
        # Include more selective price setups even when they miss a target; a
        # second explicit branch may cover it without making all days colored.
        selective = [t for t in singleton if self.catalog[t["rules"][0]["conditions"][0]["field"]]["family"] == "price"
                     and t["formal_metrics"]["color_day_pct"] <= 35 and not t["diagnostic"]]
        setups += sorted(selective, key=lambda t: -t["metrics"]["score"])[:20]
        combinations = []
        for setup, extra in itertools.product(setups, extras):
            a, c = setup["rules"][0]["conditions"], extra["rules"][0]["conditions"]
            if self.catalog[a[0]["field"]]["family"] == self.catalog[c[0]["field"]]["family"]: continue
            rules = [{"conditions": a + c}]
            combinations.append(self.evaluate(rules, "price+source", comparison=setup["rules"]))
            for n in (1, 3, 5):
                turn = condition(f"csi500-return-{n}d", "gte" if self.side == "low" else "lte", 0)
                combinations.append(self.evaluate([{"conditions": a + c + [turn]}], "price+turn+source", comparison=setup["rules"]))
        selective_reps = {}
        for trial in sorted([*singleton, *combinations], key=lambda t: -t["metrics"]["score"]):
            if trial["diagnostic"] or trial["formal_metrics"]["color_day_pct"] > 35 or not trial["covered"]:
                continue
            mask, _ = self.mask(trial["rules"])
            signature = tuple(bool(mask[i]) for i in self.targets)
            families = tuple(sorted({self.catalog[c["field"]]["family"] for g in trial["rules"] for c in g["conditions"]}))
            selective_reps.setdefault((signature, families), trial)
        alternatives = list(selective_reps.values())[:80]
        for left, right in itertools.combinations(alternatives, 2):
            a, _ = self.mask(left["rules"])
            c, _ = self.mask(right["rules"])
            if not all(a[i] or c[i] for i in self.targets):
                continue
            combinations.append(self.evaluate(left["rules"] + right["rules"], "two-branch-coverage"))
        long = [t for t in [*long, *combinations] if not t["rejected"] and all(
            (self.catalog[c["field"]]["first_available_date"] or "9999") <= POLICY["coverage_start"]
            for g in t["rules"] for c in g["conditions"] if self.catalog[c["field"]]["transform"] != "availability")]
        if not long:
            save_json(OUT / f"{self.regime}_{self.side}_attempts.json", self.attempts)
            raise RuntimeError(f"{self.regime}/{self.side}: no fully covered base candidate; do not relax")
        base = sorted(long, key=lambda t: (-t["metrics"]["score"], len(t["rules"][0]["conditions"]), t["id"]))[0]
        # Explicit alternatives preserve early coverage; missing late fields
        # never default to a value. A true base makes an OR rule determinate.
        for extra in [*singleton, *combinations]:
            if len(base["rules"]) + len(extra["rules"]) > 2: continue
            if extra["diagnostic"] or extra["formal_metrics"]["color_day_pct"] > 35: continue
            branch = []
            for group in extra["rules"]:
                conditions = list(group["conditions"])
                # Deterministic availability gate, NOT a fitted date cutoff.
                # Before source inception/warmup the branch is explicitly off;
                # after inception a missing value remains missing.
                late = [c["field"] for c in conditions if self.catalog[c["field"]]["transform"] != "availability"
                        and (self.catalog[c["field"]]["first_available_date"] or "9999") > POLICY["coverage_start"]]
                for key in late:
                    gate = key + "-available"
                    if gate not in self.catalog:
                        first = self.catalog[key]["first_available_date"]
                        self.f[gate] = (self.f.index >= (first or "9999")).astype(float)
                        self.catalog[gate] = {**self.catalog[key], "key": gate, "label": self.catalog[key]["label"] + " 数据完成预热",
                                             "family": "availability", "transform": "availability", "candidate_thresholds": [1], "unit": "0/1", "base_field": key}
                    if not any(c["field"] == gate for c in conditions):
                        conditions.append(condition(gate, "gte", 1))
                branch.append({"conditions": conditions})
            rules = base["rules"] + branch
            fields = {c["field"] for g in rules for c in g["conditions"]}
            families = {self.catalog[k]["family"] for k in fields if self.catalog[k]["family"] != "availability"}
            if len(families) > 3: continue
            trial = self.evaluate(rules, "explicit-supplement", comparison=base["rules"])
            # Incremental improvement must be real on the same known days.
            if trial.get("common_window", {}).get("delta_score", 0) <= 0 and not trial["rejected"]:
                trial["rejected"].append("no_incremental_improvement")
        # A late source may only replace/extend a base after comparing the
        # exact same visible sessions, never by using different years' returns.
        base_mask, base_known = self.mask(base["rules"])
        for trial in self.attempts:
            fields = {c["field"] for g in trial["rules"] for c in g["conditions"]
                      if self.catalog[c["field"]]["transform"] != "availability"}
            late = {k for k in fields if (self.catalog[k]["first_available_date"] or "9999") > POLICY["coverage_start"]}
            if trial["rejected"] or not late:
                continue
            mask, known = self.mask(trial["rules"])
            overlap = self.inside & known & base_known
            for field in late:
                overlap &= self.f[field].notna().to_numpy()
            old, new = self.metrics(base_mask, overlap), self.metrics(mask, overlap)
            trial["common_window"] = {"days": int(overlap.sum()), "baseline": old, "candidate": new,
                                      "delta_score": new["score"] - old["score"]}
            if trial["common_window"]["delta_score"] <= 0:
                trial["rejected"].append("no_incremental_improvement")
        qualified = [t for t in self.attempts if not t["rejected"]]
        chosen = sorted(qualified, key=lambda t: (-t["metrics"]["score"], sum(len(g["conditions"]) for g in t["rules"]), t["id"]))[0]
        print(self.regime, self.side, "trials", len(self.attempts), "chosen", chosen["rules"], chosen["metrics"], flush=True)
        return chosen, base


def research():
    f, catalog = snapshot()
    gates = {}
    for key, meta in list(catalog.items()):
        first = meta["first_available_date"]
        if meta["eligibility"] != "eligible" or not first or first <= POLICY["coverage_start"] or meta["transform"] == "availability":
            continue
        gate = key + "-available"
        if gate not in f.columns:
            gates[gate] = (f.index >= first).astype(float)
        catalog[gate] = {**meta, "key": gate, "label": meta["label"] + " 数据完成预热", "family": "availability",
                         "transform": "availability", "candidate_thresholds": [1], "unit": "0/1", "base_field": key}
    f = pd.concat([f, pd.DataFrame(gates, index=f.index)], axis=1)
    extremes = extreme_labels(f)
    _, cycles = cycle_labels(f.index)
    models, attempt_files, increment, attempt_count = {}, [], [], 0
    for regime in ("bull", "bear"):
        model, searches = {}, {}
        for side in ("low", "high"):
            search = Search(f, catalog, regime, side, extremes)
            model[side], baseline = search.run()
            searches[side] = search
            trial_file = f"{regime}_{side}_attempts.json"
            save_json(OUT / trial_file, search.attempts)
            attempt_files.append(trial_file)
            attempt_count += len(search.attempts)
            # Both ETF sources and every eligible/diagnostic feature are
            # evaluated against a baseline on genuinely overlapping dates.
            per_field = {}
            for trial in search.attempts:
                if trial["family"] != "single": continue
                key = trial["rules"][0]["conditions"][0]["field"]
                present = f[key].notna().to_numpy() & search.inside
                mask, _ = search.mask(trial["rules"])
                base_mask, _ = search.mask(baseline["rules"])
                m, old = search.metrics(mask, present), search.metrics(base_mask, present)
                comparable = bool(m["evaluated"] and old["evaluated"])
                row = {"regime": regime, "side": side, "field": key, "source": catalog[key]["source"],
                       "overlap_days": int(present.sum()), "rules": trial["rules"], "candidate": m,
                       "baseline": old, "delta_score": m["score"] - old["score"] if comparable else None,
                       "comparison_status": "comparable" if comparable else "no_evaluated_baseline_or_candidate",
                       "eligibility": catalog[key]["eligibility"]}
                old_row = per_field.get(key)
                if old_row is None or (comparable and (old_row["delta_score"] is None or row["delta_score"] > old_row["delta_score"])):
                    per_field[key] = row
            increment.extend(per_field.values())
        red, red_known = matches(f, model["low"]["rules"])
        blue, blue_known = matches(f, model["high"]["rules"])
        # Sell precedence is part of coverage, not a post-install surprise.
        low_targets = searches["low"].targets
        if any(not red[i] or blue[i] for i in low_targets):
            compatible = []
            for trial in searches["high"].attempts:
                if trial["rejected"]: continue
                mask, _ = searches["high"].mask(trial["rules"])
                if not any(mask[i] for i in low_targets): compatible.append(trial)
            if not compatible:
                raise RuntimeError(f"{regime}: no high rule preserves low coverage after sell-first; not installing")
            model["high"] = sorted(compatible, key=lambda t: (-t["metrics"]["score"], sum(len(g["conditions"]) for g in t["rules"]), t["id"]))[0]
            blue, blue_known = matches(f, model["high"]["rules"])
        model["extreme_coverage"] = [{**r, "hit": bool(red[r["index"]] and not blue[r["index"]]) if r["side"] == "low" else bool(blue[r["index"]])}
                                     for r in extremes if r["index"] in (low_targets if r["side"] == "low" else searches["high"].targets)]
        assert all(r["hit"] for r in model["extreme_coverage"])
        inside = searches["low"].inside & (f.index >= POLICY["coverage_start"])
        model["effective_formal_color_pct"] = {"red": float((red & ~blue)[inside].mean()) * 100, "blue": float(blue[inside].mean()) * 100}
        assert max(model["effective_formal_color_pct"].values()) <= POLICY["max_color_day_pct"]
        model["effective_metrics"] = {"low": searches["low"].metrics(red & ~blue, searches["low"].inside & red_known & blue_known),
                                      "high": searches["high"].metrics(blue, searches["high"].inside & blue_known)}
        daily = f[["open", "high", "low", "close"]].copy()
        daily["cycle"] = searches["low"].labels
        daily["red"], daily["blue"] = red, blue
        daily["known"] = red_known & blue_known
        daily["as_of_at"] = daily.index + "T22:30:00+08:00"
        daily.to_csv(OUT / f"{regime}_daily.csv", index_label="date")
        model["annual"] = {}
        for year in range(2005, int(f.index[-1][:4]) + 1):
            inside = (f.index >= f"{year}-01-01") & (f.index <= f"{year}-12-31")
            model["annual"][str(year)] = {s: searches[s].metrics(red & ~blue if s == "low" else blue,
                inside & searches[s].inside & (red_known & blue_known)) for s in searches}
        for side, mask in (("low", red & ~blue), ("high", blue)):
            pd.DataFrame(episodes(f, pd.Series(mask, index=f.index), side)).to_csv(OUT / f"{regime}_{side}_events.csv", index=False)
        model["config_fingerprint"] = rule_id({s: model[s]["rules"] for s in ("low", "high")})
        models[regime] = model
    selected = {c["field"] for m in models.values() for s in ("low", "high") for g in m[s]["rules"] for c in g["conditions"]}
    studied = {r["field"] for r in increment}
    for key, meta in catalog.items():
        meta["research_status"] = "selected" if key in selected else "scanned" if key in studied else "blocked"
        meta["selection_reason"] = "Chosen fixed-grid rule" if key in selected else "Not selected after common-window comparison" if key in studied else "No valid observations/insufficient warmup/publication data"
    save_json(OUT / "catalog.json", catalog)
    np.savez_compressed(OUT / "features.npz", values=f.to_numpy(dtype=float), columns=np.asarray(f.columns, dtype=str), dates=np.asarray(f.index, dtype=str))
    save_json(OUT / "attempts.json", {"files": attempt_files, "count": attempt_count})
    save_json(OUT / "incremental.json", increment)
    pd.DataFrame([{k: v for k, v in r.items() if k not in ("rules", "candidate", "baseline")} for r in increment]).to_csv(OUT / "incremental.csv", index=False)
    report = {"policy": POLICY, "as_of": f.index[-1], "data_sha256": sha256((OUT / "features.npz").read_bytes()).hexdigest(),
              "cycles": cycles, "models": models, "feature_count": len(catalog), "studied_feature_count": len(studied),
              "attempt_count": attempt_count, "selected_fields": sorted(selected), "production_updated": False}
    save_json(OUT / "report.json", report)
    lines = ["# 中证500牛市、熊市波段：全数据历史优化", "", "全部可用历史均为开发数据，不设训练/验证/样本外；历史覆盖不保证未来。", "",
             "周期按用户确认的大周期：2022反弹属于熊市；2024-09-18起为牛市；2026-07起转弱观察不参与所属环境选型。",
             "极端标签只作事后评价；22:30收盘后信号、次日开盘执行，不能解释为盘中已买到最低价。", "",
             f"数据截至 {f.index[-1]}；{len(catalog)}项原值/派生候选，实际扫描{len(studied)}项，{attempt_count}次规则尝试。",
             "原始数据表及阻断原因见tables.json；逐项覆盖、可用时间、单位及研究结果见catalog.json；全部尝试见attempts.json。", "",
             "## 来源与发布时间", "",
             "国内收盘报价按当日18:00前的可见行情；融资采用真实下一交易日制度披露截止上界，不是伪称抓取时间。",
             "银行、全球及美国利率信用数据使用库内available_at；未核验的旧宏观、汇率、情绪及复合风险分仅作诊断研究，不进入正式规则。",
             "货币宏观按独立月份和M1口径分开研究；不能核验首次发布版本的序列不得装作严格实时回测。", ""]
    for regime, m in models.items():
        lines += ["## " + ("牛市" if regime == "bull" else "熊市"), ""]
        for s in ("low", "high"):
            lines += [("红色低位" if s == "low" else "蓝色高位") + "：" + json.dumps(m[s]["rules"], ensure_ascii=False),
                      "指标：" + json.dumps(m[s]["metrics"], ensure_ascii=False), ""]
        lines += ["| 极端日期 | 类型 | 当日实际命中（卖出优先） |", "|---|---|---|"]
        for r in m["extreme_coverage"]: lines.append(f"|{r['date']}|{r['side']}|{r['hit']}|")
    lines += ["", "## 两套ETF期权的共同窗口增量", "", "两来源分开研究，不平均P/C、不混用隐波口径。下列是各来源每端最高单因子增量，不等同于最终入选。", "",
              "| 环境 | 方向 | 来源 | 扫描字段数 | 最高增量分 |", "|---|---|---|---:|---:|"]
    for regime, side, source in itertools.product(("bull", "bear"), ("low", "high"), ("sse:510500", "szse:159922")):
        rows = [r for r in increment if r["regime"] == regime and r["side"] == side and source in r["source"]]
        assert rows, "ETF source was not studied: " + source
        deltas = [r["delta_score"] for r in rows if r["delta_score"] is not None]
        best = f"{max(deltas):.2f}" if deltas else "共同窗口缺少可评价区域"
        lines.append(f"|{regime}|{side}|{source}|{len(rows)}|{best}|")
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("research complete", report["selected_fields"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    save_json(OUT / "protocol.json", POLICY)
    if args.refresh or args.resume or not (OUT / "features.npz").exists(): save_snapshot(resume=args.resume)
    if not args.snapshot_only: research()
