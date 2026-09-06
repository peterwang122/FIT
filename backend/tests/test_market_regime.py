import csv
import json
import runpy
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps.auth import get_current_user, require_authenticated_user
from app.api.routes_macro import router
from app.services import market_regime_service as service


def point(day="2026-03-13", **overrides):
    return {
        "date": day, "open": 99, "high": 102, "low": 98, "close": 100,
        "medium_ma": 95, "long_ma": 90, "long_slope": .05,
        "breadth_medium": 60, "breadth_long": 55, "traded": 1000, "eligible": 900,
        "state": "valid", "buy_multiplier": 1, **overrides,
    }


def payload():
    return {
        "schema_version": "market-regime-research-v1", "generated_at": "2026-09-06T12:00:00+08:00",
        "research_only": True, "model_approved": False, "rule_name": "balanced",
        "breadth_as_of": "2026-03-13", "notes": ["研究候选"],
        "series": {
            "sh000852": {"index_name": "中证1000", "points": [point(), point("2026-09-04", state="unavailable", buy_multiplier=0, breadth_medium=None, breadth_long=None)], "events": []},
            "sh000985": {"index_name": "中证全指", "points": [point(close=101)], "events": []},
        },
    }


@pytest.fixture
def report(tmp_path, monkeypatch):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload()), encoding="utf-8")
    monkeypatch.setattr(service, "REPORT_PATH", path)
    service._read_report.cache_clear()
    yield path
    service._read_report.cache_clear()


def test_snapshot_keeps_nulls_research_flags_and_index_isolation(report):
    csi = service.get_market_regime()
    all_share = service.get_market_regime("sh000985")
    assert csi.latest.breadth_long is None
    assert csi.latest.state == "unavailable"
    assert csi.model_approved is False and csi.research_only is True
    assert csi.latest.close == 100 and all_share.latest.close == 101
    assert csi.breadth_as_of == date(2026, 3, 13)
    assert csi.history_end == date(2026, 9, 4)
    assert csi.generated_at.utcoffset().total_seconds() == 28800


def test_window_empty_and_no_future_point_in_latest(report):
    response = service.get_market_regime(end_date=date(2026, 3, 13))
    assert len(response.points) == 1 and response.latest.date == date(2026, 3, 13)
    assert response.history_end == date(2026, 9, 4)
    empty = service.get_market_regime(start_date=date(2027, 1, 1))
    assert empty.latest is None and empty.points == [] and empty.events == []
    with pytest.raises(ValueError):
        service.get_market_regime(start_date=date(2027, 1, 1), end_date=date(2026, 1, 1))


def test_event_overlap_keeps_gap_reason(report):
    data = payload()
    data["series"]["sh000852"]["events"] = [{
        "start": "2026-03-01", "end": "2026-03-13", "days": 10,
        "closed": False, "end_reason": "unavailable", "drawdown_20d_pct": None,
    }]
    report.write_text(json.dumps(data))
    response = service.get_market_regime(start_date=date(2026, 3, 13))
    assert len(response.events) == 1
    assert response.events[0].closed is False
    assert response.events[0].drawdown_20d_pct is None
    assert not service.get_market_regime(start_date=date(2026, 4, 1)).events


def test_republished_report_invalidates_cache(report):
    assert service.get_market_regime().latest.close == 100
    data = payload()
    data["series"]["sh000852"]["points"][-1]["close"] = 101
    other = report.with_suffix(".tmp")
    other.write_text(json.dumps(data) + "\n")
    other.replace(report)
    assert service.get_market_regime().latest.close == 101


def test_missing_partial_ohlc_is_not_invented(report):
    data = payload()
    data["series"]["sh000985"]["points"][0].update(open=None, high=None, low=None)
    report.write_text(json.dumps(data))
    row = service.get_market_regime("sh000985").latest
    assert row.open is None and row.high is None and row.low is None and row.close == 101


@pytest.mark.parametrize("problem", ["duplicate", "nan", "invalid_ohlc", "inconsistent", "missing_evidence", "approved", "broken_json"])
def test_invalid_snapshot_fails_explicitly(report, problem):
    data = payload()
    row = data["series"]["sh000852"]["points"][0]
    if problem == "duplicate":
        data["series"]["sh000852"]["points"].append(row)
    elif problem == "nan":
        row["close"] = float("nan")
    elif problem == "invalid_ohlc":
        row["low"] = 105
    elif problem == "inconsistent":
        row["buy_multiplier"] = 0
    elif problem == "missing_evidence":
        row["breadth_long"] = None
    elif problem == "approved":
        data["model_approved"] = True
    report.write_text("{" if problem == "broken_json" else json.dumps(data))
    with pytest.raises(RuntimeError, match="重新生成"):
        service.get_market_regime()


def test_missing_report_has_explicit_message(report):
    report.unlink()
    with pytest.raises(RuntimeError, match="尚未生成"):
        service.get_market_regime()


def test_route_access_validation_and_serialization(report):
    app = FastAPI()
    app.include_router(router, prefix="/macro", dependencies=[Depends(require_authenticated_user)])
    with TestClient(app) as client:
        assert client.get("/macro/market-regime").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
        result = client.get("/macro/market-regime").json()["data"]
        assert result["latest"]["date"] == "2026-09-04"
        assert result["latest"]["breadth_long"] is None
        assert result["research_only"] is True
        assert client.get("/macro/market-regime?index_code=sh000985").json()["data"]["index_name"] == "中证全指"
        assert client.get("/macro/market-regime?index_code=sh000001").status_code == 422
        assert client.get("/macro/market-regime?start_date=2027-01-01&end_date=2026-01-01").status_code == 400
        report.unlink()
        assert client.get("/macro/market-regime").status_code == 503


@pytest.fixture
def publication(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    script = Path(__file__).resolve().parents[2] / "scripts/research/publish_market_regime.py"
    publish = runpy.run_path(str(script))["publish"]
    inputs = tmp_path / "inputs"
    study = inputs / "legacy-hfq-study"
    study.mkdir(parents=True)
    manifest = study / "manifest.json"
    manifest.write_text(json.dumps({
        "breadth_kind": "legacy_hfq_observed_stocks", "production_approved": False,
        "strategy_evaluation_end": "2026-03-13",
    }))
    rows = [
        point("2023-01-03", observed=1000), point(observed=1000),
        point("2026-09-04", observed=0, traded=0, eligible=0,
              breadth_medium=None, breadth_long=None, state="unavailable", buy_multiplier=0),
    ]
    for index in ("sh000852", "sh000985"):
        (inputs / f"{index}.json").write_text(json.dumps(rows))
        with (study / f"{index}_balanced-daily.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (study / f"{index}_balanced-events.csv").write_text("start,end,days,closed,end_reason\n")
    return publish, inputs, tmp_path / "published/report.json", manifest


def test_publication_preserves_history_and_unknown_coverage(publication):
    publish, inputs, target, _ = publication
    publish(inputs, target)
    report = json.loads(target.read_text())
    for series in report["series"].values():
        assert len(series["points"]) == 3 and series["points"][0]["date"] == "2023-01-03"
        assert series["points"][1]["eligible"] == 900
        assert all(series["points"][-1][key] is None for key in ("observed", "traded", "eligible"))
        assert series["points"][-1]["breadth_long"] is None
    assert not target.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("change", [{"production_approved": True}, {"breadth_kind": "unadjusted"}])
def test_publication_rejects_unapproved_source_contract(publication, change):
    publish, inputs, target, manifest = publication
    data = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**data, **change}))
    with pytest.raises(ValueError, match="Only unapproved"):
        publish(inputs, target)
    assert not target.exists()


def test_failed_publication_keeps_previous_snapshot(publication):
    publish, inputs, target, _ = publication
    publish(inputs, target)
    original = target.read_bytes()
    prices_path = inputs / "sh000985.json"
    prices = json.loads(prices_path.read_text())
    prices[0]["low"] = 999
    prices_path.write_text(json.dumps(prices))
    with pytest.raises(ValueError, match="Invalid OHLC"):
        publish(inputs, target)
    assert target.read_bytes() == original
