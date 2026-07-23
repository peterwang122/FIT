from pathlib import Path
import sys

import pandas as pd
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.analyze_vix_bottom_options import (  # noqa: E402
    build_absolute_threshold_candidates,
    build_event_top_trades,
    build_expiry_bucket_map,
    calculate_long_call_trade,
    compute_bottom_metrics,
    detect_absolute_peak_events,
    detect_high_vix_episode_events,
    detect_threshold_events,
    format_strike_bucket,
    product_display_name,
    select_contract,
)


def test_threshold_event_uses_crossing_and_requires_three_day_reset():
    dates = pd.date_range("2026-01-01", periods=9, freq="D")
    qvix = pd.DataFrame({"close_price": [9, 11, 12, 9, 9, 9, 11, 12, 8]}, index=dates)
    threshold = pd.Series(10.0, index=dates)

    events = detect_threshold_events(qvix, threshold, "fixed-10", "固定阈值10")

    assert [item["signal_date"] for item in events] == [dates[1], dates[6]]


def test_threshold_event_requires_absolute_floor_when_supplied():
    dates = pd.date_range("2026-01-01", periods=5, freq="D")
    qvix = pd.DataFrame({"close_price": [17, 19, 18, 21, 22]}, index=dates)
    threshold = pd.Series(18.0, index=dates)

    events = detect_threshold_events(qvix, threshold, "rolling", "滚动分位", minimum_signal_value=20)

    assert [item["signal_date"] for item in events] == [dates[3]]
    assert events[0]["threshold_value"] == 20


def test_absolute_peak_event_selects_highest_day_inside_high_vix_cluster():
    dates = pd.date_range("2026-01-01", periods=8, freq="D")
    qvix = pd.DataFrame({"close_price": [18, 21, 26, 23, 19, 18, 17, 22]}, index=dates)

    events = detect_absolute_peak_events(qvix, 20, "peak", "绝对峰值")

    assert [item["signal_date"] for item in events] == [dates[2], dates[7]]
    assert events[0]["vix_close"] == 26


def test_high_vix_episode_outputs_first_cross_and_range_peak_from_daily_high():
    dates = pd.date_range("2026-01-01", periods=9, freq="D")
    qvix = pd.DataFrame(
        {
            "high_price": [18, 21, 26, 23, 19, 18, 17, 22, 19],
            "close_price": [17, 19, 20, 18, 18, 17, 16, 18, 17],
        },
        index=dates,
    )

    events = detect_high_vix_episode_events(qvix, 20)

    assert list(events["event_type"]) == [
        "first_cross",
        "range_peak",
        "first_cross",
        "range_peak",
    ]
    assert list(events["signal_date"]) == [dates[1], dates[2], dates[7], dates[7]]
    assert list(events["vix_high"]) == [21, 26, 22, 22]
    assert list(events["vix_close"]) == [19, 20, 18, 18]


def test_absolute_threshold_candidates_use_high_price_and_respect_floor():
    qvix = pd.DataFrame(
        {
            "high_price": list(range(10, 50)),
            "close_price": [5] * 40,
        },
        index=pd.date_range("2026-01-01", periods=40, freq="D"),
    )

    candidates = build_absolute_threshold_candidates(qvix, 25)

    assert candidates
    assert min(candidates) >= 25
    assert max(candidates) <= 49


def test_event_top_trades_only_exports_trade_fields():
    outcomes = pd.DataFrame(
        [
            {
                "index_name": "沪深300",
                "signal_date": pd.Timestamp("2026-01-05"),
                "threshold_mode": "max_return",
                "event_type": "range_peak",
                "product_code": "IO",
                "product_name": "沪深300股指期权",
                "exchange": "CFFEX",
                "strategy_type": "long_call",
                "option_type": "CALL",
                "expiry_bucket": "current",
                "expiry_bucket_label": "当月",
                "dte_bucket": "current",
                "contract_month_label": "当月(2601)",
                "moneyness": "otm_1",
                "moneyness_label": "虚一档",
                "holding_days": 5,
                "long_contract_code": "IO2601-C-4000",
                "long_contract_month": "2601",
                "long_strike": 4000,
                "net_return": 1.25,
                "mae": -0.1,
                "mfe": 1.4,
            }
        ]
    )

    rows = build_event_top_trades(outcomes, "沪深300", "2026-01-05")

    assert len(rows) == 1
    assert rows[0]["long_contract_code"] == "IO2601-C-4000"
    assert "threshold_mode" not in rows[0]
    assert "event_type" not in rows[0]


def test_bottom_metrics_require_small_followup_loss_and_five_percent_rebound():
    dates = pd.date_range("2026-01-01", periods=25, freq="D")
    values = [100, 99, 98, 99, 101, 103, 105] + [105] * 18
    prices = pd.Series(values, index=dates, dtype=float)

    result = compute_bottom_metrics(dates[0], prices)

    assert result["bottom_hit_1pct"] is False
    assert result["bottom_hit_3pct"] is True
    assert result["bottom_hit_5pct"] is True
    assert result["bottom_status"] == "true_bottom"


def test_rally_before_signal_is_judged_as_top_not_false_bottom():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    values = [100 + index for index in range(41)] + [139, 138, 136, 132, 128] + [128] * 24
    prices = pd.Series(values, index=dates, dtype=float)

    result = compute_bottom_metrics(dates[40], prices)

    assert result["trade_direction"] == "bearish"
    assert result["bottom_status"] == "true_top"
    assert result["bottom_hit_3pct"] is None
    assert result["top_hit_3pct"] is True


def test_contract_selection_respects_dte_expiry_and_nearest_strike():
    entry_date = pd.Timestamp("2026-01-05")
    rows = pd.DataFrame(
        [
            {
                "contract_code": "near",
                "contract_month": "2601",
                "option_type": "CALL",
                "strike_price": 100,
                "open_price": 5,
                "high_price": 6,
                "low_price": 4,
                "close_price": 5.5,
                "volume": 100,
                "open_interest": 200,
                "last_trade_date": pd.Timestamp("2026-01-20"),
                "dte": 15,
            },
            {
                "contract_code": "target",
                "contract_month": "2601",
                "option_type": "CALL",
                "strike_price": 105,
                "open_price": 3,
                "high_price": 4,
                "low_price": 2,
                "close_price": 3.5,
                "volume": 100,
                "open_interest": 200,
                "last_trade_date": pd.Timestamp("2026-01-25"),
                "dte": 20,
            },
        ]
    )

    selected = select_contract(
        rows,
        entry_date=entry_date,
        underlying_price=100,
        strike_bucket="otm_1",
        expiry_bucket="current",
        minimum_expiry=entry_date + pd.Timedelta(days=10),
    )

    assert selected is not None
    assert selected["contract_code"] == "target"


def test_contract_selection_can_select_put_contracts():
    rows = pd.DataFrame(
        [
            {
                "contract_code": "call",
                "contract_month": "2601",
                "option_type": "CALL",
                "strike_price": 105,
                "open_price": 3,
                "high_price": 4,
                "low_price": 2,
                "close_price": 3.5,
                "volume": 100,
                "open_interest": 200,
                "last_trade_date": pd.Timestamp("2026-01-25"),
                "dte": 20,
            },
            {
                "contract_code": "put",
                "contract_month": "2601",
                "option_type": "PUT",
                "strike_price": 105,
                "open_price": 4,
                "high_price": 5,
                "low_price": 3,
                "close_price": 4.5,
                "volume": 100,
                "open_interest": 200,
                "last_trade_date": pd.Timestamp("2026-01-25"),
                "dte": 20,
            },
        ]
    )

    selected = select_contract(
        rows,
        entry_date=pd.Timestamp("2026-01-05"),
        underlying_price=100,
        strike_bucket="atm",
        expiry_bucket="current",
        minimum_expiry=pd.Timestamp("2026-01-15"),
        option_type="PUT",
    )

    assert selected is not None
    assert selected["contract_code"] == "put"


def test_expiry_bucket_map_uses_current_next_and_quarter_months():
    bucket_map = build_expiry_bucket_map(
        pd.Timestamp("2026-01-05"),
        ["2601", "2602", "2603", "2606", "2609"],
    )

    assert bucket_map[2026 * 12 + 1] == "current"
    assert bucket_map[2026 * 12 + 2] == "next"
    assert bucket_map[2026 * 12 + 3] == "quarter_1"
    assert bucket_map[2026 * 12 + 6] == "quarter_2"
    assert 2026 * 12 + 9 not in bucket_map


def test_strike_bucket_uses_plain_trading_labels():
    assert format_strike_bucket("itm_1") == "实一档"
    assert format_strike_bucket("itm_3") == "实三档"
    assert format_strike_bucket("atm") == "平值"
    assert format_strike_bucket("otm_2") == "虚二档"


def test_product_display_name_uses_exchange_and_index_instead_of_code():
    assert product_display_name("SSE", "中证500ETF期权") == "上交所 中证500ETF期权"
    assert product_display_name("CFFEX", "中证1000股指期权") == "中金所 中证1000股指期权"


@pytest.mark.parametrize(
    ("option_type", "bucket", "expected_strike"),
    [
        ("CALL", "itm_1", 95),
        ("CALL", "itm_2", 90),
        ("CALL", "otm_1", 105),
        ("PUT", "itm_1", 105),
        ("PUT", "otm_1", 95),
        ("PUT", "otm_2", 90),
    ],
)
def test_contract_selection_uses_real_strike_rank(option_type, bucket, expected_strike):
    entry_date = pd.Timestamp("2026-01-05")
    rows = pd.DataFrame(
        [
            {
                "contract_code": f"{option_type}-{strike}",
                "contract_month": "2601",
                "option_type": option_type,
                "strike_price": strike,
                "open_price": 3,
                "high_price": 4,
                "low_price": 2,
                "close_price": 3.5,
                "volume": 100,
                "open_interest": 200,
                "last_trade_date": pd.Timestamp("2026-01-25"),
                "dte": 20,
            }
            for strike in (90, 95, 100, 105, 110)
        ]
    )

    selected = select_contract(
        rows,
        entry_date=entry_date,
        underlying_price=100,
        strike_bucket=bucket,
        expiry_bucket="current",
        minimum_expiry=pd.Timestamp("2026-01-15"),
        option_type=option_type,
    )

    assert selected is not None
    assert selected["strike_price"] == expected_strike


def test_long_call_return_applies_both_sides_of_slippage():
    dates = pd.date_range("2026-01-05", periods=3, freq="D")
    history = pd.DataFrame({"close_price": [10, 8, 12]}, index=dates)
    row = pd.Series({"open_price": 10})

    result = calculate_long_call_trade(row, history, dates, dates[0], dates[2], slippage=0.005)

    assert result is not None
    assert result["gross_return"] == pytest.approx(0.2)
    assert result["net_return"] == pytest.approx(12 * 0.995 / (10 * 1.005) - 1)
    assert result["mae"] < 0
