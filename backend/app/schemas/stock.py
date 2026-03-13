from datetime import date

from pydantic import BaseModel


class StockCandle(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float = 0
    change: float = 0
    pct_chg: float = 0
    vol: float = 0
    amount: float = 0
    pe_ttm: float = 0
    pb: float = 0
    total_market_value: float = 0
    circulating_market_value: float = 0


class CollectTaskPayload(BaseModel):
    ts_code: str
    start_date: date | None = None
    end_date: date | None = None


class StockMetaResponse(BaseModel):
    table_name: str
    column_mapping: dict[str, str]


class StockSymbolResponse(BaseModel):
    ts_code: str
    stock_name: str


class DbStatusResponse(BaseModel):
    connected: bool
    table_name: str
    table_exists: bool
    has_required_mapping: bool
    row_count: int
    symbol_count: int
    sample_symbols: list[str]
    mapping: dict[str, str]
    error: str | None = None
