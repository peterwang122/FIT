import json
from datetime import date

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_client


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
        return {k: v for k, v in self.mapping.items() if v in cols}

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
                    f"SELECT COUNT(DISTINCT `{settings.stock_code_column}`) AS c FROM `{settings.stock_table_name}`"
                )
                symbol_count = int(self.db.execute(symbol_count_query).scalar() or 0)

                sample_query = text(
                    f"SELECT DISTINCT `{settings.stock_code_column}` AS ts_code "
                    f"FROM `{settings.stock_table_name}` ORDER BY `{settings.stock_code_column}` LIMIT 5"
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
            f"SELECT `{settings.stock_basic_info_code_column}` AS ts_code, "
            f"`{settings.stock_basic_info_name_column}` AS stock_name "
            f"FROM `{settings.stock_basic_info_table_name}` "
            f"ORDER BY `{settings.stock_basic_info_code_column}`"
        )
        return [dict(row) for row in self.db.execute(sql).mappings().all()]

    def load_stock_basics_to_cache(self) -> list[dict]:
        items = self._query_stock_basics_from_db()
        redis_client.set(settings.stock_basic_cache_key, json.dumps(items, ensure_ascii=False), ex=settings.stock_basic_cache_ttl_seconds)
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
                if key in str(item.get("ts_code", "")).lower() or key in str(item.get("stock_name", "")).lower()
            ]
        return items[:limit]

    def list_daily_kline(
        self,
        ts_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        mapping = self.available_mapping()
        required = {"ts_code", "trade_date", "open", "high", "low", "close"}
        if not required.issubset(mapping):
            return []

        optional_defaults = {
            "pre_close": 0,
            "change": 0,
            "pct_chg": 0,
            "vol": 0,
            "amount": 0,
            "pe_ttm": 0,
            "pb": 0,
            "total_market_value": 0,
            "circulating_market_value": 0,
        }

        select_parts = [
            f"`{mapping['trade_date']}` AS trade_date",
            f"`{mapping['open']}` AS open",
            f"`{mapping['high']}` AS high",
            f"`{mapping['low']}` AS low",
            f"`{mapping['close']}` AS close",
        ]
        output_alias = {
            "pre_close": "pre_close",
            "change": "change_value",
            "pct_chg": "pct_chg",
            "vol": "vol",
            "amount": "amount",
            "pe_ttm": "pe_ttm",
            "pb": "pb",
            "total_market_value": "total_market_value",
            "circulating_market_value": "circulating_market_value",
        }

        for field, alias in output_alias.items():
            if field in mapping:
                select_parts.append(f"`{mapping[field]}` AS {alias}")
            else:
                select_parts.append(f"{optional_defaults[field]} AS {alias}")

        sql = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM `{settings.stock_table_name}` "
            f"WHERE `{mapping['ts_code']}` = :ts_code"
        )

        params: dict = {"ts_code": ts_code}

        if start_date:
            sql += f" AND `{mapping['trade_date']}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{mapping['trade_date']}` <= :end_date"
            params["end_date"] = end_date

        sql += f" ORDER BY `{mapping['trade_date']}` ASC"

        rows = self.db.execute(text(sql), params).mappings().all()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["change"] = item.pop("change_value", 0)
            result.append(item)
        return result
