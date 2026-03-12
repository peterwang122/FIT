from datetime import date

from pydantic import BaseModel


class StockCandle(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    change: float
    pct_chg: float
    vol: float
    amount: float


class CollectTaskPayload(BaseModel):
    ts_code: str
    start_date: date | None = None
    end_date: date | None = None
