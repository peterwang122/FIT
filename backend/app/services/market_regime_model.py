"""Frozen, causal regime candidate. Macro confirms structure, never trades by itself."""

from bisect import bisect_right
from datetime import date, datetime, time
import math

MODEL_VERSION = "market-cycle-v1"

RULES = {
    "warning": "收盘<MA120、MA120下降且MA120参与度≤1/3，持续10日；宏观至少两组走弱时5日",
    "bear": "收盘<MA250、MA120<MA250、MA250下降且三指数MA250参与度≤1/3，持续10日；宏观至少两组走弱时5日",
    "shock": "距250日收盘高点回撤≥20%、MA120下降且MA120参与度≤1/3，持续5日",
    "repair": "收盘>MA60、20日收益>0且MA60参与度≥2/3，持续5日；宏观至少两组改善时3日",
    "bull": "收盘>MA120、MA120上升且MA120参与度≥2/3，持续5日",
}


def macro_signal(evidence):
    """Three independent families; missing is unknown, not neutral/supportive."""
    latest = {}
    for row in evidence:
        if (row.get("period_age_days", 999) > 100 or not row.get("point_in_time_verified")
                or not isinstance(row.get("value"), (int, float)) or not math.isfinite(row["value"])):
            continue
        previous = latest.get(row["series_key"])
        if previous is None or str(row["period_end"]) > str(previous["period_end"]):
            latest[row["series_key"]] = row
    groups = []

    def numeric(value):
        return isinstance(value, (int, float)) and math.isfinite(value)

    def add(key, label, keys, decide):
        rows = [latest.get(k) for k in keys]
        direction = decide(rows) if all(rows) else None
        groups.append({"key": key, "label": label, "direction": direction,
                       "inputs": [dict(r) for r in rows if r],
                       "missing": [k for k, r in zip(keys, rows) if not r],
                       "reason": "已发布的同口径证据" if direction is not None else "缺少同口径月份或当时可核验版本"})

    def money(rows):
        a, b, credit = rows
        if len({str(r["period_end"]) for r in rows}) != 1 or any(not numeric(r.get("change_3m")) for r in rows):
            return None
        gap_change = a["change_3m"] - b["change_3m"]
        if gap_change > 1e-8 and credit["change_3m"] > 1e-8:
            return 1
        if gap_change < -1e-8 and credit["change_3m"] < -1e-8:
            return -1
        return 0

    def activity(rows):
        if any(not numeric(r.get("mean_3m")) or not numeric(r.get("change_3m")) for r in rows):
            return None
        if len({str(r["period_end"]) for r in rows}) != 1:
            return None
        if all(r["mean_3m"] >= 50 and r["change_3m"] > 0 for r in rows):
            return 1
        if all(r["mean_3m"] < 50 and r["change_3m"] < 0 for r in rows):
            return -1
        return 0

    def earnings(rows):
        profit, revenue = rows
        if str(profit["period_end"]) != str(revenue["period_end"]) or any(r["period_kind"] != "ytd" for r in rows):
            return None
        # Official comparable cumulative growth, not amounts differenced into a month.
        if all(r["value"] > 0 for r in rows):
            return 1
        if all(r["value"] < 0 for r in rows):
            return -1
        return 0

    add("money_credit", "货币信用", ("m1_yoy", "m2_yoy", "tsf_stock_yoy"), money)
    add("activity", "经济景气", ("pmi_manufacturing", "pmi_new_orders"), activity)
    add("earnings", "企业盈利", ("industrial_profit_ytd_yoy", "industrial_revenue_ytd_yoy"), earnings)
    support = sum(g["direction"] == 1 for g in groups)
    adverse = sum(g["direction"] == -1 for g in groups)
    known = sum(g["direction"] is not None for g in groups)
    return {"groups": groups, "support_count": support, "adverse_count": adverse,
            "known_count": known, "complete": known == 3,
            "status": "supportive" if support >= 2 else "adverse" if adverse >= 2 else "mixed" if known == 3 else "incomplete"}


def macro_timeline(observations, days, selector, as_of):
    # Re-evaluate only when the point-in-time version set changes; daily carry is not a new observation.
    availability = sorted({max(r["available_at"], r["replay_available_at"]) for r in observations if r["replay_eligible"]})
    timeline, previous = [], None
    for day in days:
        day = date.fromisoformat(str(day))
        cutoff = min(datetime.combine(day, time(22, 45)), as_of)
        rank = bisect_right(availability, cutoff)
        # Age checks can change daily even without publication.
        evidence = selector(observations, cutoff) if rank else []
        signal = macro_signal(evidence)
        compact = {**signal, "groups": [{**g, "inputs": [{k: r.get(k) for k in (
            "series_key", "value", "change_3m", "mean_3m", "period_end", "period_kind",
            "basis_version", "available_at", "replay_available_at", "source_url")}
            for r in g["inputs"]]} for g in signal["groups"]]}
        if compact != previous:
            timeline.append({"date": str(day), "as_of_at": cutoff.isoformat(), **compact})
            previous = compact
    return timeline


def cycle_points(snapshot, code):
    timeline = snapshot.get("macro_regime_timeline") or []
    dates = [r["date"] for r in timeline]
    unknown = macro_signal([])
    state = "repair"
    state_since, trigger_rule = None, "initial"
    bull_established = False
    streaks = {k: 0 for k in ("warning", "bear", "shock", "repair", "bull")}
    points = []
    for source in snapshot["daily_points"]:
        day = str(source["date"])
        trend = source if code == "sh000985" else (source.get("adaptation") or {}).get(code)
        if not trend or not trend.get("close"):
            continue
        i = bisect_right(dates, day) - 1
        macro = timeline[i] if i >= 0 else unknown
        required = [trend.get(k) for k in ("close", "ma60", "ma120", "ma250", "ma120_change_20d_pct",
                    "ma250_change_20d_pct", "return_20d_pct", "drawdown_250d_pct")]
        participation = [source.get(f"index_participation_ma{w}_pct") for w in (60, 120, 250)]
        ready = not source.get("missing_reasons") and all(isinstance(v, (int, float)) and math.isfinite(v) for v in required + participation)
        base = {"date": day, **{k: trend.get(k) for k in ("open", "high", "low", "close")},
                "medium_ma": trend.get("ma60"), "long_ma": trend.get("ma120"),
                "long_slope": trend["ma120_change_20d_pct"] / 100 if trend.get("ma120_change_20d_pct") is not None else None,
                "breadth_medium": participation[0], "breadth_long": participation[1],
                "annual_ma": trend.get("ma250"), "annual_slope_pct": trend.get("ma250_change_20d_pct"),
                "breadth_annual": participation[2], "drawdown_250d_pct": trend.get("drawdown_250d_pct"),
                "return_20d_pct": trend.get("return_20d_pct"),
                "evidence_mode": "index_proxy", "model_version": MODEL_VERSION,
                "macro_status": macro["status"], "macro_complete": macro["complete"],
                "macro_support_count": macro["support_count"], "macro_adverse_count": macro["adverse_count"],
                "macro_evidence_date": timeline[i]["date"] if i >= 0 else None,
                "macro_applied": False, "rules": []}
        if not ready:
            streaks = {k: 0 for k in streaks}
            points.append({**base, "state": "unavailable", "buy_multiplier": 0.0,
                           "missing_reasons": ["index_history_incomplete"], "reason": "history_short"})
            continue
        close, ma60, ma120, ma250, slope120, slope250, ret20, dd = required
        p60, p120, p250 = participation
        conditions = {
            "warning": close < ma120 and slope120 < 0 and p120 <= 100 / 3 + 1e-6,
            "bear": close < ma250 and ma120 < ma250 and slope250 < 0 and p250 <= 100 / 3 + 1e-6,
            "shock": dd <= -20 and slope120 < 0 and p120 <= 100 / 3 + 1e-6,
            "repair": close > ma60 and ret20 > 0 and p60 >= 200 / 3 - 1e-6,
            "bull": close > ma120 and slope120 > 0 and p120 >= 200 / 3 - 1e-6,
        }
        for key, met in conditions.items():
            streaks[key] = streaks[key] + 1 if met else 0

        def decide(adverse, support):
            warning_days, bear_days, repair_days = (5 if adverse >= 2 else 10), (5 if adverse >= 2 else 10), (3 if support >= 2 else 5)
            if streaks["bear"] >= bear_days or streaks["shock"] >= 5:
                return "invalid"
            if streaks["bull"] >= 5:
                return "adjustment" if close < ma60 or p60 < 200 / 3 - 1e-6 else "valid"
            if state == "invalid":
                return "repair" if streaks["repair"] >= repair_days else "invalid"
            if bull_established:
                if streaks["warning"] >= warning_days:
                    return "warning"
                if state == "warning" and streaks["repair"] < repair_days:
                    return "warning"
                return "adjustment" if close < ma60 or p60 < 200 / 3 - 1e-6 else "valid"
            return "repair"

        previous_state = state
        price_state = decide(0, 0)
        adverse = macro["adverse_count"] if macro["complete"] else 0
        support = macro["support_count"] if macro["complete"] else 0
        state = decide(adverse, support)
        if state in ("valid", "adjustment"):
            bull_established = True
        elif state == "invalid":
            bull_established = False
        thresholds = {"warning": 5 if adverse >= 2 else 10,
                      "bear": 5 if adverse >= 2 else 10, "shock": 5,
                      "repair": 3 if support >= 2 else 5, "bull": 5}
        if state_since is None or previous_state != state:
            state_since = day
            trigger_rule = ("bear" if streaks["bear"] >= thresholds["bear"] else "shock") if state == "invalid" else {
                "warning": "warning", "repair": "repair" if previous_state == "invalid" else "initial",
                "valid": "bull", "adjustment": "pullback"}[state]
        points.append({**base, "state": state,
            "state_since": state_since, "trigger_rule": trigger_rule,
            "buy_multiplier": {"valid": 1.0, "adjustment": 1.0, "warning": .5, "invalid": 0.0, "repair": .5}[state],
            "reason": f"cycle_{state}", "missing_reasons": [], "observed": 3, "traded": 3,
            "eligible": 3, "coverage_pct": 100, "macro_applied": state != price_state,
            "rules": [{"key": k, "met": conditions[k], "streak": streaks[k], "days": thresholds[k]} for k in conditions]})
    return points
