from datetime import date
from decimal import Decimal
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.services.csi500_swing_features import Builder, PUBLIC_FIELDS, cycle_labels, known_financing_values, map_observations, option_numeric_fields, selected_features


@pytest.fixture
def research_module(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "scripts/research"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("csi500_research_test", directory / "csi500_swing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candles(n=280):
    dates = pd.bdate_range("2021-01-01", periods=n)
    return [{"trade_date": d.date(), "open": 100 + i, "high": 102 + i,
             "low": 98 + i, "close": 101 + i} for i, d in enumerate(dates)]


def test_approved_major_cycles_keep_2022_rally_bear():
    labels, _ = cycle_labels(["2022-04-26", "2022-07-04", "2023-04-07", "2024-05-20", "2024-09-18", "2026-06-30", "2026-07-01"])
    assert labels.tolist() == ["bear", "bear", "bear", "bear", "bull", "bull", "observation"]


def test_cutoff_and_latest_source_period_not_last_physical_row():
    rows = [
        {"source_date": "2024-04-02", "available_at": "2024-04-03T22:31:00+08:00", "value": 2},
        {"source_date": "2024-04-01", "available_at": "2024-04-04T10:00:00+08:00", "value": 1},
    ]
    values = map_observations(["2024-04-03", "2024-04-04"], rows)
    assert np.isnan(values[0])
    assert values[1] == 2


def test_percentile_uses_252_prior_source_observations_not_today():
    b = Builder(candles())
    rows = [{"source_date": d, "available_at": d + "T18:00:00+08:00", "value": i}
            for i, d in enumerate(b.frame.index)]
    b.add("example", "Example", "example", "fixture", rows, max_age_days=0)
    f, catalog = b.finish()
    assert np.isnan(f["csi500-example-pct"].iloc[251])
    assert f["csi500-example-pct"].iloc[252] == 100
    assert catalog["csi500-example-pct"].observations == 280


def test_future_append_never_changes_past_features():
    def build(n):
        b = Builder(candles(n))
        b.price_features()
        return b.finish()[0]
    short, long = build(270), build(300)
    pd.testing.assert_frame_equal(short, long.loc[short.index])


def test_missing_domestic_day_not_forward_filled():
    days = ["2024-04-01", "2024-04-02"]
    rows = [{"source_date": days[0], "available_at": days[0] + "T18:00:00+08:00", "value": 1}]
    values = map_observations(days, rows, max_age_days=0)
    assert values[0] == 1 and np.isnan(values[1])


def test_delayed_prior_input_cannot_leak_into_rank_or_change():
    b = Builder(candles())
    rows = [{"source_date": d, "available_at": d + "T18:00:00+08:00", "value": i}
            for i, d in enumerate(b.frame.index)]
    rows[250]["available_at"] = b.frame.index[260] + "T18:00:00+08:00"
    b.add("delayed", "Delayed", "fixture", "fixture", rows, max_age_days=0)
    f, _ = b.finish()
    assert np.isnan(f["csi500-delayed-pct"].iloc[252])
    assert np.isnan(f["csi500-delayed-change-3d"].iloc[253])


def test_monthly_thresholds_use_source_months_not_daily_repetitions():
    b = Builder(candles())
    rows = [{"source_date": "2021-01-31", "available_at": "2021-02-05T18:00:00+08:00", "value": 1},
            {"source_date": "2021-02-28", "available_at": "2021-03-05T18:00:00+08:00", "value": 9}]
    b.add("monthly", "Monthly", "macro", "fixture", rows, frequency="monthly", max_age_days=180)
    _, catalog = b.finish()
    assert "csi500-monthly-pct" not in catalog
    assert catalog["csi500-monthly"].candidate_thresholds[0] == 1.8
    assert catalog["csi500-monthly"].observations == 2


def test_unverified_data_is_explicitly_diagnostic():
    b = Builder(candles(3))
    b.add("legacy", "Legacy", "diagnostic", "legacy", [
        {"source_date": date(2021, 1, 1), "value": 50}], eligible=False, reason="No first-release timestamp")
    _, catalog = b.finish()
    assert catalog["csi500-legacy"].eligibility == "diagnostic"
    assert catalog["csi500-legacy"].reason == "No first-release timestamp"


def test_monthly_change_cannot_use_later_revision():
    b = Builder(candles())
    b.add("monthly-vintage", "Monthly", "macro", "fixture", [
        {"source_date": "2021-01-31", "available_at": "2021-02-05T18:00:00+08:00", "value": 1},
        {"source_date": "2021-01-31", "available_at": "2021-07-05T18:00:00+08:00", "value": 9},
        {"source_date": "2021-04-30", "available_at": "2021-05-05T18:00:00+08:00", "value": 4},
    ], frequency="monthly", max_age_days=180)
    f, _ = b.finish()
    assert f.loc["2021-05-05", "csi500-monthly-vintage-change-3m"] == 3
    assert f.loc["2021-07-06", "csi500-monthly-vintage-change-3m"] == 3


def test_late_branch_off_before_warmup_missing_afterward(research_module):
    f = pd.DataFrame({"base": [0, 0, 1], "late": [np.nan, np.nan, np.nan], "gate": [0, 1, 1]})
    rules = [{"conditions": [research_module.condition("base", "gte", 1)]},
             {"conditions": [research_module.condition("gate", "gte", 1), research_module.condition("late", "gte", 1)]}]
    hit, known = research_module.matches(f, rules)
    assert hit.tolist() == [False, False, True]
    assert known.tolist() == [True, False, True]


def test_unknown_same_bar_order_not_counted_favorable(research_module):
    f = pd.DataFrame({"open": [100] * 25, "high": [100] * 25, "low": [100] * 25, "close": [100] * 25},
                     index=pd.bdate_range("2022-01-04", periods=25).strftime("%Y-%m-%d"))
    f.iloc[1, f.columns.get_loc("high")] = 106
    f.iloc[1, f.columns.get_loc("low")] = 96
    search = research_module.Search(f, {}, "bear", "low", [])
    mask = np.zeros(len(f), bool)
    mask[0] = True
    result = search.metrics(mask)
    assert result["unknown_order"] == 1
    assert result["favorable_first_pct"] == 0
    assert result["adverse_first_pct"] == 0


def test_financing_decimal_holiday_lag_and_missing_exchange():
    dates = ["2024-04-03", "2024-04-08", "2024-04-09"]
    rows = [{"trade_date": d, "exchange": exchange, "net": Decimal(str(value))}
            for d, exchange, value in [(dates[0], "SSE", 1e8), (dates[0], "SZSE", 2e8),
                                        (dates[1], "SSE", 5e8), (dates[2], "SSE", 6e8), (dates[2], "SZSE", 7e8)]]
    values = known_financing_values(rows, dates, "net")
    assert np.isnan(values.iloc[0])
    assert values.iloc[1] == 3
    assert np.isnan(values.iloc[2])


def test_option_month_pc_kept_contract_month_is_not_a_factor():
    values = dict(option_numeric_fields({"option_pc_current_month": 1.2, "option_pc_next_month": 1.5,
        "option_pc_quarter_1": 1.6, "option_pc_current_month_contract_month": "2610", "product_code": "510500",
        "option_pc_current_month_special_flag": 0, "sample_count": 20}))
    assert values == {"option_pc_current_month": 1.2, "option_pc_next_month": 1.5, "option_pc_quarter_1": 1.6}


def test_formal_color_cap_cannot_be_diluted_by_older_history(research_module):
    dates = pd.bdate_range("2015-07-01", periods=650).strftime("%Y-%m-%d").tolist()
    dates += pd.bdate_range("2022-01-04", periods=100).strftime("%Y-%m-%d").tolist()
    f = pd.DataFrame({"open": 100, "high": 106, "low": 99, "close": 100,
                      "factor": [0] * 650 + [1] * 100}, index=dates)
    catalog = {"factor": {"eligibility": "eligible", "transform": "raw", "family": "fixture"}}
    search = research_module.Search(f, catalog, "bear", "low", [])
    trial = search.evaluate([{"conditions": [research_module.condition("factor", "gte", 1)]}], "single")
    assert trial["metrics"]["color_day_pct"] < 35
    assert trial["formal_metrics"]["color_day_pct"] == 100
    assert "color_days" in trial["rejected"]


def test_no_formal_event_is_not_a_qualified_strategy(research_module):
    dates = pd.bdate_range("2015-07-01", periods=100).strftime("%Y-%m-%d").tolist()
    dates += pd.bdate_range("2022-01-04", periods=100).strftime("%Y-%m-%d").tolist()
    f = pd.DataFrame({"open": 100, "high": 106, "low": 99, "close": 100,
                      "factor": [1] + [0] * 199}, index=dates)
    catalog = {"factor": {"eligibility": "eligible", "transform": "raw", "family": "fixture"}}
    search = research_module.Search(f, catalog, "bear", "low", [])
    trial = search.evaluate([{"conditions": [research_module.condition("factor", "gte", 1)]}], "single")
    assert trial["metrics"]["evaluated"] == 1
    assert trial["formal_metrics"]["evaluated"] == 0
    assert "no_formal_complete_outcomes" in trial["rejected"]


def test_selected_runtime_values_and_future_append_match_research():
    meta = PUBLIC_FIELDS["csi500-index-daily-data-sh000142-close-price-pct"]
    recipe = meta["recipe"]
    def compute(n):
        data = candles(n)
        rows = [{"trade_date": r["trade_date"], "close_price": 100 + i % 30} for i, r in enumerate(data)]
        fields = {"csi500-index-daily-data-sh000142-close-price-pct": meta}
        return selected_features(data, {recipe["source_key"]: rows}, fields)
    before, after = compute(280), compute(300)
    pd.testing.assert_frame_equal(before, after.loc[before.index])
    assert np.isnan(before.iloc[251, 0])
    assert np.isfinite(before.iloc[252, 0])


def test_selected_fields_only_support_csi500():
    from app.services.quant_service import QuantService
    service = QuantService.__new__(QuantService)
    assert set(PUBLIC_FIELDS) <= set(service._allowed_snapshot_filter_keys("index", "cn", "sh000905", "中证500"))
    assert not set(PUBLIC_FIELDS).intersection(service._allowed_snapshot_filter_keys("index", "cn", "sh000852", "中证1000"))
    payload = {"strategy_type": "index", "target_market": "cn", "target_code": "sh000852",
               "red_filter_groups": [{"conditions": [{"type": "numeric", "field": next(iter(PUBLIC_FIELDS)), "operator": "gte", "value": 1}]}]}
    with pytest.raises(ValueError, match="仅支持中证500"):
        service._validate_strategy_payload(payload)


def test_coverage_uses_three_valued_branches_not_all_columns(research_module):
    from app.services.csi500_swing_features import rules_status
    groups = [{"conditions": [research_module.condition("base", "gte", 1)]},
              {"conditions": [research_module.condition("gate", "gte", 1), research_module.condition("late", "gte", 1)]}]
    assert rules_status({"base": 1, "gate": 1, "late": None}, groups) is True
    assert rules_status({"base": 0, "gate": 0, "late": None}, groups) is False
    assert rules_status({"base": 0, "gate": 1, "late": None}, groups) is None


def test_selected_option_recipe_keeps_source_warmup_and_missing_day():
    import json
    key = "csi500-option-szse-159922-exchange-option-pc-json-option-volume-pc-ratio-pct"
    meta = PUBLIC_FIELDS[key]
    recipe = meta["recipe"]
    days = pd.bdate_range("2023-01-03", periods=300)
    quotes = [{"trade_date": d.date(), "open": 100, "high": 102, "low": 98, "close": 101} for d in days]
    def compute(n):
        rows = [{"trade_date": q["trade_date"], "exchange_option_pc_json": json.dumps({
            "szse:159922": {"option_volume_pc_ratio": i % 37},
            "sse:510500": {"option_volume_pc_ratio": 999},
        })} for i, q in enumerate(quotes[:n])]
        rows[260]["exchange_option_pc_json"] = json.dumps({"sse:510500": {"option_volume_pc_ratio": 999}})
        return selected_features(quotes[:n], {recipe["source_key"]: rows}, {key: meta})
    short, long = compute(280), compute(300)
    pd.testing.assert_frame_equal(short, long.loc[short.index])
    assert np.isnan(short.iloc[251, 0])
    assert short.iloc[252, 0] == pytest.approx((252 % 37 > np.arange(252) % 37).mean() * 100
        + (252 % 37 == np.arange(252) % 37).mean() * 50)
    assert np.isnan(short.iloc[260, 0])


def test_option_recipe_prelisting_and_invalid_payload():
    from app.services.csi500_swing_features import option_source_rows
    recipe = PUBLIC_FIELDS["csi500-option-szse-159922-option-vix-json-vix-low-change-1d"]["recipe"]
    rows = [
        {"trade_date": "2022-09-16", "option_vix_json": {"szse:159922": {"vix_low": 999}}},
        {"trade_date": "2022-09-19", "option_vix_json": {"szse:159922": {"vix_low": 20}}},
        {"trade_date": "2022-09-20", "option_vix_json": None},
    ]
    values = option_source_rows(rows, recipe)
    assert [row["option_vix_json"] for row in values] == [20, None]
    with pytest.raises(ValueError, match="payload"):
        option_source_rows([{"trade_date": "2023-01-03", "option_vix_json": "[]"}], recipe)


def test_option_changes_share_recipe_and_use_source_observations():
    keys = ["csi500-option-szse-159922-exchange-option-pc-json-option-turnover-pc-ratio-change-" + n + "d"
            for n in ("1", "3")]
    fields = {key: PUBLIC_FIELDS[key] for key in keys}
    recipe = fields[keys[0]]["recipe"]
    quotes = candles(5)
    recipe = {**recipe, "listed_since": "2021-01-01"}
    fields = {key: {**meta, "recipe": recipe} for key, meta in fields.items()}
    rows = [{"trade_date": q["trade_date"], "exchange_option_pc_json": {"szse:159922": {
        "option_turnover_pc_ratio": value}}} for q, value in zip(quotes, [1, 2, None, 4, 6])]
    values = selected_features(quotes, {recipe["source_key"]: rows}, fields)
    assert values.iloc[1, 0] == 1
    assert np.isnan(values.iloc[2, 0])
    assert values.iloc[3, 0] == 2
    assert values.iloc[4, 1] == 5


def test_frontend_and_backend_selected_registries_agree():
    import json
    frontend = Path(__file__).resolve().parents[2] / "frontend/src/utils/csi500SwingFields.json"
    fields = json.loads(frontend.read_text())
    assert {f["key"] for f in fields} == set(PUBLIC_FIELDS)
    for field in fields:
        assert all(field[k] == PUBLIC_FIELDS[field["key"]][k] for k in ("label", "unit", "plot"))


def test_option_strategy_has_independent_name_and_actual_start(research_module):
    import importlib
    from app.services.csi500_swing_features import config_fingerprint
    installer = importlib.import_module("install_csi500_option_swing")
    rule = [{"conditions": [{"type": "numeric", "field": "csi500-position-20d", "operator": "lte", "value": 30}]}]
    pair = {"low": {"rules": rule}, "high": {"rules": rule}, "start_date": "2026-02-03",
            "backtest": {"candidate": {"mdd_pct": 9.2}}}
    data, fingerprint = installer.payload("bull", pair)
    assert data["name"] == "中证500牛市波段-期权版"
    assert data["start_date"] == date(2026, 2, 3)
    assert data["signal_buy_color"] == "red" and data["signal_sell_color"] == "blue"
    assert data["purple_conflict_mode"] == "sell_first"
    assert data["buy_position_pct"] == .5 and data["sell_position_pct"] == 1
    assert "基础覆盖2022" not in data["notes"]
    assert fingerprint == config_fingerprint({"red": rule, "blue": rule})


def test_install_hash_preserves_legacy_and_other_owner(research_module):
    import importlib
    installer = importlib.import_module("install_csi500_option_swing")
    class Rows:
        def __init__(self, rows): self.rows = rows
        def execute(self, query): return self
        def mappings(self): return self.rows
    old = {"id": 46, "owner_user_id": 1, "name": "中证500牛市波段", "target_code": "sh000905"}
    own = {"id": 48, "owner_user_id": 1, "name": installer.NAMES["bull"], "target_code": "sh000905"}
    other = {**own, "id": 100, "owner_user_id": 2}
    original = installer.unrelated_hash(Rows([old, own, other]), 1)
    assert installer.unrelated_hash(Rows([old, {**own, "notes": "updated"}, other]), 1) == original
    assert installer.unrelated_hash(Rows([{**old, "notes": "changed"}, own, other]), 1) != original
    assert installer.unrelated_hash(Rows([old, own, {**other, "notes": "changed"}]), 1) != original


def test_option_coverage_cannot_claim_early_decidable_false_as_warmup():
    from app.services.csi500_swing_features import option_coverage_start
    keys = {"csi500-position-120d-pct",
            "csi500-option-szse-159922-exchange-option-pc-json-option-volume-pc-ratio-pct"}
    assert option_coverage_start(keys, date(2023, 1, 1)) == "2023-12-29"
    assert option_coverage_start(keys, date(2024, 1, 2)) == "2024-01-02"
    assert option_coverage_start({"csi500-position-120d-pct"}, date(2022, 1, 1)) == ""
