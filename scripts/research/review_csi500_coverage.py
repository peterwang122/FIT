"""Review narrowing candidates, without altering any saved strategy or source."""
import json

import numpy as np
import pandas as pd

from csi500_coverage_restudy import OUT, POLICY, Study, spans
from csi500_swing import extreme_labels, matches, save_json, snapshot
from csi1000_bear_swing import episodes, turning_points


def price_location(condition, side):
    key, op, value = condition["field"], condition["operator"], condition["value"]
    if key == "csi500-wr14":
        return op == ("gte" if side == "low" else "lte") and (value >= 80 if side == "low" else value <= 20)
    if key == "csi500-rsi14":
        return op == ("lte" if side == "low" else "gte") and (value <= 40 if side == "low" else value >= 60)
    if key.startswith("csi500-position-"):
        return op == ("lte" if side == "low" else "gte") and (value <= 30 if side == "low" else value >= 70)
    return False


def metadata_field(key):
    return any(part in key for part in ("risk-free-rate", "strike-count", "minute-count", "mid-quote-count",
                                       "-put-25d-strike", "-call-25d-strike"))


def semantic_reasons(trial, side):
    reasons = []
    if not all(any(price_location(c, side) for c in g["conditions"]) for g in trial["rules"]):
        reasons.append("each_branch_needs_own_index_location")
    if any(metadata_field(c["field"]) for g in trial["rules"] for c in g["conditions"]):
        reasons.append("option_calculation_metadata_not_market_pressure")
    metrics = trial["metrics"]
    if metrics["favorable_first_pct"] is None or metrics["favorable_first_pct"] < metrics["adverse_first_pct"]:
        reasons.append("negative_first_touch_edge")
    return reasons


def main():
    frame, catalog = snapshot()
    selection = json.loads((OUT / "selection.json").read_text())
    report = {"policy": POLICY, "as_of": frame.index[-1], "production_updated": False,
              "review_constraints": {"own_index_location_in_each_branch": True, "no_option_metadata_as_risk": True,
                                     "nonnegative_first_touch_edge": True}, "models": {}}
    contexts = {}
    for key, model in selection["models"].items():
        era, regime = key.split("_")
        review = {"sides": {}}
        candidates = {}
        for side in ("low", "high"):
            path = OUT / f"{era}_{regime}_{side}_attempts.jsonl"
            valid, approximate, count, reasons = [], [], 0, {}
            study = Study(frame, catalog, regime, side, era, pd.read_pickle(OUT / f"{side}_outcomes.pkl"),
                          turning_points(frame), extreme_labels(frame), log=False)
            contexts[key, side] = study
            paths = [path]
            expected_count = model[side]["summary"]["trials"]
            if "extension" in model[side]:
                paths.append(OUT / model[side]["extension"]["file"])
                expected_count += model[side]["extension"]["summary"]["trials"]
            for trial_path in paths:
                with trial_path.open(encoding="utf-8") as stream:
                    for line in stream:
                        trial = json.loads(line)
                        count += 1
                        added = semantic_reasons(trial, side)
                        for reason in added: reasons[reason] = reasons.get(reason, 0) + 1
                        if added: continue
                        if not trial["rejected"]: valid.append(trial)
                        elif set(trial["rejected"]) <= {"same_day_extreme_coverage", "ordinary_pivot_coverage"}:
                            approximate.append(trial)
            assert count == expected_count, (key, side, "Incomplete attempts", count, expected_count)
            candidates[side] = sorted(valid, key=Study.rank)[:30]
            review["sides"][side] = {"qualified_count": len(valid), "review_rejections": reasons,
                                      "best": candidates[side][0] if candidates[side] else None,
                                      "diagnostic_only_nearby": sorted(approximate, key=Study.rank)[:5]}
        pairs = []
        for red in candidates["low"]:
            for blue in candidates["high"]:
                start = max(red["start_date"], blue["start_date"])
                rm, rk = matches(frame, red["rules"])
                bm, bk = matches(frame, blue["rules"])
                covered = frame.index >= start
                effective_red, effective_blue = rm & ~bm & covered, bm & covered
                ls, hs = contexts[key, "low"], contexts[key, "high"]
                low_targets = [e for e in ls.extremes if e["date"] >= max(start, "2022-01-01")]
                if any(not effective_red[e["index"]] for e in low_targets): continue
                low_m, high_m = ls.stats(effective_red, rk & bk, start), hs.stats(effective_blue, bk, start)
                if any(m["score"] is None or m["evaluated"] < POLICY["minimum_evaluated_events"]
                       or m["formal_evaluated"] < POLICY["minimum_formal_events"]
                       or m["formal_max_region_days"] > POLICY["max_consecutive_days"]
                       or (m["pivot_coverage_pct"] or 0) < POLICY["minimum_pivot_coverage_pct"]
                       or m["favorable_first_pct"] < m["adverse_first_pct"] for m in (low_m, high_m)): continue
                pairs.append({"low": red, "high": blue, "start_date": start,
                              "effective_metrics": {"low": low_m, "high": high_m},
                              "rank_score": low_m["score"] + high_m["score"]})
        best = max(pairs, key=lambda p: p["rank_score"]) if pairs else None
        review["pair"] = best
        review["status"] = "research_candidate_only" if best else "no_qualified_pair_do_not_install"
        if best:
            for side in ("low", "high"):
                mask = matches(frame, best[side]["rules"])[0] & (frame.index >= best["start_date"])
                if side == "low": mask &= ~matches(frame, best["high"]["rules"])[0]
                events = episodes(frame, pd.Series(mask, index=frame.index), side)
                pd.DataFrame(events).to_csv(OUT / f"{key}_{side}_review_events.csv", index=False)
            daily = frame[["open", "high", "low", "close"]].copy()
            for color, side in (("red", "low"), ("blue", "high")):
                hit, known = matches(frame, best[side]["rules"])
                daily[color] = hit & (frame.index >= best["start_date"])
                daily[color + "_known"] = known & (frame.index >= best["start_date"])
            daily["red_effective"] = daily.red & ~daily.blue
            daily["data_complete"] = daily.red_known & daily.blue_known
            daily["as_of_at"] = daily.index + "T22:30:00+08:00"
            daily.to_csv(OUT / f"{key}_review_daily.csv", index_label="date")
        report["models"][key] = review
    save_json(OUT / "review.json", report)
    print({key: value["status"] for key, value in report["models"].items()}, flush=True)


if __name__ == "__main__":
    main()
