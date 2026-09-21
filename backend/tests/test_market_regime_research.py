from datetime import date, datetime, timedelta

import json

from app.services import market_regime_research
from app.services.market_regime_research import index_features, macro_derived, select_macro, macro_completeness, observation_coverage


def observation(period, value, published, seen, key="m1_yoy", basis="m1_2025", release="a"):
    return dict(series_key=key, period_end=period, value=value, period_kind="monthly",
                basis_version=basis, unit="%", published_at=published, available_at=published,
                replay_available_at=seen, first_seen_at=seen, replay_eligible=True,
                publication_precision="minute", vintage_status="first_observed_archive",
                revision_number=1, release_id=release, source_url="https://www.pbc.gov.cn/")


def test_future_release_and_first_seen_never_backdated():
    row = observation(date(2025, 1, 31), 4, datetime(2025, 2, 14), datetime(2026, 9, 20))
    assert select_macro([row], datetime(2025, 2, 20)) == []
    assert select_macro([row], datetime(2025, 2, 13), strict=False) == []
    assert select_macro([row], datetime(2025, 2, 20), strict=False)[0]["value"] == 4


def test_monthly_samples_and_three_month_change_not_daily_carry():
    rows = [observation(date(2025, m, 28), m, datetime(2025, m + 1, 10), datetime(2025, m + 1, 10)) for m in range(1, 5)]
    a = select_macro(rows, datetime(2025, 5, 11))[0]
    b = select_macro(rows, datetime(2025, 5, 31))[0]
    assert a["independent_months"] == b["independent_months"] == 4
    assert a["change_3m"] == b["change_3m"] == 3
    assert a["mean_3m"] == 3


def test_revision_does_not_rewrite_previous_cutoff():
    old = observation(date(2025, 1, 31), 4, datetime(2025, 2, 10), datetime(2025, 2, 10))
    new = observation(date(2025, 1, 31), 5, datetime(2025, 3, 10), datetime(2025, 3, 10), release="b")
    assert select_macro([old, new], datetime(2025, 2, 20))[0]["value"] == 4
    assert select_macro([old, new], datetime(2025, 3, 20))[0]["value"] == 5


def test_m1_basis_not_spliced():
    old = observation(date(2024, 10, 31), 10, datetime(2024, 11, 10), datetime(2024, 11, 10), basis="m1_legacy")
    new = observation(date(2025, 1, 31), 2, datetime(2025, 2, 10), datetime(2025, 2, 10))
    evidence = select_macro([old, new], datetime(2025, 3, 1))
    assert len(evidence) == 2
    assert all(r["change_3m"] is None for r in evidence)


def test_proxy_is_three_indices_and_appending_future_does_not_change_past():
    start = date(2024, 1, 1)
    rows = [dict(index_code=code, trade_date=start + timedelta(days=i), close_price=100+i)
            for code in ("sh000985", "sh000300", "sh000905", "sh000852") for i in range(160)]
    before = index_features(rows)
    assert before[-1]["index_participation_ma120_pct"] == 100
    assert before[-1]["trend_supportive"] is True
    assert before[10]["trend_supportive"] is None
    rows.append(dict(index_code="sh000985", trade_date=start + timedelta(days=160), close_price=1))
    assert index_features(rows)[:-1] == before
    missing = index_features([r for r in rows if r["index_code"] != "sh000905"])
    assert missing[-2]["index_participation_ma120_pct"] is None


def test_derived_credit_requires_same_period_and_monthly_not_ytd():
    evidence = [dict(series_key=k, period_end=date(2025, 1, 31), period_kind="ytd", value=v,
                     available_at=datetime(2025, 2, 1), basis_version="official")
                for k,v in (("tsf_flow", 100), ("tsf_government_bond_flow", 30))]
    assert macro_derived(evidence) == []
    for row in evidence:
        row["period_kind"] = "monthly"
    assert macro_derived(evidence)[0]["value"] == 70


def test_stale_m1_legacy_cannot_count_as_current_coverage():
    missing, stale = macro_completeness([dict(series_key='m1_yoy', period_age_days=400)])
    assert 'm1_yoy' in stale and 'm1_yoy' not in missing
    _, stale = macro_completeness([dict(series_key='m1_yoy', period_age_days=n) for n in (400, 21)])
    assert 'm1_yoy' not in stale


def test_missing_periods_distinguish_m1_basis_start_and_profit_january():
    rows = [dict(series_key=key, basis_version=basis, period_kind='monthly', period_end=day)
            for key, basis, day in [('m1_yoy','m1_2025',date(2025,2,28)),
                                    ('industrial_profit_month_yoy','official',date(2024,12,31)),
                                    ('industrial_profit_month_yoy','official',date(2025,3,31))]]
    coverage = {r['series_key']: r for r in observation_coverage(rows)}
    assert coverage['m1_yoy']['missing_periods'] == ['2025-01']
    assert coverage['industrial_profit_month_yoy']['missing_periods'] == ['2025-02']
    assert coverage['industrial_profit_month_yoy']['scheduled_nonrelease_periods'] == ['2025-01']


def test_read_snapshot_latest_follows_requested_range(tmp_path, monkeypatch):
    path = tmp_path / "lightweight.json"
    path.write_text(json.dumps({"latest": {"date": "2026-01-03"}, "daily_points": [
        {"date": "2026-01-01"}, {"date": "2026-01-02"}, {"date": "2026-01-03"}
    ]}))
    monkeypatch.setattr(market_regime_research, "REPORT_PATH", path)
    report = market_regime_research.read_snapshot(date(2026, 1, 1), date(2026, 1, 2))
    assert report["latest"]["date"] == "2026-01-02"
    assert len(report["daily_points"]) == 2
