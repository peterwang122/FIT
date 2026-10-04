"""Full-chain turnover must never be inferred from incomplete contract samples."""
from datetime import date
from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/maintenance/backfill_szse_159922_turnover.py"
spec = importlib.util.spec_from_file_location("turnover_backfill", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def contract(code="1", kind="CALL", **overrides):
    return {"exchange": "SZSE", "underlying_code": "159922", "contract_code": code,
            "option_type": kind, "listed_date": "2026-01-01", "last_trade_date": "2026-02-25",
            **overrides}


def test_full_chain_exact_ratio():
    result = m.turnover_coverage("2026-02-03", [contract(), contract("2", "PUT")],
                                 [{"contract_code": "1", "turnover": "123.45"},
                                  {"contract_code": "2", "turnover": "246.90"}])
    assert result["complete"] and result["option_turnover_pc_ratio"] == 2
    assert result["call_turnover_yuan"] == "123.45"


def test_missing_contract_is_not_complete():
    result = m.turnover_coverage("2026-02-03", [contract(), contract("2", "PUT")],
                                 [{"contract_code": "1", "turnover": 100}])
    assert not result["complete"] and result["option_turnover_pc_ratio"] is None
    assert result["missing_contracts"] == ["2"]


@pytest.mark.parametrize("amount", [None, -1, "NaN", "Infinity"])
def test_missing_amount_is_not_zero(amount):
    result = m.turnover_coverage("2026-02-03", [contract(), contract("2", "PUT")],
                                 [{"contract_code": "1", "turnover": 100},
                                  {"contract_code": "2", "turnover": amount}])
    assert not result["complete"] and result["option_turnover_pc_ratio"] is None


def test_zero_original_amount_and_zero_denominator():
    result = m.turnover_coverage("2026-02-03", [contract(), contract("2", "PUT")],
                                 [{"contract_code": "1", "turnover": 0},
                                  {"contract_code": "2", "turnover": 0}])
    assert result["complete"] and result["option_turnover_pc_ratio"] is None


def test_future_listing_and_expiry_follow_existing_scope():
    contracts = [contract(), contract("2", "PUT"),
                 contract("3", listed_date="2026-02-04"), contract("4", last_trade_date="2026-02-03")]
    result = m.turnover_coverage("2026-02-03", contracts,
                                 [{"contract_code": "1", "turnover": 100},
                                  {"contract_code": "2", "turnover": 200}])
    assert result["expected_contracts"] == 2 and result["complete"]


def test_original_history_validated_without_estimation():
    row = {"exchange": "SZSE", "contract_code": "1", "trade_date": "2026-02-03",
           "turnover": "123.45", "volume": "20"}
    result = m.valid_history([row], contract(), date(2026, 2, 3), {"2026-02-03"})
    assert result[0]["turnover"] == Decimal("123.45")
    with pytest.raises(ValueError, match="original amount"):
        m.valid_history([{**row, "turnover": None}], contract(), date(2026, 2, 3), {"2026-02-03"})
    with pytest.raises(ValueError, match="source date"):
        m.valid_history([row], contract(), date(2026, 2, 3), set())
    with pytest.raises(ValueError, match="Only SZSE"):
        m.valid_history([row], contract(underlying_code="159919"), date(2026, 2, 3), {"2026-02-03"})


def zero_quote():
    return {"code": "0", "data": {"marketTime": "2026-09-30 15:00:00", "code": "official-code",
        "amount": 0, "picupdata": [["09:30", "1", "1", "0", "0", 0, 0]] * 240}}


def test_official_no_trade_session_is_not_an_estimated_price():
    info = contract(contract_trade_code="official-code")
    row = m.official_zero_trade_row(zero_quote(), info, "2026-09-30")
    assert row["turnover"] == 0 and row["volume"] == 0
    assert row.get("close_price") is None


@pytest.mark.parametrize("field,value", [
    ("marketTime", "2026-09-29 15:00:00"), ("code", "another-code"),
    ("amount", None), ("amount", 1), ("picupdata", []),
    ("picupdata", [["09:30", "1", "1", "0", "0", 1, 0]] * 240),
])
def test_no_zero_inference_from_missing_or_inconsistent_quote(field, value):
    payload = zero_quote()
    payload["data"][field] = value
    assert m.official_zero_trade_row(payload, contract(contract_trade_code="official-code"), "2026-09-30") is None
