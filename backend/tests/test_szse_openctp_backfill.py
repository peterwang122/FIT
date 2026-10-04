"""Dated snapshots must preserve contract identity, amounts and source time."""
from decimal import Decimal
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/maintenance/backfill_szse_159922_openctp.py"
spec = importlib.util.spec_from_file_location("openctp_turnover_backfill", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def info(**overrides):
    return {"exchange": "SZSE", "underlying_code": "159922", "contract_code": "90007889",
            "listed_date": "2026-07-23", "last_trade_date": "2027-03-24", **overrides}


def quote(**overrides):
    return {"ExchangeID": "SZSE", "InstrumentID": "90007889",
            "InstrumentName": "中证500ETF购3月2850", "TradingDay": "2026-09-30",
            "UpdateDate": "2026-09-30", "UpdateTime": "15:55:03",
            "Turnover": "43673", "Volume": 18, "OpenPrice": "0.2404",
            "HighestPrice": "0.2429", "LowestPrice": "0.2404", "ClosePrice": "0.2428",
            **overrides}


def test_original_snapshot_amount_is_not_volume_times_close():
    row = m.snapshot_row(quote(), info(), "2026-09-30")
    assert row["turnover"] == Decimal("43673")
    assert row["turnover"] != row["volume"] * row["close_price"] * 10000
    assert row["raw_json"]["turnover_snapshot"]["UpdateTime"] == "15:55:03"


def test_zero_session_does_not_copy_carried_prices():
    row = m.snapshot_row(quote(Turnover=0, Volume=0), info(), "2026-09-30")
    assert row["turnover"] == 0
    assert row["close_price"] is None and row["open_price"] is None


@pytest.mark.parametrize("changes", [
    {"ExchangeID": "SSE"}, {"InstrumentID": "90003229"},
    {"InstrumentName": "沪深300ETF购3月2850"}, {"TradingDay": "2026-09-29"},
    {"UpdateDate": "2026-09-29"}, {"UpdateTime": "14:59:59"},
    {"Turnover": None}, {"Turnover": "NaN"}, {"Turnover": -1},
    {"Turnover": 0}, {"Volume": 0}, {"Volume": "1.5"}, {"ClosePrice": None},
])
def test_bad_snapshot_cannot_be_persisted(changes):
    with pytest.raises(ValueError):
        m.snapshot_row(quote(**changes), info(), "2026-09-30")


def test_listing_and_expiry_are_checked_against_official_metadata():
    with pytest.raises(ValueError):
        m.snapshot_row(quote(), info(last_trade_date="2026-09-23"), "2026-09-30")


def test_existing_original_amount_is_not_replaced():
    key = ("90007889", "2026-09-30")
    source = {"2026-09-30": [quote()]}
    contracts = {"90007889": info()}
    planned, compared = m.plan_rows(source, contracts, {key: {"turnover": Decimal("43673")}})
    assert not planned and compared == 1
    with pytest.raises(ValueError, match="disagrees"):
        m.plan_rows(source, contracts, {key: {"turnover": Decimal("43674")}})


def test_missing_amount_is_planned_and_unknown_contract_is_rejected():
    key = ("90007889", "2026-09-30")
    source = {"2026-09-30": [quote()]}
    planned, compared = m.plan_rows(source, {"90007889": info()}, {key: {"turnover": None}})
    assert len(planned) == 1 and compared == 0
    with pytest.raises(ValueError, match="official metadata"):
        m.plan_rows(source, {}, {})


def test_duplicate_contract_is_not_counted_twice():
    with pytest.raises(ValueError, match="Duplicate"):
        m.plan_rows({"2026-09-30": [quote(), quote()]}, {"90007889": info()}, {})


def test_dashboard_refresh_changes_only_the_target_turnover_fields():
    payload = {"sse:510500": {"option_turnover_pc_ratio": 2},
               "szse:159922": {"option_volume_pc_ratio": 3, "option_turnover_pc_ratio": 9}}
    coverage = {"trade_date": "2026-09-30", "complete": True, "option_turnover_pc_ratio": 0.84}
    result = json.loads(m.dashboard_payload(payload, coverage))
    assert result["sse:510500"] == {"option_turnover_pc_ratio": 2}
    assert result["szse:159922"]["option_volume_pc_ratio"] == 3
    assert result["szse:159922"]["option_turnover_pc_ratio"] == 0.84
    assert result["szse:159922"]["turnover_coverage"]["missing_reason"] is None


def test_incomplete_dashboard_keeps_the_partial_value_only_for_audit():
    payload = {"szse:159922": {"option_turnover_pc_ratio": 9}}
    coverage = {"trade_date": "2026-09-30", "complete": False, "option_turnover_pc_ratio": None}
    result = json.loads(m.dashboard_payload(payload, coverage))["szse:159922"]
    assert result["option_turnover_pc_ratio"] is None
    assert result["unverified_partial_turnover_pc_ratio"] == 9
