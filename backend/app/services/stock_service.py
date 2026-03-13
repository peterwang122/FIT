from datetime import date

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings


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

    def list_symbols(self, limit: int = 200, keyword: str | None = None) -> list[str]:
        cols = self.get_table_columns()
        if settings.stock_code_column not in cols:
            return []

        base_sql = (
            f"SELECT DISTINCT `{settings.stock_code_column}` AS ts_code "
            f"FROM `{settings.stock_table_name}`"
        )
        params: dict = {"limit": limit}

        if keyword:
            base_sql += f" WHERE `{settings.stock_code_column}` LIKE :keyword"
            params["keyword"] = f"%{keyword}%"

        base_sql += f" ORDER BY `{settings.stock_code_column}` LIMIT :limit"

        rows = self.db.execute(text(base_sql), params).mappings().all()
        return [str(row["ts_code"]) for row in rows]

    def list_daily_kline(
        self,
        ts_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 500,
    ) -> list[dict]:
        mapping = self.available_mapping()
        required = {"ts_code", "trade_date", "open", "high", "low", "close"}
        if not required.issubset(mapping):
            return []

        optional_defaults = {"pre_close": 0, "change": 0, "pct_chg": 0, "vol": 0, "amount": 0}

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
        }

        for field in ["pre_close", "change", "pct_chg", "vol", "amount"]:
            alias = output_alias[field]
            if field in mapping:
                select_parts.append(f"`{mapping[field]}` AS {alias}")
            else:
                select_parts.append(f"{optional_defaults[field]} AS {alias}")

        sql = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM `{settings.stock_table_name}` "
            f"WHERE `{mapping['ts_code']}` = :ts_code"
        )

        params: dict = {"ts_code": ts_code, "limit": limit}

        if start_date:
            sql += f" AND `{mapping['trade_date']}` >= :start_date"
            params["start_date"] = start_date
        if end_date:
            sql += f" AND `{mapping['trade_date']}` <= :end_date"
            params["end_date"] = end_date

        sql += f" ORDER BY `{mapping['trade_date']}` DESC LIMIT :limit"

        rows = self.db.execute(text(sql), params).mappings().all()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["change"] = item.pop("change_value", 0)
            result.append(item)

        return list(reversed(result))
