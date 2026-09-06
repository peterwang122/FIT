export type RegimeIndex = 'sh000852' | 'sh000985'
export type RegimeState = 'valid' | 'paused' | 'invalid' | 'repair' | 'unavailable'

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
}

export interface RegimeEvent {
  start: string
  end: string
  days: number
  closed: boolean
  end_reason: string | null
  drawdown_20d_pct: number | null
  upside_20d_pct: number | null
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
  history_start: string | null
  history_end: string | null
  notes: string[]
  latest: RegimePoint | null
  points: RegimePoint[]
  events: RegimeEvent[]
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
