export type RegimeIndex = 'sh000852' | 'sh000985' | 'sh000300'
export type RegimeState = 'valid' | 'adjustment' | 'warning' | 'paused' | 'invalid' | 'repair' | 'unavailable'
export type RegimeMissingReason = 'trend_history_short' | 'breadth_history_missing' | 'insufficient_traded' | 'insufficient_coverage' | 'index_history_incomplete'
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
  evidence_mode?: 'stock_breadth' | 'index_proxy'
  pause_met?: boolean | null
  invalid_met?: boolean | null
  recover_met?: boolean | null
  full_met?: boolean | null
  pause_streak?: number | null
  invalid_streak?: number | null
  recover_streak?: number | null
  full_streak?: number | null
  annual_ma?: number | null
  annual_slope_pct?: number | null
  breadth_annual?: number | null
  drawdown_250d_pct?: number | null
  macro_status?: string | null
  state_since?: string | null
  trigger_rule?: string | null
  macro_complete: boolean
  macro_applied: boolean
  rules: { key: string; met: boolean; streak: number; days: number }[]
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
  model_rules: Record<string, string>
  index_code: RegimeIndex
  index_name: string
  breadth_as_of: string
  daily_as_of?: string | null
  daily_update_mode?: 'stock_breadth' | 'index_proxy'
  strategy_evaluation_end?: string | null
  breadth_sources?: { table: string; start: string; end: string; note: string }[]
  history_start: string | null
  history_end: string | null
  notes: string[]
  latest: RegimePoint | null
  points: RegimePoint[]
  events: RegimeEvent[]
  coverage_gaps?: RegimeGap[]
  lightweight_research?: MarketRegimeResearch | null
  strategy_comparison?: RegimeStrategyComparison | null
}

export interface MacroCycleEvidence {
  series_key: string
  period_end: string
  period_kind: 'monthly' | 'ytd' | 'stock'
  basis_version: string
  value: number
  unit: string
  source_url: string
  published_at: string | null
  available_at: string
  replay_available_at: string
  publication_precision: string
  vintage_status: string
  revision: boolean
  parser_correction: boolean
  independent_months: number
  change_3m: number | null
  mean_3m: number | null
  point_in_time_verified: boolean
  period_age_days?: number
}

export interface MacroEvidenceResponse {
  as_of_at: string
  macro_evidence: MacroCycleEvidence[]
  archive_macro_evidence: MacroCycleEvidence[]
  derived_evidence: { series_key: string; label: string; value: number; unit: string; period_end: string; available_at: string }[]
  missing_macro: string[]
  stale_macro: string[]
  macro_complete: boolean
}

export interface RegimeComparisonResult {
  key: string
  label: string
  return_pct: number
  mdd_pct: number
  missed_return_pp: number
  blocked_baseline_buys: number
  reduced_baseline_buys: number
  missing_gate_days: string[]
  restricted_entries: { signal_date: string; execution_date: string; state: RegimeState;
    multiplier: number; baseline_bought: boolean; return_20d_pct: number | null;
    upside_20d_pct: number | null; drawdown_20d_pct: number | null }[]
}

export interface RegimeStrategyComparison {
  model_version?: string
  start_date: string
  end_date: string
  strategy_name: string
  saved_start_date: string
  strategy_updated_at: string
  execution_asset: string
  signal_data_quality?: { note: string; missing_emotion_dates: string[];
    missing_pc_dates: string[]; missing_financing_dates: string[]; strict_replay_complete: boolean }
  results: RegimeComparisonResult[]
  notes: string[]
}

export interface MarketRegimeResearch extends MacroEvidenceResponse {
  macro_regime_timeline?: RegimeMacroSignal[]
  schema_version: 'market-regime-lightweight-v1'
  research_only: true
  model_approved: false
  as_of_at: string
  target_date: string
  timezone: 'Asia/Shanghai'
  daily_points: {
    date: string
    close: number
    ma60: number | null
    ma120: number | null
    trend_supportive: boolean | null
    index_participation_ma60_pct: number | null
    index_participation_ma120_pct: number | null
    missing_reasons: string[]
  }[]
  macro_evidence: MacroCycleEvidence[]
  archive_macro_evidence: MacroCycleEvidence[]
  missing_macro: string[]
  stale_macro: string[]
  macro_complete: boolean
  notes: string[]
  daily_context: { series_key: string; trade_date: string; value: number | null;
    unit: string; available_at: string | null; point_in_time_verified: boolean }[]
}

export interface RegimeMacroSignal {
  date: string
  status: string
  complete: boolean
  support_count: number
  adverse_count: number
  groups: { key: string; label: string; direction: number | null; reason: string;
    inputs: { series_key: string; value: number; period_end: string; available_at: string }[] }[]
}

export const regimeMissingLabels: Record<RegimeMissingReason, string> = {
  index_history_incomplete: '指数缺值或均线预热不足',
  trend_history_short: '指数均线样本不足',
  breadth_history_missing: '广度缺失或窗口无有效样本',
  insufficient_traded: '当日交易样本不足500只',
  insufficient_coverage: 'MA120有效覆盖不足60%',
}

export const regimeLabels: Record<RegimeState, string> = {
  valid: '牛市环境', adjustment: '牛市内调整', warning: '转弱观察', paused: '旧规则暂停', invalid: '熊市环境', repair: '修复观察', unavailable: '数据不完整',
}
export const regimeColors: Record<RegimeState, string> = {
  valid: '#27836c', adjustment: '#7bafa0', warning: '#d4a444', paused: '#d4a444', invalid: '#cc5656', repair: '#537ead', unavailable: '#cbd5e1',
}
export const regimePermissions: Record<RegimeState, string> = {
  valid: '牛市策略适配', adjustment: '保留低吸适配', warning: '减额观察', paused: '旧规则暂停', invalid: '牛市策略不适配', repair: '试探性恢复', unavailable: '暂不判断',
}
