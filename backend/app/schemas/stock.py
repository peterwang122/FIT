from datetime import date, datetime

from pydantic import BaseModel, Field


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
    index_name: str = ""
    main_basis: float
    month_basis: float
    main_basis_adjusted: float | None = None
    basis_roll_flag: bool = False
    basis_roll_delta: float | None = None


class IndexDashboardVixPointResponse(BaseModel):
    trade_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float


class IndexDashboardUsVixPointResponse(BaseModel):
    trade_date: date
    open_value: float
    high_value: float
    low_value: float
    close_value: float


class IndexDashboardUsFearGreedPointResponse(BaseModel):
    trade_date: date
    fear_greed_value: float
    sentiment_label: str = ""


class IndexDashboardUsHedgeProxyPointResponse(BaseModel):
    report_date: date | None = None
    release_date: date
    contract_scope: str
    long_value: float | None = None
    short_value: float | None = None
    ratio_value: float | None = None


class IndexDashboardUsPutCallPointResponse(BaseModel):
    trade_date: date
    total_put_call_ratio: float | None = None
    index_put_call_ratio: float | None = None
    equity_put_call_ratio: float | None = None
    etf_put_call_ratio: float | None = None


class IndexDashboardUsTreasuryYieldPointResponse(BaseModel):
    trade_date: date
    yield_3m: float | None = None
    yield_2y: float | None = None
    yield_10y: float | None = None
    spread_10y_2y: float | None = None
    spread_10y_3m: float | None = None


class IndexDashboardUsCreditSpreadPointResponse(BaseModel):
    trade_date: date
    high_yield_oas: float | None = None


class IndexDashboardResponse(BaseModel):
    index: IndexDashboardIndexResponse
    market: str = "cn"
    supports_auxiliary_panels: bool = True
    supports_basis_panel: bool = False
    range_mode: str
    candles: list[StockCandle]
    emotion_points: list[IndexDashboardEmotionPointResponse]
    basis_points: list[IndexDashboardBasisPointResponse]
    breadth_points: list[IndexBreadthPointResponse]
    vix_points: list[IndexDashboardVixPointResponse]
    us_vix_points: list[IndexDashboardUsVixPointResponse] = Field(default_factory=list)
    us_fear_greed_points: list[IndexDashboardUsFearGreedPointResponse] = Field(default_factory=list)
    us_hedge_proxy_points: list[IndexDashboardUsHedgeProxyPointResponse] = Field(default_factory=list)
    us_put_call_points: list[IndexDashboardUsPutCallPointResponse] = Field(default_factory=list)
    us_treasury_yield_points: list[IndexDashboardUsTreasuryYieldPointResponse] = Field(default_factory=list)
    us_credit_spread_points: list[IndexDashboardUsCreditSpreadPointResponse] = Field(default_factory=list)


class HfqCollectTaskPayload(BaseModel):
    ts_code: str
    start_date: date | None = None
    end_date: date | None = None


class QuantScanTradeConfig(BaseModel):
    initial_capital: float = 1_000_000
    buy_amount_per_event: float = 10_000
    buy_offset_trading_days: int = 1
    sell_offset_trading_days: int = 2
    buy_price_basis: str = "open"
    sell_price_basis: str = "open"


class QuantStrategySavePayload(BaseModel):
    name: str
    notes: str = ""
    strategy_engine: str = "snapshot"
    sequence_mode: str = "single_target"
    strategy_type: str
    target_market: str = "cn"
    target_code: str
    target_name: str
    indicator_params: dict
    buy_sequence_groups: list[dict] = Field(default_factory=list)
    sell_sequence_groups: list[dict] = Field(default_factory=list)
    scan_trade_config: QuantScanTradeConfig = Field(default_factory=QuantScanTradeConfig)
    blue_filter_groups: list[dict] = Field(default_factory=list)
    red_filter_groups: list[dict] = Field(default_factory=list)
    blue_filters: dict = Field(default_factory=dict)
    red_filters: dict = Field(default_factory=dict)
    blue_boll_filter: dict = Field(default_factory=dict)
    red_boll_filter: dict = Field(default_factory=dict)
    signal_buy_color: str = "blue"
    signal_sell_color: str = "red"
    purple_conflict_mode: str = "sell_first"
    start_date: date | None = None
    scan_start_date: date | None = None
    scan_end_date: date | None = None
    buy_position_pct: float = 1.0
    sell_position_pct: float = 1.0
    execution_price_mode: str = "next_open"


class QuantStrategySendPayload(BaseModel):
    target_username: str = Field(min_length=1, max_length=64)


class QuantStrategyConfigResponse(BaseModel):
    id: int
    name: str
    notes: str = ""
    strategy_engine: str = "snapshot"
    sequence_mode: str = "single_target"
    strategy_type: str
    target_market: str = "cn"
    target_code: str
    target_name: str
    indicator_params: dict
    buy_sequence_groups: list[dict] = Field(default_factory=list)
    sell_sequence_groups: list[dict] = Field(default_factory=list)
    scan_trade_config: QuantScanTradeConfig = Field(default_factory=QuantScanTradeConfig)
    blue_filter_groups: list[dict] = Field(default_factory=list)
    red_filter_groups: list[dict] = Field(default_factory=list)
    blue_filters: dict
    red_filters: dict
    blue_boll_filter: dict
    red_boll_filter: dict
    signal_buy_color: str
    signal_sell_color: str
    purple_conflict_mode: str
    start_date: date | None = None
    scan_start_date: date | None = None
    scan_end_date: date | None = None
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
    position_pct: float = 0.0
    position_bucket: str | None = None


class QuantPositionPairResponse(BaseModel):
    buy_position_pct: float
    sell_position_pct: float
    cumulative_return_pct: float | None = None


class QuantPositionOptimizationTargetResponse(BaseModel):
    value_pct: float
    combinations: list[QuantPositionPairResponse] = Field(default_factory=list)


class QuantPositionOptimizationResponse(BaseModel):
    max_total_return: QuantPositionOptimizationTargetResponse
    min_drawdown: QuantPositionOptimizationTargetResponse


class QuantScanEventResponse(BaseModel):
    event_id: str
    target_type: str
    target_code: str
    target_name: str
    signal_date: date
    buy_date: date | None = None
    sell_date: date | None = None
    hit_buy_groups: list[int] = Field(default_factory=list)
    tradable: bool
    disabled_reason: str | None = None
    board: str | None = None
    lot_rule: str | None = None
    buy_price: float | None = None
    sell_price: float | None = None
    planned_quantity: int | None = None
    planned_buy_amount: float | None = None
    selected: bool | None = None
    executed: bool | None = None
    skip_reason: str | None = None
    actual_quantity: int | None = None
    actual_buy_amount: float | None = None
    actual_sell_amount: float | None = None
    pnl_amount: float | None = None
    return_pct: float | None = None


class QuantSequenceScanPreviewPayload(BaseModel):
    strategy_type: str
    buy_sequence_groups: list[dict] = Field(default_factory=list)
    scan_trade_config: QuantScanTradeConfig = Field(default_factory=QuantScanTradeConfig)
    scan_start_date: date
    scan_end_date: date


class QuantSequenceScanEventPageResponse(BaseModel):
    scan_result_id: str
    strategy_type: str
    matched_events: list[QuantScanEventResponse] = Field(default_factory=list)
    matched_event_count: int
    tradable_event_count: int
    total_event_count: int
    page: int
    page_size: int


class QuantSequenceScanTargetHitsResponse(BaseModel):
    scan_result_id: str
    target_code: str
    target_name: str
    hit_dates: list[date] = Field(default_factory=list)


class QuantSequenceScanPreviewResponse(QuantSequenceScanEventPageResponse):
    pass


class QuantSequenceScanBacktestPayload(BaseModel):
    scan_result_id: str
    scan_trade_config: QuantScanTradeConfig = Field(default_factory=QuantScanTradeConfig)
    use_all_events: bool = True
    excluded_event_ids: list[str] = Field(default_factory=list)
    selected_event_ids: list[str] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=100, ge=1, le=500)


class QuantSequenceScanBacktestSummaryResponse(BaseModel):
    matched_event_count: int
    tradable_event_count: int
    selected_event_count: int
    executed_event_count: int
    skipped_event_count: int


class QuantSequenceScanBacktestResponse(BaseModel):
    scan_result_id: str
    strategy_type: str
    matched_events: list[QuantScanEventResponse] = Field(default_factory=list)
    total_event_count: int
    page: int
    page_size: int
    cumulative_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    points: list[QuantEquityCurvePointResponse] = Field(default_factory=list)
    summary: QuantSequenceScanBacktestSummaryResponse


class QuantEquityCurveResponse(BaseModel):
    strategy: QuantStrategyConfigResponse
    cumulative_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    points: list[QuantEquityCurvePointResponse]
    position_optimization: QuantPositionOptimizationResponse
