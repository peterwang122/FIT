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
    def __init__(self, *, board: str | None, buy_open: float = 12):
        self.board = board
        self.buy_open = buy_open

    def list_stock_scan_universe(self, start_date=None, end_date=None, target_codes=None, history_max_before=None):
        candles = [
            _candle("2026-01-01", 10, 10, pct_chg=5),
            _candle("2026-01-02", self.buy_open, self.buy_open),
            _candle("2026-01-03", 13, 13),
            _candle("2026-01-04", 14, 14),
        ]
        filtered = [
            item
            for item in candles
            if (start_date is None or date.fromisoformat(item["trade_date"]) >= start_date)
            and (end_date is None or date.fromisoformat(item["trade_date"]) <= end_date)
        ]
        return {
            "TEST001": {
                "target_code": "TEST001",
                "target_name": "交易单位测试",
                "board": self.board,
                "candles": filtered,
                "history_max_high": None,
                "history_max_close": None,
            }
        }


def _scan_payload(*, buy_amount: float = 2484) -> dict:
    return {
        "strategy_type": "stock",
        "indicator_params": {"ma": {"periods": [5, 10, 20, 60]}, "boll": {"period": 20, "multiplier": 2}},
        "buy_sequence_groups": [
            {
                "conditions": [
                    {"series_key": "target-up-pct", "operator": "gt", "threshold": 1, "consecutive_days": 1}
                ]
            }
        ],
        "scan_start_date": "2026-01-01",
        "scan_end_date": "2026-01-04",
        "scan_trade_config": {
            "initial_capital": 100000,
            "buy_amount_per_event": buy_amount,
            "buy_offset_trading_days": 1,
            "sell_offset_trading_days": 2,
            "buy_price_basis": "open",
            "sell_price_basis": "close",
        },
    }


def _single_event_for_board(board: str | None, *, buy_amount: float = 2484, buy_open: float = 12) -> dict:
    service = _service()
    service.stock_service = _FakeStockService(board=board, buy_open=buy_open)
    _normalized, events = service._build_market_scan_events(_scan_payload(buy_amount=buy_amount))
    assert len(events) == 1
    return events[0]


def test_main_board_buy_quantity_rounds_to_100_share_multiple():
    event = _single_event_for_board("沪市主板")

    assert event["tradable"] is True
    assert event["planned_quantity"] == 300
    assert event["planned_quantity"] % 100 == 0
    assert event["lot_rule"] == "主板 100股起，100股递增"


def test_star_board_allows_one_share_increment_after_200_share_minimum():
    event = _single_event_for_board("科创板")

    assert event["tradable"] is True
    assert event["planned_quantity"] == 207
    assert event["planned_quantity"] >= 200
    assert event["lot_rule"] == "科创板 200股起，200股以上每次 1 股"


def test_bse_board_allows_one_share_increment_after_100_share_minimum():
    event = _single_event_for_board("北交所", buy_amount=3756)

    assert event["tradable"] is True
    assert event["planned_quantity"] == 313
    assert event["planned_quantity"] >= 100
    assert event["lot_rule"] == "北交所 100股起，100股以上每次 1 股"


def test_unknown_stock_board_is_not_tradable():
    event = _single_event_for_board(None)

    assert event["tradable"] is False
    assert event["planned_quantity"] is None
    assert event["disabled_reason"] == "无法根据 board 判断最小交易单位"


def test_main_board_non_multiple_quantity_is_blocked_even_if_rounding_regresses():
    service = _service()
    service.stock_service = _FakeStockService(board="深市主板")
    service._round_up_lot_quantity = lambda raw_quantity, lot_rule: 207

    _normalized, events = service._build_market_scan_events(_scan_payload())

    assert len(events) == 1
    assert events[0]["tradable"] is False
    assert events[0]["planned_quantity"] == 207
    assert events[0]["planned_buy_amount"] is None
    assert events[0]["disabled_reason"] == "买入数量不符合交易单位：主板 100股起，100股递增"
