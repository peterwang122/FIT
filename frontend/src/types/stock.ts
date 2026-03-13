export interface StockCandle {
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

export interface StockMeta {
  table_name: string
  column_mapping: Record<string, string>
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
