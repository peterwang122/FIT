import json
from types import SimpleNamespace

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
