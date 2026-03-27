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

export interface FuturesBasisPoint {
  trade_date: string
  index_name: string
  main_basis: number | null
  month_basis: number | null
}

export interface IndexBreadthPoint {
  trade_date: string
  up_ratio_pct: number
  up_count: number
  total_count: number
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
