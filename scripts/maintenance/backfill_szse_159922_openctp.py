"""Recover original 159922 turnover from dated public OpenCTP snapshots.

Dry-run by default. Existing amounts and other original fields are never replaced.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.maintenance.backfill_szse_159922_turnover import (
    DAILY_FIELDS, OUT, START, decimal_value, turnover_coverage, values,
)

URL = "http://dict.openctp.cn/prices"
FIRST_SNAPSHOT = date(2026, 8, 26)


def snapshot_row(raw, info, day):
    if (info.get("exchange") != "SZSE" or info.get("underlying_code") != "159922"
            or raw.get("ExchangeID") != "SZSE"
            or str(raw.get("InstrumentID")) != str(info["contract_code"])
            or not str(raw.get("InstrumentName", "")).startswith("中证500ETF")):
        raise ValueError("Snapshot contract identity mismatch")
    if (str(raw.get("TradingDay")) != day or str(raw.get("UpdateDate")) != day
            or str(raw.get("UpdateTime", "")) < "15:00:00"
            or not str(info.get("listed_date", ""))[:10] <= day
            <= str(info.get("last_trade_date", ""))[:10]):
        raise ValueError("Snapshot is not the requested completed trading session")
    amount, volume = decimal_value(raw.get("Turnover")), decimal_value(raw.get("Volume"))
    if (amount is None or volume is None or volume != volume.to_integral_value()
            or (amount == 0) != (volume == 0)):
        raise ValueError("Missing or inconsistent original amount/volume")
    row = {key: info.get(key) for key in DAILY_FIELDS}
    row.update(trade_date=day, turnover=amount, volume=volume,
               data_source="openctp_dated_turnover_snapshot",
               source_url=URL + "?types=option&markets=SZSE&tradingday=" + day,
               raw_json={"turnover_snapshot": raw, "turnover_source": URL,
                         "turnover_fetched_at": datetime.now().isoformat()})
    for target, source in (("open_price", "OpenPrice"), ("high_price", "HighestPrice"),
                           ("low_price", "LowestPrice"), ("close_price", "ClosePrice")):
        # Zero-volume snapshots may carry old prices; do not manufacture an OHLC bar.
        row[target] = decimal_value(raw.get(source)) if volume > 0 else None
    if volume > 0 and any(row[key] is None or row[key] <= 0
                          for key in ("open_price", "high_price", "low_price", "close_price")):
        raise ValueError("Positive-volume session lacks valid original prices")
    return row


def fetch(day):
    import requests
    folder = OUT / "openctp"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (day + ".json")
    if path.exists():
        content = path.read_bytes()
    else:
        response = requests.get(URL, params={"types": "option", "markets": "SZSE",
                                             "tradingday": day}, timeout=45)
        response.raise_for_status()
        content = response.content
        payload = json.loads(content, parse_float=Decimal)
        if payload.get("rsp_code") != 0 or not isinstance(payload.get("data"), list):
            raise ValueError("OpenCTP did not return a successful snapshot")
        if not payload["data"]:
            raise ValueError("Public source has no snapshot for " + day)
        path.write_bytes(content)
        time.sleep(0.5)
    payload = json.loads(content, parse_float=Decimal)
    if payload.get("rsp_code") != 0 or not isinstance(payload.get("data"), list):
        raise ValueError("Invalid cached snapshot")
    return payload["data"]


def plan_rows(snapshots, infos, existing):
    planned, compared = [], 0
    seen = set()
    for day, source_rows in snapshots.items():
        for raw in source_rows:
            code = str(raw.get("InstrumentID"))
            if not str(raw.get("InstrumentName", "")).startswith("中证500ETF"):
                continue
            if code not in infos:
                raise ValueError("Snapshot contract is absent from official metadata: " + code)
            key = (code, day)
            if key in seen:
                raise ValueError("Duplicate snapshot contract")
            seen.add(key)
            row = snapshot_row(raw, infos[code], day)
            old = existing.get(key)
            if old is not None and old.get("turnover") is not None:
                if decimal_value(old["turnover"]) != row["turnover"]:
                    raise ValueError("Existing original turnover disagrees: " + str(key))
                compared += 1
            else:
                planned.append(row)
    return planned, compared


def dashboard_payload(payload, coverage):
    payload = json.loads(payload) if isinstance(payload, str) else payload or {}
    source = payload.setdefault("szse:159922", {
        "exchange": "SZSE", "source_key": "szse:159922", "product_code": "159922",
        "product_name": "中证500ETF期权", "exchange_label": "深交所",
    })
    old_ratio = source.get("option_turnover_pc_ratio")
    if not coverage["complete"] and old_ratio is not None:
        source.setdefault("unverified_partial_turnover_pc_ratio", old_ratio)
    source["option_turnover_pc_ratio"] = coverage["option_turnover_pc_ratio"]
    source["turnover_coverage"] = {
        **coverage, "source_date": coverage["trade_date"],
        "source_urls": [URL, "https://www.szse.cn/api/market/ssjjhq/getHistoryData"],
        "missing_reason": None if coverage["complete"]
        else "Full original contract turnover is incomplete",
    }
    return json.dumps(payload, ensure_ascii=False)


async def run(args):
    if args.start < FIRST_SNAPSHOT or args.end < args.start:
        raise ValueError("Dated archive begins 2026-08-26; earlier history is not available")
    sys.path.insert(0, str(ROOT.parent / "akshareProkect/src"))
    import aiomysql
    from akshare_project.db.db_tool import DbTools

    infos_list = json.loads((OUT / "official_contracts.json").read_text())
    infos = {str(row["contract_code"]): row for row in infos_list}
    db = DbTools()
    await db.init_pool()
    try:
        async with db.pool.acquire() as lock_conn:
            async with lock_conn.cursor() as cursor:
                await cursor.execute("SELECT GET_LOCK('fit:backfill:szse:159922:turnover',0)")
                if (await cursor.fetchone())[0] != 1:
                    raise RuntimeError("Another turnover backfill is running")
            try:
                await collect(db, aiomysql, infos_list, infos, args)
            finally:
                async with lock_conn.cursor() as cursor:
                    await cursor.execute("SELECT RELEASE_LOCK('fit:backfill:szse:159922:turnover')")
    finally:
        await db.close()


async def collect(db, aiomysql, infos_list, infos, args):
    calendar = [str(day)[:10] for day in await db.list_cn_trade_dates(
        START.isoformat(), args.end.isoformat())]
    if args.end.isoformat() not in calendar:
        raise ValueError("End date is absent from the real A-share calendar")
    async with db.pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT contract_code,trade_date,turnover,raw_json "
                                 "FROM option_exchange_contract_daily_data "
                                 "WHERE exchange='SZSE' AND underlying_code='159922'")
            records = list(await cursor.fetchall())
    existing = {(str(row["contract_code"]), str(row["trade_date"])[:10]): row for row in records}
    snapshots = {}
    for day in calendar:
        if day < args.start.isoformat():
            continue
        snapshots[day] = await asyncio.to_thread(fetch, day)
        print("SNAPSHOT", day, len(snapshots[day]), flush=True)
    planned, compared = plan_rows(snapshots, infos, existing)
    latest = args.end.isoformat()
    control = [raw for raw in snapshots[latest]
               if str(raw.get("InstrumentName", "")).startswith("中证500ETF")]
    # Require a broad, independently persisted official control day before any writes.
    if len(control) < 20 or any((str(raw["InstrumentID"]), latest) not in existing
            or decimal_value(existing[(str(raw["InstrumentID"]), latest)].get("turnover"))
            != decimal_value(raw.get("Turnover")) for raw in control):
        raise ValueError("Latest complete official control day is missing or disagrees")
    before = sum(row.get("turnover") is not None for row in records)
    report = {"source": URL, "start_date": args.start, "end_date": args.end,
              "apply": args.apply, "official_control_contracts": len(control),
              "equal_existing_amounts": compared, "planned_amount_rows": len(planned),
              "amount_rows_before": before, "full_historical_backfill_complete": False}
    if args.apply:
        insert_sql = ("INSERT IGNORE INTO option_exchange_contract_daily_data ("
                      + ",".join("`" + field + "`" for field in DAILY_FIELDS) + ") VALUES ("
                      + ",".join(["%s"] * len(DAILY_FIELDS)) + ")")
        async with db.pool.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    for row in planned:
                        key = (row["contract_code"], row["trade_date"])
                        old = existing.get(key)
                        if old is None:
                            await cursor.execute(insert_sql, values(row, DAILY_FIELDS))
                        else:
                            raw = old.get("raw_json")
                            raw = json.loads(raw) if isinstance(raw, str) else raw
                            if not isinstance(raw, dict):
                                raw = {"prior_raw_json": raw}
                            raw.update(row["raw_json"])
                            await cursor.execute("UPDATE option_exchange_contract_daily_data "
                                "SET turnover=%s,raw_json=%s WHERE exchange='SZSE' "
                                "AND underlying_code='159922' AND contract_code=%s "
                                "AND trade_date=%s AND turnover IS NULL",
                                (row["turnover"], json.dumps(raw, ensure_ascii=False, default=str), *key))
                    await cursor.execute("SELECT COUNT(*) FROM option_exchange_contract_daily_data "
                        "WHERE exchange='SZSE' AND underlying_code='159922' AND turnover IS NOT NULL")
                    after = (await cursor.fetchone())[0]
                    if after - before != len(planned):
                        raise RuntimeError("Persisted amount count differs; rolling back")
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        report["amount_rows_after"] = after
    for row in planned:
        existing[(row["contract_code"], row["trade_date"])] = row
    bydate = {}
    for (_, day), row in existing.items():
        bydate.setdefault(day, []).append(row)
    coverage = [{"trade_date": day, **turnover_coverage(day, infos_list, bydate.get(day, []))}
                for day in calendar]
    if args.apply:
        byday = {row["trade_date"]: row for row in coverage}
        async with db.pool.acquire() as conn:
            try:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute("SELECT trade_date,exchange_option_pc_json "
                        "FROM quant_index_dashboard_daily WHERE index_code='sh000905' "
                        "AND trade_date BETWEEN %s AND %s FOR UPDATE", (args.start, args.end))
                    dashboards = await cursor.fetchall()
                    updates = [(dashboard_payload(row["exchange_option_pc_json"],
                                byday[str(row["trade_date"])[:10]]), row["trade_date"])
                               for row in dashboards]
                    if updates:
                        await cursor.executemany("UPDATE quant_index_dashboard_daily "
                            "SET exchange_option_pc_json=%s WHERE index_code='sh000905' AND trade_date=%s",
                            updates)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        report["dashboard_days_refreshed"] = len(updates)
        (OUT / "coverage.json").write_text(
            json.dumps(coverage, ensure_ascii=False, default=str, indent=2) + "\n")
    complete = [row["trade_date"] for row in coverage if row["option_turnover_pc_ratio"] is not None]
    report.update(complete_days=len(complete), complete_dates=complete,
                  finished_at=datetime.now().isoformat())
    (OUT / "openctp" / ("applied.json" if args.apply else "dry_run.json")).write_text(
        json.dumps(report, ensure_ascii=False, default=str, indent=2) + "\n")
    (OUT / "openctp" / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, default=str, indent=2) + "\n")
    print("SUMMARY", json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=FIRST_SNAPSHOT)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))
