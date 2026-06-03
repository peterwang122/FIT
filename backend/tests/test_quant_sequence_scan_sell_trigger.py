from datetime import date

from app.services.quant_service import QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str, open_price: float, close: float, *, pct_chg: float = 0.0) -> dict:
    return {
        "trade_date": trade_date,
        "open": open_price,
        "high": max(open_price, close),
        "low": min(open_price, close),
        "close": close,
        "pct_chg": pct_chg,
    }


class _FakeStockService:
    def __init__(self, candles: list[dict]):
        self.candles = candles

    def list_stock_scan_universe(self, start_date=None, end_date=None, target_codes=None, history_max_before=None):
        filtered = [
            item
            for item in self.candles
            if (start_date is None or date.fromisoformat(item["trade_date"]) >= start_date)
            and (end_date is None or date.fromisoformat(item["trade_date"]) <= end_date)
        ]
        return {
            "000001": {
                "target_code": "000001",
                "target_name": "测试股票",
                "board": "主板",
                "candles": filtered,
                "history_max_high": None,
                "history_max_close": None,
            }
        }


def _scan_payload(*, sell_basis: str = "open", buy_basis: str = "open", operator: str = "gt", target: str = "ma-1"):
    return {
        "strategy_type": "stock",
        "indicator_params": {"ma": {"periods": [2, 3, 4, 5]}, "boll": {"period": 2, "multiplier": 0.5}},
        "buy_sequence_groups": [{"conditions": [{"series_key": "target-up-pct", "operator": "gt", "threshold": 1, "consecutive_days": 1}]}],
        "scan_start_date": "2026-01-01",
        "scan_end_date": "2026-01-05",
        "scan_trade_config": {
            "initial_capital": 100000,
            "buy_amount_per_event": 10000,
            "buy_offset_trading_days": 1,
            "sell_offset_trading_days": 1,
            "buy_price_basis": buy_basis,
            "sell_price_basis": sell_basis,
            "sell_trigger": {"enabled": True, "operator": operator, "target": target},
        },
    }


def _fixed_scan_payload(*, sell_basis: str = "close", buy_basis: str = "open"):
    payload = _scan_payload(buy_basis=buy_basis, sell_basis=sell_basis)
    payload["scan_trade_config"].pop("sell_trigger", None)
    payload["scan_trade_config"]["sell_offset_trading_days"] = 3
    return payload


def test_market_scan_sell_trigger_exits_next_day_open_after_close_crosses_ma():
    service = _service()
    service.stock_service = _FakeStockService(
        [
            _candle("2026-01-01", 10, 10),
            _candle("2026-01-02", 11, 11, pct_chg=10),
            _candle("2026-01-03", 12, 12),
            _candle("2026-01-04", 13, 13),
            _candle("2026-01-05", 14, 14),
        ]
    )

    _normalized, events = service._build_market_scan_events(_scan_payload())

    assert len(events) == 1
    assert events[0]["tradable"] is True
    assert events[0]["buy_date"] == "2026-01-03"
    assert events[0]["sell_trigger_date"] == "2026-01-03"
    assert events[0]["sell_date"] == "2026-01-04"
    assert events[0]["sell_price"] == 13
    assert events[0]["sell_reason"] == "trigger"


def test_market_scan_hides_repeated_hits_while_target_position_is_open_and_allows_after_sell():
    service = _service()
    service.stock_service = _FakeStockService(
        [
            _candle("2026-01-01", 10, 10),
            _candle("2026-01-02", 11, 11, pct_chg=10),
            _candle("2026-01-03", 12, 12, pct_chg=10),
            _candle("2026-01-04", 13, 13),
            _candle("2026-01-05", 14, 14, pct_chg=10),
            _candle("2026-01-06", 15, 15),
            _candle("2026-01-07", 16, 16),
            _candle("2026-01-08", 17, 17),
        ]
    )

    payload = _fixed_scan_payload()
    payload["scan_end_date"] = "2026-01-08"
    _normalized, events = service._build_market_scan_events(payload)

    assert [event["signal_date"] for event in events] == ["2026-01-02", "2026-01-05"]
    assert events[0]["buy_date"] == "2026-01-03"
    assert events[0]["sell_date"] == "2026-01-05"
    assert events[1]["buy_date"] == "2026-01-06"


def test_market_scan_allows_sell_execution_day_close_signal_but_skips_sell_trigger_day_signal():
    service = _service()
    service.stock_service = _FakeStockService(
        [
            _candle("2026-01-01", 10, 10),
            _candle("2026-01-02", 11, 11, pct_chg=10),
            _candle("2026-01-03", 12, 12),
            _candle("2026-01-04", 13, 13, pct_chg=10),
            _candle("2026-01-05", 14, 14, pct_chg=10),
            _candle("2026-01-06", 15, 15),
            _candle("2026-01-07", 16, 16),
            _candle("2026-01-08", 17, 17),
        ]
    )
    payload = _scan_payload(buy_basis="close", sell_basis="open", operator="gt", target="ma-1")
    payload["scan_end_date"] = "2026-01-07"

    _normalized, events = service._build_market_scan_events(payload)

    assert [event["signal_date"] for event in events] == ["2026-01-02", "2026-01-05"]
    assert events[0]["sell_trigger_date"] == "2026-01-04"
    assert events[0]["sell_date"] == "2026-01-05"
    assert events[1]["buy_date"] == "2026-01-06"


def test_market_scan_sell_trigger_exits_next_day_close_after_close_crosses_boll_lower():
    service = _service()
    service.stock_service = _FakeStockService(
            [
                _candle("2026-01-01", 10, 10),
                _candle("2026-01-02", 11, 11, pct_chg=10),
                _candle("2026-01-03", 11, 11),
                _candle("2026-01-04", 8, 8),
                _candle("2026-01-05", 7, 7),
            ]
    )

    _normalized, events = service._build_market_scan_events(
        _scan_payload(sell_basis="close", operator="lt", target="boll-lower")
    )

    assert len(events) == 1
    assert events[0]["tradable"] is True
    assert events[0]["sell_trigger_date"] == "2026-01-04"
    assert events[0]["sell_date"] == "2026-01-05"
    assert events[0]["sell_price"] == 7
    assert events[0]["sell_reason"] == "trigger"


def test_market_scan_close_buy_does_not_allow_same_day_sell_trigger():
    service = _service()
    service.stock_service = _FakeStockService(
        [
            _candle("2026-01-01", 10, 10),
            _candle("2026-01-02", 11, 11, pct_chg=10),
            _candle("2026-01-03", 12, 12),
            _candle("2026-01-04", 11, 11),
            _candle("2026-01-05", 10, 10),
        ]
    )

    _normalized, events = service._build_market_scan_events(_scan_payload(buy_basis="close"))

    assert len(events) == 1
    assert events[0]["tradable"] is True
    assert events[0]["sell_trigger_date"] is None
    assert events[0]["sell_date"] == "2026-01-05"
    assert events[0]["sell_price"] == 10
    assert events[0]["sell_reason"] == "fallback_end"


def test_market_scan_sell_trigger_falls_back_to_scan_end_close_when_not_hit():
    service = _service()
    service.stock_service = _FakeStockService(
        [
            _candle("2026-01-01", 10, 10),
            _candle("2026-01-02", 11, 11, pct_chg=10),
            _candle("2026-01-03", 12, 12),
            _candle("2026-01-04", 13, 13),
            _candle("2026-01-05", 14, 14),
        ]
    )

    _normalized, events = service._build_market_scan_events(_scan_payload(operator="lt", target="ma-1"))

    assert len(events) == 1
    assert events[0]["tradable"] is True
    assert events[0]["sell_trigger_date"] is None
    assert events[0]["sell_date"] == "2026-01-05"
    assert events[0]["sell_price"] == 14
    assert events[0]["sell_reason"] == "fallback_end"


def test_market_scan_sell_trigger_requires_next_day_execution_price():
    service = _service()
    service.stock_service = _FakeStockService(
        [
            _candle("2026-01-01", 10, 10),
            _candle("2026-01-02", 11, 11, pct_chg=10),
            _candle("2026-01-03", 12, 12),
        ]
    )
    payload = _scan_payload()
    payload["scan_end_date"] = "2026-01-03"

    _normalized, events = service._build_market_scan_events(payload)

    assert len(events) == 1
    assert events[0]["tradable"] is False
    assert events[0]["sell_trigger_date"] == "2026-01-03"
    assert events[0]["sell_date"] is None
    assert events[0]["disabled_reason"] == "缺少次日卖出执行价"


def test_market_scan_target_hits_return_buy_and_sell_trigger_dates():
    service = _service()
    service._load_scan_result = lambda scan_result_id, owner_user_id: {
        "scan_result_id": scan_result_id,
        "matched_events": [
            {
                "target_code": "000001",
                "target_name": "测试股票",
                "signal_date": "2026-01-02",
                "sell_trigger_date": "2026-01-03",
            },
            {
                "target_code": "000001",
                "target_name": "测试股票",
                "signal_date": "2026-01-04",
                "sell_trigger_date": "2026-01-05",
            },
        ],
    }

    result = service.get_market_scan_target_hits("scan-1", "000001", 1)

    assert result["hit_dates"] == ["2026-01-02", "2026-01-04"]
    assert result["sell_trigger_dates"] == ["2026-01-03", "2026-01-05"]


def test_market_scan_backtest_skips_overlapping_same_target_events_from_stale_cache():
    service = _service()
    matched_events = [
        {
            "event_id": "stock:000001:2026-01-02",
            "target_type": "stock",
            "target_code": "000001",
            "target_name": "测试股票",
            "signal_date": "2026-01-02",
            "buy_date": "2026-01-03",
            "sell_date": "2026-01-05",
            "sell_reason": "offset",
            "hit_buy_groups": [1],
            "tradable": True,
            "buy_price": 12,
            "sell_price": 14,
            "planned_quantity": 900,
            "planned_buy_amount": 10800,
        },
        {
            "event_id": "stock:000001:2026-01-03",
            "target_type": "stock",
            "target_code": "000001",
            "target_name": "测试股票",
            "signal_date": "2026-01-03",
            "buy_date": "2026-01-04",
            "sell_date": "2026-01-06",
            "sell_reason": "offset",
            "hit_buy_groups": [1],
            "tradable": True,
            "buy_price": 13,
            "sell_price": 15,
            "planned_quantity": 800,
            "planned_buy_amount": 10400,
        },
    ]

    result = service._simulate_market_scan_backtest(
        normalized_payload={
            "strategy_type": "stock",
            "scan_trade_config": {
                "initial_capital": 100000,
                "buy_amount_per_event": 10000,
                "buy_offset_trading_days": 1,
                "sell_offset_trading_days": 3,
                "buy_price_basis": "open",
                "sell_price_basis": "close",
                "sell_trigger": None,
            },
        },
        matched_events=matched_events,
        use_all_events=True,
        excluded_event_ids=[],
        selected_event_ids=None,
        candles_by_target={
            "000001": [
                _candle("2026-01-03", 12, 12),
                _candle("2026-01-04", 13, 13),
                _candle("2026-01-05", 14, 14),
                _candle("2026-01-06", 15, 15),
            ]
        },
    )

    events = result["matched_events"]
    assert events[0]["executed"] is True
    assert events[1]["executed"] is False
    assert events[1]["skip_reason"] == "duplicate_open_position"
