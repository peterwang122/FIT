import json
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
]

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


class StockService:
    def __init__(self, db: Session):
        self.db = db

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
            f"`{settings.stock_basic_info_name_column}` AS stock_name "
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

    def list_index_options(self) -> list[dict]:
        sql = text(
            f"SELECT `{settings.index_basic_info_code_column}` AS code, "
            f"`{settings.index_basic_info_name_column}` AS name "
            f"FROM `{settings.index_basic_info_table_name}`"
        )
        items = [dict(row) for row in self.db.execute(sql).mappings().all()]
        return self._filter_named_options(items, INDEX_DISPLAY_ORDER, "code", "name")

    def list_forex_options(self) -> list[dict]:
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
        return self._filter_named_options(items, FOREX_DISPLAY_ORDER, "code", "name")

    def list_excel_index_emotions(self) -> list[dict]:
        sql = text(
            f"SELECT "
            f"`{settings.excel_index_emotion_date_column}` AS emotion_date, "
            f"`{settings.excel_index_emotion_name_column}` AS index_name, "
            f"`{settings.excel_index_emotion_value_column}` AS emotion_value "
            f"FROM `{settings.excel_index_emotion_table_name}` "
            f"ORDER BY `{settings.excel_index_emotion_date_column}` ASC"
        )
        allowed_names = set(EXCEL_INDEX_EMOTION_ORDER)
        rows = self.db.execute(sql).mappings().all()
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
        return {
            "citic_customer": citic_customer,
            "top20_institutions": top20_institutions,
        }

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

    def _query_member_open_interest_series_rows(self, member_name: str) -> list[dict]:
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
            f"GROUP BY `{settings.cffex_trade_date_column}`, `{settings.cffex_product_code_column}` "
            f"ORDER BY `{settings.cffex_trade_date_column}` ASC, `{settings.cffex_product_code_column}` ASC"
        )
        return [dict(row) for row in self.db.execute(sql, self._member_match_params(member_name)).mappings().all()]

    def _query_top20_open_interest_series_rows(self) -> list[dict]:
        product_codes_sql = self._cffex_product_codes_sql()
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
            f"GROUP BY `{settings.cffex_trade_date_column}`, `{settings.cffex_product_code_column}` "
            f"ORDER BY `{settings.cffex_trade_date_column}` ASC, `{settings.cffex_product_code_column}` ASC"
        )
        return [dict(row) for row in self.db.execute(sql).mappings().all()]

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

    def get_cffex_net_position_series(self) -> dict:
        return {
            "citic_customer": self._build_net_position_series(
                member_label=CITIC_CUSTOMER_MEMBER_NAME,
                rows=self._query_member_open_interest_series_rows(CITIC_CUSTOMER_MEMBER_NAME),
            ),
            "top20_institutions": self._build_net_position_series(
                member_label="前20机构",
                rows=self._query_top20_open_interest_series_rows(),
            ),
        }

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

        latest_spot_date_sql = text(
            f"SELECT MAX(`{settings.stock_date_column}`) AS trade_date "
            f"FROM `{settings.stock_table_name}` "
            f"WHERE `{settings.stock_code_column}` = :stock_code "
            f"AND `{settings.stock_data_source_column}` = :spot_source"
            f"{date_filter_sql}"
        )
        latest_spot_date = self.db.execute(latest_spot_date_sql, params).scalar()

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

        if latest_spot_date is not None:
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
                f"AND `{settings.stock_data_source_column}` = :spot_source "
                f"AND `{settings.stock_date_column}` = :latest_spot_date "
                f"LIMIT 1"
            )
            spot_params = {**params, "latest_spot_date": latest_spot_date}
            spot_row = self.db.execute(spot_sql, spot_params).mappings().first()
            if spot_row:
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

    def list_qfq_daily_kline(
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
            f"`{settings.stock_qfq_date_column}` AS trade_date, "
            f"`{settings.stock_qfq_open_column}` AS open, "
            f"`{settings.stock_qfq_high_column}` AS high, "
            f"`{settings.stock_qfq_low_column}` AS low, "
            f"`{settings.stock_qfq_close_column}` AS close, "
            f"CASE "
            f"WHEN `{settings.stock_qfq_change_column}` IS NULL THEN 0 "
            f"ELSE COALESCE(`{settings.stock_qfq_close_column}`, 0) - COALESCE(`{settings.stock_qfq_change_column}`, 0) "
            f"END AS pre_close, "
            f"COALESCE(`{settings.stock_qfq_change_column}`, 0) AS change_value, "
            f"COALESCE(`{settings.stock_qfq_pct_chg_column}`, 0) AS pct_chg, "
            f"COALESCE(`{settings.stock_qfq_vol_column}`, 0) AS vol, "
            f"COALESCE(`{settings.stock_qfq_amount_column}`, 0) AS amount, "
            f"COALESCE(`{settings.stock_qfq_turnover_rate_column}`, 0) AS turnover_rate, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{settings.stock_qfq_table_name}` "
            f"WHERE `{settings.stock_qfq_code_column}` = :stock_code"
        )
        params: dict[str, object] = {"stock_code": stock_code}
        if start_date:
            sql += f" AND `{settings.stock_qfq_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.stock_qfq_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.stock_qfq_date_column}` ASC"

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

    def list_index_daily_kline(
        self,
        index_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        sql = (
            f"SELECT "
            f"`{settings.index_daily_date_column}` AS trade_date, "
            f"`{settings.index_daily_open_column}` AS open, "
            f"`{settings.index_daily_high_column}` AS high, "
            f"`{settings.index_daily_low_column}` AS low, "
            f"`{settings.index_daily_close_column}` AS close, "
            f"0 AS pre_close, "
            f"`{settings.index_daily_change_column}` AS change_value, "
            f"`{settings.index_daily_pct_chg_column}` AS pct_chg, "
            f"`{settings.index_daily_vol_column}` AS vol, "
            f"`{settings.index_daily_amount_column}` AS amount, "
            f"0 AS pe_ttm, "
            f"0 AS pb, "
            f"0 AS total_market_value, "
            f"0 AS circulating_market_value "
            f"FROM `{settings.index_daily_table_name}` "
            f"WHERE `{settings.index_daily_code_column}` = :index_code"
        )
        params: dict[str, object] = {"index_code": index_code}
        if start_date:
            sql += f" AND `{settings.index_daily_date_column}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{settings.index_daily_date_column}` <= :end_date"
            params["end_date"] = end_date
        sql += f" ORDER BY `{settings.index_daily_date_column}` ASC"

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
        return self._normalize_rows(rows, numeric_fields, {"change_value": "change"})

    def list_forex_daily_kline(
        self,
        symbol_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
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
        return self._normalize_rows(rows, numeric_fields, {"change_value": "change"})
