from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.quant_service import QuantService
from app.services.vix_option_strategy_trade_service import (
    VixOptionStrategyTradeService,
    _calendar_expiry_bucket_map,
    _expiry_bucket_map,
)


def _template(option_type: str = "CALL") -> dict:
    return {
        "enabled": True,
        "report_generated_at": "2026-07-13T17:18:41+08:00",
        "direction_mode": "dynamic",
        "product_code": "510500",
        "product_name": "中证500ETF期权",
        "exchange": "SSE",
        "option_type": option_type,
        "strategy_type": "long_call" if option_type == "CALL" else "long_put",
        "expiry_bucket": "current",
        "expiry_bucket_label": "当月",
        "moneyness": "itm_1",
        "moneyness_label": "实一档",
        "holding_days": 1,
        "slippage": 0.005,
        "initial_capital": 1_000_000,
        "contracts_per_trade": 1,
    }


def _frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    target_index = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "close_price": 100.0},
            {"trade_date": "2026-01-06", "close_price": 101.0},
            {"trade_date": "2026-01-07", "close_price": 102.0},
        ]
    )
    underlying = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "open_price": 99.0, "close_price": 100.0},
            {"trade_date": "2026-01-06", "open_price": 100.0, "close_price": 101.0},
            {"trade_date": "2026-01-07", "open_price": 102.0, "close_price": 102.0},
        ]
    )
    option_rows = []
    for strike, code, open_price in ((90.0, "CALL90", 1.0), (100.0, "CALL100", 0.8), (110.0, "CALL110", 0.5)):
        option_rows.append(
            {
                "contract_code": code,
                "trade_date": "2026-01-06",
                "contract_month": "2601",
                "option_type": "CALL",
                "strike_price": strike,
                "open_price": open_price,
                "high_price": open_price + 0.2,
                "low_price": open_price - 0.2,
                "close_price": open_price + 0.1,
                "volume": 100,
                "open_interest": 200,
                "last_trade_date": "2026-01-16",
                "contract_unit": 10_000,
            }
        )
    option_rows.append(
        {
            "contract_code": "CALL90",
            "trade_date": "2026-01-07",
            "contract_month": "2601",
            "option_type": "CALL",
            "strike_price": 90.0,
            "open_price": 1.2,
            "high_price": 1.6,
            "low_price": 1.1,
            "close_price": 1.5,
            "volume": 120,
            "open_interest": 180,
            "last_trade_date": "2026-01-16",
            "contract_unit": 10_000,
        }
    )
    return target_index, underlying, pd.DataFrame(option_rows)


def test_option_template_trade_selects_real_contract_and_calculates_slippage_profit():
    target_index, underlying, options = _frames()
    result = VixOptionStrategyTradeService(None).calculate_from_frames(
        [date(2026, 1, 5)],
        _template(),
        target_index,
        underlying,
        options,
    )

    assert result["summary"]["completed_count"] == 1
    trade = result["trades"][0]
    assert trade["contract_code"] == "CALL90"
    assert trade["contract_month_label"] == "当月(2601)"
    assert trade["buy_date"] == date(2026, 1, 6)
    assert trade["sell_date"] == date(2026, 1, 7)
    assert trade["buy_price"] == pytest.approx(1.005)
    assert trade["sell_price"] == pytest.approx(1.4925)
    assert trade["contract_quantity"] == 1
    assert trade["buy_amount"] == pytest.approx(10_050.0)
    assert trade["sell_amount"] == pytest.approx(14_925.0)
    assert trade["profit_per_contract"] == pytest.approx(4_875.0)
    assert trade["return_pct"] == pytest.approx((1.4925 / 1.005 - 1) * 100)
    assert result["initial_capital"] == 1_000_000
    assert result["cumulative_return_pct"] == pytest.approx(0.4875)
    assert result["points"][0]["position_value"] == 0
    assert result["points"][1]["position_value"] == pytest.approx(11_000.0)
    assert result["points"][2]["position_value"] == 0


def test_option_template_uses_signal_direction_instead_of_fixed_template_direction():
    target_index, underlying, options = _frames()
    result = VixOptionStrategyTradeService(None).calculate_from_frames(
        [date(2026, 1, 5)],
        _template("PUT"),
        target_index,
        underlying,
        options,
    )

    assert result["summary"]["direction_mismatch_count"] == 0
    assert result["trades"][0]["status"] == "completed"
    assert result["trades"][0]["option_type"] == "CALL"
    assert result["trades"][0]["contract_code"] == "CALL90"


def test_option_template_buys_put_when_prior_rally_requires_put():
    signal_date = pd.Timestamp("2026-02-02")
    index_dates = pd.bdate_range(end=signal_date, periods=21)
    target_index = pd.DataFrame(
        {
            "trade_date": index_dates,
            "close_price": [100 + index * 0.25 for index in range(len(index_dates))],
        }
    )
    underlying = pd.DataFrame(
        [
            {"trade_date": signal_date, "open_price": 104.0, "close_price": 105.0},
            {"trade_date": "2026-02-03", "open_price": 105.0, "close_price": 105.0},
            {"trade_date": "2026-02-04", "open_price": 103.0, "close_price": 103.0},
        ]
    )
    option_rows = []
    for strike, code, open_price in ((90.0, "PUT90", 0.5), (100.0, "PUT100", 0.8), (110.0, "PUT110", 1.0)):
        option_rows.append(
            {
                "contract_code": code,
                "trade_date": "2026-02-03",
                "contract_month": "2602",
                "option_type": "PUT",
                "strike_price": strike,
                "open_price": open_price,
                "high_price": open_price + 0.2,
                "low_price": open_price - 0.2,
                "close_price": open_price + 0.1,
                "volume": 100,
                "open_interest": 200,
                "last_trade_date": "2026-02-20",
                "contract_unit": 10_000,
            }
        )
    option_rows.append(
        {
            "contract_code": "PUT110",
            "trade_date": "2026-02-04",
            "contract_month": "2602",
            "option_type": "PUT",
            "strike_price": 110.0,
            "open_price": 1.1,
            "high_price": 1.5,
            "low_price": 1.0,
            "close_price": 1.4,
            "volume": 100,
            "open_interest": 200,
            "last_trade_date": "2026-02-20",
            "contract_unit": 10_000,
        }
    )

    result = VixOptionStrategyTradeService(None).calculate_from_frames(
        [signal_date.date()],
        _template("CALL"),
        target_index,
        underlying,
        pd.DataFrame(option_rows),
    )

    assert result["summary"]["completed_count"] == 1
    assert result["summary"]["direction_mismatch_count"] == 0
    assert result["trades"][0]["option_type"] == "PUT"
    assert result["trades"][0]["contract_code"] == "PUT110"


def test_current_bucket_rolls_to_first_contract_that_covers_holding_period():
    entry_rows = pd.DataFrame(
        [
            {
                "contract_code": "PUT-CURRENT",
                "contract_month": "2510",
                "option_type": "PUT",
                "strike_price": 110.0,
                "open_price": 1.0,
                "high_price": 1.2,
                "low_price": 0.8,
                "close_price": 1.1,
                "volume": 100,
                "open_interest": 100,
                    "last_trade_date": pd.Timestamp("2025-10-17"),
                    "dte": 3,
            },
            {
                "contract_code": "PUT-ROLLED",
                "contract_month": "2511",
                "option_type": "PUT",
                "strike_price": 110.0,
                "open_price": 1.1,
                "high_price": 1.3,
                "low_price": 0.9,
                "close_price": 1.2,
                "volume": 100,
                "open_interest": 100,
                    "last_trade_date": pd.Timestamp("2025-11-21"),
                    "dte": 38,
            },
        ]
    )

    selected = VixOptionStrategyTradeService._select_contract(
        entry_rows,
        pd.Timestamp("2025-10-14"),
        100.0,
        {**_template("PUT"), "expiry_bucket": "current", "moneyness": "atm"},
        pd.Timestamp("2025-10-19"),
    )

    assert selected is not None
    assert selected["contract_code"] == "PUT-ROLLED"
    assert _expiry_bucket_map(["2511", "2512", "2603", "2606"]) == {
        2025 * 12 + 11: "current",
        2025 * 12 + 12: "next",
        2026 * 12 + 3: "quarter_1",
        2026 * 12 + 6: "quarter_2",
    }
    assert _calendar_expiry_bucket_map(
        pd.Timestamp("2015-04-10"),
        ["1504", "1505", "1506", "1509"],
    )[2015 * 12 + 9] == "quarter_2"


def test_research_option_template_is_separate_from_scan_trade_config():
    service = QuantService(MagicMock())
    normalized = service._normalize_scan_trade_config({"research_option_template": _template()})

    assert "research_option_template" not in normalized
    assert service._normalize_research_option_template(_template()) == _template()
