import json
import re
from hashlib import sha1
from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from math import ceil, sqrt

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.user import User
from app.services.notification_service import NotificationService
from app.services.stock_service import FUTURES_BASIS_SYMBOL_MAP, StockService

SHANGHAI_INDEX_NAME = "上证指数"
BEIJING50_INDEX_NAME = "北证50"
SHARED_INDEX_AUXILIARY_NAMES = {SHANGHAI_INDEX_NAME, BEIJING50_INDEX_NAME}
CORE_INDEX_NAMES = ["上证50", "沪深300", "中证500", "中证1000"]
INDEX_TO_ETF_CODE = {
    SHANGHAI_INDEX_NAME: "510210",
    "上证50": "510050",
    "沪深300": "510300",
    "中证500": "510500",
    "中证1000": "512100",
}

CN_INDEX_STRATEGY_FILTER_KEYS = [
    "emotion",
    "basis-main",
    "basis-month",
    "breadth-up-pct",
    "vix-open",
    "vix-high",
    "vix-low",
    "vix-close",
    "cn-option-put-call-current",
    "cn-option-put-call-next",
    "cn-option-put-call-quarter-1",
    "cn-option-put-call-quarter-2",
    "cn-option-flow-pc-volume",
    "cn-option-flow-pc-turnover",
    "basis-main-delta-5d",
    "basis-main-delta-7d",
    "basis-main-delta-14d",
    "basis-main-delta-20d",
    "basis-main-delta-30d",
    "basis-main-delta-60d",
    "basis-main-delta-120d",
    "basis-month-delta-5d",
    "basis-month-delta-7d",
    "basis-month-delta-14d",
    "basis-month-delta-20d",
    "basis-month-delta-30d",
    "basis-month-delta-60d",
    "basis-month-delta-120d",
    "cffex-net-short-top20-delta-5d",
    "cffex-net-short-top20-delta-7d",
    "cffex-net-short-top20-delta-14d",
    "cffex-net-short-top20-delta-20d",
    "cffex-net-short-top20-delta-30d",
    "cffex-net-short-top20-delta-60d",
    "cffex-net-short-top20-delta-120d",
    "cffex-net-short-citic-delta-5d",
    "cffex-net-short-citic-delta-7d",
    "cffex-net-short-citic-delta-14d",
    "cffex-net-short-citic-delta-20d",
    "cffex-net-short-citic-delta-30d",
    "cffex-net-short-citic-delta-60d",
    "cffex-net-short-citic-delta-120d",
    "rsi",
    "wr",
    "macd-dif",
    "macd-dea",
    "macd-histogram",
    "kdj-k",
    "kdj-d",
    "kdj-j",
]
SEQUENCE_STRATEGY_SERIES_KEYS = [
    "market-breadth-up-pct",
    "market-emotion",
    "market-qvix",
    "market-basis-main",
    "target-up-pct",
    "target-down-pct",
    "target-high-new-high",
    "target-close-new-high",
    "target-ma-bias-1",
    "target-ma-bias-2",
    "target-ma-bias-3",
    "target-ma-bias-4",
]
SEQUENCE_STRATEGY_NEW_HIGH_SERIES_KEYS = {
    "target-high-new-high",
    "target-close-new-high",
}
SEQUENCE_STRATEGY_MA_BIAS_SERIES_KEYS = {
    "target-ma-bias-1",
    "target-ma-bias-2",
    "target-ma-bias-3",
    "target-ma-bias-4",
}
SEQUENCE_STRATEGY_OPERATORS = {"gt", "gte", "lt", "lte"}
SEQUENCE_STRATEGY_MARKET_MACRO_SERIES_KEYS = {
    "market-emotion",
    "market-qvix",
    "market-basis-main",
}
SEQUENCE_MARKET_MACRO_INDEX_NAMES = {"上证指数", "沪深300", "中证500", "中证1000"}
SCAN_BOARD_FILTER_KEYS = {"main", "chinext", "star", "bse"}
STOCK_STRATEGY_FILTER_KEYS = [
    "pct-chg",
    "turnover-rate",
    "rsi",
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
INDEX_DASHBOARD_CACHE_KEY_PREFIX = "fit:quant:index_dashboard:v17"
INDEX_DASHBOARD_CACHE_TTL_SECONDS = 600
CN_OPTION_PUT_CALL_FIELD_MAP = [
    (
        "option_pc_current_month",
        "option_pc_current_month_contract_month",
        "option_pc_current_month_special_flag",
        "option_pc_current_month_special_note",
        "current_month_put_call_ratio",
        "current_month_contract_month",
        "current_month_special_calculation",
        "current_month_special_note",
    ),
    (
        "option_pc_next_month",
        "option_pc_next_month_contract_month",
        "option_pc_next_month_special_flag",
        "option_pc_next_month_special_note",
        "next_month_put_call_ratio",
        "next_month_contract_month",
        "next_month_special_calculation",
        "next_month_special_note",
    ),
    (
        "option_pc_quarter_1",
        "option_pc_quarter_1_contract_month",
        "option_pc_quarter_1_special_flag",
        "option_pc_quarter_1_special_note",
        "quarter_1_put_call_ratio",
        "quarter_1_contract_month",
        "quarter_1_special_calculation",
        "quarter_1_special_note",
    ),
    (
        "option_pc_quarter_2",
        "option_pc_quarter_2_contract_month",
        "option_pc_quarter_2_special_flag",
        "option_pc_quarter_2_special_note",
        "quarter_2_put_call_ratio",
        "quarter_2_contract_month",
        "quarter_2_special_calculation",
        "quarter_2_special_note",
    ),
]
CN_OPTION_PUT_CALL_FILTER_FIELD_MAP = [
    ("cn-option-put-call-current", "option_pc_current_month"),
    ("cn-option-put-call-next", "option_pc_next_month"),
    ("cn-option-put-call-quarter-1", "option_pc_quarter_1"),
    ("cn-option-put-call-quarter-2", "option_pc_quarter_2"),
]
CN_OPTION_PUT_CALL_FILTER_KEYS = [field_key for field_key, _column_name in CN_OPTION_PUT_CALL_FILTER_FIELD_MAP]
CN_OPTION_FLOW_PUT_CALL_FIELD_MAP = [
    ("option_volume_pc_ratio", "volume_put_call_ratio"),
    ("option_turnover_pc_ratio", "turnover_put_call_ratio"),
]
CN_OPTION_FLOW_PUT_CALL_FILTER_FIELD_MAP = [
    ("cn-option-flow-pc-volume", "option_volume_pc_ratio"),
    ("cn-option-flow-pc-turnover", "option_turnover_pc_ratio"),
]
CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS = [
    field_key for field_key, _column_name in CN_OPTION_FLOW_PUT_CALL_FILTER_FIELD_MAP
]
CN_OPTION_SUPPORTED_FILTER_KEYS = [
    *CN_OPTION_PUT_CALL_FILTER_KEYS,
    *CN_OPTION_FLOW_PUT_CALL_FILTER_KEYS,
]
CN_OPTION_PUT_CALL_SUPPORTED_INDEX_NAMES = {
    SHANGHAI_INDEX_NAME,
    "上证50",
    "沪深300",
    "中证1000",
}
CN_OPTION_PUT_CALL_SUPPORTED_INDEX_CODES = {
    "000001",
    "sh000001",
    "000016",
    "sh000016",
    "000300",
    "sh000300",
    "399300",
    "sz399300",
    "000852",
    "sh000852",
    "399852",
    "sz399852",
}
CFFEX_NET_SHORT_DELTA_WINDOWS = (5, 7, 14, 20, 30, 60, 120)
CFFEX_NET_SHORT_DELTA_SOURCES = (
    ("top20", "top20_institutions", "top20_delta"),
    ("citic", "citic_customer", "citic_delta"),
)
CFFEX_NET_SHORT_DELTA_FIELD_MAP = [
    (
        f"cffex-net-short-{field_prefix}-delta-{window}d",
        f"cffex_{field_prefix}_net_short_delta_{window}d",
        f"{payload_prefix}_{window}d",
    )
    for field_prefix, _source_key, payload_prefix in CFFEX_NET_SHORT_DELTA_SOURCES
    for window in CFFEX_NET_SHORT_DELTA_WINDOWS
]
CFFEX_NET_SHORT_DELTA_FILTER_KEYS = [
    field_key for field_key, _column_name, _payload_key in CFFEX_NET_SHORT_DELTA_FIELD_MAP
]
BASIS_DELTA_WINDOWS = CFFEX_NET_SHORT_DELTA_WINDOWS
BASIS_DELTA_FIELD_MAP = [
    (
        f"basis-{basis_prefix}-delta-{window}d",
        f"basis_{basis_prefix}_delta_{window}d",
        f"{basis_prefix}_delta_{window}d",
    )
    for basis_prefix in ("main", "month")
    for window in BASIS_DELTA_WINDOWS
]
BASIS_DELTA_FILTER_KEYS = [field_key for field_key, _column_name, _payload_key in BASIS_DELTA_FIELD_MAP]
CFFEX_NET_SHORT_PRODUCT_BY_INDEX_NAME = {
    "上证50": "IH",
    "沪深300": "IF",
    "中证500": "IC",
    "中证1000": "IM",
}
CFFEX_NET_SHORT_PRODUCT_BY_INDEX_CODE = {
    "000016": "IH",
    "sh000016": "IH",
    "000300": "IF",
    "sh000300": "IF",
    "399300": "IF",
    "sz399300": "IF",
    "000905": "IC",
    "sh000905": "IC",
    "399905": "IC",
    "sz399905": "IC",
    "000852": "IM",
    "sh000852": "IM",
    "399852": "IM",
    "sz399852": "IM",
}
CFFEX_NET_SHORT_CORE_PRODUCTS = ["IH", "IF", "IC", "IM"]
INDEX_DASHBOARD_RECENT_LIMIT = 750
BUY_POSITION_SEARCH_RATIOS = [step / 100 for step in range(20, 101, 5)]
SELL_POSITION_SEARCH_RATIOS = [step / 100 for step in range(5, 101, 5)]
OPTIMIZATION_TOLERANCE = 1e-9
DEFAULT_SCAN_INITIAL_CAPITAL = 1_000_000.0
DEFAULT_SCAN_BUY_AMOUNT = 10_000.0
DEFAULT_SCAN_BUY_OFFSET = 1
DEFAULT_SCAN_SELL_OFFSET = 2
DEFAULT_SCAN_BUY_PRICE_BASIS = "open"
DEFAULT_SCAN_SELL_PRICE_BASIS = "open"
SCAN_PRICE_BASES = {"open", "close"}
SCAN_SELL_TRIGGER_TARGETS = {
    "ma-1",
    "ma-2",
    "ma-3",
    "ma-4",
    "boll-upper",
    "boll-middle",
    "boll-lower",
}
SCAN_RESULT_CACHE_KEY_PREFIX = "fit:quant:sequence_scan:v2"
SCAN_RESULT_CACHE_TTL_SECONDS = 3600
SCAN_EVENT_PAGE_SIZE = 100
SCAN_EVENT_PAGE_SIZE_MAX = 500
SUPPORTED_TARGET_MARKETS = {"cn", "hk", "us"}
INDEX_VIX_CODE_BY_NAME = {
    "上证50": "50ETF_QVIX",
    "沪深300": "300ETF_QVIX",
    "中证500": "500ETF_QVIX",
}
INDEX_VIX_CODE_BY_INDEX_CODE = {
    "000016": "50ETF_QVIX",
    "sh000016": "50ETF_QVIX",
    "000300": "300ETF_QVIX",
    "sh000300": "300ETF_QVIX",
    "sz399300": "300ETF_QVIX",
    "399300": "300ETF_QVIX",
    "000905": "500ETF_QVIX",
    "sh000905": "500ETF_QVIX",
    "sz399905": "500ETF_QVIX",
    "399905": "500ETF_QVIX",
}
VIX_FILTER_KEYS = ["vix-open", "vix-high", "vix-low", "vix-close"]
US_VIX_FILTER_KEYS = ["us-vix-open", "us-vix-high", "us-vix-low", "us-vix-close"]
US_FEAR_GREED_FILTER_KEYS = ["us-fear-greed"]
US_HEDGE_FILTER_KEYS = ["us-hedge-long", "us-hedge-short", "us-hedge-ratio"]
US_PUT_CALL_FILTER_KEYS = [
    "us-put-call-total",
    "us-put-call-index",
    "us-put-call-equity",
    "us-put-call-etf",
]
US_TREASURY_FILTER_KEYS = [
    "us-yield-3m",
    "us-yield-2y",
    "us-yield-10y",
    "us-yield-spread-10y-2y",
    "us-yield-spread-10y-3m",
]
US_CREDIT_FILTER_KEYS = ["us-hy-oas", "us-hy-oas-change-5d"]
US_BASIS_ADJUSTED_FILTER_KEYS = ["basis-main-adjusted"]
US_MARKET_AUXILIARY_FILTER_KEYS = (
    US_VIX_FILTER_KEYS
    + US_FEAR_GREED_FILTER_KEYS
    + US_PUT_CALL_FILTER_KEYS
    + US_TREASURY_FILTER_KEYS
    + US_CREDIT_FILTER_KEYS
)
US_AUXILIARY_FILTER_KEYS = US_MARKET_AUXILIARY_FILTER_KEYS + US_HEDGE_FILTER_KEYS
US_HEDGE_PROXY_SCOPE_BY_INDEX_CODE = {
    ".INX": "ES",
    ".NDX": "NQ",
}
US_HEDGE_PROXY_SCOPE_BY_INDEX_NAME = {
    "标普500指数": "ES",
    "纳斯达克100指数": "NQ",
}
HK_INDEX_FUTURES_ROOT_BY_INDEX_CODE = {
    "HSI": "HSI",
    "HSCEI": "HHI",
    "HSTECH": "HTI",
    "HHI": "HHI",
    "HTI": "HTI",
}
HK_INDEX_FUTURES_ROOT_BY_INDEX_NAME = {
    "恒生指数": "HSI",
    "恒生中国企业指数": "HHI",
    "国企指数": "HHI",
    "恒生科技指数": "HTI",
}
BASIS_FILTER_KEYS = ["basis-main", "basis-month"]
US_BASIS_FILTER_KEYS = ["basis-main"]
CN_INDEX_FUTURES_VARIETY_BY_INDEX_NAME = {
    str(item["index_name"]): str(item["main_symbol"]).removesuffix("M")
    for item in FUTURES_BASIS_SYMBOL_MAP
}
NDX_INDEX_CODES = {".NDX"}
NDX_INDEX_NAMES = {"纳斯达克100指数"}
NDX_BASIS_ROLL_DATES = {
    "2022-09-12",
    "2022-12-12",
    "2023-03-13",
    "2023-06-13",
    "2023-09-11",
    "2023-12-11",
    "2024-03-11",
    "2024-06-18",
    "2024-09-19",
    "2024-12-18",
    "2025-03-20",
    "2025-06-18",
    "2025-09-17",
    "2025-12-17",
    "2026-03-18",
}
NDX_BASIS_ROLL_START_DATE = date(2022, 9, 12)


def _date_text(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_date_value(value: object) -> date | None:
    if isinstance(value, date):
        return value
    text_value = str(value or "").strip().split(" ")[0]
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value)
    except ValueError:
        return None


def _month_tuple_from_text(value: object) -> tuple[int, int] | None:
    text_value = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})$", text_value)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        return None
    return year, month


def _parse_cn_index_futures_contract_month(symbol: object, variety: object) -> tuple[int, int] | None:
    normalized_variety = str(variety or "").strip().upper()
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_variety or not normalized_symbol.startswith(normalized_variety):
        return None

    match = re.match(rf"^{re.escape(normalized_variety)}(\d{{2}})(\d{{2}})$", normalized_symbol)
    if not match:
        return None

    year_suffix = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        return None
    year = 1900 + year_suffix if year_suffix >= 80 else 2000 + year_suffix
    return year, month


def _contract_month_is_finished(contract_month: tuple[int, int] | None, last_trade_date: object) -> bool:
    parsed_last_trade_date = _parse_date_value(last_trade_date)
    if contract_month is None or parsed_last_trade_date is None:
        return False
    return contract_month <= (parsed_last_trade_date.year, parsed_last_trade_date.month)


def _third_friday(year: int, month: int) -> date:
    first_day = date(year, month, 1)
    days_until_friday = (4 - first_day.weekday()) % 7
    return first_day + timedelta(days=days_until_friday + 14)


def _cn_contract_last_trade_is_observed(contract_month: tuple[int, int] | None, last_trade_date: object) -> bool:
    parsed_last_trade_date = _parse_date_value(last_trade_date)
    if contract_month is None or parsed_last_trade_date is None:
        return False

    year, month = contract_month
    if (year, month) > (parsed_last_trade_date.year, parsed_last_trade_date.month):
        return False

    return parsed_last_trade_date >= _third_friday(year, month)


def _date_in_window(target_date: date, start_date: date | None, end_date: date | None) -> bool:
    if start_date is not None and target_date < start_date:
        return False
    if end_date is not None and target_date > end_date:
        return False
    return True


def _sorted_contract_marker_map(markers: dict[str, set[str]]) -> dict[str, list[str]]:
    return {
        trade_date: sorted(contracts)
        for trade_date, contracts in sorted(markers.items())
        if contracts
    }


def _build_cn_basis_contract_roll_markers(
    rows: list[dict],
    allowed_varieties: set[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, list[str]]:
    normalized_varieties = {str(item or "").strip().upper() for item in allowed_varieties if str(item or "").strip()}
    markers: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        variety = str(row.get("variety") or "").strip().upper()
        contract_code = str(row.get("contract_code") or row.get("symbol") or "").strip().upper()
        last_trade_date = _parse_date_value(row.get("last_trade_date"))
        contract_month = _parse_cn_index_futures_contract_month(contract_code, variety)
        if (
            not variety
            or variety not in normalized_varieties
            or not contract_code
            or last_trade_date is None
            or not _cn_contract_last_trade_is_observed(contract_month, last_trade_date)
            or not _date_in_window(last_trade_date, start_date, end_date)
        ):
            continue
        markers[last_trade_date.isoformat()].add(contract_code)
    return _sorted_contract_marker_map(markers)


def _build_hk_basis_contract_roll_markers(
    rows: list[dict],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, list[str]]:
    markers: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        contract_code = str(row.get("contract_code") or row.get("source_contract_code") or "").strip().upper()
        last_trade_date = _parse_date_value(row.get("last_trade_date"))
        contract_month = _month_tuple_from_text(row.get("contract_month"))
        if (
            not contract_code
            or last_trade_date is None
            or not _contract_month_is_finished(contract_month, last_trade_date)
            or not _date_in_window(last_trade_date, start_date, end_date)
        ):
            continue
        markers[last_trade_date.isoformat()].add(contract_code)
    return _sorted_contract_marker_map(markers)


def _normalize_contract_codes(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return []


def _build_sequence_dashboard_macro_values(rows: list[dict]) -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"market-emotion": [], "market-basis-main": []}
    )
    for row in rows:
        index_name = str(row.get("index_name") or "").strip()
        trade_date = _date_text(row.get("trade_date"))
        if index_name not in SEQUENCE_MARKET_MACRO_INDEX_NAMES or not trade_date:
            continue
        emotion_value = _to_float(row.get("emotion_value"))
        basis_value = _to_float(row.get("main_basis"))
        if emotion_value is not None:
            grouped[trade_date]["market-emotion"].append(emotion_value)
        if basis_value is not None:
            grouped[trade_date]["market-basis-main"].append(basis_value)

    return {
        trade_date: {
            key: sum(values) / len(values)
            for key, values in value_groups.items()
            if values
        }
        for trade_date, value_groups in grouped.items()
    }


def _build_sequence_dashboard_breadth_values(rows: list[dict]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        index_name = str(row.get("index_name") or "").strip()
        trade_date = _date_text(row.get("trade_date"))
        if index_name not in SEQUENCE_MARKET_MACRO_INDEX_NAMES or not trade_date:
            continue
        breadth_value = _to_float(row.get("breadth_up_pct"))
        if breadth_value is not None:
            grouped[trade_date].append(breadth_value)
    return {
        trade_date: sum(values) / len(values)
        for trade_date, values in grouped.items()
        if values
    }


def _build_sequence_qvix_values(rows: list[dict]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        trade_date = _date_text(row.get("trade_date"))
        close_price = _to_float(row.get("close_price"))
        if not trade_date or close_price is None or close_price <= 0:
            continue
        grouped[trade_date].append(close_price)
    return {
        trade_date: sum(values) / len(values)
        for trade_date, values in grouped.items()
        if values
    }


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
                "turnover_rate": _to_float(item.get("turnover_rate")),
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


def _calc_sma_nullable(values: list[object], period: int) -> list[float | None]:
    if period <= 0:
        return [None] * len(values)
    result: list[float | None] = [None] * len(values)
    rolling_sum = 0.0
    valid_count = 0
    numeric_values = [_to_float(value) for value in values]
    for index, value in enumerate(numeric_values):
        if value is not None:
            rolling_sum += value
            valid_count += 1
        if index >= period:
            dropped = numeric_values[index - period]
            if dropped is not None:
                rolling_sum -= dropped
                valid_count -= 1
        if index >= period - 1 and valid_count == period:
            result[index] = rolling_sum / period
    return result


def _normalize_ma_periods(params: dict | None) -> list[int]:
    defaults = [5, 10, 20, 60]
    raw_periods = params.get("ma", {}).get("periods", defaults) if isinstance(params, dict) else defaults
    period_values = raw_periods if isinstance(raw_periods, list) else defaults
    normalized: list[int] = []
    for index, fallback in enumerate(defaults):
        try:
            value = int(period_values[index])
        except (IndexError, TypeError, ValueError):
            value = fallback
        normalized.append(value if value > 0 else fallback)
    return normalized


def _calc_ma_bias(close_price: object, ma_value: object) -> float | None:
    close_value = _to_float(close_price)
    ma_number = _to_float(ma_value)
    if close_value is None or ma_number is None or ma_number <= 0:
        return None
    return (close_value - ma_number) / ma_number * 100


def _sequence_operator_matches(value: object, operator: str, threshold: float) -> bool:
    numeric_value = _to_float(value)
    if numeric_value is None:
        return False
    if operator == "gt":
        return numeric_value > threshold
    if operator == "gte":
        return numeric_value >= threshold
    if operator == "lt":
        return numeric_value < threshold
    if operator == "lte":
        return numeric_value <= threshold
    return False


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


def _calc_rsi(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result

    gain_sum = 0.0
    loss_sum = 0.0
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        if change >= 0:
            gain_sum += change
        else:
            loss_sum += abs(change)

    average_gain = gain_sum / period
    average_loss = loss_sum / period
    result[period] = 100.0 if average_loss == 0 else 100 - 100 / (1 + average_gain / average_loss)

    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = change if change > 0 else 0.0
        loss = abs(change) if change < 0 else 0.0
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
        result[index] = 100.0 if average_loss == 0 else 100 - 100 / (1 + average_gain / average_loss)

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


def _position_bucket(position_pct: float) -> str:
    if position_pct <= 0:
        return "flat"
    if position_pct <= 0.25:
        return "light"
    if position_pct <= 0.5:
        return "medium"
    if position_pct <= 0.75:
        return "heavy"
    return "full"


def _round_metric(value: float) -> float:
    return round(float(value), 6)


class QuantService:
    def __init__(self, db: Session):
        self.db = db
        self.stock_service = StockService(db)
        self.notification_service = NotificationService(db)

    def _normalize_strategy_engine(self, value: object) -> str:
        normalized = str(value or "snapshot").strip().lower()
        return "sequence" if normalized == "sequence" else "snapshot"

    def _normalize_sequence_mode(self, value: object) -> str:
        normalized = str(value or "single_target").strip().lower()
        return "market_scan" if normalized == "market_scan" else "single_target"

    def _default_scan_trade_config(self) -> dict:
        return {
            "initial_capital": DEFAULT_SCAN_INITIAL_CAPITAL,
            "buy_amount_per_event": DEFAULT_SCAN_BUY_AMOUNT,
            "buy_offset_trading_days": DEFAULT_SCAN_BUY_OFFSET,
            "sell_offset_trading_days": DEFAULT_SCAN_SELL_OFFSET,
            "buy_price_basis": DEFAULT_SCAN_BUY_PRICE_BASIS,
            "sell_price_basis": DEFAULT_SCAN_SELL_PRICE_BASIS,
            "sell_trigger": None,
            "board_filters": [],
        }

    def _normalize_scan_sell_trigger(self, raw_trigger: object) -> dict | None:
        if not isinstance(raw_trigger, dict):
            return None
        enabled = bool(raw_trigger.get("enabled"))
        if not enabled:
            return None

        operator = str(raw_trigger.get("operator", "")).strip().lower()
        target = str(raw_trigger.get("target", "")).strip().lower()
        if operator not in {"gt", "lt"}:
            raise ValueError("scan sell trigger operator must be gt or lt")
        if target not in SCAN_SELL_TRIGGER_TARGETS:
            raise ValueError("scan sell trigger target is not supported")
        return {
            "enabled": True,
            "operator": operator,
            "target": target,
        }

    def _normalize_scan_trade_config(self, raw_config: object) -> dict:
        config = raw_config if isinstance(raw_config, dict) else {}
        default = self._default_scan_trade_config()
        sell_trigger = self._normalize_scan_sell_trigger(config.get("sell_trigger"))
        raw_board_filters = config.get("board_filters")
        board_filters = [
            str(item).strip().lower()
            for item in raw_board_filters
            if str(item).strip().lower() in SCAN_BOARD_FILTER_KEYS
        ] if isinstance(raw_board_filters, list) else []

        initial_capital = _to_float(config.get("initial_capital"))
        if initial_capital is None or initial_capital <= 0:
            initial_capital = default["initial_capital"]

        buy_amount_per_event = _to_float(config.get("buy_amount_per_event"))
        if buy_amount_per_event is None or buy_amount_per_event <= 0:
            buy_amount_per_event = default["buy_amount_per_event"]

        try:
            buy_offset_trading_days = int(config.get("buy_offset_trading_days", default["buy_offset_trading_days"]))
        except (TypeError, ValueError):
            buy_offset_trading_days = default["buy_offset_trading_days"]
        try:
            sell_offset_trading_days = int(
                config.get("sell_offset_trading_days", default["sell_offset_trading_days"])
            )
        except (TypeError, ValueError):
            sell_offset_trading_days = default["sell_offset_trading_days"]

        buy_offset_trading_days = max(buy_offset_trading_days, 1)
        sell_offset_trading_days = max(sell_offset_trading_days, 1)

        buy_price_basis = str(config.get("buy_price_basis", default["buy_price_basis"])).strip().lower()
        sell_price_basis = str(config.get("sell_price_basis", default["sell_price_basis"])).strip().lower()
        if buy_price_basis not in SCAN_PRICE_BASES:
            buy_price_basis = default["buy_price_basis"]
        if sell_price_basis not in SCAN_PRICE_BASES:
            sell_price_basis = default["sell_price_basis"]

        buy_order_key = (buy_offset_trading_days, 0 if buy_price_basis == "open" else 1)
        sell_order_key = (sell_offset_trading_days, 0 if sell_price_basis == "open" else 1)
        if sell_trigger is None and sell_order_key <= buy_order_key:
            raise ValueError("scan sell execution must be later than buy execution")

        return {
            "initial_capital": float(initial_capital),
            "buy_amount_per_event": float(buy_amount_per_event),
            "buy_offset_trading_days": buy_offset_trading_days,
            "sell_offset_trading_days": sell_offset_trading_days,
            "buy_price_basis": buy_price_basis,
            "sell_price_basis": sell_price_basis,
            "sell_trigger": sell_trigger,
            "board_filters": sorted(set(board_filters)),
        }

    def _normalize_target_market(self, raw_value: object) -> str:
        normalized = str(raw_value or "cn").strip().lower()
        if normalized not in SUPPORTED_TARGET_MARKETS:
            return "cn"
        return normalized

    def _index_supports_auxiliary_panels(self, market: str) -> bool:
        return self._normalize_target_market(market) == "cn"

    def _index_supports_us_auxiliary_panels(self, market: str) -> bool:
        return self._normalize_target_market(market) == "us"

    def _resolve_hk_index_futures_root(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> str | None:
        if self._normalize_target_market(target_market) != "hk":
            return None
        normalized_code = str(target_code or "").strip().upper()
        if normalized_code in HK_INDEX_FUTURES_ROOT_BY_INDEX_CODE:
            return HK_INDEX_FUTURES_ROOT_BY_INDEX_CODE[normalized_code]
        normalized_name = str(target_name or "").strip()
        return HK_INDEX_FUTURES_ROOT_BY_INDEX_NAME.get(normalized_name)

    def _resolve_us_index_futures_root(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> str | None:
        if self._normalize_target_market(target_market) != "us":
            return None
        return self._resolve_us_hedge_proxy_scope(target_code, target_name, target_market)

    def _index_supports_basis(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> bool:
        normalized_market = self._normalize_target_market(target_market)
        if normalized_market == "cn":
            return True
        if normalized_market == "hk":
            return self._resolve_hk_index_futures_root(target_code, target_name, target_market) is not None
        if normalized_market == "us":
            return self._resolve_us_index_futures_root(target_code, target_name, target_market) is not None
        return False

    def _resolve_index_vix_code(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> str | None:
        if self._normalize_target_market(target_market) != "cn":
            return None
        normalized_code = str(target_code or "").strip().lower()
        if normalized_code in INDEX_VIX_CODE_BY_INDEX_CODE:
            return INDEX_VIX_CODE_BY_INDEX_CODE[normalized_code]
        normalized_name = str(target_name or "").strip()
        return INDEX_VIX_CODE_BY_NAME.get(normalized_name)

    def _index_supports_vix(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> bool:
        return self._resolve_index_vix_code(target_code, target_name, target_market) is not None

    def _index_supports_cn_option_put_call(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> bool:
        if self._normalize_target_market(target_market) != "cn":
            return False
        normalized_name = str(target_name or "").strip()
        if normalized_name in CN_OPTION_PUT_CALL_SUPPORTED_INDEX_NAMES:
            return True
        normalized_code = str(target_code or "").strip().lower()
        return normalized_code in CN_OPTION_PUT_CALL_SUPPORTED_INDEX_CODES

    def _resolve_us_hedge_proxy_scope(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> str | None:
        if self._normalize_target_market(target_market) != "us":
            return None
        normalized_code = str(target_code or "").strip().upper()
        if normalized_code in US_HEDGE_PROXY_SCOPE_BY_INDEX_CODE:
            return US_HEDGE_PROXY_SCOPE_BY_INDEX_CODE[normalized_code]
        normalized_name = str(target_name or "").strip()
        return US_HEDGE_PROXY_SCOPE_BY_INDEX_NAME.get(normalized_name)

    def _index_supports_adjusted_basis(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> bool:
        if self._normalize_target_market(target_market) != "us":
            return False
        normalized_code = str(target_code or "").strip().upper()
        normalized_name = str(target_name or "").strip()
        return normalized_code in NDX_INDEX_CODES or normalized_name in NDX_INDEX_NAMES

    def _load_basis_rows_for_adjustment(
        self,
        index_code: str,
        target_name: str,
        target_market: str,
        start_date: date | None,
        end_date: date | None,
    ) -> list[dict]:
        query_start_date = start_date
        if self._index_supports_adjusted_basis(index_code, target_name, target_market):
            query_start_date = NDX_BASIS_ROLL_START_DATE
        rows = self._load_index_dashboard_rows(index_code, start_date=query_start_date, end_date=end_date)
        rows = self._apply_adjusted_basis(rows, index_code, target_name, target_market)
        if start_date is not None:
            rows = [row for row in rows if row.get("trade_date") is not None and row["trade_date"] >= start_date]
        return rows

    def _apply_adjusted_basis(
        self,
        rows: list[dict],
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> list[dict]:
        if not self._index_supports_adjusted_basis(target_code, target_name, target_market):
            return [
                {
                    **row,
                    "main_basis_adjusted": None,
                    "basis_roll_flag": False,
                    "basis_roll_delta": None,
                    "basis_roll_type": None,
                    "basis_roll_contracts": [],
                }
                for row in rows
            ]

        sorted_rows = sorted(rows, key=lambda item: _date_text(item.get("trade_date")))
        roll_points: list[dict[str, object]] = []
        previous_basis: float | None = None
        for index, row in enumerate(sorted_rows):
            trade_date = _date_text(row.get("trade_date"))
            main_basis = _to_float(row.get("main_basis"))
            if trade_date in NDX_BASIS_ROLL_DATES and main_basis is not None and previous_basis is not None:
                roll_points.append(
                    {
                        "index": index,
                        "trade_date": trade_date,
                        "delta": main_basis - previous_basis,
                    }
                )
            if main_basis is not None:
                previous_basis = main_basis

        roll_by_index = {int(point["index"]): point for point in roll_points}
        offsets_by_index: dict[int, float] = {}
        for roll_index, point in enumerate(roll_points):
            start_index = int(point["index"])
            next_index = (
                int(roll_points[roll_index + 1]["index"])
                if roll_index + 1 < len(roll_points)
                else len(sorted_rows)
            )
            delta = float(point["delta"])
            segment_length = max(next_index - start_index, 1)
            denominator = max(segment_length - 1, 1)
            for row_index in range(start_index, next_index):
                # Remove the roll jump at the switch date, then release the adjustment
                # through the current contract cycle so the series stays on the raw basis scale.
                progress = (row_index - start_index) / denominator if segment_length > 1 else 0.0
                offsets_by_index[row_index] = delta * (1 - progress)

        adjusted_rows: list[dict] = []
        for index, row in enumerate(sorted_rows):
            main_basis = _to_float(row.get("main_basis"))
            offset = offsets_by_index.get(index, 0.0)
            roll_point = roll_by_index.get(index)
            adjusted_rows.append(
                {
                    **row,
                    "main_basis_adjusted": main_basis - offset if main_basis is not None else None,
                    "basis_roll_flag": roll_point is not None,
                    "basis_roll_delta": float(roll_point["delta"]) if roll_point is not None else None,
                    "basis_roll_type": "adjustment" if roll_point is not None else None,
                    "basis_roll_contracts": [],
                }
            )
        return adjusted_rows

    def _allowed_snapshot_filter_keys(
        self,
        strategy_type: str,
        target_market: str = "cn",
        target_code: object = "",
        target_name: object = "",
    ) -> list[str]:
        if strategy_type == "index":
            if self._index_supports_auxiliary_panels(target_market):
                keys = list(CN_INDEX_STRATEGY_FILTER_KEYS)
                if not self._index_supports_vix(target_code, target_name, target_market):
                    keys = [key for key in keys if key not in VIX_FILTER_KEYS]
                if not self._index_supports_cn_option_put_call(target_code, target_name, target_market):
                    keys = [key for key in keys if key not in CN_OPTION_SUPPORTED_FILTER_KEYS]
                return keys
            if self._normalize_target_market(target_market) == "hk":
                keys = list(STOCK_STRATEGY_FILTER_KEYS)
                if self._index_supports_basis(target_code, target_name, target_market):
                    keys += BASIS_FILTER_KEYS
                return keys
            if self._index_supports_us_auxiliary_panels(target_market):
                keys = list(STOCK_STRATEGY_FILTER_KEYS) + US_MARKET_AUXILIARY_FILTER_KEYS
                if self._resolve_us_hedge_proxy_scope(target_code, target_name, target_market):
                    keys += US_HEDGE_FILTER_KEYS
                if self._index_supports_basis(target_code, target_name, target_market):
                    keys += US_BASIS_FILTER_KEYS
                if self._index_supports_adjusted_basis(target_code, target_name, target_market):
                    keys += US_BASIS_ADJUSTED_FILTER_KEYS
                return keys
            return STOCK_STRATEGY_FILTER_KEYS
        return STOCK_STRATEGY_FILTER_KEYS

    def _normalize_price_rows(self, candles: list[dict]) -> list[dict]:
        return [
            {
                "trade_date": item["trade_date"],
                "open": float(item["open"]),
                "close": float(item["close"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
            }
            for item in sorted(candles, key=lambda row: _date_text(row.get("trade_date")))
            if item.get("trade_date") is not None
            and item.get("open") is not None
            and item.get("close") is not None
            and item.get("high") is not None
            and item.get("low") is not None
        ]

    def _resolve_index_option(self, index_code: str, market: str = "cn") -> dict | None:
        target_code = str(index_code or "").strip().lower()
        normalized_market = self._normalize_target_market(market)
        for item in self.stock_service.list_index_options(market=normalized_market):
            if str(item.get("code", "")).strip().lower() == target_code:
                return item
        return None

    def _resolve_index_auxiliary_source_name(self, symbol_name: str) -> str:
        normalized = str(symbol_name or "").strip()
        if normalized in SHARED_INDEX_AUXILIARY_NAMES:
            return SHANGHAI_INDEX_NAME
        return normalized

    def _resolve_cn_index_futures_varieties(self, target_name: object) -> list[str]:
        source_name = self._resolve_index_auxiliary_source_name(str(target_name or ""))
        if source_name == SHANGHAI_INDEX_NAME:
            return [
                variety
                for index_name in CORE_INDEX_NAMES
                if (variety := CN_INDEX_FUTURES_VARIETY_BY_INDEX_NAME.get(index_name))
            ]
        variety = CN_INDEX_FUTURES_VARIETY_BY_INDEX_NAME.get(source_name)
        return [variety] if variety else []

    def _load_basis_contract_roll_markers(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, list[str]]:
        normalized_market = self._normalize_target_market(target_market)
        if normalized_market == "cn":
            return self._load_cn_basis_contract_roll_markers(target_name, start_date, end_date)
        if normalized_market == "hk":
            return self._load_hk_basis_contract_roll_markers(target_code, target_name, start_date, end_date)
        return {}

    def _load_cn_basis_contract_roll_markers(
        self,
        target_name: object,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, list[str]]:
        varieties = self._resolve_cn_index_futures_varieties(target_name)
        if not varieties:
            return {}

        variety_sql = ", ".join(f":variety_{index}" for index, _ in enumerate(varieties))
        params: dict[str, object] = {
            f"variety_{index}": variety
            for index, variety in enumerate(varieties)
        }
        params["derived_source"] = settings.futures_daily_primary_source_value
        sql = text(
            f"SELECT "
            f"`variety` AS variety, "
            f"`{settings.futures_daily_symbol_column}` AS contract_code, "
            f"MAX(`{settings.futures_daily_trade_date_column}`) AS last_trade_date "
            f"FROM `{settings.futures_daily_table_name}` "
            f"WHERE `variety` IN ({variety_sql}) "
            f"AND `{settings.futures_daily_data_source_column}` <> :derived_source "
            f"AND `{settings.futures_daily_close_column}` IS NOT NULL "
            f"GROUP BY `variety`, `{settings.futures_daily_symbol_column}`"
        )
        rows = [dict(row) for row in self.db.execute(sql, params).mappings().all()]
        return _build_cn_basis_contract_roll_markers(rows, set(varieties), start_date, end_date)

    def _load_hk_basis_contract_roll_markers(
        self,
        target_code: object = "",
        target_name: object = "",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, list[str]]:
        root_symbol = self._resolve_hk_index_futures_root(target_code, target_name, "hk")
        if not root_symbol:
            return {}

        sql = text(
            "SELECT "
            "source_contract_code AS contract_code, "
            "contract_month AS contract_month, "
            "MAX(trade_date) AS last_trade_date "
            "FROM futures_hk_index_daily_data "
            "WHERE root_symbol = :root_symbol "
            "AND close_price IS NOT NULL "
            "GROUP BY source_contract_code, contract_month"
        )
        rows = [dict(row) for row in self.db.execute(sql, {"root_symbol": root_symbol}).mappings().all()]
        return _build_hk_basis_contract_roll_markers(rows, start_date, end_date)

    def _build_basis_point_payload(
        self,
        row: dict,
        default_index_name: str,
        contract_roll_markers: dict[str, list[str]] | None = None,
    ) -> dict:
        trade_date = row["trade_date"]
        marker_contracts = (contract_roll_markers or {}).get(_date_text(trade_date), [])
        basis_roll_type = str(row.get("basis_roll_type") or "").strip() or None
        basis_roll_contracts = _normalize_contract_codes(row.get("basis_roll_contracts"))
        if marker_contracts:
            basis_roll_type = "contract_last_trade"
            basis_roll_contracts = marker_contracts

        return {
            "trade_date": trade_date,
            "index_name": str(row.get("index_name") or default_index_name).strip(),
            "main_basis": _to_float(row.get("main_basis")) or 0.0,
            "month_basis": _to_float(row.get("month_basis")) or 0.0,
            "main_basis_adjusted": _to_float(row.get("main_basis_adjusted")),
            "basis_roll_flag": bool(row.get("basis_roll_flag")) or bool(marker_contracts),
            "basis_roll_delta": _to_float(row.get("basis_roll_delta")),
            "basis_roll_type": basis_roll_type,
            "basis_roll_contracts": basis_roll_contracts,
        }

    def _ensure_index_dashboard_table_ready(self) -> None:
        bind = self.db.get_bind()
        table_name = settings.quant_index_dashboard_table_name
        if bind is None:
            raise RuntimeError("database bind is unavailable")
        if not inspect(bind).has_table(table_name):
            raise RuntimeError(f"precomputed table `{table_name}` is not ready")

    def _index_dashboard_column_names(self) -> set[str]:
        bind = self.db.get_bind()
        table_name = settings.quant_index_dashboard_table_name
        if bind is None:
            return set()
        try:
            return {str(column.get("name") or "").strip() for column in inspect(bind).get_columns(table_name)}
        except SQLAlchemyError:
            return set()

    def _optional_index_dashboard_selects(self) -> str:
        existing_columns = self._index_dashboard_column_names()
        select_parts: list[str] = []
        for (
            ratio_column,
            month_column,
            special_flag_column,
            special_note_column,
            _ratio_alias,
            _month_alias,
            _special_flag_alias,
            _special_note_alias,
        ) in CN_OPTION_PUT_CALL_FIELD_MAP:
            if ratio_column in existing_columns:
                select_parts.append(f"`{ratio_column}` AS {ratio_column}")
            else:
                select_parts.append(f"NULL AS {ratio_column}")
            if month_column in existing_columns:
                select_parts.append(f"`{month_column}` AS {month_column}")
            else:
                select_parts.append(f"NULL AS {month_column}")
            if special_flag_column in existing_columns:
                select_parts.append(f"`{special_flag_column}` AS {special_flag_column}")
            else:
                select_parts.append(f"0 AS {special_flag_column}")
            if special_note_column in existing_columns:
                select_parts.append(f"`{special_note_column}` AS {special_note_column}")
            else:
                select_parts.append(f"NULL AS {special_note_column}")
        for ratio_column, _ratio_alias in CN_OPTION_FLOW_PUT_CALL_FIELD_MAP:
            if ratio_column in existing_columns:
                select_parts.append(f"`{ratio_column}` AS {ratio_column}")
            else:
                select_parts.append(f"NULL AS {ratio_column}")
        for _field_key, column_name, _payload_key in CFFEX_NET_SHORT_DELTA_FIELD_MAP:
            if column_name in existing_columns:
                select_parts.append(f"`{column_name}` AS {column_name}")
            else:
                select_parts.append(f"NULL AS {column_name}")
        for _field_key, column_name, _payload_key in BASIS_DELTA_FIELD_MAP:
            if column_name in existing_columns:
                select_parts.append(f"`{column_name}` AS {column_name}")
            else:
                select_parts.append(f"NULL AS {column_name}")
        return ", " + ", ".join(select_parts) if select_parts else ""

    def _build_cn_option_put_call_point_payload(self, row: dict) -> dict:
        payload = {"trade_date": row["trade_date"]}
        for (
            ratio_column,
            month_column,
            special_flag_column,
            special_note_column,
            ratio_alias,
            month_alias,
            special_flag_alias,
            special_note_alias,
        ) in CN_OPTION_PUT_CALL_FIELD_MAP:
            payload[ratio_alias] = _to_float(row.get(ratio_column))
            payload[month_alias] = str(row.get(month_column) or "").strip() or None
            payload[special_flag_alias] = bool(row.get(special_flag_column))
            payload[special_note_alias] = str(row.get(special_note_column) or "").strip() or None
        return payload

    def _build_cn_option_flow_put_call_point_payload(self, row: dict) -> dict:
        payload = {"trade_date": row["trade_date"]}
        for ratio_column, ratio_alias in CN_OPTION_FLOW_PUT_CALL_FIELD_MAP:
            payload[ratio_alias] = _to_float(row.get(ratio_column))
        return payload

    def _resolve_cffex_net_short_products(
        self,
        target_code: object = "",
        target_name: object = "",
        target_market: str = "cn",
    ) -> list[str]:
        if self._normalize_target_market(target_market) != "cn":
            return []
        normalized_name = str(target_name or "").strip()
        if normalized_name in SHARED_INDEX_AUXILIARY_NAMES:
            return list(CFFEX_NET_SHORT_CORE_PRODUCTS)
        if normalized_name in CFFEX_NET_SHORT_PRODUCT_BY_INDEX_NAME:
            return [CFFEX_NET_SHORT_PRODUCT_BY_INDEX_NAME[normalized_name]]
        normalized_code = str(target_code or "").strip().lower()
        product_code = CFFEX_NET_SHORT_PRODUCT_BY_INDEX_CODE.get(normalized_code)
        return [product_code] if product_code else []

    def _calculate_cffex_net_short_delta_points(
        self,
        net_position_series: dict,
        product_codes: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        selected_products = [code for code in product_codes if code in CFFEX_NET_SHORT_CORE_PRODUCTS]
        if not selected_products:
            return []

        def build_product_delta_map(source_key: str, window: int) -> dict[str, dict[str, float | None]]:
            source_series = (
                net_position_series.get(source_key, {}).get("series", {})
                if isinstance(net_position_series, dict)
                else {}
            )
            result: dict[str, dict[str, float | None]] = {}
            for product_code in selected_products:
                points = source_series.get(product_code, [])
                sorted_points = sorted(
                    [
                        {
                            "trade_date": _date_text(point.get("trade_date")),
                            "net_position": _to_float(point.get("net_position")),
                        }
                        for point in points
                        if isinstance(point, dict) and _date_text(point.get("trade_date"))
                    ],
                    key=lambda item: item["trade_date"],
                )
                product_result: dict[str, float | None] = {}
                for index, point in enumerate(sorted_points):
                    current_value = point["net_position"]
                    previous_value = sorted_points[index - window]["net_position"] if index >= window else None
                    product_result[point["trade_date"]] = (
                        current_value - previous_value
                        if current_value is not None and previous_value is not None
                        else None
                    )
                result[product_code] = product_result
            return result

        delta_sources = {
            f"{payload_prefix}_{window}d": build_product_delta_map(source_key, window)
            for _field_prefix, source_key, payload_prefix in CFFEX_NET_SHORT_DELTA_SOURCES
            for window in CFFEX_NET_SHORT_DELTA_WINDOWS
        }

        all_dates = sorted(
            {
                trade_date
                for product_maps in delta_sources.values()
                for product_map in product_maps.values()
                for trade_date in product_map.keys()
            }
        )
        if start_date is not None:
            all_dates = [trade_date for trade_date in all_dates if trade_date >= start_date.isoformat()]
        if end_date is not None:
            all_dates = [trade_date for trade_date in all_dates if trade_date <= end_date.isoformat()]

        rows: list[dict] = []
        for trade_date in all_dates:
            row = {"trade_date": trade_date}
            for payload_key, product_maps in delta_sources.items():
                values = [product_maps.get(product_code, {}).get(trade_date) for product_code in selected_products]
                valid_values = [value for value in values if value is not None]
                row[payload_key] = sum(valid_values) if valid_values else None
            rows.append(row)
        return rows

    def _load_cffex_net_short_delta_rows(
        self,
        target_code: object = "",
        target_name: object = "",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        product_codes = self._resolve_cffex_net_short_products(target_code, target_name, "cn")
        if not product_codes or not getattr(self, "stock_service", None):
            return []
        query_start_date = start_date - timedelta(days=140) if start_date is not None else None
        try:
            series = self.stock_service.get_cffex_net_position_series(
                start_date=query_start_date,
                end_date=end_date,
            )
        except Exception:
            return []
        return self._calculate_cffex_net_short_delta_points(
            series,
            product_codes,
            start_date=start_date,
            end_date=end_date,
        )

    def _build_cffex_net_short_delta_point_payload(self, row: dict) -> dict:
        payload = {"trade_date": row["trade_date"]}
        for _field_key, column_name, payload_key in CFFEX_NET_SHORT_DELTA_FIELD_MAP:
            payload[payload_key] = _to_float(row.get(column_name))
        return payload

    def _build_basis_delta_point_payload(self, row: dict) -> dict:
        payload = {"trade_date": row["trade_date"]}
        for _field_key, column_name, payload_key in BASIS_DELTA_FIELD_MAP:
            payload[payload_key] = _to_float(row.get(column_name))
        return payload

    def _resolve_recent_index_start_date(self, index_code: str, market: str = "cn") -> date | None:
        config = self.stock_service._get_index_market_config(self._normalize_target_market(market))
        sql = text(
            f"SELECT MIN(recent.trade_date) AS trade_date "
            f"FROM ("
            f"  SELECT `{config['daily_date_column']}` AS trade_date "
            f"  FROM `{config['daily_table']}` "
            f"  WHERE `{config['daily_code_column']}` = :index_code "
            f"  ORDER BY `{config['daily_date_column']}` DESC "
            f"  LIMIT {INDEX_DASHBOARD_RECENT_LIMIT}"
            f") recent"
        )
        return self.db.execute(sql, {"index_code": index_code}).scalar()

    def _load_us_auxiliary_rows(
        self,
        target_code: str,
        target_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, list[dict]]:
        hedge_scope = self._resolve_us_hedge_proxy_scope(target_code, target_name, "us")
        return {
            "us_vix_rows": self.stock_service.list_index_us_vix_daily_data(start_date=start_date, end_date=end_date),
            "us_fear_greed_rows": self.stock_service.list_index_us_fear_greed_daily_data(
                start_date=start_date,
                end_date=end_date,
            ),
            "us_hedge_proxy_rows": self.stock_service.list_index_us_hedge_proxy_data(
                hedge_scope,
                start_date=start_date,
                end_date=end_date,
            )
            if hedge_scope
            else [],
            "us_put_call_rows": self.stock_service.list_index_us_put_call_ratio_data(
                start_date=start_date,
                end_date=end_date,
            ),
            "us_treasury_yield_rows": self.stock_service.list_index_us_treasury_yield_data(
                start_date=start_date,
                end_date=end_date,
            ),
            "us_credit_spread_rows": self.stock_service.list_index_us_credit_spread_data(
                start_date=start_date,
                end_date=end_date,
            ),
        }

    def _align_sparse_rows_to_trade_dates(
        self,
        trade_dates: list[str],
        rows: list[dict],
        date_key: str,
    ) -> dict[str, dict]:
        sorted_trade_dates = sorted(date_text for date_text in trade_dates if date_text)
        if not sorted_trade_dates or not rows:
            return {}

        sorted_rows = sorted(
            (row for row in rows if row.get(date_key) is not None),
            key=lambda item: _date_text(item.get(date_key)),
        )
        aligned: dict[str, dict] = {}
        trade_index = 0
        for row in sorted_rows:
            row_date = _date_text(row.get(date_key))
            while trade_index < len(sorted_trade_dates) and sorted_trade_dates[trade_index] < row_date:
                trade_index += 1
            if trade_index < len(sorted_trade_dates):
                aligned[sorted_trade_dates[trade_index]] = row
        return aligned

    def _build_us_index_snapshots(
        self,
        target_code: str,
        target_name: str,
        params: dict,
        candles: list[dict],
    ) -> list[dict]:
        sorted_candles = _sort_candles(candles)
        if not sorted_candles:
            return []

        base_snapshots = self._build_stock_snapshots(params, candles)
        first_trade_date = sorted_candles[0].get("trade_date")
        last_trade_date = sorted_candles[-1].get("trade_date")
        basis_rows = self._load_basis_rows_for_adjustment(
            target_code,
            target_name,
            "us",
            start_date=first_trade_date if isinstance(first_trade_date, date) else None,
            end_date=last_trade_date if isinstance(last_trade_date, date) else None,
        )
        basis_main_by_date = {
            _date_text(item["trade_date"]): _to_float(item.get("main_basis"))
            for item in basis_rows
            if item.get("trade_date") is not None
        }
        basis_month_by_date = {
            _date_text(item["trade_date"]): _to_float(item.get("month_basis"))
            for item in basis_rows
            if item.get("trade_date") is not None
        }
        basis_adjusted_by_date = {
            _date_text(item["trade_date"]): _to_float(item.get("main_basis_adjusted"))
            for item in basis_rows
            if item.get("trade_date") is not None
        }
        auxiliary_rows = self._load_us_auxiliary_rows(
            target_code,
            target_name,
            start_date=first_trade_date if isinstance(first_trade_date, date) else None,
            end_date=last_trade_date if isinstance(last_trade_date, date) else None,
        )
        us_vix_by_date = {
            _date_text(item["trade_date"]): {
                "us-vix-open": _to_float(item.get("open_value")),
                "us-vix-high": _to_float(item.get("high_value")),
                "us-vix-low": _to_float(item.get("low_value")),
                "us-vix-close": _to_float(item.get("close_value")),
            }
            for item in auxiliary_rows["us_vix_rows"]
            if item.get("trade_date") is not None
        }
        fear_greed_by_date = {
            _date_text(item["trade_date"]): _to_float(item.get("fear_greed_value"))
            for item in auxiliary_rows["us_fear_greed_rows"]
            if item.get("trade_date") is not None
        }
        hedge_rows_by_trade_date = self._align_sparse_rows_to_trade_dates(
            [_date_text(item.get("trade_date")) for item in sorted_candles if item.get("trade_date") is not None],
            auxiliary_rows["us_hedge_proxy_rows"],
            "release_date",
        )
        hedge_by_date = {
            trade_date: {
                "us-hedge-long": _to_float(item.get("long_value")),
                "us-hedge-short": _to_float(item.get("short_value")),
                "us-hedge-ratio": _to_float(item.get("ratio_value")),
            }
            for trade_date, item in hedge_rows_by_trade_date.items()
        }
        put_call_by_date = {
            _date_text(item["trade_date"]): {
                "us-put-call-total": _to_float(item.get("total_put_call_ratio")),
                "us-put-call-index": _to_float(item.get("index_put_call_ratio")),
                "us-put-call-equity": _to_float(item.get("equity_put_call_ratio")),
                "us-put-call-etf": _to_float(item.get("etf_put_call_ratio")),
            }
            for item in auxiliary_rows["us_put_call_rows"]
            if item.get("trade_date") is not None
        }
        treasury_by_date = {
            _date_text(item["trade_date"]): {
                "us-yield-3m": _to_float(item.get("yield_3m")),
                "us-yield-2y": _to_float(item.get("yield_2y")),
                "us-yield-10y": _to_float(item.get("yield_10y")),
                "us-yield-spread-10y-2y": _to_float(item.get("spread_10y_2y")),
                "us-yield-spread-10y-3m": _to_float(item.get("spread_10y_3m")),
            }
            for item in auxiliary_rows["us_treasury_yield_rows"]
            if item.get("trade_date") is not None
        }
        sorted_credit_rows = sorted(
            (
                {
                    "trade_date": _date_text(item.get("trade_date")),
                    "high_yield_oas": _to_float(item.get("high_yield_oas")),
                }
                for item in auxiliary_rows["us_credit_spread_rows"]
                if item.get("trade_date") is not None
            ),
            key=lambda item: item["trade_date"],
        )
        credit_by_date = {}
        for index, item in enumerate(sorted_credit_rows):
            value = item.get("high_yield_oas")
            previous_value = sorted_credit_rows[index - 5].get("high_yield_oas") if index >= 5 else None
            credit_by_date[item["trade_date"]] = {
                "us-hy-oas": value,
                "us-hy-oas-change-5d": (
                    round(value - previous_value, 6)
                    if value is not None and previous_value is not None
                    else None
                ),
            }

        snapshots: list[dict] = []
        for snapshot in base_snapshots:
            trade_date = _date_text(snapshot.get("trade_date"))
            values = dict(snapshot.get("values") or {})
            values.update(
                {
                    "basis-main": basis_main_by_date.get(trade_date),
                    "basis-month": basis_month_by_date.get(trade_date),
                    "basis-main-adjusted": basis_adjusted_by_date.get(trade_date),
                    "us-vix-open": us_vix_by_date.get(trade_date, {}).get("us-vix-open"),
                    "us-vix-high": us_vix_by_date.get(trade_date, {}).get("us-vix-high"),
                    "us-vix-low": us_vix_by_date.get(trade_date, {}).get("us-vix-low"),
                    "us-vix-close": us_vix_by_date.get(trade_date, {}).get("us-vix-close"),
                    "us-fear-greed": fear_greed_by_date.get(trade_date),
                    "us-hedge-long": hedge_by_date.get(trade_date, {}).get("us-hedge-long"),
                    "us-hedge-short": hedge_by_date.get(trade_date, {}).get("us-hedge-short"),
                    "us-hedge-ratio": hedge_by_date.get(trade_date, {}).get("us-hedge-ratio"),
                    "us-put-call-total": put_call_by_date.get(trade_date, {}).get("us-put-call-total"),
                    "us-put-call-index": put_call_by_date.get(trade_date, {}).get("us-put-call-index"),
                    "us-put-call-equity": put_call_by_date.get(trade_date, {}).get("us-put-call-equity"),
                    "us-put-call-etf": put_call_by_date.get(trade_date, {}).get("us-put-call-etf"),
                    "us-yield-3m": treasury_by_date.get(trade_date, {}).get("us-yield-3m"),
                    "us-yield-2y": treasury_by_date.get(trade_date, {}).get("us-yield-2y"),
                    "us-yield-10y": treasury_by_date.get(trade_date, {}).get("us-yield-10y"),
                    "us-yield-spread-10y-2y": treasury_by_date.get(trade_date, {}).get("us-yield-spread-10y-2y"),
                    "us-yield-spread-10y-3m": treasury_by_date.get(trade_date, {}).get("us-yield-spread-10y-3m"),
                    "us-hy-oas": credit_by_date.get(trade_date, {}).get("us-hy-oas"),
                    "us-hy-oas-change-5d": credit_by_date.get(trade_date, {}).get("us-hy-oas-change-5d"),
                }
            )
            snapshots.append({**snapshot, "values": values})
        return snapshots

    def _build_hk_index_snapshots(
        self,
        target_code: str,
        params: dict,
        candles: list[dict],
    ) -> list[dict]:
        sorted_candles = _sort_candles(candles)
        if not sorted_candles:
            return []

        base_snapshots = self._build_stock_snapshots(params, candles)
        first_trade_date = sorted_candles[0].get("trade_date")
        last_trade_date = sorted_candles[-1].get("trade_date")
        basis_rows = self._load_index_dashboard_rows(
            target_code,
            start_date=first_trade_date if isinstance(first_trade_date, date) else None,
            end_date=last_trade_date if isinstance(last_trade_date, date) else None,
        )
        basis_main_by_date = {
            _date_text(item["trade_date"]): _to_float(item.get("main_basis"))
            for item in basis_rows
            if item.get("trade_date") is not None
        }
        basis_month_by_date = {
            _date_text(item["trade_date"]): _to_float(item.get("month_basis"))
            for item in basis_rows
            if item.get("trade_date") is not None
        }

        snapshots: list[dict] = []
        for snapshot in base_snapshots:
            trade_date = _date_text(snapshot.get("trade_date"))
            values = dict(snapshot.get("values") or {})
            values.update(
                {
                    "basis-main": basis_main_by_date.get(trade_date),
                    "basis-month": basis_month_by_date.get(trade_date),
                }
            )
            snapshots.append({**snapshot, "values": values})
        return snapshots

    def _build_index_snapshots_for_market(
        self,
        target_market: str,
        target_code: str,
        symbol_name: str,
        params: dict,
        candles: list[dict],
    ) -> list[dict]:
        normalized_market = self._normalize_target_market(target_market)
        if self._index_supports_auxiliary_panels(normalized_market):
            return self._build_index_snapshots(target_code, symbol_name, params, candles)
        if normalized_market == "hk":
            return self._build_hk_index_snapshots(target_code, params, candles)
        if self._index_supports_us_auxiliary_panels(normalized_market):
            return self._build_us_index_snapshots(target_code, symbol_name, params, candles)
        return self._build_stock_snapshots(params, candles)

    def _load_index_dashboard_rows(
        self,
        index_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        optional_selects = self._optional_index_dashboard_selects()
        sql = (
            f"SELECT "
            f"`{settings.quant_index_dashboard_date_column}` AS trade_date, "
            f"`{settings.quant_index_dashboard_name_column}` AS index_name, "
            f"`{settings.quant_index_dashboard_emotion_column}` AS emotion_value, "
            f"`{settings.quant_index_dashboard_main_basis_column}` AS main_basis, "
            f"`{settings.quant_index_dashboard_month_basis_column}` AS month_basis, "
            f"`{settings.quant_index_dashboard_breadth_up_count_column}` AS up_count, "
            f"`{settings.quant_index_dashboard_breadth_total_count_column}` AS total_count, "
            f"`{settings.quant_index_dashboard_breadth_up_pct_column}` AS up_ratio_pct"
            f"{optional_selects} "
            f"FROM `{settings.quant_index_dashboard_table_name}` "
            f"WHERE `{settings.quant_index_dashboard_code_column}` = :index_code"
        )
        params: dict[str, object] = {"index_code": index_code}
        if start_date is not None:
            sql += f" AND `{settings.quant_index_dashboard_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date is not None:
            sql += f" AND `{settings.quant_index_dashboard_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.quant_index_dashboard_date_column}` ASC"
        return [dict(row) for row in self.db.execute(text(sql), params).mappings().all()]

    def get_index_dashboard(
        self,
        index_code: str,
        mode: str = "recent",
        start_date: date | None = None,
        end_date: date | None = None,
        market: str = "cn",
    ) -> dict:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"recent", "full"}:
            raise ValueError("unsupported mode")
        normalized_market = self._normalize_target_market(market)

        normalized_index_code = str(index_code or "").strip()
        if normalized_market == "cn" and normalized_index_code.lower() == BEIJING50_INDEX_NAME.lower():
            normalized_index_code = "BJ899050"
        if normalized_market == "cn" and normalized_index_code.lower() == "bj899050":
            normalized_index_code = "BJ899050"

        option = self._resolve_index_option(normalized_index_code, normalized_market)
        if option is None:
            raise ValueError("index not found")
        auxiliary_source_name = self._resolve_index_auxiliary_source_name(option["name"])

        using_explicit_window = start_date is not None or end_date is not None
        response_mode = "window" if using_explicit_window else normalized_mode

        cache_key = (
            f"{INDEX_DASHBOARD_CACHE_KEY_PREFIX}:{normalized_market}:{normalized_index_code}:{response_mode}:"
            f"{start_date.isoformat() if start_date else 'none'}:"
            f"{end_date.isoformat() if end_date else 'none'}"
        )
        cached = redis_client.get(cache_key)
        if cached:
            try:
                payload = json.loads(cached)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

        resolved_start_date = start_date
        if resolved_start_date is None and normalized_mode == "recent":
            resolved_start_date = self._resolve_recent_index_start_date(normalized_index_code, normalized_market)

        candles = self.stock_service.list_index_daily_kline(
            index_code=normalized_index_code,
            market=normalized_market,
            start_date=resolved_start_date,
            end_date=end_date,
        )

        if not self._index_supports_auxiliary_panels(normalized_market):
            supports_basis_panel = self._index_supports_basis(option["code"], option["name"], normalized_market)
            basis_rows = (
                self._load_basis_rows_for_adjustment(
                    option["code"],
                    option["name"],
                    normalized_market,
                    start_date=resolved_start_date,
                    end_date=end_date,
                )
                if supports_basis_panel
                else []
            )
            contract_roll_markers = (
                self._load_basis_contract_roll_markers(
                    option["code"],
                    option["name"],
                    normalized_market,
                    start_date=resolved_start_date,
                    end_date=end_date,
                )
                if supports_basis_panel
                else {}
            )
            auxiliary_rows = (
                self._load_us_auxiliary_rows(
                    option["code"],
                    option["name"],
                    start_date=resolved_start_date,
                    end_date=end_date,
                )
                if self._index_supports_us_auxiliary_panels(normalized_market)
                else {
                    "us_vix_rows": [],
                    "us_fear_greed_rows": [],
                    "us_hedge_proxy_rows": [],
                    "us_put_call_rows": [],
                    "us_treasury_yield_rows": [],
                    "us_credit_spread_rows": [],
                }
            )
            result = {
                "index": {"code": option["code"], "name": option["name"]},
                "market": normalized_market,
                "supports_auxiliary_panels": False,
                "supports_basis_panel": supports_basis_panel,
                "range_mode": response_mode,
                "candles": candles,
                "emotion_points": [],
                "basis_points": [
                    self._build_basis_point_payload(row, option["name"], contract_roll_markers)
                    for row in basis_rows
                ],
                "breadth_points": [],
                "vix_points": [],
                "us_vix_points": [
                    {
                        "trade_date": row["trade_date"],
                        "open_value": _to_float(row.get("open_value")) or 0.0,
                        "high_value": _to_float(row.get("high_value")) or 0.0,
                        "low_value": _to_float(row.get("low_value")) or 0.0,
                        "close_value": _to_float(row.get("close_value")) or 0.0,
                    }
                    for row in auxiliary_rows["us_vix_rows"]
                ],
                "us_fear_greed_points": [
                    {
                        "trade_date": row["trade_date"],
                        "fear_greed_value": _to_float(row.get("fear_greed_value")) or 0.0,
                        "sentiment_label": str(row.get("sentiment_label") or "").strip(),
                    }
                    for row in auxiliary_rows["us_fear_greed_rows"]
                ],
                "us_hedge_proxy_points": [
                    {
                        "report_date": row.get("report_date"),
                        "release_date": row["release_date"],
                        "contract_scope": str(row.get("contract_scope") or "").strip().upper(),
                        "long_value": _to_float(row.get("long_value")),
                        "short_value": _to_float(row.get("short_value")),
                        "ratio_value": _to_float(row.get("ratio_value")),
                    }
                    for row in auxiliary_rows["us_hedge_proxy_rows"]
                ],
                "us_put_call_points": [
                    {
                        "trade_date": row["trade_date"],
                        "total_put_call_ratio": _to_float(row.get("total_put_call_ratio")),
                        "index_put_call_ratio": _to_float(row.get("index_put_call_ratio")),
                        "equity_put_call_ratio": _to_float(row.get("equity_put_call_ratio")),
                        "etf_put_call_ratio": _to_float(row.get("etf_put_call_ratio")),
                    }
                    for row in auxiliary_rows["us_put_call_rows"]
                ],
                "cn_option_put_call_points": [],
                "cn_option_flow_put_call_points": [],
                "cffex_net_short_delta_points": [],
                "basis_delta_points": [],
                "us_treasury_yield_points": [
                    {
                        "trade_date": row["trade_date"],
                        "yield_3m": _to_float(row.get("yield_3m")),
                        "yield_2y": _to_float(row.get("yield_2y")),
                        "yield_10y": _to_float(row.get("yield_10y")),
                        "spread_10y_2y": _to_float(row.get("spread_10y_2y")),
                        "spread_10y_3m": _to_float(row.get("spread_10y_3m")),
                    }
                    for row in auxiliary_rows["us_treasury_yield_rows"]
                ],
                "us_credit_spread_points": [
                    {
                        "trade_date": row["trade_date"],
                        "high_yield_oas": _to_float(row.get("high_yield_oas")),
                    }
                    for row in auxiliary_rows["us_credit_spread_rows"]
                ],
            }
            redis_client.set(
                cache_key,
                json.dumps(result, ensure_ascii=False, default=str),
                ex=INDEX_DASHBOARD_CACHE_TTL_SECONDS,
            )
            return result

        try:
            self._ensure_index_dashboard_table_ready()
            rows = self._load_precomputed_index_indicator_rows(auxiliary_source_name)
        except SQLAlchemyError as exc:
            raise RuntimeError("failed to load precomputed quant index dashboard data") from exc

        if resolved_start_date is not None:
            rows = [row for row in rows if row.get("trade_date") is not None and row["trade_date"] >= resolved_start_date]
        if end_date is not None:
            rows = [row for row in rows if row.get("trade_date") is not None and row["trade_date"] <= end_date]

        if not candles:
            rows = []

        contract_roll_markers = self._load_basis_contract_roll_markers(
            option["code"],
            option["name"],
            normalized_market,
            start_date=resolved_start_date,
            end_date=end_date,
        )

        vix_rows: list[dict] = []
        qvix_code = self._resolve_index_vix_code(option["code"], option["name"], normalized_market)
        if qvix_code:
            vix_rows = self.stock_service.list_index_qvix_daily_data(
                qvix_code,
                start_date=resolved_start_date,
                end_date=end_date,
            )
        result = {
            "index": {"code": option["code"], "name": option["name"]},
            "market": normalized_market,
            "supports_auxiliary_panels": True,
            "supports_basis_panel": True,
            "range_mode": response_mode,
            "candles": candles,
            "emotion_points": [
                {
                    "trade_date": row["trade_date"],
                    "value": _to_float(row.get("emotion_value")) or 50.0,
                }
                for row in rows
            ],
            "basis_points": [
                self._build_basis_point_payload(row, auxiliary_source_name, contract_roll_markers)
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
            "vix_points": [
                {
                    "trade_date": row["trade_date"],
                    "open_price": _to_float(row.get("open_price")) or 0.0,
                    "high_price": _to_float(row.get("high_price")) or 0.0,
                    "low_price": _to_float(row.get("low_price")) or 0.0,
                    "close_price": _to_float(row.get("close_price")) or 0.0,
                }
                for row in vix_rows
            ],
            "us_vix_points": [],
            "us_fear_greed_points": [],
            "us_hedge_proxy_points": [],
            "us_put_call_points": [],
            "cn_option_put_call_points": [
                self._build_cn_option_put_call_point_payload(row)
                for row in rows
            ],
            "cn_option_flow_put_call_points": [
                self._build_cn_option_flow_put_call_point_payload(row)
                for row in rows
                if any(_to_float(row.get(column_name)) is not None for column_name, _alias in CN_OPTION_FLOW_PUT_CALL_FIELD_MAP)
            ],
            "cffex_net_short_delta_points": [
                self._build_cffex_net_short_delta_point_payload(row)
                for row in rows
                if any(
                    _to_float(row.get(column_name)) is not None
                    for _field_key, column_name, _payload_key in CFFEX_NET_SHORT_DELTA_FIELD_MAP
                )
            ],
            "basis_delta_points": [
                self._build_basis_delta_point_payload(row)
                for row in rows
                if any(
                    _to_float(row.get(column_name)) is not None
                    for _field_key, column_name, _payload_key in BASIS_DELTA_FIELD_MAP
                )
            ],
            "us_treasury_yield_points": [],
            "us_credit_spread_points": [],
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
        source_name = self._resolve_index_auxiliary_source_name(symbol_name)
        rows = self.stock_service.list_excel_index_emotions()
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            index_name = str(row.get("index_name", "")).strip()
            trade_date = _date_text(row.get("emotion_date"))
            emotion_value = _to_float(row.get("emotion_value"))
            if emotion_value is None:
                continue
            if source_name == SHANGHAI_INDEX_NAME:
                if index_name not in CORE_INDEX_NAMES:
                    continue
            elif index_name != source_name:
                continue
            grouped[trade_date].append(emotion_value)
        return {trade_date: sum(values) / len(values) for trade_date, values in grouped.items() if values}

    def _load_precomputed_index_indicator_rows(self, symbol_name: str) -> list[dict]:
        try:
            self._ensure_index_dashboard_table_ready()
        except RuntimeError:
            return []
        source_name = self._resolve_index_auxiliary_source_name(symbol_name)
        optional_selects = self._optional_index_dashboard_selects()

        sql = text(
            f"SELECT "
            f"`{settings.quant_index_dashboard_date_column}` AS trade_date, "
            f"`{settings.quant_index_dashboard_name_column}` AS index_name, "
            f"`{settings.quant_index_dashboard_emotion_column}` AS emotion_value, "
            f"`{settings.quant_index_dashboard_main_basis_column}` AS main_basis, "
            f"`{settings.quant_index_dashboard_month_basis_column}` AS month_basis, "
            f"`{settings.quant_index_dashboard_breadth_up_count_column}` AS up_count, "
            f"`{settings.quant_index_dashboard_breadth_total_count_column}` AS total_count, "
            f"`{settings.quant_index_dashboard_breadth_up_pct_column}` AS up_ratio_pct"
            f"{optional_selects} "
            f"FROM `{settings.quant_index_dashboard_table_name}` "
            f"WHERE `{settings.quant_index_dashboard_name_column}` = :index_name "
            f"ORDER BY `{settings.quant_index_dashboard_date_column}` ASC"
        )
        try:
            return [dict(row) for row in self.db.execute(sql, {"index_name": source_name}).mappings().all()]
        except SQLAlchemyError:
            return []

    def _build_basis_value_by_date(self, symbol_name: str) -> tuple[dict[str, float], dict[str, float]]:
        source_name = self._resolve_index_auxiliary_source_name(symbol_name)
        rows = self.stock_service.list_index_futures_basis()
        grouped_main: dict[str, list[float]] = defaultdict(list)
        grouped_month: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            index_name = str(row.get("index_name", "")).strip()
            trade_date = _date_text(row.get("trade_date"))
            main_basis = _to_float(row.get("main_basis"))
            month_basis = _to_float(row.get("month_basis"))
            if source_name == SHANGHAI_INDEX_NAME:
                if index_name not in CORE_INDEX_NAMES:
                    continue
            elif index_name != source_name:
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

    def _build_breadth_value_by_date(self) -> dict[str, float]:
        return {
            _date_text(item["trade_date"]): float(item["up_ratio_pct"])
            for item in self.list_index_breadth()
        }

    def _build_index_snapshots(self, target_code: str, symbol_name: str, params: dict, candles: list[dict]) -> list[dict]:
        sorted_candles = _sort_candles(candles)
        if not sorted_candles:
            return []

        times = [item["trade_date"] for item in sorted_candles]
        closes = [item["close"] for item in sorted_candles]
        ma_periods = _normalize_ma_periods(params)
        macd_params = params.get("macd", {})
        kdj_params = params.get("kdj", {})
        wr_params = params.get("wr", {})
        rsi_params = params.get("rsi", {})
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
        rsi_values = _calc_rsi(closes, int(rsi_params.get("period", 14)))
        precomputed_rows = self._load_precomputed_index_indicator_rows(symbol_name)
        if precomputed_rows:
            emotion_map = {
                _date_text(item["trade_date"]): _to_float(item.get("emotion_value")) or 50.0
                for item in precomputed_rows
            }
            basis_main_map = {
                _date_text(item["trade_date"]): _to_float(item.get("main_basis")) or 0.0
                for item in precomputed_rows
            }
            basis_month_map = {
                _date_text(item["trade_date"]): _to_float(item.get("month_basis")) or 0.0
                for item in precomputed_rows
            }
            breadth_map = {
                _date_text(item["trade_date"]): _to_float(item.get("up_ratio_pct")) or 0.0
                for item in precomputed_rows
            }
            option_put_call_maps = {
                field_key: {
                    _date_text(item["trade_date"]): _to_float(item.get(column_name))
                    for item in precomputed_rows
                }
                for field_key, column_name in CN_OPTION_PUT_CALL_FILTER_FIELD_MAP
            }
            option_flow_put_call_maps = {
                field_key: {
                    _date_text(item["trade_date"]): _to_float(item.get(column_name))
                    for item in precomputed_rows
                }
                for field_key, column_name in CN_OPTION_FLOW_PUT_CALL_FILTER_FIELD_MAP
            }
            cffex_net_short_delta_maps = {
                field_key: {
                    _date_text(item["trade_date"]): _to_float(item.get(column_name))
                    for item in precomputed_rows
                }
                for field_key, column_name, _payload_key in CFFEX_NET_SHORT_DELTA_FIELD_MAP
            }
            basis_delta_maps = {
                field_key: {
                    _date_text(item["trade_date"]): _to_float(item.get(column_name))
                    for item in precomputed_rows
                }
                for field_key, column_name, _payload_key in BASIS_DELTA_FIELD_MAP
            }
        else:
            emotion_map = self._build_emotion_value_by_date(symbol_name)
            basis_main_map, basis_month_map = self._build_basis_value_by_date(symbol_name)
            breadth_map = self._build_breadth_value_by_date()
            option_put_call_maps = {field_key: {} for field_key, _column_name in CN_OPTION_PUT_CALL_FILTER_FIELD_MAP}
            option_flow_put_call_maps = {
                field_key: {} for field_key, _column_name in CN_OPTION_FLOW_PUT_CALL_FILTER_FIELD_MAP
            }
            cffex_net_short_delta_maps = {
                field_key: {} for field_key, _column_name, _payload_key in CFFEX_NET_SHORT_DELTA_FIELD_MAP
            }
            basis_delta_maps = {
                field_key: {} for field_key, _column_name, _payload_key in BASIS_DELTA_FIELD_MAP
            }

        vix_by_date: dict[str, dict[str, float | None]] = {}
        qvix_code = self._resolve_index_vix_code(target_code, symbol_name, "cn")
        if qvix_code:
            first_trade_date = sorted_candles[0].get("trade_date")
            last_trade_date = sorted_candles[-1].get("trade_date")
            qvix_rows = self.stock_service.list_index_qvix_daily_data(
                qvix_code,
                start_date=first_trade_date if isinstance(first_trade_date, date) else None,
                end_date=last_trade_date if isinstance(last_trade_date, date) else None,
            )
            vix_by_date = {
                _date_text(item["trade_date"]): {
                    "vix-open": _to_float(item.get("open_price")),
                    "vix-high": _to_float(item.get("high_price")),
                    "vix-low": _to_float(item.get("low_price")),
                    "vix-close": _to_float(item.get("close_price")),
                }
                for item in qvix_rows
                if item.get("trade_date") is not None
            }

        snapshots: list[dict] = []
        for index, trade_date in enumerate(times):
            vix_values = vix_by_date.get(trade_date, {})
            snapshots.append(
                {
                    "trade_date": trade_date,
                    "close": closes[index],
                    "high": sorted_candles[index]["high"],
                    "low": sorted_candles[index]["low"],
                    "values": {
                        "emotion": emotion_map.get(trade_date, 50.0),
                        "basis-main": basis_main_map.get(trade_date, 0.0),
                        "basis-month": basis_month_map.get(trade_date, 0.0),
                        "breadth-up-pct": breadth_map.get(trade_date, 0.0),
                        "vix-open": vix_values.get("vix-open"),
                        "vix-high": vix_values.get("vix-high"),
                        "vix-low": vix_values.get("vix-low"),
                        "vix-close": vix_values.get("vix-close"),
                        "cn-option-put-call-current": option_put_call_maps["cn-option-put-call-current"].get(trade_date),
                        "cn-option-put-call-next": option_put_call_maps["cn-option-put-call-next"].get(trade_date),
                        "cn-option-put-call-quarter-1": option_put_call_maps["cn-option-put-call-quarter-1"].get(trade_date),
                        "cn-option-put-call-quarter-2": option_put_call_maps["cn-option-put-call-quarter-2"].get(trade_date),
                        "cn-option-flow-pc-volume": option_flow_put_call_maps["cn-option-flow-pc-volume"].get(trade_date),
                        "cn-option-flow-pc-turnover": option_flow_put_call_maps["cn-option-flow-pc-turnover"].get(trade_date),
                        **{
                            field_key: cffex_net_short_delta_maps[field_key].get(trade_date)
                            for field_key in CFFEX_NET_SHORT_DELTA_FILTER_KEYS
                        },
                        **{
                            field_key: basis_delta_maps[field_key].get(trade_date)
                            for field_key in BASIS_DELTA_FILTER_KEYS
                        },
                        "rsi": rsi_values[index],
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
        ma_periods = _normalize_ma_periods(params)
        macd_params = params.get("macd", {})
        kdj_params = params.get("kdj", {})
        wr_params = params.get("wr", {})
        rsi_params = params.get("rsi", {})
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
        rsi_values = _calc_rsi(closes, int(rsi_params.get("period", 14)))

        snapshots: list[dict] = []
        for index, trade_date in enumerate(times):
            snapshots.append(
                {
                    "trade_date": trade_date,
                    "close": closes[index],
                    "high": sorted_candles[index]["high"],
                    "low": sorted_candles[index]["low"],
                    "values": {
                        "pct-chg": sorted_candles[index]["pct_chg"],
                        "turnover-rate": (
                            sorted_candles[index]["turnover_rate"] * 100
                            if sorted_candles[index].get("turnover_rate") is not None
                            else None
                        ),
                        "rsi": rsi_values[index],
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
                        "target-ma-bias-1": _calc_ma_bias(closes[index], ma_values[0][index] if len(ma_values) > 0 else None),
                        "target-ma-bias-2": _calc_ma_bias(closes[index], ma_values[1][index] if len(ma_values) > 1 else None),
                        "target-ma-bias-3": _calc_ma_bias(closes[index], ma_values[2][index] if len(ma_values) > 2 else None),
                        "target-ma-bias-4": _calc_ma_bias(closes[index], ma_values[3][index] if len(ma_values) > 3 else None),
                        "boll-upper": boll_upper[index],
                        "boll-middle": boll_middle[index],
                        "boll-lower": boll_lower[index],
                    },
                }
            )
        return snapshots

    def _normalize_sequence_groups(self, raw_groups: object) -> list[dict]:
        if not isinstance(raw_groups, list):
            return []

        normalized_groups: list[dict] = []
        allowed_series_keys = set(SEQUENCE_STRATEGY_SERIES_KEYS)
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                continue
            raw_conditions = raw_group.get("conditions")
            if not isinstance(raw_conditions, list):
                continue

            conditions: list[dict] = []
            for raw_condition in raw_conditions:
                if not isinstance(raw_condition, dict):
                    continue
                series_key = str(raw_condition.get("series_key", "")).strip()
                if series_key in SEQUENCE_STRATEGY_NEW_HIGH_SERIES_KEYS:
                    conditions.append(
                        {
                            "series_key": series_key,
                            "operator": "gt",
                            "threshold": 0.0,
                            "consecutive_days": 1,
                        }
                    )
                    continue
                operator = str(raw_condition.get("operator", "")).strip()
                threshold = _normalize_threshold(raw_condition.get("threshold"))
                consecutive_days = raw_condition.get("consecutive_days")
                try:
                    consecutive_days_value = int(consecutive_days)
                except (TypeError, ValueError):
                    consecutive_days_value = 0
                if (
                    series_key not in allowed_series_keys
                    or operator not in SEQUENCE_STRATEGY_OPERATORS
                    or threshold is None
                    or consecutive_days_value <= 0
                ):
                    continue
                conditions.append(
                    {
                        "series_key": series_key,
                        "operator": operator,
                        "threshold": threshold,
                        "consecutive_days": consecutive_days_value,
                    }
                )

            if conditions:
                normalized_groups.append({"conditions": conditions})

        return normalized_groups

    def _get_sequence_groups(self, strategy: QuantStrategyConfig, side: str) -> list[dict]:
        raw_groups = getattr(strategy, f"{side}_sequence_groups", None)
        return self._normalize_sequence_groups(raw_groups)

    def _sequence_group_hit_indexes(self, snapshots: list[dict], index: int, groups: list[dict]) -> list[int]:
        matches: list[int] = []
        for group_index, group in enumerate(groups):
            if self._matches_sequence_group_at(snapshots, index, group):
                matches.append(group_index + 1)
        return matches

    def _max_consecutive_days_in_groups(self, groups: list[dict]) -> int:
        max_days = 0
        for group in groups:
            for condition in group.get("conditions", []):
                try:
                    max_days = max(max_days, int(condition.get("consecutive_days") or 0))
                except (TypeError, ValueError):
                    continue
        return max_days

    def _sequence_groups_require_breadth(self, groups: list[dict]) -> bool:
        for group in groups:
            for condition in group.get("conditions", []):
                if str(condition.get("series_key", "")).strip() == "market-breadth-up-pct":
                    return True
        return False

    def _load_sequence_breadth_values_by_date(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, float]:
        params: dict[str, object] = {}
        sql = (
            "SELECT trade_date, index_name, breadth_up_pct "
            "FROM quant_index_dashboard_daily "
            "WHERE breadth_up_pct IS NOT NULL"
        )
        if start_date is not None:
            params["start_date"] = start_date
            sql += " AND trade_date >= :start_date"
        if end_date is not None:
            params["end_date"] = end_date
            sql += " AND trade_date <= :end_date"
        rows = [dict(row) for row in self.db.execute(text(sql), params).mappings().all()]
        return _build_sequence_dashboard_breadth_values(rows)

    def _sequence_groups_require_market_macro(self, groups: list[dict]) -> bool:
        for group in groups:
            for condition in group.get("conditions", []):
                if str(condition.get("series_key", "")).strip() in SEQUENCE_STRATEGY_MARKET_MACRO_SERIES_KEYS:
                    return True
        return False

    def _sequence_groups_require_full_price_history(self, groups: list[dict]) -> bool:
        for group in groups:
            for condition in group.get("conditions", []):
                if str(condition.get("series_key", "")).strip() in SEQUENCE_STRATEGY_NEW_HIGH_SERIES_KEYS:
                    return True
        return False

    def _sequence_groups_require_ma_bias(self, groups: list[dict]) -> bool:
        for group in groups:
            for condition in group.get("conditions", []):
                if str(condition.get("series_key", "")).strip() in SEQUENCE_STRATEGY_MA_BIAS_SERIES_KEYS:
                    return True
        return False

    def _load_sequence_market_macro_values_by_date(
        self,
        groups: list[dict],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, dict[str, float]]:
        if not self._sequence_groups_require_market_macro(groups):
            return {}

        dashboard_params: dict[str, object] = {}
        dashboard_sql = (
            "SELECT trade_date, index_name, emotion_value, main_basis "
            "FROM quant_index_dashboard_daily"
        )
        dashboard_filters: list[str] = []
        if start_date is not None:
            dashboard_params["start_date"] = start_date
            dashboard_filters.append("trade_date >= :start_date")
        if end_date is not None:
            dashboard_params["end_date"] = end_date
            dashboard_filters.append("trade_date <= :end_date")
        if dashboard_filters:
            dashboard_sql += " WHERE " + " AND ".join(dashboard_filters)
        dashboard_rows = [dict(row) for row in self.db.execute(text(dashboard_sql), dashboard_params).mappings().all()]
        macro_values = _build_sequence_dashboard_macro_values(dashboard_rows)

        qvix_params: dict[str, object] = {}
        qvix_sql = "SELECT trade_date, close_price FROM index_qvix_daily_data"
        qvix_filters = ["close_price > 0"]
        if start_date is not None:
            qvix_params["start_date"] = start_date
            qvix_filters.append("trade_date >= :start_date")
        if end_date is not None:
            qvix_params["end_date"] = end_date
            qvix_filters.append("trade_date <= :end_date")
        qvix_sql += " WHERE " + " AND ".join(qvix_filters)
        qvix_values = _build_sequence_qvix_values(
            [dict(row) for row in self.db.execute(text(qvix_sql), qvix_params).mappings().all()]
        )
        for trade_date, qvix_value in qvix_values.items():
            macro_values.setdefault(trade_date, {})["market-qvix"] = qvix_value
        return macro_values

    def _build_sequence_snapshots(self, strategy: QuantStrategyConfig) -> list[dict]:
        strategy_type = str(strategy.strategy_type or "").strip().lower()
        if strategy_type == "index":
            target_candles = self.stock_service.list_index_daily_kline(
                strategy.target_code,
                market=self._normalize_target_market(getattr(strategy, "target_market", "cn")),
            )
        elif strategy_type == "stock":
            target_candles = self.stock_service.list_daily_kline(strategy.target_code)
        elif strategy_type == "etf":
            target_candles = self.stock_service.list_etf_daily_kline(strategy.target_code)
        else:
            return []

        sorted_candles = _sort_candles(target_candles)
        if not sorted_candles:
            return []

        buy_groups = self._get_sequence_groups(strategy, "buy")
        sell_groups = self._get_sequence_groups(strategy, "sell")
        requires_breadth = self._sequence_groups_require_breadth(buy_groups) or self._sequence_groups_require_breadth(sell_groups)
        requires_macro = self._sequence_groups_require_market_macro(buy_groups) or self._sequence_groups_require_market_macro(sell_groups)
        breadth_by_date = (
            self._load_sequence_breadth_values_by_date()
            if requires_breadth
            else {}
        )
        macro_by_date = (
            self._load_sequence_market_macro_values_by_date(buy_groups + sell_groups)
            if requires_macro
            else {}
        )
        ma_values: list[list[float | None]] = []
        if strategy_type in {"stock", "etf"}:
            closes = [item["close"] for item in sorted_candles]
            ma_values = [_calc_sma(closes, period) for period in _normalize_ma_periods(strategy.indicator_params or {})]

        snapshots: list[dict] = []
        prior_max_high: float | None = None
        prior_max_close: float | None = None
        for index, candle in enumerate(sorted_candles):
            trade_date = candle["trade_date"]
            high_price = _to_float(candle.get("high"))
            close_price = _to_float(candle.get("close"))
            high_is_new_high = (
                high_price is not None and prior_max_high is not None and high_price > prior_max_high
            )
            close_is_new_high = (
                close_price is not None and prior_max_close is not None and close_price > prior_max_close
            )
            snapshots.append(
                {
                    "trade_date": trade_date,
                    "values": {
                        "target-up-pct": candle.get("pct_chg") if _to_float(candle.get("pct_chg")) and _to_float(candle.get("pct_chg")) > 0 else None,
                        "target-down-pct": abs(_to_float(candle.get("pct_chg"))) if _to_float(candle.get("pct_chg")) and _to_float(candle.get("pct_chg")) < 0 else None,
                        "market-breadth-up-pct": breadth_by_date.get(trade_date),
                        **(macro_by_date.get(_date_text(trade_date), {})),
                        "target-high-new-high": 1.0 if high_is_new_high else 0.0,
                        "target-close-new-high": 1.0 if close_is_new_high else 0.0,
                        "target-ma-bias-1": _calc_ma_bias(close_price, ma_values[0][index] if len(ma_values) > 0 else None),
                        "target-ma-bias-2": _calc_ma_bias(close_price, ma_values[1][index] if len(ma_values) > 1 else None),
                        "target-ma-bias-3": _calc_ma_bias(close_price, ma_values[2][index] if len(ma_values) > 2 else None),
                        "target-ma-bias-4": _calc_ma_bias(close_price, ma_values[3][index] if len(ma_values) > 3 else None),
                    },
                }
            )
            if high_price is not None:
                prior_max_high = high_price if prior_max_high is None else max(prior_max_high, high_price)
            if close_price is not None:
                prior_max_close = close_price if prior_max_close is None else max(prior_max_close, close_price)
        return snapshots

    def _matches_sequence_condition_at(self, snapshots: list[dict], index: int, condition: dict) -> bool:
        consecutive_days = int(condition.get("consecutive_days") or 0)
        if consecutive_days <= 0 or index - consecutive_days + 1 < 0:
            return False

        series_key = str(condition.get("series_key", "")).strip()
        operator = str(condition.get("operator", "")).strip()
        threshold = _normalize_threshold(condition.get("threshold"))
        if series_key not in SEQUENCE_STRATEGY_SERIES_KEYS or operator not in SEQUENCE_STRATEGY_OPERATORS or threshold is None:
            return False

        start_index = index - consecutive_days + 1
        for cursor in range(start_index, index + 1):
            value = snapshots[cursor].get("values", {}).get(series_key)
            if not _sequence_operator_matches(value, operator, threshold):
                return False
        return True

    def _matches_sequence_group_at(self, snapshots: list[dict], index: int, group: dict) -> bool:
        conditions = group.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            return False
        return all(self._matches_sequence_condition_at(snapshots, index, condition) for condition in conditions)

    def _build_sequence_signal_map(self, strategy: QuantStrategyConfig, snapshots: list[dict]) -> dict[str, str]:
        buy_groups = self._get_sequence_groups(strategy, "buy")
        sell_groups = self._get_sequence_groups(strategy, "sell")
        signal_map: dict[str, str] = {}
        for index, snapshot in enumerate(snapshots):
            is_buy = any(self._matches_sequence_group_at(snapshots, index, group) for group in buy_groups)
            is_sell = any(self._matches_sequence_group_at(snapshots, index, group) for group in sell_groups)
            if is_buy and is_sell:
                signal_map[snapshot["trade_date"]] = "purple"
            elif is_buy:
                signal_map[snapshot["trade_date"]] = "blue"
            elif is_sell:
                signal_map[snapshot["trade_date"]] = "red"
        return signal_map

    def _parse_optional_date(self, value: object) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        text_value = str(value).strip()
        if not text_value:
            return None
        return date.fromisoformat(text_value)

    def _normalize_scan_payload(self, payload: dict) -> dict:
        strategy_type = str(payload.get("strategy_type", "")).strip().lower()
        if strategy_type not in {"stock", "etf"}:
            raise ValueError("market scan only supports stock or etf")
        buy_groups = self._normalize_sequence_groups(payload.get("buy_sequence_groups"))
        if not buy_groups:
            raise ValueError("market scan requires at least one buy rule group")
        scan_start_date = self._parse_optional_date(payload.get("scan_start_date"))
        scan_end_date = self._parse_optional_date(payload.get("scan_end_date"))
        if scan_start_date is None or scan_end_date is None:
            raise ValueError("market scan requires scan_start_date and scan_end_date")
        if scan_end_date < scan_start_date:
            raise ValueError("scan_end_date must be later than or equal to scan_start_date")
        return {
            "strategy_type": strategy_type,
            "indicator_params": payload.get("indicator_params") if isinstance(payload.get("indicator_params"), dict) else {},
            "buy_sequence_groups": buy_groups,
            "scan_trade_config": self._normalize_scan_trade_config(payload.get("scan_trade_config") or {}),
            "scan_start_date": scan_start_date,
            "scan_end_date": scan_end_date,
        }

    def _resolve_scan_sell_trigger_lookback_days(self, indicator_params: dict, trade_config: dict) -> int:
        sell_trigger = trade_config.get("sell_trigger")
        if not isinstance(sell_trigger, dict) or not sell_trigger.get("enabled"):
            return 0
        target = str(sell_trigger.get("target") or "")
        if target.startswith("ma-"):
            try:
                period_index = int(target.split("-", 1)[1]) - 1
            except (IndexError, TypeError, ValueError):
                period_index = 0
            raw_periods = indicator_params.get("ma", {}).get("periods", [5, 10, 20, 60])
            period_values = raw_periods if isinstance(raw_periods, list) else [5, 10, 20, 60]
            try:
                period = int(period_values[period_index])
            except (IndexError, TypeError, ValueError):
                period = 60
        else:
            try:
                period = int(indicator_params.get("boll", {}).get("period", 20))
            except (TypeError, ValueError):
                period = 20
        return max(60, period * 4)

    def _resolve_sequence_ma_bias_lookback_days(self, groups: list[dict], indicator_params: dict) -> int:
        period_indexes: set[int] = set()
        for group in groups:
            for condition in group.get("conditions", []):
                series_key = str(condition.get("series_key", "")).strip()
                if series_key not in SEQUENCE_STRATEGY_MA_BIAS_SERIES_KEYS:
                    continue
                try:
                    period_indexes.add(int(series_key.rsplit("-", 1)[1]) - 1)
                except (IndexError, TypeError, ValueError):
                    continue
        if not period_indexes:
            return 0
        ma_periods = _normalize_ma_periods(indicator_params)
        selected_periods = [ma_periods[index] for index in period_indexes if 0 <= index < len(ma_periods)]
        if not selected_periods:
            return 0
        max_period = max(selected_periods)
        return max(60, max_period * 4)

    def _resolve_scan_query_start_date(
        self,
        start_date: date,
        buy_groups: list[dict],
        indicator_params: dict | None = None,
        trade_config: dict | None = None,
    ) -> date:
        max_days = self._max_consecutive_days_in_groups(buy_groups)
        sell_trigger_lookback = self._resolve_scan_sell_trigger_lookback_days(
            indicator_params or {},
            trade_config or {},
        )
        ma_bias_lookback = self._resolve_sequence_ma_bias_lookback_days(buy_groups, indicator_params or {})
        lookback_days = max(60, max_days * 5, sell_trigger_lookback, ma_bias_lookback)
        return start_date - timedelta(days=lookback_days)

    def _normalize_scan_page(self, page: int | None = None, page_size: int | None = None) -> tuple[int, int]:
        normalized_page = int(page or 1)
        normalized_size = int(page_size or SCAN_EVENT_PAGE_SIZE)
        normalized_page = max(normalized_page, 1)
        normalized_size = max(1, min(normalized_size, SCAN_EVENT_PAGE_SIZE_MAX))
        return normalized_page, normalized_size

    def _serialize_scan_payload_for_cache(self, normalized_payload: dict) -> dict:
        return {
            "strategy_type": normalized_payload["strategy_type"],
            "indicator_params": normalized_payload["indicator_params"],
            "buy_sequence_groups": normalized_payload["buy_sequence_groups"],
            "scan_trade_config": normalized_payload["scan_trade_config"],
            "scan_start_date": normalized_payload["scan_start_date"].isoformat(),
            "scan_end_date": normalized_payload["scan_end_date"].isoformat(),
        }

    def _build_scan_result_id(self, owner_user_id: int, serialized_payload: dict) -> str:
        serialized_text = json.dumps(serialized_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha1(f"{owner_user_id}:{serialized_text}".encode("utf-8")).hexdigest()

    def _scan_result_cache_key(self, scan_result_id: str) -> str:
        return f"{SCAN_RESULT_CACHE_KEY_PREFIX}:{scan_result_id}"

    def _store_scan_result(
        self,
        *,
        scan_result_id: str,
        owner_user_id: int,
        normalized_payload: dict,
        matched_events: list[dict],
    ) -> dict:
        payload = {
            "scan_result_id": scan_result_id,
            "owner_user_id": owner_user_id,
            "normalized_payload": self._serialize_scan_payload_for_cache(normalized_payload),
            "matched_events": matched_events,
            "matched_event_count": len(matched_events),
            "tradable_event_count": sum(1 for event in matched_events if event.get("tradable")),
        }
        redis_client.set(
            self._scan_result_cache_key(scan_result_id),
            json.dumps(payload, ensure_ascii=False, default=str),
            ex=SCAN_RESULT_CACHE_TTL_SECONDS,
        )
        return payload

    def _load_scan_result(self, scan_result_id: str, owner_user_id: int) -> dict:
        cached = redis_client.get(self._scan_result_cache_key(scan_result_id))
        if not cached:
            raise ValueError("scan result not found")
        try:
            payload = json.loads(cached)
        except json.JSONDecodeError as exc:
            raise ValueError("scan result not found") from exc
        if int(payload.get("owner_user_id") or 0) != owner_user_id:
            raise ValueError("scan result not found")
        redis_client.expire(self._scan_result_cache_key(scan_result_id), SCAN_RESULT_CACHE_TTL_SECONDS)
        return payload

    def _paginate_scan_events(self, matched_events: list[dict], page: int | None = None, page_size: int | None = None) -> dict:
        normalized_page, normalized_size = self._normalize_scan_page(page, page_size)
        total_count = len(matched_events)
        offset = (normalized_page - 1) * normalized_size
        return {
            "page": normalized_page,
            "page_size": normalized_size,
            "total_event_count": total_count,
            "matched_events": matched_events[offset : offset + normalized_size],
        }

    def _resolve_scan_lot_rule(self, strategy_type: str, board: str | None) -> dict | None:
        if strategy_type == "etf":
            return {"min_qty": 100, "step": 100, "mode": "multiple", "label": "ETF 100份起，100份递增"}
        normalized_board = str(board or "").strip()
        if not normalized_board:
            return None
        if "科创板" in normalized_board:
            return {"min_qty": 200, "step": 1, "mode": "after_minimum", "label": "科创板 200股起，200股以上每次 1 股"}
        if "北交所" in normalized_board or "北证" in normalized_board:
            return {"min_qty": 100, "step": 1, "mode": "after_minimum", "label": "北交所 100股起，100股以上每次 1 股"}
        if "主板" in normalized_board:
            return {"min_qty": 100, "step": 100, "mode": "multiple", "label": "主板 100股起，100股递增"}
        if "创业板" in normalized_board:
            return {"min_qty": 100, "step": 100, "mode": "multiple", "label": "创业板 100股起，100股递增"}
        return None

    def _round_up_lot_quantity(self, raw_quantity: float, lot_rule: dict) -> int | None:
        if raw_quantity <= 0:
            return None
        min_qty = int(lot_rule.get("min_qty") or 0)
        step = int(lot_rule.get("step") or 1)
        mode = str(lot_rule.get("mode") or "multiple")
        if mode == "after_minimum":
            return max(min_qty, int(ceil(raw_quantity)))
        return max(min_qty, int(ceil(raw_quantity / step) * step))

    def _is_valid_scan_lot_quantity(self, quantity: int | None, lot_rule: dict | None) -> bool:
        if quantity is None or lot_rule is None:
            return False
        min_qty = int(lot_rule.get("min_qty") or 0)
        step = int(lot_rule.get("step") or 1)
        mode = str(lot_rule.get("mode") or "multiple")
        if quantity < min_qty or step <= 0:
            return False
        if mode == "after_minimum":
            return (quantity - min_qty) % step == 0
        return quantity % step == 0

    def _resolve_scan_board_filter_key(self, board: object) -> str | None:
        normalized_board = str(board or "").strip()
        if not normalized_board:
            return None
        if "科创板" in normalized_board:
            return "star"
        if "北交所" in normalized_board or "北证" in normalized_board:
            return "bse"
        if "创业板" in normalized_board:
            return "chinext"
        if "主板" in normalized_board:
            return "main"
        return None

    def _scan_board_is_allowed(self, board: object, board_filters: list[str]) -> bool:
        if not board_filters:
            return True
        board_key = self._resolve_scan_board_filter_key(board)
        return board_key in set(board_filters)

    def _build_scan_snapshots(
        self,
        candles: list[dict],
        breadth_by_date: dict[str, float | None],
        *,
        initial_max_high: object = None,
        initial_max_close: object = None,
        macro_by_date: dict[str, dict[str, float]] | None = None,
        indicator_params: dict | None = None,
    ) -> list[dict]:
        snapshots: list[dict] = []
        prior_max_high = _to_float(initial_max_high)
        prior_max_close = _to_float(initial_max_close)
        macro_by_date = macro_by_date or {}
        ma_values: list[list[float | None]] = []
        if indicator_params is not None:
            closes = [candle.get("close") for candle in candles]
            ma_values = [_calc_sma_nullable(closes, period) for period in _normalize_ma_periods(indicator_params)]
        for index, candle in enumerate(candles):
            trade_date = _date_text(candle.get("trade_date"))
            pct_chg = _to_float(candle.get("pct_chg"))
            high_price = _to_float(candle.get("high"))
            close_price = _to_float(candle.get("close"))
            high_is_new_high = (
                high_price is not None and prior_max_high is not None and high_price > prior_max_high
            )
            close_is_new_high = (
                close_price is not None and prior_max_close is not None and close_price > prior_max_close
            )
            snapshots.append(
                {
                    "trade_date": trade_date,
                    "values": {
                        "target-up-pct": pct_chg if pct_chg is not None and pct_chg > 0 else None,
                        "target-down-pct": abs(pct_chg) if pct_chg is not None and pct_chg < 0 else None,
                        "market-breadth-up-pct": breadth_by_date.get(trade_date),
                        **macro_by_date.get(trade_date, {}),
                        "target-high-new-high": 1.0 if high_is_new_high else 0.0,
                        "target-close-new-high": 1.0 if close_is_new_high else 0.0,
                        "target-ma-bias-1": _calc_ma_bias(close_price, ma_values[0][index] if len(ma_values) > 0 else None),
                        "target-ma-bias-2": _calc_ma_bias(close_price, ma_values[1][index] if len(ma_values) > 1 else None),
                        "target-ma-bias-3": _calc_ma_bias(close_price, ma_values[2][index] if len(ma_values) > 2 else None),
                        "target-ma-bias-4": _calc_ma_bias(close_price, ma_values[3][index] if len(ma_values) > 3 else None),
                    },
                }
            )
            if high_price is not None:
                prior_max_high = high_price if prior_max_high is None else max(prior_max_high, high_price)
            if close_price is not None:
                prior_max_close = close_price if prior_max_close is None else max(prior_max_close, close_price)
        return snapshots

    def _sequence_condition_cache_key(self, condition: dict) -> tuple[str, str, float, int] | None:
        series_key = str(condition.get("series_key", "")).strip()
        operator = str(condition.get("operator", "")).strip()
        threshold = _normalize_threshold(condition.get("threshold"))
        consecutive_days = int(condition.get("consecutive_days") or 0)
        if (
            series_key not in SEQUENCE_STRATEGY_SERIES_KEYS
            or operator not in SEQUENCE_STRATEGY_OPERATORS
            or threshold is None
            or consecutive_days <= 0
        ):
            return None
        return (series_key, operator, float(threshold), consecutive_days)

    def _build_scan_group_hits(self, snapshots: list[dict], groups: list[dict]) -> list[list[int]]:
        if not snapshots or not groups:
            return [[] for _ in snapshots]

        condition_keys: dict[tuple[str, str, float, int], tuple[str, str, float, int]] = {}
        group_condition_keys: list[list[tuple[str, str, float, int]]] = []
        for group in groups:
            normalized_keys: list[tuple[str, str, float, int]] = []
            for condition in group.get("conditions", []):
                condition_key = self._sequence_condition_cache_key(condition)
                if condition_key is None:
                    continue
                condition_keys[condition_key] = condition_key
                normalized_keys.append(condition_key)
            group_condition_keys.append(normalized_keys)

        if not condition_keys:
            return [[] for _ in snapshots]

        condition_matches: dict[tuple[str, str, float, int], list[bool]] = {}
        for condition_key in condition_keys:
            series_key, operator, threshold, consecutive_days = condition_key
            streak = 0
            matches = [False] * len(snapshots)
            for index, snapshot in enumerate(snapshots):
                value = snapshot.get("values", {}).get(series_key)
                is_match = _sequence_operator_matches(value, operator, threshold)
                streak = streak + 1 if is_match else 0
                matches[index] = streak >= consecutive_days
            condition_matches[condition_key] = matches

        hit_indexes_by_snapshot: list[list[int]] = [[] for _ in snapshots]
        for group_index, normalized_keys in enumerate(group_condition_keys):
            if not normalized_keys:
                continue
            for index in range(len(snapshots)):
                if all(condition_matches[condition_key][index] for condition_key in normalized_keys):
                    hit_indexes_by_snapshot[index].append(group_index + 1)
        return hit_indexes_by_snapshot

    def _matches_scan_sell_trigger_at(self, snapshot: dict | None, sell_trigger: dict | None) -> bool:
        if not snapshot or not isinstance(sell_trigger, dict) or not sell_trigger.get("enabled"):
            return False
        close_price = _to_float(snapshot.get("close"))
        target_value = _to_float(snapshot.get("values", {}).get(str(sell_trigger.get("target") or "")))
        operator = str(sell_trigger.get("operator") or "")
        if close_price is None or target_value is None:
            return False
        if operator == "gt":
            return close_price > target_value
        if operator == "lt":
            return close_price < target_value
        return False

    def _last_candle_index_on_or_before(self, candles: list[dict], end_date_text: str) -> int | None:
        last_index: int | None = None
        for index, candle in enumerate(candles):
            if _date_text(candle.get("trade_date")) <= end_date_text:
                last_index = index
            else:
                break
        return last_index

    def _scan_execution_order(self, basis: object) -> int:
        return 0 if str(basis or "open").strip().lower() == "open" else 1

    def _scan_event_is_during_open_position(
        self,
        *,
        signal_rank: tuple[object, int],
        buy_rank: tuple[object, int],
        active_sell_rank: tuple[object, int] | None,
    ) -> bool:
        if active_sell_rank is None:
            return False
        if buy_rank <= active_sell_rank:
            return True
        return signal_rank < active_sell_rank

    def _build_market_scan_events(self, payload: dict) -> tuple[dict, list[dict]]:
        normalized_payload = self._normalize_scan_payload(payload)
        requires_full_price_history = self._sequence_groups_require_full_price_history(
            normalized_payload["buy_sequence_groups"]
        )
        requires_ma_bias = self._sequence_groups_require_ma_bias(normalized_payload["buy_sequence_groups"])
        query_start_date = self._resolve_scan_query_start_date(
            normalized_payload["scan_start_date"],
            normalized_payload["buy_sequence_groups"],
            normalized_payload["indicator_params"],
            normalized_payload["scan_trade_config"],
        )
        strategy_type = normalized_payload["strategy_type"]
        trade_config = normalized_payload["scan_trade_config"]
        board_filters = trade_config.get("board_filters") or []
        sell_trigger = trade_config.get("sell_trigger")
        uses_dynamic_sell = isinstance(sell_trigger, dict) and bool(sell_trigger.get("enabled"))
        query_end_date = (
            normalized_payload["scan_end_date"] + timedelta(days=30)
            if uses_dynamic_sell
            else normalized_payload["scan_end_date"]
        )
        if strategy_type == "stock":
            scan_universe = self.stock_service.list_stock_scan_universe(
                start_date=query_start_date,
                end_date=query_end_date,
                history_max_before=query_start_date if requires_full_price_history else None,
            )
        else:
            scan_universe = self.stock_service.list_etf_scan_universe(
                start_date=query_start_date,
                end_date=query_end_date,
                history_max_before=query_start_date if requires_full_price_history else None,
            )

        breadth_by_date = (
            self._load_sequence_breadth_values_by_date(
                start_date=query_start_date,
                end_date=query_end_date,
            )
            if self._sequence_groups_require_breadth(normalized_payload["buy_sequence_groups"])
            else {}
        )
        macro_by_date = self._load_sequence_market_macro_values_by_date(
            normalized_payload["buy_sequence_groups"],
            start_date=query_start_date,
            end_date=query_end_date,
        )

        buy_offset = int(trade_config["buy_offset_trading_days"])
        sell_offset = int(trade_config["sell_offset_trading_days"])
        buy_basis = str(trade_config["buy_price_basis"])
        sell_basis = str(trade_config["sell_price_basis"])
        scan_start_date_text = normalized_payload["scan_start_date"].isoformat()
        scan_end_date_text = normalized_payload["scan_end_date"].isoformat()

        matched_events: list[dict] = []

        for target_code, target_payload in sorted(scan_universe.items()):
            if strategy_type == "stock" and not self._scan_board_is_allowed(target_payload.get("board"), board_filters):
                continue
            target_candles = target_payload.get("candles") or []
            if not target_candles:
                continue
            snapshots = self._build_scan_snapshots(
                target_candles,
                breadth_by_date,
                initial_max_high=target_payload.get("history_max_high"),
                initial_max_close=target_payload.get("history_max_close"),
                macro_by_date=macro_by_date,
                indicator_params=normalized_payload["indicator_params"] if requires_ma_bias else None,
            )
            if not snapshots:
                continue
            hit_buy_groups_by_index = self._build_scan_group_hits(snapshots, normalized_payload["buy_sequence_groups"])
            indicator_snapshots_by_date = (
                {
                    _date_text(item.get("trade_date")): item
                    for item in self._build_stock_snapshots(normalized_payload["indicator_params"], target_candles)
                }
                if uses_dynamic_sell
                else {}
            )
            fallback_sell_index = self._last_candle_index_on_or_before(target_candles, scan_end_date_text)
            board = target_payload.get("board")
            lot_rule = self._resolve_scan_lot_rule(strategy_type, board)
            active_sell_rank: tuple[int, int] | None = None
            for index, (snapshot, hit_buy_groups) in enumerate(zip(snapshots, hit_buy_groups_by_index, strict=False)):
                signal_date = _date_text(snapshot["trade_date"])
                if signal_date < scan_start_date_text or signal_date > scan_end_date_text:
                    continue
                if not hit_buy_groups:
                    continue

                buy_index = index + buy_offset
                sell_index = index + sell_offset
                disabled_reason: str | None = None
                buy_date: str | None = None
                sell_date: str | None = None
                sell_trigger_date: str | None = None
                sell_reason: str | None = "trigger" if uses_dynamic_sell else "offset"
                buy_price: float | None = None
                sell_price: float | None = None
                planned_quantity: int | None = None
                planned_buy_amount: float | None = None
                tradable = True
                buy_rank: tuple[int, int] | None = None
                sell_rank: tuple[int, int] | None = None

                if buy_index >= len(target_candles):
                    tradable = False
                    disabled_reason = "买入日期不足"
                else:
                    buy_candle = target_candles[buy_index]
                    buy_date = buy_candle["trade_date"]
                    buy_price = float(buy_candle[buy_basis])
                    buy_rank = (buy_index, self._scan_execution_order(buy_basis))

                if buy_rank is not None and self._scan_event_is_during_open_position(
                    signal_rank=(index, 1),
                    buy_rank=buy_rank,
                    active_sell_rank=active_sell_rank,
                ):
                    continue

                if tradable and uses_dynamic_sell:
                    if fallback_sell_index is None:
                        tradable = False
                        disabled_reason = "扫描结束日前无可用卖出价格"
                    elif buy_index > fallback_sell_index:
                        tradable = False
                        disabled_reason = "买入执行日超过扫描结束日"
                    else:
                        trigger_start_index = buy_index if buy_basis == "open" else buy_index + 1
                        trigger_index: int | None = None
                        for cursor in range(trigger_start_index, fallback_sell_index + 1):
                            cursor_date = _date_text(target_candles[cursor].get("trade_date"))
                            if self._matches_scan_sell_trigger_at(
                                indicator_snapshots_by_date.get(cursor_date),
                                sell_trigger,
                            ):
                                trigger_index = cursor
                                break

                        if trigger_index is not None:
                            sell_trigger_date = _date_text(target_candles[trigger_index].get("trade_date"))
                            sell_reason = "trigger"
                            execution_index = trigger_index + 1
                            if execution_index >= len(target_candles):
                                tradable = False
                                disabled_reason = "缺少次日卖出执行价"
                            else:
                                sell_candle = target_candles[execution_index]
                                sell_date = _date_text(sell_candle.get("trade_date"))
                                sell_price = float(sell_candle[sell_basis])
                        else:
                            sell_reason = "fallback_end"
                            sell_candle = target_candles[fallback_sell_index]
                            sell_date = _date_text(sell_candle.get("trade_date"))
                            sell_price = float(sell_candle["close"])
                elif tradable and sell_index >= len(target_candles):
                    tradable = False
                    disabled_reason = "卖出日期不足"
                elif tradable:
                    sell_candle = target_candles[sell_index]
                    sell_date = _date_text(sell_candle.get("trade_date"))
                    sell_price = float(sell_candle[sell_basis])

                if tradable and buy_date and sell_date:
                    if uses_dynamic_sell and sell_reason == "fallback_end":
                        sell_rank = (fallback_sell_index if fallback_sell_index is not None else -1, 1)
                    elif uses_dynamic_sell:
                        sell_rank = (
                            next(
                                (
                                    cursor
                                    for cursor, candle in enumerate(target_candles)
                                    if _date_text(candle.get("trade_date")) == sell_date
                                ),
                                -1,
                            ),
                            self._scan_execution_order(sell_basis),
                        )
                    else:
                        sell_rank = (sell_index, self._scan_execution_order(sell_basis))
                    if buy_rank is not None and sell_rank <= buy_rank:
                        tradable = False
                        disabled_reason = "卖出执行时点必须晚于买入"

                if tradable and ((buy_price or 0) <= 0 or (sell_price or 0) <= 0):
                    tradable = False
                    disabled_reason = "买卖价格不可用"

                if tradable and lot_rule is None:
                    tradable = False
                    disabled_reason = "无法根据 board 判断最小交易单位"

                if tradable and buy_price and lot_rule is not None:
                    raw_quantity = float(trade_config["buy_amount_per_event"]) / buy_price
                    planned_quantity = self._round_up_lot_quantity(raw_quantity, lot_rule)
                    if planned_quantity is None:
                        tradable = False
                        disabled_reason = "无法计算合法买入数量"
                    elif not self._is_valid_scan_lot_quantity(planned_quantity, lot_rule):
                        tradable = False
                        disabled_reason = f"买入数量不符合交易单位：{lot_rule['label']}"
                    else:
                        planned_buy_amount = _round_metric(planned_quantity * buy_price)

                matched_events.append(
                    {
                        "event_id": f"{strategy_type}:{target_code}:{signal_date}",
                        "target_type": strategy_type,
                        "target_code": target_code,
                        "target_name": target_payload.get("target_name") or target_code,
                        "signal_date": signal_date,
                        "buy_date": buy_date,
                        "sell_date": sell_date,
                        "sell_trigger_date": sell_trigger_date,
                        "sell_reason": sell_reason,
                        "hit_buy_groups": hit_buy_groups,
                        "tradable": tradable,
                        "disabled_reason": disabled_reason,
                        "board": board,
                        "lot_rule": lot_rule["label"] if lot_rule else None,
                        "buy_price": _round_metric(buy_price) if buy_price is not None else None,
                        "sell_price": _round_metric(sell_price) if sell_price is not None else None,
                        "planned_quantity": planned_quantity,
                        "planned_buy_amount": planned_buy_amount,
                    }
                )
                if tradable and sell_rank is not None:
                    active_sell_rank = sell_rank

        matched_events.sort(key=lambda item: (item["signal_date"], item["target_code"], item["event_id"]))
        return normalized_payload, matched_events

    def _get_or_create_market_scan_result(self, payload: dict, owner_user_id: int) -> dict:
        normalized_payload = self._normalize_scan_payload(payload)
        serialized_payload = self._serialize_scan_payload_for_cache(normalized_payload)
        scan_result_id = self._build_scan_result_id(owner_user_id, serialized_payload)
        cache_key = self._scan_result_cache_key(scan_result_id)
        cached = redis_client.get(cache_key)
        if cached:
            try:
                payload_data = json.loads(cached)
            except json.JSONDecodeError:
                payload_data = None
            if isinstance(payload_data, dict) and int(payload_data.get("owner_user_id") or 0) == owner_user_id:
                redis_client.expire(cache_key, SCAN_RESULT_CACHE_TTL_SECONDS)
                return payload_data

        normalized_payload, matched_events = self._build_market_scan_events(payload)
        return self._store_scan_result(
            scan_result_id=scan_result_id,
            owner_user_id=owner_user_id,
            normalized_payload=normalized_payload,
            matched_events=matched_events,
        )

    def _load_market_scan_candles_for_events(self, strategy_type: str, matched_events: list[dict]) -> dict[str, list[dict]]:
        relevant_events = [
            event for event in matched_events if event.get("tradable") and event.get("buy_date") and event.get("sell_date")
        ]
        if not relevant_events:
            return {}

        target_codes = sorted({str(event["target_code"]) for event in relevant_events})
        start_date = min(date.fromisoformat(str(event["buy_date"])) for event in relevant_events)
        end_date = max(date.fromisoformat(str(event["sell_date"])) for event in relevant_events)

        if strategy_type == "stock":
            scan_universe = self.stock_service.list_stock_scan_universe(
                start_date=start_date,
                end_date=end_date,
                target_codes=target_codes,
            )
        else:
            scan_universe = self.stock_service.list_etf_scan_universe(
                start_date=start_date,
                end_date=end_date,
                target_codes=target_codes,
            )

        return {
            target_code: _sort_candles(payload.get("candles") or [])
            for target_code, payload in scan_universe.items()
            if payload.get("candles")
        }

    def _simulate_market_scan_backtest(
        self,
        *,
        normalized_payload: dict,
        matched_events: list[dict],
        use_all_events: bool,
        excluded_event_ids: list[str] | None,
        selected_event_ids: list[str] | None,
        candles_by_target: dict[str, list[dict]],
    ) -> dict:
        excluded_id_set = {str(item).strip() for item in (excluded_event_ids or []) if str(item).strip()}
        explicit_selected_id_set = (
            {str(item).strip() for item in (selected_event_ids or []) if str(item).strip()}
            if not use_all_events
            else None
        )
        candidate_execution_events: list[dict] = []
        execution_events: list[dict] = []
        events_by_target: dict[str, list[dict]] = defaultdict(list)
        output_events: list[dict] = []
        trade_config = normalized_payload["scan_trade_config"]
        initial_capital = float(trade_config["initial_capital"])

        for event in matched_events:
            event_copy = dict(event)
            default_selected = bool(event_copy.get("tradable")) and event_copy["event_id"] not in excluded_id_set
            is_selected = default_selected if use_all_events else event_copy["event_id"] in (explicit_selected_id_set or set())
            event_copy["selected"] = is_selected
            event_copy["executed"] = False
            event_copy["skip_reason"] = None
            event_copy["actual_quantity"] = None
            event_copy["actual_buy_amount"] = None
            event_copy["actual_sell_amount"] = None
            event_copy["pnl_amount"] = None
            event_copy["return_pct"] = None
            output_events.append(event_copy)
            if is_selected and event_copy.get("tradable"):
                candidate_execution_events.append(event_copy)

        candidate_execution_events.sort(
            key=lambda item: (
                item["buy_date"],
                self._scan_execution_order(normalized_payload["scan_trade_config"]["buy_price_basis"]),
                item["target_code"],
                item["event_id"],
            )
        )
        active_sell_rank_by_target: dict[str, tuple[str, int]] = {}
        for event in candidate_execution_events:
            target_code = str(event.get("target_code") or "")
            buy_date = str(event.get("buy_date") or "")
            sell_date = str(event.get("sell_date") or "")
            if not target_code or not buy_date or not sell_date:
                event["skip_reason"] = "invalid_trade_plan"
                continue
            buy_rank = (buy_date, self._scan_execution_order(normalized_payload["scan_trade_config"]["buy_price_basis"]))
            signal_rank = (str(event.get("signal_date") or buy_date), 1)
            sell_basis = (
                "close"
                if str(event.get("sell_reason") or "") == "fallback_end"
                else str(normalized_payload["scan_trade_config"]["sell_price_basis"])
            )
            sell_rank = (sell_date, self._scan_execution_order(sell_basis))
            if self._scan_event_is_during_open_position(
                signal_rank=signal_rank,
                buy_rank=buy_rank,
                active_sell_rank=active_sell_rank_by_target.get(target_code),
            ):
                event["skip_reason"] = "duplicate_open_position"
                continue
            execution_events.append(event)
            events_by_target[target_code].append(event)
            active_sell_rank_by_target[target_code] = sell_rank

        cash = initial_capital
        open_positions: list[dict] = []
        event_by_id = {event["event_id"]: event for event in output_events}
        all_dates: set[str] = set()

        for target_code, target_events in events_by_target.items():
            candle_map = {candle["trade_date"]: candle for candle in candles_by_target.get(target_code, [])}
            if not candle_map:
                continue
            min_date = min(event["buy_date"] for event in target_events if event.get("buy_date"))
            max_date = max(event["sell_date"] for event in target_events if event.get("sell_date"))
            for candle in candles_by_target.get(target_code, []):
                trade_date = candle["trade_date"]
                if min_date <= trade_date <= max_date:
                    all_dates.add(trade_date)

        sorted_dates = sorted(all_dates)
        date_to_buys: dict[str, list[dict]] = defaultdict(list)
        date_to_sells: dict[str, list[dict]] = defaultdict(list)
        for event in execution_events:
            date_to_buys[str(event["buy_date"])].append(event)
            date_to_sells[str(event["sell_date"])].append(event)

        for items in date_to_buys.values():
            items.sort(key=lambda item: (item["target_code"], item["event_id"]))
        for items in date_to_sells.values():
            items.sort(key=lambda item: (item["target_code"], item["event_id"]))

        candle_maps = {
            target_code: {candle["trade_date"]: candle for candle in rows}
            for target_code, rows in candles_by_target.items()
        }

        points: list[dict] = []
        peak_nav = 0.0
        max_drawdown_pct = 0.0

        for trade_date in sorted_dates:
            for position in list(open_positions):
                if position["sell_date"] != trade_date:
                    continue
                cash += position["quantity"] * position["sell_price"]
                event_item = event_by_id[position["event_id"]]
                event_item["executed"] = True
                event_item["actual_sell_amount"] = _round_metric(position["quantity"] * position["sell_price"])
                event_item["pnl_amount"] = _round_metric(event_item["actual_sell_amount"] - position["actual_buy_amount"])
                event_item["return_pct"] = _round_metric(
                    ((event_item["actual_sell_amount"] / position["actual_buy_amount"]) - 1) * 100
                    if position["actual_buy_amount"] > 0
                    else 0.0
                )
                open_positions.remove(position)

            for event in date_to_buys.get(trade_date, []):
                planned_buy_amount = float(event.get("planned_buy_amount") or 0)
                planned_quantity = int(event.get("planned_quantity") or 0)
                if planned_buy_amount <= 0 or planned_quantity <= 0:
                    event["skip_reason"] = "invalid_trade_plan"
                    continue
                if planned_buy_amount > cash + OPTIMIZATION_TOLERANCE:
                    event["skip_reason"] = "insufficient_cash"
                    continue
                cash -= planned_buy_amount
                event["actual_quantity"] = planned_quantity
                event["actual_buy_amount"] = _round_metric(planned_buy_amount)
                open_positions.append(
                    {
                        "event_id": event["event_id"],
                        "target_code": event["target_code"],
                        "quantity": planned_quantity,
                        "sell_date": event["sell_date"],
                        "sell_price": float(event["sell_price"]),
                        "actual_buy_amount": float(event["actual_buy_amount"]),
                    }
                )

            position_value = 0.0
            for position in open_positions:
                candle = candle_maps.get(position["target_code"], {}).get(trade_date)
                if candle is None:
                    continue
                position_value += position["quantity"] * float(candle["close"])
            nav = cash + position_value
            position_pct = max(min((position_value / nav) if nav > 0 else 0.0, 1.0), 0.0)
            points.append(
                {
                    "trade_date": trade_date,
                    "nav": nav / initial_capital if initial_capital > 0 else 0.0,
                    "benchmark_nav": None,
                    "signal": None,
                    "close_price": None,
                    "position_value": _round_metric(position_value),
                    "position_pct": position_pct,
                    "position_bucket": _position_bucket(position_pct),
                }
            )
            peak_nav = max(peak_nav, nav)
            if peak_nav > 0:
                max_drawdown_pct = max(max_drawdown_pct, (peak_nav - nav) / peak_nav * 100)

        normalized_last_nav = points[-1]["nav"] if points else 1.0
        cumulative_return_pct = (normalized_last_nav - 1) * 100 if points else 0.0
        if len(points) >= 2:
            start_dt = date.fromisoformat(points[0]["trade_date"])
            end_dt = date.fromisoformat(points[-1]["trade_date"])
            days_span = max((end_dt - start_dt).days, 0)
            if days_span > 0 and normalized_last_nav > 0:
                annualized_return_pct = ((normalized_last_nav ** (365 / days_span)) - 1) * 100
            else:
                annualized_return_pct = cumulative_return_pct
        else:
            annualized_return_pct = cumulative_return_pct if points else 0.0

        executed_event_count = sum(1 for event in output_events if event.get("executed"))
        skipped_event_count = sum(
            1
            for event in output_events
            if event.get("selected") and event.get("tradable") and not event.get("executed")
        )

        return {
            "matched_events": output_events,
            "cumulative_return_pct": cumulative_return_pct,
            "annualized_return_pct": annualized_return_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "points": points,
            "summary": {
                "matched_event_count": len(matched_events),
                "tradable_event_count": sum(1 for event in matched_events if event.get("tradable")),
                "selected_event_count": sum(1 for event in output_events if event.get("selected")),
                "executed_event_count": executed_event_count,
                "skipped_event_count": skipped_event_count,
            },
        }

    def preview_market_scan(self, payload: dict, owner_user_id: int, page: int = 1, page_size: int = SCAN_EVENT_PAGE_SIZE) -> dict:
        scan_result = self._get_or_create_market_scan_result(payload, owner_user_id)
        page_payload = self._paginate_scan_events(scan_result["matched_events"], page=page, page_size=page_size)
        return {
            "scan_result_id": scan_result["scan_result_id"],
            "strategy_type": scan_result["normalized_payload"]["strategy_type"],
            "matched_events": page_payload["matched_events"],
            "matched_event_count": scan_result["matched_event_count"],
            "tradable_event_count": scan_result["tradable_event_count"],
            "total_event_count": page_payload["total_event_count"],
            "page": page_payload["page"],
            "page_size": page_payload["page_size"],
        }

    def get_market_scan_events(
        self,
        scan_result_id: str,
        owner_user_id: int,
        page: int = 1,
        page_size: int = SCAN_EVENT_PAGE_SIZE,
    ) -> dict:
        scan_result = self._load_scan_result(scan_result_id, owner_user_id)
        page_payload = self._paginate_scan_events(scan_result["matched_events"], page=page, page_size=page_size)
        return {
            "scan_result_id": scan_result["scan_result_id"],
            "strategy_type": scan_result["normalized_payload"]["strategy_type"],
            "matched_events": page_payload["matched_events"],
            "matched_event_count": scan_result["matched_event_count"],
            "tradable_event_count": scan_result["tradable_event_count"],
            "total_event_count": page_payload["total_event_count"],
            "page": page_payload["page"],
            "page_size": page_payload["page_size"],
        }

    def get_market_scan_target_hits(self, scan_result_id: str, target_code: str, owner_user_id: int) -> dict:
        scan_result = self._load_scan_result(scan_result_id, owner_user_id)
        normalized_target_code = str(target_code or "").strip()
        target_events = [event for event in scan_result["matched_events"] if str(event.get("target_code")) == normalized_target_code]
        if not target_events:
            raise ValueError("scan target not found")
        hit_dates = sorted({str(event["signal_date"]) for event in target_events if event.get("signal_date")})
        sell_trigger_dates = sorted(
            {str(event["sell_trigger_date"]) for event in target_events if event.get("sell_trigger_date")}
        )
        return {
            "scan_result_id": scan_result["scan_result_id"],
            "target_code": normalized_target_code,
            "target_name": str(target_events[0].get("target_name") or normalized_target_code),
            "hit_dates": hit_dates,
            "sell_trigger_dates": sell_trigger_dates,
        }

    def backtest_market_scan(self, payload: dict, owner_user_id: int) -> dict:
        scan_result_id = str(payload.get("scan_result_id", "")).strip()
        if not scan_result_id:
            raise ValueError("scan_result_id is required")
        scan_result = self._load_scan_result(scan_result_id, owner_user_id)
        use_all_events = bool(payload.get("use_all_events", True))
        excluded_event_ids = [str(item).strip() for item in payload.get("excluded_event_ids", []) if str(item).strip()]
        explicit_selected_event_ids = [
            str(item).strip() for item in (payload.get("selected_event_ids") or []) if str(item).strip()
        ]
        normalized_payload = {
            "strategy_type": scan_result["normalized_payload"]["strategy_type"],
            "indicator_params": scan_result["normalized_payload"].get("indicator_params") or {},
            "buy_sequence_groups": scan_result["normalized_payload"]["buy_sequence_groups"],
            "scan_trade_config": self._normalize_scan_trade_config(
                payload.get("scan_trade_config") or scan_result["normalized_payload"].get("scan_trade_config") or {}
            ),
            "scan_start_date": date.fromisoformat(scan_result["normalized_payload"]["scan_start_date"]),
            "scan_end_date": date.fromisoformat(scan_result["normalized_payload"]["scan_end_date"]),
        }
        matched_events = list(scan_result["matched_events"])
        excluded_id_set = set(excluded_event_ids)
        explicit_selected_id_set = set(explicit_selected_event_ids)
        selected_events = [
            event
            for event in matched_events
            if event.get("tradable")
            and (
                (
                    use_all_events
                    and str(event["event_id"]) not in excluded_id_set
                )
                or (
                    not use_all_events
                    and str(event["event_id"]) in explicit_selected_id_set
                )
            )
        ]
        candles_by_target = self._load_market_scan_candles_for_events(
            normalized_payload["strategy_type"],
            selected_events,
        )
        result = self._simulate_market_scan_backtest(
            normalized_payload=normalized_payload,
            matched_events=matched_events,
            use_all_events=use_all_events,
            excluded_event_ids=excluded_event_ids,
            selected_event_ids=explicit_selected_event_ids,
            candles_by_target=candles_by_target,
        )
        page_payload = self._paginate_scan_events(
            result["matched_events"],
            page=payload.get("page"),
            page_size=payload.get("page_size"),
        )
        return {
            "scan_result_id": scan_result_id,
            "strategy_type": normalized_payload["strategy_type"],
            "matched_events": page_payload["matched_events"],
            "total_event_count": page_payload["total_event_count"],
            "page": page_payload["page"],
            "page_size": page_payload["page_size"],
            "cumulative_return_pct": result["cumulative_return_pct"],
            "annualized_return_pct": result["annualized_return_pct"],
            "max_drawdown_pct": result["max_drawdown_pct"],
            "points": result["points"],
            "summary": result["summary"],
        }

    def _normalize_rule_groups(self, raw_groups: object, allowed_keys: list[str]) -> list[dict]:
        if not isinstance(raw_groups, list):
            return []

        allowed_key_set = set(allowed_keys)
        allowed_tracks = {"boll-upper", "boll-middle", "boll-lower"}
        normalized_groups: list[dict] = []

        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                continue
            raw_conditions = raw_group.get("conditions")
            if not isinstance(raw_conditions, list):
                continue

            conditions: list[dict] = []
            for raw_condition in raw_conditions:
                if not isinstance(raw_condition, dict):
                    continue
                condition_type = str(raw_condition.get("type", "")).strip()
                operator = str(raw_condition.get("operator", "")).strip()
                if operator not in {"gt", "lt"}:
                    continue

                if condition_type == "numeric":
                    field = str(raw_condition.get("field", "")).strip()
                    value = _normalize_threshold(raw_condition.get("value"))
                    if field not in allowed_key_set or value is None:
                        continue
                    conditions.append(
                        {
                            "type": "numeric",
                            "field": field,
                            "operator": operator,
                            "value": value,
                        }
                    )
                    continue

                if condition_type == "boll":
                    mode = str(raw_condition.get("mode", "")).strip()
                    track = str(raw_condition.get("track", "")).strip()
                    if mode not in {"close", "intraday"} or track not in allowed_tracks:
                        continue
                    conditions.append(
                        {
                            "type": "boll",
                            "mode": mode,
                            "operator": operator,
                            "track": track,
                        }
                    )

            if conditions:
                normalized_groups.append({"conditions": conditions})

        return normalized_groups

    def _legacy_filters_to_rule_groups(self, filters: object, boll_filter: object, allowed_keys: list[str]) -> list[dict]:
        if not isinstance(filters, dict):
            filters = {}
        if not isinstance(boll_filter, dict):
            boll_filter = {}

        allowed_key_set = set(allowed_keys)
        allowed_tracks = {"boll-upper", "boll-middle", "boll-lower"}
        conditions: list[dict] = []

        for key, threshold in filters.items():
            if key not in allowed_key_set or not isinstance(threshold, dict):
                continue
            gt_value = _normalize_threshold(threshold.get("gt"))
            lt_value = _normalize_threshold(threshold.get("lt"))
            if gt_value is not None:
                conditions.append({"type": "numeric", "field": key, "operator": "gt", "value": gt_value})
            if lt_value is not None:
                conditions.append({"type": "numeric", "field": key, "operator": "lt", "value": lt_value})

        for operator, key_name in (("gt", "gt"), ("lt", "lt")):
            track = boll_filter.get(key_name)
            if track in allowed_tracks:
                conditions.append({"type": "boll", "mode": "close", "operator": operator, "track": track})

        for operator, key_name in (("gt", "intraday_gt"), ("lt", "intraday_lt")):
            track = boll_filter.get(key_name)
            if track in allowed_tracks:
                conditions.append({"type": "boll", "mode": "intraday", "operator": operator, "track": track})

        return [{"conditions": conditions}] if conditions else []

    def _get_rule_groups(self, strategy: QuantStrategyConfig, color: str, allowed_keys: list[str]) -> list[dict]:
        raw_groups = getattr(strategy, f"{color}_filter_groups", None)
        if isinstance(raw_groups, list) and raw_groups:
            return self._normalize_rule_groups(raw_groups, allowed_keys)
        filters = getattr(strategy, f"{color}_filters", None)
        boll_filter = getattr(strategy, f"{color}_boll_filter", None)
        return self._legacy_filters_to_rule_groups(filters, boll_filter, allowed_keys)

    def _payload_contains_vix_rules(self, payload: dict) -> bool:
        for color in ("blue", "red"):
            raw_groups = payload.get(f"{color}_filter_groups")
            if isinstance(raw_groups, list):
                for raw_group in raw_groups:
                    if not isinstance(raw_group, dict):
                        continue
                    raw_conditions = raw_group.get("conditions")
                    if not isinstance(raw_conditions, list):
                        continue
                    for raw_condition in raw_conditions:
                        if not isinstance(raw_condition, dict):
                            continue
                        if str(raw_condition.get("type", "")).strip() != "numeric":
                            continue
                        if str(raw_condition.get("field", "")).strip() in VIX_FILTER_KEYS:
                            return True
            raw_filters = payload.get(f"{color}_filters")
            if isinstance(raw_filters, dict):
                for key in raw_filters.keys():
                    if str(key).strip() in VIX_FILTER_KEYS:
                        return True
        return False

    def _validate_strategy_payload(self, payload: dict) -> None:
        strategy_engine = self._normalize_strategy_engine(payload.get("strategy_engine", "snapshot"))
        strategy_type = str(payload.get("strategy_type", "")).strip()
        target_market = self._normalize_target_market(payload.get("target_market", "cn"))
        target_code = str(payload.get("target_code", "")).strip()
        target_name = str(payload.get("target_name", "")).strip()

        if strategy_engine != "snapshot" or strategy_type != "index":
            return
        if not self._payload_contains_vix_rules(payload):
            return
        if not self._index_supports_vix(target_code, target_name, target_market):
            raise ValueError("当前指数不支持 VIX 条件，请先移除 VIX 规则。")

    def _matches_rule_condition(self, snapshot: dict, condition: dict, allowed_keys: list[str]) -> bool:
        condition_type = str(condition.get("type", "")).strip()
        operator = str(condition.get("operator", "")).strip()

        if condition_type == "numeric":
            field = str(condition.get("field", "")).strip()
            if field not in allowed_keys:
                return False
            value = snapshot["values"].get(field)
            threshold = _normalize_threshold(condition.get("value"))
            if value is None or threshold is None:
                return False
            return value > threshold if operator == "gt" else value < threshold

        if condition_type == "boll":
            track = str(condition.get("track", "")).strip()
            mode = str(condition.get("mode", "")).strip()
            reference_value = snapshot["values"].get(track)
            if reference_value is None:
                return False
            if mode == "close":
                close_value = snapshot.get("close")
                if close_value is None:
                    return False
                return close_value > reference_value if operator == "gt" else close_value < reference_value
            if mode == "intraday":
                if operator == "gt":
                    high_value = snapshot.get("high")
                    return high_value is not None and high_value > reference_value
                low_value = snapshot.get("low")
                return low_value is not None and low_value < reference_value

        return False

    def _matches_rule_group(self, snapshot: dict, group: dict, allowed_keys: list[str]) -> bool:
        conditions = group.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            return False
        return all(self._matches_rule_condition(snapshot, condition, allowed_keys) for condition in conditions)

    def _matches_rule_groups(self, snapshot: dict, groups: list[dict], allowed_keys: list[str]) -> bool:
        if not groups:
            return False
        return any(self._matches_rule_group(snapshot, group, allowed_keys) for group in groups)

    def _payload_contains_numeric_rules(self, payload: dict, target_fields: list[str]) -> bool:
        field_set = {str(item).strip() for item in target_fields}
        if not field_set:
            return False
        for color in ("blue", "red"):
            raw_groups = payload.get(f"{color}_filter_groups")
            if isinstance(raw_groups, list):
                for raw_group in raw_groups:
                    if not isinstance(raw_group, dict):
                        continue
                    raw_conditions = raw_group.get("conditions")
                    if not isinstance(raw_conditions, list):
                        continue
                    for raw_condition in raw_conditions:
                        if not isinstance(raw_condition, dict):
                            continue
                        if str(raw_condition.get("type", "")).strip() != "numeric":
                            continue
                        if str(raw_condition.get("field", "")).strip() in field_set:
                            return True
            raw_filters = payload.get(f"{color}_filters")
            if isinstance(raw_filters, dict):
                for key in raw_filters.keys():
                    if str(key).strip() in field_set:
                        return True
        return False

    def _payload_contains_sequence_series(self, payload: dict, target_series: set[str]) -> bool:
        if not target_series:
            return False
        for side in ("buy", "sell"):
            raw_groups = payload.get(f"{side}_sequence_groups")
            if not isinstance(raw_groups, list):
                continue
            for raw_group in raw_groups:
                if not isinstance(raw_group, dict):
                    continue
                raw_conditions = raw_group.get("conditions")
                if not isinstance(raw_conditions, list):
                    continue
                for raw_condition in raw_conditions:
                    if (
                        isinstance(raw_condition, dict)
                        and str(raw_condition.get("series_key", "")).strip() in target_series
                    ):
                        return True
        return False

    def _validate_strategy_payload(self, payload: dict) -> None:
        strategy_engine = self._normalize_strategy_engine(payload.get("strategy_engine", "snapshot"))
        strategy_type = str(payload.get("strategy_type", "")).strip()
        target_market = self._normalize_target_market(payload.get("target_market", "cn"))
        target_code = str(payload.get("target_code", "")).strip()
        target_name = str(payload.get("target_name", "")).strip()

        if (
            strategy_engine == "sequence"
            and strategy_type == "index"
            and self._payload_contains_sequence_series(payload, SEQUENCE_STRATEGY_MA_BIAS_SERIES_KEYS)
        ):
            raise ValueError("指数条件策略不支持 MA 乖离条件，请先移除相关规则。")

        if strategy_engine != "snapshot" or strategy_type != "index":
            return
        if self._payload_contains_numeric_rules(payload, VIX_FILTER_KEYS) and not self._index_supports_vix(
            target_code, target_name, target_market
        ):
            raise ValueError("当前指数不支持 VIX 条件，请先移除相关规则。")
        if self._payload_contains_numeric_rules(payload, BASIS_FILTER_KEYS) and not self._index_supports_basis(
            target_code, target_name, target_market
        ):
            raise ValueError("当前指数不支持期现差条件，请先移除相关规则。")
        if self._payload_contains_numeric_rules(
            payload, CN_OPTION_SUPPORTED_FILTER_KEYS
        ) and not self._index_supports_cn_option_put_call(target_code, target_name, target_market):
            raise ValueError("当前指数不支持 A股 Put/Call 条件，请先移除相关规则。")
        if self._payload_contains_numeric_rules(payload, CFFEX_NET_SHORT_DELTA_FILTER_KEYS) and target_market != "cn":
            raise ValueError("当前市场不支持股指期货净空单增量条件，请先移除相关规则。")
        if self._payload_contains_numeric_rules(payload, BASIS_DELTA_FILTER_KEYS) and target_market != "cn":
            raise ValueError("当前市场不支持期现差变化条件，请先移除相关规则。")
        if target_market == "us" and self._payload_contains_numeric_rules(payload, ["basis-month"]):
            raise ValueError("当前美股指数只支持连续期现差条件，请先移除月连期现差规则。")
        if self._payload_contains_numeric_rules(payload, US_BASIS_ADJUSTED_FILTER_KEYS) and not self._index_supports_adjusted_basis(
            target_code, target_name, target_market
        ):
            raise ValueError("当前指数不支持换月调整期现差条件，请先移除相关规则。")
        if self._payload_contains_numeric_rules(payload, US_MARKET_AUXILIARY_FILTER_KEYS) and target_market != "us":
            raise ValueError("当前市场不支持美股辅助指标条件，请先移除相关规则。")
        if self._payload_contains_numeric_rules(payload, US_HEDGE_FILTER_KEYS) and not self._resolve_us_hedge_proxy_scope(
            target_code, target_name, target_market
        ):
            raise ValueError("当前指数不支持对冲基金代理条件，请先移除相关规则。")

    def _build_signal_map(self, strategy: QuantStrategyConfig, snapshots: list[dict]) -> dict[str, str]:
        if self._normalize_strategy_engine(strategy.strategy_engine) == "sequence":
            return self._build_sequence_signal_map(strategy, snapshots)

        allowed_keys = self._allowed_snapshot_filter_keys(
            strategy.strategy_type,
            self._normalize_target_market(getattr(strategy, "target_market", "cn")),
            getattr(strategy, "target_code", ""),
            getattr(strategy, "target_name", ""),
        )
        blue_groups = self._get_rule_groups(strategy, "blue", allowed_keys)
        red_groups = self._get_rule_groups(strategy, "red", allowed_keys)

        signal_map: dict[str, str] = {}
        for snapshot in snapshots:
            is_blue = self._matches_rule_groups(snapshot, blue_groups, allowed_keys)
            is_red = self._matches_rule_groups(snapshot, red_groups, allowed_keys)

            if is_blue and is_red:
                signal_map[snapshot["trade_date"]] = "purple"
            elif is_blue:
                signal_map[snapshot["trade_date"]] = "blue"
            elif is_red:
                signal_map[snapshot["trade_date"]] = "red"
        return signal_map

    def _serialize_strategy(self, item: QuantStrategyConfig) -> dict:
        allowed_keys = self._allowed_snapshot_filter_keys(
            item.strategy_type,
            self._normalize_target_market(getattr(item, "target_market", "cn")),
            getattr(item, "target_code", ""),
            getattr(item, "target_name", ""),
        )
        return {
            "id": item.id,
            "name": item.name,
            "notes": item.notes or "",
            "strategy_engine": self._normalize_strategy_engine(item.strategy_engine),
            "sequence_mode": self._normalize_sequence_mode(item.sequence_mode),
            "strategy_type": item.strategy_type,
            "target_market": self._normalize_target_market(getattr(item, "target_market", "cn")),
            "target_code": item.target_code,
            "target_name": item.target_name,
            "indicator_params": item.indicator_params or {},
            "buy_sequence_groups": self._get_sequence_groups(item, "buy"),
            "sell_sequence_groups": self._get_sequence_groups(item, "sell"),
            "scan_trade_config": self._normalize_scan_trade_config(item.scan_trade_config or {}),
            "blue_filter_groups": self._get_rule_groups(item, "blue", allowed_keys),
            "red_filter_groups": self._get_rule_groups(item, "red", allowed_keys),
            "blue_filters": item.blue_filters or {},
            "red_filters": item.red_filters or {},
            "blue_boll_filter": item.blue_boll_filter or {},
            "red_boll_filter": item.red_boll_filter or {},
            "signal_buy_color": item.signal_buy_color,
            "signal_sell_color": item.signal_sell_color,
            "purple_conflict_mode": item.purple_conflict_mode,
            "start_date": item.start_date,
            "scan_start_date": item.scan_start_date,
            "scan_end_date": item.scan_end_date,
            "buy_position_pct": float(item.buy_position_pct),
            "sell_position_pct": float(item.sell_position_pct),
            "execution_price_mode": item.execution_price_mode,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def _get_owned_strategy(self, strategy_id: int, owner_user_id: int) -> QuantStrategyConfig:
        item = (
            self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.id == strategy_id,
                QuantStrategyConfig.owner_user_id == owner_user_id,
            )
            .first()
        )
        if item is None:
            raise ValueError("strategy not found")
        return item

    def list_strategies(self, owner_user_id: int) -> list[dict]:
        items = (
            self.db.query(QuantStrategyConfig)
            .filter(QuantStrategyConfig.owner_user_id == owner_user_id)
            .order_by(QuantStrategyConfig.updated_at.desc())
            .all()
        )
        return [self._serialize_strategy(item) for item in items]

    def get_strategy(self, strategy_id: int, owner_user_id: int) -> dict:
        item = self._get_owned_strategy(strategy_id, owner_user_id)
        return self._serialize_strategy(item)

    def create_strategy(self, payload: dict, owner_user_id: int) -> dict:
        self._validate_strategy_payload(payload)
        item = QuantStrategyConfig(
            owner_user_id=owner_user_id,
            name=str(payload.get("name", "")).strip(),
            notes=str(payload.get("notes", "")).strip(),
            strategy_engine=self._normalize_strategy_engine(payload.get("strategy_engine", "snapshot")),
            sequence_mode=self._normalize_sequence_mode(payload.get("sequence_mode", "single_target")),
            strategy_type=str(payload.get("strategy_type", "")).strip(),
            target_market=self._normalize_target_market(payload.get("target_market", "cn")),
            target_code=str(payload.get("target_code", "")).strip(),
            target_name=str(payload.get("target_name", "")).strip(),
            indicator_params=payload.get("indicator_params") or {},
            buy_sequence_groups=payload.get("buy_sequence_groups") or [],
            sell_sequence_groups=payload.get("sell_sequence_groups") or [],
            scan_trade_config=self._normalize_scan_trade_config(payload.get("scan_trade_config") or {}),
            blue_filter_groups=payload.get("blue_filter_groups") or [],
            red_filter_groups=payload.get("red_filter_groups") or [],
            blue_filters=payload.get("blue_filters") or {},
            red_filters=payload.get("red_filters") or {},
            blue_boll_filter=payload.get("blue_boll_filter") or {},
            red_boll_filter=payload.get("red_boll_filter") or {},
            signal_buy_color=str(payload.get("signal_buy_color", "blue")).strip(),
            signal_sell_color=str(payload.get("signal_sell_color", "red")).strip(),
            purple_conflict_mode=str(payload.get("purple_conflict_mode", "sell_first")).strip(),
            start_date=payload.get("start_date"),
            scan_start_date=payload.get("scan_start_date"),
            scan_end_date=payload.get("scan_end_date"),
            buy_position_pct=_normalize_ratio(payload.get("buy_position_pct", 1)),
            sell_position_pct=_normalize_ratio(payload.get("sell_position_pct", 1)),
            execution_price_mode=str(payload.get("execution_price_mode", "next_open")).strip(),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._serialize_strategy(item)

    def update_strategy(self, strategy_id: int, payload: dict, owner_user_id: int) -> dict:
        item = self._get_owned_strategy(strategy_id, owner_user_id)
        self._validate_strategy_payload(payload)

        item.name = str(payload.get("name", item.name)).strip()
        item.notes = str(payload.get("notes", item.notes or "")).strip()
        item.strategy_engine = self._normalize_strategy_engine(payload.get("strategy_engine", item.strategy_engine))
        item.sequence_mode = self._normalize_sequence_mode(payload.get("sequence_mode", item.sequence_mode))
        item.strategy_type = str(payload.get("strategy_type", item.strategy_type)).strip()
        item.target_market = self._normalize_target_market(payload.get("target_market", item.target_market))
        item.target_code = str(payload.get("target_code", item.target_code)).strip()
        item.target_name = str(payload.get("target_name", item.target_name)).strip()
        item.indicator_params = payload.get("indicator_params") or item.indicator_params or {}
        item.buy_sequence_groups = payload.get("buy_sequence_groups") or []
        item.sell_sequence_groups = payload.get("sell_sequence_groups") or []
        item.scan_trade_config = self._normalize_scan_trade_config(payload.get("scan_trade_config") or item.scan_trade_config or {})
        item.blue_filter_groups = payload.get("blue_filter_groups") or []
        item.red_filter_groups = payload.get("red_filter_groups") or []
        item.blue_filters = payload.get("blue_filters") or {}
        item.red_filters = payload.get("red_filters") or {}
        item.blue_boll_filter = payload.get("blue_boll_filter") or {}
        item.red_boll_filter = payload.get("red_boll_filter") or {}
        item.signal_buy_color = str(payload.get("signal_buy_color", item.signal_buy_color)).strip()
        item.signal_sell_color = str(payload.get("signal_sell_color", item.signal_sell_color)).strip()
        item.purple_conflict_mode = str(payload.get("purple_conflict_mode", item.purple_conflict_mode)).strip()
        item.start_date = payload.get("start_date", item.start_date)
        item.scan_start_date = payload.get("scan_start_date", item.scan_start_date)
        item.scan_end_date = payload.get("scan_end_date", item.scan_end_date)
        item.buy_position_pct = _normalize_ratio(payload.get("buy_position_pct", item.buy_position_pct))
        item.sell_position_pct = _normalize_ratio(payload.get("sell_position_pct", item.sell_position_pct))
        item.execution_price_mode = str(payload.get("execution_price_mode", item.execution_price_mode)).strip()
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._serialize_strategy(item)

    def delete_strategy(self, strategy_id: int, owner_user_id: int) -> None:
        item = self._get_owned_strategy(strategy_id, owner_user_id)
        self.db.delete(item)
        self.db.commit()

    def send_strategy(self, strategy_id: int, owner_user_id: int, target_username: str) -> dict:
        source = self._get_owned_strategy(strategy_id, owner_user_id)
        normalized_target = target_username.strip()
        if not normalized_target:
            raise ValueError("target user is required")

        target_user = (
            self.db.query(User)
            .filter(
                User.role == "user",
                (User.username == normalized_target) | (User.phone == normalized_target),
            )
            .first()
        )
        if target_user is None:
            raise ValueError("target user not found")
        if target_user.id == owner_user_id:
            raise ValueError("cannot send strategy to yourself")

        copied = QuantStrategyConfig(
            owner_user_id=target_user.id,
            name=source.name,
            notes=source.notes or "",
            strategy_engine=self._normalize_strategy_engine(source.strategy_engine),
            sequence_mode=self._normalize_sequence_mode(source.sequence_mode),
            strategy_type=source.strategy_type,
            target_market=self._normalize_target_market(getattr(source, "target_market", "cn")),
            target_code=source.target_code,
            target_name=source.target_name,
            indicator_params=source.indicator_params or {},
            buy_sequence_groups=source.buy_sequence_groups or [],
            sell_sequence_groups=source.sell_sequence_groups or [],
            scan_trade_config=self._normalize_scan_trade_config(source.scan_trade_config or {}),
            blue_filter_groups=source.blue_filter_groups or [],
            red_filter_groups=source.red_filter_groups or [],
            blue_filters=source.blue_filters or {},
            red_filters=source.red_filters or {},
            blue_boll_filter=source.blue_boll_filter or {},
            red_boll_filter=source.red_boll_filter or {},
            signal_buy_color=source.signal_buy_color,
            signal_sell_color=source.signal_sell_color,
            purple_conflict_mode=source.purple_conflict_mode,
            start_date=source.start_date,
            scan_start_date=source.scan_start_date,
            scan_end_date=source.scan_end_date,
            buy_position_pct=source.buy_position_pct,
            sell_position_pct=source.sell_position_pct,
            execution_price_mode=source.execution_price_mode,
        )
        self.db.add(copied)
        self.db.commit()
        self.db.refresh(copied)
        sender_user = self.db.get(User, owner_user_id)
        if sender_user is not None:
            self.notification_service.create_strategy_received_notification(
                recipient_user_id=target_user.id,
                sender_user=sender_user,
                strategy=copied,
            )
        return self._serialize_strategy(copied)

    def list_strategy_notification_summaries(
        self,
        strategy_ids: list[int],
        owner_user_id: int,
        basis_trade_date: date | None = None,
    ) -> list[dict]:
        return self._list_strategy_notification_summaries_fixed(strategy_ids, owner_user_id, basis_trade_date)
        """
        if not strategy_ids:
            return []

        owned_items = (
            self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == owner_user_id,
                QuantStrategyConfig.id.in_(strategy_ids),
            )
            .all()
        )
        strategy_map = {item.id: item for item in owned_items}
        results: list[dict] = []

        for strategy_id in strategy_ids:
            item = strategy_map.get(strategy_id)
            if item is None:
                results.append(
                    {
                        "strategy_id": strategy_id,
                        "strategy_name": f"策略#{strategy_id}",
                        "target_name": "-",
                        "latest_trade_date": "-",
                        "signal": None,
                        "signal_text": "无操作",
                        "note": "策略不存在或不再属于当前用户",
                    }
                )
                continue

            strategy_engine = self._normalize_strategy_engine(item.strategy_engine)
            sequence_mode = self._normalize_sequence_mode(item.sequence_mode)
            if strategy_engine == "sequence" and sequence_mode == "market_scan":
                scan_payload = {
                    "strategy_type": item.strategy_type,
                    "buy_sequence_groups": item.buy_sequence_groups or [],
                    "scan_trade_config": item.scan_trade_config or {},
                    "start_date": item.start_date,
                }
                scan_result = self.preview_market_scan(scan_payload, int(item.owner_user_id or 0))
                basis_date_text = basis_trade_date.isoformat() if basis_trade_date else None
                candidate_events = scan_result["matched_events"]
                if basis_date_text:
                    candidate_events = [
                        event for event in candidate_events if str(event.get("signal_date")) <= basis_date_text
                    ]
                latest_trade_date = "-"
                signal = None
                note = "当日无操作"
                if candidate_events:
                    latest_trade_date = max(str(event["signal_date"]) for event in candidate_events)
                    today_events = [event for event in candidate_events if str(event["signal_date"]) == latest_trade_date]
                    if today_events:
                        signal = "blue"
                        sample_targets = "、".join(
                            sorted({str(event["target_name"]) for event in today_events if event.get("target_name")})[:3]
                        )
                        note = f"当日新命中 {len(today_events)} 条事件{f'：包含 {sample_targets}' if sample_targets else ''}"
                results.append(
                    {
                        "strategy_id": item.id,
                        "strategy_name": item.name,
                        "target_name": item.target_name,
                        "latest_trade_date": latest_trade_date,
                        "signal": signal,
                        "signal_text": "蓝色" if signal else "无操作",
                        "note": note,
                    }
                )
                continue

            if strategy_engine == "sequence":
                snapshots = self._build_sequence_snapshots(item)
            else:
                if item.strategy_type == "index":
                    signal_candles = self.stock_service.list_index_daily_kline(
                        item.target_code,
                        market=self._normalize_target_market(getattr(item, "target_market", "cn")),
                    )
                    snapshots = self._build_index_snapshots_for_market(
                        self._normalize_target_market(getattr(item, "target_market", "cn")),
                        item.target_code,
                        item.target_name,
                        item.indicator_params or {},
                        signal_candles,
                    )
                else:
                    signal_candles = self.stock_service.list_hfq_daily_kline(item.target_code)
                    snapshots = self._build_stock_snapshots(item.indicator_params or {}, signal_candles)

            if not snapshots:
                results.append(
                    {
                        "strategy_id": item.id,
                        "strategy_name": item.name,
                        "target_name": item.target_name,
                        "latest_trade_date": "-",
                        "signal": None,
                        "signal_text": "无操作",
                        "note": "当前策略暂无可用于通知的行情数据",
                    }
                )
                continue

            eligible_snapshots = snapshots
            if basis_trade_date is not None:
                basis_date_text = basis_trade_date.isoformat()
                eligible_snapshots = [
                    snapshot
                    for snapshot in snapshots
                    if _date_text(snapshot.get("trade_date")) <= basis_date_text
                ]
            if not eligible_snapshots:
                results.append(
                    {
                        "strategy_id": item.id,
                        "strategy_name": item.name,
                        "target_name": item.target_name,
                        "latest_trade_date": "-",
                        "signal": None,
                        "signal_text": "无操作",
                        "note": "在当前通知基准交易日前暂无可用行情数据",
                    }
                )
                continue

            latest_snapshot = eligible_snapshots[-1]
            latest_trade_date = _date_text(latest_snapshot.get("trade_date"))
            signal_map = self._build_signal_map(item, snapshots)
            signal = signal_map.get(latest_trade_date)
            signal_text_map = {
                "blue": "蓝",
                "red": "红",
                "purple": "紫",
            }
            results.append(
                {
                    "strategy_id": item.id,
                    "strategy_name": item.name,
                    "target_name": item.target_name,
                    "latest_trade_date": latest_trade_date,
                    "signal": signal,
                    "signal_text": signal_text_map.get(signal, "无操作"),
                    "note": "出现操作信号" if signal else "当日无红蓝信号",
                }
            )

        return results
        """

    def _list_strategy_notification_summaries_fixed(
        self,
        strategy_ids: list[int],
        owner_user_id: int,
        basis_trade_date: date | None = None,
    ) -> list[dict]:
        if not strategy_ids:
            return []

        owned_items = (
            self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == owner_user_id,
                QuantStrategyConfig.id.in_(strategy_ids),
            )
            .all()
        )
        strategy_map = {item.id: item for item in owned_items}
        results: list[dict] = []

        for strategy_id in strategy_ids:
            item = strategy_map.get(strategy_id)
            if item is None:
                results.append(
                    {
                        "strategy_id": strategy_id,
                        "strategy_name": f"策略#{strategy_id}",
                        "target_name": "-",
                        "latest_trade_date": "-",
                        "signal": None,
                        "signal_text": "无操作",
                        "note": "策略不存在或不再属于当前用户",
                    }
                )
                continue

            strategy_engine = self._normalize_strategy_engine(item.strategy_engine)
            sequence_mode = self._normalize_sequence_mode(item.sequence_mode)
            if strategy_engine == "sequence" and sequence_mode == "market_scan":
                scan_payload = {
                    "strategy_type": item.strategy_type,
                    "buy_sequence_groups": item.buy_sequence_groups or [],
                    "scan_trade_config": item.scan_trade_config or {},
                    "start_date": item.start_date,
                }
                scan_result = self.preview_market_scan(scan_payload, int(item.owner_user_id or 0))
                basis_date_text = basis_trade_date.isoformat() if basis_trade_date else None
                candidate_events = scan_result["matched_events"]
                if basis_date_text:
                    candidate_events = [
                        event for event in candidate_events if str(event.get("signal_date")) <= basis_date_text
                    ]
                latest_trade_date = "-"
                signal = None
                note = "当日无操作"
                if candidate_events:
                    latest_trade_date = max(str(event["signal_date"]) for event in candidate_events)
                    today_events = [event for event in candidate_events if str(event["signal_date"]) == latest_trade_date]
                    if today_events:
                        signal = "blue"
                        sample_targets = "、".join(
                            sorted({str(event["target_name"]) for event in today_events if event.get("target_name")})[:3]
                        )
                        note = f"当日新命中 {len(today_events)} 条事件{f'，包含 {sample_targets}' if sample_targets else ''}"
                results.append(
                    {
                        "strategy_id": item.id,
                        "strategy_name": item.name,
                        "target_name": item.target_name,
                        "latest_trade_date": latest_trade_date,
                        "signal": signal,
                        "signal_text": "蓝" if signal else "无操作",
                        "note": note,
                    }
                )
                continue

            if strategy_engine == "sequence":
                snapshots = self._build_sequence_snapshots(item)
            else:
                if item.strategy_type == "index":
                    signal_candles = self.stock_service.list_index_daily_kline(
                        item.target_code,
                        market=self._normalize_target_market(getattr(item, "target_market", "cn")),
                    )
                    snapshots = self._build_index_snapshots_for_market(
                        self._normalize_target_market(getattr(item, "target_market", "cn")),
                        item.target_code,
                        item.target_name,
                        item.indicator_params or {},
                        signal_candles,
                    )
                else:
                    signal_candles = self.stock_service.list_hfq_daily_kline(item.target_code)
                    snapshots = self._build_stock_snapshots(item.indicator_params or {}, signal_candles)

            if not snapshots:
                results.append(
                    {
                        "strategy_id": item.id,
                        "strategy_name": item.name,
                        "target_name": item.target_name,
                        "latest_trade_date": "-",
                        "signal": None,
                        "signal_text": "无操作",
                        "note": "当前策略暂无可用于通知的行情数据",
                    }
                )
                continue

            eligible_snapshots = snapshots
            if basis_trade_date is not None:
                basis_date_text = basis_trade_date.isoformat()
                eligible_snapshots = [
                    snapshot
                    for snapshot in snapshots
                    if _date_text(snapshot.get("trade_date")) <= basis_date_text
                ]
            if not eligible_snapshots:
                results.append(
                    {
                        "strategy_id": item.id,
                        "strategy_name": item.name,
                        "target_name": item.target_name,
                        "latest_trade_date": "-",
                        "signal": None,
                        "signal_text": "无操作",
                        "note": "在当前通知基准交易日前暂无可用行情数据",
                    }
                )
                continue

            latest_snapshot = eligible_snapshots[-1]
            latest_trade_date = _date_text(latest_snapshot.get("trade_date"))
            signal_map = self._build_signal_map(item, snapshots)
            signal = signal_map.get(latest_trade_date)
            signal_text_map = {
                "blue": "蓝",
                "red": "红",
                "purple": "紫",
            }
            results.append(
                {
                    "strategy_id": item.id,
                    "strategy_name": item.name,
                    "target_name": item.target_name,
                    "latest_trade_date": latest_trade_date,
                    "signal": signal,
                    "signal_text": signal_text_map.get(signal, "无操作"),
                    "note": "出现操作信号" if signal else "当日无红蓝信号",
                }
            )

        return results

    def _build_market_scan_payload_from_strategy(self, strategy: QuantStrategyConfig) -> dict:
        return {
            "strategy_type": strategy.strategy_type,
            "indicator_params": strategy.indicator_params or {},
            "buy_sequence_groups": strategy.buy_sequence_groups or [],
            "scan_trade_config": strategy.scan_trade_config or {},
            "scan_start_date": strategy.scan_start_date,
            "scan_end_date": strategy.scan_end_date,
        }

    def _load_etf_price_rows(self, etf_code: str) -> list[dict]:
        return self._normalize_price_rows(self.stock_service.list_etf_daily_kline(etf_code))

    def _load_index_backtest_price_rows(
        self,
        index_code: str,
        index_name: str,
        target_market: str = "cn",
        signal_candles: list[dict] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        normalized_market = self._normalize_target_market(target_market)
        candles = (
            signal_candles
            if signal_candles is not None
            else self.stock_service.list_index_daily_kline(index_code, market=normalized_market)
        )
        if normalized_market != "cn":
            return candles, self._normalize_price_rows(candles)
        if str(index_name or "").strip() == BEIJING50_INDEX_NAME:
            return candles, self._normalize_price_rows(candles)

        etf_code = INDEX_TO_ETF_CODE.get(index_name)
        if not etf_code:
            raise ValueError("unsupported index target")
        return candles, self._load_etf_price_rows(etf_code)

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

    def _build_equity_curve_context(self, strategy: QuantStrategyConfig) -> tuple[list[dict], dict[str, str], dict[str, str], float]:
        strategy_type = str(strategy.strategy_type or "").strip().lower()
        strategy_engine = self._normalize_strategy_engine(strategy.strategy_engine)

        if strategy_engine == "sequence":
            snapshots = self._build_sequence_snapshots(strategy)
            if strategy_type == "index":
                _signal_candles, price_rows = self._load_index_backtest_price_rows(
                    strategy.target_code,
                    strategy.target_name,
                    self._normalize_target_market(getattr(strategy, "target_market", "cn")),
                )
            elif strategy_type == "stock":
                price_rows = self._normalize_price_rows(self.stock_service.list_daily_kline(strategy.target_code))
            elif strategy_type == "etf":
                price_rows = self._normalize_price_rows(self.stock_service.list_etf_daily_kline(strategy.target_code))
            else:
                raise ValueError("unsupported sequence target")
        else:
            if strategy_type == "index":
                signal_candles, price_rows = self._load_index_backtest_price_rows(
                    strategy.target_code,
                    strategy.target_name,
                    self._normalize_target_market(getattr(strategy, "target_market", "cn")),
                )
                snapshots = self._build_index_snapshots_for_market(
                    self._normalize_target_market(getattr(strategy, "target_market", "cn")),
                    strategy.target_code,
                    strategy.target_name,
                    strategy.indicator_params or {},
                    signal_candles,
                )
            else:
                signal_candles = self.stock_service.list_hfq_daily_kline(strategy.target_code)
                snapshots = self._build_stock_snapshots(strategy.indicator_params or {}, signal_candles)
                price_rows = self._normalize_price_rows(signal_candles)

        if not price_rows:
            return [], {}, {}, 1.0

        signal_map = self._build_signal_map(strategy, snapshots)
        start_date_text = strategy.start_date.isoformat() if strategy.start_date else _date_text(price_rows[0]["trade_date"])
        filtered_prices = [row for row in price_rows if _date_text(row["trade_date"]) >= start_date_text]
        if not filtered_prices:
            return [], signal_map, {}, 1.0

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

        initial_close = float(filtered_prices[0]["close"]) if filtered_prices else 1.0
        return filtered_prices, signal_map, pending_actions, initial_close

    def _simulate_equity_curve(
        self,
        *,
        filtered_prices: list[dict],
        signal_map: dict[str, str],
        pending_actions: dict[str, str],
        initial_close: float,
        buy_ratio: float,
        sell_ratio: float,
        execution_price_mode: str,
        include_signals: bool,
    ) -> dict:
        if not filtered_prices:
            return {
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "points": [],
            }

        cash = 1.0
        shares = 0.0
        points: list[dict] = []

        for row in filtered_prices:
            trade_date = _date_text(row["trade_date"])
            action = pending_actions.get(trade_date)
            if execution_price_mode == "next_open":
                exec_price = float(row["open"])
            elif execution_price_mode == "next_close":
                exec_price = float(row["close"])
            elif execution_price_mode == "next_best":
                exec_price = float(row["low"] if action == "buy" else row["high"])
            else:
                exec_price = float(row["open"])

            if action == "buy" and exec_price > 0:
                nav_before_trade = cash + shares * exec_price
                current_position_ratio = (shares * exec_price / nav_before_trade) if nav_before_trade > 0 else 0.0
                delta_ratio = max(min(1.0 - current_position_ratio, buy_ratio), 0.0)
                invest_cash = min(cash, nav_before_trade * delta_ratio)
                if invest_cash > 0:
                    shares += invest_cash / exec_price
                    cash -= invest_cash
            elif action == "sell" and exec_price > 0:
                nav_before_trade = cash + shares * exec_price
                current_position_ratio = (shares * exec_price / nav_before_trade) if nav_before_trade > 0 else 0.0
                delta_ratio = max(min(current_position_ratio, sell_ratio), 0.0)
                sell_value = nav_before_trade * delta_ratio
                sell_shares = min(shares, sell_value / exec_price) if exec_price > 0 else 0.0
                if sell_shares > 0:
                    shares -= sell_shares
                    cash += sell_shares * exec_price

            close_price = float(row["close"])
            position_value = shares * close_price
            nav = cash + position_value
            benchmark_nav = close_price / initial_close if initial_close else None
            position_pct = max(min((position_value / nav) if nav > 0 else 0.0, 1.0), 0.0)
            points.append(
                {
                    "trade_date": row["trade_date"],
                    "nav": nav,
                    "benchmark_nav": benchmark_nav,
                    "signal": signal_map.get(trade_date) if include_signals else None,
                    "close_price": close_price,
                    "position_value": position_value,
                    "position_pct": position_pct,
                    "position_bucket": _position_bucket(position_pct),
                }
            )

        cumulative_return_pct = (points[-1]["nav"] - 1) * 100 if points else 0.0
        peak_nav = 0.0
        max_drawdown_pct = 0.0
        for point in points:
            nav = float(point["nav"])
            peak_nav = max(peak_nav, nav)
            if peak_nav > 0:
                drawdown_pct = (peak_nav - nav) / peak_nav * 100
                max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

        start_dt = filtered_prices[0]["trade_date"]
        end_dt = filtered_prices[-1]["trade_date"]
        days_span = max((end_dt - start_dt).days, 0)
        if points and days_span > 0 and points[-1]["nav"] > 0:
            annualized_return_pct = ((points[-1]["nav"] ** (365 / days_span)) - 1) * 100
        else:
            annualized_return_pct = cumulative_return_pct if points else 0.0

        return {
            "cumulative_return_pct": cumulative_return_pct,
            "annualized_return_pct": annualized_return_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "points": points,
        }

    def _optimize_position_pairs(
        self,
        *,
        filtered_prices: list[dict],
        signal_map: dict[str, str],
        pending_actions: dict[str, str],
        initial_close: float,
        execution_price_mode: str,
    ) -> dict:
        max_total_return_value: float | None = None
        min_drawdown_value: float | None = None
        max_total_return_pairs: list[dict] = []
        min_drawdown_pairs: list[dict] = []

        for buy_ratio in BUY_POSITION_SEARCH_RATIOS:
            for sell_ratio in SELL_POSITION_SEARCH_RATIOS:
                result = self._simulate_equity_curve(
                    filtered_prices=filtered_prices,
                    signal_map=signal_map,
                    pending_actions=pending_actions,
                    initial_close=initial_close,
                    buy_ratio=buy_ratio,
                    sell_ratio=sell_ratio,
                    execution_price_mode=execution_price_mode,
                    include_signals=False,
                )
                if not result["points"]:
                    continue

                pair = {
                    "buy_position_pct": _round_metric(buy_ratio),
                    "sell_position_pct": _round_metric(sell_ratio),
                    "cumulative_return_pct": _round_metric(result["cumulative_return_pct"]),
                }
                total_return = float(result["cumulative_return_pct"])
                drawdown = float(result["max_drawdown_pct"])

                if max_total_return_value is None or total_return > max_total_return_value + OPTIMIZATION_TOLERANCE:
                    max_total_return_value = total_return
                    max_total_return_pairs = [pair]
                elif abs(total_return - max_total_return_value) <= OPTIMIZATION_TOLERANCE:
                    max_total_return_pairs.append(pair)

                if min_drawdown_value is None or drawdown < min_drawdown_value - OPTIMIZATION_TOLERANCE:
                    min_drawdown_value = drawdown
                    min_drawdown_pairs = [pair]
                elif abs(drawdown - min_drawdown_value) <= OPTIMIZATION_TOLERANCE:
                    min_drawdown_pairs.append(pair)

        return {
            "max_total_return": {
                "value_pct": _round_metric(max_total_return_value or 0.0),
                "combinations": max_total_return_pairs,
            },
            "min_drawdown": {
                "value_pct": _round_metric(min_drawdown_value or 0.0),
                "combinations": min_drawdown_pairs,
            },
        }

    def calculate_equity_curve(self, strategy_id: int, owner_user_id: int) -> dict:
        strategy = self._get_owned_strategy(strategy_id, owner_user_id)
        if (
            self._normalize_strategy_engine(strategy.strategy_engine) == "sequence"
            and self._normalize_sequence_mode(strategy.sequence_mode) == "market_scan"
        ):
            preview = self.preview_market_scan(self._build_market_scan_payload_from_strategy(strategy), owner_user_id)
            scan_result = self.backtest_market_scan(
                {
                    "scan_result_id": preview["scan_result_id"],
                    "scan_trade_config": strategy.scan_trade_config or {},
                    "use_all_events": True,
                    "excluded_event_ids": [],
                },
                owner_user_id,
            )
            empty_optimization = {
                "max_total_return": {"value_pct": 0.0, "combinations": []},
                "min_drawdown": {"value_pct": 0.0, "combinations": []},
            }
            return {
                "strategy": self._serialize_strategy(strategy),
                "cumulative_return_pct": scan_result["cumulative_return_pct"],
                "annualized_return_pct": scan_result["annualized_return_pct"],
                "max_drawdown_pct": scan_result["max_drawdown_pct"],
                "points": scan_result["points"],
                "position_optimization": empty_optimization,
            }

        filtered_prices, signal_map, pending_actions, initial_close = self._build_equity_curve_context(strategy)
        empty_optimization = {
            "max_total_return": {"value_pct": 0.0, "combinations": []},
            "min_drawdown": {"value_pct": 0.0, "combinations": []},
        }
        if not filtered_prices:
            return {
                "strategy": self._serialize_strategy(strategy),
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "points": [],
                "position_optimization": empty_optimization,
            }

        execution_price_mode = (strategy.execution_price_mode or "next_open").strip()
        result = self._simulate_equity_curve(
            filtered_prices=filtered_prices,
            signal_map=signal_map,
            pending_actions=pending_actions,
            initial_close=initial_close,
            buy_ratio=_normalize_ratio(strategy.buy_position_pct),
            sell_ratio=_normalize_ratio(strategy.sell_position_pct),
            execution_price_mode=execution_price_mode,
            include_signals=True,
        )
        optimization = self._optimize_position_pairs(
            filtered_prices=filtered_prices,
            signal_map=signal_map,
            pending_actions=pending_actions,
            initial_close=initial_close,
            execution_price_mode=execution_price_mode,
        )

        return {
            "strategy": self._serialize_strategy(strategy),
            "cumulative_return_pct": result["cumulative_return_pct"],
            "annualized_return_pct": result["annualized_return_pct"],
            "max_drawdown_pct": result["max_drawdown_pct"],
            "points": result["points"],
            "position_optimization": optimization,
        }
