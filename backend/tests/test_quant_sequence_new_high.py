from datetime import date

from app.services.quant_service import QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str, high, close: float, *, pct_chg: float = 0.0) -> dict:
    return {
        "trade_date": trade_date,
        "open": close,
        "high": high,
        "low": close,
        "close": close,
        "pct_chg": pct_chg,
    }


def test_scan_snapshots_mark_strict_high_and_close_new_high():
    service = _service()

    snapshots = service._build_scan_snapshots(
        [
            _candle("2026-01-01", 10.0, 8.0),
            _candle("2026-01-02", 10.0, 9.0),
            _candle("2026-01-03", 11.0, 9.0),
            _candle("2026-01-04", None, None),
            _candle("2026-01-05", 11.0, 10.0),
        ],
        {},
    )

    assert [item["values"]["target-high-new-high"] for item in snapshots] == [0.0, 0.0, 1.0, 0.0, 0.0]
    assert [item["values"]["target-close-new-high"] for item in snapshots] == [0.0, 1.0, 0.0, 0.0, 1.0]


def test_new_high_sequence_conditions_are_normalized_as_boolean_one_day():
    service = _service()

    groups = service._normalize_sequence_groups(
        [
            {
                "conditions": [
                    {
                        "series_key": "target-high-new-high",
                        "operator": "lt",
                        "threshold": 99,
                        "consecutive_days": 5,
                    },
                    {"series_key": "target-close-new-high"},
                ]
            }
        ]
    )

    assert groups == [
        {
            "conditions": [
                {
                    "series_key": "target-high-new-high",
                    "operator": "gt",
                    "threshold": 0.0,
                    "consecutive_days": 1,
                },
                {
                    "series_key": "target-close-new-high",
                    "operator": "gt",
                    "threshold": 0.0,
                    "consecutive_days": 1,
                },
            ]
        }
    ]


def test_new_high_condition_group_hits_only_matching_dates():
    service = _service()
    snapshots = service._build_scan_snapshots(
        [
            _candle("2026-01-01", 10.0, 10.0),
            _candle("2026-01-02", 10.0, 11.0),
            _candle("2026-01-03", 12.0, 11.0),
        ],
        {},
    )

    groups = service._normalize_sequence_groups(
        [{"conditions": [{"series_key": "target-high-new-high"}]}]
    )
    hits = service._build_scan_group_hits(snapshots, groups)

    assert hits == [[], [], [1]]


class _FakeStockService:
    def __init__(self, candles: list[dict]):
        self.candles = candles
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
                "history_max_high": 100.0 if history_max_before is not None else None,
                "history_max_close": 10.0 if history_max_before is not None else None,
            }
        }


def test_market_scan_new_high_uses_prior_history_max_and_limits_events_to_scan_window():
    service = _service()
    fake_stock_service = _FakeStockService(
        [
            _candle("2026-02-01", 90.0, 10.0),
            _candle("2026-02-02", 95.0, 10.0),
            _candle("2026-02-03", 101.0, 10.0),
            _candle("2026-02-04", 101.0, 10.0),
            _candle("2026-02-05", 99.0, 10.0),
        ]
    )
    service.stock_service = fake_stock_service

    normalized_payload, events = service._build_market_scan_events(
        {
            "strategy_type": "stock",
            "buy_sequence_groups": [
                {"conditions": [{"series_key": "target-high-new-high", "threshold": 100, "consecutive_days": 9}]}
            ],
            "scan_start_date": "2026-02-01",
            "scan_end_date": "2026-02-04",
            "scan_trade_config": {
                "initial_capital": 100000,
                "buy_amount_per_event": 10000,
                "buy_offset_trading_days": 1,
                "sell_offset_trading_days": 2,
                "buy_price_basis": "close",
                "sell_price_basis": "close",
            },
        }
    )

    assert fake_stock_service.requests[0]["start_date"] == date(2025, 12, 3)
    assert fake_stock_service.requests[0]["history_max_before"] == date(2025, 12, 3)
    assert normalized_payload["buy_sequence_groups"][0]["conditions"] == [
        {
            "series_key": "target-high-new-high",
            "operator": "gt",
            "threshold": 0.0,
            "consecutive_days": 1,
        }
    ]
    assert [event["signal_date"] for event in events] == ["2026-02-03"]
