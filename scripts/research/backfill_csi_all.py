"""Fill only missing CSI All Share sessions using the existing official collector."""

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

FIT = Path(__file__).resolve().parents[2]
AK = FIT.parent / "akshareProkect"
sys.path.insert(0, str(FIT / "backend"))
sys.path.insert(0, str(AK / "src"))
from app.db.session import SessionLocal
from akshare_project.collectors.global_risk import build_csi_tech_index_rows, fetch_csi_index_perf
from akshare_project.db.db_tool import DbTools


def inventory():
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        dates = set(db.execute(text("SELECT trade_date FROM index_daily_data "
             "WHERE index_code='sh000001' AND trade_date>='2005-01-04' "
             "AND trade_date<=:today"), {"today": date.today()}).scalars())
        rows = [dict(r) for r in db.execute(text("SELECT trade_date,open_price,high_price,"
             "low_price,close_price,turnover,data_source FROM index_daily_data "
             "WHERE index_code='sh000985' ORDER BY trade_date")).mappings()]
    present = {r["trade_date"] for r in rows}
    return sorted(dates - present), rows


async def main():
    missing, before = inventory()
    out = FIT / "runtime/research/market-regime-20260906"
    out.mkdir(parents=True, exist_ok=True)
    audit = {"missing_before": missing, "before_count": len(before),
             "before_latest": before[-1]["trade_date"]}
    print(json.dumps(audit, default=str), flush=True)
    if missing:
        raw = await asyncio.to_thread(fetch_csi_index_perf, "000985", min(missing), max(missing))
        (out / "csi-all-official-response.json").write_text(json.dumps(raw, default=str), encoding="utf-8")
        parsed = build_csi_tech_index_rows(raw, "000985", "sh000985")
        target = {d.isoformat() for d in missing}
        rows = [r for r in parsed if r["trade_date"] in target]
        unavailable = target - {r["trade_date"] for r in rows}
        if unavailable:
            raise RuntimeError(f"Official source missing requested dates: {sorted(unavailable)}")
        for row in rows:
            op, hi, lo, cl = [row[k] for k in ("open_price", "high_price", "low_price", "close_price")]
            if None in (op, hi, lo, cl) or not 0 < lo <= min(op, cl) <= max(op, cl) <= hi:
                raise ValueError(f"Invalid official OHLC: {row}")
        db = DbTools()
        await db.init_pool()
        try:
            audit["affected"] = await db.upsert_index_daily_data(rows)
        finally:
            await db.close()
        audit["inserted_rows"] = rows
    remaining, after = inventory()
    after_by_date = {r["trade_date"]: r for r in after}
    assert all(r == after_by_date[r["trade_date"]] for r in before), "Existing values changed"
    audit.update(missing_after=remaining, after_count=len(after), after_latest=after[-1],
                 existing_rows_unchanged=True)
    (out / "csi-all-backfill-audit.json").write_text(json.dumps(audit, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, default=str, indent=2), flush=True)
    assert not remaining


if __name__ == "__main__":
    asyncio.run(main())
