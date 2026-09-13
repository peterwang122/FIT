export type RegimeIndex = 'sh000852' | 'sh000985'
export type RegimeState = 'valid' | 'paused' | 'invalid' | 'repair' | 'unavailable'
export type RegimeMissingReason = 'trend_history_short' | 'breadth_history_missing' | 'insufficient_traded' | 'insufficient_coverage'
export type RegimeWindow = 5 | 10 | 20 | 60

export interface RegimePoint {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number
  medium_ma: number | null
  long_ma: number | null
  long_slope: number | null
  breadth_medium: number | null
  breadth_long: number | null
  observed: number | null
  traded: number | null
  eligible: number | null
  state: RegimeState
  buy_multiplier: number
  reason?: string | null
  coverage_pct?: number | null
  missing_reasons?: RegimeMissingReason[]
  pause_met?: boolean | null
  invalid_met?: boolean | null
  recover_met?: boolean | null
  full_met?: boolean | null
  pause_streak?: number | null
  invalid_streak?: number | null
  recover_streak?: number | null
  full_streak?: number | null
}

export interface RegimeEvent {
  start: string
  end: string
  days: number
  closed: boolean
  end_reason: string | null
  resumed_date?: string | null
  states?: RegimeState[]
  drawdown_5d_pct?: number | null
  upside_5d_pct?: number | null
  drawdown_10d_pct?: number | null
  upside_10d_pct?: number | null
  drawdown_20d_pct: number | null
  upside_20d_pct: number | null
  drawdown_60d_pct?: number | null
  upside_60d_pct?: number | null
}

export interface RegimeGap {
  start: string
  end: string
  days: number
  min_coverage_pct: number | null
  max_coverage_pct: number | null
  reasons: RegimeMissingReason[]
}

export interface MarketRegimeDashboard {
  schema_version: string
  generated_at: string
  research_only: true
  model_approved: false
  rule_name: string
  index_code: RegimeIndex
  index_name: string
  breadth_as_of: string
  strategy_evaluation_end?: string | null
  breadth_sources?: { table: string; start: string; end: string; note: string }[]
  history_start: string | null
  history_end: string | null
  notes: string[]
  latest: RegimePoint | null
  points: RegimePoint[]
  events: RegimeEvent[]
  coverage_gaps?: RegimeGap[]
}

export const regimeMissingLabels: Record<RegimeMissingReason, string> = {
  trend_history_short: '指数均线样本不足',
  breadth_history_missing: '广度缺失或窗口无有效样本',
  insufficient_traded: '当日交易样本不足500只',
  insufficient_coverage: 'MA120有效覆盖不足60%',
}

export const regimeLabels: Record<RegimeState, string> = {
  valid: '环境有效', paused: '临时暂停', invalid: '假设失效', repair: '修复观察', unavailable: '数据不完整',
}
export const regimeColors: Record<RegimeState, string> = {
  valid: '#27836c', paused: '#d4a444', invalid: '#cc5656', repair: '#537ead', unavailable: '#cbd5e1',
}
export const regimePermissions: Record<RegimeState, string> = {
  valid: '允许', paused: '暂停新买入', invalid: '停用牛市低吸', repair: '半额观察', unavailable: '暂不判断',
}
