export interface KlineCandle {
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  pre_close: number
  change: number
  pct_chg: number
  vol: number
  amount: number
  turnover_rate: number
  pe_ttm: number
  pb: number
  total_market_value: number
  circulating_market_value: number
}

export interface StockSymbol {
  ts_code: string
  stock_name: string
}

export interface MarketOption {
  code: string
  name: string
}

export interface IndexEmotionPoint {
  emotion_date: string
  index_name: string
  emotion_value: number
}

export interface IndexDashboardEmotionPoint {
  trade_date: string
  value: number
}

export interface FuturesBasisPoint {
  trade_date: string
  index_name: string
  main_basis: number | null
  month_basis: number | null
  main_basis_adjusted?: number | null
  basis_roll_flag?: boolean
  basis_roll_delta?: number | null
  basis_roll_type?: string | null
  basis_roll_contracts?: string[]
}

export interface IndexDashboardBasisPoint {
  trade_date: string
  index_name: string
  main_basis: number
  month_basis: number
  main_basis_adjusted?: number | null
  basis_roll_flag?: boolean
  basis_roll_delta?: number | null
  basis_roll_type?: string | null
  basis_roll_contracts?: string[]
}

export interface IndexBreadthPoint {
  trade_date: string
  up_ratio_pct: number
  up_count: number
  total_count: number
}

export interface IndexVixPoint {
  trade_date: string
  open_price: number
  high_price: number
  low_price: number
  close_price: number
}

export interface IndexRelatedVixSeries {
  source_key: 'reference-vix-hs300-high' | 'reference-vix-csi500-high'
  source_name: string
  qvix_code: string
  points: IndexVixPoint[]
}

export interface IndexUsVixPoint {
  trade_date: string
  open_value: number
  high_value: number
  low_value: number
  close_value: number
}

export interface IndexUsFearGreedPoint {
  trade_date: string
  fear_greed_value: number
  sentiment_label: string
}

export interface IndexUsHedgeProxyPoint {
  report_date: string | null
  release_date: string
  contract_scope: string
  long_value: number | null
  short_value: number | null
  ratio_value: number | null
}

export interface IndexUsPutCallPoint {
  trade_date: string
  total_put_call_ratio: number | null
  index_put_call_ratio: number | null
  equity_put_call_ratio: number | null
  etf_put_call_ratio: number | null
  premium_put_call_ratio: number | null
  total_premium_million_usd: number | null
  call_premium_million_usd: number | null
  put_premium_million_usd: number | null
  premium_rounding_unit_million_usd: number | null
  premium_value_basis: string | null
  option_product_code: string | null
  option_product_name: string | null
  current_month_price_put_call_ratio: number | null
  current_month_contract_month: string | null
  next_month_price_put_call_ratio: number | null
  next_month_contract_month: string | null
  quarter_1_price_put_call_ratio: number | null
  quarter_1_contract_month: string | null
  quarter_2_price_put_call_ratio: number | null
  quarter_2_contract_month: string | null
  price_value_basis: string | null
  price_data_source: string | null
}

export interface IndexCnOptionPutCallPoint {
  trade_date: string
  current_month_put_call_ratio: number | null
  current_month_contract_month: string | null
  current_month_special_calculation: boolean
  current_month_special_note: string | null
  next_month_put_call_ratio: number | null
  next_month_contract_month: string | null
  next_month_special_calculation: boolean
  next_month_special_note: string | null
  quarter_1_put_call_ratio: number | null
  quarter_1_contract_month: string | null
  quarter_1_special_calculation: boolean
  quarter_1_special_note: string | null
  quarter_2_put_call_ratio: number | null
  quarter_2_contract_month: string | null
  quarter_2_special_calculation: boolean
  quarter_2_special_note: string | null
}

export interface IndexCnOptionFlowPutCallPoint {
  trade_date: string
  volume_put_call_ratio: number | null
  turnover_put_call_ratio: number | null
  turnover_call_put_ratio: number | null
}

export interface IndexCnOptionVixPoint {
  trade_date: string
  vix_open: number | null
  vix_high: number | null
  vix_low: number | null
  vix_close: number | null
  near_contract_month: string | null
  near_expiry_date: string | null
  near_strike_count: number | null
  next_contract_month: string | null
  next_expiry_date: string | null
  next_strike_count: number | null
  risk_free_curve_date: string | null
  near_risk_free_rate: number | null
  next_risk_free_rate: number | null
  calculation_method: string | null
  uses_minute_ohlc: boolean
  minute_count: number | null
  minute_mid_quote_count: number | null
  price_basis_counts: Record<string, number>
  pre_settle_sources: string[]
  reference_qvix_code: string | null
  reference_match_type: 'direct_product' | 'same_index_proxy' | null
  reference_vix_open: number | null
  reference_vix_high: number | null
  reference_vix_low: number | null
  reference_vix_close: number | null
  open_error: number | null
  high_error: number | null
  low_error: number | null
  close_error: number | null
  open_error_pct: number | null
  high_error_pct: number | null
  low_error_pct: number | null
  close_error_pct: number | null
  ohlc_mean_abs_error: number | null
  ohlc_mean_abs_pct_error: number | null
}

export interface IndexCnOptionSeries {
  source_key: string
  exchange: 'CFFEX' | 'SSE' | 'SZSE'
  exchange_label: string
  product_code: string
  product_name: string
  put_call_points: IndexCnOptionPutCallPoint[]
  flow_points: IndexCnOptionFlowPutCallPoint[]
  vix_points: IndexCnOptionVixPoint[]
}

export interface IndexCffexNetShortDeltaPoint {
  trade_date: string
  top20_delta_5d: number | null
  top20_delta_7d: number | null
  top20_delta_14d: number | null
  top20_delta_20d: number | null
  top20_delta_30d: number | null
  top20_delta_60d: number | null
  top20_delta_120d: number | null
  citic_delta_5d: number | null
  citic_delta_7d: number | null
  citic_delta_14d: number | null
  citic_delta_20d: number | null
  citic_delta_30d: number | null
  citic_delta_60d: number | null
  citic_delta_120d: number | null
}

export interface IndexBasisDeltaPoint {
  trade_date: string
  main_delta_5d: number | null
  main_delta_7d: number | null
  main_delta_14d: number | null
  main_delta_20d: number | null
  main_delta_30d: number | null
  main_delta_60d: number | null
  main_delta_120d: number | null
  month_delta_5d: number | null
  month_delta_7d: number | null
  month_delta_14d: number | null
  month_delta_20d: number | null
  month_delta_30d: number | null
  month_delta_60d: number | null
  month_delta_120d: number | null
}

export interface IndexFundPurchaseLimitPoint {
  trade_date: string
  limited_fund_count: number
  total_fund_count: number
  limited_fund_pct: number
}

export interface IndexCnMarketFearGreedPoint {
  trade_date: string
  fear_greed_value: number
  sentiment_label: string
}

export interface IndexCnBaifenweiFearGreedPoint {
  trade_date: string
  fear_greed_value: number
  sentiment_label: string
  volatility_score: number
  relative_turnover_score: number
  margin_trading_score: number
  market_breadth_score: number
  rsi_score: number
  limit_up_down_ratio_score: number
  market_index_value: number | null
  value_origin: 'published' | 'reconstructed' | string
}

export interface IndexMarginTradingPoint {
  trade_date: string
  financing_balance: number | null
  securities_lending_balance: number | null
  total_balance: number | null
  financing_net_buy_amount: number | null
  leverage_ratio_pct: number | null
  total_market_cap_leverage_ratio_pct: number | null
}

export interface IndexMarginFinancingNetBuySumPoint {
  trade_date: string
  sum_5d: number | null
  sum_7d: number | null
  sum_14d: number | null
  sum_20d: number | null
  sum_30d: number | null
  sum_60d: number | null
  sum_120d: number | null
}

export interface IndexTurnoverConcentrationPoint {
  trade_date: string
  top5_pct: number | null
  top1_pct: number | null
  top1_raw_pct: number | null
  stock_count: number | null
  top1_stock_count: number | null
  top5_data_source: string | null
  top1_data_source: string | null
  source_date: string | null
}

export interface IndexSelfSentimentPoint {
  trade_date: string
  score: number | null
  core_score: number | null
  derivative_score: number | null
  component_count: number
  components: Record<string, number | null>
  version: string
}

export interface IndexUsTreasuryYieldPoint {
  trade_date: string
  yield_3m: number | null
  yield_2y: number | null
  yield_10y: number | null
  spread_10y_2y: number | null
  spread_10y_3m: number | null
}

export interface IndexUsCreditSpreadPoint {
  trade_date: string
  high_yield_oas: number | null
}

export interface IndexRiskStrategyPoint {
  trade_date: string
  yellow_vulnerability: boolean | null
  yellow_score: number | null
  red_escalation: boolean | null
  red_score: number | null
  global_shock: boolean | null
  global_score: number | null
  global_mode: string | null
  components: Record<string, unknown>
}

export interface IndexDashboardResponse {
  index: {
    code: string
    name: string
  }
  market: 'cn' | 'hk' | 'us'
  supports_auxiliary_panels: boolean
  supports_basis_panel: boolean
  range_mode: 'recent' | 'full' | 'window'
  candles: KlineCandle[]
  emotion_points: IndexDashboardEmotionPoint[]
  cn_market_fear_greed_points: IndexCnMarketFearGreedPoint[]
  cn_baifenwei_fear_greed_points: IndexCnBaifenweiFearGreedPoint[]
  basis_points: IndexDashboardBasisPoint[]
  breadth_points: IndexBreadthPoint[]
  vix_points: IndexVixPoint[]
  related_vix_series?: IndexRelatedVixSeries[]
  us_vix_points: IndexUsVixPoint[]
  us_fear_greed_points: IndexUsFearGreedPoint[]
  us_hedge_proxy_points: IndexUsHedgeProxyPoint[]
  us_put_call_points: IndexUsPutCallPoint[]
  cn_option_put_call_points: IndexCnOptionPutCallPoint[]
  cn_option_flow_put_call_points: IndexCnOptionFlowPutCallPoint[]
  cn_option_series: IndexCnOptionSeries[]
  cffex_net_short_delta_points: IndexCffexNetShortDeltaPoint[]
  basis_delta_points: IndexBasisDeltaPoint[]
  fund_purchase_limit_points: IndexFundPurchaseLimitPoint[]
  margin_trading_points: IndexMarginTradingPoint[]
  margin_financing_net_buy_sum_points: IndexMarginFinancingNetBuySumPoint[]
  turnover_concentration_points: IndexTurnoverConcentrationPoint[]
  self_sentiment_points: IndexSelfSentimentPoint[]
  us_treasury_yield_points: IndexUsTreasuryYieldPoint[]
  us_credit_spread_points: IndexUsCreditSpreadPoint[]
  risk_strategy_points: IndexRiskStrategyPoint[]
}

export interface NetPositionRow {
  product_code: string
  index_name: string
  short_position: number
  long_position: number
  net_position: number
  net_position_text: string
  action: string
}

export interface NetPositionTable {
  member_label: string
  trade_date: string | null
  title: string
  total_net_position: number
  total_net_position_text: string
  rows: NetPositionRow[]
}

export interface NetPositionTables {
  citic_customer: NetPositionTable
  top20_institutions: NetPositionTable
}

export type CffexSeriesKey = 'OVERALL' | 'IF' | 'IH' | 'IC' | 'IM'
export type CffexCustomerMemberKey = 'citic_customer' | 'guotai_customer'

export interface NetPositionSeriesPoint {
  trade_date: string
  net_position: number
}

export interface NetPositionSeriesGroup {
  member_label: string
  series: Record<CffexSeriesKey, NetPositionSeriesPoint[]>
}

export interface NetPositionSeries {
  citic_customer: NetPositionSeriesGroup
  guotai_customer: NetPositionSeriesGroup
  top20_institutions: NetPositionSeriesGroup
}

export interface StockMeta {
  table_name: string
  column_mapping: Record<string, string>
}

export interface TaskSubmitResult {
  task_id: string
  status: string
}

export interface TaskStatusResult {
  task_id: string
  state: string
  result: Record<string, unknown> | null
}

export interface ForexCollectResult {
  status: string
  symbol_code: string
  symbol_name: string | null
  refresh_mode?: string
  rows_fetched: number
  upserted_rows: number
  earliest_trade_date: string | null
  latest_trade_date: string | null
  upstream_response?: Record<string, unknown>
}

export interface DbStatus {
  connected: boolean
  table_name: string
  table_exists: boolean
  has_required_mapping: boolean
  row_count: number
  symbol_count: number
  sample_symbols: string[]
  mapping: Record<string, string>
  error?: string
}
