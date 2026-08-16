import type { KlineCandle } from './stock'

export type QuantRiskStrategyKey = 'yellow_vulnerability' | 'red_escalation' | 'global_shock'
export type QuantRiskLevel = 'stable' | 'vulnerable' | 'high' | 'severe'
export type QuantRiskEventEndReason = 'released' | 'data_gap' | 'open'

export interface QuantRiskDashboardPoint {
  trade_date: string
  yellow_vulnerability: boolean | null
  yellow_score: number | null
  red_escalation: boolean | null
  red_score: number | null
  global_shock: boolean | null
  global_score: number | null
  global_mode: string | null
  composite_score: number | null
  risk_level: QuantRiskLevel | null
  risk_level_label: string | null
  data_complete: boolean
}

export interface QuantRiskStrategySpan {
  strategy_key: QuantRiskStrategyKey
  strategy_label: string
  start_date: string
  end_date: string
  release_date: string | null
  active_days: number
  mode: string | null
  key_evidence: string[]
}

export interface QuantRiskDrawdown {
  trading_days: 5 | 10 | 20
  value_pct: number | null
  trough_date: string | null
  days_to_trough: number | null
  status: 'complete' | 'pending'
}

export interface QuantRiskEvent {
  event_id: string
  start_date: string
  end_date: string
  release_date: string | null
  end_reason: QuantRiskEventEndReason
  is_open: boolean
  duration_trade_days: number
  first_trigger_date: string
  active_strategies: QuantRiskStrategyKey[]
  strategy_spans: QuantRiskStrategySpan[]
  drawdowns: QuantRiskDrawdown[]
}

export interface QuantRiskDashboardResponse {
  target_code: string
  target_name: string
  range_mode: string
  start_date: string
  end_date: string
  as_of_date: string | null
  candles: KlineCandle[]
  points: QuantRiskDashboardPoint[]
  events: QuantRiskEvent[]
}

export interface QuantRiskEvidenceCell {
  trade_date: string
  value: number | null
  unit: string | null
  percentile: number | null
  absolute_threshold: number | null
  percentile_threshold: number | null
  direction: 'high' | 'low' | null
  matched: boolean | null
  partial: boolean
  data_date: string | null
  data_source: string | null
  missing_reason: string | null
}

export interface QuantRiskEvidenceRow {
  key: string
  strategy_key: QuantRiskStrategyKey
  strategy_label: string
  section_key: string
  section_label: string
  label: string
  cells: QuantRiskEvidenceCell[]
}

export interface QuantRiskEvidenceResponse {
  start_date: string
  end_date: string
  dates: string[]
  rows: QuantRiskEvidenceRow[]
}
