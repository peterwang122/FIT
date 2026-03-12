from datetime import date

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.models.stock_data import StockData


class StockService:
    def __init__(self, db: Session):
        self.db = db

    def list_daily_kline(
        self,
        ts_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 500,
    ) -> list[StockData]:
        stmt: Select[tuple[StockData]] = select(StockData).where(StockData.ts_code == ts_code)
        if start_date:
            stmt = stmt.where(StockData.trade_date >= start_date)
        if end_date:
            stmt = stmt.where(StockData.trade_date <= end_date)
        stmt = stmt.order_by(desc(StockData.trade_date)).limit(limit)
        return list(reversed(self.db.execute(stmt).scalars().all()))
