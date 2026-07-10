export type VixBottomStatus = 'true_bottom' | 'false_bottom' | 'true_top' | 'false_top' | 'incomplete'

export interface VixOptionRecommendation {
  rule_id: string
  rule_label: string
  product_code: string
  product_name: string
  exchange: string
  option_type: 'CALL' | 'PUT'
  strategy_type: 'long_call' | 'long_put'
  dte_bucket: string
  expiry_bucket?: string
  expiry_bucket_label?: string
  moneyness_label: string
  holding_days: number
  trade_count: number
  net_return_median: number
  net_return_p25: number
  net_return_p10: number
  win_rate: number
  median_mae: number
  median_mfe: number
  worst_loss: number
  sequence_drawdown_units: number
  balanced_score: number
  defensive_score: number
}

export interface VixThresholdPerformance {
  rule_id: string
  rule_label: string
  event_count: number
  complete_count: number
  bottom_hit_rate_1pct: number | null
  bottom_hit_rate_3pct: number | null
  bottom_hit_rate_5pct: number | null
  top_hit_rate_1pct: number | null
  top_hit_rate_3pct: number | null
  top_hit_rate_5pct: number | null
}

export interface VixIndexSummary {
  index_name: string
  qvix_code: string
  absolute_vix_floor: number
  data_start: string
  data_end: string
  event_count: number
  complete_event_count: number
  bottom_hit_rate_1pct: number | null
  bottom_hit_rate_3pct: number | null
  bottom_hit_rate_5pct: number | null
  top_hit_rate_1pct: number | null
  top_hit_rate_3pct: number | null
  top_hit_rate_5pct: number | null
  recommendation: VixOptionRecommendation | null
  defensive_recommendation: VixOptionRecommendation | null
  walk_forward: {
    trade_count: number
    net_return_median: number
    net_return_p25: number
    net_return_p10: number
    win_rate: number
    median_mae: number
    worst_loss: number
    sequence_drawdown_units: number
  } | null
  stable_ranges: {
    dte_buckets: Record<string, number>
    moneyness: Record<string, number>
    holding_days: Record<string, number>
  }
  threshold_performance: VixThresholdPerformance[]
  reference_checks: Array<{
    signal_date: string
    selected: boolean
    vix_close: number | null
    rule_labels: string
    trade_direction: string
    direction_reason: string
  }>
}

export interface VixOptionEvent {
  index_name: string
  signal_date: string
  rule_ids: string
  rule_labels: string
  vix_close: number
  threshold_value: number
  bottom_status: VixBottomStatus
  prior_60d_drawdown: number | null
  prior_20d_return: number | null
  prior_40d_return: number | null
  trade_direction: 'bullish' | 'bearish'
  direction_reason: string
  future_10d_min_return: number | null
  future_10d_max_return: number | null
  future_20d_min_return: number | null
  future_20d_max_return: number | null
  forward_5d_return: number | null
  forward_10d_return: number | null
  forward_20d_return: number | null
  forward_40d_return: number | null
  hindsight_product_code?: string | null
  hindsight_strategy_type?: string | null
  hindsight_option_type?: string | null
  hindsight_dte_bucket?: string | null
  hindsight_contract_month_label?: string | null
  hindsight_moneyness?: string | null
  hindsight_holding_days?: number | null
  hindsight_net_return?: number | null
  hindsight_mae?: number | null
  hindsight_mfe?: number | null
  hindsight_long_contract?: string | null
  hindsight_long_strike?: number | null
  hindsight_long_strike_label?: string | null
}

export interface VixOptionAnalysisReport {
  generated_at: string
  overall_conclusion?: {
    best_index: string
    summary: string
    rankings: Array<{
      index_name: string
      score: number
      product_code?: string | null
      strategy_type?: string | null
      expiry_bucket_label?: string | null
      moneyness_label?: string | null
      holding_days?: number | null
      net_return_median?: number | null
      net_return_p25?: number | null
      win_rate?: number | null
      median_mae?: number | null
    }>
  }
  methodology: {
    signal: string
    direction: string
    entry: string
    slippage: number
    bottom_definition: string
    top_definition: string
    holding_days: number[]
    dte_buckets: string[]
    moneyness: string[]
    reference_dates: string[]
  }
  index_summaries: VixIndexSummary[]
  events: VixOptionEvent[]
  top_combinations: Array<VixOptionRecommendation & { index_name: string }>
}
