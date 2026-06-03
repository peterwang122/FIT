from datetime import date

from app.services.quant_service import (
    QuantService,
    _build_sequence_dashboard_breadth_values,
    _build_sequence_dashboard_macro_values,
    _build_sequence_qvix_values,
)


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
    def __init__(self, boards: dict[str, str]):
        self.boards = boards

    def list_stock_scan_universe(self, start_date=None, end_date=None, target_codes=None, history_max_before=None):
        result = {}
        for code, board in self.boards.items():
            result[code] = {
                "target_code": code,
                "target_name": f"测试{code}",
                "board": board,
                "candles": [
                    _candle("2026-01-01", 10, 10),
                    _candle("2026-01-02", 11, 11, pct_chg=10),
                    _candle("2026-01-03", 12, 12),
                    _candle("2026-01-04", 13, 13),
                ],
                "history_max_high": None,
                "history_max_close": None,
            }
        return result


def _scan_payload(*, buy_groups: list[dict] | None = None, board_filters: list[str] | None = None) -> dict:
    return {
        "strategy_type": "stock",
        "indicator_params": {"ma": {"periods": [5, 10, 20, 60]}, "boll": {"period": 20, "multiplier": 2}},
        "buy_sequence_groups": buy_groups
        or [
            {
                "conditions": [
                    {"series_key": "target-close-new-high", "operator": "gt", "threshold": 0, "consecutive_days": 1}
                ]
            }
        ],
        "scan_start_date": "2026-01-01",
        "scan_end_date": "2026-01-04",
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


def test_dashboard_macro_values_average_core_indexes_only():
    rows = [
        {"trade_date": date(2026, 1, 2), "index_name": "上证指数", "emotion_value": 60, "main_basis": -20},
        {"trade_date": date(2026, 1, 2), "index_name": "沪深300", "emotion_value": 80, "main_basis": -40},
        {"trade_date": date(2026, 1, 2), "index_name": "上证50", "emotion_value": 10, "main_basis": 100},
    ]

    values = _build_sequence_dashboard_macro_values(rows)

    assert values["2026-01-02"]["market-emotion"] == 70
    assert values["2026-01-02"]["market-basis-main"] == -30


def test_dashboard_breadth_values_average_core_indexes_only():
    rows = [
        {"trade_date": date(2026, 1, 2), "index_name": "上证指数", "breadth_up_pct": 60},
        {"trade_date": date(2026, 1, 2), "index_name": "沪深300", "breadth_up_pct": 80},
        {"trade_date": date(2026, 1, 2), "index_name": "上证50", "breadth_up_pct": 10},
    ]

    assert _build_sequence_dashboard_breadth_values(rows) == {"2026-01-02": 70}


def test_qvix_values_ignore_zero_and_negative_prices():
    rows = [
        {"trade_date": date(2026, 1, 2), "close_price": 0},
        {"trade_date": date(2026, 1, 2), "close_price": -1},
        {"trade_date": date(2026, 1, 2), "close_price": 20},
        {"trade_date": date(2026, 1, 2), "close_price": 30},
    ]

    assert _build_sequence_qvix_values(rows) == {"2026-01-02": 25}


def test_market_macro_condition_filters_scan_events():
    service = _service()
    service.stock_service = _FakeStockService({"000001": "主板"})
    service._load_sequence_market_macro_values_by_date = lambda groups, start_date=None, end_date=None: {
        "2026-01-02": {"market-emotion": 70}
    }
    buy_groups = [
        {
            "conditions": [
                {"series_key": "target-close-new-high", "operator": "gt", "threshold": 0, "consecutive_days": 1},
                {"series_key": "market-emotion", "operator": "gt", "threshold": 60, "consecutive_days": 1},
            ]
        }
    ]

    _normalized, events = service._build_market_scan_events(_scan_payload(buy_groups=buy_groups))

    assert [event["signal_date"] for event in events] == ["2026-01-02"]


def test_market_macro_condition_misses_when_value_unavailable():
    service = _service()
    service.stock_service = _FakeStockService({"000001": "主板"})
    service._load_sequence_market_macro_values_by_date = lambda groups, start_date=None, end_date=None: {}
    buy_groups = [
        {
            "conditions": [
                {"series_key": "target-close-new-high", "operator": "gt", "threshold": 0, "consecutive_days": 1},
                {"series_key": "market-qvix", "operator": "lt", "threshold": 28, "consecutive_days": 1},
            ]
        }
    ]

    _normalized, events = service._build_market_scan_events(_scan_payload(buy_groups=buy_groups))

    assert events == []


def test_stock_board_filter_reduces_scan_universe():
    service = _service()
    service.stock_service = _FakeStockService({"000001": "主板", "920001": "北交所"})

    _normalized, events = service._build_market_scan_events(_scan_payload(board_filters=["main"]))

    assert sorted({event["target_code"] for event in events}) == ["000001"]


def test_missing_stock_board_filter_keeps_legacy_all_board_behavior():
    service = _service()
    service.stock_service = _FakeStockService({"000001": "主板", "920001": "北交所"})

    _normalized, events = service._build_market_scan_events(_scan_payload())

    assert sorted({event["target_code"] for event in events}) == ["000001", "920001"]
