from datetime import date, timedelta
from math import sqrt

import pytest

from app.services.macro_service import MacroService


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = str(statement)
        self.params = params
        return _FakeResult(self.rows)


def test_append_style_indicators_builds_twenty_day_buffer_and_bollinger_bands():
    points = [
        {
            "chinext_csi_dividend_ratio": float(index + 1),
            "star50_csi_dividend_ratio": float((index + 1) * 2),
        }
        for index in range(21)
    ]

    MacroService._append_style_indicators(points)

    assert points[18]["chinext_csi_dividend_ratio_ma20"] is None
    assert points[19]["chinext_csi_dividend_ratio_ma20"] == pytest.approx(10.5)
    assert points[19]["chinext_csi_dividend_ratio_upper_1pct"] == pytest.approx(10.605)
    assert points[19]["chinext_csi_dividend_ratio_lower_1pct"] == pytest.approx(10.395)
    assert points[19]["chinext_csi_dividend_ratio_boll_upper"] == pytest.approx(10.5 + 2 * sqrt(33.25))
    assert points[19]["chinext_csi_dividend_ratio_boll_lower"] == pytest.approx(10.5 - 2 * sqrt(33.25))
    assert points[20]["chinext_csi_dividend_ratio_ma20"] == pytest.approx(11.5)
    assert points[20]["star50_csi_dividend_ratio_ma20"] == pytest.approx(23.0)


def test_append_macro_bollinger_bands_builds_each_indicator_band():
    points = [
        {
            field: float(index + 1)
            for field in MacroService.MACRO_BOLL_FIELDS
        }
        for index in range(20)
    ]

    MacroService._append_macro_bollinger_bands(points)

    expected_upper = 10.5 + 2 * sqrt(33.25)
    expected_lower = 10.5 - 2 * sqrt(33.25)
    for field in MacroService.MACRO_BOLL_FIELDS:
        assert points[18][f"{field}_boll_mid"] is None
        assert points[19][f"{field}_boll_mid"] == pytest.approx(10.5)
        assert points[19][f"{field}_boll_upper"] == pytest.approx(expected_upper)
        assert points[19][f"{field}_boll_lower"] == pytest.approx(expected_lower)


def test_get_dashboard_joins_three_indices_and_exposes_style_methodology():
    start_date = date(2026, 7, 1)
    rows = [
        {
            "trade_date": start_date + timedelta(days=index),
            "chinext_csi_dividend_ratio": 0.4 + index * 0.001,
            "star50_csi_dividend_ratio": 0.2 + index * 0.001,
        }
        for index in range(20)
    ]
    db = _FakeDb(rows)

    dashboard = MacroService(db).get_dashboard(
        start_date=start_date,
        end_date=start_date + timedelta(days=19),
    )

    assert "LEFT JOIN index_daily_data AS chinext" in db.statement
    assert "LEFT JOIN index_daily_data AS star50" in db.statement
    assert "LEFT JOIN index_daily_data AS csi_dividend" in db.statement
    assert db.params["chinext_index_code"] == "sz399006"
    assert db.params["star50_index_code"] == "sh000688"
    assert db.params["csi_dividend_index_code"] == "sh000922"
    assert dashboard["latest"]["chinext_csi_dividend_ratio_ma20"] == pytest.approx(0.4095)
    assert dashboard["latest"]["chinext_csi_dividend_ratio_boll_upper"] is not None
    assert "hs300_equity_bond_spread_pp_boll_upper" in dashboard["latest"]
    assert "BOLL(20,2)" in dashboard["methodology"]["growth_dividend_ratio"]
