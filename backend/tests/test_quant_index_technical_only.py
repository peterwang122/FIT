from datetime import date

from app.services import quant_service as quant_service_module
from app.services.quant_service import (
    BASIS_FILTER_KEYS,
    CN_INDEX_STRATEGY_FILTER_KEYS,
    STOCK_STRATEGY_FILTER_KEYS,
    VIX_FILTER_KEYS,
    QuantService,
)


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def test_star_50_uses_only_technical_index_indicators():
    service = _service()

    assert not service._index_supports_auxiliary_panels(
        "cn",
        "sh000688",
        "科创50",
    )
    assert not service._index_supports_basis("sh000688", "科创50", "cn")
    assert service._resolve_index_vix_code("sh000688", "科创50", "cn") == "KCB_QVIX"
    allowed_keys = service._allowed_snapshot_filter_keys(
        "index",
        "cn",
        "sh000688",
        "科创50",
    )
    assert allowed_keys[: len(STOCK_STRATEGY_FILTER_KEYS)] == STOCK_STRATEGY_FILTER_KEYS
    assert "cn-option-pc-sse-588000-current" in allowed_keys
    assert "cn-option-flow-pc-turnover-sse-588080" in allowed_keys
    assert set(VIX_FILTER_KEYS).issubset(allowed_keys)
    assert "emotion" not in allowed_keys
    assert "basis-main" not in allowed_keys


def test_star_50_dashboard_includes_collected_qvix(monkeypatch):
    class FakeStockService:
        def list_index_daily_kline(self, **_kwargs):
            return [
                {
                    "trade_date": date(2026, 7, 3),
                    "open": 1000,
                    "high": 1010,
                    "low": 990,
                    "close": 1005,
                }
            ]

        def list_index_qvix_daily_data(self, qvix_code, **_kwargs):
            assert qvix_code == "KCB_QVIX"
            return [
                {
                    "trade_date": date(2026, 7, 3),
                    "open_price": 31,
                    "high_price": 33,
                    "low_price": 30,
                    "close_price": 32,
                }
            ]

    service = _service()
    service.stock_service = FakeStockService()
    service._resolve_index_option = lambda *_args: {"code": "sh000688", "name": "科创50"}
    service._load_precomputed_index_indicator_rows = lambda *_args: []
    monkeypatch.setattr(quant_service_module.redis_client, "get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(quant_service_module.redis_client, "set", lambda *_args, **_kwargs: True)

    payload = service.get_index_dashboard(
        "sh000688",
        start_date=date(2026, 7, 3),
        market="cn",
    )

    assert payload["vix_points"] == [
        {
            "trade_date": date(2026, 7, 3),
            "open_price": 31.0,
            "high_price": 33.0,
            "low_price": 30.0,
            "close_price": 32.0,
        }
    ]


def test_existing_cn_indexes_keep_auxiliary_indicators():
    service = _service()

    assert service._index_supports_auxiliary_panels(
        "cn",
        "sh000300",
        "沪深300",
    )
    assert service._index_supports_basis("sh000300", "沪深300", "cn")
    allowed = service._allowed_snapshot_filter_keys(
        "index",
        "cn",
        "sh000300",
        "沪深300",
    )
    assert set(BASIS_FILTER_KEYS).issubset(allowed)
    assert set(allowed).issubset(CN_INDEX_STRATEGY_FILTER_KEYS)


def test_star_50_backtest_uses_most_liquid_etf():
    class FakeStockService:
        requested_etf_code = None

        def list_etf_daily_kline(self, etf_code):
            self.requested_etf_code = etf_code
            return [
                {
                    "trade_date": "2026-07-03",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                }
            ]

    service = _service()
    service.stock_service = FakeStockService()
    signal_candles = [
        {
            "trade_date": "2026-07-03",
            "open": 1000,
            "high": 1000,
            "low": 1000,
            "close": 1000,
        }
    ]

    returned_signal_candles, price_rows = service._load_index_backtest_price_rows(
        "sh000688",
        "科创50",
        "cn",
        signal_candles,
    )

    assert service.stock_service.requested_etf_code == "588000"
    assert returned_signal_candles == signal_candles
    assert price_rows[0]["close"] == 1


def test_star_50_strategy_snapshots_include_collected_vix():
    service = _service()
    service._build_index_snapshots = lambda *args: [{"trade_date": "2026-07-03", "values": {"vix-high": 45}}]

    snapshots = service._build_index_snapshots_for_market(
        "cn",
        "sh000688",
        "科创50",
        {},
        [{"trade_date": "2026-07-03", "open": 1, "high": 1, "low": 1, "close": 1}],
    )

    assert snapshots[0]["values"]["vix-high"] == 45
