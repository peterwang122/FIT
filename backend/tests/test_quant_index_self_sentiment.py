from datetime import date

from app.services.quant_service import CN_INDEX_STRATEGY_FILTER_KEYS, QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str) -> dict:
    return {
        "trade_date": trade_date,
        "open": 6000.0,
        "high": 6050.0,
        "low": 5950.0,
        "close": 6020.0,
    }


def test_self_sentiment_filter_is_available_for_supported_cn_indices():
    service = _service()
    allowed = service._allowed_snapshot_filter_keys("index", "cn", "sh000852", "中证1000")

    assert "self-sentiment-score" in CN_INDEX_STRATEGY_FILTER_KEYS
    assert "self-sentiment-score" in allowed


def test_index_snapshot_reads_precomputed_self_sentiment_score():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda _symbol_name: [
        {
            "trade_date": date(2026, 7, 29),
            "emotion_value": 50,
            "main_basis": 0,
            "month_basis": 0,
            "up_ratio_pct": 50,
            "self_sentiment_score": 67.25,
        }
    ]
    service._load_cn_market_fear_greed_rows = lambda **_kwargs: []

    snapshots = service._build_index_snapshots(
        "sh000001",
        "上证指数",
        {},
        [_candle("2026-07-29")],
    )

    assert snapshots[0]["values"]["self-sentiment-score"] == 67.25


def test_missing_self_sentiment_does_not_match_filter():
    service = _service()
    condition = {
        "type": "numeric",
        "field": "self-sentiment-score",
        "operator": "gte",
        "value": 70,
    }

    assert not service._matches_rule_condition(
        {"values": {"self-sentiment-score": None}},
        condition,
        CN_INDEX_STRATEGY_FILTER_KEYS,
    )
