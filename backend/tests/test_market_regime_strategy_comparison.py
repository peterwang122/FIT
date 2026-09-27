import runpy
import sys
from pathlib import Path

import pytest


@pytest.fixture
def compare(monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    folder = Path(__file__).resolve().parents[2] / "scripts/research"
    sys.path.insert(0, str(folder))
    return runpy.run_path(str(folder / "compare_market_regime_strategy.py"))["compare"]


def prices():
    return [{"date": f"2026-01-{i:02d}", "open": price, "high": price,
             "low": price, "close": price} for i, price in enumerate((100, 100, 150, 200, 210), 1)]


def test_same_signal_next_open_and_only_buy_is_gated(compare):
    candles = prices()
    gate = [{"date": r["date"], "buy_multiplier": 0, "state": "paused"} for r in candles]
    result = compare(candles, {"2026-01-01": "red", "2026-01-03": "blue"},
                     [("gate", "gate", gate)], .5, .5)
    assert result[0]["trades"][0]["date"] == "2026-01-02"
    assert result[0]["trades"][1]["date"] == "2026-01-04"
    assert result[1]["return_pct"] == 0
    assert result[1]["missed_return_pp"] == result[0]["return_pct"]
    assert result[1]["blocked_baseline_buys"] == 1
    assert result[1]["restricted_entries"][0]["return_20d_pct"] is None


def test_full_cash_constraint_and_pending_last_day_not_counted(compare):
    candles = prices()
    signals = {r["date"]: "red" for r in candles}
    gate = [{"date": r["date"], "buy_multiplier": 0, "state": "paused"} for r in candles]
    result = compare(candles, signals, [("gate", "gate", gate)], 1, .5)
    assert result[0]["buy_trades"] == 1
    assert result[1]["blocked_baseline_buys"] == 1
    assert result[1]["restricted_count"] == 4


def test_half_permission_not_entire_position_half(compare):
    candles = prices()
    gate = [{"date": r["date"], "buy_multiplier": .5, "state": "repair"} for r in candles]
    result = compare(candles, {"2026-01-01": "red"}, [("gate", "gate", gate)], .5, .5)
    assert result[1]["trades"][0]["quantity"] == pytest.approx(.25 / 100)
    assert result[1]["blocked_baseline_buys"] == 0
    assert result[1]["reduced_baseline_buys"] == 1
