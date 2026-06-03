from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import itertools
import json
import math
import sys
from functools import partial
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.models.quant_strategy_config import QuantStrategyConfig  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.quant_service import QuantService  # noqa: E402


print = partial(print, flush=True)

TARGET_MARKET = "cn"
TARGET_CODE = "sh000852"
TARGET_NAME = "中证1000"
STRATEGY_PREFIX = "中证1000波段高点"
TRAIN_START = pd.Timestamp("2025-01-01")
TRAIN_END = pd.Timestamp("2026-03-23")
CURRENT_SEGMENT_START = pd.Timestamp("2026-03-23")
EXCLUDED_SEGMENTS = (
    ("旧段4", pd.Timestamp("2025-09-04"), pd.Timestamp("2025-10-09")),
    ("旧段6", pd.Timestamp("2026-02-02"), pd.Timestamp("2026-02-27")),
)
WINDOWS = (5, 7, 14, 20, 30, 60, 120)
REPORT_PATH = Path("/private/tmp/csi1000_top_blue_strategy_report.json")

DEFAULT_INDICATOR_PARAMS = {
    "ma": {"periods": [5, 10, 20, 60]},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "kdj": {"period": 9, "kSmoothing": 3, "dSmoothing": 3},
    "wr": {"period": 14},
    "rsi": {"period": 14},
    "boll": {"period": 20, "multiplier": 2},
}


def configure_from_args(argv: list[str] | None = None) -> None:
    global TARGET_CODE, TARGET_NAME, STRATEGY_PREFIX, REPORT_PATH

    parser = argparse.ArgumentParser(description="Generate index top-zone blue filter strategies.")
    parser.add_argument("--target-code", default=TARGET_CODE, help="Index code used in index_daily_data.")
    parser.add_argument("--target-name", default=TARGET_NAME, help="Index name used in quant_index_dashboard_daily.")
    parser.add_argument(
        "--strategy-prefix",
        default=None,
        help="Prefix for saved strategy names. Defaults to '<target-name>波段高点'.",
    )
    parser.add_argument(
        "--report-path",
        default=str(REPORT_PATH),
        help="Output JSON report path.",
    )
    args = parser.parse_args(argv)

    TARGET_CODE = args.target_code
    TARGET_NAME = args.target_name
    STRATEGY_PREFIX = args.strategy_prefix or f"{TARGET_NAME}波段高点"
    REPORT_PATH = Path(args.report_path)


@dataclass(frozen=True)
class FeatureSpec:
    feature: str
    field_key: str
    label: str
    family: str
    emotion_scope: bool = False


@dataclass(frozen=True)
class Rule:
    spec: FeatureSpec
    operator: str
    threshold: float

    @property
    def key(self) -> tuple[str, str, float]:
        return (self.spec.field_key, self.operator, round(float(self.threshold), 10))

    @property
    def label(self) -> str:
        symbol = ">" if self.operator == "gt" else "<"
        return f"{self.spec.label} {symbol} {format_number(self.threshold)}"

    def to_condition(self) -> dict:
        return {
            "type": "numeric",
            "field": self.spec.field_key,
            "operator": self.operator,
            "value": round(float(self.threshold), 6),
        }


@dataclass
class Combo:
    rules: tuple[Rule, ...]
    mask: pd.Series
    metrics: dict

    @property
    def key(self) -> tuple[tuple[str, str, float], ...]:
        return tuple(rule.key for rule in self.rules)

    @property
    def label(self) -> str:
        return " AND ".join(rule.label for rule in self.rules)


def format_number(value: float) -> str:
    if not np.isfinite(value):
        return "-"
    abs_value = abs(value)
    if abs_value >= 10000:
        return f"{value:.0f}"
    if abs_value >= 100:
        return f"{value:.1f}"
    if abs_value >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def format_pct(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "-"
    return f"{value * 100:.2f}%"


def fetch_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    db = SessionLocal()
    try:
        rows = db.execute(text(sql), params or {}).mappings().all()
        return pd.DataFrame([dict(row) for row in rows])
    finally:
        db.close()


def calculate_ema(values: pd.Series, period: int) -> pd.Series:
    arr = values.astype(float).to_numpy()
    if len(arr) == 0:
        return pd.Series([], dtype=float, index=values.index)
    out = np.zeros(len(arr), dtype=float)
    multiplier = 2 / (period + 1)
    out[0] = arr[0]
    for index in range(1, len(arr)):
        out[index] = arr[index] * multiplier + out[index - 1] * (1 - multiplier)
    return pd.Series(out, index=values.index)


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["close_price"].astype(float)
    high = df["high_price"].astype(float)
    low = df["low_price"].astype(float)

    ema_fast = calculate_ema(close, 12)
    ema_slow = calculate_ema(close, 26)
    dif = ema_fast - ema_slow
    dif.iloc[:25] = np.nan
    dea = pd.Series(np.nan, index=df.index, dtype=float)
    seed_index = None
    for index in range(25, len(df)):
        window = dif.iloc[index - 8 : index + 1]
        if len(window) == 9 and window.notna().all():
            dea.iloc[index] = window.mean()
            seed_index = index
            break
    if seed_index is not None:
        multiplier = 2 / (9 + 1)
        for index in range(seed_index + 1, len(df)):
            if np.isfinite(dif.iloc[index]) and np.isfinite(dea.iloc[index - 1]):
                dea.iloc[index] = dif.iloc[index] * multiplier + dea.iloc[index - 1] * (1 - multiplier)
    df["macd_dif"] = dif
    df["macd_dea"] = dea
    df["macd_histogram"] = 2 * (dif - dea)

    k_values = np.full(len(df), np.nan)
    d_values = np.full(len(df), np.nan)
    j_values = np.full(len(df), np.nan)
    prev_k = 50.0
    prev_d = 50.0
    for index in range(8, len(df)):
        highest = high.iloc[index - 8 : index + 1].max()
        lowest = low.iloc[index - 8 : index + 1].min()
        denominator = highest - lowest
        rsv = 50.0 if denominator == 0 else (close.iloc[index] - lowest) / denominator * 100
        cur_k = (2 * prev_k + rsv) / 3
        cur_d = (2 * prev_d + cur_k) / 3
        cur_j = 3 * cur_k - 2 * cur_d
        k_values[index] = cur_k
        d_values[index] = cur_d
        j_values[index] = cur_j
        prev_k = cur_k
        prev_d = cur_d
    df["kdj_k"] = k_values
    df["kdj_d"] = d_values
    df["kdj_j"] = j_values

    wr_values = np.full(len(df), np.nan)
    for index in range(13, len(df)):
        highest = high.iloc[index - 13 : index + 1].max()
        lowest = low.iloc[index - 13 : index + 1].min()
        denominator = highest - lowest
        wr_values[index] = 0.0 if denominator == 0 else (highest - close.iloc[index]) / denominator * 100
    df["wr_14"] = wr_values

    rsi_values = np.full(len(df), np.nan)
    if len(df) > 14:
        gains = 0.0
        losses = 0.0
        for index in range(1, 15):
            change = close.iloc[index] - close.iloc[index - 1]
            if change >= 0:
                gains += change
            else:
                losses += abs(change)
        avg_gain = gains / 14
        avg_loss = losses / 14
        rsi_values[14] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        for index in range(15, len(df)):
            change = close.iloc[index] - close.iloc[index - 1]
            gain = max(change, 0.0)
            loss = max(-change, 0.0)
            avg_gain = (avg_gain * 13 + gain) / 14
            avg_loss = (avg_loss * 13 + loss) / 14
            rsi_values[index] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    df["rsi_14"] = rsi_values
    return df


def build_up_segments(
    df: pd.DataFrame,
    half_window: int = 10,
    min_gain: float = 0.06,
    min_days: int = 10,
    split_drawdown: float = 0.08,
) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    close = df["close_price"].astype(float).reset_index(drop=True)
    roll_max = close.rolling(half_window * 2 + 1, center=True, min_periods=half_window + 1).max()
    roll_min = close.rolling(half_window * 2 + 1, center=True, min_periods=half_window + 1).min()
    extrema: list[dict] = []
    for index, value in close.items():
        if not np.isfinite(value):
            continue
        if value == roll_min.iloc[index]:
            extrema.append({"idx": index, "type": "low", "price": value})
        if value == roll_max.iloc[index]:
            extrema.append({"idx": index, "type": "high", "price": value})
    extrema.sort(key=lambda item: (item["idx"], 0 if item["type"] == "low" else 1))

    alternating: list[dict] = []
    for item in extrema:
        if not alternating or alternating[-1]["type"] != item["type"]:
            alternating.append(item)
            continue
        previous = alternating[-1]
        if item["type"] == "low" and item["price"] < previous["price"]:
            alternating[-1] = item
        elif item["type"] == "high":
            previous_low = next((candidate for candidate in reversed(alternating[:-1]) if candidate["type"] == "low"), None)
            if previous_low is not None and item["idx"] > previous["idx"]:
                trough_slice = close.iloc[previous["idx"] + 1 : item["idx"] + 1]
                if not trough_slice.empty:
                    trough_idx = int(trough_slice.idxmin())
                    trough_price = float(close.iloc[trough_idx])
                    previous_gain = previous["price"] / previous_low["price"] - 1
                    previous_drawdown = trough_price / previous["price"] - 1
                    previous_calendar_days = (
                        pd.Timestamp(df.loc[previous["idx"], "trade_date"])
                        - pd.Timestamp(df.loc[previous_low["idx"], "trade_date"])
                    ).days
                    if (
                        trough_idx > previous["idx"]
                        and (previous["idx"] - previous_low["idx"] >= min_days or previous_calendar_days >= min_days)
                        and previous_gain >= min_gain
                        and previous_drawdown <= -split_drawdown
                    ):
                        alternating.append({"idx": trough_idx, "type": "low", "price": trough_price})
                        alternating.append(item)
                        continue
            if item["price"] > previous["price"]:
                alternating[-1] = item

    labeled = df.copy()
    labeled["segment_id"] = np.nan
    labeled["segment_low_date"] = pd.NaT
    labeled["segment_high_date"] = pd.NaT
    labeled["segment_gain"] = np.nan
    labeled["remaining_upside_share"] = np.nan
    labeled["topzone_20"] = False
    labeled["topzone_10"] = False

    segment_id = 0
    for low, high in zip(alternating, alternating[1:]):
        if low["type"] != "low" or high["type"] != "high":
            continue
        calendar_days = (pd.Timestamp(labeled.loc[high["idx"], "trade_date"]) - pd.Timestamp(labeled.loc[low["idx"], "trade_date"])).days
        if high["idx"] - low["idx"] < min_days and calendar_days < min_days:
            continue
        gain = high["price"] / low["price"] - 1
        if gain < min_gain:
            continue
        move = high["price"] - low["price"]
        if move <= 0:
            continue
        idx_range = list(range(low["idx"], high["idx"] + 1))
        remaining_share = (high["price"] - close.iloc[idx_range]) / move
        segment_id += 1
        labeled.loc[idx_range, "segment_id"] = segment_id
        labeled.loc[idx_range, "segment_low_date"] = labeled.loc[low["idx"], "trade_date"]
        labeled.loc[idx_range, "segment_high_date"] = labeled.loc[high["idx"], "trade_date"]
        labeled.loc[idx_range, "segment_gain"] = gain
        labeled.loc[idx_range, "remaining_upside_share"] = remaining_share.to_numpy()
        labeled.loc[idx_range, "topzone_20"] = remaining_share <= 0.20
        labeled.loc[idx_range, "topzone_10"] = remaining_share <= 0.10
    return labeled


def feature_specs() -> list[FeatureSpec]:
    specs = [
        FeatureSpec("macd_dif", "macd-dif", "MACD DIF", "technical"),
        FeatureSpec("macd_dea", "macd-dea", "MACD DEA", "technical"),
        FeatureSpec("macd_histogram", "macd-histogram", "MACD柱", "technical"),
        FeatureSpec("kdj_k", "kdj-k", "KDJ K", "technical"),
        FeatureSpec("kdj_d", "kdj-d", "KDJ D", "technical"),
        FeatureSpec("kdj_j", "kdj-j", "KDJ J", "technical"),
        FeatureSpec("wr_14", "wr", "WR14", "technical"),
        FeatureSpec("rsi_14", "rsi", "RSI14", "technical"),
        FeatureSpec("emotion_value", "emotion", "情绪指标", "sentiment", True),
        FeatureSpec("breadth_up_pct", "breadth-up-pct", "上涨家数百分比", "sentiment"),
        FeatureSpec("main_basis", "basis-main", "主连期现差", "basis"),
        FeatureSpec("month_basis", "basis-month", "月连期现差", "basis"),
        FeatureSpec("option_pc_current_month", "cn-option-put-call-current", "平值P/C当月", "putcall"),
        FeatureSpec("option_pc_next_month", "cn-option-put-call-next", "平值P/C下月", "putcall"),
        FeatureSpec("option_pc_quarter_1", "cn-option-put-call-quarter-1", "平值P/C季月1", "putcall"),
        FeatureSpec("option_pc_quarter_2", "cn-option-put-call-quarter-2", "平值P/C季月2", "putcall"),
        FeatureSpec("option_volume_pc_ratio", "cn-option-flow-pc-volume", "成交量P/C", "flowpc"),
        FeatureSpec("option_turnover_pc_ratio", "cn-option-flow-pc-turnover", "成交额P/C", "flowpc"),
    ]
    for window in WINDOWS:
        specs.append(
            FeatureSpec(
                f"cffex_top20_net_short_delta_{window}d",
                f"cffex-net-short-top20-delta-{window}d",
                f"前20净空增量{window}D",
                "netshort",
            )
        )
        specs.append(
            FeatureSpec(
                f"cffex_citic_net_short_delta_{window}d",
                f"cffex-net-short-citic-delta-{window}d",
                f"中信净空增量{window}D",
                "netshort",
            )
        )
        specs.append(
            FeatureSpec(
                f"basis_main_delta_{window}d",
                f"basis-main-delta-{window}d",
                f"主连期现差变化{window}D",
                "basisdelta",
            )
        )
        specs.append(
            FeatureSpec(
                f"basis_month_delta_{window}d",
                f"basis-month-delta-{window}d",
                f"月连期现差变化{window}D",
                "basisdelta",
            )
        )
    return specs


def build_dataset() -> pd.DataFrame:
    price = fetch_df(
        """
        SELECT trade_date, open_price, high_price, low_price, close_price
        FROM index_daily_data
        WHERE index_code = :target_code
        ORDER BY trade_date
        """,
        {"target_code": TARGET_CODE},
    )
    dashboard_columns = [
        "emotion_value",
        "main_basis",
        "month_basis",
        "breadth_up_pct",
        "option_pc_current_month",
        "option_pc_next_month",
        "option_pc_quarter_1",
        "option_pc_quarter_2",
        "option_volume_pc_ratio",
        "option_turnover_pc_ratio",
    ]
    for window in WINDOWS:
        dashboard_columns.extend(
            [
                f"cffex_top20_net_short_delta_{window}d",
                f"cffex_citic_net_short_delta_{window}d",
                f"basis_main_delta_{window}d",
                f"basis_month_delta_{window}d",
            ]
        )
    dashboard = fetch_df(
        f"""
        SELECT trade_date, {", ".join(dashboard_columns)}
        FROM quant_index_dashboard_daily
        WHERE index_name = :target_name
        ORDER BY trade_date
        """,
        {"target_name": TARGET_NAME},
    )
    for frame in (price, dashboard):
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    df = price.merge(dashboard, on="trade_date", how="inner")
    numeric_cols = [column for column in df.columns if column != "trade_date"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    df = df.sort_values("trade_date").reset_index(drop=True)
    return build_up_segments(add_technical_indicators(df), half_window=10, min_gain=0.06, min_days=10)


def is_excluded_row(row: pd.Series) -> bool:
    trade_date = row["trade_date"]
    for _label, start, end in EXCLUDED_SEGMENTS:
        if start <= trade_date <= end:
            return True
    segment_low_date = row.get("segment_low_date")
    if pd.notna(segment_low_date) and pd.Timestamp(segment_low_date) >= CURRENT_SEGMENT_START:
        return True
    return trade_date >= CURRENT_SEGMENT_START


def build_training_views(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trainable = df[df["trade_date"] <= TRAIN_END].copy()
    trainable = trainable[~trainable.apply(is_excluded_row, axis=1)].copy()
    final_window = trainable[trainable["trade_date"] >= TRAIN_START].copy()
    emotion_window = final_window.copy()
    return trainable, final_window, emotion_window


def signal_mask(frame: pd.DataFrame, rule: Rule) -> pd.Series:
    series = pd.to_numeric(frame[rule.spec.feature], errors="coerce")
    if rule.operator == "gt":
        return series > rule.threshold
    return series < rule.threshold


def combo_mask(frame: pd.DataFrame, rules: Iterable[Rule]) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for rule in rules:
        mask &= signal_mask(frame, rule)
    return mask.fillna(False)


def target_segment_ids(final_window: pd.DataFrame) -> list[float]:
    segment_ids = final_window.loc[final_window["segment_id"].notna(), "segment_id"].drop_duplicates().tolist()
    return [float(segment_id) for segment_id in segment_ids]


def segment_summary(final_window: pd.DataFrame) -> list[dict]:
    rows = []
    for segment_id in target_segment_ids(final_window):
        segment = final_window[final_window["segment_id"] == segment_id]
        rows.append(
            {
                "segment_id": int(segment_id),
                "low_date": str(pd.Timestamp(segment["segment_low_date"].iloc[0]).date()),
                "high_date": str(pd.Timestamp(segment["segment_high_date"].iloc[0]).date()),
                "gain": float(segment["segment_gain"].iloc[0]),
                "top20_dates": [str(item.date()) for item in segment.loc[segment["topzone_20"], "trade_date"]],
                "top10_dates": [str(item.date()) for item in segment.loc[segment["topzone_10"], "trade_date"]],
            }
        )
    return rows


def evaluate_mask(frame: pd.DataFrame, mask: pd.Series, target_col: str, segment_ids: list[float]) -> dict:
    mask = mask.fillna(False)
    hits = frame[mask].copy()
    if hits.empty:
        return {
            "count": 0,
            "top20_rate": math.nan,
            "top10_rate": math.nan,
            "target_rate": math.nan,
            "avg_remaining": math.nan,
            "median_remaining": math.nan,
            "covered_top20_segments": [],
            "covered_top10_segments": [],
            "target_segments": [],
            "dates": [],
            "target_dates": [],
            "false_dates": [],
        }

    in_segment = hits[hits["segment_id"].notna()]
    top20_hits = hits[hits["topzone_20"]]
    top10_hits = hits[hits["topzone_10"]]
    target_hits = hits[hits[target_col]]
    false_hits = hits[~hits[target_col]]
    return {
        "count": int(len(hits)),
        "top20_rate": float(hits["topzone_20"].mean()),
        "top10_rate": float(hits["topzone_10"].mean()),
        "target_rate": float(hits[target_col].mean()),
        "avg_remaining": float(in_segment["remaining_upside_share"].mean()) if len(in_segment) else math.nan,
        "median_remaining": float(in_segment["remaining_upside_share"].median()) if len(in_segment) else math.nan,
        "covered_top20_segments": sorted(
            int(item) for item in top20_hits["segment_id"].dropna().unique().tolist() if item in segment_ids
        ),
        "covered_top10_segments": sorted(
            int(item) for item in top10_hits["segment_id"].dropna().unique().tolist() if item in segment_ids
        ),
        "target_segments": sorted(
            int(item) for item in target_hits["segment_id"].dropna().unique().tolist() if item in segment_ids
        ),
        "dates": [str(item.date()) for item in hits["trade_date"].tolist()],
        "target_dates": [str(item.date()) for item in target_hits["trade_date"].tolist()],
        "false_dates": [str(item.date()) for item in false_hits["trade_date"].tolist()],
    }


def build_candidates(long_window: pd.DataFrame, final_window: pd.DataFrame, emotion_window: pd.DataFrame) -> list[tuple[Rule, dict]]:
    quantiles_gt = (0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.92)
    quantiles_lt = (0.08, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55)
    candidates: list[tuple[Rule, dict]] = []
    seen: set[tuple[str, str, float]] = set()
    segment_ids = target_segment_ids(final_window)

    for spec in feature_specs():
        if spec.feature not in final_window.columns:
            continue
        scope = emotion_window if spec.emotion_scope else long_window
        values = pd.to_numeric(scope[spec.feature], errors="coerce").dropna()
        min_values = 35 if spec.emotion_scope else 90
        if len(values) < min_values or values.nunique() < 12:
            continue
        for operator, quantiles in (("gt", quantiles_gt), ("lt", quantiles_lt)):
            for quantile in quantiles:
                threshold = float(values.quantile(quantile))
                if not np.isfinite(threshold):
                    continue
                rule = Rule(spec=spec, operator=operator, threshold=threshold)
                if rule.key in seen:
                    continue
                seen.add(rule.key)
                metrics = evaluate_mask(final_window, signal_mask(final_window, rule), "topzone_20", segment_ids)
                if metrics["count"] >= 4:
                    candidates.append((rule, metrics))
    return candidates


def build_rule_pool(candidates: list[tuple[Rule, dict]], limit: int = 56) -> list[Rule]:
    def score(item: tuple[Rule, dict]) -> tuple:
        _rule, metrics = item
        return (
            len(metrics["covered_top20_segments"]),
            metrics["top20_rate"] if np.isfinite(metrics["top20_rate"]) else -1,
            metrics["top10_rate"] if np.isfinite(metrics["top10_rate"]) else -1,
            -(metrics["avg_remaining"] if np.isfinite(metrics["avg_remaining"]) else 99),
            -metrics["count"],
        )

    ranked = sorted(candidates, key=score, reverse=True)
    pool: list[Rule] = []
    pool.extend(rule for rule, _metrics in ranked[:28])
    families = sorted({rule.spec.family for rule, _metrics in candidates})
    for family in families:
        family_ranked = [item for item in ranked if item[0].spec.family == family]
        pool.extend(rule for rule, _metrics in family_ranked[:8])
    dedup: dict[tuple[str, str, float], Rule] = {}
    for rule in pool:
        dedup[rule.key] = rule
    return list(dedup.values())[:limit]


def valid_combo(rules: tuple[Rule, ...]) -> bool:
    if len({rule.spec.feature for rule in rules}) != len(rules):
        return False
    families = [rule.spec.family for rule in rules]
    if len(set(families)) < 2:
        return False
    return all(families.count(family) <= 2 for family in set(families))


def scan_combos(final_window: pd.DataFrame, pool: list[Rule]) -> list[Combo]:
    segment_ids = target_segment_ids(final_window)
    combos: list[Combo] = []
    scanned = 0
    for size in (3, 4):
        rule_iter = itertools.combinations(pool if size == 3 else pool[:48], size)
        for rules in rule_iter:
            scanned += 1
            if scanned % 100000 == 0:
                print(f"  已扫描复合规则 {scanned:,} 个，候选 {len(combos):,} 个...")
            if not valid_combo(rules):
                continue
            mask = combo_mask(final_window, rules)
            metrics = evaluate_mask(final_window, mask, "topzone_20", segment_ids)
            if metrics["count"] < 1:
                continue
            if not metrics["covered_top20_segments"]:
                continue
            if metrics["count"] > 80:
                continue
            if metrics["top20_rate"] < 0.25:
                continue
            combos.append(Combo(rules=rules, mask=mask, metrics=metrics))
    return combos


def combo_sort_key(combo: Combo, target_col: str) -> tuple:
    metrics = combo.metrics
    target_segments = metrics["covered_top10_segments"] if target_col == "topzone_10" else metrics["covered_top20_segments"]
    target_rate = metrics["top10_rate"] if target_col == "topzone_10" else metrics["top20_rate"]
    return (
        len(target_segments),
        target_rate if np.isfinite(target_rate) else -1,
        metrics["top20_rate"] if np.isfinite(metrics["top20_rate"]) else -1,
        -(metrics["avg_remaining"] if np.isfinite(metrics["avg_remaining"]) else 99),
        -len(metrics["false_dates"]),
        -metrics["count"],
    )


def combo_scope(combo: Combo) -> str:
    if any(rule.spec.field_key == "emotion" for rule in combo.rules):
        return "emotion_recent"
    families = {rule.spec.family for rule in combo.rules}
    if families & {"basis", "putcall", "flowpc", "netshort", "basisdelta"}:
        return "mid_derivative"
    return "long_technical"


def combo_shape_key(combo: Combo) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((rule.spec.field_key, rule.operator) for rule in combo.rules))


def history_signal_count(combo: Combo, history_window: pd.DataFrame, before: pd.Timestamp | None = None) -> int:
    mask = combo_mask(history_window, combo.rules)
    if before is not None:
        mask &= history_window["trade_date"] < before
    return int(mask.sum())


def max_same_day_hit(combos: list[Combo]) -> int:
    counts: dict[str, int] = {}
    for combo in combos:
        for trade_date in combo.metrics["dates"]:
            counts[trade_date] = counts.get(trade_date, 0) + 1
    return max(counts.values(), default=0)


def common_false_dates(combos: list[Combo], final_window: pd.DataFrame, target_col: str) -> list[str]:
    if not combos:
        return []
    common_dates = set.intersection(*(set(combo.metrics["dates"]) for combo in combos))
    if not common_dates:
        return []
    target_dates = {
        str(item.date())
        for item in final_window.loc[final_window[target_col], "trade_date"].tolist()
    }
    return sorted(common_dates - target_dates)


def choose_groups(
    combos: list[Combo],
    final_window: pd.DataFrame,
    history_window: pd.DataFrame,
    strict: bool,
) -> tuple[list[Combo], set[int], dict]:
    segment_ids = [int(item) for item in target_segment_ids(final_window)]
    selected: list[Combo] = []
    selected_keys: set[tuple[tuple[str, str, float], ...]] = set()
    selected_shapes: set[tuple[tuple[str, str], ...]] = set()
    fallback_segments: set[int] = set()
    all_segments = set(segment_ids)

    def add_combo(combo: Combo) -> None:
        selected.append(combo)
        selected_keys.add(combo.key)
        selected_shapes.add(combo_shape_key(combo))

    def combo_segments(combo: Combo, target_col: str) -> set[int]:
        return set(combo.metrics["covered_top10_segments"] if target_col == "topzone_10" else combo.metrics["covered_top20_segments"])

    def signal_dates(combo: Combo) -> set[str]:
        return set(combo.metrics["dates"])

    def is_diverse(combo: Combo, relaxed: bool = False) -> bool:
        if not selected:
            return True
        if combo_shape_key(combo) in selected_shapes:
            return False
        combo_rule_fields = {rule.spec.field_key for rule in combo.rules}
        combo_dates = signal_dates(combo)
        for current in selected:
            current_rule_fields = {rule.spec.field_key for rule in current.rules}
            field_overlap = len(combo_rule_fields & current_rule_fields) / max(len(combo_rule_fields | current_rule_fields), 1)
            date_overlap = len(combo_dates & signal_dates(current)) / max(len(combo_dates | signal_dates(current)), 1)
            if not relaxed and field_overlap > 0.65 and date_overlap > 0.80:
                return False
            if relaxed and field_overlap > 0.85 and date_overlap > 0.95:
                return False
        return True

    def add_score(combo: Combo, target_col: str, relaxed: bool = False) -> tuple:
        metrics = combo.metrics
        target_rate = metrics["top10_rate"] if target_col == "topzone_10" else metrics["top20_rate"]
        pre2025_count = history_signal_count(combo, history_window, before=TRAIN_START)
        return (
            is_diverse(combo, relaxed),
            pre2025_count > 0,
            target_rate if np.isfinite(target_rate) else -1,
            metrics["top20_rate"] if np.isfinite(metrics["top20_rate"]) else -1,
            -len(metrics["false_dates"]),
            -(metrics["avg_remaining"] if np.isfinite(metrics["avg_remaining"]) else 99),
            -metrics["count"],
        )

    def quality_floor(combo: Combo, target_col: str) -> bool:
        metrics = combo.metrics
        if target_col == "topzone_10":
            if combo_scope(combo) == "emotion_recent":
                return metrics["top20_rate"] >= 0.75 and metrics["top10_rate"] >= 0.45 and metrics["count"] <= 20
            return metrics["top20_rate"] >= 0.65 and metrics["top10_rate"] >= 0.35 and metrics["count"] <= 35
        return metrics["top20_rate"] >= 0.75 and metrics["count"] <= 24

    def can_add(combo: Combo, relaxed: bool = False) -> bool:
        if combo.key in selected_keys:
            return False
        if not is_diverse(combo, relaxed=relaxed):
            return False
        return True

    def select_from(candidates: list[Combo], target_col: str, limit: int) -> None:
        ranked = sorted(candidates, key=lambda combo: add_score(combo, target_col), reverse=True)
        for combo in ranked:
            if len(selected) >= limit:
                return
            if can_add(combo):
                add_combo(combo)
        for combo in ranked:
            if len(selected) >= limit:
                return
            if can_add(combo, relaxed=True):
                add_combo(combo)

    def add_breakers_for_common_false_dates(candidates: list[Combo], target_col: str, limit: int) -> None:
        def bad_common_dates(items: list[Combo]) -> list[str]:
            bad_dates = set(common_false_dates(items, final_window, "topzone_20"))
            if target_col != "topzone_20":
                bad_dates.update(common_false_dates(items, final_window, target_col))
            return sorted(bad_dates)

        bad_dates = bad_common_dates(selected)
        while bad_dates and len(selected) < limit:
            ranked = sorted(
                [
                    combo
                    for combo in candidates
                    if combo.key not in selected_keys
                    and bad_common_dates([*selected, combo]) != bad_dates
                ],
                key=lambda combo: (
                    -len(bad_common_dates([*selected, combo])),
                    add_score(combo, target_col, relaxed=True),
                ),
                reverse=True,
            )
            if not ranked:
                return
            add_combo(ranked[0])
            bad_dates = bad_common_dates(selected)

    primary_col = "topzone_10" if strict else "topzone_20"
    full_primary = [
        combo
        for combo in combos
        if all_segments <= combo_segments(combo, primary_col) and quality_floor(combo, primary_col)
    ]
    eligible = full_primary
    if strict:
        # 10%严格版优先用top10全段覆盖；为了避免全部规则都由短历史情绪指标控制，
        # 也允许top20全段覆盖且top10表现尚可的中历史衍生指标组作为兜底。
        eligible = [
            combo
            for combo in combos
            if all_segments <= combo_segments(combo, "topzone_20")
            and quality_floor(combo, primary_col)
        ]
        if len(full_primary) < 6:
            fallback_segments = set(segment_ids)

    mid_candidates = [
        combo
        for combo in eligible
        if combo_scope(combo) == "mid_derivative" and history_signal_count(combo, history_window, before=TRAIN_START) > 0
    ]
    emotion_candidates = [combo for combo in eligible if combo_scope(combo) == "emotion_recent"]
    long_candidates = [combo for combo in eligible if combo_scope(combo) == "long_technical"]

    target_limit = 8 if strict else 10
    select_from(mid_candidates, primary_col, limit=4 if strict else 5)
    select_from(long_candidates, primary_col, limit=5 if strict else 6)
    select_from(emotion_candidates, primary_col, limit=min(target_limit, len(selected) + (3 if strict else 3)))
    if len(selected) < (6 if strict else 8):
        select_from([combo for combo in eligible if combo_scope(combo) != "emotion_recent"], primary_col, limit=target_limit)
    if len(selected) < 6:
        select_from(eligible, primary_col, limit=6)
    add_breakers_for_common_false_dates(eligible, primary_col, target_limit)

    diagnostics = {
        "eligible_count": len(eligible),
        "full_primary_count": len(full_primary),
        "selected_scope_counts": {
            str(scope): int(count)
            for scope, count in pd.Series([combo_scope(combo) for combo in selected]).value_counts().items()
        } if selected else {},
        "max_same_day_hit": max_same_day_hit(selected),
        "common_false_dates_top20": common_false_dates(selected, final_window, "topzone_20"),
        "common_false_dates_target": common_false_dates(selected, final_window, primary_col),
        "long_technical_full_coverage_count": len(long_candidates),
        "mid_derivative_full_coverage_count": len(mid_candidates),
        "emotion_recent_full_coverage_count": len(emotion_candidates),
    }
    return selected[:target_limit], fallback_segments, diagnostics


def evaluate_selected(final_window: pd.DataFrame, selected: list[Combo], target_col: str) -> dict:
    segment_ids = target_segment_ids(final_window)
    if not selected:
        return evaluate_mask(final_window, pd.Series(False, index=final_window.index), target_col, segment_ids)
    union_mask = pd.Series(False, index=final_window.index)
    for combo in selected:
        union_mask |= combo.mask
    return evaluate_mask(final_window, union_mask, target_col, segment_ids)


def groups_from_combos(combos: list[Combo]) -> list[dict]:
    return [{"conditions": [rule.to_condition() for rule in combo.rules]} for combo in combos]


def truncate_notes(notes: str) -> str:
    return notes[:990] if len(notes) > 990 else notes


def build_notes(
    name: str,
    metrics: dict,
    selected: list[Combo],
    fallback_segments: set[int],
    segments: list[dict],
    diagnostics: dict,
) -> str:
    coverage = sorted(set(metrics["covered_top20_segments"]))
    segment_hit_parts = []
    for segment in segments:
        segment_id = segment["segment_id"]
        dates = []
        for combo in selected:
            combo_dates = [
                date_text
                for date_text in combo.metrics["target_dates"]
                if segment["low_date"] <= date_text <= segment["high_date"]
            ]
            dates.extend(combo_dates[:2])
        segment_hit_parts.append(f"S{segment_id}:{','.join(sorted(set(dates))[:3]) or '-'}")
    fallback_text = f"; 10%不足用20%兜底段={sorted(fallback_segments)}" if fallback_segments else ""
    common_false_dates_top20 = diagnostics.get("common_false_dates_top20") or []
    if common_false_dates_top20:
        common_false_text = f"共同误命中={len(common_false_dates_top20)}日({','.join(common_false_dates_top20[:3])})"
    else:
        common_false_text = "共同误命中=0日"
    notes = (
        f"自动生成{name}; 分池训练: 中历史衍生指标用自身最长有效历史, 情绪用2025-01-01~2026-03-23; "
        f"排除旧段4(2025-09-04~2025-10-09)、旧段6(2026-02-02~2026-02-27)、当前段>=2026-03-23; "
        f"蓝区n={metrics['count']}, top20={format_pct(metrics['top20_rate'])}, "
        f"top10={format_pct(metrics['top10_rate'])}, 平均剩余={format_pct(metrics['avg_remaining'])}, "
        f"覆盖段={coverage}, {common_false_text}{fallback_text}; 命中: {';'.join(segment_hit_parts)}"
    )
    return truncate_notes(notes)


def base_payload(name: str, notes: str, groups: list[dict]) -> dict:
    return {
        "name": name,
        "notes": notes,
        "strategy_engine": "snapshot",
        "sequence_mode": "single_target",
        "strategy_type": "index",
        "target_market": TARGET_MARKET,
        "target_code": TARGET_CODE,
        "target_name": TARGET_NAME,
        "indicator_params": DEFAULT_INDICATOR_PARAMS,
        "buy_sequence_groups": [],
        "sell_sequence_groups": [],
        "scan_trade_config": {},
        "blue_filter_groups": groups,
        "red_filter_groups": [],
        "blue_filters": {},
        "red_filters": {},
        "blue_boll_filter": {"gt": None, "lt": None, "intraday_gt": None, "intraday_lt": None},
        "red_boll_filter": {"gt": None, "lt": None, "intraday_gt": None, "intraday_lt": None},
        "signal_buy_color": "blue",
        "signal_sell_color": "red",
        "purple_conflict_mode": "sell_first",
        "start_date": date(2022, 1, 1),
        "scan_start_date": None,
        "scan_end_date": None,
        "buy_position_pct": 1.0,
        "sell_position_pct": 1.0,
        "execution_price_mode": "next_open",
    }


def save_strategy(name: str, payload: dict) -> dict:
    db = SessionLocal()
    try:
        root = db.query(User).filter(User.username == "root").first()
        owner_user_id = int(root.id) if root else 1
        service = QuantService(db)
        existing = (
            db.query(QuantStrategyConfig)
            .filter(QuantStrategyConfig.owner_user_id == owner_user_id, QuantStrategyConfig.name == name)
            .first()
        )
        if existing:
            return service.update_strategy(int(existing.id), payload, owner_user_id)
        return service.create_strategy(payload, owner_user_id)
    finally:
        db.close()


def report_combo(combo: Combo, history_window: pd.DataFrame) -> dict:
    return {
        "label": combo.label,
        "training_scope": combo_scope(combo),
        "conditions": [rule.to_condition() for rule in combo.rules],
        "count": combo.metrics["count"],
        "top20_rate": combo.metrics["top20_rate"],
        "top10_rate": combo.metrics["top10_rate"],
        "avg_remaining": combo.metrics["avg_remaining"],
        "pre_2025_signal_count": history_signal_count(combo, history_window, before=TRAIN_START),
        "history_signal_count": history_signal_count(combo, history_window),
        "covered_top20_segments": combo.metrics["covered_top20_segments"],
        "covered_top10_segments": combo.metrics["covered_top10_segments"],
        "target_dates": combo.metrics["target_dates"],
        "false_dates": combo.metrics["false_dates"],
    }


def print_strategy_report(name: str, metrics: dict, combos: list[Combo], segments: list[dict], fallback_segments: set[int]) -> None:
    print(f"\n{name}")
    print(
        f"  总蓝区={metrics['count']}, top20={format_pct(metrics['top20_rate'])}, "
        f"top10={format_pct(metrics['top10_rate'])}, 平均剩余={format_pct(metrics['avg_remaining'])}, "
        f"段覆盖={metrics['covered_top20_segments']}"
    )
    if fallback_segments:
        print(f"  严格版兜底段: {sorted(fallback_segments)}")
    for segment in segments:
        hit_dates = []
        for combo in combos:
            hit_dates.extend(
                date_text
                for date_text in combo.metrics["target_dates"]
                if segment["low_date"] <= date_text <= segment["high_date"]
            )
        print(
            f"  段{segment['segment_id']} {segment['low_date']}->{segment['high_date']} "
            f"涨幅={format_pct(segment['gain'])} 命中={','.join(sorted(set(hit_dates))[:6]) or '-'}"
        )
    for index, combo in enumerate(combos, 1):
        print(
            f"  G{index}: {combo.label}\n"
            f"      n={combo.metrics['count']}, top20={format_pct(combo.metrics['top20_rate'])}, "
            f"top10={format_pct(combo.metrics['top10_rate'])}, 平均剩余={format_pct(combo.metrics['avg_remaining'])}, "
            f"scope={combo_scope(combo)}, 日期={','.join(combo.metrics['target_dates'][:8]) or '-'}"
        )


def main() -> None:
    configure_from_args()
    print(f"[1/6] 读取{TARGET_NAME}行情和看板指标...")
    df = build_dataset()
    long_window, final_window, emotion_window = build_training_views(df)
    segments = segment_summary(final_window)
    print(
        f"  全样本 {df.trade_date.min().date()} ~ {df.trade_date.max().date()}, rows={len(df)}\n"
        f"  长训练 {long_window.trade_date.min().date()} ~ {long_window.trade_date.max().date()}, rows={len(long_window)}\n"
        f"  复核窗口 {final_window.trade_date.min().date()} ~ {final_window.trade_date.max().date()}, rows={len(final_window)}"
    )
    print("  保留上涨段:")
    for segment in segments:
        print(
            f"    段{segment['segment_id']}: {segment['low_date']} -> {segment['high_date']}, "
            f"涨幅={format_pct(segment['gain'])}, top20天数={len(segment['top20_dates'])}, top10天数={len(segment['top10_dates'])}"
        )

    print("[2/6] 生成单指标阈值候选...")
    candidates = build_candidates(long_window, final_window, emotion_window)
    print(f"  单条件候选={len(candidates)}")
    pool = build_rule_pool(candidates)
    print(f"  复合扫描池={len(pool)}")

    print("[3/6] 扫描 3-4 条件复合规则...")
    combos = scan_combos(final_window, pool)
    combos = sorted(combos, key=lambda combo: combo_sort_key(combo, "topzone_20"), reverse=True)
    print(f"  复合候选={len(combos)}")

    print("[4/6] 选择蓝区20%主策略和蓝区10%严格策略...")
    selected20, fallback20, diagnostics20 = choose_groups(combos, final_window, long_window, strict=False)
    selected10, fallback10, diagnostics10 = choose_groups(combos, final_window, long_window, strict=True)
    metrics20 = evaluate_selected(final_window, selected20, "topzone_20")
    metrics10 = evaluate_selected(final_window, selected10, "topzone_10")

    name20 = f"{STRATEGY_PREFIX}-蓝区20%"
    name10 = f"{STRATEGY_PREFIX}-蓝区10%"
    print_strategy_report(name20, metrics20, selected20, segments, fallback20)
    print(f"  诊断: {diagnostics20}")
    print_strategy_report(name10, metrics10, selected10, segments, fallback10)
    print(f"  诊断: {diagnostics10}")

    print("[5/6] 写入已保存策略...")
    payload20 = base_payload(
        name20,
        build_notes(name20, metrics20, selected20, fallback20, segments, diagnostics20),
        groups_from_combos(selected20),
    )
    payload10 = base_payload(
        name10,
        build_notes(name10, metrics10, selected10, fallback10, segments, diagnostics10),
        groups_from_combos(selected10),
    )
    saved20 = save_strategy(name20, payload20)
    saved10 = save_strategy(name10, payload10)
    print(f"  已保存 {name20}: id={saved20['id']}, 蓝色规则组={len(saved20['blue_filter_groups'])}, 红色规则组={len(saved20['red_filter_groups'])}")
    print(f"  已保存 {name10}: id={saved10['id']}, 蓝色规则组={len(saved10['blue_filter_groups'])}, 红色规则组={len(saved10['red_filter_groups'])}")

    print("[6/6] 保存训练报告...")
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target": {"market": TARGET_MARKET, "code": TARGET_CODE, "name": TARGET_NAME},
        "training": {
            "emotion_window": ["2025-01-01", "2026-03-23"],
            "long_window": [str(long_window.trade_date.min().date()), str(long_window.trade_date.max().date())],
            "final_validation_window": ["2025-01-01", "2026-03-23"],
            "excluded_segments": [
                {"label": label, "start": str(start.date()), "end": str(end.date())}
                for label, start, end in EXCLUDED_SEGMENTS
            ],
            "current_segment_excluded_from": str(CURRENT_SEGMENT_START.date()),
            "strategy_display_start_date": "2022-01-01",
            "selection_constraints": {
                "all_groups_cover_all_retained_segments": True,
                "avoid_duplicate_rule_shape": True,
                "avoid_all_group_common_false_dates": True,
                "prefer_mid_history_derivative_groups_with_pre_2025_signals": True,
                "emotion_group_quota_target": "2-3 when eligible",
                "emotion_groups_are_trained_on_short_history_pool": True,
            },
        },
        "segments": segments,
        "strategies": [
            {
                "id": saved20["id"],
                "name": name20,
                "metrics": metrics20,
                "diagnostics": diagnostics20,
                "groups": [report_combo(combo, long_window) for combo in selected20],
            },
            {
                "id": saved10["id"],
                "name": name10,
                "metrics": metrics10,
                "fallback_segments": sorted(fallback10),
                "diagnostics": diagnostics10,
                "groups": [report_combo(combo, long_window) for combo in selected10],
            },
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  报告: {REPORT_PATH}")


if __name__ == "__main__":
    main()
