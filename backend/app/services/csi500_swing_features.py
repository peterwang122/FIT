"""Source-aware CSI500 research. Historical cycle labels never enter features."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import deque
from datetime import datetime, time
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json
import re

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.services.bear_swing_features import number, prior_percentile

VERSION = "csi500-swing-features-v3"
INDEX_CODE = "sh000905"
# Frozen after selection; candidate-only fields are never public filters.
PUBLIC_FIELDS: dict[str, dict] = json.loads(Path(__file__).with_name("csi500_swing_fields.json").read_text(encoding="utf-8"))

@dataclass
class Feature:
    key: str
    label: str
    family: str
    source: str
    unit: str = "official source unit"
    eligibility: str = "eligible"
    reason: str = ""
    frequency: str = "daily"
    transform: str = "raw"
    first_source_date: str | None = None
    first_available_date: str | None = None
    observations: int = 0
    valid_days: int = 0
    publication: str = ""
    candidate_thresholds: tuple[float, ...] = ()


def safe_key(value):
    return re.sub(r"[^a-z0-9-]+", "-", str(value).lower()).strip("-")


def option_numeric_fields(payload):
    for field, value in payload.items():
        if field.endswith(("flag", "contract_month", "date", "code", "available_at")) or field.startswith("sample") or isinstance(value, bool):
            continue
        value = number(value)
        if value is not None:
            yield field, value


@lru_cache(maxsize=40000)
def stamp(value):
    result = pd.Timestamp(value)
    return result.tz_localize("Asia/Shanghai") if result.tzinfo is None else result.tz_convert("Asia/Shanghai")


def map_observations(dates, rows, max_age_days=None, cutoffs=None):
    """Last *source period* visible at the cutoff, not last physical DB row."""
    result = np.full(len(dates), np.nan)
    cutoffs = cutoffs or [stamp(datetime.combine(pd.Timestamp(d).date(), time(22, 30))) for d in dates]
    records = sorted([(stamp(r["available_at"]), str(r["source_date"])[:10], pd.Timestamp(r["source_date"]).date(), number(r.get("value")))
                      for r in rows if r.get("available_at") and r.get("source_date")], key=lambda r: r[0])
    latest, cursor = None, 0
    for i, cutoff in enumerate(cutoffs):
        while cursor < len(records) and records[cursor][0] <= cutoff:
            r = records[cursor]
            if latest is None or r[1] >= latest[1]:
                latest = r
            cursor += 1
        if latest is None:
            continue
        age = (cutoff.date() - latest[2]).days
        if max_age_days is None or 0 <= age <= max_age_days:
            v = latest[3]
            if v is not None:
                result[i] = v
    return result


def cycle_labels(dates):
    """User-approved ex-post major cycles, for evaluation ONLY."""
    pivots = [
        ("2005-01-04", "bear"), ("2005-07-18", "bull"),
        ("2008-01-15", "bear"), ("2008-11-04", "bull"),
        ("2010-11-10", "bear"), ("2012-12-03", "bull"),
        ("2015-06-12", "bear"), ("2018-10-18", "bull"),
        ("2021-09-13", "bear"), ("2024-09-18", "bull"),
        ("2026-07-01", "observation"),
    ]
    labels = []
    for d in dates:
        labels.append(next((label for start, label in reversed(pivots) if str(d) >= start), "unknown"))
    return np.array(labels), pivots


class Builder:
    def __init__(self, candles):
        self.frame = pd.DataFrame(candles).set_index("trade_date").sort_index()
        self.frame.index = self.frame.index.map(lambda d: str(d)[:10])
        self.frame = self.frame.apply(pd.to_numeric, errors="coerce")
        self.cutoffs = [stamp(datetime.combine(pd.Timestamp(d).date(), time(22, 30))) for d in self.frame.index]
        self.catalog: dict[str, Feature] = {}
        self.columns = {}

    def add(self, key, label, family, source, observations, *, eligible=True,
            reason="", frequency="daily", unit="official source unit", publication="",
            transform=True, max_age_days=7):
        key = "csi500-" + safe_key(key)
        if key in self.catalog:
            raise ValueError("Duplicate feature: " + key)
        rows = [dict(r, value=number(r.get("value"))) for r in observations]
        rows = [r for r in rows if r["value"] is not None and r.get("source_date")]
        rows.sort(key=lambda r: str(r["source_date"]))
        if not eligible:
            # Diagnostic alignment is explicitly NOT a publication-time claim.
            for r in rows:
                r["available_at"] = datetime.combine(pd.Timestamp(r["source_date"]).date(), time(22, 30))
        meta = Feature(key, label, family, source, unit, "eligible" if eligible else "diagnostic",
                       reason, frequency, publication=publication)
        if rows:
            meta.first_source_date = str(rows[0]["source_date"])[:10]
            meta.observations = len(rows)
        variants = [(key, rows, "raw", unit)]
        if transform and rows:
            # Revisions are not new monthly observations. Unverified/revised
            # monthly ranks are omitted; original values can still be studied.
            if frequency != "monthly":
                ranks = prior_percentile([r["value"] for r in rows])
                ranked = []
                window, absent, maximum = deque(), deque(), deque()
                for i, (r, v) in enumerate(zip(rows, ranks)):
                    t = stamp(r["available_at"]) if r.get("available_at") else None
                    window.append((i, t))
                    if t is None:
                        absent.append(i)
                    else:
                        while maximum and maximum[-1][1] <= t:
                            maximum.pop()
                        maximum.append((i, t))
                    while window and window[0][0] < i - 1260:
                        window.popleft()
                    while absent and absent[0] < i - 1260:
                        absent.popleft()
                    while maximum and maximum[0][0] < i - 1260:
                        maximum.popleft()
                    ranked.append(dict(r, value=v, available_at=maximum[0][1] if maximum and not absent else None))
                variants.append((key + "-pct", ranked, "prior-percentile", "%"))
                for n in (1, 3, 5):
                    values = pd.Series([r["value"] for r in rows], dtype=float).diff(n)
                    changes = [dict(r, value=v, available_at=max((r["available_at"], rows[i - n]["available_at"]), key=stamp)
                                    if i >= n and r.get("available_at") and rows[i - n].get("available_at") else None)
                               for i, (r, v) in enumerate(zip(rows, values))]
                    variants.append((key + f"-change-{n}d", changes, f"change-{n}d", unit))
            else:
                # Compare calendar months, never daily repetitions or bases.
                changes = []
                by_month = {}
                for prior_row in rows:
                    by_month.setdefault(pd.Timestamp(prior_row["source_date"]).to_period("M"), []).append(prior_row)
                for r in rows:
                    previous = pd.Timestamp(r["source_date"]).to_period("M") - 3
                    visible = [a for a in by_month.get(previous, [])
                               if a.get("available_at") and r.get("available_at") and stamp(a["available_at"]) <= stamp(r["available_at"])]
                    prior = max(visible, key=lambda a: stamp(a["available_at"])) if visible else None
                    changes.append(dict(r, value=r["value"] - prior["value"] if prior else None))
                variants.append((key + "-change-3m", changes, "change-3m", unit))
        for feature_key, records, operation, feature_unit in variants:
            values = map_observations(self.frame.index, records, max_age_days, self.cutoffs)
            item = Feature(**{**asdict(meta), "key": feature_key, "transform": operation, "unit": feature_unit})
            item.valid_days = int(np.isfinite(values).sum())
            source_values = [number(r.get("value")) for r in records]
            source_values = [v for v in source_values if v is not None]
            if source_values:
                item.candidate_thresholds = tuple(sorted(set(float(v) for v in np.quantile(source_values, [.1, .2, .3, .7, .8, .9]))))
            valid = np.flatnonzero(np.isfinite(values))
            item.first_available_date = self.frame.index[valid[0]] if len(valid) else None
            if operation == "prior-percentile":
                item.label += " historical percentile"
            self.catalog[feature_key] = item
            self.columns[feature_key] = values

    def price_features(self):
        from app.services.quant_service import _calc_rsi, _calc_wr
        f = self.frame
        dates = f.index
        def add(key, label, values, family="price", unit="%"):
            self.add(key, label, family, "index_daily_data:sh000905", [
                {"source_date": d, "available_at": d + "T15:15:00+08:00", "value": v}
                for d, v in zip(dates, values)], unit=unit, publication="A-share closing quote, same session", transform=False, max_age_days=0)
        add("rsi14", "中证500 RSI14", _calc_rsi(f.close.tolist(), 14))
        add("wr14", "中证500 WR14", _calc_wr(f.to_dict("records"), 14))
        for n in (1, 3, 5, 10, 20, 60):
            add(f"return-{n}d", f"中证500 {n}D涨跌幅", f.close.pct_change(n, fill_method=None) * 100)
        for n in (20, 60, 120):
            hi, lo = f.high.rolling(n).max(), f.low.rolling(n).min()
            position = (f.close - lo) / (hi - lo).replace(0, np.nan) * 100
            add(f"position-{n}d", f"中证500 {n}D价格位置", position)
            add(f"position-{n}d-pct", f"中证500 {n}D位置历史分位", prior_percentile(position))
            add(f"distance-ma{n}", f"中证500 MA{n}乖离率", (f.close / f.close.rolling(n).mean() - 1) * 100)
            add(f"volatility-{n}d", f"中证500 {n}D收益波动率", f.close.pct_change(fill_method=None).rolling(n).std() * 100)

    def finish(self):
        return pd.concat([self.frame, pd.DataFrame(self.columns, index=self.frame.index)], axis=1), self.catalog


def read_rows(db, table, where="", params=None, fields=None):
    if not re.fullmatch(r"[a-z0-9_]+", table):
        raise ValueError("Invalid table")
    columns = [r[0] for r in db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t ORDER BY ordinal_position"), {"t": table})]
    # Raw responses stay in the source DB; never export credentials or payloads.
    selected = [c for c in columns if c not in {"raw_json", "raw_response", "raw_payload_json", "raw_trading_json", "raw_metrics_json"}
                and (fields is None or c in fields)]
    return [dict(r) for r in db.execute(text("SELECT " + ",".join("`" + c + "`" for c in selected) + " FROM `" + table + "` " + where), params or {}).mappings()]


def known_financing_values(rows, dates, field, window=1):
    frame = pd.DataFrame(rows)
    frame["day"] = frame.trade_date.map(lambda d: str(d)[:10])
    pivot = frame.pivot_table(index="day", columns="exchange", values=field, aggfunc="last").reindex(index=dates, columns=["SSE", "SZSE"])
    total = pivot.apply(pd.to_numeric, errors="coerce").astype(float).sum(axis=1, min_count=2)
    return total.rolling(window, min_periods=window).sum().shift(1) / 1e8


def load_research_features(db, cache_dir=None, resume=False):
    candles = [dict(r) for r in db.execute(text("SELECT trade_date,open_price AS open,high_price AS high,low_price AS low,close_price AS close,volume,turnover FROM index_daily_data WHERE index_code=:code ORDER BY trade_date"), {"code": INDEX_CODE}).mappings()]
    b = Builder(candles)
    b.price_features()
    catalog_tables = {}
    def daily_table(table, grouping=(), *, eligible=False, publication="", reason="Historical publication time is not independently verified", time_column=None, date_column="trade_date", fields=None, frequency="daily"):
        print("reading", table, flush=True)
        cached_path = cache_dir / (table + ".npz") if cache_dir else None
        signature = sha256(json.dumps([VERSION, list(b.frame.index), grouping, eligible, publication, reason, time_column,
                                      date_column, sorted(fields) if fields else None, frequency], default=str).encode()).hexdigest()
        if resume and cached_path and cached_path.exists():
            with np.load(cached_path, allow_pickle=False) as data:
                metadata = json.loads(str(data["metadata"]))
                if metadata["signature"] == signature:
                    cached_values = data["values"]
                    for i, key in enumerate(metadata["keys"]):
                        b.columns[key] = cached_values[:, i].copy()
                        b.catalog[key] = Feature(**metadata["catalog"][key])
                    catalog_tables[table] = metadata["table"]
                    print("resumed", table, len(metadata["keys"]), "features", flush=True)
                    return
        before = set(b.catalog)
        ignore = {"id", "created_at", "updated_at", date_column, *grouping}
        schema = db.execute(text("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=:t ORDER BY ordinal_position"), {"t": table}).all()
        numeric = [c for c, kind in schema if kind in {"decimal", "float", "double", "int", "bigint", "smallint", "tinyint"}
                   and c not in ignore and (fields is None or c in fields)
                   and not ((c.endswith("flag") and fields is None) or c in {"locked", "tenor_days", "tenor_years"})]
        selected = list(dict.fromkeys([date_column, *grouping, *([time_column] if time_column else []), *numeric]))
        query = "SELECT " + ",".join("`" + c + "`" for c in selected) + " FROM `" + table + "` ORDER BY " + ",".join("`" + c + "`" for c in [*grouping, date_column])
        groups, current, row_count, group_count = {}, None, 0, 0
        def flush(group):
            for field, observations in groups.items():
                key = "-".join((table, *group, field))
                family = ":".join((table, *group))
                b.add(key, ":".join((*group, field)), family, table, observations, eligible=eligible,
                      reason="" if eligible else reason, frequency=frequency, publication=publication,
                      max_age_days=180 if frequency == "monthly" else 0 if eligible and not time_column else 7)
            groups.clear()
        # Stream one source series at a time, not millions of quote dictionaries.
        result = db.execute(text(query), execution_options={"stream_results": True})
        for row in result.mappings():
            row_count += 1
            group = tuple(str(row.get(g) or "") for g in grouping)
            if current is not None and group != current:
                flush(current)
                group_count += 1
                if group_count % 50 == 0:
                    print(table, "series groups", group_count, "features", len(b.catalog), flush=True)
            current = group
            for field in numeric:
                raw = row[field]
                if raw is None:
                    continue
                available = row.get(time_column) if time_column else (str(row[date_column])[:10] + "T18:00:00+08:00" if eligible else None)
                groups.setdefault(field, []).append({"source_date": row[date_column], "available_at": available, "value": raw})
        result.close()
        if current is not None:
            flush(current)
        catalog_tables[table] = {"rows": row_count, "research": "numeric daily/monthly series"}
        if cached_path:
            cache_dir.mkdir(parents=True, exist_ok=True)
            keys = sorted(set(b.catalog) - before)
            metadata = {"signature": signature, "keys": keys, "catalog": {k: asdict(b.catalog[k]) for k in keys}, "table": catalog_tables[table]}
            np.savez_compressed(cached_path, values=np.column_stack([b.columns[k] for k in keys]) if keys else np.empty((len(b.frame), 0)),
                                metadata=np.asarray(json.dumps(metadata, default=str)))
        print("scanned", table, "features", len(b.catalog), flush=True)

    # Market-level rows only; stock/contract detail is represented by existing
    # aggregates, avoiding a current-constituent survivorship shortcut.
    daily_table("index_daily_data", ("index_code",), eligible=True,
                fields={"close_price", "volume", "turnover", "turnover_rate"}, publication="Domestic closing quote")
    daily_table("index_hk_daily_data", ("index_code",), eligible=True,
                fields={"close_price", "volume", "turnover"}, publication="Hong Kong same-day closing quote before 22:30")
    for table, group, fields in (
        ("index_us_daily_data", ("index_code",), {"close_price", "volume", "turnover"}),
        ("forex_daily_data", ("symbol_code",), {"latest_price", "amplitude"}),
        ("cn_index_valuation_daily", ("index_code",), {"pe_ttm", "earnings_yield_pct"}),
        ("cn_macro_indicator_daily", (), None),
        ("margin_trading_daily_data", ("exchange",), None),
        ("excel_index_emotion_daily", ("index_name",), {"emotion_value"}),
        ("douyin_index_emotion_daily", (), {"hs300_emotion", "zz500_emotion", "zz1000_emotion", "sz50_emotion"}),
        ("index_cn_market_fear_greed_daily", (), {"fear_greed_value"}),
        ("index_cn_baifenwei_fear_greed_daily", (), None),
        ("index_us_put_call_ratio_daily", (), None),
        ("index_us_option_premium_daily", (), None),
        ("index_us_fear_greed_daily", (), None),
        ("index_us_vix_daily", (), {"open_value", "high_value", "low_value", "close_value"}),
        ("index_news_sentiment_scope_daily", (), {"sentiment_value"}),
        ("cn_risk_free_rate_daily", ("tenor_code",), {"rate_pct"}),
        ("cn_government_bond_yield_daily", ("tenor_years",), {"maturity_yield_pct"}),
        ("cn_stock_market_cap_daily", ("exchange",), {"total_market_cap_cny", "circulating_market_cap_cny"}),
    ):
        daily_table(table, group, fields=fields, date_column="emotion_date" if "emotion_daily" in table else "trade_date")
    catalog_tables["fund_purchase_limit_daily_data"] = {"research": "Daily aggregate fields in quant_index_dashboard_daily are scanned",
        "blocked_reason": "Individual fund flags are not a single daily market series; raw product-key rows repeat the same date across funds and must not be treated as independent time observations"}
    margin = read_rows(db, "margin_trading_daily_data")
    finance_pct = None
    for field in ("financing_balance", "financing_net_buy_amount", "financing_buy_amount", "securities_lending_balance", "margin_balance"):
        windows = (1, 5, 7, 14, 20, 30, 60, 120) if field == "financing_net_buy_amount" else (1,)
        for n in windows:
            values = known_financing_values(margin, b.frame.index, field, n)
            rows = [{"source_date": d, "available_at": d + "T09:30:00+08:00", "value": v}
                    for d, v in zip(b.frame.index, values)]
            key = f"known-margin-{field}-{n}d"
            b.add(key, f"沪深{field}:{n}D(上个实际交易日已披露)", "known-financing", "margin_trading_daily_data:SSE+SZSE",
                  rows, unit="亿元", publication="Exchange rule publication deadline before next actual trading session open; bound, not captured timestamp", max_age_days=0)
            if field == "financing_net_buy_amount" and n == 30:
                finance_pct = prior_percentile(values)
    if finance_pct is not None:
        close = b.frame.close
        strength = (close - close.rolling(60).min()) / (close.rolling(60).max() - close.rolling(60).min()).replace(0, np.nan) * 100
        realized = np.log(close / close.shift(1)).rolling(20).std(ddof=0)
        parts = pd.DataFrame({"rsi": b.columns["csi500-rsi14"], "momentum": prior_percentile(close.pct_change(20, fill_method=None)),
                              "strength": strength, "low_volatility": 100 - pd.Series(prior_percentile(realized), index=b.frame.index),
                              "financing": finance_pct}, index=b.frame.index)
        core = parts.mean(axis=1).where(parts.notna().all(axis=1))
        b.add("known-core", "中证500可知时点核心情绪研究版", "known-core", "Causal price+T-1 financing components",
              [{"source_date": d, "available_at": d + "T18:00:00+08:00", "value": v} for d, v in zip(b.frame.index, core)],
              unit="分", publication="Same-day prices plus previous-session official financing; not the unaudited stored core", max_age_days=0)
    for table in ("index_us_credit_spread_daily", "index_us_treasury_yield_daily"):
        daily_table(table, eligible=True, time_column="available_at", publication="Stored source available_at")
    daily_table("global_risk_asset_daily", ("asset_code",), eligible=True, time_column="available_at",
                fields={"close_value", "volume"}, publication="Stored actual source available_at")
    daily_table("a_share_turnover_concentration_daily", eligible=True, time_column="available_at",
                fields={"top5_pct", "top1_pct", "top1_raw_pct"}, publication="Stored source available_at")
    bank = read_rows(db, "cn_bank_liquidity_daily")
    catalog_tables["cn_bank_liquidity_daily"] = {"rows": len(bank), "research": "Source-specific publication times"}
    bank_fields = {
        "frr_available_at": ("fr001_pct", "fr007_pct", "fdr001_pct", "fdr007_pct"),
        "closing_repo_available_at": ("dr001_weighted_pct", "dr007_weighted_pct", "r001_weighted_pct", "r007_weighted_pct"),
        "chinabond_available_at": ("bank_bond_aaa_1y_yield_pct", "cgb_1y_yield_pct", "factor_bank_funding_spread_bp", "pct_bank_funding_spread"),
        "pbc_available_at": ("reverse_repo_injection_cny", "reverse_repo_maturity_cny", "reverse_repo_net_cny", "reverse_repo_net_5d_cny", "reverse_repo_net_20d_cny"),
    }
    for time_field, fields in bank_fields.items():
        for field in fields:
            b.add("bank-" + field, field, "bank:" + time_field, "cn_bank_liquidity_daily",
                  [{"source_date": r["trade_date"], "available_at": r.get(time_field), "value": r.get(field)} for r in bank], publication=time_field)
    for field in ("liquidity_tightness_score", "factor_fdr007_policy_spread_bp", "factor_overnight_pressure_bp", "factor_nonbank_layering_bp", "pct_fdr007_policy_spread", "pct_overnight_pressure", "pct_nonbank_layering"):
        observations = []
        for r in bank:
            times = [r.get(k) for k in ("frr_available_at", "chinabond_available_at", "reverse_repo_7d_policy_available_at")]
            observations.append({"source_date": r["trade_date"], "available_at": max(times) if all(times) else None, "value": r.get(field)})
        b.add("bank-" + field, field, "bank:core", "cn_bank_liquidity_daily", observations, publication="Latest required component available_at")
    daily_table("cn_household_deposit_monthly", date_column="period_end", frequency="monthly")
    daily_table("cn_pbc_liquidity_tool_monthly", ("tool_type",), eligible=True, time_column="published_at", date_column="period_end", frequency="monthly", publication="Official published_at")

    print("reading quant_index_dashboard_daily", flush=True)
    schema = db.execute(text("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='quant_index_dashboard_daily'")).all()
    dashboard_fields = {c for c, kind in schema if kind in {"decimal", "float", "double", "int", "bigint", "smallint", "tinyint"}} | {"index_code", "trade_date", "risk_as_of_at", "exchange_option_pc_json", "option_vix_json"}
    dashboards = read_rows(db, "quant_index_dashboard_daily", fields=dashboard_fields)
    catalog_tables["quant_index_dashboard_daily"] = {"rows": len(dashboards), "research": "All numeric fields and source-specific option JSON"}
    groups = {}
    for r in dashboards:
        for field, value in r.items():
            if field in {"id", "emotion_value", "main_basis", "month_basis"}:
                continue
            if isinstance(value, (int, float)) or value.__class__.__name__ == "Decimal":
                groups.setdefault((r["index_code"], field), []).append({"source_date": r["trade_date"], "available_at": r.get("risk_as_of_at") if field.startswith("risk_") else None, "value": value})
    for (index, field), rows in groups.items():
        derivative = field.startswith(("cffex_", "basis_", "option_"))
        listed = {"sh000905": "2015-04-16", "sh000852": "2022-07-22", "sh000016": "2015-04-16", "sh000300": "2010-04-16"}.get(index, "9999")
        if derivative:
            rows = [dict(r, available_at=str(r["source_date"])[:10] + "T18:00:00+08:00") for r in rows if str(r["source_date"])[:10] >= listed]
        # Risk composites include financing and vintage-sensitive inputs; a
        # calculation timestamp alone does not certify those components.
        b.add(f"dashboard-{index}-{field}", f"{index}:{field}", f"dashboard:{index}:" + field.split("_")[0],
              "quant_index_dashboard_daily", rows, eligible=derivative,
              reason="Composite underlying publication/vintage audit incomplete" if not derivative else "",
              publication="Domestic derivatives after close" if derivative else "Diagnostic only", max_age_days=0)
    print("scanned dashboard numeric fields", len(b.catalog), flush=True)
    def obj(raw):
        return raw if isinstance(raw, dict) else json.loads(raw or "{}")
    for source in ("sse:510500", "szse:159922"):
        for json_field, family in (("exchange_option_pc_json", "option-price-flow"), ("option_vix_json", "option-volatility")):
            groups = {}
            for r in dashboards:
                if r["index_code"] != INDEX_CODE or str(r["trade_date"])[:10] < "2022-09-19":
                    continue
                payload = obj(r.get(json_field)).get(source, {})
                for field, value in option_numeric_fields(payload):
                    groups.setdefault(field, []).append({"source_date": r["trade_date"], "available_at": str(r["trade_date"])[:10] + "T18:00:00+08:00", "value": value})
            for field, rows in groups.items():
                b.add(f"option-{source}-{json_field}-{field}", f"{source}:{field}", family + ":" + source,
                      f"quant_index_dashboard_daily.{json_field}:{source}", rows, publication="Domestic listed ETF option closing quote", max_age_days=0)
    daily_table("option_exchange_daily_stats", ("exchange", "underlying_code"), eligible=True, publication="Official domestic option session totals")
    daily_table("index_qvix_daily_data", ("index_code",), eligible=True, fields={"close_price", "high_price", "low_price", "open_price"}, publication="Domestic closing volatility index")

    # True numeric IC contracts, chosen using contemporaneous open interest.
    futures = read_rows(db, "futures_daily_data", "WHERE symbol REGEXP '^IC[0-9]{4}$'")
    main = {}
    for r in futures:
        d = str(r["trade_date"])[:10]
        if d < "2015-04-16" or number(r.get("open_interest")) is None:
            continue
        if d not in main or (float(r["open_interest"]), r["symbol"]) > (float(main[d]["open_interest"]), main[d]["symbol"]):
            main[d] = r
    basis = []
    for d, r in sorted(main.items()):
        if d in b.frame.index and number(r["close_price"]) is not None and b.frame.loc[d, "close"] > 0:
            basis.append({"source_date": d, "available_at": d + "T18:00:00+08:00", "value": (float(r["close_price"]) / b.frame.loc[d, "close"] - 1) * 100})
    b.add("ic-main-basis-rate", "真实IC持仓主力期现差率", "ic-basis", "futures_daily_data:numeric IC max OI", basis, unit="%", publication="Actual numeric contract closing quote", max_age_days=0)
    catalog_tables["futures_daily_data"] = {"rows": len(futures), "research": "Actual max-OI numeric IC basis; no synthetic contract"}

    observations = [dict(r) for r in db.execute(text("SELECT o.series_key,o.period_end,o.basis_version,o.value,o.unit,r.replay_available_at,r.available_at,r.replay_eligible,r.vintage_status,r.revision_number FROM cn_macro_observation o JOIN cn_macro_release r ON r.release_id=o.release_id ORDER BY r.available_at")).mappings()]
    macro = {}
    for r in observations:
        macro.setdefault((r["series_key"], r["basis_version"]), []).append(r)
    for (series, basis_version), rows in macro.items():
        eligible = all(r["replay_eligible"] and r["revision_number"] == 1 and r.get("replay_available_at") for r in rows)
        b.add(f"macro-{series}-{basis_version}", f"{series}:{basis_version}", "macro:" + series.split(".")[0], "cn_macro_observation+cn_macro_release",
              [{"source_date": r["period_end"], "available_at": r["replay_available_at"], "value": r["value"]} for r in rows],
              eligible=eligible, reason="First-release vintage or publication time not independently replayable" if not eligible else "",
              frequency="monthly", unit=rows[0]["unit"], publication="Verified replay_available_at" if eligible else "Diagnostic only", max_age_days=180)
    catalog_tables["cn_macro_observation"] = {"rows": len(observations), "research": "All series, M1 bases separated; monthly observations not daily ranks"}
    tables = [r[0] for r in db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE()"))]
    for table in tables:
        if table not in catalog_tables and any(s in table for s in ("daily_data", "minute_data", "position", "liquidity", "risk_asset")):
            catalog_tables[table] = {"research": "detail/explanatory inventory", "blocked_reason": "Contract/stock/minute detail needs a stable historical aggregation and constituent/publication contract; existing derived series are researched separately"}
    frame, catalog = b.finish()
    print("feature matrix complete", frame.shape, flush=True)
    return frame, catalog, catalog_tables


def config_fingerprint(rules):
    return sha256(json.dumps(rules, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def selected_features(candles, source_rows, fields=None):
    """The small production path never loads the all-market research matrix."""
    fields = PUBLIC_FIELDS if fields is None else fields
    b = Builder(candles)
    recipes = {}
    for key, meta in fields.items():
        if meta.get("base_field"):
            continue
        recipe = meta["recipe"]
        identity = json.dumps(recipe, sort_keys=True)
        recipes.setdefault(identity, (meta, recipe))
    for meta, recipe in recipes.values():
        if recipe["kind"] == "price":
            b.price_features()
            continue
        rows = source_rows[recipe["source_key"]]
        if recipe["kind"] == "option":
            rows = option_source_rows(rows, recipe)
        observations = [{"source_date": row[recipe["date_column"]],
                         "available_at": row.get(recipe["time_column"]) if recipe.get("time_column")
                         else str(row[recipe["date_column"]])[:10] + "T18:00:00+08:00",
                         "value": row.get(recipe["column"])} for row in rows]
        b.add(recipe["key"], recipe["label"], recipe["family"], recipe["source"], observations,
              unit=recipe["unit"], publication=meta["publication"],
              max_age_days=recipe.get("max_age_days", 0))
    frame, _ = b.finish()
    for key, meta in fields.items():
        if meta.get("base_field"):
            frame[key] = (frame.index >= meta["first_available_date"]).astype(float)
    return frame[list(fields)]


def option_source_rows(rows, recipe):
    """Keep exchange/ETF sources separate and omit pre-listing observations."""
    result = []
    for row in rows:
        if str(row[recipe["date_column"]])[:10] < recipe["listed_since"]:
            continue
        payload = row.get(recipe["column"])
        if isinstance(payload, str):
            payload = json.loads(payload or "{}")
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("Invalid CSI500 option payload")
        source = (payload or {}).get(recipe["option_source"], {})
        if not isinstance(source, dict):
            raise ValueError("Invalid CSI500 option source")
        result.append({**row, recipe["column"]: source.get(recipe["value_field"])})
    return result


def feature_points(db):
    if not PUBLIC_FIELDS:
        return []
    from app.core.redis_client import redis_client
    queries = {}
    for meta in PUBLIC_FIELDS.values():
        recipe = meta.get("recipe")
        if recipe and recipe["kind"] != "price":
            queries[recipe["source_key"]] = recipe
    queries["target"] = {"table": "index_daily_data", "where": "index_code=:code",
                         "params": {"code": INDEX_CODE}, "date_column": "trade_date"}
    revisions = []
    for key, recipe in sorted(queries.items()):
        table = recipe["table"]
        if not re.fullmatch(r"[a-z0-9_]+", table):
            raise ValueError("Invalid selected feature table")
        row = db.execute(text(f"SELECT MAX(updated_at),COUNT(*) FROM `{table}` WHERE {recipe['where']}"),
                         recipe["params"]).one()
        revisions.append((key, *row))
    cache_key = "quant:csi500-swing:" + VERSION + ":" + sha256(str((PUBLIC_FIELDS, revisions)).encode()).hexdigest()[:24]
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    candles = [dict(row) for row in db.execute(text("""SELECT trade_date,open_price AS open,
        high_price AS high,low_price AS low,close_price AS close FROM index_daily_data
        WHERE index_code=:code ORDER BY trade_date"""), {"code": INDEX_CODE}).mappings()]
    inputs = {}
    for key, recipe in queries.items():
        if key == "target":
            continue
        columns = list(dict.fromkeys([recipe["date_column"], recipe["column"],
                                      *([recipe["time_column"]] if recipe.get("time_column") else [])]))
        if any(not re.fullmatch(r"[a-z0-9_]+", column) for column in columns):
            raise ValueError("Invalid selected feature column")
        inputs[key] = [dict(row) for row in db.execute(text(
            "SELECT " + ",".join(f"`{column}`" for column in columns) + f" FROM `{recipe['table']}`"
            + f" WHERE {recipe['where']} ORDER BY `{recipe['date_column']}`"), recipe["params"]).mappings()]
    frame = selected_features(candles, inputs)
    points = [{"trade_date": day, "values": {key: number(row[key]) for key in PUBLIC_FIELDS},
               "as_of_at": day + "T22:30:00+08:00"} for day, row in frame.iterrows()]
    redis_client.set(cache_key, json.dumps(points, allow_nan=False), ex=1800)
    return points


def rules_status(values, groups):
    """Three-valued OR/AND knowledge used for coverage, not the trade engine."""
    unknown = False
    for group in groups:
        results = []
        for item in group["conditions"]:
            value, threshold = number(values.get(item.get("field"))), number(item.get("value"))
            if item.get("type") != "numeric" or value is None or threshold is None:
                results.append(None)
                continue
            operator = item.get("operator")
            results.append({"gte": value >= threshold, "lte": value <= threshold,
                            "gt": value > threshold, "lt": value < threshold}.get(operator))
        if all(result is True for result in results):
            return True
        if not any(result is False for result in results):
            unknown = True
    return None if unknown else False


def option_coverage_start(used_fields, start_date):
    starts = [PUBLIC_FIELDS[key]["first_available_date"] for key in used_fields if key in PUBLIC_FIELDS
              and PUBLIC_FIELDS[key].get("recipe", {}).get("kind") == "option"]
    if not starts:
        return ""
    return max([str(start_date or ""), *starts])
