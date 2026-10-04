"""Backfill original SZSE 159922 amounts and audit full-chain P/C coverage.

Run with the akshareProkect Python environment. No services are restarted.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runtime/backfill/szse_159922_turnover"
PRODUCT = "159922"
START = date(2022, 9, 19)


def decimal_value(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() and result >= 0 else None


def valid_history(rows, info, end, calendar):
    if info.get("underlying_code") != PRODUCT or info.get("exchange") != "SZSE":
        raise ValueError("Only SZSE 159922 is allowed")
    listed, expires = info.get("listed_date"), info.get("last_trade_date")
    if not listed or not expires:
        raise ValueError("Official listing/expiry dates are required")
    listed, expires = str(listed)[:10], str(expires)[:10]
    result = []
    for row in rows:
        day = str(row["trade_date"])[:10]
        if not listed <= day <= expires or day not in calendar:
            raise ValueError(f"Unexpected source date: {info['contract_code']} {day}")
        if day > end.isoformat() or day < START.isoformat():
            continue
        if row.get("exchange") != "SZSE" or str(row.get("contract_code")) != str(info["contract_code"]):
            raise ValueError("Source contract mismatch")
        amount, volume = decimal_value(row.get("turnover")), decimal_value(row.get("volume"))
        if amount is None or volume is None or (volume > 0 and amount == 0):
            raise ValueError(f"Missing/invalid original amount: {info['contract_code']} {day}")
        result.append({**row, "turnover": amount, "volume": volume})
    return result


def turnover_coverage(day, contracts, records):
    # Match the existing dashboard's exclusion of the expiry trading day.
    expected = {str(c["contract_code"]): c for c in contracts
                if c.get("listed_date") and c.get("last_trade_date")
                and str(c["listed_date"])[:10] <= day < str(c["last_trade_date"])[:10]}
    actual = {str(r["contract_code"]): r for r in records}
    missing_rows, missing_amounts = [], []
    sums = {"CALL": Decimal(0), "PUT": Decimal(0)}
    types = set()
    for code, info in expected.items():
        if code not in actual:
            missing_rows.append(code)
            continue
        amount = decimal_value(actual[code].get("turnover"))
        if amount is None:
            missing_amounts.append(code)
            continue
        kind = str(info.get("option_type") or "").upper()
        if kind not in sums:
            raise ValueError("Invalid official option type")
        sums[kind] += amount
        types.add(kind)
    complete = bool(expected) and not missing_rows and not missing_amounts and types == {"CALL", "PUT"}
    ratio = float(sums["PUT"] / sums["CALL"]) if complete and sums["CALL"] > 0 else None
    return {"complete": complete, "expected_contracts": len(expected),
            "present_contracts": len(expected.keys() & actual.keys()),
            "missing_contracts": missing_rows, "missing_turnover_contracts": missing_amounts,
            "call_turnover_yuan": str(sums["CALL"]) if complete else None,
            "put_turnover_yuan": str(sums["PUT"]) if complete else None,
            "option_turnover_pc_ratio": ratio}


def official_zero_trade_row(payload, info, day):
    data = payload.get("data") or {}
    minutes = data.get("picupdata") or []
    if (str(payload.get("code")) != "0"
            or str(data.get("marketTime") or "") != day + " 15:00:00"
            or data.get("code") != info.get("contract_trade_code")
            or decimal_value(data.get("amount")) != 0
            or len(minutes) < 220
            or not all(len(m) >= 7 and decimal_value(m[5]) == 0
                       and decimal_value(m[6]) == 0 for m in minutes)):
        return None
    # No-trade sessions are omitted by the daily chart. The official full-session
    # minute response proves zero turnover; it does not provide a new closing price.
    return {**info, "trade_date": day, "volume": Decimal(0), "turnover": Decimal(0),
            "data_source": "szse_official_no_trade_session",
            "source_url": "https://www.szse.cn/api/market/ssjjhq/getTimeData",
            "raw_json": payload}


INFO_FIELDS = ("exchange", "contract_code", "contract_trade_code", "contract_name", "underlying_code",
               "underlying_name", "option_type", "contract_month", "strike_price", "contract_unit",
               "listed_date", "last_trade_date", "exercise_date", "expire_date", "delivery_date",
               "data_source", "source_url", "raw_json")
DAILY_FIELDS = ("exchange", "contract_code", "contract_trade_code", "contract_name", "underlying_code",
                "underlying_name", "option_type", "contract_month", "strike_price", "trade_date",
                "open_price", "high_price", "low_price", "close_price", "volume", "turnover",
                "data_source", "source_url", "raw_json")


def upsert_sql(table, fields):
    update = ",".join(f"`{f}`=COALESCE(VALUES(`{f}`),`{f}`)" for f in fields
                      if f not in {"exchange", "contract_code", "trade_date"})
    return (f"INSERT INTO `{table}` (" + ",".join(f"`{f}`" for f in fields) + ") VALUES ("
            + ",".join(["%s"] * len(fields)) + ") ON DUPLICATE KEY UPDATE " + update)


def values(row, fields):
    return tuple(json.dumps(row.get(f), ensure_ascii=False, default=str) if f == "raw_json"
                 and isinstance(row.get(f), (dict, list)) else row.get(f) for f in fields)


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, default=str, indent=2) + "\n", encoding="utf-8")


async def run(args):
    sys.path.insert(0, str(ROOT.parent / "akshareProkect/src"))
    import aiomysql
    from akshare_project.collectors.exchange_option import (
        fetch_official_history_sync, fetch_szse_all_contract_info_sync, fetch_szse_risk_rows_sync,
    )
    from akshare_project.db.db_tool import DbTools

    db = DbTools()
    await db.init_pool()
    try:
        async with db.pool.acquire() as lock_conn:
            async with lock_conn.cursor() as cursor:
                await cursor.execute("SELECT GET_LOCK('fit:backfill:szse:159922:turnover',0)")
                if (await cursor.fetchone())[0] != 1:
                    raise RuntimeError("A 159922 turnover backfill is already running")
            try:
                await collect(db, args, aiomysql, fetch_official_history_sync,
                              fetch_szse_all_contract_info_sync, fetch_szse_risk_rows_sync)
            finally:
                async with lock_conn.cursor() as cursor:
                    await cursor.execute("SELECT RELEASE_LOCK('fit:backfill:szse:159922:turnover')")
    finally:
        await db.close()


async def collect(db, args, aiomysql, fetch_history, fetch_info, fetch_risk):
    print("Downloading official contract metadata", flush=True)
    infos = [r for r in await asyncio.to_thread(fetch_info) if r.get("underlying_code") == PRODUCT]
    if not infos:
        raise RuntimeError("No official 159922 contract metadata")
    save("official_contracts.json", infos)
    active = [r for r in infos if r.get("listed_date") and r.get("last_trade_date")
              and str(r["listed_date"])[:10] <= args.end.isoformat() <= str(r["last_trade_date"])[:10]]
    official_today = [r for r in await asyncio.to_thread(fetch_risk, args.end.isoformat())
                      if r.get("underlying_code") == PRODUCT]
    if {r["contract_code"] for r in active} != {r["contract_code"] for r in official_today}:
        raise RuntimeError("Full contract metadata disagrees with the target-day official risk report")
    save("official_target_contracts.json", official_today)
    calendar = {str(d)[:10] for d in await db.list_cn_trade_dates(START.isoformat(), args.end.isoformat())}
    if args.end.isoformat() not in calendar:
        raise RuntimeError("Target date is absent from the real trading calendar")
    async with db.pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.executemany(upsert_sql("option_exchange_contract_info", INFO_FIELDS),
                                     [values(r, INFO_FIELDS) for r in infos])
        await conn.commit()
    report = {"end_date": args.end.isoformat(), "original_amount_unit": "CNY",
              "official_contract_count": len(infos), "active_contract_count": len(active),
              "contracts": [], "full_historical_backfill_complete": False}
    cache = OUT / "contracts"
    cache.mkdir(parents=True, exist_ok=True)
    # Samples prove whether expired contracts are still publicly available.
    probes = [min((r for r in infos if str(r.get("last_trade_date"))[:4] == str(y)),
                  key=lambda r: r["contract_code"], default=None) for y in range(2022, 2027)]
    candidates = {r["contract_code"]: r for r in [*active, *probes] if r}
    for i, info in enumerate(candidates.values(), 1):
        code = str(info["contract_code"])
        path = cache / f"{code}-{args.end}.json"
        try:
            if path.exists():
                source_rows = json.loads(path.read_text())
            else:
                source_rows = await asyncio.to_thread(fetch_history, "SZSE", code)
                if source_rows:
                    path.write_text(json.dumps(source_rows, ensure_ascii=False, default=str), encoding="utf-8")
                await asyncio.sleep(2)
            rows = valid_history(source_rows, info, args.end, calendar)
            merged = [{**{f: info.get(f) for f in DAILY_FIELDS}, **r} for r in rows]
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    if merged:
                        await cursor.executemany(upsert_sql("option_exchange_contract_daily_data", DAILY_FIELDS),
                                                 [values(r, DAILY_FIELDS) for r in merged])
                await conn.commit()
            status = {"contract_code": code, "status": "persisted" if rows else "source_empty",
                      "rows": len(rows), "first_date": rows[0]["trade_date"] if rows else None,
                      "last_date": rows[-1]["trade_date"] if rows else None}
        except Exception as exc:
            status = {"contract_code": code, "status": "failed", "error": str(exc)}
        report["contracts"].append(status)
        save("progress.json", report)
        print(f"{i}/{len(candidates)} {status}", flush=True)
    async with db.pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT contract_code,trade_date,turnover FROM option_exchange_contract_daily_data "
                                 "WHERE exchange='SZSE' AND underlying_code='159922' ORDER BY trade_date")
            raw = await cursor.fetchall()
            await cursor.execute("SELECT trade_date,exchange_option_pc_json FROM quant_index_dashboard_daily "
                                 "WHERE index_code='sh000905' AND trade_date>=%s ORDER BY trade_date", (START,))
            dashboard = await cursor.fetchall()
    bydate = {}
    for row in raw:
        bydate.setdefault(str(row["trade_date"])[:10], []).append(row)
    target_day = args.end.isoformat()
    missing = turnover_coverage(target_day, infos, bydate.get(target_day, []))["missing_contracts"]
    info_bycode = {str(r["contract_code"]): r for r in infos}
    import requests
    zero_rows = []
    for code in missing:
        response = await asyncio.to_thread(requests.get,
            "https://www.szse.cn/api/market/ssjjhq/getTimeData",
            params={"marketId": "70", "moduleType": "realoption", "code": code}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        save(f"target_quote_{code}.json", payload)
        row = official_zero_trade_row(payload, info_bycode[code], target_day)
        if row:
            zero_rows.append(row)
            bydate.setdefault(target_day, []).append(row)
        await asyncio.sleep(1)
    if zero_rows:
        async with db.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(upsert_sql("option_exchange_contract_daily_data", DAILY_FIELDS),
                    [values(r, DAILY_FIELDS) for r in zero_rows])
            await conn.commit()
    report["official_zero_trade_sessions"] = len(zero_rows)
    if not (OUT / "dashboard_before.json").exists():
        save("dashboard_before.json", dashboard)
    audit = [{"trade_date": day, **turnover_coverage(day, infos, bydate.get(day, []))}
             for day in sorted(calendar)]
    coverage_bydate = {r["trade_date"]: r for r in audit}
    updates = []
    for row in dashboard:
        day = str(row["trade_date"])[:10]
        if day > args.end.isoformat():
            continue
        coverage = coverage_bydate[day]
        payload = row["exchange_option_pc_json"]
        payload = json.loads(payload) if isinstance(payload, str) else payload or {}
        source = payload.get("szse:159922")
        if not isinstance(source, dict):
            source = {"exchange": "SZSE", "source_key": "szse:159922", "product_code": PRODUCT,
                      "product_name": "中证500ETF期权", "exchange_label": "深交所"}
            payload["szse:159922"] = source
        old_ratio = source.get("option_turnover_pc_ratio")
        if not coverage["complete"] and old_ratio is not None:
            source.setdefault("unverified_partial_turnover_pc_ratio", old_ratio)
        source["option_turnover_pc_ratio"] = coverage["option_turnover_pc_ratio"]
        source["turnover_coverage"] = {**coverage, "source_date": day,
            "source_url": "http://www.szse.cn/api/market/ssjjhq/getHistoryData",
            "missing_reason": None if coverage["complete"] else "Full official contract turnover is incomplete"}
        updates.append((json.dumps(payload, ensure_ascii=False), day))
    save("coverage.json", audit)
    async with db.pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.executemany("UPDATE quant_index_dashboard_daily SET exchange_option_pc_json=%s "
                                     "WHERE index_code='sh000905' AND trade_date=%s", updates)
        await conn.commit()
    complete = [r["trade_date"] for r in audit if r["option_turnover_pc_ratio"] is not None]
    report.update(complete_days=len(complete), first_complete_day=min(complete) if complete else None,
                  last_complete_day=max(complete) if complete else None,
                  source_rows_processed=sum(r.get("rows", 0) for r in report["contracts"]),
                  target_coverage=next((r for r in audit if r["trade_date"] == args.end.isoformat()), None),
                  finished_at=datetime.now().isoformat())
    save("progress.json", report)
    print("SUMMARY", json.dumps({k: v for k, v in report.items() if k != "contracts"}, ensure_ascii=False), flush=True)
    if any(r["status"] == "failed" for r in report["contracts"]):
        raise RuntimeError("Some contract requests failed; completed contracts are resumable")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    asyncio.run(run(parser.parse_args()))
