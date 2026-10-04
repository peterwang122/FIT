"""Causal CSI1000 research features, shared by charts, filters and research.

No imputation or price adjustment is performed here. Percentiles are based on
prior *observations*, not calendar days, and never include the current value.
"""
from bisect import bisect_left, bisect_right, insort
from collections import deque
from datetime import datetime, time
import json
from math import isfinite

import pandas as pd
from sqlalchemy import text

VERSION = "csi1000-bear-features-v1"
PREFIX = "bear-"
# Only selected factors are public. Candidate-only features remain research data.
FEATURE_FIELDS = {
    "bear-bank-tightness": "银行流动性紧张度（22:30已知）",
    "bear-position60-pct": "60D价格位置历史分位",
    "bear-return-1d": "指数1D涨跌幅",
    "bear-mo-vix-pct": "MO隐含波动率历史分位",
    "bear-citic14-pct": "中信IM净空14D增量历史分位",
}


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def prior_percentile(values, window=1260, minimum=252):
    ordered, history, result = [], deque(), []
    for raw in values:
        value = number(raw)
        result.append(None if value is None or len(history) < minimum else
                      50 * (bisect_left(ordered, value) + bisect_right(ordered, value)) / len(ordered))
        if value is not None:
            history.append(value)
            insort(ordered, value)
            if len(history) > window:
                ordered.pop(bisect_left(ordered, history.popleft()))
    return result


def json_object(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}


def available_values(dates, observations, max_age_days=7):
    """Map timestamped observations to 22:30 China time, without backdating."""
    def timestamp(row):
        stamp = pd.Timestamp(row["available_at"])
        return stamp.tz_localize("Asia/Shanghai") if stamp.tzinfo is None else stamp.tz_convert("Asia/Shanghai")

    rows = sorted((r for r in observations if r.get("available_at") and r.get("source_date")),
                  key=timestamp)
    result, cursor, known = [], 0, {}
    for day in dates:
        cutoff = pd.Timestamp(datetime.combine(pd.Timestamp(day).date(), time(22, 30)), tz="Asia/Shanghai")
        while cursor < len(rows):
            row = rows[cursor]
            stamp = timestamp(row)
            if stamp > cutoff:
                break
            known[str(row["source_date"])[:10]] = row
            cursor += 1
        latest = known[max(known)] if known else None
        valid = latest and 0 <= (cutoff.date() - pd.Timestamp(latest["source_date"]).date()).days <= max_age_days
        result.append(number(latest["value"]) if valid else None)
    return result


def build_features(candles, dashboard, bank_rows=(), global_rows=()):
    """All prices must be unadjusted index OHLC, sorted in actual trading order."""
    from app.services.quant_service import _calc_wr, _calc_rsi
    candles = sorted(candles, key=lambda c: str(c["trade_date"]))
    dates = [str(c["trade_date"])[:10] for c in candles]
    frame = pd.DataFrame([{k: number(c[k]) for k in ("open", "high", "low", "close")} for c in candles],
                         columns=["open", "high", "low", "close"], index=dates, dtype=float)
    close = frame.close
    frame["wr"] = _calc_wr(frame.to_dict("records"), 14)
    frame["rsi"] = _calc_rsi(close.tolist(), 14)
    frame["bear-momentum20-pct"] = prior_percentile(close.pct_change(20, fill_method=None))
    high60, low60 = frame.high.rolling(60).max(), frame.low.rolling(60).min()
    position = (close - low60) / (high60 - low60).replace(0, float("nan")) * 100
    frame["bear-position60-pct"] = prior_percentile(position)
    for window in (1, 3, 5):
        frame[f"bear-return-{window}d"] = close.pct_change(window, fill_method=None) * 100
    by_date = {str(r["trade_date"])[:10]: r for r in dashboard}
    # The original core/total contains same-date financing. Keep it diagnostic,
    # not eligible for rule selection without independently audited publication.
    for field, column in {
        "diagnostic-core": "self_sentiment_core_score",
        "diagnostic-financing30": "margin_financing_net_buy_sum_30d",
        "diagnostic-risk-total": "risk_overall_score",
        "bear-mo-turnover-pc": "option_turnover_pc_ratio",
        "bear-im-basis": "main_basis",
        "bear-citic14": "cffex_citic_net_short_delta_14d",
    }.items():
        values = [number(by_date.get(day, {}).get(column)) for day in dates]
        if field.startswith("bear-"):
            # Domestic derivatives close before 22:30. Do not use pre-listing data.
            values = [v if day >= "2022-07-22" else None for day, v in zip(dates, values)]
        frame[field] = values
        frame[field + "-pct"] = prior_percentile(values)
    for field, key in (("bear-mo-vix", "vix_close"), ("bear-mo-term", "vix_term_structure")):
        values = [number(json_object(by_date.get(day, {}).get("option_vix_json")).get("cffex:MO", {}).get(key))
                  if day >= "2022-07-22" else None for day in dates]
        frame[field] = values
        frame[field + "-pct"] = prior_percentile(values)
    bank_observations = []
    for row in bank_rows:
        times = [row.get(k) for k in ("frr_available_at", "chinabond_available_at", "reverse_repo_7d_policy_available_at")]
        if all(times):
            bank_observations.append({"source_date": row["trade_date"], "available_at": max(times),
                                      "value": row.get("liquidity_tightness_score")})
    frame["bear-bank-tightness"] = available_values(dates, bank_observations)
    # Rank each external market on its own observation dates before mapping it.
    for asset in ("VIX9D", "VIX3M", "VVIX", "ACWI_NAV"):
        rows = sorted([r for r in global_rows if r["asset_code"] == asset], key=lambda r: str(r["source_date"]))
        ranks = prior_percentile([r["close_value"] for r in rows])
        frame["bear-" + asset.lower() + "-pct"] = available_values(dates, [
            {**r, "value": value} for r, value in zip(rows, ranks)])
    return frame


def load_inputs(db, candles=None):
    # Read the canonical rows directly: a price-cache hit from before a repair
    # must not populate features under the repaired source revision.
    if candles is None:
        candles = [dict(r) for r in db.execute(text("""SELECT trade_date,open_price AS open,
            high_price AS high,low_price AS low,close_price AS close FROM index_daily_data
            WHERE index_code='sh000852' ORDER BY trade_date""")).mappings()]
    dashboard = [dict(r) for r in db.execute(text("""SELECT trade_date,self_sentiment_core_score,
        margin_financing_net_buy_sum_30d,risk_overall_score,option_turnover_pc_ratio,main_basis,
        cffex_citic_net_short_delta_14d,option_vix_json FROM quant_index_dashboard_daily
        WHERE index_code='sh000852' AND trade_date>='2005-01-01' ORDER BY trade_date""")).mappings()]
    bank = [dict(r) for r in db.execute(text("""SELECT trade_date,liquidity_tightness_score,
        frr_available_at,chinabond_available_at,reverse_repo_7d_policy_available_at
        FROM cn_bank_liquidity_daily ORDER BY trade_date""")).mappings()]
    global_rows = [dict(r) for r in db.execute(text("""SELECT asset_code,source_date,available_at,close_value
        FROM global_risk_asset_daily WHERE asset_code IN ('VIX9D','VIX3M','VVIX','ACWI_NAV')
        ORDER BY source_date""")).mappings()]
    return candles, dashboard, bank, global_rows


def load_features(db, candles=None):
    return build_features(*load_inputs(db, candles))


def feature_points(db):
    """Cache by source revision, not wall-clock date, so same-day repairs show up."""
    from hashlib import sha256
    from app.core.redis_client import redis_client
    stamps = [tuple(r) for r in db.execute(text("""SELECT MAX(updated_at),COUNT(*) FROM
        quant_index_dashboard_daily WHERE index_code='sh000852'
        UNION ALL SELECT MAX(updated_at),COUNT(*) FROM cn_bank_liquidity_daily
        UNION ALL SELECT MAX(updated_at),COUNT(*) FROM index_daily_data WHERE index_code='sh000852'"""))]
    key = "quant:bear-features:" + VERSION + ":" + sha256(str(stamps).encode()).hexdigest()[:20]
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)
    frame = load_features(db)
    result = [{"trade_date": day, "values": {k: number(row[k]) for k in FEATURE_FIELDS},
               "as_of_at": day + "T22:30:00+08:00"} for day, row in frame.iterrows()]
    redis_client.set(key, json.dumps(result, allow_nan=False), ex=1800)
    return result
