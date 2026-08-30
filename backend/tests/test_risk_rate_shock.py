from datetime import date

import pytest

import app.services.task_service as task_service_module
from app.core.config import settings
from app.services.quant_service import (
    RISK_DASHBOARD_CACHE_KEY_PREFIX,
    RISK_DASHBOARD_EVIDENCE_CACHE_KEY_PREFIX,
    QuantService,
)
from app.services.task_service import TaskService
from app.schemas.stock import QuantRiskEvidenceCellResponse


class _UntouchableSession:
    def __init__(self, *args, **kwargs):
        return None

    def query(self, *args, **kwargs):
        raise AssertionError("database must not be touched")

    def get(self, *args, **kwargs):
        raise AssertionError("database must not be touched")


class _FixedMarketCalendar:
    def previous_trading_day(self, _market_scope, _target_date):
        return date(2026, 8, 14)


def _make_service(monkeypatch):
    service = TaskService(_UntouchableSession())
    service.market_calendar = _FixedMarketCalendar()
    cleared = []

    class _FakeQuant:
        def clear_risk_dashboard_caches(self):
            cleared.append(True)
            return 1

    class _FakeStock:
        def list_index_us_treasury_yield_data(self, start_date=None, end_date=None):
            return [
                {
                    "trade_date": "2026-08-13",
                    "yield_3m": 4.1,
                    "yield_2y": 4.2,
                    "yield_10y": 4.3,
                    "yield_real_10y": 2.2,
                    "available_at": "2026-08-14T05:00:00+08:00",
                }
            ]

        def list_index_us_credit_spread_data(self, start_date=None, end_date=None):
            return [
                {
                    "trade_date": "2026-08-14",
                    "high_yield_oas": 3.5,
                    "available_at": "2026-08-17T00:45:00+08:00",
                }
            ]

    service.quant_service = _FakeQuant()
    service.stock_service = _FakeStock()
    return service, cleared


def test_risk_cache_prefixes_bumped_to_v11():
    assert "risk_dashboard:v11" in RISK_DASHBOARD_CACHE_KEY_PREFIX
    assert "risk_dashboard:evidence:v11" in RISK_DASHBOARD_EVIDENCE_CACHE_KEY_PREFIX
    assert settings.index_us_credit_spread_available_at_column == "available_at"


def test_global_mode_label_includes_usd_rate_shock():
    assert QuantService._global_mode_label("usd_rate_shock") == "美元利率冲击"
    assert QuantService._global_mode_label("broad_risk_off") == "全面避险"
    assert (
        QuantService._global_mode_label("tech_deleveraging+usd_rate_shock")
        == "科技去杠杆+美元利率冲击"
    )
    assert (
        QuantService._global_mode_label("broad_risk_off+tech_deleveraging+usd_rate_shock")
        == "全面避险+科技去杠杆+美元利率冲击"
    )
    assert QuantService._global_mode_label(None) == ""


def test_clear_risk_dashboard_caches_uses_scan(monkeypatch):
    deleted = []

    class _FakeRedis:
        def scan_iter(self, pattern):
            return iter([f"{pattern}:2026-08-14:2026-08-15"])

        def delete(self, key):
            deleted.append(key)

    import app.services.quant_service as quant_service_module

    monkeypatch.setattr(quant_service_module, "redis_client", _FakeRedis())
    cleared = QuantService(_UntouchableSession()).clear_risk_dashboard_caches()
    assert cleared == 2
    assert len(deleted) == 2


def test_recompute_risk_after_us_treasury_success(monkeypatch):
    service, cleared = _make_service(monkeypatch)
    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "status": "SUCCESS",
                "result": {"previous_cn_trade_date": "2026-08-14"},
            },
        },
    )
    summary = service._recompute_risk_after_us_treasury("美债收益率日更")
    assert "2026-08-14" in summary
    assert "美债共同来源日期：2026-08-13" in summary
    assert "可用时间 2026-08-14T05:00:00+08:00" in summary
    assert "3M/2Y/10Y/实际10Y 均非空" in summary
    assert cleared == [True]


def test_recompute_risk_after_us_credit_spread_success(monkeypatch):
    service, cleared = _make_service(monkeypatch)
    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "status": "SUCCESS",
                "result": {"previous_cn_trade_date": "2026-08-14"},
            },
        },
    )
    summary = service._recompute_risk_after_us_credit_spread("美股高收益债利差日更")
    assert "前一个A股交易日 2026-08-14" in summary
    assert "HY OAS 来源日期：2026-08-14" in summary
    assert "可用时间 2026-08-17T00:45:00+08:00" in summary
    assert "利差 3.5%" in summary
    assert cleared == [True]


def test_recompute_risk_after_us_treasury_failure_propagates(monkeypatch):
    service, _cleared = _make_service(monkeypatch)

    def _raise(**kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(task_service_module, "run_daily_collection_request", _raise)
    with pytest.raises(RuntimeError, match="定向重算前一个A股交易日风险看板失败"):
        service._recompute_risk_after_us_treasury("美债收益率日更")


def test_recompute_risk_after_us_treasury_rejects_missing_upstream_date(monkeypatch):
    service, cleared = _make_service(monkeypatch)
    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {"status": "SUCCESS"},
        },
    )
    with pytest.raises(RuntimeError, match="未返回 previous_cn_trade_date"):
        service._recompute_risk_after_us_treasury("美债收益率日更")
    assert cleared == []


def test_recompute_risk_after_us_treasury_rejects_mismatched_upstream_date(monkeypatch):
    service, cleared = _make_service(monkeypatch)
    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "status": "SUCCESS",
                "result": {"previous_cn_trade_date": "2026-08-13"},
            },
        },
    )
    with pytest.raises(RuntimeError, match="定向重算日期不一致"):
        service._recompute_risk_after_us_treasury("美债收益率日更")
    assert cleared == []


def test_latest_us_treasury_common_row_rejects_missing_real_yield(monkeypatch):
    service, _cleared = _make_service(monkeypatch)
    service.stock_service = type(
        "Fake",
        (),
        {
            "list_index_us_treasury_yield_data": lambda self, start_date=None, end_date=None: [
                {
                    "trade_date": "2026-08-13",
                    "yield_3m": 4.1,
                    "yield_2y": 4.2,
                    "yield_10y": 4.3,
                    "yield_real_10y": None,
                }
            ]
        },
    )()
    with pytest.raises(RuntimeError, match="缺失：实际10Y"):
        service._latest_us_treasury_common_row("美债收益率日更")


def test_latest_us_treasury_common_row_skips_incomplete_physical_last_row(monkeypatch):
    service, _cleared = _make_service(monkeypatch)
    service.stock_service = type(
        "Fake",
        (),
        {
            "list_index_us_treasury_yield_data": lambda self, start_date=None, end_date=None: [
                {
                    "trade_date": "2026-08-13",
                    "yield_3m": 4.1,
                    "yield_2y": 4.2,
                    "yield_10y": 4.3,
                    "yield_real_10y": 2.2,
                    "available_at": "2026-08-14T05:00:00+08:00",
                },
                {
                    "trade_date": "2026-08-14",
                    "yield_3m": 4.0,
                    "yield_2y": 4.1,
                    "yield_10y": 4.2,
                    "yield_real_10y": None,
                },
            ]
        },
    )()
    row = service._latest_us_treasury_common_row("美债收益率日更")
    assert row["trade_date"] == "2026-08-13"


def _risk_payload_with_rate_mode():
    return {
        "global": {
            "usd_rate_shock": {
                "complete": True,
                "active": True,
                "score": 100.0,
                "matched_condition_count": 3,
                "components": [
                    {
                        "label": "名义10年美债收益率5D变化",
                        "value": 0.25,
                        "level_value": 4.5,
                        "matched": True,
                        "data_date": "2026-08-13",
                        "data_source": "fred_public_csv",
                        "available_at": "2026-08-14T05:00:00+08:00",
                    },
                    {
                        "label": "市场确认（SOX 或 IXN/ACWI 相对收益）",
                        "matched": True,
                        "components": [
                            {
                                "label": "SOX 10D",
                                "value": -6.0,
                                "matched": True,
                                "data_date": "2026-08-13",
                                "data_source": "global_risk",
                                "available_at": "2026-08-14T06:00:00+08:00",
                            },
                            {
                                "label": "IXN/ACWI相对收益10D",
                                "value": -3.0,
                                "matched": True,
                            },
                        ],
                    },
                ],
            }
        }
    }


def test_flatten_risk_components_includes_usd_rate_shock_rows():
    entries = QuantService._flatten_risk_components(_risk_payload_with_rate_mode())
    labels = [entry["label"] for entry in entries]
    assert "名义10年美债收益率5D变化" in labels
    assert "市场确认（SOX 或 IXN/ACWI 相对收益）" in labels
    assert "SOX 10D" in labels
    assert "IXN/ACWI相对收益10D" in labels
    rate_entries = [
        entry for entry in entries if entry["section_key"] == "usd_rate_shock"
    ]
    assert rate_entries[0]["component"]["available_at"] == "2026-08-14T05:00:00+08:00"
    assert rate_entries[0]["component"]["level_value"] == 4.5


def test_flatten_risk_components_tolerates_old_json_without_rate_mode():
    entries = QuantService._flatten_risk_components({"global": {}})
    assert entries == []


def test_flatten_risk_components_keeps_top5_and_no_top1():
    payload = {
        "yellow": {
            "observations": {
                "turnover_concentration": {
                    "label": "A股成交拥挤观察",
                    "components": [
                        {
                            "label": "A股成交额前5%集中度MA5",
                            "matched": True,
                        },
                        {
                            "label": "A股成交额前1%集中度MA5",
                            "matched": True,
                        },
                    ],
                }
            }
        }
    }
    entries = QuantService._flatten_risk_components(payload)
    labels = [entry["label"] for entry in entries]
    assert "A股成交额前5%集中度MA5" in labels
    assert not any("前1%" in label for label in labels)


@pytest.mark.parametrize("matched", [True, False])
def test_aggregate_market_confirmation_preserves_explicit_tri_state(matched):
    component = {
        "label": "市场确认（SOX 或 IXN/ACWI 相对收益）",
        "matched": matched,
        "components": [
            {"label": "SOX 10D", "value": -6.0, "matched": True},
            {"label": "IXN/ACWI相对收益10D", "value": -1.0, "matched": False},
        ],
    }
    assert QuantService._risk_component_match_state(component) is matched


def test_aggregate_market_confirmation_missing_stays_incomplete():
    component = {
        "label": "市场确认（SOX 或 IXN/ACWI 相对收益）",
        "matched": None,
        "components": [
            {"label": "SOX 10D", "value": -1.0, "matched": False},
            {"label": "IXN/ACWI相对收益10D", "value": None, "matched": None},
        ],
        "missing_reason": "市场确认数据不完整",
    }
    assert QuantService._risk_component_match_state(component) is None


def test_risk_evidence_schema_serializes_level_and_availability():
    payload = QuantRiskEvidenceCellResponse.model_validate(
        {
            "trade_date": "2026-08-14",
            "value": 0.25,
            "level_value": 4.5,
            "matched": True,
            "available_at": "2026-08-15T05:00:00+08:00",
        }
    ).model_dump(mode="json")
    assert payload["level_value"] == 4.5
    assert payload["available_at"] == "2026-08-15T05:00:00+08:00"
