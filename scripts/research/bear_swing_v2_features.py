"""Read-only, publication-aware inputs for the second bear-swing study."""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.bear_swing_features import build_features, load_inputs, prior_percentile


def snapshot(db):
    candles, dashboard, bank, global_rows = load_inputs(db)
    queries = {
        "margin": """SELECT trade_date,exchange,financing_balance,financing_net_buy_amount,
            data_source FROM margin_trading_daily_data WHERE exchange IN ('SSE','SZSE')
            ORDER BY trade_date,exchange""",
        "valuation": """SELECT trade_date,csi1000_equity_bond_spread_pp,data_source
            FROM cn_macro_indicator_daily ORDER BY trade_date""",
        "fx": """SELECT symbol_code,symbol_name,MIN(trade_date) first_date,
            MAX(trade_date) last_date,COUNT(*) n FROM forex_daily_data
            GROUP BY symbol_code,symbol_name""",
        "monthly_coverage": """SELECT series_key,MIN(period_end) first_period,
            MAX(period_end) last_period,COUNT(DISTINCT period_end) periods,
            MIN(r.available_at) first_published,MIN(r.replay_available_at) first_replay
            FROM cn_macro_observation o JOIN cn_macro_release r USING(release_id)
            GROUP BY series_key ORDER BY series_key""",
        "strategies": """SELECT id,name,start_date,indicator_params,red_filter_groups,
            blue_filter_groups FROM quant_strategy_configs WHERE id IN (1,31,44,45)
            ORDER BY id""",
        "mo_gap": """SELECT * FROM option_cffex_rtj_daily_data
            WHERE product_prefix='MO' AND trade_date IN ('2024-01-22','2024-02-05')
            ORDER BY trade_date,contract_code""",
    }
    return {"candles": candles, "dashboard": dashboard, "bank": bank,
            "global": global_rows, **{k: [dict(r) for r in db.execute(text(q)).mappings()]
                                      for k, q in queries.items()}}


def features(raw):
    f = build_features(raw["candles"], raw["dashboard"], raw["bank"], raw["global"])
    close = f.close
    for window in (60, 120):
        lo, hi = f.low.rolling(window).min(), f.high.rolling(window).max()
        position = (close - lo) / (hi - lo).replace(0, np.nan) * 100
        f[f"position{window}_pct"] = prior_percentile(position)
    margin = pd.DataFrame(raw["margin"])
    margin["trade_date"] = margin.trade_date.astype(str).str[:10]
    for col in ("financing_balance", "financing_net_buy_amount"):
        margin[col] = pd.to_numeric(margin[col], errors="coerce")
    # Reindex to the actual index sessions BEFORE rolling and shifting. A missing
    # exchange/day breaks the window instead of silently shortening it.
    flow = margin.pivot(index="trade_date", columns="exchange", values="financing_net_buy_amount")
    balance = margin.pivot(index="trade_date", columns="exchange", values="financing_balance")
    flow = flow.reindex(index=f.index, columns=["SSE", "SZSE"]).sum(axis=1, min_count=2)
    balance = balance.reindex(index=f.index, columns=["SSE", "SZSE"]).sum(axis=1, min_count=2)
    f["finance_source_date"] = pd.Series(f.index, index=f.index).shift(1).where(flow.shift(1).notna())
    f["finance30"] = flow.rolling(30).sum().shift(1) / 1e8
    f["finance30_pct"] = prior_percentile(f.finance30)
    f["finance30_intensity_pct"] = prior_percentile(flow.rolling(30).sum().div(balance).shift(1))
    for n in (1, 3, 5):
        f[f"finance_change{n}"] = f.finance30.diff(n)
        f[f"return{n}"] = close.pct_change(n, fill_method=None) * 100
    price_strength = (close - close.rolling(60).min()) / (
        close.rolling(60).max() - close.rolling(60).min()).replace(0, np.nan) * 100
    realized = np.log(close / close.shift(1)).rolling(20).std(ddof=0) * np.sqrt(252)
    components = pd.DataFrame({"rsi": f.rsi, "momentum": f["bear-momentum20-pct"],
        "strength": price_strength, "low_volatility": 100 - pd.Series(prior_percentile(realized), index=f.index),
        "financing": f.finance30_pct})
    f["core_known"] = components.mean(axis=1).where(components.notna().all(axis=1))
    f["core_known_pct"] = prior_percentile(f.core_known)
    f["break_high1"] = (close - f.high.shift(1)).where(f.high.shift(1).notna())
    f["break_low1"] = (close - f.low.shift(1)).where(f.low.shift(1).notna())
    f["break_high3"] = (close - f.high.shift(1).rolling(3).max()).where(f.high.shift(1).rolling(3).count() == 3)
    f["break_low3"] = (close - f.low.shift(1).rolling(3).min()).where(f.low.shift(1).rolling(3).count() == 3)
    f["im_basis_rate_pct"] = prior_percentile(f["bear-im-basis"] / close * 100)
    return f


def coverage(f):
    result = {}
    for col in f.select_dtypes(include="number").columns:
        values = f[col].dropna()
        result[col] = {"first_valid": str(values.index[0]) if len(values) else None,
                       "last_valid": str(values.index[-1]) if len(values) else None,
                       "valid_observations": len(values), "years": {}}
        for y in range(2018, 2027):
            part = f.loc[f"{y}-01-01":f"{y}-12-31", col]
            result[col]["years"][str(y)] = {"total": len(part), "valid": int(part.notna().sum())}
    return result


def json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return float(value)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default,
                               allow_nan=False), encoding="utf-8")
