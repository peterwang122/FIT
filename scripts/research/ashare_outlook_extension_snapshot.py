"""Read-only, full-coverage evidence for the outlook's expanded research."""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from ashare_outlook_snapshot import encode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal
from app.services.market_regime_research import read_observations

AS_OF = datetime.fromisoformat("2026-10-04T04:00:00")
FOLDER = ROOT / "runtime/reports/ashare_outlook/2026-10-04"
INDEX_CODES = ["sh000986", "sh000987", "sh000988", "sh000989", "sh000990",
               "sh000991", "sh000992", "sh000993", "sh000994", "sh000995",
               "sh931775", "sh000057", "sh000058", "sh000922", "sh000982"]


def collect():
    queries = {
        "indexes": """SELECT d.index_code,d.trade_date,d.open_price,d.high_price,
            d.low_price,d.close_price,d.turnover,d.data_source,b.index_name
            FROM index_daily_data d LEFT JOIN index_basic_info b ON b.index_code=d.index_code
            WHERE d.index_code IN (""" + ",".join(f":i{i}" for i in range(len(INDEX_CODES))) + """ )
            AND trade_date<=:market_day ORDER BY d.index_code,d.trade_date""",
        "valuations": "SELECT * FROM cn_index_valuation_daily WHERE trade_date<=:market_day ORDER BY index_code,trade_date",
        "financing": """SELECT trade_date,exchange,financing_balance,financing_net_buy_amount,
            data_source,source_url FROM margin_trading_daily_data
            WHERE trade_date<=:market_day ORDER BY trade_date,exchange""",
        "us_yields": "SELECT * FROM index_us_treasury_yield_daily WHERE trade_date<=:day AND (available_at IS NULL OR available_at<=:as_of) ORDER BY trade_date",
        "us_credit": "SELECT * FROM index_us_credit_spread_daily WHERE trade_date<=:day AND (available_at IS NULL OR available_at<=:as_of) ORDER BY trade_date",
        "global_assets": """SELECT asset_code,trade_date,close_value,source_date,available_at,data_source
            FROM global_risk_asset_daily WHERE trade_date<=:day AND available_at<=:as_of
            AND asset_code IN ('ACWI_NAV','EFA_NAV','EEM_NAV','KOSPI','WTI','BRENT','COPPER_HG')
            ORDER BY asset_code,trade_date""",
        "fx": """SELECT symbol_code,symbol_name,trade_date,latest_price,data_source
            FROM forex_daily_data WHERE symbol_code IN ('UDI','USDCNH','USDJPY')
            AND trade_date<=:day ORDER BY symbol_code,trade_date""",
    }
    params = {"market_day": "2026-09-30", "day": AS_OF.date(), "as_of": AS_OF,
              **{f"i{i}": code for i, code in enumerate(INDEX_CODES)}}
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        data = {key: [dict(row) for row in db.execute(text(query), params).mappings()]
                for key, query in queries.items()}
        data["macro_observations"] = read_observations(db)
        data["macro_observations"] = [r for r in data["macro_observations"]
                                      if r["available_at"] <= AS_OF]
    comparison = FOLDER.parent.parent / "market_regime/strategy_comparison.json"
    data["strategy_comparison"] = json.loads(comparison.read_text())
    payload = {"as_of_at": AS_OF.isoformat(), "market_date": "2026-09-30",
               "read_only": True, "requested_index_codes": INDEX_CODES,
               "queries": queries, "data": data}
    raw = json.dumps(payload, default=encode, ensure_ascii=False, allow_nan=False).encode()
    output = FOLDER / "extension_snapshot.json"
    output.write_bytes(raw)
    print(json.dumps({"path": str(output), "sha256": hashlib.sha256(raw).hexdigest(),
                      "rows": {k: len(v) for k, v in data.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    collect()
