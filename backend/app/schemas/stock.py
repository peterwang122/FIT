from datetime import date, datetime

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
    turnover_rate: float = 0
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


class MarketOptionResponse(BaseModel):
    code: str
    name: str


class IndexEmotionPointResponse(BaseModel):
    emotion_date: date
    index_name: str
    emotion_value: float


class FuturesBasisPointResponse(BaseModel):
    trade_date: date
    index_name: str
    main_basis: float | None = None
    month_basis: float | None = None


class NetPositionRowResponse(BaseModel):
    product_code: str
    index_name: str
    short_position: int
    long_position: int
    net_position: int
    net_position_text: str
    action: str


class NetPositionTableResponse(BaseModel):
    member_label: str
    trade_date: date | None = None
    title: str
    total_net_position: int
    total_net_position_text: str
    rows: list[NetPositionRowResponse]


class NetPositionTablesResponse(BaseModel):
    citic_customer: NetPositionTableResponse
    top20_institutions: NetPositionTableResponse


class NetPositionSeriesPointResponse(BaseModel):
    trade_date: date
    net_position: int


class NetPositionSeriesGroupResponse(BaseModel):
    member_label: str
    series: dict[str, list[NetPositionSeriesPointResponse]]


class NetPositionSeriesResponse(BaseModel):
    citic_customer: NetPositionSeriesGroupResponse
    top20_institutions: NetPositionSeriesGroupResponse


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


class IndexBreadthPointResponse(BaseModel):
    trade_date: date
    up_ratio_pct: float
    up_count: int
    total_count: int


class IndexDashboardIndexResponse(BaseModel):
    code: str
    name: str


class IndexDashboardEmotionPointResponse(BaseModel):
    trade_date: date
    value: float


class IndexDashboardBasisPointResponse(BaseModel):
    trade_date: date
    main_basis: float
    month_basis: float


class IndexDashboardResponse(BaseModel):
    index: IndexDashboardIndexResponse
    range_mode: str
    candles: list[StockCandle]
    emotion_points: list[IndexDashboardEmotionPointResponse]
    basis_points: list[IndexDashboardBasisPointResponse]
    breadth_points: list[IndexBreadthPointResponse]


class QfqCollectTaskPayload(BaseModel):
    ts_code: str
    start_date: date | None = None
    end_date: date | None = None


class QuantStrategySavePayload(BaseModel):
    name: str
    strategy_type: str
    target_code: str
    target_name: str
    indicator_params: dict
    blue_filters: dict = {}
    red_filters: dict = {}
    blue_boll_filter: dict = {}
    red_boll_filter: dict = {}
    signal_buy_color: str = "blue"
    signal_sell_color: str = "red"
    purple_conflict_mode: str = "sell_first"
    start_date: date | None = None
    buy_position_pct: float = 1.0
    sell_position_pct: float = 1.0
    execution_price_mode: str = "next_open"


class QuantStrategyConfigResponse(BaseModel):
    id: int
    name: str
    strategy_type: str
    target_code: str
    target_name: str
    indicator_params: dict
    blue_filters: dict
    red_filters: dict
    blue_boll_filter: dict
    red_boll_filter: dict
    signal_buy_color: str
    signal_sell_color: str
    purple_conflict_mode: str
    start_date: date | None = None
    buy_position_pct: float
    sell_position_pct: float
    execution_price_mode: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QuantEquityCurvePointResponse(BaseModel):
    trade_date: date
    nav: float
    benchmark_nav: float | None = None
    signal: str | None = None
    close_price: float | None = None


class QuantEquityCurveResponse(BaseModel):
    strategy: QuantStrategyConfigResponse
    cumulative_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    points: list[QuantEquityCurvePointResponse]
