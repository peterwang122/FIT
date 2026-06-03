from datetime import date

import pytest

from app.services.quant_service import QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str, close: float | None, *, high: float | None = None, pct_chg: float = 0.0) -> dict:
    return {
        "trade_date": trade_date,
        "open": close,
        "high": high if high is not None else close,
        "low": close,
        "close": close,
        "pct_chg": pct_chg,
    }


def test_ma10_bias_formula_uses_close_relative_to_ma_percent():
    service = _service()
    closes = [98.33333333333333] * 9 + [115.0]
    snapshots = service._build_scan_snapshots(
        [_candle(f"2026-01-{index + 1:02d}", close) for index, close in enumerate(closes)],
        {},
        indicator_params={"ma": {"periods": [5, 10, 20, 60]}},
    )

    assert snapshots[-1]["values"]["target-ma-bias-2"] == pytest.approx(15.0)


def test_ma_bias_lte_includes_equal_threshold_but_lt_does_not():
    service = _service()
    snapshots = [
        {"trade_date": "2026-01-10", "values": {"target-ma-bias-2": 15.0}},
    ]

    assert service._matches_sequence_condition_at(
        snapshots,
        0,
        {"series_key": "target-ma-bias-2", "operator": "lte", "threshold": 15, "consecutive_days": 1},
    )
    assert not service._matches_sequence_condition_at(
        snapshots,
        0,
        {"series_key": "target-ma-bias-2", "operator": "lt", "threshold": 15, "consecutive_days": 1},
    )


def test_ma_bias_is_missing_until_ma_available_or_when_close_invalid():
    service = _service()
    snapshots = service._build_scan_snapshots(
        [
            _candle("2026-01-01", 10.0),
            _candle("2026-01-02", None),
            _candle("2026-01-03", 12.0),
        ],
        {},
        indicator_params={"ma": {"periods": [2, 10, 20, 60]}},
    )

    assert [item["values"]["target-ma-bias-1"] for item in snapshots] == [None, None, None]


def test_ma_bias_is_missing_when_ma_is_not_positive():
    service = _service()
    snapshots = service._build_scan_snapshots(
        [_candle("2026-01-01", 0.0), _candle("2026-01-02", 0.0)],
        {},
        indicator_params={"ma": {"periods": [2, 10, 20, 60]}},
    )

    assert snapshots[-1]["values"]["target-ma-bias-1"] is None


class _FakeStockService:
    def __init__(self, universes: dict[str, dict]):
        self.universes = universes
        self.requests: list[dict] = []

    def list_stock_scan_universe(self, start_date=None, end_date=None, target_codes=None, history_max_before=None):
        self.requests.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "target_codes": target_codes,
                "history_max_before": history_max_before,
            }
        )
        return self._filter_universe(start_date, end_date, target_codes)

    def list_etf_scan_universe(self, start_date=None, end_date=None, target_codes=None, history_max_before=None):
        self.requests.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "target_codes": target_codes,
                "history_max_before": history_max_before,
            }
        )
        return self._filter_universe(start_date, end_date, target_codes)

    def _filter_universe(self, start_date=None, end_date=None, target_codes=None):
        allowed_codes = set(target_codes or self.universes.keys())
        result = {}
        for code, payload in self.universes.items():
            if code not in allowed_codes:
                continue
            candles = [
                item
                for item in payload["candles"]
                if (start_date is None or date.fromisoformat(item["trade_date"]) >= start_date)
                and (end_date is None or date.fromisoformat(item["trade_date"]) <= end_date)
            ]
            if candles:
                result[code] = {**payload, "candles": candles}
        return result


def _scan_payload(*, strategy_type: str = "stock", board_filters: list[str] | None = None) -> dict:
    return {
        "strategy_type": strategy_type,
        "indicator_params": {"ma": {"periods": [5, 10, 20, 60]}, "boll": {"period": 20, "multiplier": 2}},
        "buy_sequence_groups": [
            {
                "conditions": [
                    {"series_key": "target-close-new-high", "operator": "gt", "threshold": 0, "consecutive_days": 1},
                    {"series_key": "market-breadth-up-pct", "operator": "gt", "threshold": 60, "consecutive_days": 1},
                    {"series_key": "target-ma-bias-2", "operator": "lte", "threshold": 15, "consecutive_days": 1},
                ]
            }
        ],
        "scan_start_date": "2026-01-10",
        "scan_end_date": "2026-01-12",
        "scan_trade_config": {
            "initial_capital": 100000,
            "buy_amount_per_event": 10000,
            "buy_offset_trading_days": 1,
            "sell_offset_trading_days": 2,
            "buy_price_basis": "open",
            "sell_price_basis": "close",
            "board_filters": board_filters or [],
        },
    }


def test_market_scan_filters_by_ma10_bias_and_board_scope():
    service = _service()
    service.stock_service = _FakeStockService(
        {
            "000001": {
                "target_code": "000001",
                "target_name": "不过热",
                "board": "主板A股",
                "candles": [
                    *[_candle(f"2026-01-{index + 1:02d}", 98.33333333333333) for index in range(9)],
                    _candle("2026-01-10", 115.0, pct_chg=8),
                    _candle("2026-01-11", 114.0),
                    _candle("2026-01-12", 113.0),
                ],
                "history_max_high": None,
                "history_max_close": None,
            },
            "688001": {
                "target_code": "688001",
                "target_name": "科创过滤",
                "board": "科创板",
                "candles": [
                    *[_candle(f"2026-01-{index + 1:02d}", 98.33333333333333) for index in range(9)],
                    _candle("2026-01-10", 115.0, pct_chg=8),
                    _candle("2026-01-11", 114.0),
                    _candle("2026-01-12", 113.0),
                ],
                "history_max_high": None,
                "history_max_close": None,
            },
            "300001": {
                "target_code": "300001",
                "target_name": "过热",
                "board": "创业板",
                "candles": [
                    *[_candle(f"2026-01-{index + 1:02d}", 90.0) for index in range(9)],
                    _candle("2026-01-10", 120.0, pct_chg=12),
                    _candle("2026-01-11", 119.0),
                    _candle("2026-01-12", 118.0),
                ],
                "history_max_high": None,
                "history_max_close": None,
            },
        }
    )
    service._load_sequence_breadth_values_by_date = lambda start_date=None, end_date=None: {
        "2026-01-10": 70.0,
        "2026-01-11": 70.0,
        "2026-01-12": 70.0,
    }

    _normalized, events = service._build_market_scan_events(_scan_payload(board_filters=["main", "chinext"]))

    assert [event["target_code"] for event in events] == ["000001"]
    assert service.stock_service.requests[0]["start_date"] < date(2026, 1, 10)


def test_etf_market_scan_supports_ma_bias_filter():
    service = _service()
    service.stock_service = _FakeStockService(
        {
            "510300": {
                "target_code": "510300",
                "target_name": "ETF测试",
                "board": "ETF",
                "candles": [
                    *[_candle(f"2026-01-{index + 1:02d}", 98.33333333333333) for index in range(9)],
                    _candle("2026-01-10", 115.0, pct_chg=8),
                    _candle("2026-01-11", 114.0),
                    _candle("2026-01-12", 113.0),
                ],
                "history_max_high": None,
                "history_max_close": None,
            }
        }
    )
    service._load_sequence_breadth_values_by_date = lambda start_date=None, end_date=None: {"2026-01-10": 70.0}

    _normalized, events = service._build_market_scan_events(_scan_payload(strategy_type="etf"))

    assert [event["target_code"] for event in events] == ["510300"]


def test_index_sequence_strategy_rejects_ma_bias_conditions():
    service = _service()

    with pytest.raises(ValueError, match="MA 乖离"):
        service._validate_strategy_payload(
            {
                "strategy_engine": "sequence",
                "sequence_mode": "single_target",
                "strategy_type": "index",
                "target_code": "000300",
                "target_name": "沪深300",
                "buy_sequence_groups": [
                    {
                        "conditions": [
                            {"series_key": "target-ma-bias-2", "operator": "lte", "threshold": 15, "consecutive_days": 1}
                        ]
                    }
                ],
            }
        )
