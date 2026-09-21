"""Daily index-only research, isolated from the approved strategy/task behavior."""

import json
import math
import os
import tempfile
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import text


REPORT_PATH = Path(__file__).resolve().parents[3] / "runtime/reports/market_regime/lightweight.json"
INDEXES = {"sh000985": "中证全指", "sh000300": "沪深300", "sh000905": "中证500", "sh000852": "中证1000"}
PROXY_CODES = ("sh000300", "sh000905", "sh000852")
MACRO_CORE = ("m1_yoy", "m2_yoy", "tsf_stock_yoy", "tsf_flow", "tsf_government_bond_flow",
              "loan_household_mlt", "loan_corporate_mlt", "pmi_manufacturing", "pmi_production",
              "pmi_new_orders", "pmi_nonmanufacturing", "cpi_yoy", "core_cpi_yoy", "ppi_yoy",
              "industrial_profit_ytd_yoy", "industrial_revenue_ytd_yoy")


def finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def month_number(period):
    return period.year * 12 + period.month


def select_macro(observations, as_of, *, strict=True):
    """One vintage per independent month/basis. Carried days never add samples."""
    candidates = {}
    for source in observations:
        if source["available_at"] > as_of:
            continue
        if strict and (not source["replay_eligible"] or source["replay_available_at"] > as_of):
            continue
        identity = (source["series_key"], source["period_end"], source["period_kind"], source["basis_version"])
        previous = candidates.get(identity)
        rank = (source["available_at"], source["first_seen_at"], source["release_id"])
        if previous is None or rank > (previous["available_at"], previous["first_seen_at"], previous["release_id"]):
            candidates[identity] = source
    groups = defaultdict(list)
    for identity, source in candidates.items():
        groups[(identity[0], identity[2], identity[3])].append(source)
    result = []
    for (key, kind, basis), rows in sorted(groups.items()):
        rows.sort(key=lambda r: r["period_end"])
        current = rows[-1]
        by_month = {month_number(r["period_end"]): r for r in rows}
        previous = by_month.get(month_number(current["period_end"]) - 3)
        value = finite(current["value"])
        window = [by_month.get(month_number(current["period_end"]) - n) for n in range(3)]
        # Legacy M1 remains accessible but is never mixed into the new-basis change.
        result.append({k: current.get(k) for k in (
            "series_key", "period_end", "period_kind", "basis_version", "unit", "source_url",
            "published_at", "available_at", "replay_available_at", "publication_precision",
            "vintage_status", "revision_number", "release_id") } | {
                "value": value, "independent_months": len(rows),
                "change_3m": value - float(previous["value"]) if previous else None,
                "mean_3m": sum(float(r["value"]) for r in window) / 3 if all(window) else None,
                "period_age_days": (as_of.date() - current["period_end"]).days,
                "revision": current["vintage_status"] == "observed_revision",
                "parser_correction": current["vintage_status"] == "parser_correction",
                "point_in_time_verified": strict,
            })
    return result


def macro_completeness(evidence):
    """A stale legacy row cannot satisfy current coverage; this is not a release forecast."""
    missing, stale = [], []
    for key in MACRO_CORE:
        rows = [r for r in evidence if r['series_key'] == key]
        if not rows:
            missing.append(key)
        elif min(r['period_age_days'] for r in rows) > 100:
            stale.append(key)
    return missing, stale


def observation_coverage(observations):
    groups = defaultdict(set)
    for r in observations:
        groups[(r['series_key'], r['period_kind'], r['basis_version'])].add(r['period_end'])
    result = []
    for (key, kind, basis), periods in sorted(groups.items()):
        first, last = min(periods), max(periods)
        start = month_number(date(2025, 1, 1)) if basis == 'm1_2025' else month_number(first)
        observed = {month_number(p) for p in periods}
        gaps, nonrelease = [], []
        for number in range(start, month_number(last) + 1):
            year, month = divmod(number - 1, 12)
            label = f'{year:04d}-{month + 1:02d}'
            if number not in observed:
                if key.startswith('industrial_') and month == 0:
                    nonrelease.append(label)
                else:
                    gaps.append(label)
        result.append(dict(series_key=key, period_kind=kind, basis_version=basis,
                           first_period=first, last_period=last, independent_months=len(periods),
                           missing_periods=gaps, scheduled_nonrelease_periods=nonrelease))
    return result


def macro_derived(evidence):
    latest = {}
    for row in evidence:
        if row["period_kind"] != "monthly":
            continue
        previous = latest.get(row["series_key"])
        if previous is None or row["period_end"] > previous["period_end"]:
            latest[row["series_key"]] = row
    result = []
    for key, left, right, kind, label in (
        ("m1_minus_m2_yoy", "m1_yoy", "m2_yoy", "monthly", "M1-M2同比增速差"),
        ("tsf_ex_government_flow", "tsf_flow", "tsf_government_bond_flow", "monthly", "剔除政府债券社融增量（派生，非私人部门信用）"),
    ):
        a, b = latest.get(left), latest.get(right)
        if a and b and a["period_end"] == b["period_end"] and a["period_kind"] == b["period_kind"] == kind:
            result.append({"series_key": key, "label": label, "period_end": a["period_end"],
                           "value": a["value"] - b["value"], "unit": "pp" if key.startswith("m1") else "CNY",
                           "basis_version": a["basis_version"], "derived": True,
                           "available_at": max(a["available_at"], b["available_at"])})
    return result


def index_features(rows):
    by_code = defaultdict(list)
    for row in rows:
        if row["index_code"] in INDEXES and finite(row["close_price"]) and float(row["close_price"]) > 0:
            by_code[row["index_code"]].append(row)
    features = {}
    for code, values in by_code.items():
        values = sorted({r["trade_date"]: r for r in values}.values(), key=lambda r: r["trade_date"])
        closes = [float(r["close_price"]) for r in values]
        prefix = [0.0]
        for close in closes:
            prefix.append(prefix[-1] + close)
        points = {}
        for i, row in enumerate(values):
            ma60 = (prefix[i + 1] - prefix[i - 59]) / 60 if i >= 59 else None
            ma120 = (prefix[i + 1] - prefix[i - 119]) / 120 if i >= 119 else None
            old_ma = (prefix[i - 19] - prefix[i - 139]) / 120 if i >= 139 else None
            slope = (ma120 / old_ma - 1) * 100 if old_ma else None
            trend = None if slope is None else closes[i] >= ma120 and slope > 0
            points[row["trade_date"]] = {"date": row["trade_date"], "close": closes[i],
                "ma60": ma60, "ma120": ma120, "ma120_change_20d_pct": slope,
                "above_ma60": closes[i] >= ma60 if ma60 else None,
                "above_ma120": closes[i] >= ma120 if ma120 else None,
                "trend_supportive": trend, "data_source": row.get("data_source")}
        features[code] = points
    main = []
    for day, point in sorted(features.get("sh000985", {}).items()):
        point = dict(point)
        missing = []
        for window in (60, 120):
            votes = [features.get(code, {}).get(day, {}).get(f"above_ma{window}") for code in PROXY_CODES]
            point[f"index_participation_ma{window}_pct"] = sum(votes) / 3 * 100 if all(v is not None for v in votes) else None
            if any(v is None for v in votes):
                missing.append(f"index_proxy_ma{window}_missing")
        point["adaptation"] = {code: features.get(code, {}).get(day) for code in ("sh000300", "sh000852")}
        point["missing_reasons"] = missing + (["main_trend_history_short"] if point["trend_supportive"] is None else [])
        point["trend_plus_participation"] = (point["trend_supportive"] and point["index_participation_ma120_pct"] >= 2 / 3 * 100) if not point["missing_reasons"] else None
        main.append(point)
    return main


def read_observations(db):
    return [dict(row) for row in db.execute(text("""SELECT o.*,r.source_url,r.published_at,r.available_at,
        GREATEST(r.replay_available_at,COALESCE(o.observed_at,r.first_seen_at)) AS replay_available_at,
        r.publication_precision,r.replay_eligible,r.vintage_status,
        r.revision_number,r.first_seen_at FROM cn_macro_observation o
        JOIN cn_macro_release r USING(release_id) ORDER BY o.period_end,r.available_at""")).mappings()]


def daily_context(db, target_date, as_of):
    """Read existing sources without claiming unversioned historical rows were known then."""
    evidence = []
    queries = (
        ("bank_liquidity", """SELECT trade_date,liquidity_tightness_score AS value,
            GREATEST(frr_available_at,chinabond_available_at,reverse_repo_7d_policy_available_at) AS available_at,
            fetched_at AS observed_at FROM cn_bank_liquidity_daily
            WHERE trade_date<=:day AND liquidity_tightness_score IS NOT NULL ORDER BY trade_date DESC LIMIT 1""", "points"),
        ("hs300_equity_bond_spread", """SELECT trade_date,hs300_equity_bond_spread_pp AS value,
            NULL AS available_at,updated_at AS observed_at FROM cn_macro_indicator_daily
            WHERE trade_date<=:day AND hs300_equity_bond_spread_pp IS NOT NULL ORDER BY trade_date DESC LIMIT 1""", "pp"),
        ("csi1000_equity_bond_spread", """SELECT trade_date,csi1000_equity_bond_spread_pp AS value,
            NULL AS available_at,updated_at AS observed_at FROM cn_macro_indicator_daily
            WHERE trade_date<=:day AND csi1000_equity_bond_spread_pp IS NOT NULL ORDER BY trade_date DESC LIMIT 1""", "pp"),
        ("financing_net_buy", """SELECT trade_date,SUM(financing_net_buy_amount) AS value,
            NULL AS available_at,MAX(updated_at) AS observed_at FROM margin_trading_daily_data
            WHERE trade_date<=:day AND exchange IN ('SSE','SZSE') GROUP BY trade_date
            HAVING COUNT(DISTINCT exchange)=2 AND COUNT(financing_net_buy_amount)=2
            ORDER BY trade_date DESC LIMIT 1""", "CNY"),
    )
    for key, query, unit in queries:
        row = db.execute(text(query), {"day": target_date}).mappings().first()
        if row:
            row = dict(row)
            # Existing unversioned tables are evidence, not certified historical predictors.
            known = all(row.get(k) is not None and row[k] <= as_of for k in ("available_at", "observed_at"))
            evidence.append({"series_key": key, **row, "value": finite(row["value"]), "unit": unit,
                             "point_in_time_verified": known, "role": "explanation_only"})
    for row in db.execute(text("""SELECT symbol_code,trade_date,latest_price,updated_at FROM forex_daily_data
        WHERE trade_date=(SELECT MAX(f.trade_date) FROM forex_daily_data f
            WHERE f.symbol_code=forex_daily_data.symbol_code AND f.trade_date<=:day)
        AND symbol_code IN ('UDI','USDCNY','USDCNH')"""), {"day": target_date}).mappings():
        evidence.append({"series_key": row["symbol_code"], "trade_date": row["trade_date"],
                         "value": finite(row["latest_price"]), "unit": "quote", "available_at": None,
                         "observed_at": row["updated_at"], "point_in_time_verified": False,
                         "role": "explanation_only"})
    return evidence


def build_snapshot(db, target_date, as_of=None):
    as_of = as_of or datetime.combine(target_date, time(22, 45))
    if as_of > datetime.now():
        raise ValueError("Cannot publish a snapshot with a future knowledge cutoff")
    rows = [dict(r) for r in db.execute(text("""SELECT index_code,trade_date,close_price,data_source
        FROM index_daily_data WHERE index_code IN ('sh000985','sh000300','sh000905','sh000852')
        AND trade_date<=:target ORDER BY index_code,trade_date"""), {"target": target_date}).mappings()]
    points = index_features(rows)
    if not points or points[-1]["date"] != target_date or points[-1]["missing_reasons"]:
        raise RuntimeError("Target-day official index series or warmup history is incomplete")
    observations = read_observations(db)
    evidence = select_macro(observations, as_of)
    archive_evidence = select_macro(observations, as_of, strict=False)
    missing, stale = macro_completeness(evidence)
    coverage = observation_coverage(observations)
    return {"schema_version": "market-regime-lightweight-v1", "research_only": True,
            "model_approved": False, "generated_at": datetime.now(), "as_of_at": as_of,
            "timezone": "Asia/Shanghai",
            "target_date": target_date, "latest": points[-1], "daily_points": points,
            "macro_evidence": evidence, "derived_evidence": macro_derived(evidence),
            "archive_macro_evidence": archive_evidence,
            "daily_context": daily_context(db, target_date, as_of),
            "coverage": coverage, "missing_macro": missing, "stale_macro": stale,
            "macro_complete": not (missing or stale),
            "notes": ["均线参与比例是沪深300/中证500/中证1000三指数代理，不是个股广度。",
                      "月度数据仅沿用已经公开并留存的版本；严格时点不早于首次抓取。",
                      "历史归档可展示，但未经当时版本核验的宏观历史不进入严格回测。",
                      "本快照不替换旧牛熊判定，不产生停买、交易或通知。",
                      "指数发布前的回溯行情只能作扩展研究，不能当成当时已存在的实时产品。"]}


def publish_snapshot(db, target_date, as_of=None, path=REPORT_PATH):
    report = build_snapshot(db, target_date, as_of)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, default=str, allow_nan=False)
    # Each cutoff is retained; the latest pointer never makes a failed run look current.
    archive = path.parent / "daily" / f"{target_date}-{report['as_of_at'].strftime('%Y%m%dT%H%M%S%f')}.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    try:
        with archive.open("x") as f:
            f.write(payload)
    except FileExistsError:
        pass
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".lightweight-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return report


def read_snapshot(start_date=None, end_date=None):
    if not REPORT_PATH.exists():
        return None
    try:
        report = json.loads(REPORT_PATH.read_text())
    except (OSError, ValueError):
        return None
    report["daily_points"] = [p for p in report["daily_points"]
                              if (start_date is None or p["date"] >= start_date.isoformat())
                              and (end_date is None or p["date"] <= end_date.isoformat())]
    report["latest"] = report["daily_points"][-1] if report["daily_points"] else None
    return report
