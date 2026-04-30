import json
from collections import defaultdict
from datetime import date

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client

INDEX_DISPLAY_ORDER = [
    "上证指数",
    "上证50",
    "沪深300",
    "中证500",
    "中证1000",
    "北证50",
]

SUPPORTED_INDEX_MARKETS = {"cn", "hk", "us"}

BEIJING50_INDEX_OPTION = {
    "code": "BJ899050",
    "name": "北证50",
}

FOREX_DISPLAY_ORDER = [
    "美元指数",
    "美元兑离岸人民币",
    "离岸人民币兑日元",
    "离岸人民币兑欧元",
    "离岸人民币兑港币",
    "美元兑港币",
    "美元兑日元",
    "美元兑欧元",
]

EXCEL_INDEX_EMOTION_ORDER = [
    "上证50",
    "沪深300",
    "中证500",
    "中证1000",
]

FUTURES_BASIS_SYMBOL_MAP = [
    {"index_name": "上证50", "main_symbol": "IHM", "month_symbol": "IHM0"},
    {"index_name": "沪深300", "main_symbol": "IFM", "month_symbol": "IFM0"},
    {"index_name": "中证500", "main_symbol": "ICM", "month_symbol": "ICM0"},
    {"index_name": "中证1000", "main_symbol": "IMM", "month_symbol": "IMM0"},
]

CFFEX_PRODUCT_INDEX_MAP = [
    {"product_code": "IH", "index_name": "上证50"},
    {"product_code": "IF", "index_name": "沪深300"},
    {"product_code": "IC", "index_name": "中证500"},
    {"product_code": "IM", "index_name": "中证1000"},
]

CFFEX_SERIES_KEYS = ["OVERALL", "IF", "IH", "IC", "IM"]

CITIC_CUSTOMER_MEMBER_NAME = "中信期货(代客)"
CITIC_CUSTOMER_MEMBER_NAME_BROKER = "中信期货(经纪)"
CITIC_CUSTOMER_MEMBER_NAME_LEGACY = "中信期货"
CITIC_CUSTOMER_MEMBER_BROKER_START_DATE = date(2024, 2, 26)
CITIC_CUSTOMER_MEMBER_CURRENT_START_DATE = date(2024, 4, 29)

INDEX_OPTIONS_CACHE_KEY_PREFIX = "fit:stock:index_options:v5"
FOREX_OPTIONS_CACHE_KEY = "fit:stock:forex_options:v2"
INDEX_EMOTIONS_CACHE_KEY_PREFIX = "fit:stock:index_emotions:v2"
CFFEX_NET_POSITION_TABLES_CACHE_KEY_PREFIX = "fit:stock:cffex:tables:v1"
CFFEX_NET_POSITION_SERIES_CACHE_KEY_PREFIX = "fit:stock:cffex:series:v1"
INDEX_KLINE_CACHE_KEY_PREFIX = "fit:stock:index_kline:v1"
FOREX_KLINE_CACHE_KEY_PREFIX = "fit:stock:forex_kline:v1"
CACHE_TTL_SECONDS = 600


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class StockService:
    def __init__(self, db: Session):
        self.db = db

    def _normalize_stock_scan_row(self, row: dict) -> dict:
        item = dict(row)
        item["change"] = item.pop("change_value", 0)
        for field in [
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "turnover_rate",
            "pe_ttm",
            "pb",
            "total_market_value",
            "circulating_market_value",
        ]:
            if item.get(field) is None:
                item[field] = 0
        return item

    def _cache_get_json(self, key: str):
        cached = redis_client.get(key)
        if not cached:
            return None
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            return None

    def _cache_set_json(self, key: str, value) -> None:
        redis_client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=CACHE_TTL_SECONDS)

    def clear_forex_cache(self, symbol_code: str | None = None) -> None:
        redis_client.delete(FOREX_OPTIONS_CACHE_KEY)
        normalized_codes = {
            str(symbol_code or "").strip(),
            str(symbol_code or "").strip().upper(),
        }
        cache_keys: set[str] = set()
        for code in normalized_codes:
            if not code:
                continue
            cache_keys.update(redis_client.scan_iter(f"{FOREX_KLINE_CACHE_KEY_PREFIX}:{code}:*"))
        if cache_keys:
            redis_client.delete(*cache_keys)

    @property
    def mapping(self) -> dict[str, str]:
        return {
            "ts_code": settings.stock_code_column,
            "trade_date": settings.stock_date_column,
            "open": settings.stock_open_column,
            "high": settings.stock_high_column,
            "low": settings.stock_low_column,
            "close": settings.stock_close_column,
            "pre_close": settings.stock_pre_close_column,
            "change": settings.stock_change_column,
            "pct_chg": settings.stock_pct_chg_column,
            "vol": settings.stock_vol_column,
            "amount": settings.stock_amount_column,
            "pe_ttm": settings.stock_pe_ttm_column,
            "pb": settings.stock_pb_column,
            "total_market_value": settings.stock_total_market_value_column,
            "circulating_market_value": settings.stock_circulating_market_value_column,
        }

    def get_table_columns(self) -> set[str]:
        inspector = inspect(self.db.bind)
        return {col["name"] for col in inspector.get_columns(settings.stock_table_name)}

    def available_mapping(self) -> dict[str, str]:
        cols = self.get_table_columns()
        return {key: value for key, value in self.mapping.items() if value in cols}

    def connection_status(self) -> dict:
        try:
            self.db.execute(text("SELECT 1"))
            cols = self.get_table_columns()
            mapping = self.available_mapping()
            required = {"ts_code", "trade_date", "open", "high", "low", "close"}
            has_required_mapping = required.issubset(mapping)

            symbol_count = 0
            sample_symbols: list[str] = []

            if settings.stock_code_column in cols:
                symbol_count_query = text(
                    f"SELECT COUNT(DISTINCT `{settings.stock_code_column}`) AS c "
                    f"FROM `{settings.stock_table_name}`"
                )
                symbol_count = int(self.db.execute(symbol_count_query).scalar() or 0)

                sample_query = text(
                    f"SELECT DISTINCT `{settings.stock_code_column}` AS ts_code "
                    f"FROM `{settings.stock_table_name}` "
                    f"ORDER BY `{settings.stock_code_column}` LIMIT 5"
                )
                sample_symbols = [str(row["ts_code"]) for row in self.db.execute(sample_query).mappings().all()]

            count_query = text(f"SELECT COUNT(*) AS c FROM `{settings.stock_table_name}`")
            rows_count = int(self.db.execute(count_query).scalar() or 0)

            return {
                "connected": True,
                "table_name": settings.stock_table_name,
                "table_exists": True,
                "has_required_mapping": has_required_mapping,
                "row_count": rows_count,
                "symbol_count": symbol_count,
                "sample_symbols": sample_symbols,
                "mapping": mapping,
            }
        except Exception as exc:
            return {
                "connected": False,
                "table_name": settings.stock_table_name,
                "table_exists": False,
                "has_required_mapping": False,
                "row_count": 0,
                "symbol_count": 0,
                "sample_symbols": [],
                "mapping": {},
                "error": str(exc),
            }

    def _query_stock_basics_from_db(self) -> list[dict]:
        sql = text(
            f"SELECT "
            f"`{settings.stock_basic_info_code_column}` AS ts_code, "
            f"`{settings.stock_basic_info_prefixed_code_column}` AS prefixed_code, "
            f"`{settings.stock_basic_info_name_column}` AS stock_name, "
            f"`{settings.stock_basic_info_board_column}` AS board "
            f"FROM `{settings.stock_basic_info_table_name}` "
            f"ORDER BY `{settings.stock_basic_info_code_column}`"
        )
        return [dict(row) for row in self.db.execute(sql).mappings().all()]

    def load_stock_basics_to_cache(self) -> list[dict]:
        items = self._query_stock_basics_from_db()
        redis_client.set(
            settings.stock_basic_cache_key,
            json.dumps(items, ensure_ascii=False),
            ex=settings.stock_basic_cache_ttl_seconds,
        )
        return items

    def get_stock_basics(self) -> list[dict]:
        cached = redis_client.get(settings.stock_basic_cache_key)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        return self.load_stock_basics_to_cache()

    def search_symbols(self, keyword: str | None = None, limit: int = 200) -> list[dict]:
        items = self.get_stock_basics()
        if keyword:
            key = keyword.strip().lower()
            items = [
                item
                for item in items
                if key in str(item.get("ts_code", "")).lower()
                or key in str(item.get("prefixed_code", "")).lower()
                or key in str(item.get("stock_name", "")).lower()
            ]
        return items[:limit]

    def search_etf_options(self, keyword: str | None = None, limit: int = 200) -> list[dict]:
        sql = text(
            f"SELECT DISTINCT "
            f"`{settings.etf_basic_info_code_column}` AS code, "
            f"`{settings.etf_basic_info_name_column}` AS name "
            f"FROM `{settings.etf_basic_info_table_name}` "
            f"ORDER BY `{settings.etf_basic_info_code_column}` ASC"
        )
        items = [dict(row) for row in self.db.execute(sql).mappings().all()]
        if keyword:
            key = keyword.strip().lower()
            items = [
                item
                for item in items
                if key in str(item.get("code", "")).lower() or key in str(item.get("name", "")).lower()
            ]
        return items[:limit]

    def get_stock_basic_map(self) -> dict[str, dict]:
        return {
            str(item.get("ts_code", "")).strip(): item
            for item in self._query_stock_basics_from_db()
            if str(item.get("ts_code", "")).strip()
        }

    def get_etf_basic_map(self) -> dict[str, dict]:
        sql = text(
            f"SELECT DISTINCT "
            f"`{settings.etf_basic_info_code_column}` AS code, "
            f"`{settings.etf_basic_info_name_column}` AS name "
            f"FROM `{settings.etf_basic_info_table_name}` "
            f"ORDER BY `{settings.etf_basic_info_code_column}` ASC"
        )
        return {
            str(row.get("code", "")).strip(): dict(row)
            for row in self.db.execute(sql).mappings().all()
            if str(row.get("code", "")).strip()
        }

    def _build_in_filter_sql(self, column_name: str, value_prefix: str, values: list[str], params: dict[str, object]) -> str:
        normalized_values = [str(value).strip() for value in values if str(value).strip()]
        if not normalized_values:
            return " AND 1 = 0"
        placeholders: list[str] = []
        for index, value in enumerate(sorted(set(normalized_values))):
            param_name = f"{value_prefix}_{index}"
            params[param_name] = value
            placeholders.append(f":{param_name}")
        return f" AND `{column_name}` IN ({', '.join(placeholders)})"

    def list_stock_scan_universe(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        target_codes: list[str] | None = None,
    ) -> dict[str, dict]:
        basics_by_code = self.get_stock_basic_map()
        if not basics_by_code:
            return {}
        if target_codes is not None:
            allowed_codes = {str(code).strip() for code in target_codes if str(code).strip()}
            basics_by_code = {code: basic for code, basic in basics_by_code.items() if code in allowed_codes}
            if not basics_by_code:
                return {}

        table_columns = self.get_table_columns()
        turnover_rate_expr = (
            f"COALESCE(`{settings.stock_turnover_rate_column}`, 0)"
            if settings.stock_turnover_rate_column in table_columns
            else "0"
        )
        params: dict[str, object] = {
            "hist_source": settings.stock_hist_source_value,
            "spot_source": settings.stock_spot_source_value,
        }
        date_filter_sql = ""
        if start_date:
            params["start_date"] = start_date
            date_filter_sql += f" AND `{settings.stock_date_column}` >= :start_date"
        if end_date:
            params["end_date"] = end_date
            date_filter_sql += f" AND `{settings.stock_date_column}` <= :end_date"
        if target_codes is not None:
            date_filter_sql += self._build_in_filter_sql(settings.stock_code_column, "stock_code", list(basics_by_code.keys()), params)

        base_select = (
            f"SELECT "
            f"`{settings.stock_code_column}` AS stock_code, "
            f"`{settings.stock_date_column}` AS trade_date, "
            f"`{settings.stock_open_column}` AS open, "
            f"`{settings.stock_high_column}` AS high, "
            f"`{settings.stock_low_column}` AS low, "
            f"`{settings.stock_close_column}` AS close, "
            f"COALESCE(`{settings.stock_pre_close_column}`, 0) AS pre_close, "
            f"COALESCE(`{settings.stock_change_column}`, 0) AS change_value, "
            f"COALESCE(`{settings.stock_pct_chg_column}`, 0) AS pct_chg, "
            f"COALESCE(`{settings.stock_vol_column}`, 0) AS vol, "
            f"COALESCE(`{settings.stock_amount_column}`, 0) AS amount, "
            f"{turnover_rate_expr} AS turnover_rate, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{settings.stock_table_name}` "
            f"WHERE `{settings.stock_data_source_column}` = :data_source"
            f"{date_filter_sql} "
        )

        hist_rows = self.db.execute(
            text(base_select),
            {**params, "data_source": settings.stock_hist_source_value},
        ).mappings().all()
        spot_rows = self.db.execute(
            text(
                (
                    f"SELECT "
                    f"`{settings.stock_code_column}` AS stock_code, "
                    f"`{settings.stock_date_column}` AS trade_date, "
                    f"`{settings.stock_open_column}` AS open, "
                    f"`{settings.stock_high_column}` AS high, "
                    f"`{settings.stock_low_column}` AS low, "
                    f"COALESCE(`{settings.stock_latest_price_column}`, `{settings.stock_close_column}`) AS close, "
                    f"COALESCE(`{settings.stock_pre_close_column}`, 0) AS pre_close, "
                    f"COALESCE(`{settings.stock_change_column}`, 0) AS change_value, "
                    f"COALESCE(`{settings.stock_pct_chg_column}`, 0) AS pct_chg, "
                    f"COALESCE(`{settings.stock_vol_column}`, 0) AS vol, "
                    f"COALESCE(`{settings.stock_amount_column}`, 0) AS amount, "
                    f"{turnover_rate_expr} AS turnover_rate, "
                    f"0 AS pe_ttm, "
                    f"0 AS pb, "
                    f"0 AS total_market_value, "
                    f"0 AS circulating_market_value "
                    f"FROM `{settings.stock_table_name}` "
                    f"WHERE `{settings.stock_data_source_column}` = :data_source"
                    f"{date_filter_sql} "
                )
            ),
            {**params, "data_source": settings.stock_spot_source_value},
        ).mappings().all()

        rows_by_code: dict[str, dict[date, dict]] = defaultdict(dict)
        for row in hist_rows:
            stock_code = str(row.get("stock_code", "")).strip()
            trade_date = row.get("trade_date")
            if not stock_code or trade_date is None or stock_code not in basics_by_code:
                continue
            rows_by_code[stock_code][trade_date] = self._normalize_stock_scan_row(dict(row))
        for row in spot_rows:
            stock_code = str(row.get("stock_code", "")).strip()
            trade_date = row.get("trade_date")
            if not stock_code or trade_date is None or stock_code not in basics_by_code:
                continue
            rows_by_code[stock_code][trade_date] = self._normalize_stock_scan_row(dict(row))

        result: dict[str, dict] = {}
        for stock_code, basic in basics_by_code.items():
            rows_by_date = rows_by_code.get(stock_code)
            if not rows_by_date:
                continue
            candles = [rows_by_date[trade_date] for trade_date in sorted(rows_by_date.keys())]
            result[stock_code] = {
                "target_code": stock_code,
                "target_name": str(basic.get("stock_name", "")).strip() or stock_code,
                "board": str(basic.get("board", "")).strip() or None,
                "candles": candles,
            }
        return result

    def list_etf_scan_universe(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        target_codes: list[str] | None = None,
    ) -> dict[str, dict]:
        basics_by_code = self.get_etf_basic_map()
        if not basics_by_code:
            return {}
        if target_codes is not None:
            allowed_codes = {str(code).strip() for code in target_codes if str(code).strip()}
            basics_by_code = {code: basic for code, basic in basics_by_code.items() if code in allowed_codes}
            if not basics_by_code:
                return {}

        params: dict[str, object] = {
            "hist_source": settings.etf_daily_hist_source_value,
            "spot_source": settings.etf_daily_spot_source_value,
        }
        date_filter_sql = ""
        if start_date:
            params["start_date"] = start_date
            date_filter_sql += f" AND `{settings.etf_daily_date_column}` >= :start_date"
        if end_date:
            params["end_date"] = end_date
            date_filter_sql += f" AND `{settings.etf_daily_date_column}` <= :end_date"
        if target_codes is not None:
            date_filter_sql += self._build_in_filter_sql(
                settings.etf_daily_code_column,
                "etf_code",
                list(basics_by_code.keys()),
                params,
            )

        hist_sql = text(
            f"SELECT "
            f"`{settings.etf_daily_code_column}` AS etf_code, "
            f"`{settings.etf_daily_date_column}` AS trade_date, "
            f"`{settings.etf_daily_open_column}` AS open, "
            f"`{settings.etf_daily_high_column}` AS high, "
            f"`{settings.etf_daily_low_column}` AS low, "
            f"`{settings.etf_daily_close_column}` AS close "
            f"FROM `{settings.etf_daily_table_name}` "
            f"WHERE `{settings.etf_daily_data_source_column}` = :hist_source"
            f"{date_filter_sql} "
            f"ORDER BY `{settings.etf_daily_code_column}` ASC, `{settings.etf_daily_date_column}` ASC"
        )
        spot_sql = text(
            f"SELECT "
            f"`{settings.etf_daily_code_column}` AS etf_code, "
            f"`{settings.etf_daily_date_column}` AS trade_date, "
            f"`{settings.etf_daily_open_column}` AS open, "
            f"`{settings.etf_daily_high_column}` AS high, "
            f"`{settings.etf_daily_low_column}` AS low, "
            f"`{settings.etf_daily_close_column}` AS close "
            f"FROM `{settings.etf_daily_table_name}` "
            f"WHERE `{settings.etf_daily_data_source_column}` = :spot_source"
            f"{date_filter_sql} "
            f"ORDER BY `{settings.etf_daily_code_column}` ASC, `{settings.etf_daily_date_column}` ASC"
        )
        rows_by_key: dict[tuple[str, date], dict] = {}
        for row in self.db.execute(hist_sql, params).mappings().all():
            etf_code = str(row.get("etf_code", "")).strip()
            trade_date = row.get("trade_date")
            if not etf_code or trade_date is None or etf_code not in basics_by_code:
                continue
            rows_by_key[(etf_code, trade_date)] = dict(row)
        for row in self.db.execute(spot_sql, params).mappings().all():
            etf_code = str(row.get("etf_code", "")).strip()
            trade_date = row.get("trade_date")
            if not etf_code or trade_date is None or etf_code not in basics_by_code:
                continue
            rows_by_key[(etf_code, trade_date)] = dict(row)

        grouped: dict[str, list[dict]] = {}
        for (etf_code, _trade_date), row in sorted(rows_by_key.items(), key=lambda item: (item[0][0], item[0][1])):
            open_price = _to_float(row.get("open"))
            high_price = _to_float(row.get("high"))
            low_price = _to_float(row.get("low"))
            close_price = _to_float(row.get("close"))
            trade_date = row.get("trade_date")
            if trade_date is None or open_price is None or high_price is None or low_price is None or close_price is None:
                continue
            candles = grouped.setdefault(etf_code, [])
            previous_close = candles[-1]["close"] if candles else close_price
            change_value = close_price - previous_close
            pct_chg = (change_value / previous_close * 100) if previous_close else 0.0
            candles.append(
                {
                    "trade_date": trade_date,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "pre_close": previous_close,
                    "change": change_value,
                    "pct_chg": pct_chg,
                    "vol": 0.0,
                    "amount": 0.0,
                    "turnover_rate": 0.0,
                    "pe_ttm": 0.0,
                    "pb": 0.0,
                    "total_market_value": 0.0,
                    "circulating_market_value": 0.0,
                }
            )

        result: dict[str, dict] = {}
        for etf_code, basic in basics_by_code.items():
            candles = grouped.get(etf_code)
            if not candles:
                continue
            result[etf_code] = {
                "target_code": etf_code,
                "target_name": str(basic.get("name", "")).strip() or etf_code,
                "board": "ETF",
                "candles": candles,
            }
        return result

    def _resolve_stock_code(self, ts_code: str) -> str:
        normalized = str(ts_code or "").strip().lower()
        if not normalized:
            return ""
        if normalized.isdigit() and len(normalized) == 6:
            return normalized

        sql = text(
            f"SELECT `{settings.stock_basic_info_code_column}` AS stock_code "
            f"FROM `{settings.stock_basic_info_table_name}` "
            f"WHERE LOWER(`{settings.stock_basic_info_code_column}`) = :code "
            f"OR LOWER(`{settings.stock_basic_info_prefixed_code_column}`) = :code "
            f"LIMIT 1"
        )
        row = self.db.execute(sql, {"code": normalized}).mappings().first()
        if not row:
            return normalized
        return str(row["stock_code"]).strip()

    def _filter_named_options(self, items: list[dict], order: list[str], code_key: str, name_key: str) -> list[dict]:
        item_by_name: dict[str, list[dict[str, str]]] = {}
        for item in items:
            code = str(item.get(code_key, "")).strip()
            name = str(item.get(name_key, "")).strip()
            if not code or not name:
                continue
            item_by_name.setdefault(name, []).append({"code": code, "name": name})

        result: list[dict[str, str]] = []
        for name in order:
            matched = item_by_name.get(name, [])
            if not matched:
                continue
            if name == "美元指数":
                udi_match = next((item for item in matched if item["code"].upper() == "UDI"), None)
                result.append(udi_match or matched[0])
                continue
            if name == "中证1000":
                sh_match = next((item for item in matched if item["code"].lower().startswith("sh")), None)
                result.append(sh_match or matched[0])
                continue
            result.append(matched[0])
        return result

    def _normalize_index_market(self, market: str | None) -> str:
        normalized = str(market or "cn").strip().lower()
        return normalized if normalized in SUPPORTED_INDEX_MARKETS else "cn"

    def _get_index_market_config(self, market: str | None) -> dict[str, str]:
        normalized = self._normalize_index_market(market)
        if normalized == "hk":
            return {
                "market": "hk",
                "basic_table": settings.index_hk_basic_info_table_name,
                "basic_code_column": settings.index_hk_basic_info_code_column,
                "basic_name_column": settings.index_hk_basic_info_name_column,
                "daily_table": settings.index_hk_daily_table_name,
                "daily_code_column": settings.index_hk_daily_code_column,
                "daily_date_column": settings.index_hk_daily_date_column,
                "daily_open_column": settings.index_hk_daily_open_column,
                "daily_high_column": settings.index_hk_daily_high_column,
                "daily_low_column": settings.index_hk_daily_low_column,
                "daily_close_column": settings.index_hk_daily_close_column,
                "daily_change_column": settings.index_hk_daily_change_column,
                "daily_pct_chg_column": settings.index_hk_daily_pct_chg_column,
                "daily_vol_column": settings.index_hk_daily_vol_column,
                "daily_amount_column": settings.index_hk_daily_amount_column,
            }
        if normalized == "us":
            return {
                "market": "us",
                "basic_table": settings.index_us_basic_info_table_name,
                "basic_code_column": settings.index_us_basic_info_code_column,
                "basic_name_column": settings.index_us_basic_info_name_column,
                "daily_table": settings.index_us_daily_table_name,
                "daily_code_column": settings.index_us_daily_code_column,
                "daily_date_column": settings.index_us_daily_date_column,
                "daily_open_column": settings.index_us_daily_open_column,
                "daily_high_column": settings.index_us_daily_high_column,
                "daily_low_column": settings.index_us_daily_low_column,
                "daily_close_column": settings.index_us_daily_close_column,
                "daily_change_column": settings.index_us_daily_change_column,
                "daily_pct_chg_column": settings.index_us_daily_pct_chg_column,
                "daily_vol_column": settings.index_us_daily_vol_column,
                "daily_amount_column": settings.index_us_daily_amount_column,
            }
        return {
            "market": "cn",
            "basic_table": settings.index_basic_info_table_name,
            "basic_code_column": settings.index_basic_info_code_column,
            "basic_name_column": settings.index_basic_info_name_column,
            "daily_table": settings.index_daily_table_name,
            "daily_code_column": settings.index_daily_code_column,
            "daily_date_column": settings.index_daily_date_column,
            "daily_open_column": settings.index_daily_open_column,
            "daily_high_column": settings.index_daily_high_column,
            "daily_low_column": settings.index_daily_low_column,
            "daily_close_column": settings.index_daily_close_column,
            "daily_change_column": settings.index_daily_change_column,
            "daily_pct_chg_column": settings.index_daily_pct_chg_column,
            "daily_vol_column": settings.index_daily_vol_column,
            "daily_amount_column": settings.index_daily_amount_column,
        }

    def list_index_options(self, market: str | None = "cn") -> list[dict]:
        normalized_market = self._normalize_index_market(market)
        cache_key = f"{INDEX_OPTIONS_CACHE_KEY_PREFIX}:{normalized_market}"
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached
        config = self._get_index_market_config(normalized_market)
        sql = text(
            f"SELECT `{config['basic_code_column']}` AS code, "
            f"`{config['basic_name_column']}` AS name "
            f"FROM `{config['basic_table']}`"
        )
        items = [dict(row) for row in self.db.execute(sql).mappings().all()]
        if normalized_market == "cn" and not any(str(item.get("name", "")).strip() == BEIJING50_INDEX_OPTION["name"] for item in items):
            items.append(dict(BEIJING50_INDEX_OPTION))
        if normalized_market == "cn":
            result = self._filter_named_options(items, INDEX_DISPLAY_ORDER, "code", "name")
            result = [
                {
                    "code": BEIJING50_INDEX_OPTION["code"]
                    if str(item.get("code", "")).strip().lower() == BEIJING50_INDEX_OPTION["code"].lower()
                    or str(item.get("name", "")).strip() == BEIJING50_INDEX_OPTION["name"]
                    else str(item.get("code", "")).strip(),
                    "name": str(item.get("name", "")).strip(),
                }
                for item in result
            ]
        else:
            result = sorted(
                [
                    {"code": str(item.get("code", "")).strip(), "name": str(item.get("name", "")).strip()}
                    for item in items
                    if str(item.get("code", "")).strip() and str(item.get("name", "")).strip()
                ],
                key=lambda item: (item["name"], item["code"]),
            )
        self._cache_set_json(cache_key, result)
        return result

    def list_forex_options(self) -> list[dict]:
        cached = self._cache_get_json(FOREX_OPTIONS_CACHE_KEY)
        if isinstance(cached, list):
            return cached
        sql = text(
            f"SELECT DISTINCT "
            f"`{settings.forex_daily_code_column}` AS code, "
            f"`{settings.forex_daily_name_column}` AS name "
            f"FROM `{settings.forex_daily_table_name}`"
        )
        items = [dict(row) for row in self.db.execute(sql).mappings().all()]
        if not items:
            fallback_sql = text(
                f"SELECT `{settings.forex_basic_info_code_column}` AS code, "
                f"`{settings.forex_basic_info_name_column}` AS name "
                f"FROM `{settings.forex_basic_info_table_name}`"
            )
            items = [dict(row) for row in self.db.execute(fallback_sql).mappings().all()]
        result = self._filter_named_options(items, FOREX_DISPLAY_ORDER, "code", "name")
        self._cache_set_json(FOREX_OPTIONS_CACHE_KEY, result)
        return result

    def list_excel_index_emotions(self, start_date: date | None = None) -> list[dict]:
        cache_key = f"{INDEX_EMOTIONS_CACHE_KEY_PREFIX}:{start_date.isoformat() if start_date else 'full'}"
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached
        sql = text(
            f"SELECT "
            f"`{settings.excel_index_emotion_date_column}` AS emotion_date, "
            f"`{settings.excel_index_emotion_name_column}` AS index_name, "
            f"`{settings.excel_index_emotion_value_column}` AS emotion_value "
            f"FROM `{settings.excel_index_emotion_table_name}` "
            f"{f'WHERE `{settings.excel_index_emotion_date_column}` >= :start_date ' if start_date else ''}"
            f"ORDER BY `{settings.excel_index_emotion_date_column}` ASC"
        )
        allowed_names = set(EXCEL_INDEX_EMOTION_ORDER)
        rows = self.db.execute(sql, {"start_date": start_date} if start_date else {}).mappings().all()
        result: list[dict] = []
        for row in rows:
            index_name = str(row.get("index_name", "")).strip()
            if index_name not in allowed_names:
                continue
            emotion_value = row.get("emotion_value")
            if emotion_value is None:
                continue
            result.append(
                {
                    "emotion_date": row.get("emotion_date"),
                    "index_name": index_name,
                    "emotion_value": float(emotion_value),
                }
            )
        self._cache_set_json(cache_key, result)
        return result

    def list_index_futures_basis(self) -> list[dict]:
        allowed_names = {item["index_name"] for item in FUTURES_BASIS_SYMBOL_MAP}
        index_code_by_name = {
            str(item["name"]): str(item["code"])
            for item in self.list_index_options()
            if str(item.get("name", "")).strip() in allowed_names
        }

        if not index_code_by_name:
            return []

        code_to_name = {code: name for name, code in index_code_by_name.items()}
        code_sql = ", ".join([f":code_{index}" for index, _ in enumerate(index_code_by_name.values())])
        code_params = {f"code_{index}": code for index, code in enumerate(index_code_by_name.values())}

        index_sql = text(
            f"SELECT "
            f"`{settings.index_daily_code_column}` AS index_code, "
            f"`{settings.index_daily_date_column}` AS trade_date, "
            f"`{settings.index_daily_close_column}` AS close_price "
            f"FROM `{settings.index_daily_table_name}` "
            f"WHERE `{settings.index_daily_code_column}` IN ({code_sql})"
        )
        spot_rows = self.db.execute(index_sql, code_params).mappings().all()
        spot_close_by_key = {
            (code_to_name.get(str(row["index_code"]), ""), row["trade_date"]): float(row["close_price"])
            for row in spot_rows
            if row.get("trade_date") is not None
            and row.get("close_price") is not None
            and str(row.get("index_code", "")).strip() in code_to_name
        }

        symbol_meta: dict[str, tuple[str, str]] = {}
        for item in FUTURES_BASIS_SYMBOL_MAP:
            symbol_meta[item["main_symbol"]] = (item["index_name"], "main_basis")
            symbol_meta[item["month_symbol"]] = (item["index_name"], "month_basis")

        symbol_sql = ", ".join([f":symbol_{index}" for index, _ in enumerate(symbol_meta.keys())])
        symbol_params = {f"symbol_{index}": symbol for index, symbol in enumerate(symbol_meta.keys())}
        symbol_params["primary_source"] = settings.futures_daily_primary_source_value
        symbol_params["fallback_source"] = settings.futures_daily_fallback_source_value

        futures_sql = text(
            f"SELECT "
            f"`{settings.futures_daily_trade_date_column}` AS trade_date, "
            f"`{settings.futures_daily_symbol_column}` AS symbol, "
            f"`{settings.futures_daily_close_column}` AS close_price, "
            f"`{settings.futures_daily_data_source_column}` AS data_source "
            f"FROM `{settings.futures_daily_table_name}` "
            f"WHERE `{settings.futures_daily_symbol_column}` IN ({symbol_sql}) "
            f"AND `{settings.futures_daily_data_source_column}` IN (:primary_source, :fallback_source) "
            f"ORDER BY `{settings.futures_daily_trade_date_column}` ASC"
        )
        futures_rows = self.db.execute(futures_sql, symbol_params).mappings().all()

        source_priority = {
            settings.futures_daily_primary_source_value: 0,
            settings.futures_daily_fallback_source_value: 1,
        }
        best_futures_by_key: dict[tuple[str, object], dict] = {}
        for row in futures_rows:
            trade_date = row.get("trade_date")
            symbol = str(row.get("symbol", "")).strip().upper()
            close_price = row.get("close_price")
            data_source = str(row.get("data_source", "")).strip()
            priority = source_priority.get(data_source)
            if trade_date is None or close_price is None or symbol not in symbol_meta or priority is None:
                continue

            row_key = (symbol, trade_date)
            current = best_futures_by_key.get(row_key)
            if current is None or priority < current["source_priority"]:
                best_futures_by_key[row_key] = {
                    "trade_date": trade_date,
                    "symbol": symbol,
                    "close_price": float(close_price),
                    "source_priority": priority,
                }

        basis_rows_by_key: dict[tuple[str, object], dict] = {}
        for row in sorted(best_futures_by_key.values(), key=lambda item: (item["trade_date"], item["symbol"])):
            trade_date = row.get("trade_date")
            symbol = str(row.get("symbol", "")).strip().upper()
            close_price = row.get("close_price")
            if trade_date is None or close_price is None or symbol not in symbol_meta:
                continue

            index_name, basis_key = symbol_meta[symbol]
            row_key = (index_name, trade_date)
            target = basis_rows_by_key.setdefault(
                row_key,
                {
                    "trade_date": trade_date,
                    "index_name": index_name,
                    "main_basis": None,
                    "month_basis": None,
                },
            )
            spot_close = spot_close_by_key.get((index_name, trade_date))
            if spot_close is None:
                target[basis_key] = None
                continue
            target[basis_key] = float(close_price) - float(spot_close)

        return sorted(
            basis_rows_by_key.values(),
            key=lambda item: (str(item["index_name"]), item["trade_date"]),
        )

    def _latest_cffex_trade_date(self) -> date | None:
        sql = text(
            f"SELECT MAX(`{settings.cffex_trade_date_column}`) AS trade_date "
            f"FROM `{settings.cffex_member_rankings_table_name}`"
        )
        row = self.db.execute(sql).mappings().first()
        if not row:
            return None
        return row.get("trade_date")

    def _resolve_cffex_trade_date(self, trade_date: date | None) -> date | None:
        if trade_date is None:
            return self._latest_cffex_trade_date()

        sql = text(
            f"SELECT 1 "
            f"FROM `{settings.cffex_member_rankings_table_name}` "
            f"WHERE `{settings.cffex_trade_date_column}` = :trade_date "
            f"LIMIT 1"
        )
        row = self.db.execute(sql, {"trade_date": trade_date}).first()
        if row is None:
            raise ValueError(f"{trade_date.isoformat()} 暂无中金所会员排名数据")
        return trade_date

    def _to_int(self, value: object) -> int:
        if value is None:
            return 0
        return int(round(float(value)))

    def _format_net_position_text(self, net_position: int) -> str:
        if net_position > 0:
            return f"空{abs(net_position):,}手"
        if net_position < 0:
            return f"多{abs(net_position):,}手"
        return "持平"

    def _net_position_action(self, net_position: int) -> str:
        if net_position > 0:
            return "加仓"
        if net_position < 0:
            return "减仓"
        return "持平"

    def _build_net_position_table(self, trade_date: date | None, member_label: str, sums_by_code: dict[str, dict]) -> dict:
        rows: list[dict] = []
        total_net_position = 0
        for item in CFFEX_PRODUCT_INDEX_MAP:
            product_code = item["product_code"]
            data = sums_by_code.get(product_code, {})
            short_position = self._to_int(data.get("short_position"))
            long_position = self._to_int(data.get("long_position"))
            net_position = short_position - long_position
            total_net_position += net_position
            rows.append(
                {
                    "product_code": product_code,
                    "index_name": item["index_name"],
                    "short_position": short_position,
                    "long_position": long_position,
                    "net_position": net_position,
                    "net_position_text": self._format_net_position_text(net_position),
                    "action": self._net_position_action(net_position),
                }
            )

        trade_date_text = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date or "--")
        total_text = self._format_net_position_text(total_net_position)
        return {
            "member_label": member_label,
            "trade_date": trade_date,
            "title": f"{trade_date_text} {member_label}净多空：{total_text}",
            "total_net_position": total_net_position,
            "total_net_position_text": total_text,
            "rows": rows,
        }

    def _query_member_position_sums(self, trade_date: date | None, member_name: str) -> dict[str, dict]:
        if trade_date is None:
            return {}

        resolved_member_name = self._resolve_member_name_for_trade_date(member_name, trade_date)
        product_codes_sql = ", ".join([f"'{item['product_code']}'" for item in CFFEX_PRODUCT_INDEX_MAP])
        sql = text(
            f"SELECT "
            f"`{settings.cffex_product_code_column}` AS product_code, "
            f"SUM(CASE "
            f"WHEN `{settings.cffex_short_member_column}` = :member_name "
            f"THEN COALESCE(`{settings.cffex_short_change_value_column}`, 0) "
            f"ELSE 0 END) AS short_position, "
            f"SUM(CASE "
            f"WHEN `{settings.cffex_long_member_column}` = :member_name "
            f"THEN COALESCE(`{settings.cffex_long_change_value_column}`, 0) "
            f"ELSE 0 END) AS long_position "
            f"FROM `{settings.cffex_member_rankings_table_name}` "
            f"WHERE `{settings.cffex_trade_date_column}` = :trade_date "
            f"AND `{settings.cffex_product_code_column}` IN ({product_codes_sql}) "
            f"GROUP BY `{settings.cffex_product_code_column}`"
        )
        rows = self.db.execute(
            sql,
            {"trade_date": trade_date, "member_name": resolved_member_name},
        ).mappings().all()
        return {
            str(row["product_code"]): {
                "short_position": row.get("short_position"),
                "long_position": row.get("long_position"),
            }
            for row in rows
        }

    def _query_top20_position_sums(self, trade_date: date | None) -> dict[str, dict]:
        if trade_date is None:
            return {}

        product_codes_sql = ", ".join([f"'{item['product_code']}'" for item in CFFEX_PRODUCT_INDEX_MAP])
        sql = text(
            f"SELECT "
            f"`{settings.cffex_product_code_column}` AS product_code, "
            f"SUM(COALESCE(`{settings.cffex_short_change_value_column}`, 0)) AS short_position, "
            f"SUM(COALESCE(`{settings.cffex_long_change_value_column}`, 0)) AS long_position "
            f"FROM `{settings.cffex_member_rankings_table_name}` "
            f"WHERE `{settings.cffex_trade_date_column}` = :trade_date "
            f"AND `{settings.cffex_product_code_column}` IN ({product_codes_sql}) "
            f"AND `{settings.cffex_rank_no_column}` <= 20 "
            f"AND `{settings.cffex_volume_member_column}` IS NOT NULL "
            f"GROUP BY `{settings.cffex_product_code_column}`"
        )
        rows = self.db.execute(sql, {"trade_date": trade_date}).mappings().all()
        return {
            str(row["product_code"]): {
                "short_position": row.get("short_position"),
                "long_position": row.get("long_position"),
            }
            for row in rows
        }

    def get_cffex_net_position_tables(self, trade_date: date | None = None) -> dict:
        cache_key = f"{CFFEX_NET_POSITION_TABLES_CACHE_KEY_PREFIX}:{trade_date.isoformat() if trade_date else 'latest'}"
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, dict):
            return cached
        trade_date = self._resolve_cffex_trade_date(trade_date)
        citic_customer = self._build_net_position_table(
            trade_date=trade_date,
            member_label=self._display_member_label_for_trade_date(CITIC_CUSTOMER_MEMBER_NAME, trade_date),
            sums_by_code=self._query_member_position_sums(trade_date, CITIC_CUSTOMER_MEMBER_NAME),
        )
        top20_institutions = self._build_net_position_table(
            trade_date=trade_date,
            member_label="前20机构",
            sums_by_code=self._query_top20_position_sums(trade_date),
        )
        result = {
            "citic_customer": citic_customer,
            "top20_institutions": top20_institutions,
        }
        self._cache_set_json(cache_key, result)
        return result

    def _cffex_product_codes_sql(self) -> str:
        return ", ".join([f"'{item['product_code']}'" for item in CFFEX_PRODUCT_INDEX_MAP])

    def _resolve_member_name_for_trade_date(self, member_name: str, trade_date: date | None) -> str:
        if member_name != CITIC_CUSTOMER_MEMBER_NAME or trade_date is None:
            return member_name
        if trade_date >= CITIC_CUSTOMER_MEMBER_CURRENT_START_DATE:
            return CITIC_CUSTOMER_MEMBER_NAME
        if trade_date >= CITIC_CUSTOMER_MEMBER_BROKER_START_DATE:
            return CITIC_CUSTOMER_MEMBER_NAME_BROKER
        return CITIC_CUSTOMER_MEMBER_NAME_LEGACY

    def _display_member_label_for_trade_date(self, member_name: str, trade_date: date | None) -> str:
        return self._resolve_member_name_for_trade_date(member_name, trade_date)

    def _member_match_sql(self, member_column: str, trade_date_column_sql: str, member_name: str) -> str:
        quoted_member_column = f"`{member_column}`"
        if member_name != CITIC_CUSTOMER_MEMBER_NAME:
            return f"{quoted_member_column} = :member_name"

        return (
            f"(({trade_date_column_sql} < :citic_member_broker_start_date "
            f"AND {quoted_member_column} = :citic_member_name_legacy) "
            f"OR ({trade_date_column_sql} >= :citic_member_broker_start_date "
            f"AND {trade_date_column_sql} < :citic_member_current_start_date "
            f"AND {quoted_member_column} = :citic_member_name_broker) "
            f"OR ({trade_date_column_sql} >= :citic_member_current_start_date "
            f"AND {quoted_member_column} = :citic_member_name_current))"
        )

    def _member_match_params(self, member_name: str) -> dict[str, object]:
        if member_name != CITIC_CUSTOMER_MEMBER_NAME:
            return {"member_name": member_name}
        return {
            "citic_member_broker_start_date": CITIC_CUSTOMER_MEMBER_BROKER_START_DATE,
            "citic_member_current_start_date": CITIC_CUSTOMER_MEMBER_CURRENT_START_DATE,
            "citic_member_name_legacy": CITIC_CUSTOMER_MEMBER_NAME_LEGACY,
            "citic_member_name_broker": CITIC_CUSTOMER_MEMBER_NAME_BROKER,
            "citic_member_name_current": CITIC_CUSTOMER_MEMBER_NAME,
        }

    def _query_member_open_interest_series_rows(
        self,
        member_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        product_codes_sql = self._cffex_product_codes_sql()
        trade_date_column_sql = f"`{settings.cffex_trade_date_column}`"
        short_member_match_sql = self._member_match_sql(
            settings.cffex_short_member_column,
            trade_date_column_sql,
            member_name,
        )
        long_member_match_sql = self._member_match_sql(
            settings.cffex_long_member_column,
            trade_date_column_sql,
            member_name,
        )
        params = self._member_match_params(member_name)
        date_filter_sql = ""
        if start_date:
            params["start_date"] = start_date
            date_filter_sql += f" AND {trade_date_column_sql} >= :start_date"
        if end_date:
            params["end_date"] = end_date
            date_filter_sql += f" AND {trade_date_column_sql} <= :end_date"
        sql = text(
            f"SELECT "
            f"{trade_date_column_sql} AS trade_date, "
            f"`{settings.cffex_product_code_column}` AS product_code, "
            f"SUM(CASE "
            f"WHEN {short_member_match_sql} "
            f"THEN COALESCE(`{settings.cffex_short_open_interest_column}`, 0) "
            f"ELSE 0 END) AS short_position, "
            f"SUM(CASE "
            f"WHEN {long_member_match_sql} "
            f"THEN COALESCE(`{settings.cffex_long_open_interest_column}`, 0) "
            f"ELSE 0 END) AS long_position "
            f"FROM `{settings.cffex_member_rankings_table_name}` "
            f"WHERE `{settings.cffex_product_code_column}` IN ({product_codes_sql}) "
            f"{date_filter_sql} "
            f"GROUP BY `{settings.cffex_trade_date_column}`, `{settings.cffex_product_code_column}` "
            f"ORDER BY `{settings.cffex_trade_date_column}` ASC, `{settings.cffex_product_code_column}` ASC"
        )
        return [dict(row) for row in self.db.execute(sql, params).mappings().all()]

    def _query_top20_open_interest_series_rows(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        product_codes_sql = self._cffex_product_codes_sql()
        params: dict[str, object] = {}
        date_filter_sql = ""
        if start_date:
            params["start_date"] = start_date
            date_filter_sql += f" AND `{settings.cffex_trade_date_column}` >= :start_date"
        if end_date:
            params["end_date"] = end_date
            date_filter_sql += f" AND `{settings.cffex_trade_date_column}` <= :end_date"
        sql = text(
            f"SELECT "
            f"`{settings.cffex_trade_date_column}` AS trade_date, "
            f"`{settings.cffex_product_code_column}` AS product_code, "
            f"SUM(COALESCE(`{settings.cffex_short_open_interest_column}`, 0)) AS short_position, "
            f"SUM(COALESCE(`{settings.cffex_long_open_interest_column}`, 0)) AS long_position "
            f"FROM `{settings.cffex_member_rankings_table_name}` "
            f"WHERE `{settings.cffex_product_code_column}` IN ({product_codes_sql}) "
            f"AND `{settings.cffex_rank_no_column}` <= 20 "
            f"AND `{settings.cffex_volume_member_column}` IS NOT NULL "
            f"{date_filter_sql} "
            f"GROUP BY `{settings.cffex_trade_date_column}`, `{settings.cffex_product_code_column}` "
            f"ORDER BY `{settings.cffex_trade_date_column}` ASC, `{settings.cffex_product_code_column}` ASC"
        )
        return [dict(row) for row in self.db.execute(sql, params).mappings().all()]

    def _build_net_position_series(self, member_label: str, rows: list[dict]) -> dict:
        series: dict[str, list[dict]] = {key: [] for key in CFFEX_SERIES_KEYS}
        overall_by_date: dict[date, int] = {}

        for row in rows:
            trade_date = row.get("trade_date")
            product_code = str(row.get("product_code", "")).strip().upper()
            if trade_date is None or product_code not in series or product_code == "OVERALL":
                continue

            short_position = self._to_int(row.get("short_position"))
            long_position = self._to_int(row.get("long_position"))
            net_position = short_position - long_position
            series[product_code].append(
                {
                    "trade_date": trade_date,
                    "net_position": net_position,
                }
            )
            overall_by_date[trade_date] = overall_by_date.get(trade_date, 0) + net_position

        series["OVERALL"] = [
            {"trade_date": trade_date, "net_position": net_position}
            for trade_date, net_position in sorted(overall_by_date.items(), key=lambda item: item[0])
        ]
        for key in CFFEX_SERIES_KEYS:
            if key == "OVERALL":
                continue
            series[key] = sorted(series[key], key=lambda item: item["trade_date"])

        return {
            "member_label": member_label,
            "series": series,
        }

    def get_cffex_net_position_series(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        cache_key = (
            f"{CFFEX_NET_POSITION_SERIES_CACHE_KEY_PREFIX}:"
            f"{start_date.isoformat() if start_date else 'none'}:"
            f"{end_date.isoformat() if end_date else 'none'}"
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, dict):
            return cached
        result = {
            "citic_customer": self._build_net_position_series(
                member_label=CITIC_CUSTOMER_MEMBER_NAME,
                rows=self._query_member_open_interest_series_rows(
                    CITIC_CUSTOMER_MEMBER_NAME,
                    start_date=start_date,
                    end_date=end_date,
                ),
            ),
            "top20_institutions": self._build_net_position_series(
                member_label="前20机构",
                rows=self._query_top20_open_interest_series_rows(
                    start_date=start_date,
                    end_date=end_date,
                ),
            ),
        }
        self._cache_set_json(cache_key, result)
        return result

    def _normalize_rows(
        self,
        rows: list,
        numeric_fields: list[str],
        alias_renames: dict[str, str] | None = None,
    ) -> list[dict]:
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            if alias_renames:
                for source, target in alias_renames.items():
                    item[target] = item.pop(source, 0)
            for field in numeric_fields:
                if item.get(field) is None:
                    item[field] = 0
            result.append(item)
        return result

    def list_daily_kline(
        self,
        ts_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        stock_code = self._resolve_stock_code(ts_code)
        if not stock_code:
            return []
        table_columns = self.get_table_columns()
        turnover_rate_expr = (
            f"COALESCE(`{settings.stock_turnover_rate_column}`, 0)"
            if settings.stock_turnover_rate_column in table_columns
            else "0"
        )

        params: dict[str, object] = {
            "stock_code": stock_code,
            "hist_source": settings.stock_hist_source_value,
            "spot_source": settings.stock_spot_source_value,
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        date_filter_sql = ""
        if start_date:
            date_filter_sql += f" AND `{settings.stock_date_column}` >= :start_date"
        if end_date:
            date_filter_sql += f" AND `{settings.stock_date_column}` <= :end_date"

        hist_sql = text(
            f"SELECT "
            f"`{settings.stock_date_column}` AS trade_date, "
            f"`{settings.stock_open_column}` AS open, "
            f"`{settings.stock_high_column}` AS high, "
            f"`{settings.stock_low_column}` AS low, "
            f"`{settings.stock_close_column}` AS close, "
            f"COALESCE(`{settings.stock_pre_close_column}`, 0) AS pre_close, "
            f"COALESCE(`{settings.stock_change_column}`, 0) AS change_value, "
            f"COALESCE(`{settings.stock_pct_chg_column}`, 0) AS pct_chg, "
            f"COALESCE(`{settings.stock_vol_column}`, 0) AS vol, "
            f"COALESCE(`{settings.stock_amount_column}`, 0) AS amount, "
            f"{turnover_rate_expr} AS turnover_rate, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{settings.stock_table_name}` "
            f"WHERE `{settings.stock_code_column}` = :stock_code "
            f"AND `{settings.stock_data_source_column}` = :hist_source"
            f"{date_filter_sql} "
            f"ORDER BY `{settings.stock_date_column}` ASC"
        )
        hist_rows = [dict(row) for row in self.db.execute(hist_sql, params).mappings().all()]

        rows_by_date = {row["trade_date"]: row for row in hist_rows if row.get("trade_date") is not None}

        spot_sql = text(
            f"SELECT "
            f"`{settings.stock_date_column}` AS trade_date, "
            f"`{settings.stock_open_column}` AS open, "
            f"`{settings.stock_high_column}` AS high, "
            f"`{settings.stock_low_column}` AS low, "
            f"COALESCE(`{settings.stock_latest_price_column}`, `{settings.stock_close_column}`) AS close, "
            f"COALESCE(`{settings.stock_pre_close_column}`, 0) AS pre_close, "
            f"COALESCE(`{settings.stock_change_column}`, 0) AS change_value, "
            f"COALESCE(`{settings.stock_pct_chg_column}`, 0) AS pct_chg, "
            f"COALESCE(`{settings.stock_vol_column}`, 0) AS vol, "
            f"COALESCE(`{settings.stock_amount_column}`, 0) AS amount, "
            f"{turnover_rate_expr} AS turnover_rate, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{settings.stock_table_name}` "
            f"WHERE `{settings.stock_code_column}` = :stock_code "
            f"AND `{settings.stock_data_source_column}` = :spot_source"
            f"{date_filter_sql} "
            f"ORDER BY `{settings.stock_date_column}` ASC"
        )
        spot_rows = self.db.execute(spot_sql, params).mappings().all()
        for spot_row in spot_rows:
            if spot_row.get("trade_date") is not None:
                rows_by_date[spot_row["trade_date"]] = dict(spot_row)

        rows = [rows_by_date[key] for key in sorted(rows_by_date.keys())]
        numeric_fields = [
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "turnover_rate",
            "pe_ttm",
            "pb",
            "total_market_value",
            "circulating_market_value",
        ]
        return self._normalize_rows(rows, numeric_fields, {"change_value": "change"})

    def list_hfq_daily_kline(
        self,
        ts_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        stock_code = self._resolve_stock_code(ts_code)
        if not stock_code:
            return []

        sql = (
            f"SELECT "
            f"`{settings.stock_hfq_date_column}` AS trade_date, "
            f"`{settings.stock_hfq_open_column}` AS open, "
            f"`{settings.stock_hfq_high_column}` AS high, "
            f"`{settings.stock_hfq_low_column}` AS low, "
            f"`{settings.stock_hfq_close_column}` AS close, "
            f"CASE "
            f"WHEN `{settings.stock_hfq_change_column}` IS NULL THEN 0 "
            f"ELSE COALESCE(`{settings.stock_hfq_close_column}`, 0) - COALESCE(`{settings.stock_hfq_change_column}`, 0) "
            f"END AS pre_close, "
            f"COALESCE(`{settings.stock_hfq_change_column}`, 0) AS change_value, "
            f"COALESCE(`{settings.stock_hfq_pct_chg_column}`, 0) AS pct_chg, "
            f"COALESCE(`{settings.stock_hfq_vol_column}`, 0) AS vol, "
            f"COALESCE(`{settings.stock_hfq_amount_column}`, 0) AS amount, "
            f"COALESCE(`{settings.stock_hfq_turnover_rate_column}`, 0) AS turnover_rate, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{settings.stock_hfq_table_name}` "
            f"WHERE `{settings.stock_hfq_code_column}` = :stock_code"
        )
        params: dict[str, object] = {"stock_code": stock_code}
        if start_date:
            sql += f" AND `{settings.stock_hfq_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.stock_hfq_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.stock_hfq_date_column}` ASC"

        rows = self.db.execute(text(sql), params).mappings().all()
        numeric_fields = [
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "turnover_rate",
            "pe_ttm",
            "pb",
            "total_market_value",
            "circulating_market_value",
        ]
        return self._normalize_rows(rows, numeric_fields, {"change_value": "change"})

    def list_etf_daily_kline(
        self,
        etf_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        normalized_code = str(etf_code or "").strip()
        if not normalized_code:
            return []

        params: dict[str, object] = {
            "etf_code": normalized_code,
            "hist_source": settings.etf_daily_hist_source_value,
            "spot_source": settings.etf_daily_spot_source_value,
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        date_filter_sql = ""
        if start_date:
            date_filter_sql += f" AND `{settings.etf_daily_date_column}` >= :start_date"
        if end_date:
            date_filter_sql += f" AND `{settings.etf_daily_date_column}` <= :end_date"

        hist_sql = text(
            f"SELECT "
            f"`{settings.etf_daily_date_column}` AS trade_date, "
            f"`{settings.etf_daily_open_column}` AS open, "
            f"`{settings.etf_daily_high_column}` AS high, "
            f"`{settings.etf_daily_low_column}` AS low, "
            f"`{settings.etf_daily_close_column}` AS close "
            f"FROM `{settings.etf_daily_table_name}` "
            f"WHERE `{settings.etf_daily_code_column}` = :etf_code "
            f"AND `{settings.etf_daily_data_source_column}` = :hist_source"
            f"{date_filter_sql} "
            f"ORDER BY `{settings.etf_daily_date_column}` ASC"
        )
        rows_by_date = {
            row["trade_date"]: dict(row)
            for row in self.db.execute(hist_sql, params).mappings().all()
            if row.get("trade_date") is not None
        }

        spot_sql = text(
            f"SELECT "
            f"`{settings.etf_daily_date_column}` AS trade_date, "
            f"`{settings.etf_daily_open_column}` AS open, "
            f"`{settings.etf_daily_high_column}` AS high, "
            f"`{settings.etf_daily_low_column}` AS low, "
            f"`{settings.etf_daily_close_column}` AS close "
            f"FROM `{settings.etf_daily_table_name}` "
            f"WHERE `{settings.etf_daily_code_column}` = :etf_code "
            f"AND `{settings.etf_daily_data_source_column}` = :spot_source"
            f"{date_filter_sql} "
            f"ORDER BY `{settings.etf_daily_date_column}` ASC"
        )
        for row in self.db.execute(spot_sql, params).mappings().all():
            if row.get("trade_date") is not None:
                rows_by_date[row["trade_date"]] = dict(row)

        ordered_rows = [rows_by_date[key] for key in sorted(rows_by_date.keys())]
        result: list[dict] = []
        previous_close: float | None = None
        for row in ordered_rows:
            open_price = _to_float(row.get("open"))
            high_price = _to_float(row.get("high"))
            low_price = _to_float(row.get("low"))
            close_price = _to_float(row.get("close"))
            trade_date = row.get("trade_date")
            if trade_date is None or open_price is None or high_price is None or low_price is None or close_price is None:
                continue
            pre_close = previous_close if previous_close is not None else close_price
            change_value = close_price - pre_close
            pct_chg = (change_value / pre_close * 100) if pre_close else 0.0
            result.append(
                {
                    "trade_date": trade_date,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "pre_close": pre_close,
                    "change": change_value,
                    "pct_chg": pct_chg,
                    "vol": 0.0,
                    "amount": 0.0,
                    "turnover_rate": 0.0,
                    "pe_ttm": 0.0,
                    "pb": 0.0,
                    "total_market_value": 0.0,
                    "circulating_market_value": 0.0,
                }
            )
            previous_close = close_price

        return result

    def list_index_daily_kline(
        self,
        index_code: str,
        market: str | None = "cn",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        config = self._get_index_market_config(market)
        normalized_index_code = str(index_code).strip()
        if config["market"] == "cn" and normalized_index_code.lower() == BEIJING50_INDEX_OPTION["code"].lower():
            normalized_index_code = BEIJING50_INDEX_OPTION["code"]
        cache_key = (
            f"{INDEX_KLINE_CACHE_KEY_PREFIX}:{config['market']}:{normalized_index_code}:"
            f"{start_date.isoformat() if start_date else 'none'}:{end_date.isoformat() if end_date else 'none'}"
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached
        sql = (
            f"SELECT "
            f"`{config['daily_date_column']}` AS trade_date, "
            f"`{config['daily_open_column']}` AS open, "
            f"`{config['daily_high_column']}` AS high, "
            f"`{config['daily_low_column']}` AS low, "
            f"`{config['daily_close_column']}` AS close, "
            f"0 AS pre_close, "
            f"`{config['daily_change_column']}` AS change_value, "
            f"`{config['daily_pct_chg_column']}` AS pct_chg, "
            f"`{config['daily_vol_column']}` AS vol, "
            f"`{config['daily_amount_column']}` AS amount, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{config['daily_table']}` "
            f"WHERE `{config['daily_code_column']}` = :index_code"
        )
        params: dict[str, object] = {"index_code": normalized_index_code}
        if start_date:
            sql += f" AND `{config['daily_date_column']}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{config['daily_date_column']}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{config['daily_date_column']}` ASC"

        rows = self.db.execute(text(sql), params).mappings().all()
        numeric_fields = [
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "pe_ttm",
            "pb",
            "total_market_value",
            "circulating_market_value",
        ]
        result = self._normalize_rows(rows, numeric_fields, {"change_value": "change"})
        self._cache_set_json(cache_key, result)
        return result

    def list_index_qvix_daily_data(
        self,
        qvix_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        normalized_code = str(qvix_code or "").strip()
        if not normalized_code:
            return []
        bind = self.db.get_bind()
        if bind is None or not inspect(bind).has_table(settings.index_qvix_daily_table_name):
            return []

        sql = (
            f"SELECT "
            f"`{settings.index_qvix_daily_date_column}` AS trade_date, "
            f"`{settings.index_qvix_daily_open_column}` AS open_price, "
            f"`{settings.index_qvix_daily_high_column}` AS high_price, "
            f"`{settings.index_qvix_daily_low_column}` AS low_price, "
            f"`{settings.index_qvix_daily_close_column}` AS close_price "
            f"FROM `{settings.index_qvix_daily_table_name}` "
            f"WHERE `{settings.index_qvix_daily_code_column}` = :index_code"
        )
        params: dict[str, object] = {"index_code": normalized_code}
        if start_date:
            sql += f" AND `{settings.index_qvix_daily_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_qvix_daily_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_qvix_daily_date_column}` ASC"

        return [
            {
                "trade_date": row.get("trade_date"),
                "open_price": _to_float(row.get("open_price")),
                "high_price": _to_float(row.get("high_price")),
                "low_price": _to_float(row.get("low_price")),
                "close_price": _to_float(row.get("close_price")),
            }
            for row in self.db.execute(text(sql), params).mappings().all()
            if row.get("trade_date") is not None
        ]

    def list_index_us_vix_daily_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        bind = self.db.get_bind()
        table_name = settings.index_us_vix_daily_table_name
        if bind is None or not inspect(bind).has_table(table_name):
            return []

        sql = (
            f"SELECT "
            f"`{settings.index_us_vix_daily_date_column}` AS trade_date, "
            f"`{settings.index_us_vix_daily_open_column}` AS open_value, "
            f"`{settings.index_us_vix_daily_high_column}` AS high_value, "
            f"`{settings.index_us_vix_daily_low_column}` AS low_value, "
            f"`{settings.index_us_vix_daily_close_column}` AS close_value "
            f"FROM `{table_name}` "
            f"WHERE 1 = 1"
        )
        params: dict[str, object] = {}
        if start_date:
            sql += f" AND `{settings.index_us_vix_daily_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_us_vix_daily_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_us_vix_daily_date_column}` ASC"

        return [
            {
                "trade_date": row.get("trade_date"),
                "open_value": _to_float(row.get("open_value")),
                "high_value": _to_float(row.get("high_value")),
                "low_value": _to_float(row.get("low_value")),
                "close_value": _to_float(row.get("close_value")),
            }
            for row in self.db.execute(text(sql), params).mappings().all()
            if row.get("trade_date") is not None
        ]

    def list_index_us_fear_greed_daily_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        bind = self.db.get_bind()
        table_name = settings.index_us_fear_greed_daily_table_name
        if bind is None or not inspect(bind).has_table(table_name):
            return []

        sql = (
            f"SELECT "
            f"`{settings.index_us_fear_greed_daily_date_column}` AS trade_date, "
            f"`{settings.index_us_fear_greed_daily_value_column}` AS fear_greed_value, "
            f"`{settings.index_us_fear_greed_daily_label_column}` AS sentiment_label "
            f"FROM `{table_name}` "
            f"WHERE 1 = 1"
        )
        params: dict[str, object] = {}
        if start_date:
            sql += f" AND `{settings.index_us_fear_greed_daily_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_us_fear_greed_daily_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_us_fear_greed_daily_date_column}` ASC"

        return [
            {
                "trade_date": row.get("trade_date"),
                "fear_greed_value": _to_float(row.get("fear_greed_value")),
                "sentiment_label": str(row.get("sentiment_label") or "").strip(),
            }
            for row in self.db.execute(text(sql), params).mappings().all()
            if row.get("trade_date") is not None
        ]

    def list_index_us_hedge_proxy_data(
        self,
        contract_scope: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        normalized_scope = str(contract_scope or "").strip().upper()
        if not normalized_scope:
            return []
        bind = self.db.get_bind()
        table_name = settings.index_us_hedge_proxy_table_name
        if bind is None or not inspect(bind).has_table(table_name):
            return []

        sql = (
            f"SELECT "
            f"`{settings.index_us_hedge_proxy_report_date_column}` AS report_date, "
            f"`{settings.index_us_hedge_proxy_scope_column}` AS contract_scope, "
            f"`{settings.index_us_hedge_proxy_long_column}` AS long_value, "
            f"`{settings.index_us_hedge_proxy_short_column}` AS short_value, "
            f"`{settings.index_us_hedge_proxy_ratio_column}` AS ratio_value, "
            f"`{settings.index_us_hedge_proxy_release_date_column}` AS release_date "
            f"FROM `{table_name}` "
            f"WHERE `{settings.index_us_hedge_proxy_scope_column}` = :contract_scope"
        )
        params: dict[str, object] = {"contract_scope": normalized_scope}
        if start_date:
            sql += f" AND `{settings.index_us_hedge_proxy_release_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_us_hedge_proxy_release_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_us_hedge_proxy_release_date_column}` ASC"

        return [
            {
                "report_date": row.get("report_date"),
                "contract_scope": str(row.get("contract_scope") or "").strip().upper(),
                "long_value": _to_float(row.get("long_value")),
                "short_value": _to_float(row.get("short_value")),
                "ratio_value": _to_float(row.get("ratio_value")),
                "release_date": row.get("release_date"),
            }
            for row in self.db.execute(text(sql), params).mappings().all()
            if row.get("release_date") is not None
        ]

    def list_index_us_put_call_ratio_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        bind = self.db.get_bind()
        table_name = settings.index_us_put_call_table_name
        if bind is None or not inspect(bind).has_table(table_name):
            return []

        sql = (
            f"SELECT "
            f"`{settings.index_us_put_call_date_column}` AS trade_date, "
            f"`{settings.index_us_put_call_total_column}` AS total_put_call_ratio, "
            f"`{settings.index_us_put_call_index_column}` AS index_put_call_ratio, "
            f"`{settings.index_us_put_call_equity_column}` AS equity_put_call_ratio, "
            f"`{settings.index_us_put_call_etf_column}` AS etf_put_call_ratio "
            f"FROM `{table_name}` "
            f"WHERE 1 = 1"
        )
        params: dict[str, object] = {}
        if start_date:
            sql += f" AND `{settings.index_us_put_call_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_us_put_call_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_us_put_call_date_column}` ASC"

        return [
            {
                "trade_date": row.get("trade_date"),
                "total_put_call_ratio": _to_float(row.get("total_put_call_ratio")),
                "index_put_call_ratio": _to_float(row.get("index_put_call_ratio")),
                "equity_put_call_ratio": _to_float(row.get("equity_put_call_ratio")),
                "etf_put_call_ratio": _to_float(row.get("etf_put_call_ratio")),
            }
            for row in self.db.execute(text(sql), params).mappings().all()
            if row.get("trade_date") is not None
        ]

    def list_index_us_treasury_yield_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        bind = self.db.get_bind()
        table_name = settings.index_us_treasury_yield_table_name
        if bind is None or not inspect(bind).has_table(table_name):
            return []

        sql = (
            f"SELECT "
            f"`{settings.index_us_treasury_yield_date_column}` AS trade_date, "
            f"`{settings.index_us_treasury_yield_3m_column}` AS yield_3m, "
            f"`{settings.index_us_treasury_yield_2y_column}` AS yield_2y, "
            f"`{settings.index_us_treasury_yield_10y_column}` AS yield_10y, "
            f"`{settings.index_us_treasury_yield_spread_10y_2y_column}` AS spread_10y_2y, "
            f"`{settings.index_us_treasury_yield_spread_10y_3m_column}` AS spread_10y_3m "
            f"FROM `{table_name}` "
            f"WHERE 1 = 1"
        )
        params: dict[str, object] = {}
        if start_date:
            sql += f" AND `{settings.index_us_treasury_yield_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_us_treasury_yield_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_us_treasury_yield_date_column}` ASC"

        return [
            {
                "trade_date": row.get("trade_date"),
                "yield_3m": _to_float(row.get("yield_3m")),
                "yield_2y": _to_float(row.get("yield_2y")),
                "yield_10y": _to_float(row.get("yield_10y")),
                "spread_10y_2y": _to_float(row.get("spread_10y_2y")),
                "spread_10y_3m": _to_float(row.get("spread_10y_3m")),
            }
            for row in self.db.execute(text(sql), params).mappings().all()
            if row.get("trade_date") is not None
        ]

    def list_index_us_credit_spread_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        bind = self.db.get_bind()
        table_name = settings.index_us_credit_spread_table_name
        if bind is None or not inspect(bind).has_table(table_name):
            return []

        sql = (
            f"SELECT "
            f"`{settings.index_us_credit_spread_date_column}` AS trade_date, "
            f"`{settings.index_us_credit_spread_hy_oas_column}` AS high_yield_oas "
            f"FROM `{table_name}` "
            f"WHERE 1 = 1"
        )
        params: dict[str, object] = {}
        if start_date:
            sql += f" AND `{settings.index_us_credit_spread_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_us_credit_spread_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_us_credit_spread_date_column}` ASC"

        return [
            {
                "trade_date": row.get("trade_date"),
                "high_yield_oas": _to_float(row.get("high_yield_oas")),
            }
            for row in self.db.execute(text(sql), params).mappings().all()
            if row.get("trade_date") is not None
        ]

    def list_forex_daily_kline(
        self,
        symbol_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        cache_key = (
            f"{FOREX_KLINE_CACHE_KEY_PREFIX}:{symbol_code}:"
            f"{start_date.isoformat() if start_date else 'none'}:{end_date.isoformat() if end_date else 'none'}"
        )
        cached = self._cache_get_json(cache_key)
        if isinstance(cached, list):
            return cached
        sql = (
            f"SELECT "
            f"d.`{settings.forex_daily_date_column}` AS trade_date, "
            f"d.`{settings.forex_daily_open_column}` AS open, "
            f"d.`{settings.forex_daily_high_column}` AS high, "
            f"d.`{settings.forex_daily_low_column}` AS low, "
            f"d.`{settings.forex_daily_close_column}` AS close, "
            f"0 AS pre_close, "
            f"0 AS change_value, "
            f"COALESCE(d.`amplitude`, 0) AS pct_chg, "
            f"0 AS vol, "
            f"0 AS amount, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{settings.forex_daily_table_name}` d "
            f"LEFT JOIN `{settings.forex_basic_info_table_name}` b "
            f"ON b.`{settings.forex_basic_info_code_column}` = d.`{settings.forex_daily_code_column}` "
            f"WHERE ("
            f"d.`{settings.forex_daily_code_column}` = :symbol_key "
            f"OR d.`{settings.forex_daily_name_column}` = :symbol_key "
            f"OR b.`{settings.forex_basic_info_name_column}` = :symbol_key"
            f")"
        )
        params: dict[str, object] = {"symbol_key": symbol_code}
        if start_date:
            sql += f" AND d.`{settings.forex_daily_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND d.`{settings.forex_daily_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY d.`{settings.forex_daily_date_column}` ASC"

        rows = self.db.execute(text(sql), params).mappings().all()
        numeric_fields = [
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "pe_ttm",
            "pb",
            "total_market_value",
            "circulating_market_value",
        ]
        result = self._normalize_rows(rows, numeric_fields, {"change_value": "change"})
        self._cache_set_json(cache_key, result)
        return result

