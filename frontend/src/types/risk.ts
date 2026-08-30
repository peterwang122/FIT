import type { KlineCandle } from './stock'

export type QuantRiskStrategyKey = 'domestic_vulnerability' | 'domestic_deterioration' | 'global_shock' | 'flat_score'
export type QuantRiskLevel = 'stable' | 'yellow' | 'red'
export type QuantRiskDisplayState =
  | 'stable'
  | 'global'
  | 'yellow'
  | 'yellow_global'
  | 'red'
  | 'red_global'
  | 'incomplete'
export type QuantRiskEventEndReason = 'released' | 'data_gap' | 'open'

export interface QuantRiskDashboardPoint {
  trade_date: string
  scoring_mode: 'grouped' | 'flat'
  model_version: string
  yellow_vulnerability: boolean | null
  yellow_score: number | null
  red_escalation: boolean | null
  red_score: number | null
  global_shock: boolean | null
  global_raw_leading: boolean | null
  global_raw_leading_score: number | null
  global_raw_leading_mode: string | null
  global_leading: boolean | null
  global_leading_score: number | null
  global_leading_mode: string | null
  global_leading_trigger_date: string | null
  global_leading_valid_through: string | null
  global_leading_gate_score: number | null
  global_leading_trigger_threshold: number | null
  global_leading_release_threshold: number | null
  global_confirmation_score: number | null
  global_score: number | null
  global_mode: string | null
  overall_score: number | null
  domestic_vulnerability_score: number | null
  domestic_deterioration_score: number | null
  domestic_vulnerability_contribution: number | null
  domestic_deterioration_contribution: number | null
  global_contribution: number | null
  base_state: QuantRiskLevel | null
  display_state: QuantRiskDisplayState | null
  global_active_modules: string[]
  as_of_at: string | null
  decision_trade_date: string | null
  composite_score: number | null
  risk_level: QuantRiskLevel | null
  risk_level_label: string | null
  data_complete: boolean
}

export interface QuantRiskStrategySpan {
  strategy_key: string
  strategy_label: string
  start_date: string
  end_date: string
  release_date: string | null
  active_days: number
  mode: string | null
  key_evidence: string[]
}

export interface QuantRiskStateSpan {
  display_state: QuantRiskDisplayState
  state_label: string
  start_date: string
  end_date: string
  active_days: number
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
  active_strategies: string[]
  strategy_spans: QuantRiskStrategySpan[]
  state_spans: QuantRiskStateSpan[]
  drawdowns: QuantRiskDrawdown[]
}

export interface QuantRiskDashboardResponse {
  target_code: string
  target_name: string
  scoring_mode: 'grouped' | 'flat'
  model_version: string
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
  level_value: number | null
  unit: string | null
  percentile: number | null
  absolute_threshold: number | null
  percentile_threshold: number | null
  score: number | null
  weight: number | null
  contribution: number | null
  direction: 'high' | 'low' | null
  matched: boolean | null
  partial: boolean
  data_date: string | null
  data_source: string | null
  available_at: string | null
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
  target_code: string
  target_name: string
  scoring_mode: 'grouped' | 'flat'
  start_date: string
  end_date: string
  dates: string[]
  rows: QuantRiskEvidenceRow[]
}
