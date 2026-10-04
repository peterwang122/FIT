"""Read-only evidence snapshot for the dated A-share outlook report."""

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal
from app.services.market_regime_research import read_observations, select_macro, macro_derived


def encode(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def snapshot(as_of):
    day = as_of.date()
    queries = {
        "indexes": """SELECT index_code,trade_date,open_price,close_price,high_price,
            low_price,volume,turnover,data_source FROM index_daily_data
            WHERE index_code IN ('sh000001','sh000985','sh000300','sh000905','sh000852')
            AND trade_date<=:day ORDER BY index_code,trade_date""",
        "valuations": """SELECT * FROM cn_index_valuation_daily
            WHERE trade_date>= '2020-01-01' AND trade_date<=:day ORDER BY index_code,trade_date""",
        "macro_daily": """SELECT * FROM cn_macro_indicator_daily
            WHERE trade_date>='2023-01-01' AND trade_date<=:day ORDER BY trade_date""",
        "china_bonds": """SELECT trade_date,tenor_years,maturity_yield_pct,data_source,source_url
            FROM cn_government_bond_yield_daily WHERE trade_date>='2024-01-01'
            AND trade_date<=:day ORDER BY tenor_years,trade_date""",
        "bank_liquidity": """SELECT trade_date,fdr001_pct,fdr007_pct,fr007_pct,
            reverse_repo_7d_policy_rate_pct,liquidity_tightness_score,liquidity_state,
            liquidity_trend,score_change_5d,frr_available_at,chinabond_available_at,
            source_url_frr,source_url_chinabond FROM cn_bank_liquidity_daily
            WHERE trade_date>='2024-01-01' AND trade_date<=:day ORDER BY trade_date""",
        "financing": """SELECT trade_date,exchange,financing_balance,financing_net_buy_amount,
            data_source,source_url FROM margin_trading_daily_data
            WHERE trade_date>='2023-01-01' AND trade_date<=:day ORDER BY exchange,trade_date""",
        "fx": """SELECT symbol_code,symbol_name,trade_date,latest_price,data_source
            FROM forex_daily_data WHERE trade_date>='2024-01-01' AND trade_date<=:day
            ORDER BY symbol_code,trade_date""",
        "us_yields": """SELECT * FROM index_us_treasury_yield_daily
            WHERE trade_date>='2024-01-01' AND trade_date<=:day
            AND (available_at IS NULL OR available_at<=:as_of) ORDER BY trade_date""",
        "us_credit": """SELECT * FROM index_us_credit_spread_daily
            WHERE trade_date>='2024-01-01' AND trade_date<=:day
            AND (available_at IS NULL OR available_at<=:as_of) ORDER BY trade_date""",
        "global_assets": """SELECT asset_code,asset_name,trade_date,close_value,
            source_date,available_at,data_source,source_url FROM global_risk_asset_daily
            WHERE trade_date>='2024-01-01' AND trade_date<=:day AND available_at<=:as_of
            ORDER BY asset_code,trade_date""",
        "dashboard": """SELECT index_code,trade_date,self_sentiment_core_score,
            self_sentiment_derivative_score,margin_financing_net_buy_sum_5d,
            margin_financing_net_buy_sum_30d,margin_financing_net_buy_sum_120d,
            risk_overall_score,risk_display_state,risk_as_of_at,risk_global_score,
            risk_global_leading,risk_global_raw_leading,main_basis,month_basis,
            cffex_citic_net_short_delta_14d,turnover_concentration_top5_pct
            FROM quant_index_dashboard_daily WHERE index_code IN ('sh000300','sh000852')
            AND trade_date>='2024-01-01' AND trade_date<=:day ORDER BY index_code,trade_date""",
    }
    with SessionLocal() as db:
        result = {key: [dict(r) for r in db.execute(text(sql), {"day": day, "as_of": as_of}).mappings()]
                  for key, sql in queries.items()}
        observations = read_observations(db)
        result["monthly_macro"] = select_macro(observations, as_of)
        result["derived_macro"] = macro_derived(result["monthly_macro"])
    return {"as_of_at": as_of.isoformat(), "timezone": "Asia/Shanghai",
            "queries": queries, "read_only": True, "data": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=datetime.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.as_of > datetime.now():
        raise ValueError("Future research cutoff is not allowed")
    result = snapshot(args.as_of)
    payload = json.dumps(result, default=encode, ensure_ascii=False, allow_nan=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"path": str(args.output), "sha256": hashlib.sha256(payload.encode()).hexdigest(),
                      "rows": {k: len(v) for k, v in result["data"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
