from datetime import date

import pytest

from app.services.csi1000_futures_analysis import (
    CONTRACT_MULTIPLIER,
    FEE_RATE,
    FuturesBar,
    FuturesUniverse,
    IndexBar,
    ZigZagPivot,
    ZigZagWave,
    contract_expiry,
    detect_zigzag_waves,
    simulate_wave_contract,
    tenor_label,
    third_friday,
)


def _futures_bar(
    trade_date: date,
    symbol: str,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    settle: float | None = None,
) -> FuturesBar:
    expiry = contract_expiry(symbol)
    assert expiry is not None
    return FuturesBar(
        trade_date=trade_date,
        symbol=symbol,
        open=open_price,
        high=high,
        low=low,
        close=close,
        settle=settle,
        volume=100,
        open_interest=1000,
        expiry=expiry,
    )


def _wave(direction: str, start: date, end: date, complete: bool = True) -> ZigZagWave:
    if direction == "up":
        start_pivot = ZigZagPivot("low", start, 6000, True, start)
        end_pivot = ZigZagPivot("high", end, 7500, complete, end if complete else None)
    else:
        start_pivot = ZigZagPivot("high", start, 7500, True, start)
        end_pivot = ZigZagPivot("low", end, 6000, complete, end if complete else None)
    return ZigZagWave(1, direction, start_pivot, end_pivot, complete)


def test_zigzag_20_percent_builds_up_down_and_provisional_waves():
    bars = [
        IndexBar(date(2025, 1, 2), 102, 105, 100, 103),
        IndexBar(date(2025, 1, 3), 112, 121, 110, 119),
        IndexBar(date(2025, 1, 6), 120, 125, 118, 123),
        IndexBar(date(2025, 1, 7), 105, 110, 99, 101),
        IndexBar(date(2025, 1, 8), 95, 100, 90, 92),
        IndexBar(date(2025, 1, 9), 103, 108, 100, 106),
    ]

    waves = detect_zigzag_waves(bars, 0.20)

    assert [(item.direction, item.complete) for item in waves] == [
        ("up", True),
        ("down", True),
        ("up", False),
    ]
    assert waves[0].start.value == 100
    assert waves[0].end.value == 125
    assert waves[1].end.value == 90


def test_all_actual_active_contracts_are_returned_without_four_contract_cap():
    trade_date = date(2025, 1, 6)
    symbols = ["IM2501", "IM2502", "IM2503", "IM2506", "IM2509", "IM2512"]
    universe = FuturesUniverse(
        [
            _futures_bar(trade_date, symbol, open_price=6000, high=6100, low=5900, close=6050)
            for symbol in symbols
        ]
    )

    assert [item.symbol for item in universe.active(trade_date)] == symbols
    assert tenor_label(5) == "第6到期"


def test_up_wave_uses_same_day_futures_low_and_high():
    start = date(2025, 1, 6)
    end = date(2025, 1, 10)
    universe = FuturesUniverse(
        [
            _futures_bar(start, "IM2502", open_price=6000, high=6060, low=5900, close=6020),
            _futures_bar(end, "IM2502", open_price=6200, high=6300, low=6150, close=6250),
        ]
    )

    result = simulate_wave_contract(universe, _wave("up", start, end), universe.active(start)[0], 0)

    expected_fee = (5900 + 6300) * CONTRACT_MULTIPLIER * FEE_RATE
    assert result["entry_price"] == 5900
    assert result["exit_price"] == 6300
    assert result["gross_points"] == 400
    assert result["net_pnl"] == pytest.approx(400 * 200 - expected_fee, abs=0.01)


def test_down_wave_uses_same_day_futures_high_and_low():
    start = date(2025, 1, 6)
    end = date(2025, 1, 10)
    universe = FuturesUniverse(
        [
            _futures_bar(start, "IM2502", open_price=6200, high=6300, low=6150, close=6250),
            _futures_bar(end, "IM2502", open_price=6000, high=6060, low=5900, close=6020),
        ]
    )

    result = simulate_wave_contract(universe, _wave("down", start, end), universe.active(start)[0], 0)

    assert result["entry_price"] == 6300
    assert result["exit_price"] == 5900
    assert result["gross_points"] == 400


def test_roll_only_happens_after_expiry_and_enters_next_near_month_at_open():
    start = date(2025, 1, 2)
    expiry_day = date(2025, 1, 17)
    next_day = date(2025, 1, 20)
    end = date(2025, 1, 24)
    bars = [
        _futures_bar(start, "IM2501", open_price=6000, high=6050, low=5900, close=6020),
        _futures_bar(expiry_day, "IM2501", open_price=6100, high=6150, low=6080, close=6120, settle=6110),
        _futures_bar(next_day, "IM2502", open_price=6140, high=6200, low=6120, close=6180),
        _futures_bar(end, "IM2502", open_price=6300, high=6400, low=6280, close=6380),
    ]
    universe = FuturesUniverse(bars)

    result = simulate_wave_contract(universe, _wave("up", start, end), universe.active(start)[0], 0)

    assert result["roll_count"] == 1
    assert result["rolls"][0]["expiry_date"] == "2025-01-17"
    assert result["rolls"][0]["next_entry_date"] == "2025-01-20"
    assert result["rolls"][0]["next_entry_price"] == 6140
    assert [item["contract"] for item in result["contract_path"]] == ["IM2501", "IM2502"]


def test_third_friday_and_contract_expiry():
    assert third_friday(2025, 1) == date(2025, 1, 17)
    assert contract_expiry("IM2501") == date(2025, 1, 17)
    assert contract_expiry("IMM0") is None
