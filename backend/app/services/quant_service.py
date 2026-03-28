import json
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from math import sqrt

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client
from app.models.quant_strategy_config import QuantStrategyConfig
from app.services.stock_service import StockService

CORE_INDEX_NAMES = ["上证50", "沪深300", "中证500", "中证1000"]
INDEX_TO_ETF_CODE = {
    "上证指数": "510210",
    "上证50": "510050",
    "沪深300": "510300",
    "中证500": "510500",
    "中证1000": "512100",
}
INDEX_STRATEGY_FILTER_KEYS = [
    "emotion",
    "basis-main",
    "basis-month",
    "breadth-up-pct",
    "wr",
    "macd-dif",
    "macd-dea",
    "macd-histogram",
    "kdj-k",
    "kdj-d",
    "kdj-j",
]
STOCK_STRATEGY_FILTER_KEYS = [
    "wr",
    "macd-dif",
    "macd-dea",
    "macd-histogram",
    "kdj-k",
    "kdj-d",
    "kdj-j",
    "ma-1",
    "ma-2",
    "ma-3",
    "ma-4",
]
INDEX_BREADTH_CACHE_KEY = "fit:quant:index_breadth:v3"
INDEX_BREADTH_CACHE_TTL_SECONDS = 600
INDEX_DASHBOARD_CACHE_KEY_PREFIX = "fit:quant:index_dashboard:v1"
INDEX_DASHBOARD_CACHE_TTL_SECONDS = 600
INDEX_DASHBOARD_RECENT_LIMIT = 750


def _date_text(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sort_candles(candles: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in candles:
        open_price = _to_float(item.get("open"))
        high_price = _to_float(item.get("high"))
        low_price = _to_float(item.get("low"))
        close_price = _to_float(item.get("close"))
        if open_price is None or high_price is None or low_price is None or close_price is None:
            continue
        normalized.append(
            {
                "trade_date": _date_text(item.get("trade_date")),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "pct_chg": _to_float(item.get("pct_chg")) or 0.0,
            }
        )
    return sorted(normalized, key=lambda item: item["trade_date"])


def _calc_sma(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    rolling_sum = 0.0
    for index, value in enumerate(values):
        rolling_sum += value
        if index >= period:
            rolling_sum -= values[index - period]
        if index >= period - 1:
            result[index] = rolling_sum / period
    return result


def _calc_std(values: list[float], period: int, means: list[float | None]) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(period - 1, len(values)):
        mean = means[index]
        if mean is None:
            continue
        variance_sum = 0.0
        for offset in range(index - period + 1, index + 1):
            diff = values[offset] - mean
            variance_sum += diff * diff
        result[index] = sqrt(variance_sum / period)
    return result


def _calc_ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * multiplier + result[-1] * (1 - multiplier))
    return result


def _calc_macd(values: list[float], fast: int, slow: int, signal: int) -> tuple[list[float | None], list[float | None], list[float | None]]:
    ema_fast = _calc_ema(values, fast)
    ema_slow = _calc_ema(values, slow)
    dif: list[float | None] = [None] * len(values)
    for index in range(len(values)):
        if index >= slow - 1:
            dif[index] = ema_fast[index] - ema_slow[index]

    dea: list[float | None] = [None] * len(values)
    seed_index = -1
    for index in range(slow - 1, len(dif)):
        slice_values = dif[index - signal + 1 : index + 1]
        if len(slice_values) == signal and all(value is not None for value in slice_values):
            dea[index] = sum(slice_values) / signal
            seed_index = index
            break

    if seed_index >= 0:
        multiplier = 2 / (signal + 1)
        for index in range(seed_index + 1, len(dif)):
            current_dif = dif[index]
            previous_dea = dea[index - 1]
            if current_dif is None or previous_dea is None:
                continue
            dea[index] = current_dif * multiplier + previous_dea * (1 - multiplier)

    histogram: list[float | None] = [None] * len(values)
    for index in range(len(values)):
        if dif[index] is None or dea[index] is None:
            continue
        histogram[index] = 2 * (dif[index] - dea[index])

    return dif, dea, histogram


def _calc_kdj(
    candles: list[dict],
    period: int,
    k_smoothing: int,
    d_smoothing: int,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    k_values: list[float | None] = [None] * len(candles)
    d_values: list[float | None] = [None] * len(candles)
    j_values: list[float | None] = [None] * len(candles)
    previous_k = 50.0
    previous_d = 50.0

    for index in range(period - 1, len(candles)):
        window = candles[index - period + 1 : index + 1]
        highest_high = max(item["high"] for item in window)
        lowest_low = min(item["low"] for item in window)
        denominator = highest_high - lowest_low
        rsv = 50.0 if denominator == 0 else ((candles[index]["close"] - lowest_low) / denominator) * 100
        current_k = ((k_smoothing - 1) * previous_k + rsv) / k_smoothing
        current_d = ((d_smoothing - 1) * previous_d + current_k) / d_smoothing
        current_j = 3 * current_k - 2 * current_d
        k_values[index] = current_k
        d_values[index] = current_d
        j_values[index] = current_j
        previous_k = current_k
        previous_d = current_d

    return k_values, d_values, j_values


def _calc_wr(candles: list[dict], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(candles)
    for index in range(period - 1, len(candles)):
        window = candles[index - period + 1 : index + 1]
        highest_high = max(item["high"] for item in window)
        lowest_low = min(item["low"] for item in window)
        denominator = highest_high - lowest_low
        result[index] = 0.0 if denominator == 0 else ((highest_high - candles[index]["close"]) / denominator) * 100
    return result


def _normalize_threshold(value: object) -> float | None:
    return _to_float(value)


def _normalize_ratio(value: object) -> float:
    parsed = _to_float(value)
    if parsed is None:
        return 1.0
    if parsed > 1:
        return max(min(parsed / 100, 1.0), 0.0)
    return max(min(parsed, 1.0), 0.0)


class QuantService:
    def __init__(self, db: Session):
        self.db = db
        self.stock_service = StockService(db)

    def _resolve_index_option(self, index_code: str) -> dict | None:
        for item in self.stock_service.list_index_options():
            if str(item.get("code", "")).strip() == index_code:
                return item
        return None

    def _ensure_index_dashboard_table_ready(self) -> None:
        bind = self.db.get_bind()
        table_name = settings.quant_index_dashboard_table_name
        if bind is None:
            raise RuntimeError("database bind is unavailable")
        if not inspect(bind).has_table(table_name):
            raise RuntimeError(f"precomputed table `{table_name}` is not ready")

    def _resolve_recent_index_start_date(self, index_code: str) -> date | None:
        sql = text(
            f"SELECT MIN(recent.trade_date) AS trade_date "
            f"FROM ("
            f"  SELECT `{settings.index_daily_date_column}` AS trade_date "
            f"  FROM `{settings.index_daily_table_name}` "
            f"  WHERE `{settings.index_daily_code_column}` = :index_code "
            f"  ORDER BY `{settings.index_daily_date_column}` DESC "
            f"  LIMIT {INDEX_DASHBOARD_RECENT_LIMIT}"
            f") recent"
        )
        return self.db.execute(sql, {"index_code": index_code}).scalar()

    def _load_index_dashboard_rows(self, index_code: str, start_date: date | None = None) -> list[dict]:
        sql = (
            f"SELECT "
            f"`{settings.quant_index_dashboard_date_column}` AS trade_date, "
            f"`{settings.quant_index_dashboard_emotion_column}` AS emotion_value, "
            f"`{settings.quant_index_dashboard_main_basis_column}` AS main_basis, "
            f"`{settings.quant_index_dashboard_month_basis_column}` AS month_basis, "
            f"`{settings.quant_index_dashboard_breadth_up_count_column}` AS up_count, "
            f"`{settings.quant_index_dashboard_breadth_total_count_column}` AS total_count, "
            f"`{settings.quant_index_dashboard_breadth_up_pct_column}` AS up_ratio_pct "
            f"FROM `{settings.quant_index_dashboard_table_name}` "
            f"WHERE `{settings.quant_index_dashboard_code_column}` = :index_code"
        )
        params: dict[str, object] = {"index_code": index_code}
        if start_date is not None:
            sql += f" AND `{settings.quant_index_dashboard_date_column}` >= :start_date"
            params["start_date"] = start_date
        sql += f" ORDER BY `{settings.quant_index_dashboard_date_column}` ASC"
        return [dict(row) for row in self.db.execute(text(sql), params).mappings().all()]

    def get_index_dashboard(self, index_code: str, mode: str = "recent") -> dict:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"recent", "full"}:
            raise ValueError("unsupported mode")

        option = self._resolve_index_option(index_code)
        if option is None:
            raise ValueError("index not found")

        cache_key = f"{INDEX_DASHBOARD_CACHE_KEY_PREFIX}:{index_code}:{normalized_mode}"
        cached = redis_client.get(cache_key)
        if cached:
            try:
                payload = json.loads(cached)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

        start_date = self._resolve_recent_index_start_date(index_code) if normalized_mode == "recent" else None
        candles = self.stock_service.list_index_daily_kline(index_code=index_code, start_date=start_date)

        try:
            self._ensure_index_dashboard_table_ready()
            rows = self._load_index_dashboard_rows(index_code=index_code, start_date=start_date)
        except SQLAlchemyError as exc:
            raise RuntimeError("failed to load precomputed quant index dashboard data") from exc

        result = {
            "index": {"code": option["code"], "name": option["name"]},
            "range_mode": normalized_mode,
            "candles": candles,
            "emotion_points": [
                {
                    "trade_date": row["trade_date"],
                    "value": _to_float(row.get("emotion_value")) or 50.0,
                }
                for row in rows
            ],
            "basis_points": [
                {
                    "trade_date": row["trade_date"],
                    "main_basis": _to_float(row.get("main_basis")) or 0.0,
                    "month_basis": _to_float(row.get("month_basis")) or 0.0,
                }
                for row in rows
            ],
            "breadth_points": [
                {
                    "trade_date": row["trade_date"],
                    "up_ratio_pct": _to_float(row.get("up_ratio_pct")) or 0.0,
                    "up_count": int(row.get("up_count") or 0),
                    "total_count": int(row.get("total_count") or 0),
                }
                for row in rows
            ],
        }
        redis_client.set(
            cache_key,
            json.dumps(result, ensure_ascii=False, default=str),
            ex=INDEX_DASHBOARD_CACHE_TTL_SECONDS,
        )
        return result

    def list_index_breadth(self) -> list[dict]:
        cached = redis_client.get(INDEX_BREADTH_CACHE_KEY)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        change_expr = (
            f"COALESCE("
            f"`{settings.stock_change_column}`, "
            f"`{settings.stock_close_column}` - `{settings.stock_pre_close_column}`, "
            f"`{settings.stock_latest_price_column}` - `{settings.stock_pre_close_column}`"
            f")"
        )
        hist_sql = text(
            f"SELECT "
            f"calendar.trade_date AS trade_date, "
            f"SUM(CASE WHEN prev.`{settings.stock_close_column}` IS NOT NULL "
            f"AND curr.`{settings.stock_close_column}` > prev.`{settings.stock_close_column}` THEN 1 ELSE 0 END) AS up_count, "
            f"SUM(CASE WHEN prev.`{settings.stock_close_column}` IS NOT NULL THEN 1 ELSE 0 END) AS total_count "
            f"FROM ("
            f"  SELECT "
            f"  trade_date, "
            f"  LAG(trade_date) OVER (ORDER BY trade_date) AS prev_trade_date "
            f"  FROM ("
            f"    SELECT DISTINCT `{settings.stock_date_column}` AS trade_date "
            f"    FROM `{settings.stock_table_name}` "
            f"    WHERE `{settings.stock_data_source_column}` = :hist_source"
            f"  ) distinct_dates"
            f") calendar "
            f"LEFT JOIN `{settings.stock_table_name}` curr "
            f"  ON curr.`{settings.stock_date_column}` = calendar.trade_date "
            f" AND curr.`{settings.stock_data_source_column}` = :hist_source "
            f"LEFT JOIN `{settings.stock_table_name}` prev "
            f"  ON prev.`{settings.stock_prefixed_code_column}` = curr.`{settings.stock_prefixed_code_column}` "
            f" AND prev.`{settings.stock_date_column}` = calendar.prev_trade_date "
            f" AND prev.`{settings.stock_data_source_column}` = :hist_source "
            f"GROUP BY calendar.trade_date "
            f"ORDER BY calendar.trade_date ASC"
        )
        rows_by_date = {
            row["trade_date"]: {
                "trade_date": row["trade_date"],
                "up_count": int(row.get("up_count") or 0),
                "total_count": int(row.get("total_count") or 0),
            }
            for row in self.db.execute(hist_sql, {"hist_source": settings.stock_hist_source_value}).mappings().all()
        }

        spot_sql = text(
            f"SELECT "
            f"`{settings.stock_date_column}` AS trade_date, "
            f"SUM(CASE WHEN {change_expr} > 0 THEN 1 ELSE 0 END) AS up_count, "
            f"SUM(CASE WHEN {change_expr} IS NOT NULL THEN 1 ELSE 0 END) AS total_count "
            f"FROM `{settings.stock_table_name}` "
            f"WHERE `{settings.stock_data_source_column}` = :spot_source "
            f"GROUP BY `{settings.stock_date_column}` "
            f"ORDER BY `{settings.stock_date_column}` ASC"
        )
        for row in self.db.execute(spot_sql, {"spot_source": settings.stock_spot_source_value}).mappings().all():
            rows_by_date[row["trade_date"]] = {
                "trade_date": row["trade_date"],
                "up_count": int(row.get("up_count") or 0),
                "total_count": int(row.get("total_count") or 0),
            }

        result: list[dict] = []
        for trade_date in sorted(rows_by_date.keys()):
            item = rows_by_date[trade_date]
            total_count = item["total_count"]
            up_count = item["up_count"]
            result.append(
                {
                    "trade_date": trade_date,
                    "up_ratio_pct": (up_count / total_count * 100) if total_count else 0.0,
                    "up_count": up_count,
                    "total_count": total_count,
                }
            )
        redis_client.set(
            INDEX_BREADTH_CACHE_KEY,
            json.dumps(result, ensure_ascii=False, default=str),
            ex=INDEX_BREADTH_CACHE_TTL_SECONDS,
        )
        return result

    def _build_emotion_value_by_date(self, symbol_name: str) -> dict[str, float]:
        rows = self.stock_service.list_excel_index_emotions()
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            index_name = str(row.get("index_name", "")).strip()
            trade_date = _date_text(row.get("emotion_date"))
            emotion_value = _to_float(row.get("emotion_value"))
            if emotion_value is None:
                continue
            if symbol_name == "上证指数":
                if index_name not in CORE_INDEX_NAMES:
                    continue
            elif index_name != symbol_name:
                continue
            grouped[trade_date].append(emotion_value)
        return {trade_date: sum(values) / len(values) for trade_date, values in grouped.items() if values}

    def _build_basis_value_by_date(self, symbol_name: str) -> tuple[dict[str, float], dict[str, float]]:
        rows = self.stock_service.list_index_futures_basis()
        grouped_main: dict[str, list[float]] = defaultdict(list)
        grouped_month: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            index_name = str(row.get("index_name", "")).strip()
            trade_date = _date_text(row.get("trade_date"))
            main_basis = _to_float(row.get("main_basis"))
            month_basis = _to_float(row.get("month_basis"))
            if symbol_name == "上证指数":
                if index_name not in CORE_INDEX_NAMES:
                    continue
            elif index_name != symbol_name:
                continue
            if main_basis is not None:
                grouped_main[trade_date].append(main_basis)
            if month_basis is not None:
                grouped_month[trade_date].append(month_basis)
        main_map = {trade_date: sum(values) / len(values) for trade_date, values in grouped_main.items() if values}
        month_map = {
            trade_date: sum(values) / len(values) for trade_date, values in grouped_month.items() if values
        }
        return main_map, month_map

    def _build_index_snapshots(self, symbol_name: str, params: dict, candles: list[dict]) -> list[dict]:
        sorted_candles = _sort_candles(candles)
        if not sorted_candles:
            return []

        times = [item["trade_date"] for item in sorted_candles]
        closes = [item["close"] for item in sorted_candles]
        ma_periods = [int(value) for value in params.get("ma", {}).get("periods", [5, 10, 20, 60])]
        macd_params = params.get("macd", {})
        kdj_params = params.get("kdj", {})
        wr_params = params.get("wr", {})
        boll_params = params.get("boll", {})
        boll_period = int(boll_params.get("period", 20))
        boll_multiplier = float(boll_params.get("multiplier", 2))

        ma_values = [_calc_sma(closes, period) for period in ma_periods]
        boll_middle = _calc_sma(closes, boll_period)
        boll_std = _calc_std(closes, boll_period, boll_middle)
        boll_upper = [
            middle + boll_multiplier * std if middle is not None and std is not None else None
            for middle, std in zip(boll_middle, boll_std)
        ]
        boll_lower = [
            middle - boll_multiplier * std if middle is not None and std is not None else None
            for middle, std in zip(boll_middle, boll_std)
        ]
        macd_dif, macd_dea, macd_hist = _calc_macd(
            closes,
            int(macd_params.get("fast", 12)),
            int(macd_params.get("slow", 26)),
            int(macd_params.get("signal", 9)),
        )
        kdj_k, kdj_d, kdj_j = _calc_kdj(
            sorted_candles,
            int(kdj_params.get("period", 9)),
            int(kdj_params.get("kSmoothing", 3)),
            int(kdj_params.get("dSmoothing", 3)),
        )
        wr_values = _calc_wr(sorted_candles, int(wr_params.get("period", 14)))
        emotion_map = self._build_emotion_value_by_date(symbol_name)
        basis_main_map, basis_month_map = self._build_basis_value_by_date(symbol_name)
        breadth_map = {
            _date_text(item["trade_date"]): float(item["up_ratio_pct"]) for item in self.list_index_breadth()
        }

        snapshots: list[dict] = []
        for index, trade_date in enumerate(times):
            snapshots.append(
                {
                    "trade_date": trade_date,
                    "close": closes[index],
                    "values": {
                        "emotion": emotion_map.get(trade_date, 50.0),
                        "basis-main": basis_main_map.get(trade_date, 0.0),
                        "basis-month": basis_month_map.get(trade_date, 0.0),
                        "breadth-up-pct": breadth_map.get(trade_date, 0.0),
                        "wr": wr_values[index],
                        "macd-dif": macd_dif[index],
                        "macd-dea": macd_dea[index],
                        "macd-histogram": macd_hist[index],
                        "kdj-k": kdj_k[index],
                        "kdj-d": kdj_d[index],
                        "kdj-j": kdj_j[index],
                        "ma-1": ma_values[0][index] if len(ma_values) > 0 else None,
                        "ma-2": ma_values[1][index] if len(ma_values) > 1 else None,
                        "ma-3": ma_values[2][index] if len(ma_values) > 2 else None,
                        "ma-4": ma_values[3][index] if len(ma_values) > 3 else None,
                        "boll-upper": boll_upper[index],
                        "boll-middle": boll_middle[index],
                        "boll-lower": boll_lower[index],
                    },
                }
            )
        return snapshots

    def _build_stock_snapshots(self, params: dict, candles: list[dict]) -> list[dict]:
        sorted_candles = _sort_candles(candles)
        if not sorted_candles:
            return []

        times = [item["trade_date"] for item in sorted_candles]
        closes = [item["close"] for item in sorted_candles]
        ma_periods = [int(value) for value in params.get("ma", {}).get("periods", [5, 10, 20, 60])]
        macd_params = params.get("macd", {})
        kdj_params = params.get("kdj", {})
        wr_params = params.get("wr", {})
        boll_params = params.get("boll", {})
        boll_period = int(boll_params.get("period", 20))
        boll_multiplier = float(boll_params.get("multiplier", 2))

        ma_values = [_calc_sma(closes, period) for period in ma_periods]
        boll_middle = _calc_sma(closes, boll_period)
        boll_std = _calc_std(closes, boll_period, boll_middle)
        boll_upper = [
            middle + boll_multiplier * std if middle is not None and std is not None else None
            for middle, std in zip(boll_middle, boll_std)
        ]
        boll_lower = [
            middle - boll_multiplier * std if middle is not None and std is not None else None
            for middle, std in zip(boll_middle, boll_std)
        ]
        macd_dif, macd_dea, macd_hist = _calc_macd(
            closes,
            int(macd_params.get("fast", 12)),
            int(macd_params.get("slow", 26)),
            int(macd_params.get("signal", 9)),
        )
        kdj_k, kdj_d, kdj_j = _calc_kdj(
            sorted_candles,
            int(kdj_params.get("period", 9)),
            int(kdj_params.get("kSmoothing", 3)),
            int(kdj_params.get("dSmoothing", 3)),
        )
        wr_values = _calc_wr(sorted_candles, int(wr_params.get("period", 14)))

        snapshots: list[dict] = []
        for index, trade_date in enumerate(times):
            snapshots.append(
                {
                    "trade_date": trade_date,
                    "close": closes[index],
                    "values": {
                        "wr": wr_values[index],
                        "macd-dif": macd_dif[index],
                        "macd-dea": macd_dea[index],
                        "macd-histogram": macd_hist[index],
                        "kdj-k": kdj_k[index],
                        "kdj-d": kdj_d[index],
                        "kdj-j": kdj_j[index],
                        "ma-1": ma_values[0][index] if len(ma_values) > 0 else None,
                        "ma-2": ma_values[1][index] if len(ma_values) > 1 else None,
                        "ma-3": ma_values[2][index] if len(ma_values) > 2 else None,
                        "ma-4": ma_values[3][index] if len(ma_values) > 3 else None,
                        "boll-upper": boll_upper[index],
                        "boll-middle": boll_middle[index],
                        "boll-lower": boll_lower[index],
                    },
                }
            )
        return snapshots

    def _matches_numeric_filters(self, snapshot: dict, filters: dict, allowed_keys: list[str]) -> bool:
        for key, threshold in filters.items():
            if key not in allowed_keys:
                continue
            value = snapshot["values"].get(key)
            if value is None:
                return False
            gt_value = _normalize_threshold((threshold or {}).get("gt"))
            lt_value = _normalize_threshold((threshold or {}).get("lt"))
            if gt_value is not None and not (value > gt_value):
                return False
            if lt_value is not None and not (value < lt_value):
                return False
        return True

    def _matches_boll_filter(self, snapshot: dict, boll_filter: dict) -> bool:
        gt_key = (boll_filter or {}).get("gt")
        lt_key = (boll_filter or {}).get("lt")
        if not gt_key and not lt_key:
            return True
        close_value = snapshot.get("close")
        if close_value is None:
            return False
        if gt_key:
            gt_value = snapshot["values"].get(gt_key)
            if gt_value is None or not (close_value > gt_value):
                return False
        if lt_key:
            lt_value = snapshot["values"].get(lt_key)
            if lt_value is None or not (close_value < lt_value):
                return False
        return True

    def _build_signal_map(self, strategy: QuantStrategyConfig, snapshots: list[dict]) -> dict[str, str]:
        allowed_keys = INDEX_STRATEGY_FILTER_KEYS if strategy.strategy_type == "index" else STOCK_STRATEGY_FILTER_KEYS
        blue_filters = strategy.blue_filters or {}
        red_filters = strategy.red_filters or {}
        blue_boll = strategy.blue_boll_filter or {}
        red_boll = strategy.red_boll_filter or {}
        has_blue = bool(blue_filters) or bool(blue_boll.get("gt")) or bool(blue_boll.get("lt"))
        has_red = bool(red_filters) or bool(red_boll.get("gt")) or bool(red_boll.get("lt"))

        signal_map: dict[str, str] = {}
        for snapshot in snapshots:
            is_blue = False
            is_red = False
            if has_blue:
                is_blue = self._matches_numeric_filters(snapshot, blue_filters, allowed_keys) and self._matches_boll_filter(
                    snapshot, blue_boll
                )
            if has_red:
                is_red = self._matches_numeric_filters(snapshot, red_filters, allowed_keys) and self._matches_boll_filter(
                    snapshot, red_boll
                )

            if is_blue and is_red:
                signal_map[snapshot["trade_date"]] = "purple"
            elif is_blue:
                signal_map[snapshot["trade_date"]] = "blue"
            elif is_red:
                signal_map[snapshot["trade_date"]] = "red"
        return signal_map

    def _serialize_strategy(self, item: QuantStrategyConfig) -> dict:
        return {
            "id": item.id,
            "name": item.name,
            "strategy_type": item.strategy_type,
            "target_code": item.target_code,
            "target_name": item.target_name,
            "indicator_params": item.indicator_params or {},
            "blue_filters": item.blue_filters or {},
            "red_filters": item.red_filters or {},
            "blue_boll_filter": item.blue_boll_filter or {},
            "red_boll_filter": item.red_boll_filter or {},
            "signal_buy_color": item.signal_buy_color,
            "signal_sell_color": item.signal_sell_color,
            "purple_conflict_mode": item.purple_conflict_mode,
            "start_date": item.start_date,
            "buy_position_pct": float(item.buy_position_pct),
            "sell_position_pct": float(item.sell_position_pct),
            "execution_price_mode": item.execution_price_mode,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def list_strategies(self) -> list[dict]:
        items = self.db.query(QuantStrategyConfig).order_by(QuantStrategyConfig.updated_at.desc()).all()
        return [self._serialize_strategy(item) for item in items]

    def create_strategy(self, payload: dict) -> dict:
        item = QuantStrategyConfig(
            name=str(payload.get("name", "")).strip(),
            strategy_type=str(payload.get("strategy_type", "")).strip(),
            target_code=str(payload.get("target_code", "")).strip(),
            target_name=str(payload.get("target_name", "")).strip(),
            indicator_params=payload.get("indicator_params") or {},
            blue_filters=payload.get("blue_filters") or {},
            red_filters=payload.get("red_filters") or {},
            blue_boll_filter=payload.get("blue_boll_filter") or {},
            red_boll_filter=payload.get("red_boll_filter") or {},
            signal_buy_color=str(payload.get("signal_buy_color", "blue")).strip(),
            signal_sell_color=str(payload.get("signal_sell_color", "red")).strip(),
            purple_conflict_mode=str(payload.get("purple_conflict_mode", "sell_first")).strip(),
            start_date=payload.get("start_date"),
            buy_position_pct=_normalize_ratio(payload.get("buy_position_pct", 1)),
            sell_position_pct=_normalize_ratio(payload.get("sell_position_pct", 1)),
            execution_price_mode=str(payload.get("execution_price_mode", "next_open")).strip(),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._serialize_strategy(item)

    def update_strategy(self, strategy_id: int, payload: dict) -> dict:
        item = self.db.get(QuantStrategyConfig, strategy_id)
        if item is None:
            raise ValueError("strategy not found")

        item.name = str(payload.get("name", item.name)).strip()
        item.strategy_type = str(payload.get("strategy_type", item.strategy_type)).strip()
        item.target_code = str(payload.get("target_code", item.target_code)).strip()
        item.target_name = str(payload.get("target_name", item.target_name)).strip()
        item.indicator_params = payload.get("indicator_params") or item.indicator_params or {}
        item.blue_filters = payload.get("blue_filters") or {}
        item.red_filters = payload.get("red_filters") or {}
        item.blue_boll_filter = payload.get("blue_boll_filter") or {}
        item.red_boll_filter = payload.get("red_boll_filter") or {}
        item.signal_buy_color = str(payload.get("signal_buy_color", item.signal_buy_color)).strip()
        item.signal_sell_color = str(payload.get("signal_sell_color", item.signal_sell_color)).strip()
        item.purple_conflict_mode = str(payload.get("purple_conflict_mode", item.purple_conflict_mode)).strip()
        item.start_date = payload.get("start_date", item.start_date)
        item.buy_position_pct = _normalize_ratio(payload.get("buy_position_pct", item.buy_position_pct))
        item.sell_position_pct = _normalize_ratio(payload.get("sell_position_pct", item.sell_position_pct))
        item.execution_price_mode = str(payload.get("execution_price_mode", item.execution_price_mode)).strip()
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._serialize_strategy(item)

    def delete_strategy(self, strategy_id: int) -> None:
        item = self.db.get(QuantStrategyConfig, strategy_id)
        if item is None:
            raise ValueError("strategy not found")
        self.db.delete(item)
        self.db.commit()

    def _load_etf_price_rows(self, etf_code: str) -> list[dict]:
        params = {
            "etf_code": etf_code,
            "hist_source": settings.etf_daily_hist_source_value,
            "spot_source": settings.etf_daily_spot_source_value,
        }
        hist_sql = text(
            f"SELECT "
            f"`{settings.etf_daily_date_column}` AS trade_date, "
            f"`{settings.etf_daily_open_column}` AS open, "
            f"`{settings.etf_daily_close_column}` AS close "
            f"FROM `{settings.etf_daily_table_name}` "
            f"WHERE `{settings.etf_daily_code_column}` = :etf_code "
            f"AND `{settings.etf_daily_data_source_column}` = :hist_source "
            f"ORDER BY `{settings.etf_daily_date_column}` ASC"
        )
        rows_by_date = {
            row["trade_date"]: {
                "trade_date": row["trade_date"],
                "open": float(row["open"]),
                "close": float(row["close"]),
            }
            for row in self.db.execute(hist_sql, params).mappings().all()
            if row.get("trade_date") is not None and row.get("open") is not None and row.get("close") is not None
        }

        latest_spot_date_sql = text(
            f"SELECT MAX(`{settings.etf_daily_date_column}`) AS trade_date "
            f"FROM `{settings.etf_daily_table_name}` "
            f"WHERE `{settings.etf_daily_code_column}` = :etf_code "
            f"AND `{settings.etf_daily_data_source_column}` = :spot_source"
        )
        latest_spot_date = self.db.execute(latest_spot_date_sql, params).scalar()
        if latest_spot_date is not None:
            spot_sql = text(
                f"SELECT "
                f"`{settings.etf_daily_date_column}` AS trade_date, "
                f"`{settings.etf_daily_open_column}` AS open, "
                f"`{settings.etf_daily_close_column}` AS close "
                f"FROM `{settings.etf_daily_table_name}` "
                f"WHERE `{settings.etf_daily_code_column}` = :etf_code "
                f"AND `{settings.etf_daily_data_source_column}` = :spot_source "
                f"AND `{settings.etf_daily_date_column}` = :latest_spot_date "
                f"LIMIT 1"
            )
            spot_row = self.db.execute(spot_sql, {**params, "latest_spot_date": latest_spot_date}).mappings().first()
            if spot_row and spot_row.get("open") is not None and spot_row.get("close") is not None:
                rows_by_date[spot_row["trade_date"]] = {
                    "trade_date": spot_row["trade_date"],
                    "open": float(spot_row["open"]),
                    "close": float(spot_row["close"]),
                }

        return [rows_by_date[key] for key in sorted(rows_by_date.keys())]

    def _resolve_action(self, color: str | None, strategy: QuantStrategyConfig) -> str | None:
        if color is None:
            return None
        if color == "purple":
            mode = (strategy.purple_conflict_mode or "sell_first").strip()
            if mode == "buy_first":
                return "buy"
            if mode == "skip":
                return None
            return "sell"
        if color == strategy.signal_buy_color:
            return "buy"
        if color == strategy.signal_sell_color:
            return "sell"
        return None

    def calculate_equity_curve(self, strategy_id: int) -> dict:
        strategy = self.db.get(QuantStrategyConfig, strategy_id)
        if strategy is None:
            raise ValueError("strategy not found")

        if strategy.strategy_type == "index":
            signal_candles = self.stock_service.list_index_daily_kline(strategy.target_code)
            snapshots = self._build_index_snapshots(strategy.target_name, strategy.indicator_params or {}, signal_candles)
            etf_code = INDEX_TO_ETF_CODE.get(strategy.target_name)
            if not etf_code:
                raise ValueError("unsupported index target")
            price_rows = self._load_etf_price_rows(etf_code)
        else:
            signal_candles = self.stock_service.list_qfq_daily_kline(strategy.target_code)
            snapshots = self._build_stock_snapshots(strategy.indicator_params or {}, signal_candles)
            price_rows = [
                {
                    "trade_date": item["trade_date"],
                    "open": float(item["open"]),
                    "close": float(item["close"]),
                }
                for item in sorted(signal_candles, key=lambda row: _date_text(row.get("trade_date")))
                if item.get("trade_date") is not None and item.get("open") is not None and item.get("close") is not None
            ]

        if not price_rows:
            return {
                "strategy": self._serialize_strategy(strategy),
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "points": [],
            }

        signal_map = self._build_signal_map(strategy, snapshots)
        start_date_text = strategy.start_date.isoformat() if strategy.start_date else _date_text(price_rows[0]["trade_date"])
        filtered_prices = [row for row in price_rows if _date_text(row["trade_date"]) >= start_date_text]
        if not filtered_prices:
            return {
                "strategy": self._serialize_strategy(strategy),
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "points": [],
            }

        price_dates = [_date_text(item["trade_date"]) for item in filtered_prices]
        pending_actions: dict[str, str] = {}
        for trade_date, color in signal_map.items():
            if trade_date < start_date_text:
                continue
            current_index = bisect_right(price_dates, trade_date) - 1
            if current_index < 0 or current_index + 1 >= len(price_dates):
                continue
            action = self._resolve_action(color, strategy)
            if action:
                pending_actions[price_dates[current_index + 1]] = action

        cash = 1.0
        shares = 0.0
        initial_close = float(filtered_prices[0]["close"]) if filtered_prices else 1.0
        buy_ratio = _normalize_ratio(strategy.buy_position_pct)
        sell_ratio = _normalize_ratio(strategy.sell_position_pct)
        execution_price_mode = (strategy.execution_price_mode or "next_open").strip()

        points: list[dict] = []
        for row in filtered_prices:
            trade_date = _date_text(row["trade_date"])
            action = pending_actions.get(trade_date)
            exec_price = float(row["open"] if execution_price_mode == "next_open" else row["close"])
            if action == "buy" and exec_price > 0:
                invest_cash = cash * buy_ratio
                shares += invest_cash / exec_price
                cash -= invest_cash
            elif action == "sell" and exec_price > 0:
                sell_shares = shares * sell_ratio
                shares -= sell_shares
                cash += sell_shares * exec_price

            close_price = float(row["close"])
            nav = cash + shares * close_price
            benchmark_nav = close_price / initial_close if initial_close else None
            points.append(
                {
                    "trade_date": row["trade_date"],
                    "nav": nav,
                    "benchmark_nav": benchmark_nav,
                    "signal": signal_map.get(trade_date),
                    "close_price": close_price,
                }
            )

        cumulative_return_pct = (points[-1]["nav"] - 1) * 100 if points else 0.0
        start_dt = filtered_prices[0]["trade_date"]
        end_dt = filtered_prices[-1]["trade_date"]
        days_span = max((end_dt - start_dt).days, 0)
        if points and days_span > 0 and points[-1]["nav"] > 0:
            annualized_return_pct = ((points[-1]["nav"] ** (365 / days_span)) - 1) * 100
        else:
            annualized_return_pct = cumulative_return_pct if points else 0.0

        return {
            "strategy": self._serialize_strategy(strategy),
            "cumulative_return_pct": cumulative_return_pct,
            "annualized_return_pct": annualized_return_pct,
            "points": points,
        }
