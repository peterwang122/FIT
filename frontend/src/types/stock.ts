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
}

export interface StockSymbol {
  ts_code: string
}

export interface StockMeta {
  table_name: string
  column_mapping: Record<string, string>
}
