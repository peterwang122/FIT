from datetime import date
from types import SimpleNamespace

import pytest

from app.services.quant_service import CSI1000_REFERENCE_VIX_FILTER_KEYS, QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _payload(target_code: str = "sh000852", target_name: str = "中证1000") -> dict:
    return {
        "strategy_engine": "snapshot",
        "strategy_type": "index",
        "target_market": "cn",
        "target_code": target_code,
        "target_name": target_name,
        "blue_filter_groups": [
            {
                "conditions": [
                    {
                        "type": "numeric",
                        "field": "reference-vix-hs300-high",
                        "operator": "gte",
                        "value": 25,
                    }
                ]
            }
        ],
    }


def test_reference_vix_fields_are_scoped_to_csi1000():
    service = _service()

    csi1000_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000852", "中证1000")
    hs300_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000300", "沪深300")

    assert set(CSI1000_REFERENCE_VIX_FILTER_KEYS).issubset(csi1000_keys)
    assert not set(CSI1000_REFERENCE_VIX_FILTER_KEYS).intersection(hs300_keys)


def test_reference_vix_snapshot_uses_hs300_and_csi500_collected_highs():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda _name: []
    service._build_emotion_value_by_date = lambda _name: {}
    service._build_basis_value_by_date = lambda _name: ({}, {})
    service._build_breadth_value_by_date = lambda: {}

    rows_by_code = {
        "300ETF_QVIX": [{"trade_date": date(2026, 3, 23), "high_price": 50.75}],
        "500ETF_QVIX": [{"trade_date": date(2026, 3, 23), "high_price": 57.96}],
    }
    service.stock_service = SimpleNamespace(
        list_index_qvix_daily_data=lambda code, **_kwargs: rows_by_code.get(code, []),
    )

    snapshots = service._build_index_snapshots(
        "sh000852",
        "中证1000",
        {},
        [
            {
                "trade_date": date(2026, 3, 23),
                "open": 7000,
                "high": 7100,
                "low": 6900,
                "close": 7050,
            }
        ],
    )

    values = snapshots[0]["values"]
    assert values["reference-vix-hs300-high"] == 50.75
    assert values["reference-vix-csi500-high"] == 57.96


def test_reference_vix_rule_supports_threshold_equality():
    service = _service()
    condition = {
        "type": "numeric",
        "field": "reference-vix-hs300-high",
        "operator": "gte",
        "value": 25,
    }

    assert service._matches_rule_condition(
        {"values": {"reference-vix-hs300-high": 25}},
        condition,
        CSI1000_REFERENCE_VIX_FILTER_KEYS,
    )


def test_episode_start_requires_three_previous_days_below_threshold():
    service = _service()
    field = "reference-vix-hs300-high"
    condition = {
        "type": "numeric",
        "field": field,
        "operator": "episode_start",
        "value": 25,
    }
    previous = [
        {"values": {field: 24}},
        {"values": {field: 23}},
        {"values": {field: 24.5}},
    ]

    assert service._matches_rule_condition(
        {"values": {field: 25}}, condition, CSI1000_REFERENCE_VIX_FILTER_KEYS, previous
    )
    assert not service._matches_rule_condition(
        {"values": {field: 25}}, condition, CSI1000_REFERENCE_VIX_FILTER_KEYS, previous[-2:]
    )


def test_reference_vix_rule_rejected_for_other_indexes():
    service = _service()

    with pytest.raises(ValueError, match="仅支持中证1000"):
        service._validate_strategy_payload(_payload("sh000300", "沪深300"))
