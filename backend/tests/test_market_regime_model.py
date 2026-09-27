from datetime import date, datetime, timedelta
from copy import deepcopy

from app.services.market_regime_model import cycle_points, macro_signal, macro_timeline
from app.services.market_regime_research import select_macro, index_features


def day(i, **changes):
    return {"date": str(date(2024, 1, 1) + timedelta(days=i)), "open": 100, "high": 101, "low": 99,
            "close": 100, "ma60": 95, "ma120": 90, "ma250": 80,
            "ma120_change_20d_pct": 2, "ma250_change_20d_pct": 1,
            "return_20d_pct": 5, "drawdown_250d_pct": -2,
            "index_participation_ma60_pct": 100, "index_participation_ma120_pct": 100,
            "index_participation_ma250_pct": 100, "missing_reasons": [], **changes}


def bear(i):
    return day(i, ma60=110, ma120=115, ma250=120, ma120_change_20d_pct=-2,
               ma250_change_20d_pct=-1, index_participation_ma60_pct=0,
               index_participation_ma120_pct=0, index_participation_ma250_pct=0, return_20d_pct=-3)


def run(points, macro=None):
    return cycle_points({"daily_points": points, "macro_regime_timeline": macro or []}, "sh000985")


def test_normal_bull_pullback_keeps_entry_permission():
    points = [day(i) for i in range(5)] + [day(i, ma60=105, index_participation_ma60_pct=0) for i in range(5, 25)]
    result = run(points)
    assert result[4]["state"] == "valid"
    assert all(p["state"] == "adjustment" and p["buy_multiplier"] == 1 for p in result[5:])


def test_bear_requires_structure_not_just_ma60_and_macro_accelerates_only_with_price():
    points = [day(i) for i in range(5)] + [bear(i) for i in range(5, 15)]
    baseline = run(points)
    assert baseline[8]["state"] != "invalid" and baseline[-1]["state"] == "invalid"
    macro = [{"date": points[0]["date"], **macro_signal([]), "adverse_count": 2, "status": "adverse", "complete": True}]
    faster = run(points, macro)
    assert faster[8]["state"] != "invalid" and faster[9]["state"] == "invalid"
    assert faster[9]["macro_applied"]
    assert run([day(i) for i in range(20)], macro)[-1]["state"] == "valid"


def test_macro_repair_is_earlier_not_full_bull_and_gap_does_not_release_bear():
    points = [bear(i) for i in range(10)]
    points += [day(10, missing_reasons=["gap"])]
    points += [day(i, ma120=110, ma120_change_20d_pct=-1) for i in range(11, 14)]
    timeline = [{"date": points[0]["date"], **macro_signal([]), "support_count": 2, "status": "supportive", "complete": True}]
    result = run(points, timeline)
    assert result[9]["state"] == "invalid" and result[10]["state"] == "unavailable"
    assert result[11]["state"] == "invalid" and result[-1]["state"] == "repair"
    assert run(points)[-1]["state"] == "invalid"


def evidence(key, value, change=1, mean=51, **kw):
    return dict(series_key=key, period_end=date(2025, 4, 30), period_kind="monthly", basis_version="official",
                value=value, change_3m=change, mean_3m=mean, period_age_days=30, point_in_time_verified=True, **kw)


def test_money_credit_not_duplicate_votes_and_old_m1_never_spliced():
    rows = [evidence("m1_yoy", 5, change=2), evidence("m2_yoy", 8, change=1), evidence("tsf_stock_yoy", 9)]
    signal = macro_signal(rows)
    assert signal["support_count"] == 1 and not signal["complete"]
    rows[0]["change_3m"] = None
    assert macro_signal(rows)["known_count"] == 0
    rows[0]["change_3m"] = 2
    rows[0]["period_age_days"] = 400
    assert macro_signal(rows)["known_count"] == 0


def test_macro_requires_compatible_periods_no_cumulative_month_estimation():
    rows = [evidence("industrial_profit_ytd_yoy", -1), evidence("industrial_revenue_ytd_yoy", -2)]
    for r in rows:
        r["period_kind"] = "ytd"
        r["change_3m"] = 999
    assert macro_signal(rows)["adverse_count"] == 1
    rows[1]["period_end"] = date(2025, 3, 31)
    assert macro_signal(rows)["known_count"] == 0


def test_future_append_does_not_change_previous_states():
    points = [day(i) for i in range(12)]
    before = run(points)
    future = {"date": "2025-01-01", **macro_signal([]), "adverse_count": 3}
    assert run(points + [bear(12)], [future])[:-1] == before


def test_strict_timeline_does_not_backdate_observed_archive():
    row = {**evidence("m1_yoy", 5), "available_at": datetime(2025, 5, 10),
           "replay_available_at": datetime(2026, 9, 20), "first_seen_at": datetime(2026, 9, 20),
           "release_id": "a", "replay_eligible": True, "vintage_status": "first_observed_archive"}
    rows = [row]
    days = [date(2025, 5, 11), date(2026, 9, 21)]
    result = macro_timeline(rows, days, select_macro, datetime(2026, 9, 21, 22, 45))
    assert all(r["known_count"] == 0 for r in result)
    assert result[0]["groups"][0]["inputs"] == []


def test_250_day_window_exact_and_future_independent():
    start = date(2020, 1, 1)
    rows = [{"index_code": code, "trade_date": start + timedelta(days=i), "close_price": 100+i}
            for code in ("sh000985", "sh000300", "sh000905", "sh000852") for i in range(300)]
    features = index_features(rows)
    assert features[248]["ma250"] is None and features[249]["ma250"] == 224.5
    assert features[268]["ma250_change_20d_pct"] is None
    assert features[269]["ma250_change_20d_pct"] > 0
    before = deepcopy(features)
    rows.append({"index_code": "sh000985", "trade_date": start + timedelta(days=300), "close_price": 1})
    assert index_features(rows)[:-1] == before
