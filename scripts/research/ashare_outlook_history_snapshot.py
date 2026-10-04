"""Capture only the additional stock evidence; never replace the fixed index snapshot."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal
from ashare_outlook_snapshot import encode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    query = """SELECT stock_code,trade_date,open_price,close_price,high_price,low_price,
        data_source FROM stock_daily_data WHERE stock_code='600519'
        AND trade_date BETWEEN '2020-01-01' AND '2022-12-31' ORDER BY trade_date"""
    with SessionLocal() as db:
        rows = [dict(r) for r in db.execute(text(query)).mappings()]
    result = {"read_only": True, "query": query, "stocks": rows,
              "price_basis": "unadjusted", "stock_name": "贵州茅台",
              "note": "数据库二级行情，未复权价格；现金分红除息影响价格，不作为含分红收益率。"}
    payload = json.dumps(result, default=encode, ensure_ascii=False, allow_nan=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"path": str(args.output), "rows": len(rows),
                      "sha256": hashlib.sha256(payload.encode()).hexdigest()}))


if __name__ == "__main__":
    main()
