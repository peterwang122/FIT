import copy
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps.auth import require_non_guest_user
from app.api.routes_research import router
from app.services import research_service
from app.services.research_service import ResearchService

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts" / "research"
sys.path.insert(0, str(RESEARCH))
spec = importlib.util.spec_from_file_location("outlook_analysis", RESEARCH / "ashare_outlook_analysis.py")
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
from ashare_outlook_external import parse_rows
from ashare_outlook_history import compare, period, prepared
from ashare_outlook_extensions import forward, monthly_change, strict_financing, valuation_parts, visible_months
from ashare_outlook_supplement import etf_metrics, parse_ah, policy_metrics, refreshed_global_metrics


def history(count=600):
    return [{"index_code": "sh000985", "trade_date": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
             "open_price": 100 + i * .1, "close_price": 100 + i * .1,
             "low_price": 99 + i * .1, "high_price": 101 + i * .1, "data_source": "fixture"}
            for i in range(count)]


def test_price_calculations_are_cutoff_stable_and_use_sessions():
    rows = history()
    cutoff = rows[399]["trade_date"]
    before = analysis.index_analysis(rows[:400], "sh000985", cutoff)
    after = analysis.index_analysis(rows, "sh000985", cutoff)
    assert before == after
    assert before["ma60"] == pytest.approx(sum(100 + i * .1 for i in range(340, 400)) / 60)
    assert before["return_20d_pct"] == pytest.approx(((100 + 399 * .1) / (100 + 379 * .1) - 1) * 100)
    assert all(c["date"] <= cutoff for c in after["candles"])


def test_price_rows_reject_invalid_ohlc_and_do_not_fill_missing():
    rows = history(3)
    rows[0]["open_price"] = None
    rows[1]["high_price"] = 1
    assert analysis.price_rows(rows, "sh000985", "2026-01-01") == [rows[2]]
    with pytest.raises(ValueError, match="Insufficient"):
        analysis.index_analysis(rows, "sh000985", "2026-01-01")


def test_historical_events_exclude_trigger_day_and_incomplete_future_windows():
    rows = history(275)
    for i in range(250, len(rows)):
        rows[i].update(open_price=80, close_price=80, high_price=81, low_price=79)
    # The trigger day's intraday collapse must not leak into the following window.
    rows[254]["low_price"] = 1
    result = analysis.historical_breaks(rows)
    event = result["events"][0]
    assert event["date"] == rows[254]["trade_date"]
    assert event["worst_20d_pct"] == pytest.approx((79 / 80 - 1) * 100)
    assert event["worst_60d_pct"] is None
    assert result["summaries"][1]["sample_count"] == 0


def test_stress_levels_are_arithmetic_not_fitted_forecasts():
    r = analysis.index_analysis(history(), "sh000985", "2026-01-01")
    assert [s["peak_drawdown_pct"] for s in r["stress_levels"]] == [20, 25, 30]
    assert r["stress_levels"][0]["value"] == pytest.approx(r["cycle_peak"] * .8)


def test_old_cutoff_has_explicit_cycle_error():
    rows = history(300)
    for i, row in enumerate(rows):
        row["trade_date"] = (date(2020, 1, 1) + timedelta(days=i)).isoformat()
    with pytest.raises(ValueError, match="current cycle"):
        analysis.index_analysis(rows, "sh000985", "2021-01-01")


def test_financing_needs_two_exchanges_and_does_not_invent_rolling_windows():
    rows = [{"trade_date": "2026-09-29", "exchange": e, "financing_balance": 100,
             "financing_net_buy_amount": -2} for e in ("SSE", "SZSE")]
    rows += [{"trade_date": "2026-09-30", "exchange": "SSE", "financing_balance": 110,
              "financing_net_buy_amount": None}]
    r = analysis.financing_summary(rows)
    assert r["source_date"] == "2026-09-29"
    assert r["net_buy_cny"] == -4
    assert r["consecutive_windows_verified"] is False


def test_jgb_and_cboe_parsing_skips_notes_and_preserves_units():
    content = b"Interest Rate,,,,\nDate,1Y,2Y,10Y,30Y\n2026/10/1,1.668,-,3.092,4.122\n,\nNote,,,,\n"
    rows = parse_rows("jgb_current", content)
    assert rows == [{"date": "2026-10-01", "1Y": 1.668, "10Y": 3.092, "30Y": 4.122}]
    assert parse_rows("vix", b"DATE,OPEN,HIGH,LOW,CLOSE\n10/02/2026,16,17,15,15.31\n") == [{"date": "2026-10-02", "value": 15.31}]
    assert parse_rows("sp500", b"observation_date,SP500\n2026-10-01,.\n2026-10-02,7722.72\n")[0]["value"] == 7722.72


def test_sge_official_close_parser_rejects_missing_nonpositive_values():
    html = b"<table><tr><td>2026-09-30</td><td>Au99.99</td><td>899</td><td>909</td><td>897.5</td><td>907.32</td></tr><tr><td>2026-09-30</td><td>Ag(T+D)</td><td>14818</td><td>14999</td><td>14766</td><td>14,896.00</td></tr><tr><td>2026-09-29</td><td>Au99.99</td><td>-</td><td>-</td><td>-</td><td>0</td></tr><tr><td>2026-09-28</td><td>Ag(T+D)</td><td>-</td><td>-</td><td>-</td><td>nan</td></tr></table>"
    result = parse_rows("sge", html)
    assert len(result) == 2
    assert next(r for r in result if r["contract"] == "Au99.99")["value"] == 907.32
    assert next(r for r in result if r["contract"] == "Ag(T+D)")["unit"] == "CNY/kg"


def test_dated_report_is_complete_and_source_linked():
    report = ResearchService().get_ashare_outlook()
    assert report["research_only"] and not report["live"]
    assert len(report["indexes"]) == 5
    assert len(report["sections"]) == 24
    assert report["sections"][0]["id"] == "synthesis"
    assert {"relay", "earnings_quality", "stock_funding", "macro_transmission", "shock_types", "policy_delivery",
            "conditional_bottom", "strategy_value", "cross_listing"} <= {s["id"] for s in report["sections"]}
    assert any(s["id"] == "history" for s in report["sections"])
    assert len(report["sources"]) >= 30
    assert {r["contract"] for r in report["precious_metals"]} == {"Au99.99", "Ag(T+D)"}
    assert report["market_date"] == "2026-09-30"
    for i in report["indexes"]:
        assert i["close"] < i["ma250"]
    assert report["provenance"]["production_writes"] is False
    assert all(r["latest"]["risk_overall_score"] is None for r in report["missing_dashboard"])
    assert next(m for m in report["monthly_macro"] if m["series_key"] == "m1_yoy")["period_end"] == "2026-08-31"
    assert next(m for m in report["monthly_macro"] if m["series_key"] == "industrial_profit_ytd_yoy")["period_kind"] == "ytd"
    ids = {s["id"] for s in report["sources"]}
    assert all(set(p["sources"]) <= ids for s in report["sections"] for p in s["paragraphs"])
    assert report["provenance"]["extension_snapshot_sha256"]
    assert report["extensions"]["strict_joint_historical_replay"] is False
    assert report["extensions"]["financing"]["source_date"] == "2026-09-29"
    assert not report["extensions"]["financing"]["latest_target_missing"]
    assert report["extensions"]["financing"]["reference_trade_date"] == "2026-09-30"
    assert report["extensions"]["financing"]["expected_source_date"] == "2026-09-29"
    assert report["extensions"]["financing"]["status"] == "available_lagged"
    assert report["extensions"]["financing"]["lag_trade_days"] == 1
    assert report["financing"]["status"] == "available_lagged"
    assert report["financing"]["consecutive_windows_verified"]
    assert not any(r["item"] == "9月30日深市融资" for r in report["supplement"]["remaining"])
    assert report["extensions"]["financing"]["windows"][0]["net_buy_cny"] == pytest.approx(-42976866522)
    assert report["extensions"]["strategy_comparison"]["signal_data_quality"]["strict_replay_complete"] is False
    assert report["version"] == "ashare-outlook-2026-10-04-v5"
    supplement = report["supplement"]
    assert supplement["ah"]["market_day"] == {"date": "2026-09-30", "value": 124.53}
    assert supplement["ah"]["latest"] == {"date": "2026-10-02", "value": 126.77}
    assert supplement["financing_partial"]["net_buy_cny"] == -22961819001
    assert supplement["financing_partial"]["SZSE_complete"] is False
    assert supplement["concentration"]["top5_pct"] == 42.96
    assert {r["code"] for r in supplement["etf"]} == {"510050", "510300", "510500", "512100"}
    assert all(not w["missing_dates"] for r in supplement["etf"] for w in r["windows"])
    assert supplement["policy_monthly"][-1]["net_cny"] == -4086e8
    assert len(supplement["worldbank"]["current"]) == 12
    assert supplement["worldbank"]["published_date"] == "2026-10-02"
    assert supplement["worldbank"]["history"][0]["changes"]["铁矿石"] is None
    assert not supplement["strict_joint_historical_replay"]
    nav = next(r for r in report["global_markets"] if r["asset_code"] == "ACWI_NAV")
    assert nav["source_date"] == "2026-10-02"
    assert nav["value"] == 160.083613
    assert nav["available_at"] != "2026-10-03T08:00:00"
    assert next(r for r in report["global_markets"] if r["asset_code"] == "BRENT")["value"] == 113.96
    assert report["provenance"]["original_snapshot_as_of_at"] == "2026-10-04T04:00:00"
    assert all(len(row) == len(t["columns"]) for s in report["sections"] for t in s.get("tables", []) for row in t["rows"])
    macro_table = next(s for s in report["sections"] if s["id"] == "macro_transmission")["tables"][0]
    pmi_row = next(row for row in macro_table["rows"] if row[0].startswith("制造业PMI"))
    assert pmi_row[2:] == ["50.10点", "-0.20点", "-0.30点", "2026-09-30T09:30:00", "60 / 29"]
    rates_table = next(s for s in report["sections"] if s["id"] == "shock_types")["tables"][0]
    assert rates_table["rows"][0][1].endswith("%")
    assert rates_table["rows"][0][3].endswith("bp")


@pytest.mark.parametrize("mutation", ["future", "unknown_source", "live", "shape", "historical_future", "historical_cutoff",
                                     "evidence_cells", "extension_cutoff", "macro_future", "supplement_cutoff",
                                     "etf_future", "ah_future", "commodity_future", "policy_future", "refresh_future", "financing_future"])
def test_reader_rejects_invalid_report(tmp_path, monkeypatch, mutation):
    payload = copy.deepcopy(ResearchService().get_ashare_outlook())
    if mutation == "future":
        payload["indexes"][0]["candles"][-1]["date"] = "2027-01-01"
    elif mutation == "unknown_source":
        payload["sections"][0]["paragraphs"][0]["sources"] = ["not-a-source"]
    elif mutation == "live":
        payload["live"] = True
    elif mutation == "historical_future":
        payload["history_comparison"]["spring_2021"]["paths"][0]["points"][-1]["date"] = "2027-01-01"
    elif mutation == "historical_cutoff":
        payload["history_comparison"]["as_of_at"] = "2026-10-05T04:00:00"
    elif mutation == "evidence_cells":
        payload["sections"][0]["tables"][0]["rows"][0].append("invalid")
    elif mutation == "extension_cutoff":
        payload["extensions"]["as_of_at"] = "2026-10-05T04:00:00"
    elif mutation == "macro_future":
        payload["extensions"]["monthly"][0]["available_at"] = "2026-10-05T04:00:00"
    elif mutation == "supplement_cutoff":
        payload["supplement"]["as_of_at"] = "2026-10-05T04:00:00"
    elif mutation == "etf_future":
        payload["supplement"]["etf"][0]["date"] = "2026-10-05"
    elif mutation == "ah_future":
        payload["supplement"]["ah"]["latest"]["date"] = "2026-10-05"
    elif mutation == "commodity_future":
        payload["supplement"]["worldbank"]["published_date"] = "2026-10-04"
    elif mutation == "policy_future":
        payload["supplement"]["policy_monthly"][-1]["published_at"] = "2026-10-05T04:00:00"
    elif mutation == "refresh_future":
        payload["supplement"]["global_refresh"][0]["retrieved_at"] = "2026-10-05T00:00:00"
    elif mutation == "financing_future":
        payload["financing"]["source_date"] = payload["market_date"]
    else:
        payload["indexes"] = None
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(research_service, "ASHARE_OUTLOOK_REPORT_PATH", path)
    with pytest.raises(RuntimeError, match="格式无效"):
        ResearchService().get_ashare_outlook()


def test_missing_report_has_explicit_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(research_service, "ASHARE_OUTLOOK_REPORT_PATH", tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        ResearchService().get_ashare_outlook()


def test_report_api_permission_and_serialization():
    app = FastAPI()
    app.include_router(router, prefix="/research")
    app.dependency_overrides[require_non_guest_user] = lambda: require_non_guest_user(SimpleNamespace(role="guest"))
    client = TestClient(app)
    assert client.get("/research/ashare-outlook").status_code == 403
    app.dependency_overrides[require_non_guest_user] = lambda: require_non_guest_user(SimpleNamespace(role="user"))
    response = client.get("/research/ashare-outlook")
    assert response.status_code == 200
    assert response.json()["data"]["market_date"] == "2026-09-30"


def test_financing_windows_do_not_compress_missing_sessions():
    calendar = [f"2026-09-{i:02d}" for i in range(1, 8)]
    rows = [{"trade_date": day, "exchange": exchange, "financing_balance": 100,
             "financing_net_buy_amount": -2} for day in calendar for exchange in ("SSE", "SZSE")]
    rows = [r for r in rows if not (r["trade_date"] == calendar[-3] and r["exchange"] == "SZSE")]
    decision_calendar = calendar + ["2026-09-08"]
    result = strict_financing(rows, decision_calendar)
    assert result["source_date"] == calendar[-1]
    assert result["windows"][0]["net_buy_cny"] is None
    assert result["windows"][0]["missing_dates"] == [calendar[-3]]
    assert strict_financing(rows + [{**rows[0], "trade_date": "2027-01-01"}], decision_calendar) == result


def test_financing_t_minus_one_is_available_even_when_current_day_is_missing_or_complete():
    calendar = [f"2026-09-{i:02d}" for i in range(1, 26)]
    rows = [{"trade_date": day, "exchange": exchange, "financing_balance": 100,
             "financing_net_buy_amount": -2} for day in calendar[:-1] for exchange in ("SSE", "SZSE")]
    result = strict_financing(rows, calendar, "2026-09-25T22:30:00")
    assert result["source_date"] == "2026-09-24"
    assert result["reference_trade_date"] == "2026-09-25"
    assert result["lag_trade_days"] == 1
    assert not result["latest_target_missing"]
    assert result["status"] == "available_lagged"
    assert result["windows"][0]["net_buy_cny"] == -20
    assert result["windows"][1]["net_buy_cny"] == -80
    assert result["consecutive_windows_verified"]
    same_day = [{**rows[0], "trade_date": calendar[-1], "exchange": exchange,
                 "financing_net_buy_amount": 9999} for exchange in ("SSE", "SZSE")]
    assert strict_financing(rows + same_day, calendar, "2026-09-25T22:30:00") == result


def test_financing_uses_actual_sessions_across_weekends_and_national_holiday():
    calendar = ["2026-09-24", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-08"]
    rows = [{"trade_date": day, "exchange": exchange, "financing_balance": 100,
             "financing_net_buy_amount": -2} for day in calendar[:-1] for exchange in ("SSE", "SZSE")]
    result = strict_financing(rows, calendar, "2026-10-08T22:30:00")
    assert result["source_date"] == "2026-09-30"
    assert result["lag_trade_days"] == 1
    assert result["available_at"] == "2026-10-08T09:30:00"
    assert not result["latest_target_missing"]
    assert result["windows"][0]["net_buy_cny"] is None  # Insufficient samples, never pad.


def test_financing_previous_day_real_missing_or_unreleased_is_not_normal_lag():
    calendar = ["2026-09-28", "2026-09-29", "2026-09-30"]
    rows = [{"trade_date": day, "exchange": exchange, "financing_balance": 100,
             "financing_net_buy_amount": -2} for day in calendar for exchange in ("SSE", "SZSE")]
    missing = [r for r in rows if not (r["trade_date"] == "2026-09-29" and r["exchange"] == "SZSE")]
    result = strict_financing(missing, calendar, "2026-09-30T22:30:00")
    assert result["source_date"] == "2026-09-28"
    assert result["lag_trade_days"] == 2
    assert result["latest_target_missing"]
    assert result["status"] == "data_incomplete"
    late = [{**r, "available_at": "2026-10-01T01:00:00"} if r["trade_date"] == "2026-09-29" and r["exchange"] == "SZSE" else r for r in rows]
    assert strict_financing(late, calendar, "2026-09-30T22:30:00")["latest_target_missing"]
    assert not strict_financing(late, calendar, "2026-10-01T02:00:00")["latest_target_missing"]
    with pytest.raises(ValueError, match="reference date"):
        strict_financing(rows, calendar, "2026-09-29T22:30:00")
    assert strict_financing(rows, calendar, "2026-09-30T09:20:00")["latest_target_missing"]
    assert strict_financing([], calendar)["status"] == "data_incomplete"
    assert strict_financing(rows, calendar[:1])["source_date"] is None


def test_financing_t_minus_one_rejects_conflicts_and_does_not_relabel_source():
    calendar = ["2026-09-29", "2026-09-30"]
    rows = [{"trade_date": "2026-09-29", "exchange": e, "financing_balance": 100,
             "financing_net_buy_amount": -2} for e in ("SSE", "SZSE")]
    with pytest.raises(ValueError, match="Conflicting"):
        strict_financing(rows + [{**rows[0], "financing_balance": 999}], calendar)
    original = copy.deepcopy(rows)
    result = analysis.financing_summary(rows, calendar, "2026-09-30T22:30:00")
    assert rows == original
    assert result["source_date"] == "2026-09-29"
    assert not result["first_publication_times_verified"]


def test_global_refresh_uses_observed_availability_not_assumed_parser_time():
    payload = {"assets": {code: {"retrieved_at": "2026-10-04T20:00:00", "url": "https://example.test/nav",
                 "rows": [{"source_date": "2026-10-02", "close_value": 101,
                           "available_at": "2026-10-03T08:00:00"}]}
               for code in ("ACWI_NAV", "EFA_NAV", "EEM_NAV")}}
    brent = {"retrieved_at": "2026-10-04T20:01:00", "available_at": "2026-10-01T01:18:00",
             "url": "https://example.test/oil", "observations": [{"source_date": "2026-09-29", "close_value": 110}]}
    cutoff = "2026-10-04T21:00:00"
    result = refreshed_global_metrics(payload, brent, [], cutoff)
    assert result[0]["available_at"] == "2026-10-04T20:00:00"
    assert result[0]["change_20obs_pct"] is None
    assert not result[0]["first_publication_time_verified"]
    assert result[-1]["current_version_timestamp_verified"]
    with pytest.raises(ValueError, match="retrieved after"):
        refreshed_global_metrics(payload, brent, [], "2026-10-04T04:00:00")
    bad = copy.deepcopy(payload)
    bad["assets"]["ACWI_NAV"]["rows"].append({"source_date": "2026-10-02", "close_value": 102})
    with pytest.raises(ValueError, match="Conflicting"):
        refreshed_global_metrics(bad, brent, [], cutoff)
    bad["assets"]["ACWI_NAV"]["rows"] = [{"source_date": "2026-10-05", "close_value": 101}]
    with pytest.raises(ValueError, match="Invalid"):
        refreshed_global_metrics(bad, brent, [], cutoff)


def test_monthly_period_kind_basis_revision_and_cutoff_are_separate():
    baseline = {"series_key": "m1_yoy", "basis_version": "new", "period_kind": "monthly",
                "period_end": "2026-08-31", "value": 4.1, "available_at": "2026-09-14T17:00:00"}
    earlier = {**baseline, "period_end": "2026-05-31", "value": 5.5, "available_at": "2026-06-14T17:00:00"}
    future = {**baseline, "value": 9, "revision_number": 2, "available_at": "2026-10-05T00:00:00"}
    old_basis = {**earlier, "basis_version": "old", "value": 15}
    ytd = {**earlier, "period_kind": "ytd", "value": 20}
    rows = [baseline, earlier, old_basis, ytd]
    cutoff = "2026-10-04T04:00:00"
    assert visible_months(rows + [future], cutoff) == visible_months(rows, cutoff)
    assert monthly_change(visible_months(rows, cutoff), baseline, 3) == pytest.approx(-1.4)
    assert monthly_change(visible_months([baseline, old_basis, ytd], cutoff), baseline, 3) is None


def test_extended_windows_exclude_current_low_and_keep_incomplete_null():
    rows = history(25)
    rows[0]["low_price"] = 1
    values = forward(rows, rows[0]["trade_date"], 20)
    assert values["lowest_pct"] == pytest.approx((99.1 / 100 - 1) * 100)
    assert forward(rows, rows[0]["trade_date"], 60) == {"return_pct": None, "lowest_pct": None}


def test_valuation_identity_is_not_official_eps():
    result = valuation_parts(100, 90, 20, 15)
    assert result["implied_earnings_scale_change_pct"] == pytest.approx(20)
    assert (1 + result["pe_change_pct"] / 100) * (1 + result["implied_earnings_scale_change_pct"] / 100) == pytest.approx(.9)


def test_historical_panels_are_cutoff_stable_and_preserve_fixed_evidence():
    snap = {"as_of_at": "2026-10-04T04:00:00", "data": {"indexes": [
        {**r, "index_code": code} for code in analysis.NAMES for r in history()
    ]}}
    extra = {"stocks": []}
    baseline = compare(snap, extra)
    snap["data"]["indexes"].extend([{**r, "trade_date": "2027-01-01", "close_price": 1, "low_price": .5}
                                    for r in snap["data"]["indexes"][-5:]])
    assert compare(snap, extra) == baseline
    fixed = ResearchService().get_ashare_outlook()["history_comparison"]
    rows = {r["code"]: r for r in fixed["spring_2021"]["rows"]}
    assert rows["sh000300"]["spring_to_end_pct"] == pytest.approx(-14.9344321)
    assert rows["sh000852"]["spring_to_end_pct"] == pytest.approx(27.0811685)
    assert rows["600519"]["spring_to_march_pct"] == pytest.approx(-25.5290273)
    panels = {r["date"]: r for r in fixed["panels"]}
    assert panels["2021-03-09"]["above_ma250_count"] == 4
    assert panels["2020-03-23"]["above_ma250_count"] == 0
    assert panels["2026-09-30"]["rising_ma250_count"] == 5


def test_historical_period_missing_endpoints_are_not_silently_rebased():
    rows = prepared(history())
    value = period({"sh000985": rows}, rows[0]["trade_date"], "2030-01-01")[0]
    assert value["return_pct"] is None
    complete = period({"sh000985": rows}, rows[10]["trade_date"], rows[30]["trade_date"])[0]
    assert complete["return_pct"] == pytest.approx((103 / 101 - 1) * 100)


def test_historical_ma_uses_only_previous_and_current_sessions():
    rows = prepared(history())
    assert rows[249]["ma250"] == pytest.approx(sum(100 + i * .1 for i in range(250)) / 250)
    assert rows[268]["ma250_slope_20d_pct"] is None
    assert rows[269]["ma250_slope_20d_pct"] == pytest.approx((rows[269]["ma250"] / rows[249]["ma250"] - 1) * 100)


def test_v1_report_still_loads_without_new_history_fields(tmp_path, monkeypatch):
    payload = copy.deepcopy(ResearchService().get_ashare_outlook())
    payload.pop("history_comparison", None)
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(research_service, "ASHARE_OUTLOOK_REPORT_PATH", path)
    assert ResearchService().get_ashare_outlook()["market_date"] == "2026-09-30"


def test_ah_epoch_uses_hong_kong_session_not_utc_day():
    assert parse_ah({"indexCode": "01044.00", "indexLevels-5y": [[1790697600000, 124.53]]}) == [
        {"date": "2026-09-30", "value": 124.53}]
    with pytest.raises(ValueError, match="Invalid AH"):
        parse_ah({"indexCode": "01044.00", "indexLevels-5y": [[1790697600000, 0]]})
    with pytest.raises(ValueError, match="Wrong AH"):
        parse_ah({"indexCode": "other", "indexLevels-5y": []})


def test_etf_change_requires_every_session_and_never_uses_future_rows():
    calendar = [f"2026-09-{i:02d}" for i in range(1, 8)]
    rows = [{"code": "510300", "name": "ETF", "date": day, "shares_10k": 100+i} for i, day in enumerate(calendar)]
    baseline = etf_metrics({"rows": rows}, calendar, calendar[-1])
    assert baseline[0]["windows"][0]["delta_shares_10k"] == 5
    assert etf_metrics({"rows": rows + [{**rows[-1], "date": "2027-01-01", "shares_10k": 1}]}, calendar, calendar[-1]) == baseline
    missing = etf_metrics({"rows": rows[:3]+rows[4:]}, calendar, calendar[-1])
    assert missing[0]["windows"][0]["delta_shares_10k"] is None
    assert missing[0]["windows"][0]["missing_dates"] == [calendar[3]]
    with pytest.raises(ValueError, match="Invalid ETF"):
        etf_metrics({"rows": [{**rows[-1], "shares_10k": 0}]}, calendar, calendar[-1])


def test_policy_keeps_non_disclosed_gross_null_and_two_repo_lines_separate():
    base = {"period_end": "2026-08-31", "published_at": "2026-09-02T17:00:00", "coverage_status": "official_complete",
            "tool_type": "reverse_repo", "tool_name": "overnight / 7D", "injection_cny": 100,
            "withdrawal_cny": 150, "net_injection_cny": -50}
    other = {**base, "tool_name": "other term", "injection_cny": 70, "withdrawal_cny": 20, "net_injection_cny": 50}
    rrr = {**base, "tool_name": "reserve cut", "injection_cny": 20, "withdrawal_cny": None, "net_injection_cny": 20}
    result = policy_metrics([base, other, rrr], "2026-10-04T04:00:00")
    assert result[0]["net_cny"] == 20
    assert result[0]["line_count"] == 3
    assert result[0]["components"][-1]["withdrawal_cny"] is None
    assert policy_metrics([base, {**other, "published_at": "2027-01-01T00:00:00"}], "2026-10-04T04:00:00")[0]["net_cny"] == -50
    with pytest.raises(ValueError, match="Duplicate"):
        policy_metrics([base, base], "2026-10-04T04:00:00")
    with pytest.raises(ValueError, match="identity"):
        policy_metrics([{**base, "net_injection_cny": 0}], "2026-10-04T04:00:00")
