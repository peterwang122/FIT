from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

REPORT_DIR = REPO_ROOT / "runtime" / "reports" / "vix_option_analysis"
SLIPPAGE = 0.005
ROLLING_WINDOW = 252
ROLLING_MIN_PERIODS = 126
ROLLING_QUANTILES = (0.90, 0.95, 0.975)
HOLDING_DAYS = (1, 2, 3, 5, 10, 15, 20, 30)
MONEYNESS_TARGETS = (-0.10, -0.05, -0.025, 0.0, 0.025, 0.05, 0.10)
REFERENCE_SIGNAL_DATES = (
    pd.Timestamp("2024-10-08"),
    pd.Timestamp("2025-04-07"),
    pd.Timestamp("2026-03-23"),
)
EXPIRY_BUCKETS = (
    ("current", "当月"),
    ("next", "下月"),
    ("quarter_1", "季月1"),
    ("quarter_2", "季月2"),
)


@dataclass(frozen=True)
class ProductSpec:
    product_code: str
    exchange: str
    product_name: str
    kind: str
    underlying_code: str


@dataclass(frozen=True)
class IndexSpec:
    index_name: str
    index_code: str
    qvix_code: str
    absolute_vix_floor: float
    fixed_thresholds: tuple[float, ...]
    products: tuple[ProductSpec, ...]


INDEX_SPECS = (
    IndexSpec(
        "上证50",
        "sh000016",
        "50ETF_QVIX",
        30,
        (30, 35, 40, 45),
        (
            ProductSpec("510050", "SSE", "上证50ETF期权", "etf", "510050"),
            ProductSpec("HO", "CFFEX", "上证50股指期权", "cffex", "sh000016"),
        ),
    ),
    IndexSpec(
        "沪深300",
        "sh000300",
        "300ETF_QVIX",
        25,
        (25, 28, 30, 35),
        (
            ProductSpec("510300", "SSE", "沪深300ETF期权", "etf", "510300"),
            ProductSpec("159919", "SZSE", "沪深300ETF期权", "etf", "159919"),
            ProductSpec("IO", "CFFEX", "沪深300股指期权", "cffex", "sh000300"),
        ),
    ),
    IndexSpec(
        "中证500",
        "sh000905",
        "500ETF_QVIX",
        28,
        (28, 30, 35, 40),
        (
            ProductSpec("510500", "SSE", "中证500ETF期权", "etf", "510500"),
            ProductSpec("159922", "SZSE", "中证500ETF期权", "etf", "159922"),
        ),
    ),
    IndexSpec(
        "科创50",
        "sh000688",
        "KCB_QVIX",
        45,
        (45, 50, 55, 60),
        (
            ProductSpec("588000", "SSE", "科创50ETF期权", "etf", "588000"),
            ProductSpec("588080", "SSE", "科创板50ETF期权", "etf", "588080"),
        ),
    ),
)


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _json_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def sanitize_record(record: dict) -> dict:
    return _json_value(record)


def format_moneyness(value: float) -> str:
    if abs(value) < 1e-9:
        return "平值附近"
    magnitude = f"{abs(value) * 100:g}%"
    side = "高行权价" if value > 0 else "低行权价"
    return f"{side}约{magnitude}"


def format_option_moneyness(value: float, option_type: str) -> str:
    if abs(value) < 1e-9:
        return "平值附近"
    magnitude = f"{abs(value) * 100:g}%"
    is_call = option_type.upper() == "CALL"
    is_itm = value < 0 if is_call else value > 0
    side = "高行权价" if value > 0 else "低行权价"
    return f"{side}约{magnitude}（{'实值' if is_itm else '虚值'}）"


def format_actual_strike_bucket(underlying_price: object, strike_price: object, option_type: str) -> str:
    underlying = _number(underlying_price)
    strike = _number(strike_price)
    if underlying is None or underlying <= 0 or strike is None or strike <= 0:
        return "-"
    distance = strike / underlying - 1
    if abs(distance) < 0.005:
        return "平值附近"
    side = "高行权价" if distance > 0 else "低行权价"
    is_call = option_type.upper() == "CALL"
    is_itm = distance < 0 if is_call else distance > 0
    return f"{side}{abs(distance) * 100:.1f}%（{'实值' if is_itm else '虚值'}）"


def strategy_label(value: str | None) -> str:
    mapping = {
        "long_call": "单买认购",
        "long_put": "单买认沽",
    }
    return mapping.get(str(value or ""), "-")


def contract_month_label(entry_date: pd.Timestamp, contract_month: object) -> str:
    text = str(contract_month or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 6:
        year = int(digits[:4])
        month = int(digits[4:6])
    elif len(digits) == 4:
        year = 2000 + int(digits[:2])
        month = int(digits[2:4])
    else:
        return text or "-"
    if month < 1 or month > 12:
        return text or "-"
    diff = (year - entry_date.year) * 12 + (month - entry_date.month)
    if diff == 0:
        prefix = "当月"
    elif diff == 1:
        prefix = "下月"
    elif month in (3, 6, 9, 12):
        prefix = "季月" if diff <= 6 else "远季月"
    else:
        prefix = f"{diff}个月后" if diff > 1 else "近月"
    return f"{prefix}({year % 100:02d}{month:02d})"


def parse_contract_month(contract_month: object) -> tuple[int, int] | None:
    text = str(contract_month or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 6:
        year = int(digits[:4])
        month = int(digits[4:6])
    elif len(digits) == 4:
        year = 2000 + int(digits[:2])
        month = int(digits[2:4])
    else:
        return None
    if month < 1 or month > 12:
        return None
    return year, month


def contract_month_sort_key(contract_month: object) -> int | None:
    parsed = parse_contract_month(contract_month)
    if parsed is None:
        return None
    year, month = parsed
    return year * 12 + month


def build_expiry_bucket_map(entry_date: pd.Timestamp, contract_months: Iterable[object]) -> dict[int, str]:
    entry_key = entry_date.year * 12 + entry_date.month
    unique_months = sorted(
        {
            key
            for key in (contract_month_sort_key(item) for item in contract_months)
            if key is not None and key >= entry_key
        }
    )
    result: dict[int, str] = {}
    for key in unique_months:
        diff = key - entry_key
        if diff == 0:
            result[key] = "current"
        elif diff == 1:
            result[key] = "next"
    quarter_months = [
        key
        for key in unique_months
        if key not in result and ((key - 1) % 12 + 1) in (3, 6, 9, 12)
    ]
    for index, key in enumerate(quarter_months[:2], start=1):
        result[key] = f"quarter_{index}"
    return result


def detect_threshold_events(
    qvix: pd.DataFrame,
    threshold: pd.Series,
    rule_id: str,
    rule_label: str,
    minimum_signal_value: float | None = None,
) -> list[dict]:
    rows: list[dict] = []
    armed = True
    below_count = 0
    previous_value: float | None = None
    previous_threshold: float | None = None
    for trade_date, value in qvix["close_price"].items():
        current = _number(value)
        current_threshold = _number(threshold.get(trade_date))
        if current is None or current_threshold is None:
            previous_value = current
            previous_threshold = current_threshold
            continue
        effective_threshold = max(current_threshold, minimum_signal_value or current_threshold)
        crossed = (
            previous_value is not None
            and previous_threshold is not None
            and previous_value < effective_threshold
            and current >= effective_threshold
        )
        if armed and crossed:
            rows.append(
                {
                    "signal_date": pd.Timestamp(trade_date),
                    "rule_id": rule_id,
                    "rule_label": rule_label,
                    "vix_close": current,
                    "threshold_value": effective_threshold,
                }
            )
            armed = False
            below_count = 0
        elif not armed:
            below_count = below_count + 1 if current < effective_threshold else 0
            if below_count >= 3:
                armed = True
        previous_value = current
        previous_threshold = current_threshold
    return rows


def detect_absolute_peak_events(
    qvix: pd.DataFrame,
    floor: float,
    rule_id: str,
    rule_label: str,
) -> list[dict]:
    rows: list[dict] = []
    cluster: list[tuple[pd.Timestamp, float]] = []
    below_count = 0
    for trade_date, value in qvix["close_price"].items():
        current = _number(value)
        if current is None:
            continue
        if current >= floor:
            cluster.append((pd.Timestamp(trade_date), current))
            below_count = 0
            continue
        if cluster:
            below_count += 1
            if below_count >= 3:
                peak_date, peak_value = max(cluster, key=lambda item: item[1])
                rows.append(
                    {
                        "signal_date": peak_date,
                        "rule_id": rule_id,
                        "rule_label": rule_label,
                        "vix_close": peak_value,
                        "threshold_value": floor,
                    }
                )
                cluster = []
                below_count = 0
    if cluster:
        peak_date, peak_value = max(cluster, key=lambda item: item[1])
        rows.append(
            {
                "signal_date": peak_date,
                "rule_id": rule_id,
                "rule_label": rule_label,
                "vix_close": peak_value,
                "threshold_value": floor,
            }
        )
    return rows


def build_vix_events(qvix: pd.DataFrame, spec: IndexSpec) -> pd.DataFrame:
    events: list[dict] = []
    close = qvix["close_price"]
    events.extend(
        detect_absolute_peak_events(
            qvix,
            spec.absolute_vix_floor,
            f"absolute-peak-{spec.absolute_vix_floor:g}",
            f"绝对高VIX区间峰值(VIX不低于{spec.absolute_vix_floor:g})",
        )
    )
    history = close.shift(1).rolling(ROLLING_WINDOW, min_periods=ROLLING_MIN_PERIODS)
    for quantile in ROLLING_QUANTILES:
        threshold = history.quantile(quantile)
        events.extend(
            detect_threshold_events(
                qvix,
                threshold,
                f"rolling-{quantile:g}",
                f"滚动{quantile * 100:g}%分位且VIX不低于{spec.absolute_vix_floor:g}",
                spec.absolute_vix_floor,
            )
        )
    for fixed in spec.fixed_thresholds:
        threshold = pd.Series(float(fixed), index=qvix.index)
        events.extend(
            detect_threshold_events(
                qvix,
                threshold,
                f"fixed-{fixed:g}",
                f"VIX收盘不低于{fixed:g}",
                spec.absolute_vix_floor,
            )
        )
    frame = pd.DataFrame(events)
    if frame.empty:
        return frame
    frame["index_name"] = spec.index_name
    return frame.sort_values(["signal_date", "rule_id"]).reset_index(drop=True)


def compute_bottom_metrics(signal_date: pd.Timestamp, prices: pd.Series) -> dict:
    prices = prices.dropna().sort_index()
    if signal_date not in prices.index:
        return {"bottom_status": "incomplete"}
    position = prices.index.get_loc(signal_date)
    if not isinstance(position, (int, np.integer)):
        return {"bottom_status": "incomplete"}
    base = float(prices.iloc[position])
    result: dict[str, object] = {}
    previous = prices.iloc[max(0, position - 59) : position + 1]
    result["prior_60d_drawdown"] = base / float(previous.max()) - 1 if len(previous) else None
    result["prior_20d_return"] = (
        base / float(prices.iloc[position - 20]) - 1 if position >= 20 and float(prices.iloc[position - 20]) > 0 else None
    )
    result["prior_40d_return"] = (
        base / float(prices.iloc[position - 40]) - 1 if position >= 40 and float(prices.iloc[position - 40]) > 0 else None
    )
    prior_20 = result["prior_20d_return"]
    prior_40 = result["prior_40d_return"]
    if prior_20 is not None and float(prior_20) >= 0.03:
        result["trade_direction"] = "bearish"
        result["direction_reason"] = "前20个交易日已经明显上涨，按高位波动处理，优先看认沽"
    elif prior_40 is not None and float(prior_40) >= 0.06:
        result["trade_direction"] = "bearish"
        result["direction_reason"] = "前40个交易日累计涨幅较大，按涨多后的风险释放处理，优先看认沽"
    else:
        result["trade_direction"] = "bullish"
        result["direction_reason"] = "前期没有明显涨多，按下跌或震荡后的恐慌处理，优先看认购"
    for horizon in (5, 10, 20, 40):
        target_position = position + horizon
        result[f"forward_{horizon}d_return"] = (
            float(prices.iloc[target_position]) / base - 1 if target_position < len(prices) else None
        )
    for horizon in (10, 20):
        window = prices.iloc[position : min(len(prices), position + horizon + 1)]
        complete = position + horizon < len(prices)
        result[f"future_{horizon}d_min_return"] = float(window.min()) / base - 1 if complete else None
        result[f"future_{horizon}d_max_return"] = float(window.max()) / base - 1 if complete else None
    min_10 = result.get("future_10d_min_return")
    max_10 = result.get("future_10d_max_return")
    min_20 = result.get("future_20d_min_return")
    max_20 = result.get("future_20d_max_return")
    for tolerance in (0.01, 0.03, 0.05):
        result[f"bottom_hit_{int(tolerance * 100)}pct"] = None
        result[f"top_hit_{int(tolerance * 100)}pct"] = None
    if result["trade_direction"] == "bearish":
        for tolerance in (0.01, 0.03, 0.05):
            result[f"top_hit_{int(tolerance * 100)}pct"] = (
                None
                if max_10 is None or min_20 is None
                else bool(float(max_10) <= tolerance and float(min_20) <= -0.05)
            )
        if result["top_hit_3pct"] is None:
            result["bottom_status"] = "incomplete"
        else:
            result["bottom_status"] = "true_top" if result["top_hit_3pct"] else "false_top"
    else:
        for tolerance in (0.01, 0.03, 0.05):
            result[f"bottom_hit_{int(tolerance * 100)}pct"] = (
                None
                if min_10 is None or max_20 is None
                else bool(float(min_10) >= -tolerance and float(max_20) >= 0.05)
            )
        if result["bottom_hit_3pct"] is None:
            result["bottom_status"] = "incomplete"
        else:
            result["bottom_status"] = "true_bottom" if result["bottom_hit_3pct"] else "false_bottom"
    return result


def is_valid_entry_row(row: pd.Series) -> bool:
    open_price = _number(row.get("open_price"))
    high_price = _number(row.get("high_price"))
    low_price = _number(row.get("low_price"))
    close_price = _number(row.get("close_price"))
    volume = _number(row.get("volume"))
    return bool(
        open_price
        and high_price
        and low_price is not None
        and close_price
        and volume
        and volume > 0
        and high_price >= max(open_price, close_price)
        and low_price <= min(open_price, close_price)
        and low_price >= 0
    )


def select_contract(
    entry_rows: pd.DataFrame,
    entry_date: pd.Timestamp,
    underlying_price: float,
    moneyness: float,
    expiry_bucket: str,
    minimum_expiry: pd.Timestamp,
    option_type: str = "CALL",
) -> pd.Series | None:
    if entry_rows.empty or underlying_price <= 0:
        return None
    bucket_map = build_expiry_bucket_map(entry_date, entry_rows["contract_month"].dropna().unique())
    eligible = entry_rows[
        entry_rows.apply(is_valid_entry_row, axis=1)
        & (entry_rows["option_type"] == option_type.upper())
        & (entry_rows["last_trade_date"] >= minimum_expiry)
    ].copy()
    if eligible.empty:
        return None
    eligible["contract_month_key"] = eligible["contract_month"].map(contract_month_sort_key)
    eligible["expiry_bucket"] = eligible["contract_month_key"].map(bucket_map)
    eligible = eligible[eligible["expiry_bucket"] == expiry_bucket].copy()
    if eligible.empty:
        return None
    target_strike = underlying_price * (1 + moneyness)
    eligible["strike_distance"] = (eligible["strike_price"] - target_strike).abs() / underlying_price
    eligible = eligible.sort_values(
        ["strike_distance", "dte", "volume", "open_interest"],
        ascending=[True, True, False, False],
    )
    return eligible.iloc[0]


def _history_path(
    history: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> pd.DataFrame | None:
    expected = calendar[(calendar >= entry_date) & (calendar <= exit_date)]
    if entry_date not in history.index or exit_date not in history.index:
        return None
    path = history.reindex(expected)
    if path["close_price"].isna().any():
        return None
    return path


def calculate_long_call_trade(
    entry_row: pd.Series,
    history: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    slippage: float = SLIPPAGE,
) -> dict | None:
    path = _history_path(history, calendar, entry_date, exit_date)
    if path is None:
        return None
    entry = float(entry_row["open_price"])
    exit_price = _number(path.loc[exit_date, "close_price"])
    if entry <= 0 or exit_price is None or exit_price <= 0:
        return None
    entry_net = entry * (1 + slippage)
    exit_net = exit_price * (1 - slippage)
    marked = path["close_price"].astype(float) * (1 - slippage)
    marked_returns = marked / entry_net - 1
    return {
        "gross_return": exit_price / entry - 1,
        "net_return": exit_net / entry_net - 1,
        "mae": float(min(0.0, marked_returns.min())),
        "mfe": float(max(0.0, marked_returns.max())),
        "entry_debit": entry_net,
        "exit_value": exit_net,
    }


def calculate_long_put_trade(
    entry_row: pd.Series,
    history: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
    slippage: float = SLIPPAGE,
) -> dict | None:
    return calculate_long_call_trade(entry_row, history, calendar, entry_date, exit_date, slippage)


def sequence_drawdown_units(returns: Iterable[float]) -> float:
    values = np.asarray(list(returns), dtype=float)
    if not len(values):
        return 0.0
    cumulative = np.concatenate(([0.0], np.cumsum(values)))
    peaks = np.maximum.accumulate(cumulative)
    return float(np.max(peaks - cumulative))


CANDIDATE_COLUMNS = [
    "rule_id",
    "rule_label",
    "product_code",
    "product_name",
    "exchange",
    "option_type",
    "strategy_type",
    "dte_bucket",
    "moneyness",
    "moneyness_label",
    "holding_days",
]


def aggregate_outcomes(frame: pd.DataFrame, minimum_trades: int = 5) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for key, group in frame.groupby(CANDIDATE_COLUMNS, dropna=False):
        group = group.sort_values("signal_date")
        if len(group) < minimum_trades:
            continue
        values = group["net_return"].astype(float)
        maes = group["mae"].astype(float)
        rows.append(
            {
                **dict(zip(CANDIDATE_COLUMNS, key)),
                "trade_count": len(group),
                "gross_return_median": float(group["gross_return"].median()),
                "net_return_mean": float(values.mean()),
                "net_return_median": float(values.median()),
                "net_return_p25": float(values.quantile(0.25)),
                "net_return_p10": float(values.quantile(0.10)),
                "win_rate": float((values > 0).mean()),
                "median_mae": float(maes.median()),
                "median_mfe": float(group["mfe"].median()),
                "worst_loss": float(values.min()),
                "sequence_drawdown_units": sequence_drawdown_units(values),
            }
        )
    return pd.DataFrame(rows)


def score_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    score_fields = [
        "net_return_median",
        "net_return_p25",
        "win_rate",
        "median_mae",
    ]
    ranks = [result[field].rank(pct=True, method="average") for field in score_fields]
    ranks.append((-result["sequence_drawdown_units"]).rank(pct=True, method="average"))
    result["balanced_score"] = sum(ranks) / len(ranks)
    defensive = [
        result["net_return_p25"].rank(pct=True),
        result["win_rate"].rank(pct=True),
        result["median_mae"].rank(pct=True),
        (-result["sequence_drawdown_units"]).rank(pct=True),
    ]
    result["defensive_score"] = sum(defensive) / len(defensive)
    return result.sort_values(
        ["balanced_score", "net_return_median", "trade_count"],
        ascending=[False, False, False],
    )


def walk_forward_summary(frame: pd.DataFrame, minimum_history_events: int = 8) -> dict | None:
    if frame.empty:
        return None
    event_dates = sorted(frame["signal_date"].drop_duplicates())
    selected_rows: list[dict] = []
    for index in range(minimum_history_events, len(event_dates)):
        current_date = event_dates[index]
        train = frame[frame["signal_date"] < current_date]
        current = frame[frame["signal_date"] == current_date]
        ranked = score_candidates(aggregate_outcomes(train, minimum_trades=5))
        if ranked.empty or current.empty:
            continue
        current_keys = current[CANDIDATE_COLUMNS].drop_duplicates()
        available = ranked.merge(current_keys, on=CANDIDATE_COLUMNS, how="inner")
        if available.empty:
            continue
        chosen = available.sort_values(
            ["balanced_score", "net_return_median", "trade_count"],
            ascending=[False, False, False],
        ).iloc[0]
        mask = pd.Series(True, index=current.index)
        for column in CANDIDATE_COLUMNS:
            value = chosen[column]
            if pd.isna(value):
                mask &= current[column].isna()
            else:
                mask &= current[column] == value
        test = current[mask]
        if test.empty:
            continue
        outcome = test.iloc[0]
        selected_rows.append(
            {
                "signal_date": current_date,
                **{column: chosen[column] for column in CANDIDATE_COLUMNS},
                "net_return": float(outcome["net_return"]),
                "mae": float(outcome["mae"]),
                "mfe": float(outcome["mfe"]),
            }
        )
    if not selected_rows:
        return None
    result = pd.DataFrame(selected_rows).sort_values("signal_date")
    returns = result["net_return"]
    return {
        "trade_count": len(result),
        "net_return_median": float(returns.median()),
        "net_return_p25": float(returns.quantile(0.25)),
        "net_return_p10": float(returns.quantile(0.10)),
        "win_rate": float((returns > 0).mean()),
        "median_mae": float(result["mae"].median()),
        "worst_loss": float(returns.min()),
        "sequence_drawdown_units": sequence_drawdown_units(returns),
        "events": [sanitize_record(item) for item in selected_rows],
    }


class VixOptionAnalyzer:
    def __init__(self, db):
        self.db = db

    def _read(self, sql: str, params: dict) -> pd.DataFrame:
        return pd.read_sql(text(sql), self.db.connection(), params=params)

    def load_qvix(self, qvix_code: str) -> pd.DataFrame:
        frame = self._read(
            """
            SELECT trade_date, open_price, high_price, low_price, close_price
            FROM index_qvix_daily_data
            WHERE index_code = :code AND close_price > 0
            ORDER BY trade_date
            """,
            {"code": qvix_code},
        )
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        return frame.drop_duplicates("trade_date").set_index("trade_date").sort_index()

    def load_index_prices(self, index_code: str) -> pd.DataFrame:
        frame = self._read(
            """
            SELECT trade_date, open_price, high_price, low_price, close_price
            FROM index_daily_data
            WHERE index_code = :code AND close_price > 0
            ORDER BY trade_date
            """,
            {"code": index_code},
        )
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        return frame.drop_duplicates("trade_date").set_index("trade_date").sort_index()

    def load_product(self, product: ProductSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
        if product.kind == "etf":
            underlying = self._read(
                """
                SELECT trade_date, open_price, high_price, low_price, close_price
                FROM etf_daily_data_sina
                WHERE etf_code = :code AND close_price > 0
                ORDER BY trade_date
                """,
                {"code": product.underlying_code},
            )
            options = self._read(
                """
                SELECT d.contract_code, d.contract_trade_code, d.trade_date,
                       d.contract_month, d.option_type, d.strike_price, d.open_price, d.high_price,
                       d.low_price, d.close_price, d.volume, d.turnover,
                       d.open_interest, i.last_trade_date
                FROM option_exchange_contract_daily_data d
                JOIN option_exchange_contract_info i
                  ON i.exchange = d.exchange AND i.contract_code = d.contract_code
                WHERE d.exchange = :exchange
                  AND d.underlying_code = :code
                  AND i.contract_trade_code REGEXP 'M[0-9]+$'
                ORDER BY d.trade_date, d.contract_code
                """,
                {"exchange": product.exchange, "code": product.product_code},
            )
        else:
            underlying = self.load_index_prices(product.underlying_code).reset_index()
            options = self._read(
                """
                SELECT contract_code, contract_code AS contract_trade_code, trade_date,
                       contract_month, option_type, strike_price, open_price, high_price, low_price,
                       close_price, volume, turnover, open_interest
                FROM option_cffex_rtj_daily_data
                WHERE product_prefix = :code AND option_type IN ('CALL', 'PUT')
                ORDER BY trade_date, contract_code
                """,
                {"code": product.product_code},
            )
            options["last_trade_date"] = options["contract_month"].map(self._cffex_expiry)
        underlying["trade_date"] = pd.to_datetime(underlying["trade_date"])
        underlying = underlying.drop_duplicates("trade_date").set_index("trade_date").sort_index()
        for column in ("trade_date", "last_trade_date"):
            options[column] = pd.to_datetime(options[column])
        options["option_type"] = (
            options["option_type"]
            .astype(str)
            .str.upper()
            .replace({"认购": "CALL", "购": "CALL", "C": "CALL", "认沽": "PUT", "沽": "PUT", "P": "PUT"})
        )
        for column in (
            "strike_price",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "turnover",
            "open_interest",
        ):
            options[column] = pd.to_numeric(options[column], errors="coerce")
        options["dte"] = (options["last_trade_date"] - options["trade_date"]).dt.days
        options = options.drop_duplicates(["trade_date", "contract_code"], keep="last")
        return underlying, options

    @staticmethod
    def _cffex_expiry(contract_month: object) -> pd.Timestamp:
        text_value = str(contract_month or "")
        if len(text_value) != 4 or not text_value.isdigit():
            return pd.NaT
        year = 2000 + int(text_value[:2])
        month = int(text_value[2:])
        first = pd.Timestamp(year=year, month=month, day=1)
        friday_offset = (4 - first.weekday()) % 7
        return first + pd.Timedelta(days=friday_offset + 14)

    def _product_outcomes(
        self,
        spec: IndexSpec,
        product: ProductSpec,
        events: pd.DataFrame,
    ) -> pd.DataFrame:
        underlying, options = self.load_product(product)
        if underlying.empty or options.empty:
            return pd.DataFrame()
        calendar = pd.DatetimeIndex(underlying.index)
        entry_rows_by_date = {date: group.copy() for date, group in options.groupby("trade_date")}
        histories = {
            code: group.set_index("trade_date").sort_index()
            for code, group in options.groupby("contract_code")
        }
        event_context = events.sort_values("signal_date").drop_duplicates("signal_date").set_index("signal_date")
        rows: list[dict] = []
        for signal_date in sorted(events["signal_date"].drop_duplicates()):
            context = event_context.loc[signal_date]
            direction = str(context.get("trade_direction") or "bullish")
            option_type = "PUT" if direction == "bearish" else "CALL"
            later = calendar[calendar > signal_date]
            if not len(later):
                continue
            entry_date = later[0]
            if entry_date not in entry_rows_by_date or entry_date not in underlying.index:
                continue
            underlying_price = _number(underlying.loc[entry_date, "open_price"])
            if underlying_price is None or underlying_price <= 0:
                continue
            entry_rows = entry_rows_by_date[entry_date]
            entry_position = calendar.get_loc(entry_date)
            if not isinstance(entry_position, (int, np.integer)):
                continue
            for holding_days in HOLDING_DAYS:
                exit_position = entry_position + holding_days
                if exit_position >= len(calendar):
                    continue
                exit_date = calendar[exit_position]
                minimum_expiry = exit_date + pd.Timedelta(days=3)
                for expiry_bucket, expiry_label in EXPIRY_BUCKETS:
                    for moneyness in MONEYNESS_TARGETS:
                        long_row = select_contract(
                            entry_rows,
                            entry_date,
                            underlying_price,
                            moneyness,
                            expiry_bucket,
                            minimum_expiry,
                            option_type,
                        )
                        if long_row is None:
                            continue
                        long_code = str(long_row["contract_code"])
                        base = {
                            "index_name": spec.index_name,
                            "signal_date": signal_date,
                            "entry_date": entry_date,
                            "exit_date": exit_date,
                            "product_code": product.product_code,
                            "product_name": product.product_name,
                            "exchange": product.exchange,
                            "option_type": option_type,
                            "dte_bucket": expiry_label,
                            "expiry_bucket": expiry_bucket,
                            "expiry_bucket_label": expiry_label,
                            "entry_dte": int(long_row["dte"]),
                            "moneyness": moneyness,
                            "moneyness_label": format_option_moneyness(moneyness, option_type),
                            "holding_days": holding_days,
                            "long_contract_code": long_code,
                            "long_contract_month": str(long_row["contract_month"]),
                            "contract_month_label": contract_month_label(entry_date, long_row["contract_month"]),
                            "long_strike": float(long_row["strike_price"]),
                            "underlying_entry_price": float(underlying_price),
                            "long_strike_label": format_actual_strike_bucket(
                                underlying_price,
                                long_row["strike_price"],
                                option_type,
                            ),
                        }
                        long_trade = (
                            calculate_long_put_trade if option_type == "PUT" else calculate_long_call_trade
                        )(
                            long_row,
                            histories[long_code],
                            calendar,
                            entry_date,
                            exit_date,
                        )
                        if long_trade:
                            rows.append(
                                {
                                    **base,
                                    "strategy_type": "long_put" if option_type == "PUT" else "long_call",
                                    **long_trade,
                                }
                            )
        return pd.DataFrame(rows)

    def analyze_index(self, spec: IndexSpec) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        qvix = self.load_qvix(spec.qvix_code)
        index_prices = self.load_index_prices(spec.index_code)
        qvix = qvix[qvix.index.isin(index_prices.index)]
        events = build_vix_events(qvix, spec)
        if events.empty:
            return events, pd.DataFrame(), {}
        unique_events = events[["index_name", "signal_date"]].drop_duplicates().copy()
        bottom_rows = [
            {"index_name": spec.index_name, "signal_date": date, **compute_bottom_metrics(date, index_prices["close_price"])}
            for date in unique_events["signal_date"]
        ]
        bottom = pd.DataFrame(bottom_rows)
        events = events.merge(bottom, on=["index_name", "signal_date"], how="left")
        outcome_frames = []
        for product in spec.products:
            print(f"[{spec.index_name}] 分析 {product.exchange}:{product.product_code}", flush=True)
            outcome = self._product_outcomes(spec, product, events)
            if not outcome.empty:
                outcome_frames.append(outcome)
        outcomes = pd.concat(outcome_frames, ignore_index=True) if outcome_frames else pd.DataFrame()
        if outcomes.empty:
            return events, outcomes, {}
        evaluated = events.merge(outcomes, on=["index_name", "signal_date"], how="inner")
        scored = score_candidates(aggregate_outcomes(evaluated))
        summary = self._build_index_summary(spec, events, outcomes, evaluated, scored)
        return events, evaluated, summary

    def _build_index_summary(
        self,
        spec: IndexSpec,
        events: pd.DataFrame,
        outcomes: pd.DataFrame,
        evaluated: pd.DataFrame,
        scored: pd.DataFrame,
    ) -> dict:
        unique_events = events.sort_values("signal_date").drop_duplicates("signal_date")
        complete = unique_events[unique_events["bottom_status"] != "incomplete"]
        recommendation = scored.iloc[0].to_dict() if not scored.empty else None
        defensive = (
            scored.sort_values(["defensive_score", "net_return_p25"], ascending=[False, False]).iloc[0].to_dict()
            if not scored.empty
            else None
        )
        top = scored.head(20)
        stable = {
            "dte_buckets": top["dte_bucket"].value_counts().to_dict() if not top.empty else {},
            "moneyness": top["moneyness_label"].value_counts().to_dict() if not top.empty else {},
            "holding_days": {str(k): int(v) for k, v in top["holding_days"].value_counts().to_dict().items()}
            if not top.empty
            else {},
        }
        threshold_rows = []
        for (rule_id, rule_label), group in events.groupby(["rule_id", "rule_label"]):
            valid = group[group["bottom_status"] != "incomplete"]
            threshold_rows.append(
                {
                    "rule_id": rule_id,
                    "rule_label": rule_label,
                    "event_count": int(group["signal_date"].nunique()),
                    "complete_count": int(valid["signal_date"].nunique()),
                    "bottom_hit_rate_1pct": _mean_bool(valid["bottom_hit_1pct"]),
                    "bottom_hit_rate_3pct": _mean_bool(valid["bottom_hit_3pct"]),
                    "bottom_hit_rate_5pct": _mean_bool(valid["bottom_hit_5pct"]),
                    "top_hit_rate_1pct": _mean_bool(valid["top_hit_1pct"]),
                    "top_hit_rate_3pct": _mean_bool(valid["top_hit_3pct"]),
                    "top_hit_rate_5pct": _mean_bool(valid["top_hit_5pct"]),
                }
            )
        event_best = (
            outcomes.sort_values(["signal_date", "net_return"], ascending=[True, False])
            .drop_duplicates("signal_date")
            .set_index("signal_date")
        )
        reference_checks = []
        for date in REFERENCE_SIGNAL_DATES:
            matched = unique_events[unique_events["signal_date"] == date]
            reference_checks.append(
                {
                    "signal_date": date,
                    "selected": bool(not matched.empty),
                    "vix_close": None if matched.empty else float(matched.iloc[0]["vix_close"]),
                    "rule_labels": "" if matched.empty else " / ".join(sorted(set(matched["rule_label"]))),
                    "trade_direction": "" if matched.empty else str(matched.iloc[0].get("trade_direction") or ""),
                    "direction_reason": "" if matched.empty else str(matched.iloc[0].get("direction_reason") or ""),
                }
            )
        return {
            "index_name": spec.index_name,
            "qvix_code": spec.qvix_code,
            "absolute_vix_floor": spec.absolute_vix_floor,
            "data_start": unique_events["signal_date"].min(),
            "data_end": unique_events["signal_date"].max(),
            "event_count": int(unique_events["signal_date"].nunique()),
            "complete_event_count": int(complete["signal_date"].nunique()),
            "bottom_hit_rate_1pct": _mean_bool(complete["bottom_hit_1pct"]),
            "bottom_hit_rate_3pct": _mean_bool(complete["bottom_hit_3pct"]),
            "bottom_hit_rate_5pct": _mean_bool(complete["bottom_hit_5pct"]),
            "top_hit_rate_1pct": _mean_bool(complete["top_hit_1pct"]),
            "top_hit_rate_3pct": _mean_bool(complete["top_hit_3pct"]),
            "top_hit_rate_5pct": _mean_bool(complete["top_hit_5pct"]),
            "recommendation": sanitize_record(recommendation) if recommendation else None,
            "defensive_recommendation": sanitize_record(defensive) if defensive else None,
            "walk_forward": walk_forward_summary(evaluated),
            "stable_ranges": stable,
            "threshold_performance": threshold_rows,
            "reference_checks": reference_checks,
            "hindsight_best_trade_count": len(event_best),
        }


def _mean_bool(series: pd.Series) -> float | None:
    valid = series.dropna()
    return float(valid.astype(bool).mean()) if len(valid) else None


def build_event_export(events: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events
    grouped_rules = (
        events.groupby(["index_name", "signal_date"], as_index=False)
        .agg(
            rule_ids=("rule_id", lambda values: " / ".join(sorted(set(values)))),
            rule_labels=("rule_label", lambda values: " / ".join(sorted(set(values)))),
            vix_close=("vix_close", "max"),
            threshold_value=("threshold_value", "min"),
            bottom_status=("bottom_status", "first"),
            prior_60d_drawdown=("prior_60d_drawdown", "first"),
            prior_20d_return=("prior_20d_return", "first"),
            prior_40d_return=("prior_40d_return", "first"),
            trade_direction=("trade_direction", "first"),
            direction_reason=("direction_reason", "first"),
            future_10d_min_return=("future_10d_min_return", "first"),
            future_10d_max_return=("future_10d_max_return", "first"),
            future_20d_min_return=("future_20d_min_return", "first"),
            future_20d_max_return=("future_20d_max_return", "first"),
            forward_5d_return=("forward_5d_return", "first"),
            forward_10d_return=("forward_10d_return", "first"),
            forward_20d_return=("forward_20d_return", "first"),
            forward_40d_return=("forward_40d_return", "first"),
            bottom_hit_1pct=("bottom_hit_1pct", "first"),
            bottom_hit_3pct=("bottom_hit_3pct", "first"),
            bottom_hit_5pct=("bottom_hit_5pct", "first"),
            top_hit_1pct=("top_hit_1pct", "first"),
            top_hit_3pct=("top_hit_3pct", "first"),
            top_hit_5pct=("top_hit_5pct", "first"),
        )
    )
    if outcomes.empty:
        return grouped_rules
    best = (
        outcomes.sort_values(["index_name", "signal_date", "net_return"], ascending=[True, True, False])
        .drop_duplicates(["index_name", "signal_date"])
        .rename(
            columns={
                "product_code": "hindsight_product_code",
                "strategy_type": "hindsight_strategy_type",
                "option_type": "hindsight_option_type",
                "dte_bucket": "hindsight_dte_bucket",
                "moneyness_label": "hindsight_moneyness",
                "holding_days": "hindsight_holding_days",
                "contract_month_label": "hindsight_contract_month_label",
                "net_return": "hindsight_net_return",
                "mae": "hindsight_mae",
                "mfe": "hindsight_mfe",
                "long_contract_code": "hindsight_long_contract",
                "long_strike": "hindsight_long_strike",
                "long_strike_label": "hindsight_long_strike_label",
            }
        )
    )
    columns = [
        "index_name",
        "signal_date",
        "entry_date",
        "hindsight_product_code",
        "hindsight_strategy_type",
        "hindsight_option_type",
        "hindsight_dte_bucket",
        "hindsight_contract_month_label",
        "hindsight_moneyness",
        "hindsight_holding_days",
        "hindsight_net_return",
        "hindsight_mae",
        "hindsight_mfe",
        "hindsight_long_contract",
        "hindsight_long_strike",
        "hindsight_long_strike_label",
    ]
    return grouped_rules.merge(best[columns], on=["index_name", "signal_date"], how="left")


def build_overall_conclusion(summaries: list[dict]) -> dict:
    candidates: list[dict] = []
    for item in summaries:
        rec = item.get("recommendation") or {}
        defensive = item.get("defensive_recommendation") or {}
        if not rec:
            continue
        median = _number(rec.get("net_return_median")) or 0.0
        p25 = _number(rec.get("net_return_p25")) or 0.0
        win_rate = _number(rec.get("win_rate")) or 0.0
        mae = _number(rec.get("median_mae")) or 0.0
        worst_loss = _number(defensive.get("worst_loss")) or _number(rec.get("worst_loss")) or 0.0
        score = median * 0.25 + p25 * 0.35 + win_rate * 0.25 + mae * 0.10 + worst_loss * 0.05
        candidates.append(
            {
                "index_name": item.get("index_name"),
                "score": score,
                "recommendation": rec,
                "defensive_recommendation": defensive or None,
                "bottom_hit_rate_3pct": item.get("bottom_hit_rate_3pct"),
                "top_hit_rate_3pct": item.get("top_hit_rate_3pct"),
            }
        )
    if not candidates:
        return {
            "best_index": "-",
            "summary": "样本不足，暂时不能给出优先指数。",
            "rankings": [],
        }
    rankings = sorted(candidates, key=lambda item: item["score"], reverse=True)
    best = rankings[0]
    rec = best["recommendation"] or {}
    defensive = best.get("defensive_recommendation") or {}
    best_text = (
        f"综合收益中位数、25%收益分位、胜率、单笔回撤和最差单笔，当前样本里优先看"
        f"{best['index_name']}对应期权；主模板是{rec.get('product_code', '-')}"
        f"{strategy_label(rec.get('strategy_type'))}，到期选{rec.get('expiry_bucket_label') or rec.get('dte_bucket', '-')}"
        f"，行权选{rec.get('moneyness_label', '-')}，持有{rec.get('holding_days', '-')}个交易日。"
    )
    if defensive:
        best_text += (
            f" 如果更看重回撤，低回撤模板可参考{defensive.get('product_code', '-')}"
            f"{strategy_label(defensive.get('strategy_type'))}，到期选"
            f"{defensive.get('expiry_bucket_label') or defensive.get('dte_bucket', '-')}"
            f"，行权选{defensive.get('moneyness_label', '-')}。"
        )
    return {
        "best_index": best["index_name"],
        "summary": best_text,
        "rankings": [
            {
                "index_name": item["index_name"],
                "score": item["score"],
                "product_code": (item.get("recommendation") or {}).get("product_code"),
                "strategy_type": (item.get("recommendation") or {}).get("strategy_type"),
                "expiry_bucket_label": (item.get("recommendation") or {}).get("expiry_bucket_label")
                or (item.get("recommendation") or {}).get("dte_bucket"),
                "moneyness_label": (item.get("recommendation") or {}).get("moneyness_label"),
                "holding_days": (item.get("recommendation") or {}).get("holding_days"),
                "net_return_median": (item.get("recommendation") or {}).get("net_return_median"),
                "net_return_p25": (item.get("recommendation") or {}).get("net_return_p25"),
                "win_rate": (item.get("recommendation") or {}).get("win_rate"),
                "median_mae": (item.get("recommendation") or {}).get("median_mae"),
            }
            for item in rankings
        ],
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# VIX异常高与底部期权策略分析",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "## 核心结果",
        "",
        f"结论：{report.get('overall_conclusion', {}).get('summary', '-')}",
        "",
        "| 指数 | 绝对VIX地板 | 高VIX事件 | 3%底部命中率 | 长期参数模板 | 持仓 |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for item in report["index_summaries"]:
        rec = item.get("recommendation") or {}
        description = (
            f"{rec.get('product_code', '-')} / {strategy_label(rec.get('strategy_type'))} / "
            f"{rec.get('expiry_bucket_label') or rec.get('dte_bucket', '-')} / {rec.get('moneyness_label', '-')}"
        )
        lines.append(
            f"| {item['index_name']} | {item.get('absolute_vix_floor', '-')} | {item['event_count']} | "
            f"{_pct(item.get('bottom_hit_rate_3pct'))} | {description} | {rec.get('holding_days', '-')}日 |"
        )
    lines += [
        "",
        "说明：长期参数模板描述的是到期月份口径和行权价相对标的哪一档；逐事件CSV里给出当次回望最佳的具体合约月份、合约代码、行权价和实际高/低行权档。本版只做单买期权，不做价差。",
        "",
        "## 口径",
        "",
        "- VIX信号必须达到对应指数的绝对数值地板；滚动分位只能作为辅助，不能让低绝对VIX入选。",
        "- VIX信号在收盘确认，期权于下一交易日开盘成交。",
        "- 信号日前20个交易日涨幅超过3%，或40个交易日涨幅超过6%，按涨多后的高波动处理，只测试单买认沽；否则只测试单买认购。",
        "- 每笔交易独立，收益按买入权利金计算；开仓和平仓各计入0.5%滑点，不做价差组合。",
        "- “真实底部”主口径为未来10日继续下跌不超过3%，且未来20日最大反弹不低于5%。",
        "- 逐事件最高收益属于回望结果，只用于解释历史，不代表实时可选择结果。",
        "",
    ]
    return "\n".join(lines)


def _pct(value: object) -> str:
    parsed = _number(value)
    return "-" if parsed is None else f"{parsed * 100:.2f}%"


def write_report(
    output_dir: Path,
    summaries: list[dict],
    events: pd.DataFrame,
    scored: pd.DataFrame,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    event_export = build_event_export(events, events.attrs.get("outcomes", pd.DataFrame()))
    top_combinations = (
        scored.sort_values(["index_name", "balanced_score"], ascending=[True, False])
        .groupby("index_name", as_index=False)
        .head(50)
        if not scored.empty
        else scored
    )
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "methodology": {
            "signal": "采集QVIX收盘首次突破绝对阈值；滚动分位规则也必须同时达到该指数绝对VIX地板，连续3日回落后重置",
            "direction": "信号日前20个交易日涨幅超过3%，或40个交易日涨幅超过6%，按涨多后的高波动只测试单买认沽；否则按下跌或震荡后的恐慌只测试单买认购",
            "entry": "下一交易日开盘",
            "slippage": SLIPPAGE,
            "bottom_definition": "未来10日继续下跌不超过3%，且未来20日最大反弹不少于5%",
            "top_definition": "认沽方向不判断底部；未来10日继续上涨不超过3%，且未来20日最大回落不少于5%，记为高位有效",
            "holding_days": list(HOLDING_DAYS),
            "dte_buckets": [item[1] for item in EXPIRY_BUCKETS],
            "moneyness": [format_moneyness(item) for item in MONEYNESS_TARGETS],
            "reference_dates": [item.date().isoformat() for item in REFERENCE_SIGNAL_DATES],
        },
        "overall_conclusion": build_overall_conclusion(summaries),
        "index_summaries": _json_value(summaries),
        "events": [sanitize_record(row) for row in event_export.to_dict("records")],
        "top_combinations": [sanitize_record(row) for row in top_combinations.to_dict("records")],
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    event_export.to_csv(output_dir / "events.csv", index=False, encoding="utf-8-sig")
    top_combinations.to_csv(output_dir / "combinations.csv", index=False, encoding="utf-8-sig")
    (output_dir / "summary.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze high-QVIX bottom signals and option structures.")
    parser.add_argument("--output-dir", default=str(REPORT_DIR))
    parser.add_argument(
        "--indexes",
        default=",".join(spec.index_name for spec in INDEX_SPECS),
        help="Comma-separated index names.",
    )
    return parser.parse_args()


def main() -> None:
    from app.db.session import SessionLocal

    args = parse_args()
    selected = {item.strip() for item in args.indexes.split(",") if item.strip()}
    summaries: list[dict] = []
    event_frames: list[pd.DataFrame] = []
    evaluated_frames: list[pd.DataFrame] = []
    scored_frames: list[pd.DataFrame] = []
    with SessionLocal() as db:
        analyzer = VixOptionAnalyzer(db)
        for spec in INDEX_SPECS:
            if spec.index_name not in selected:
                continue
            print(f"[{spec.index_name}] 生成高VIX事件", flush=True)
            events, evaluated, summary = analyzer.analyze_index(spec)
            if not events.empty:
                event_frames.append(events)
            if not evaluated.empty:
                evaluated_frames.append(evaluated)
                scored = score_candidates(aggregate_outcomes(evaluated))
                if not scored.empty:
                    scored["index_name"] = spec.index_name
                    scored_frames.append(scored)
            if summary:
                summaries.append(summary)
    all_events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    all_evaluated = pd.concat(evaluated_frames, ignore_index=True) if evaluated_frames else pd.DataFrame()
    all_events.attrs["outcomes"] = all_evaluated.drop_duplicates(
        [
            "index_name",
            "signal_date",
            "product_code",
            "strategy_type",
            "dte_bucket",
            "moneyness",
            "holding_days",
        ]
    ) if not all_evaluated.empty else pd.DataFrame()
    all_scored = pd.concat(scored_frames, ignore_index=True) if scored_frames else pd.DataFrame()
    report = write_report(Path(args.output_dir), summaries, all_events, all_scored)
    print(
        f"完成：{len(report['index_summaries'])}个指数，"
        f"{len(report['events'])}个独立事件，输出到 {args.output_dir}",
        flush=True,
    )


if __name__ == "__main__":
    main()
