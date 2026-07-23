from datetime import date
from types import SimpleNamespace

import pytest

from app.services.quant_service import QuantService


def _candle(trade_date: str, close: float) -> dict:
    return {
        "trade_date": trade_date,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "pre_close": close,
        "change": 0,
        "pct_chg": 0,
        "vol": 100,
        "amount": 1000,
        "turnover_rate": 0,
        "pe_ttm": 0,
        "pb": 0,
        "total_market_value": 0,
        "circulating_market_value": 0,
    }


def _snapshot_strategy(**overrides):
    payload = {
        "id": 1,
        "strategy_engine": "snapshot",
        "sequence_mode": "single_target",
        "strategy_type": "stock",
        "target_market": "cn",
        "target_code": "600000",
        "target_name": "测试股票",
        "indicator_params": {},
        "blue_filter_groups": [
            {"conditions": [{"type": "numeric", "field": "rsi", "operator": "lte", "value": 50}]}
        ],
        "red_filter_groups": [
            {"conditions": [{"type": "numeric", "field": "rsi", "operator": "gte", "value": 50}]}
        ],
        "blue_filters": {},
        "red_filters": {},
        "blue_boll_filter": {},
        "red_boll_filter": {},
        "buy_sequence_groups": [],
        "sell_sequence_groups": [],
        "scan_trade_config": {},
        "research_option_template": None,
        "start_date": None,
        "scan_start_date": None,
        "scan_end_date": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class _StockService:
    def __init__(self, candles: list[dict]):
        self.candles = candles
        self.index_calls: list[tuple[str, str]] = []
        self.etf_calls: list[str] = []

    def list_hfq_daily_kline(self, target_code):
        return self.candles

    def list_daily_kline(self, target_code):
        return self.candles

    def list_etf_daily_kline(self, target_code):
        self.etf_calls.append(target_code)
        return self.candles

    def list_index_daily_kline(self, target_code, market="cn"):
        self.index_calls.append((target_code, market))
        return self.candles


def _service(strategy, candles=None) -> QuantService:
    service = QuantService.__new__(QuantService)
    service.stock_service = _StockService(candles or [_candle("2026-01-01", 10)])
    service._get_owned_strategy = lambda strategy_id, owner_user_id: strategy
    return service


def test_snapshot_option_template_chart_returns_blue_red_and_overlap_groups():
    strategy = _snapshot_strategy(research_option_template={"enabled": True})
    service = _service(
        strategy,
        [
            _candle("2026-01-01", 10),
            _candle("2026-01-02", 11),
            _candle("2026-01-03", 12),
        ],
    )
    service._build_stock_snapshots = lambda params, candles: [
        {"trade_date": "2026-01-01", "values": {"rsi": 40}, "close": 10, "high": 10, "low": 10},
        {"trade_date": "2026-01-02", "values": {"rsi": 60}, "close": 11, "high": 11, "low": 11},
        {"trade_date": "2026-01-03", "values": {"rsi": 50}, "close": 12, "high": 12, "low": 12},
    ]

    result = service.get_strategy_target_chart(1, 7)

    assert [item["color"] for item in result["highlight_bands"]] == ["blue", "red", "purple"]
    assert result["highlight_bands"][2]["blueHitGroups"] == [1]
    assert result["highlight_bands"][2]["redHitGroups"] == [1]
    assert result["candles"][0]["trade_date"] == "2026-01-01"


def test_index_target_chart_uses_index_candles_instead_of_backtest_etf():
    strategy = _snapshot_strategy(
        strategy_type="index",
        target_code="sh000852",
        target_name="中证1000",
        blue_filter_groups=[],
        red_filter_groups=[],
    )
    service = _service(strategy, [_candle("2026-01-01", 6000)])
    service._build_index_snapshots_for_market = lambda *args: []

    result = service.get_strategy_target_chart(1, 7)

    assert result["target_code"] == "sh000852"
    assert service.stock_service.index_calls == [("sh000852", "cn")]
    assert service.stock_service.etf_calls == []


def test_single_target_sequence_chart_marks_buy_and_sell_groups():
    strategy = _snapshot_strategy(
        strategy_engine="sequence",
        buy_sequence_groups=[
            {
                "conditions": [
                    {
                        "series_key": "target-up-pct",
                        "operator": "gt",
                        "threshold": 1,
                        "consecutive_days": 1,
                    }
                ]
            }
        ],
        sell_sequence_groups=[
            {
                "conditions": [
                    {
                        "series_key": "target-down-pct",
                        "operator": "gt",
                        "threshold": 1,
                        "consecutive_days": 1,
                    }
                ]
            }
        ],
    )
    service = _service(strategy, [_candle("2026-01-01", 10), _candle("2026-01-02", 9)])
    service._build_sequence_snapshots = lambda current_strategy: [
        {
            "trade_date": "2026-01-01",
            "values": {"target-up-pct": 2, "target-down-pct": None},
        },
        {
            "trade_date": "2026-01-02",
            "values": {"target-up-pct": None, "target-down-pct": 2},
        },
    ]

    result = service.get_strategy_target_chart(1, 7)

    assert [(item["tradeDate"], item["color"]) for item in result["highlight_bands"]] == [
        ("2026-01-01", "blue"),
        ("2026-01-02", "red"),
    ]


def test_market_scan_target_chart_merges_buy_and_sell_hits_and_validates_owner():
    strategy = _snapshot_strategy(
        strategy_engine="sequence",
        sequence_mode="market_scan",
        strategy_type="stock",
        buy_sequence_groups=[
            {
                "conditions": [
                    {
                        "series_key": "target-up-pct",
                        "operator": "gt",
                        "threshold": 1,
                        "consecutive_days": 1,
                    }
                ]
            }
        ],
        scan_trade_config={
            "initial_capital": 100000,
            "buy_amount_per_event": 10000,
            "buy_offset_trading_days": 1,
            "sell_offset_trading_days": 2,
            "buy_price_basis": "open",
            "sell_price_basis": "open",
            "sell_trigger": {"enabled": True, "operator": "lt", "target": "ma-1"},
            "board_filters": [],
        },
        scan_start_date=date(2026, 1, 1),
        scan_end_date=date(2026, 1, 31),
    )
    service = _service(strategy, [_candle("2026-01-01", 10), _candle("2026-01-02", 9)])
    expected_payload = service._serialize_scan_payload_for_cache(
        service._normalize_scan_payload(service._build_market_scan_payload_from_strategy(strategy))
    )

    def _load_scan_result(scan_result_id, owner_user_id):
        assert owner_user_id == 7
        return {
            "scan_result_id": scan_result_id,
            "normalized_payload": expected_payload,
            "matched_events": [
                {
                    "target_code": "600000",
                    "target_name": "测试股票",
                    "signal_date": "2026-01-01",
                    "sell_trigger_date": "2026-01-02",
                    "hit_buy_groups": [2],
                },
                {
                    "target_code": "600000",
                    "target_name": "测试股票",
                    "signal_date": "2026-01-02",
                    "sell_trigger_date": None,
                    "hit_buy_groups": [1],
                },
            ],
        }

    service._load_scan_result = _load_scan_result

    result = service.get_strategy_target_chart(
        1,
        7,
        scan_result_id="scan-1",
        target_code="600000",
    )

    assert result["highlight_bands"] == [
        {
            "tradeDate": "2026-01-01",
            "color": "blue",
            "variant": "solid",
            "blueHitGroups": [2],
            "redHitGroups": [],
        },
        {
            "tradeDate": "2026-01-02",
            "color": "purple",
            "variant": "solid",
            "blueHitGroups": [1],
            "redHitGroups": [1],
        },
    ]


def test_market_scan_target_chart_rejects_unrelated_scan_configuration():
    strategy = _snapshot_strategy(
        strategy_engine="sequence",
        sequence_mode="market_scan",
        scan_start_date=date(2026, 1, 1),
        scan_end_date=date(2026, 1, 31),
        buy_sequence_groups=[
            {
                "conditions": [
                    {
                        "series_key": "target-up-pct",
                        "operator": "gt",
                        "threshold": 1,
                        "consecutive_days": 1,
                    }
                ]
            }
        ],
    )
    service = _service(strategy)
    service._load_scan_result = lambda scan_result_id, owner_user_id: {
        "normalized_payload": {"strategy_type": "stock"},
        "matched_events": [],
    }

    with pytest.raises(ValueError, match="scan result does not match strategy"):
        service.get_strategy_target_chart(
            1,
            7,
            scan_result_id="other-scan",
            target_code="600000",
        )
