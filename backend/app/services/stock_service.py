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

    def list_symbols(self, limit: int = 200) -> list[str]:
        cols = self.get_table_columns()
        if settings.stock_code_column not in cols:
            return []

        query = text(
            f"SELECT DISTINCT `{settings.stock_code_column}` AS ts_code "
            f"FROM `{settings.stock_table_name}` "
            f"ORDER BY `{settings.stock_code_column}` LIMIT :limit"
        )
        rows = self.db.execute(query, {"limit": limit}).mappings().all()
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
        for field in ["pre_close", "change", "pct_chg", "vol", "amount"]:
            if field in mapping:
                select_parts.append(f"`{mapping[field]}` AS {field}")
            else:
                select_parts.append(f"{optional_defaults[field]} AS {field}")

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
        return list(reversed([dict(row) for row in rows]))
