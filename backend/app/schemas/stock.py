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
    guotai_customer: NetPositionSeriesGroupResponse
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


class IndexDashboardCnMarketFearGreedPointResponse(BaseModel):
    trade_date: date
    fear_greed_value: float
    sentiment_label: str = ""


class IndexDashboardCnBaifenweiFearGreedPointResponse(BaseModel):
    trade_date: date
    fear_greed_value: float
    sentiment_label: str = ""
    volatility_score: float
    relative_turnover_score: float
    margin_trading_score: float
    market_breadth_score: float
    rsi_score: float
    limit_up_down_ratio_score: float
    market_index_value: float | None = None
    value_origin: str = ""


class IndexDashboardBasisPointResponse(BaseModel):
    trade_date: date
    index_name: str = ""
    main_basis: float
    month_basis: float
    main_basis_adjusted: float | None = None
    basis_roll_flag: bool = False
    basis_roll_delta: float | None = None
    basis_roll_type: str | None = None
    basis_roll_contracts: list[str] = Field(default_factory=list)


class IndexDashboardVixPointResponse(BaseModel):
    trade_date: date
    open_price: float
    high_price: float
    low_price: float
    close_price: float


class IndexDashboardRelatedVixSeriesResponse(BaseModel):
    source_key: str
    source_name: str
    qvix_code: str
    points: list[IndexDashboardVixPointResponse] = Field(default_factory=list)


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
    premium_put_call_ratio: float | None = None
    total_premium_million_usd: float | None = None
    call_premium_million_usd: float | None = None
    put_premium_million_usd: float | None = None
    premium_rounding_unit_million_usd: float | None = None
    premium_value_basis: str | None = None
    option_product_code: str | None = None
    option_product_name: str | None = None
    current_month_price_put_call_ratio: float | None = None
    current_month_contract_month: str | None = None
    next_month_price_put_call_ratio: float | None = None
    next_month_contract_month: str | None = None
    quarter_1_price_put_call_ratio: float | None = None
    quarter_1_contract_month: str | None = None
    quarter_2_price_put_call_ratio: float | None = None
    quarter_2_contract_month: str | None = None
    price_value_basis: str | None = None
    price_data_source: str | None = None


class IndexDashboardCnOptionPutCallPointResponse(BaseModel):
    trade_date: date
    current_month_put_call_ratio: float | None = None
    current_month_contract_month: str | None = None
    current_month_special_calculation: bool = False
    current_month_special_note: str | None = None
    next_month_put_call_ratio: float | None = None
    next_month_contract_month: str | None = None
    next_month_special_calculation: bool = False
    next_month_special_note: str | None = None
    quarter_1_put_call_ratio: float | None = None
    quarter_1_contract_month: str | None = None
    quarter_1_special_calculation: bool = False
    quarter_1_special_note: str | None = None
    quarter_2_put_call_ratio: float | None = None
    quarter_2_contract_month: str | None = None
    quarter_2_special_calculation: bool = False
    quarter_2_special_note: str | None = None


class IndexDashboardCnOptionFlowPutCallPointResponse(BaseModel):
    trade_date: date
    volume_put_call_ratio: float | None = None
    turnover_put_call_ratio: float | None = None
    turnover_call_put_ratio: float | None = None


class IndexDashboardCnOptionVixPointResponse(BaseModel):
    trade_date: date
    vix_open: float | None = None
    vix_high: float | None = None
    vix_low: float | None = None
    vix_close: float | None = None
    near_contract_month: str | None = None
    near_expiry_date: date | None = None
    near_strike_count: int | None = None
    next_contract_month: str | None = None
    next_expiry_date: date | None = None
    next_strike_count: int | None = None
    risk_free_curve_date: date | None = None
    near_risk_free_rate: float | None = None
    next_risk_free_rate: float | None = None
    calculation_method: str | None = None
    uses_minute_ohlc: bool = False
    minute_count: int | None = None
    minute_mid_quote_count: int | None = None
    price_basis_counts: dict[str, int] = Field(default_factory=dict)
    pre_settle_sources: list[str] = Field(default_factory=list)
    reference_qvix_code: str | None = None
    reference_match_type: str | None = None
    reference_vix_open: float | None = None
    reference_vix_high: float | None = None
    reference_vix_low: float | None = None
    reference_vix_close: float | None = None
    open_error: float | None = None
    high_error: float | None = None
    low_error: float | None = None
    close_error: float | None = None
    open_error_pct: float | None = None
    high_error_pct: float | None = None
    low_error_pct: float | None = None
    close_error_pct: float | None = None
    ohlc_mean_abs_error: float | None = None
    ohlc_mean_abs_pct_error: float | None = None


class IndexDashboardCnOptionSeriesResponse(BaseModel):
    source_key: str
    exchange: str
    exchange_label: str
    product_code: str
    product_name: str
    put_call_points: list[IndexDashboardCnOptionPutCallPointResponse] = Field(default_factory=list)
    flow_points: list[IndexDashboardCnOptionFlowPutCallPointResponse] = Field(default_factory=list)
    vix_points: list[IndexDashboardCnOptionVixPointResponse] = Field(default_factory=list)


class IndexDashboardCffexNetShortDeltaPointResponse(BaseModel):
    trade_date: date
    top20_delta_5d: float | None = None
    top20_delta_7d: float | None = None
    top20_delta_14d: float | None = None
    top20_delta_20d: float | None = None
    top20_delta_30d: float | None = None
    top20_delta_60d: float | None = None
    top20_delta_120d: float | None = None
    citic_delta_5d: float | None = None
    citic_delta_7d: float | None = None
    citic_delta_14d: float | None = None
    citic_delta_20d: float | None = None
    citic_delta_30d: float | None = None
    citic_delta_60d: float | None = None
    citic_delta_120d: float | None = None


class IndexDashboardBasisDeltaPointResponse(BaseModel):
    trade_date: date
    main_delta_5d: float | None = None
    main_delta_7d: float | None = None
    main_delta_14d: float | None = None
    main_delta_20d: float | None = None
    main_delta_30d: float | None = None
    main_delta_60d: float | None = None
    main_delta_120d: float | None = None
    month_delta_5d: float | None = None
    month_delta_7d: float | None = None
    month_delta_14d: float | None = None
    month_delta_20d: float | None = None
    month_delta_30d: float | None = None
    month_delta_60d: float | None = None
    month_delta_120d: float | None = None


class IndexDashboardFundPurchaseLimitPointResponse(BaseModel):
    trade_date: date
    limited_fund_count: int
    total_fund_count: int
    limited_fund_pct: float


class IndexDashboardMarginTradingPointResponse(BaseModel):
    trade_date: date
    financing_balance: float | None = None
    securities_lending_balance: float | None = None
    total_balance: float | None = None
    financing_net_buy_amount: float | None = None
    leverage_ratio_pct: float | None = None
    total_market_cap_leverage_ratio_pct: float | None = None


class IndexDashboardMarginFinancingNetBuySumPointResponse(BaseModel):
    trade_date: date
    sum_5d: float | None = None
    sum_7d: float | None = None
    sum_14d: float | None = None
    sum_20d: float | None = None
    sum_30d: float | None = None
    sum_60d: float | None = None
    sum_120d: float | None = None


class IndexDashboardTurnoverConcentrationPointResponse(BaseModel):
    trade_date: date
    top5_pct: float | None = None
    top1_pct: float | None = None
    top1_raw_pct: float | None = None
    stock_count: int | None = None
    top1_stock_count: int | None = None
    top5_data_source: str | None = None
    top1_data_source: str | None = None
    source_date: date | None = None


class IndexDashboardSelfSentimentPointResponse(BaseModel):
    trade_date: date
    score: float | None = None
    core_score: float | None = None
    derivative_score: float | None = None
    component_count: int = 0
    components: dict[str, float | None] = Field(default_factory=dict)
    version: str = ""


class IndexDashboardUsTreasuryYieldPointResponse(BaseModel):
    trade_date: date
    yield_3m: float | None = None
    yield_2y: float | None = None
    yield_10y: float | None = None
    yield_real_10y: float | None = None
    spread_10y_2y: float | None = None
    spread_10y_3m: float | None = None
    available_at: str | None = None


class IndexDashboardUsCreditSpreadPointResponse(BaseModel):
    trade_date: date
    high_yield_oas: float | None = None
    available_at: str | None = None


class IndexDashboardRiskStrategyPointResponse(BaseModel):
    trade_date: date
    yellow_vulnerability: bool | None = None
    yellow_score: float | None = None
    red_escalation: bool | None = None
    red_score: float | None = None
    global_shock: bool | None = None
    global_raw_leading: bool | None = None
    global_raw_leading_score: float | None = None
    global_raw_leading_mode: str | None = None
    global_leading: bool | None = None
    global_leading_score: float | None = None
    global_leading_mode: str | None = None
    global_leading_trigger_date: date | None = None
    global_leading_valid_through: date | None = None
    global_leading_gate_score: float | None = None
    global_leading_trigger_threshold: float | None = None
    global_leading_release_threshold: float | None = None
    global_confirmation_score: float | None = None
    global_score: float | None = None
    global_mode: str | None = None
    overall_score: float | None = None
    domestic_vulnerability_score: float | None = None
    domestic_deterioration_score: float | None = None
    base_state: str | None = None
    display_state: str | None = None
    global_active_modules: list[str] = Field(default_factory=list)
    as_of_at: str | None = None
    decision_trade_date: date | None = None
    components: dict = Field(default_factory=dict)


class QuantRiskDashboardPointResponse(BaseModel):
    trade_date: date
    scoring_mode: str = "grouped"
    model_version: str = ""
    yellow_vulnerability: bool | None = None
    yellow_score: float | None = None
    red_escalation: bool | None = None
    red_score: float | None = None
    global_shock: bool | None = None
    global_raw_leading: bool | None = None
    global_raw_leading_score: float | None = None
    global_raw_leading_mode: str | None = None
    global_leading: bool | None = None
    global_leading_score: float | None = None
    global_leading_mode: str | None = None
    global_leading_trigger_date: date | None = None
    global_leading_valid_through: date | None = None
    global_leading_gate_score: float | None = None
    global_leading_trigger_threshold: float | None = None
    global_leading_release_threshold: float | None = None
    global_confirmation_score: float | None = None
    global_score: float | None = None
    global_mode: str | None = None
    overall_score: float | None = None
    domestic_vulnerability_score: float | None = None
    domestic_deterioration_score: float | None = None
    domestic_vulnerability_contribution: float | None = None
    domestic_deterioration_contribution: float | None = None
    global_contribution: float | None = None
    base_state: str | None = None
    display_state: str | None = None
    global_active_modules: list[str] = Field(default_factory=list)
    as_of_at: str | None = None
    decision_trade_date: date | None = None
    composite_score: float | None = None
    risk_level: str | None = None
    risk_level_label: str | None = None
    data_complete: bool = False


class QuantRiskStrategySpanResponse(BaseModel):
    strategy_key: str
    strategy_label: str
    start_date: date
    end_date: date
    release_date: date | None = None
    active_days: int
    mode: str | None = None
    key_evidence: list[str] = Field(default_factory=list)


class QuantRiskStateSpanResponse(BaseModel):
    display_state: str
    state_label: str
    start_date: date
    end_date: date
    active_days: int
    key_evidence: list[str] = Field(default_factory=list)


class QuantRiskDrawdownResponse(BaseModel):
    trading_days: int
    value_pct: float | None = None
    trough_date: date | None = None
    days_to_trough: int | None = None
    status: str


class QuantRiskEventResponse(BaseModel):
    event_id: str
    start_date: date
    end_date: date
    release_date: date | None = None
    end_reason: str
    is_open: bool = False
    duration_trade_days: int
    first_trigger_date: date
    active_strategies: list[str] = Field(default_factory=list)
    strategy_spans: list[QuantRiskStrategySpanResponse] = Field(default_factory=list)
    state_spans: list[QuantRiskStateSpanResponse] = Field(default_factory=list)
    drawdowns: list[QuantRiskDrawdownResponse] = Field(default_factory=list)


class QuantRiskDashboardResponse(BaseModel):
    target_code: str
    target_name: str
    scoring_mode: str = "grouped"
    model_version: str = ""
    range_mode: str
    start_date: date
    end_date: date
    as_of_date: date | None = None
    candles: list[StockCandle] = Field(default_factory=list)
    points: list[QuantRiskDashboardPointResponse] = Field(default_factory=list)
    events: list[QuantRiskEventResponse] = Field(default_factory=list)


class QuantRiskEvidenceCellResponse(BaseModel):
    trade_date: date
    value: float | None = None
    level_value: float | None = None
    unit: str | None = None
    percentile: float | None = None
    absolute_threshold: float | None = None
    percentile_threshold: float | None = None
    score: float | None = None
    weight: float | None = None
    contribution: float | None = None
    direction: str | None = None
    matched: bool | None = None
    partial: bool = False
    data_date: date | None = None
    data_source: str | None = None
    available_at: str | None = None
    missing_reason: str | None = None


class QuantRiskEvidenceRowResponse(BaseModel):
    key: str
    strategy_key: str
    strategy_label: str
    section_key: str
    section_label: str
    label: str
    cells: list[QuantRiskEvidenceCellResponse] = Field(default_factory=list)


class QuantRiskEvidenceResponse(BaseModel):
    target_code: str
    target_name: str
    scoring_mode: str = "grouped"
    start_date: date
    end_date: date
    dates: list[date] = Field(default_factory=list)
    rows: list[QuantRiskEvidenceRowResponse] = Field(default_factory=list)


class IndexDashboardResponse(BaseModel):
    index: IndexDashboardIndexResponse
    market: str = "cn"
    supports_auxiliary_panels: bool = True
    supports_basis_panel: bool = False
    range_mode: str
    candles: list[StockCandle]
    emotion_points: list[IndexDashboardEmotionPointResponse]
    cn_market_fear_greed_points: list[IndexDashboardCnMarketFearGreedPointResponse] = Field(default_factory=list)
    cn_baifenwei_fear_greed_points: list[IndexDashboardCnBaifenweiFearGreedPointResponse] = Field(
        default_factory=list
    )
    basis_points: list[IndexDashboardBasisPointResponse]
    breadth_points: list[IndexBreadthPointResponse]
    vix_points: list[IndexDashboardVixPointResponse]
    related_vix_series: list[IndexDashboardRelatedVixSeriesResponse] = Field(default_factory=list)
    us_vix_points: list[IndexDashboardUsVixPointResponse] = Field(default_factory=list)
    us_fear_greed_points: list[IndexDashboardUsFearGreedPointResponse] = Field(default_factory=list)
    us_hedge_proxy_points: list[IndexDashboardUsHedgeProxyPointResponse] = Field(default_factory=list)
    us_put_call_points: list[IndexDashboardUsPutCallPointResponse] = Field(default_factory=list)
    cn_option_put_call_points: list[IndexDashboardCnOptionPutCallPointResponse] = Field(default_factory=list)
    cn_option_flow_put_call_points: list[IndexDashboardCnOptionFlowPutCallPointResponse] = Field(default_factory=list)
    cn_option_series: list[IndexDashboardCnOptionSeriesResponse] = Field(default_factory=list)
    cffex_net_short_delta_points: list[IndexDashboardCffexNetShortDeltaPointResponse] = Field(default_factory=list)
    basis_delta_points: list[IndexDashboardBasisDeltaPointResponse] = Field(default_factory=list)
    fund_purchase_limit_points: list[IndexDashboardFundPurchaseLimitPointResponse] = Field(default_factory=list)
    margin_trading_points: list[IndexDashboardMarginTradingPointResponse] = Field(default_factory=list)
    margin_financing_net_buy_sum_points: list[IndexDashboardMarginFinancingNetBuySumPointResponse] = Field(default_factory=list)
    turnover_concentration_points: list[IndexDashboardTurnoverConcentrationPointResponse] = Field(default_factory=list)
    self_sentiment_points: list[IndexDashboardSelfSentimentPointResponse] = Field(default_factory=list)
    us_treasury_yield_points: list[IndexDashboardUsTreasuryYieldPointResponse] = Field(default_factory=list)
    us_credit_spread_points: list[IndexDashboardUsCreditSpreadPointResponse] = Field(default_factory=list)
    risk_strategy_points: list[IndexDashboardRiskStrategyPointResponse] = Field(default_factory=list)


class HfqCollectTaskPayload(BaseModel):
    ts_code: str
    start_date: date | None = None
    end_date: date | None = None


class QuantScanSellTriggerConfig(BaseModel):
    enabled: bool = False
    operator: str = "lt"
    target: str = "ma-1"


class QuantResearchOptionTemplateConfig(BaseModel):
    enabled: bool = True
    report_generated_at: str | None = None
    direction_mode: str = "dynamic"
    product_code: str
    product_name: str
    exchange: str
    option_type: str
    strategy_type: str
    expiry_bucket: str
    expiry_bucket_label: str
    moneyness: str
    moneyness_label: str
    holding_days: int
    slippage: float = 0.005
    initial_capital: float = 1_000_000
    contracts_per_trade: int = 1


class QuantScanTradeConfig(BaseModel):
    initial_capital: float = 1_000_000
    buy_amount_per_event: float = 10_000
    buy_offset_trading_days: int = 1
    sell_offset_trading_days: int = 2
    buy_price_basis: str = "open"
    sell_price_basis: str = "open"
    sell_trigger: QuantScanSellTriggerConfig | None = None
    board_filters: list[str] = Field(default_factory=list)


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
    research_option_template: QuantResearchOptionTemplateConfig | None = None
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
    research_option_template: QuantResearchOptionTemplateConfig | None = None
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
    position_value: float | None = None
    position_pct: float = 0.0
    position_bucket: str | None = None


class QuantStrategyHighlightBandResponse(BaseModel):
    tradeDate: date
    color: str
    variant: str = "solid"
    blueHitGroups: list[int] = Field(default_factory=list)
    redHitGroups: list[int] = Field(default_factory=list)
    riskDetails: dict | None = None


class QuantStrategyTargetChartResponse(BaseModel):
    target_type: str
    target_market: str
    target_code: str
    target_name: str
    candles: list[StockCandle] = Field(default_factory=list)
    highlight_bands: list[QuantStrategyHighlightBandResponse] = Field(default_factory=list)
    risk_strategy_points: list[IndexDashboardRiskStrategyPointResponse] = Field(default_factory=list)


class QuantOptionTradeResponse(BaseModel):
    signal_date: date
    product_code: str
    product_name: str
    exchange: str
    option_type: str
    expiry_bucket: str
    expiry_bucket_label: str
    moneyness: str
    moneyness_label: str
    holding_days: int
    direction_reason: str
    prior_20d_return_pct: float | None = None
    prior_40d_return_pct: float | None = None
    contract_code: str | None = None
    contract_month: str | None = None
    contract_month_label: str | None = None
    strike_price: float | None = None
    contract_unit: float | None = None
    contract_quantity: int | None = None
    buy_date: date | None = None
    buy_price: float | None = None
    buy_amount: float | None = None
    sell_date: date | None = None
    sell_price: float | None = None
    sell_amount: float | None = None
    profit_per_contract: float | None = None
    return_pct: float | None = None
    status: str
    status_reason: str


class QuantOptionTradeSummaryResponse(BaseModel):
    signal_count: int = 0
    completed_count: int = 0
    pending_count: int = 0
    direction_mismatch_count: int = 0
    not_listed_count: int = 0
    unavailable_count: int = 0


class QuantOptionTradeResultResponse(BaseModel):
    template: QuantResearchOptionTemplateConfig
    trades: list[QuantOptionTradeResponse] = Field(default_factory=list)
    summary: QuantOptionTradeSummaryResponse = Field(default_factory=QuantOptionTradeSummaryResponse)
    initial_capital: float = 1_000_000
    cumulative_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    points: list[QuantEquityCurvePointResponse] = Field(default_factory=list)


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
    sell_trigger_date: date | None = None
    sell_reason: str | None = None
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
    indicator_params: dict = Field(default_factory=dict)
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
    sell_trigger_dates: list[date] = Field(default_factory=list)


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
