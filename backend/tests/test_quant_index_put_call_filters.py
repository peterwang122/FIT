from datetime import date

import pytest

from app.services.quant_service import (
    CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS,
    CN_OPTION_PUT_CALL_FILTER_KEYS,
    QuantService,
)


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str, close: float) -> dict:
    return {
        "trade_date": trade_date,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
    }


def _put_call_rule_payload(target_name: str, target_code: str = "sh000300") -> dict:
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
                        "field": "cn-option-put-call-current",
                        "operator": "lt",
                        "value": 1,
                    }
                ]
            }
        ],
    }


def test_cn_option_put_call_filter_keys_allowed_only_for_supported_indexes():
    service = _service()

    hs300_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000300", "沪深300")
    csi500_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000905", "中证500")

    assert set(CN_OPTION_PUT_CALL_FILTER_KEYS).issubset(hs300_keys)
    assert not set(CN_OPTION_PUT_CALL_FILTER_KEYS).intersection(csi500_keys)


def test_index_snapshots_include_precomputed_cn_option_put_call_values():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda symbol_name: [
        {
            "trade_date": date(2026, 4, 30),
            "emotion_value": 60,
            "main_basis": -20,
            "month_basis": -5,
            "up_ratio_pct": 55,
            "option_pc_current_month": 0.8,
            "option_pc_next_month": 0.9,
            "option_pc_quarter_1": 1.1,
            "option_pc_quarter_2": 1.2,
            "option_volume_pc_ratio": 0.7,
            "option_turnover_pc_ratio": 0.6,
        }
    ]

    snapshots = service._build_index_snapshots("sh000001", "上证指数", {}, [_candle("2026-04-30", 3000)])

    values = snapshots[0]["values"]
    assert values["cn-option-put-call-current"] == 0.8
    assert values["cn-option-put-call-next"] == 0.9
    assert values["cn-option-put-call-quarter-1"] == 1.1
    assert values["cn-option-put-call-quarter-2"] == 1.2
    assert values["cn-option-flow-pc-volume"] == 0.7
    assert values["cn-option-flow-pc-turnover"] == 0.6


def test_cn_option_flow_put_call_payload_includes_volume_and_turnover():
    service = _service()
    payload = service._build_cn_option_flow_put_call_point_payload(
        {
            "trade_date": date(2026, 5, 8),
            "option_volume_pc_ratio": 0.72,
            "option_turnover_pc_ratio": 0.44,
        }
    )

    assert payload == {
        "trade_date": date(2026, 5, 8),
        "volume_put_call_ratio": 0.72,
        "turnover_put_call_ratio": 0.44,
    }


def test_cn_option_flow_put_call_filter_keys_share_supported_indexes():
    service = _service()

    hs300_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000300", "沪深300")
    csi500_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000905", "中证500")

    assert set(CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS).issubset(hs300_keys)
    assert not set(CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS).intersection(csi500_keys)


def test_cn_option_put_call_payload_includes_special_marker():
    service = _service()
    payload = service._build_cn_option_put_call_point_payload(
        {
            "trade_date": date(2025, 4, 7),
            "option_pc_current_month": 2.0,
            "option_pc_current_month_contract_month": "2504",
            "option_pc_current_month_special_flag": 1,
            "option_pc_current_month_special_note": "中证1000 MO2504 使用特殊点位 5500 计算",
            "option_pc_next_month": 400 / 278.8,
            "option_pc_next_month_contract_month": "2505",
            "option_pc_next_month_special_flag": 1,
            "option_pc_next_month_special_note": "中证1000 MO2505 使用特殊点位 5500 计算",
            "option_pc_quarter_1": None,
            "option_pc_quarter_1_contract_month": None,
            "option_pc_quarter_2": None,
            "option_pc_quarter_2_contract_month": None,
        }
    )

    assert payload["next_month_special_calculation"] is True
    assert payload["next_month_special_note"] == "中证1000 MO2505 使用特殊点位 5500 计算"
    assert payload["quarter_1_special_calculation"] is False
    assert payload["quarter_1_special_note"] is None


def test_cn_option_put_call_payload_defaults_old_rows_to_not_special():
    service = _service()
    payload = service._build_cn_option_put_call_point_payload(
        {
            "trade_date": date(2025, 4, 7),
            "option_pc_current_month": 2.0,
            "option_pc_current_month_contract_month": "2504",
            "option_pc_next_month": 1.4,
            "option_pc_next_month_contract_month": "2505",
            "option_pc_quarter_1": None,
            "option_pc_quarter_1_contract_month": None,
            "option_pc_quarter_2": None,
            "option_pc_quarter_2_contract_month": None,
        }
    )

    assert payload["current_month_special_calculation"] is False
    assert payload["current_month_special_note"] is None


def test_cn_option_put_call_filter_rejects_unsupported_index():
    service = _service()

    with pytest.raises(ValueError, match="A股 Put/Call"):
        service._validate_strategy_payload(_put_call_rule_payload("中证500", "sh000905"))


def test_cn_option_flow_put_call_filter_rejects_unsupported_index():
    service = _service()
    payload = _put_call_rule_payload("中证500", "sh000905")
    payload["blue_filter_groups"][0]["conditions"][0]["field"] = "cn-option-flow-pc-volume"

    with pytest.raises(ValueError, match="A股 Put/Call"):
        service._validate_strategy_payload(payload)


def test_cn_option_put_call_null_value_does_not_match_rule():
    service = _service()
    snapshot = {"values": {"cn-option-put-call-current": None}}
    condition = {
        "type": "numeric",
        "field": "cn-option-put-call-current",
        "operator": "lt",
        "value": 1,
    }

    assert not service._matches_rule_condition(snapshot, condition, CN_OPTION_PUT_CALL_FILTER_KEYS)


def test_cn_option_flow_put_call_null_value_does_not_match_rule():
    service = _service()
    snapshot = {"values": {"cn-option-flow-pc-turnover": None}}
    condition = {
        "type": "numeric",
        "field": "cn-option-flow-pc-turnover",
        "operator": "lt",
        "value": 1,
    }

    assert not service._matches_rule_condition(snapshot, condition, CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS)
