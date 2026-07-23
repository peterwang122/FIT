from datetime import date

import pytest

from app.services.quant_service import MARGIN_TRADING_FILTER_KEYS, QuantService


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


def test_margin_trading_filters_are_available_for_every_cn_index():
    service = _service()

    for code, name in (
        ("sh000001", "上证指数"),
        ("sh000300", "沪深300"),
        ("sh000688", "科创50"),
    ):
        allowed = service._allowed_snapshot_filter_keys("index", "cn", code, name)
        assert set(MARGIN_TRADING_FILTER_KEYS).issubset(allowed)


def test_index_snapshot_reads_precomputed_margin_trading_values():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda _symbol_name: [
        {
            "trade_date": date(2026, 7, 16),
            "emotion_value": 55,
            "main_basis": -10,
            "month_basis": -3,
            "up_ratio_pct": 60,
            "margin_financing_balance": 2_829_025_453_142,
            "margin_securities_lending_balance": 20_454_339_987,
            "margin_total_balance": 2_849_479_793_129,
            "margin_financing_net_buy_amount": -28_586_475_046,
        }
    ]

    snapshots = service._build_index_snapshots(
        "sh000001",
        "上证指数",
        {},
        [_candle("2026-07-16")],
    )

    values = snapshots[0]["values"]
    assert values["margin-financing-balance"] == 2_829_025_453_142
    assert values["margin-securities-lending-balance"] == 20_454_339_987
    assert values["margin-total-balance"] == 2_849_479_793_129
    assert values["margin-financing-net-buy"] == -28_586_475_046


def test_null_margin_trading_value_does_not_match_filter():
    service = _service()
    condition = {
        "type": "numeric",
        "field": "margin-financing-net-buy",
        "operator": "gt",
        "value": 0,
    }

    assert not service._matches_rule_condition(
        {"values": {"margin-financing-net-buy": None}},
        condition,
        MARGIN_TRADING_FILTER_KEYS,
    )


def test_margin_trading_filter_rejects_non_cn_market():
    service = _service()
    payload = {
        "strategy_engine": "snapshot",
        "strategy_type": "index",
        "target_market": "us",
        "target_code": ".INX",
        "target_name": "标普500指数",
        "blue_filter_groups": [
            {
                "conditions": [
                    {
                        "type": "numeric",
                        "field": "margin-total-balance",
                        "operator": "gt",
                        "value": 1,
                    }
                ]
            }
        ],
    }

    with pytest.raises(ValueError, match="融资融券"):
        service._validate_strategy_payload(payload)
