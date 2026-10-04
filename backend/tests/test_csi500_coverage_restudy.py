import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def module(monkeypatch, tmp_path):
    directory = Path(__file__).resolve().parents[2] / "scripts/research"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("csi500_coverage_test", directory / "csi500_coverage_restudy.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    monkeypatch.setattr(result, "OUT", tmp_path)
    return result


def fixture(module, values, regime="bear", start="2022-01-04", first=None):
    dates = pd.bdate_range(start, periods=len(values)).strftime("%Y-%m-%d")
    frame = pd.DataFrame({"open": 100, "high": 106, "low": 99, "close": 100, "factor": values}, index=dates)
    catalog = {"factor": {"eligibility": "eligible", "transform": "raw", "family": "fixture",
                          "source": "fixture", "first_available_date": first or dates[0]}}
    outcomes = module.all_outcomes(frame, "low")
    return module.Study(frame, catalog, regime, "low", "long", outcomes, [], [])


def test_spans_are_actual_consecutive_sessions(module):
    start, end, lengths = module.spans([False, True, True, False, True])
    assert start.tolist() == [1, 4]
    assert end.tolist() == [2, 4]
    assert lengths.tolist() == [2, 1]


def test_long_signal_rejected_not_clipped_afterward(module):
    study = fixture(module, [1] * 20 + [0] * 50)
    trial = study.evaluate([{"conditions": [module.condition("factor", "gte", 1)]}], "single")
    assert trial["metrics"]["formal_max_region_days"] == 20
    assert "long_signal_region" in trial["rejected"]
    assert module.matches(study.f, trial["rules"])[0].sum() == 20
    study.stream.close()


def test_wrong_regime_long_region_cannot_escape_admission(module):
    study = fixture(module, [1] * 20 + [0] * 50, regime="bull")
    trial = study.evaluate([{"conditions": [module.condition("factor", "gte", 1)]}], "single")
    assert trial["metrics"]["events"] == 0
    assert "long_signal_region" in trial["rejected"]
    study.stream.close()


def test_late_source_cannot_claim_2022_coverage(module):
    study = fixture(module, [1, 0] * 50, first="2022-02-01")
    trial = study.evaluate([{"conditions": [module.condition("factor", "gte", 1)]}], "single")
    assert trial["start_date"] == "2022-02-01"
    assert "late_source" in trial["rejected"]
    study.stream.close()


def test_no_evaluated_baseline_is_not_fake_incremental_gain(module):
    study = fixture(module, [1, 0] * 50)
    trial = study.evaluate([{"conditions": [module.condition("factor", "gte", 1)]}], "single",
                           baseline={"rules": [{"conditions": [module.condition("factor", "gte", 2)]}]})
    assert trial["common_window"]["baseline"]["score"] is None
    assert trial["common_window"]["delta_score"] is None
    study.stream.close()


def test_pivot_coverage_uses_onset_not_any_day_in_long_region(module):
    study = fixture(module, [1] * 25 + [0] * 45)
    study.pivots = np.asarray([20])
    mask, known = module.matches(study.f, [{"conditions": [module.condition("factor", "gte", 1)]}])
    result = study.stats(mask, known, study.f.index[0])
    assert result["covered_pivots"] == 0
    study.stream.close()


def test_single_lucky_event_cannot_be_deployed(module):
    study = fixture(module, [1] + [0] * 69)
    trial = study.evaluate([{"conditions": [module.condition("factor", "gte", 1)]}], "single")
    assert "too_few_events" in trial["rejected"]
    study.stream.close()


def test_raw_index_level_is_not_repeatable_timing(module):
    meta = {"source": "index_daily_data", "transform": "raw"}
    assert module.raw_level(meta, "csi500-index-daily-data-test-close-price")
    assert not module.raw_level({**meta, "transform": "prior-percentile"}, "csi500-index-daily-data-test-close-price-pct")
    assert not module.raw_level(meta, "csi500-index-daily-data-test-close-price-change-1d")


def test_analysis_context_does_not_overwrite_attempts(module, tmp_path):
    path = tmp_path / "long_bear_low_attempts.jsonl"
    path.write_text("preserve this research audit\n")
    dates = pd.bdate_range("2022-01-04", periods=30).strftime("%Y-%m-%d")
    frame = pd.DataFrame({"open": 100, "high": 106, "low": 99, "close": 100}, index=dates)
    study = module.Study(frame, {}, "bear", "low", "long", module.all_outcomes(frame, "low"), [], [], log=False)
    assert path.read_text() == "preserve this research audit\n"
    study.stream.close()


def test_review_requires_own_location_in_every_or_branch(module):
    from review_csi500_coverage import semantic_reasons
    trial = {"rules": [{"conditions": [module.condition("csi500-position-20d", "lte", 30)]},
                       {"conditions": [module.condition("other_index", "gte", 1)]}],
             "metrics": {"favorable_first_pct": 60, "adverse_first_pct": 20}}
    assert "each_branch_needs_own_index_location" in semantic_reasons(trial, "low")


def test_option_model_inputs_are_not_protection_demand(module):
    from review_csi500_coverage import metadata_field
    assert metadata_field("csi500-option-sse-510500-option-vix-json-near-risk-free-rate")
    assert metadata_field("csi500-option-sse-510500-option-vix-json-near-strike-count")
    assert not metadata_field("csi500-option-sse-510500-option-vix-json-vix-close")


def test_canonical_sources_keep_etf_sources_separate_and_respect_warmup(module):
    from extend_csi500_coverage import keys_for
    meta = {"eligibility": "eligible", "valid_days": 300, "transform": "prior-percentile",
            "source": "fixture", "first_available_date": "2023-10-09"}
    catalog = {"csi500-option-sse-510500-pc-pct": meta,
               "csi500-option-szse-159922-pc-pct": {**meta, "first_available_date": "2024-01-02"},
               "csi500-option-sse-510500-near-risk-free-rate-pct": meta}
    assert set(keys_for(catalog, "options")) == {"csi500-option-sse-510500-pc-pct", "csi500-option-szse-159922-pc-pct"}
    assert list(keys_for(catalog, "long")) == []


def test_replay_preserves_native_price_dates_and_matches_engine(module):
    from datetime import date
    from app.services.quant_service import QuantService
    from report_csi500_coverage import replay
    prices = [{"trade_date": date(2024, 1, i), "open": 100 + i, "high": 102 + i,
               "low": 98 + i, "close": 101 + i} for i in range(2, 9)]
    result, detail = replay(QuantService(None), prices, {"2024-01-02": "red", "2024-01-05": "blue"})
    assert result["return_pct"] > 0
    assert detail["trades"][0]["date"] == "2024-01-03"
    assert prices[0]["trade_date"] == date(2024, 1, 2)
