"""Read-only, bounded SQL export. Compute raw-price breadth offline in resumable batches."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal
from market_regime import stock_breadth_parts


def fetch(sql, params=None):
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text("SET SESSION MAX_EXECUTION_TIME=30000"))
        return [dict(r) for r in db.execute(text(sql), params or {}).mappings()]


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")


def extend_hfq_breadth(total, calendar, out):
    # Calculate each source's moving averages independently, then join aggregates.
    cutoff = "2026-03-13"
    following = calendar[calendar > cutoff]
    if following.empty:
        return total, []
    first = calendar.get_loc(following[0])
    warmup = str(calendar[max(0, first - 119)])
    end = str(calendar[-1])
    codes = fetch("SELECT DISTINCT stock_code FROM stock_hfq_daily_data "
                  "WHERE trade_date>=:start AND trade_date<=:end ORDER BY stock_code",
                  {"start": following[0], "end": end})
    if not codes:
        raise ValueError("No current adjusted history available")
    extension = None
    audit = []
    for start in range(0, len(codes), 80):
        subset = [row["stock_code"] for row in codes[start:start + 80]]
        placeholders = ",".join(f":c{i}" for i in range(len(subset)))
        rows = fetch("SELECT stock_code AS prefixed_code,trade_date,close_price,volume,data_source "
                     f"FROM stock_hfq_daily_data WHERE stock_code IN ({placeholders}) "
                     "AND trade_date>=:warmup AND trade_date<=:end ORDER BY stock_code,trade_date",
                     {**{f"c{i}": code for i, code in enumerate(subset)}, "warmup": warmup, "end": end})
        frame = pd.DataFrame(rows)
        if frame.empty:
            continue
        frame["trade_date"] = frame.trade_date.astype(str)
        part = stock_breadth_parts(frame, calendar[calendar >= warmup])
        extension = part if extension is None else extension.add(part, fill_value=0)
        audit.append({"codes": subset, "rows": len(rows), "sources": frame.data_source.value_counts().to_dict(),
                      "first": frame.trade_date.min(), "last": frame.trade_date.max()})
        print("current hfq breadth", min(start + 80, len(codes)), "/", len(codes), flush=True)
    if extension is None:
        raise ValueError("No adjusted prices returned")
    dates = extension.index[(extension.index > cutoff) & extension.observed.gt(0)]
    if dates.empty:
        raise ValueError("No adjusted observations after legacy cutoff")
    replace = extension.index[extension.index > cutoff]
    total.loc[replace, extension.columns] = extension.loc[replace]
    extension.to_csv(out / "breadth-hfq-extension.csv", index_label="date")
    save(out / "breadth-hfq-extension-audit.json", {"warmup_start": warmup, "batches": audit})
    return total, [{"table": "stock_hfq_daily_data", "start": dates[0], "end": dates[-1],
                    "note": "真实后复权日线，单独预热120日；未获取的股票不填价格，覆盖率按日保留。"}]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--breadth", action="store_true")
    parser.add_argument("--legacy-hfq", action="store_true")
    parser.add_argument("--refresh-hfq", action="store_true", help="Extend legacy aggregates with current adjusted history")
    args = parser.parse_args()
    if args.refresh_hfq and not (args.legacy_hfq and args.breadth):
        parser.error("--refresh-hfq requires --breadth --legacy-hfq")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    for code in ("sh000001", "sh000300", "sh000852", "sh000985", "sz399106"):
        rows = fetch("SELECT trade_date AS date,open_price AS open,close_price AS close,"
                     "high_price AS high,low_price AS low,data_source FROM index_daily_data "
                     "WHERE index_code=:code AND trade_date>='2004-01-01' ORDER BY trade_date", {"code": code})
        save(out / f"{code}.json", rows)
        print(code, len(rows), rows[0]["date"], rows[-1]["date"], flush=True)
    save(out / "liquidity.json", fetch("SELECT trade_date,liquidity_tightness_score,"
         "factor_fdr007_policy_spread_bp,frr_available_at,chinabond_available_at "
         "FROM cn_bank_liquidity_daily ORDER BY trade_date"))
    save(out / "risk.json", fetch("SELECT trade_date,risk_global_shock,risk_global_leading,"
         "risk_as_of_at,risk_decision_trade_date FROM quant_index_dashboard_daily "
         "WHERE index_code='sh000852' ORDER BY trade_date"))
    if not args.breadth:
        return
    calendar = pd.Index([str(r["date"]) for r in json.loads((out / "sh000001.json").read_text())])
    codes_path = out / ("codes-legacy.json" if args.legacy_hfq else "codes.json")
    if not codes_path.exists():
        query = ("SELECT DISTINCT stock_code AS prefixed_code FROM stock_data ORDER BY stock_code"
                 if args.legacy_hfq else "SELECT DISTINCT prefixed_code FROM stock_daily_data ORDER BY prefixed_code")
        save(codes_path, fetch(query))
    codes = [r["prefixed_code"] for r in json.loads(codes_path.read_text())
             if r["prefixed_code"] and r["prefixed_code"].startswith(
                 ("60", "68", "00", "30", "43", "83", "87", "92") if args.legacy_hfq
                 else ("sh60", "sh68", "sz00", "sz30", "bj"))]
    batches = out / ("breadth-legacy-batches" if args.legacy_hfq else "breadth-batches")
    batches.mkdir(exist_ok=True)
    for start in range(0, len(codes), 80):
        subset = codes[start:start + 80]
        fingerprint = hashlib.sha256("|".join(subset).encode()).hexdigest()[:10]
        dest = batches / f"{start:05d}-{fingerprint}.csv"
        if dest.exists():
            continue
        placeholders = ",".join(f":c{i}" for i in range(len(subset)))
        sql = ("SELECT stock_code AS prefixed_code,date AS trade_date,close_price,volume,"
               "'legacy_akshare_hfq' AS data_source FROM stock_data "
               f"WHERE stock_code IN ({placeholders}) AND date>='2004-01-01' "
               "AND date<='2026-03-13' ORDER BY stock_code,date" if args.legacy_hfq else
               "SELECT prefixed_code,trade_date,close_price,volume,data_source "
                     f"FROM stock_daily_data WHERE prefixed_code IN ({placeholders}) "
                     "AND trade_date>='2004-01-01' AND trade_date<='2026-09-04' "
                     "ORDER BY prefixed_code,trade_date")
        rows = fetch(sql, {f"c{i}": c for i, c in enumerate(subset)})
        frame = pd.DataFrame(rows)
        if frame.empty:
            continue
        frame["trade_date"] = frame.trade_date.astype(str)
        parts = stock_breadth_parts(frame, calendar)
        parts.to_csv(dest, index_label="date")
        save(dest.with_suffix(".json"), {"codes": subset, "rows": len(rows),
             "sources": frame.data_source.value_counts().to_dict(),
             "first": frame.trade_date.min(), "last": frame.trade_date.max()})
        print("breadth", min(start + 80, len(codes)), "/", len(codes), "rows", len(rows), flush=True)
        time.sleep(.15)
    total = None
    for file in sorted(batches.glob("*.csv")):
        part = pd.read_csv(file, index_col="date")
        total = part if total is None else total.add(part, fill_value=0)
    if total is None:
        raise ValueError("No breadth batches available")
    total = total.reindex(calendar, fill_value=0)
    sources = []
    if args.legacy_hfq:
        observed = total.index[total.observed.gt(0)]
        sources = [{"table": "stock_data", "start": observed[0], "end": observed[-1],
                    "note": "旧采集器后复权历史，完整市场交易日窗口；停牌与原始缺口尚未逐股区分。"}]
    if args.refresh_hfq:
        total, extra_sources = extend_hfq_breadth(total, calendar, out)
        sources.extend(extra_sources)
    for w in (40, 60, 80, 120):
        total[f"breadth{w}"] = total[f"above{w}"] / total[f"valid{w}"].replace(0, float("nan")) * 100
    total.to_csv(out / ("breadth-legacy-hfq.csv" if args.legacy_hfq else "breadth-raw.csv"), index_label="date")
    if args.legacy_hfq:
        save(out / "breadth-provenance.json", {"sources": sources})
    print("BREADTH COMPLETE", len(total), flush=True)


if __name__ == "__main__":
    main()
