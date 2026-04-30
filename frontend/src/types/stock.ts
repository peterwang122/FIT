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
}

export interface IndexDashboardBasisPoint {
  trade_date: string
  index_name: string
  main_basis: number
  month_basis: number
  main_basis_adjusted?: number | null
  basis_roll_flag?: boolean
  basis_roll_delta?: number | null
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
  basis_points: IndexDashboardBasisPoint[]
  breadth_points: IndexBreadthPoint[]
  vix_points: IndexVixPoint[]
  us_vix_points: IndexUsVixPoint[]
  us_fear_greed_points: IndexUsFearGreedPoint[]
  us_hedge_proxy_points: IndexUsHedgeProxyPoint[]
  us_put_call_points: IndexUsPutCallPoint[]
  us_treasury_yield_points: IndexUsTreasuryYieldPoint[]
  us_credit_spread_points: IndexUsCreditSpreadPoint[]
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
