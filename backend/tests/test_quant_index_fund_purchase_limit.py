from datetime import date

import pytest

from app.services.quant_service import FUND_PURCHASE_LIMIT_FILTER_KEYS, QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str, close: float = 3000.0) -> dict:
    return {
        "trade_date": trade_date,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
    }


def test_fund_purchase_limit_filters_are_available_only_for_shanghai_index():
    service = _service()

    shanghai_keys = service._allowed_snapshot_filter_keys(
        "index", "cn", "sh000001", "上证指数"
    )
    hs300_keys = service._allowed_snapshot_filter_keys(
        "index", "cn", "sh000300", "沪深300"
    )

    assert set(FUND_PURCHASE_LIMIT_FILTER_KEYS).issubset(shanghai_keys)
    assert not set(FUND_PURCHASE_LIMIT_FILTER_KEYS).intersection(hs300_keys)


def test_index_snapshot_reads_precomputed_fund_purchase_limit_values():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda _symbol_name: [
        {
            "trade_date": date(2026, 7, 16),
            "emotion_value": 55,
            "main_basis": -10,
            "month_basis": -3,
            "up_ratio_pct": 60,
            "fund_purchase_limit_count": 420,
            "fund_purchase_limit_total_count": 2100,
            "fund_purchase_limit_pct": 20,
        }
    ]

    snapshots = service._build_index_snapshots(
        "sh000001", "上证指数", {}, [_candle("2026-07-16")]
    )

    assert snapshots[0]["values"]["fund-purchase-limit-count"] == 420
    assert snapshots[0]["values"]["fund-purchase-limit-pct"] == 20


def test_null_fund_purchase_limit_value_does_not_match_filter():
    service = _service()
    condition = {
        "type": "numeric",
        "field": "fund-purchase-limit-pct",
        "operator": "gt",
        "value": 10,
    }

    assert not service._matches_rule_condition(
        {"values": {"fund-purchase-limit-pct": None}},
        condition,
        FUND_PURCHASE_LIMIT_FILTER_KEYS,
    )


def test_fund_purchase_limit_filter_rejects_other_index():
    service = _service()
    payload = {
        "strategy_engine": "snapshot",
        "strategy_type": "index",
        "target_market": "cn",
        "target_code": "sh000300",
        "target_name": "沪深300",
        "blue_filter_groups": [
            {
                "conditions": [
                    {
                        "type": "numeric",
                        "field": "fund-purchase-limit-count",
                        "operator": "gt",
                        "value": 100,
                    }
                ]
            }
        ],
    }

    with pytest.raises(ValueError, match="公募基金限购"):
        service._validate_strategy_payload(payload)
