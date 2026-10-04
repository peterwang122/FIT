from datetime import date, timedelta
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from app.services.bear_swing_features import available_values, build_features, prior_percentile

spec = importlib.util.spec_from_file_location("bear_research", Path(__file__).resolve().parents[2] / "scripts/research/csi1000_bear_swing.py")
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)


def test_prior_percentile_excludes_current_and_counts_observations():
    assert prior_percentile([1, 2, None, 2, 3], minimum=2, window=3) == [None, None, None, 75, 100]
    assert prior_percentile([1] * 252 + [1, 2])[-2:] == [50, 100]
    assert prior_percentile([1] * 251 + [2])[-1] is None


def test_publication_cutoff_does_not_backdate_holiday_release():
    rows = [{"source_date": "2025-04-03", "available_at": "2025-04-04 08:00:00", "value": 9},
            {"source_date": "2025-04-07", "available_at": "2025-04-07 22:30:01", "value": 12}]
    assert available_values(["2025-04-03", "2025-04-07", "2025-04-08", "2025-04-20"], rows) == [None, 9, 12, None]
    assert available_values(["2025-04-07"], [{"source_date": "2025-04-07", "available_at": "2025-04-07T14:30:00Z", "value": 1}]) == [1]


def candles(n):
    return [{"trade_date": date(2020, 1, 1) + timedelta(days=i), "open": 100 + i % 23,
             "high": 105 + i % 23, "low": 98 + i % 23, "close": 103 + i % 23} for i in range(n)]


def test_future_append_preserves_every_feature_and_signal():
    before = build_features(candles(400), [])
    after = build_features(candles(450), [])
    pd.testing.assert_frame_equal(before, after.iloc[:400])
    rule = research.condition("bear-position60-pct", "lte", 30)
    pd.testing.assert_series_equal(research.rule_mask(before, [rule]), research.rule_mask(after, [rule]).iloc[:400])


def test_stock_api_string_prices_match_numeric_research_prices():
    data = candles(400)
    strings = [{k: str(v) if k != "trade_date" else v for k, v in row.items()} for row in data]
    pd.testing.assert_frame_equal(build_features(data, []), build_features(strings, []))


def test_empty_prices_and_mixed_timezone_publications():
    assert build_features([], []).empty
    rows = [{"source_date": "2025-04-07", "available_at": "2025-04-07T15:00:00Z", "value": 2},
            {"source_date": "2025-04-07", "available_at": "2025-04-07 22:00:00", "value": 1}]
    assert available_values(["2025-04-07", "2025-04-08"], rows) == [1, 2]


def test_selected_filters_are_csi1000_only_and_missing_does_not_match():
    from app.services.quant_service import QuantService
    from app.services.bear_swing_features import FEATURE_FIELDS
    service = QuantService.__new__(QuantService)
    keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000852", "中证1000")
    assert set(FEATURE_FIELDS) <= set(keys)
    assert not set(FEATURE_FIELDS).intersection(service._allowed_snapshot_filter_keys("index", "cn", "sh000300", "沪深300"))
    payload = {"strategy_type": "index", "target_market": "cn", "target_code": "sh000300",
               "red_filter_groups": [{"conditions": [research.condition("bear-mo-vix-pct", "gte", 70)]}]}
    with pytest.raises(ValueError, match="仅支持中证1000"):
        service._validate_strategy_payload(payload)


def test_missing_derivatives_are_never_zero_or_prelisting_values():
    data = candles(2)
    dashboard = [{"trade_date": c["trade_date"], "main_basis": 20, "option_turnover_pc_ratio": 1} for c in data]
    frame = build_features(data, dashboard)
    assert frame["bear-im-basis"].isna().all()
    assert not research.rule_mask(frame, [research.condition("bear-im-basis", "lte", 0)]).any()


def test_clusters_use_first_day_and_ambiguous_intraday_order():
    frame = pd.DataFrame([{"open": 100, "high": 106, "low": 96, "close": 100}] * 30,
                         index=pd.date_range("2024-01-01", periods=30).strftime("%Y-%m-%d"))
    mask = pd.Series([True, True, False] + [False] * 27, index=frame.index)
    events = research.episodes(frame, mask, "low")
    assert len(events) == 1 and events[0]["days"] == 2
    assert events[0]["first_touch"] == "unknown"
    assert events[0]["entry_date"] == "2024-01-02"
    assert events[0]["mfe_20d"] == pytest.approx(6)
    summary = research.summarize(events, "2024-01-01", "2024-01-10", [], frame)
    assert summary["evaluated"] == 0 and summary["pending_or_purged"] == 1


def test_rule_grid_bounded_complexity_and_no_diagnostic_features():
    for enhanced in (False, True):
        for side in ("low", "high"):
            for rule in research.candidates(side, enhanced):
                assert 1 <= len(rule["conditions"]) <= 3
                assert not any(c["field"].startswith("diagnostic-") for c in rule["conditions"])


def test_unconfirmed_zigzag_tail_not_an_evaluation_label():
    frame = pd.DataFrame({"close": [100, 94, 99, 102, 101]})
    pivots = research.turning_points(frame)
    assert [(p["index"], p["side"]) for p in pivots] == [(0, "high"), (1, "low")]
