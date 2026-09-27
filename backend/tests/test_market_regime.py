import csv
import json
import runpy
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps.auth import get_current_user, require_authenticated_user
from app.api.routes_macro import router
from app.schemas.market_regime import RegimePoint
from app.services import market_regime_service as service


def point(day="2026-03-13", **overrides):
    return {"date": day, "open": 99, "high": 102, "low": 98, "close": 100,
        "medium_ma": 95, "long_ma": 90, "long_slope": .05,
        "breadth_medium": 60, "breadth_long": 55, "traded": 1000, "eligible": 900,
        "state": "valid", "buy_multiplier": 1, **overrides}


def source(day, close=100, **overrides):
    trend = {"open": close, "high": close + 2, "low": close - 2, "close": close,
             "ma60": 95, "ma120": 90, "ma120_change_20d_pct": 1,
             "ma250": 85, "ma250_change_20d_pct": 1, "return_20d_pct": 5, "drawdown_250d_pct": 0}
    return {"date": str(day), **trend, "index_participation_ma60_pct": 100,
        "index_participation_ma120_pct": 100, "missing_reasons": [],
        "index_participation_ma250_pct": 100,
        "adaptation": {"sh000852": {**trend, "close": close + 1}, "sh000300": trend}, **overrides}


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    report = {"generated_at": "2026-09-21T22:45:00+08:00", "target_date": "2026-09-21",
              "as_of_at": "2026-09-21T22:45:00", "macro_evidence": [{"series_key": "m1_yoy", "value": 4.1}],
              "macro_regime_timeline": [],
              "daily_points": [source(date(2026, 9, 1) + timedelta(days=i)) for i in range(21)]}
    monkeypatch.setattr(service, "REPORT_PATH", tmp_path / "report.json")
    monkeypatch.setattr(service, "read_snapshot", lambda *args, **kwargs: report)
    return report


def test_all_history_index_only_without_legacy_file(snapshot):
    for code in ("sh000985", "sh000852", "sh000300"):
        result = service.get_market_regime(code)
        assert result.latest.date == date(2026, 9, 21)
        assert result.latest.state == "valid"
        assert result.daily_update_mode == "index_proxy"
        assert all(p.evidence_mode == "index_proxy" and p.traded == p.eligible == 3 for p in result.points)
        assert result.model_approved is False and result.research_only is True
        assert result.lightweight_research["macro_evidence"][0]["series_key"] == "m1_yoy"
        assert "daily_points" not in result.lightweight_research
    assert service.get_market_regime().latest.close == 101
    assert service.get_market_regime("sh000985").latest.close == 100


def test_deprecated_stock_report_never_affects_current_state(snapshot):
    service.REPORT_PATH.write_text('{"corrupt": "obsolete data"}')
    assert service.get_market_regime().latest.state == "valid"


def test_missing_daily_snapshot_does_not_fallback(snapshot, monkeypatch):
    monkeypatch.setattr(service, "read_snapshot", lambda: None)
    with pytest.raises(RuntimeError, match="不回退"):
        service.get_market_regime()


def test_range_does_not_reset_state_or_include_future_points(snapshot):
    complete = service.get_market_regime()
    result = service.get_market_regime(start_date=date(2026, 9, 20), end_date=date(2026, 9, 20))
    assert result.points == complete.points[-2:-1]
    assert result.history_end == date(2026, 9, 21)
    assert not service.get_market_regime(start_date=date(2027, 1, 1)).points
    with pytest.raises(ValueError):
        service.get_market_regime(start_date=date(2027, 1, 1), end_date=date(2026, 1, 1))


def test_future_points_do_not_change_past(snapshot):
    before = service.get_market_regime().points
    snapshot["daily_points"].append(source("2026-09-22", close=50))
    assert service.get_market_regime().points[:-1] == before


def test_missing_inputs_not_zero_or_valid(snapshot):
    snapshot["daily_points"][-1]["index_participation_ma60_pct"] = None
    result = service.get_market_regime()
    assert result.latest.state == "unavailable" and result.latest.breadth_medium is None
    assert result.latest.missing_reasons == ["index_history_incomplete"]
    assert result.coverage_gaps[-1].days == 1


def test_streaks_and_missing_do_not_release_invalid():
    points = [source(date(2026, 1, 1) + timedelta(days=i), close=50, ma60=100, ma120=100,
                     ma120_change_20d_pct=-1, index_participation_ma60_pct=0,
                     index_participation_ma120_pct=0) for i in range(12)]
    points[10]["missing_reasons"] = ["gap"]
    states = service._proxy_points({"daily_points": points}, "sh000985")
    assert states[1]["state"] == "repair" and states[2]["state"] == "paused"
    assert states[9]["state"] == "invalid" and states[10]["state"] == "unavailable"
    assert states[11]["state"] == "invalid" and states[11]["invalid_streak"] == 1


def test_event_gaps_not_merged_and_forward_window_complete():
    points = [{**point(date(2026, 1, 1) + timedelta(days=i)), "state": "paused" if i < 4 else "valid"} for i in range(25)]
    points[1]["state"] = "unavailable"
    points[4]["low"] = 80
    events = service._events(points)
    assert len(events) == 2 and events[0]["end_reason"] == "unavailable"
    assert not events[0]["closed"] and events[1]["closed"]
    assert events[1]["resumed_date"] == points[4]["date"]
    assert events[0]["drawdown_5d_pct"] == pytest.approx(-20)
    assert events[0]["drawdown_60d_pct"] is None
    points[4]["high"] = None
    assert service._events(points)[0]["upside_5d_pct"] is None


def test_route_auth_index_selection_and_serialization(snapshot):
    app = FastAPI()
    app.include_router(router, prefix="/macro", dependencies=[Depends(require_authenticated_user)])
    with TestClient(app) as client:
        assert client.get("/macro/market-regime").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
        result = client.get("/macro/market-regime").json()["data"]
        assert result["latest"]["date"] == "2026-09-21"
        assert result["lightweight_research"]["macro_evidence"]
        assert client.get("/macro/market-regime?index_code=sh000300").json()["data"]["index_name"] == "沪深300"
        assert client.get("/macro/market-regime?index_code=sh000001").status_code == 422
        assert client.get("/macro/market-regime?start_date=2027-01-01&end_date=2026-01-01").status_code == 400


@pytest.mark.parametrize("change", [{"close": float("nan")}, {"low": 110},
    {"buy_multiplier": 0}, {"medium_ma": None}, {"eligible": 599}])
def test_schema_rejects_inconsistent_evidence(change):
    with pytest.raises(ValidationError):
        RegimePoint.model_validate(point(**change))


@pytest.fixture
def publication(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    publish = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/research/publish_market_regime.py"))["publish"]
    inputs = tmp_path / "inputs"
    study = inputs / "legacy-hfq-study"
    study.mkdir(parents=True)
    manifest = study / "manifest.json"
    manifest.write_text(json.dumps({"breadth_kind": "legacy_hfq_observed_stocks", "production_approved": False,
                                    "strategy_evaluation_end": "2026-03-13"}))
    rows = [point("2023-01-03", observed=1000), point(observed=1000),
        point("2026-09-04", observed=0, traded=0, eligible=0, breadth_medium=None,
              breadth_long=None, state="unavailable", buy_multiplier=0)]
    for index in ("sh000852", "sh000985"):
        (inputs / f"{index}.json").write_text(json.dumps(rows))
        with (study / f"{index}_balanced-daily.csv").open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (study / f"{index}_balanced-events.csv").write_text("start,end,days,closed,end_reason\n")
    return publish, inputs, tmp_path / "published/report.json", manifest


def test_legacy_publication_preserved_as_research_only(publication):
    publish, inputs, target, _ = publication
    publish(inputs, target)
    report = json.loads(target.read_text())
    assert report["strategy_evaluation_end"] == "2026-03-13"
    for series in report["series"].values():
        assert len(series["points"]) == 3 and series["points"][-1]["breadth_long"] is None
    original = target.read_bytes()
    prices_path = inputs / "sh000985.json"
    prices = json.loads(prices_path.read_text())
    prices[0]["low"] = 999
    prices_path.write_text(json.dumps(prices))
    with pytest.raises(ValueError, match="Invalid OHLC"):
        publish(inputs, target)
    assert target.read_bytes() == original


@pytest.mark.parametrize("change", [{"production_approved": True}, {"breadth_kind": "unadjusted"}])
def test_legacy_publication_rejects_unapproved_contract(publication, change):
    publish, inputs, target, manifest = publication
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()), **change}))
    with pytest.raises(ValueError, match="Only unapproved"):
        publish(inputs, target)
    assert not target.exists()
