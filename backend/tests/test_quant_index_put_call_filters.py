from datetime import date
from types import SimpleNamespace

import pytest

from app.services.quant_service import (
    CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS,
    CN_OPTION_PUT_CALL_FILTER_KEYS,
    EXCHANGE_OPTION_FILTER_KEYS,
    OPTION_VIX_FILTER_KEYS,
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
    assert values["cn-option-flow-cp-turnover"] == pytest.approx(1 / 0.6)


def test_cn_option_flow_put_call_payload_includes_volume_turnover_and_reciprocal():
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
        "turnover_call_put_ratio": pytest.approx(1 / 0.44),
    }


@pytest.mark.parametrize(
    ("put_call_ratio", "expected"),
    [
        (0.5, 2.0),
        (1.0, 1.0),
        (None, None),
        (0, None),
        (-1, None),
        (float("nan"), None),
        (float("inf"), None),
    ],
)
def test_cn_option_flow_call_put_ratio_handles_invalid_denominators(put_call_ratio, expected):
    service = _service()
    payload = service._build_cn_option_flow_put_call_point_payload(
        {
            "trade_date": date(2026, 5, 8),
            "option_volume_pc_ratio": 0.72,
            "option_turnover_pc_ratio": put_call_ratio,
        }
    )

    assert payload["turnover_call_put_ratio"] == expected


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
    snapshot = {"values": {"cn-option-flow-cp-turnover": None}}
    condition = {
        "type": "numeric",
        "field": "cn-option-flow-cp-turnover",
        "operator": "lt",
        "value": 1,
    }

    assert not service._matches_rule_condition(snapshot, condition, CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS)


def test_exchange_option_filter_keys_are_scoped_to_index_products():
    service = _service()

    hs300_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000300", "沪深300")
    csi500_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000905", "中证500")
    star50_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000688", "科创50")

    assert "cn-option-pc-sse-510300-current" in hs300_keys
    assert "cn-option-flow-pc-turnover-szse-159919" in hs300_keys
    assert "cn-option-pc-sse-510500-current" in csi500_keys
    assert "cn-option-pc-sse-510300-current" not in csi500_keys
    assert "cn-option-pc-sse-588000-current" in star50_keys
    assert "cn-option-flow-cp-turnover-sse-588080" in star50_keys


def test_exchange_option_snapshot_values_are_read_from_json_without_mixing_sources():
    service = _service()
    service.stock_service = SimpleNamespace(
        list_index_qvix_daily_data=lambda *_args, **_kwargs: [],
    )
    service._load_precomputed_index_indicator_rows = lambda _symbol_name: [
        {
            "trade_date": date(2026, 7, 3),
            "emotion_value": 50,
            "main_basis": 0,
            "month_basis": 0,
            "up_ratio_pct": 0,
            "exchange_option_pc_json": {
                "sse:510300": {
                    "option_pc_current_month": 0.8,
                    "option_turnover_pc_ratio": 0.5,
                },
                "szse:159919": {
                    "option_pc_current_month": 1.2,
                    "option_turnover_pc_ratio": 2.0,
                },
            },
        }
    ]

    values = service._build_index_snapshots(
        "sh000300",
        "沪深300",
        {},
        [_candle("2026-07-03", 4000)],
    )[0]["values"]

    assert values["cn-option-pc-sse-510300-current"] == 0.8
    assert values["cn-option-pc-szse-159919-current"] == 1.2
    assert values["cn-option-flow-cp-turnover-sse-510300"] == 2.0
    assert values["cn-option-flow-cp-turnover-szse-159919"] == 0.5


def test_exchange_option_series_keeps_products_separate():
    service = _service()
    rows = [
        {
            "trade_date": date(2026, 7, 3),
            "exchange_option_pc_json": {
                "sse:588000": {
                    "option_pc_current_month": 0.9,
                    "option_volume_pc_ratio": 0.7,
                },
                "sse:588080": {
                    "option_pc_current_month": 1.1,
                    "option_volume_pc_ratio": 1.3,
                },
            },
        }
    ]

    series = service._build_cn_option_series(rows, "科创50")

    assert [item["source_key"] for item in series] == ["sse:588000", "sse:588080"]
    assert series[0]["put_call_points"][0]["current_month_put_call_ratio"] == 0.9
    assert series[1]["flow_points"][0]["volume_put_call_ratio"] == 1.3


def test_exchange_option_strategy_rejects_other_index_product():
    service = _service()
    payload = _put_call_rule_payload("中证500", "sh000905")
    payload["blue_filter_groups"][0]["conditions"][0]["field"] = (
        "cn-option-pc-sse-510300-current"
    )

    with pytest.raises(ValueError, match="交易所/ETF期权"):
        service._validate_strategy_payload(payload)

    assert "cn-option-pc-sse-510300-current" in EXCHANGE_OPTION_FILTER_KEYS


def test_option_vix_filter_keys_are_scoped_by_index_and_source():
    service = _service()

    hs300_keys = service._allowed_snapshot_filter_keys(
        "index",
        "cn",
        "sh000300",
        "沪深300",
    )
    csi500_keys = service._allowed_snapshot_filter_keys(
        "index",
        "cn",
        "sh000905",
        "中证500",
    )

    assert "cn-option-vix-open-cffex-io" in hs300_keys
    assert "cn-option-vix-close-sse-510300" in hs300_keys
    assert "cn-option-vix-close-szse-159919" in hs300_keys
    assert "cn-option-vix-close-sse-510500" in csi500_keys
    assert "cn-option-vix-close-cffex-io" not in csi500_keys


def test_option_vix_snapshot_values_are_read_without_mixing_sources():
    service = _service()
    service.stock_service = SimpleNamespace(
        list_index_qvix_daily_data=lambda *_args, **_kwargs: [],
    )
    service._load_precomputed_index_indicator_rows = lambda _symbol_name: [
        {
            "trade_date": date(2026, 7, 3),
            "emotion_value": 50,
            "main_basis": 0,
            "month_basis": 0,
            "up_ratio_pct": 0,
            "option_vix_json": {
                "cffex:IO": {"vix_open": 24.3, "vix_close": 22.4},
                "sse:510300": {"vix_open": 24.0, "vix_close": 22.3},
                "szse:159919": {"vix_open": 24.4, "vix_close": 22.5},
            },
        }
    ]

    values = service._build_index_snapshots(
        "sh000300",
        "沪深300",
        {},
        [_candle("2026-07-03", 4000)],
    )[0]["values"]

    assert values["cn-option-vix-open-cffex-io"] == 24.3
    assert values["cn-option-vix-close-sse-510300"] == 22.3
    assert values["cn-option-vix-close-szse-159919"] == 22.5


def test_option_vix_series_returns_open_close_and_contract_metadata():
    service = _service()
    rows = [
        {
            "trade_date": date(2026, 7, 3),
            "option_vix_json": {
                "cffex:IO": {
                    "vix_open": 24.3,
                    "vix_high": 24.3,
                    "vix_low": 22.4,
                    "vix_close": 22.4,
                    "near_contract_month": "2607",
                    "near_expiry_date": "2026-07-17",
                    "near_strike_count": 23,
                    "next_contract_month": "2608",
                    "next_expiry_date": "2026-08-21",
                    "next_strike_count": 23,
                },
            },
        }
    ]

    series = service._build_cn_option_series(rows, "沪深300")
    cffex = next(item for item in series if item["source_key"] == "cffex:IO")

    assert cffex["vix_points"][0]["vix_open"] == 24.3
    assert cffex["vix_points"][0]["vix_close"] == 22.4
    assert cffex["vix_points"][0]["near_contract_month"] == "2607"
    assert cffex["vix_points"][0]["next_strike_count"] == 23


def test_option_vix_strategy_rejects_other_index_source():
    service = _service()
    payload = _put_call_rule_payload("中证500", "sh000905")
    payload["blue_filter_groups"][0]["conditions"][0]["field"] = (
        "cn-option-vix-close-cffex-io"
    )

    with pytest.raises(ValueError, match="自算VIX"):
        service._validate_strategy_payload(payload)

    assert "cn-option-vix-close-cffex-io" in OPTION_VIX_FILTER_KEYS
