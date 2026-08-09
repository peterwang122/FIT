from datetime import date

from app.services.quant_service import CN_INDEX_STRATEGY_FILTER_KEYS, QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str) -> dict:
    return {
        "trade_date": trade_date,
        "open": 3000.0,
        "high": 3010.0,
        "low": 2990.0,
        "close": 3005.0,
    }


def test_cn_market_fear_greed_filter_is_available_with_cn_auxiliary_indicators():
    service = _service()

    allowed = service._allowed_snapshot_filter_keys("index", "cn", "sh000001", "上证指数")

    assert "cn-market-fear-greed" in CN_INDEX_STRATEGY_FILTER_KEYS
    assert "cn-market-fear-greed" in allowed
    assert "cn-baifenwei-fear-greed" in allowed
    assert "cn-baifenwei-volatility" in allowed
    assert "cn-baifenwei-limit-up-down-ratio" in allowed


def test_index_snapshot_injects_cn_market_fear_greed_value():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda _symbol_name: [
        {
            "trade_date": date(2026, 7, 27),
            "emotion_value": 50,
            "main_basis": 0,
            "month_basis": 0,
            "up_ratio_pct": 50,
        }
    ]
    service._load_cn_market_fear_greed_rows = lambda **_kwargs: [
        {
            "trade_date": date(2026, 7, 27),
            "fear_greed_value": 32.41,
            "sentiment_label": "中性",
        }
    ]

    snapshots = service._build_index_snapshots(
        "sh000001",
        "上证指数",
        {},
        [_candle("2026-07-27")],
    )

    assert snapshots[0]["values"]["cn-market-fear-greed"] == 32.41


def test_missing_cn_market_fear_greed_does_not_match_filter():
    service = _service()
    condition = {
        "type": "numeric",
        "field": "cn-market-fear-greed",
        "operator": "lt",
        "value": 15,
    }

    assert not service._matches_rule_condition(
        {"values": {"cn-market-fear-greed": None}},
        condition,
        CN_INDEX_STRATEGY_FILTER_KEYS,
    )


def test_index_snapshot_injects_cn_baifenwei_fear_greed_components():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda _symbol_name: [
        {
            "trade_date": date(2026, 8, 5),
            "emotion_value": 50,
            "main_basis": 0,
            "month_basis": 0,
            "up_ratio_pct": 50,
        }
    ]
    service._load_cn_market_fear_greed_rows = lambda **_kwargs: []
    service._load_cn_baifenwei_fear_greed_rows = lambda **_kwargs: [
        {
            "trade_date": date(2026, 8, 5),
            "fear_greed_value": 40.26,
            "volatility_score": 5.23,
            "relative_turnover_score": 70.90,
            "margin_trading_score": 0.79,
            "market_breadth_score": 60.19,
            "rsi_score": 64.29,
            "limit_up_down_ratio_score": 91.53,
        }
    ]

    snapshots = service._build_index_snapshots(
        "sh000001",
        "上证指数",
        {},
        [_candle("2026-08-05")],
    )

    values = snapshots[0]["values"]
    assert values["cn-baifenwei-fear-greed"] == 40.26
    assert values["cn-baifenwei-volatility"] == 5.23
    assert values["cn-baifenwei-relative-turnover"] == 70.90
    assert values["cn-baifenwei-margin-trading"] == 0.79
    assert values["cn-baifenwei-market-breadth"] == 60.19
    assert values["cn-baifenwei-rsi"] == 64.29
    assert values["cn-baifenwei-limit-up-down-ratio"] == 91.53


def test_missing_cn_baifenwei_component_does_not_match_filter():
    service = _service()
    condition = {
        "type": "numeric",
        "field": "cn-baifenwei-market-breadth",
        "operator": "gt",
        "value": 80,
    }

    assert not service._matches_rule_condition(
        {"values": {"cn-baifenwei-market-breadth": None}},
        condition,
        CN_INDEX_STRATEGY_FILTER_KEYS,
    )
