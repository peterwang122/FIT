import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps.auth import require_non_guest_user
from app.services import research_service
from app.services.research_service import ResearchService


def test_guest_cannot_access_research():
    with pytest.raises(HTTPException) as exc_info:
        require_non_guest_user(SimpleNamespace(role="guest"))

    assert exc_info.value.status_code == 403


def test_regular_user_can_access_research():
    user = SimpleNamespace(role="user")

    assert require_non_guest_user(user) is user


def test_research_service_reads_generated_report(tmp_path, monkeypatch):
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps({"index_summaries": [{"index_name": "上证50"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(research_service, "VIX_OPTION_REPORT_PATH", report_path)

    payload = ResearchService().get_vix_option_analysis()

    assert payload["index_summaries"][0]["index_name"] == "上证50"


def test_research_service_rejects_missing_report(tmp_path, monkeypatch):
    monkeypatch.setattr(research_service, "VIX_OPTION_REPORT_PATH", tmp_path / "missing.json")

    with pytest.raises(FileNotFoundError):
        ResearchService().get_vix_option_analysis()


def test_csi1000_futures_report_reads_wave_report_without_strategy(tmp_path, monkeypatch):
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps({"waves": [{"wave_id": 1, "direction": "up"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(research_service, "CSI1000_FUTURES_REPORT_PATH", report_path)

    payload = ResearchService().get_csi1000_futures_analysis()

    assert payload["waves"][0]["direction"] == "up"


def test_csi1000_futures_report_rejects_old_strategy_report_shape(tmp_path, monkeypatch):
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps({"rankings": [], "strategy": {"fingerprint": "value"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(research_service, "CSI1000_FUTURES_REPORT_PATH", report_path)

    with pytest.raises(RuntimeError, match="格式无效"):
        ResearchService().get_csi1000_futures_analysis()


def test_option_contract_candles_reads_cffex_daily_table():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = [
        {
            "trade_date": date(2026, 3, 23),
            "open_price": 10.0,
            "high_price": 12.0,
            "low_price": 9.0,
            "close_price": 11.0,
            "volume": 120,
            "turnover": 1300,
            "open_interest": 88,
        }
    ]

    payload = ResearchService(db).get_option_contract_candles("cffex", "MO2604-C-8000")

    assert payload["exchange"] == "CFFEX"
    assert payload["candles"][0]["trade_date"] == "2026-03-23"
    assert payload["candles"][0]["close"] == 11.0
    assert "option_cffex_rtj_daily_data" in str(db.execute.call_args.args[0])


def test_option_contract_candles_reads_exchange_daily_table_and_skips_invalid_ohlc():
    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = [
        {
            "trade_date": date(2026, 3, 20),
            "open_price": None,
            "high_price": 0,
            "low_price": 0,
            "close_price": 0,
            "volume": 0,
            "turnover": 0,
            "open_interest": 0,
            "underlying_code": "510300",
        },
        {
            "trade_date": date(2026, 3, 23),
            "open_price": 0.12,
            "high_price": 0.16,
            "low_price": 0.1,
            "close_price": 0.14,
            "volume": 200,
            "turnover": 28000,
            "open_interest": 100,
            "underlying_code": "510300",
        },
    ]

    payload = ResearchService(db).get_option_contract_candles("SSE", "10009000")

    assert payload["underlying_code"] == "510300"
    assert len(payload["candles"]) == 1
    assert payload["candles"][0]["open"] == 0.12
    assert "option_exchange_contract_daily_data" in str(db.execute.call_args.args[0])
    assert db.execute.call_args.args[1]["exchange"] == "SSE"


def test_option_contract_candles_rejects_unknown_exchange():
    with pytest.raises(ValueError, match="不支持的期权交易所"):
        ResearchService(MagicMock()).get_option_contract_candles("UNKNOWN", "123")
