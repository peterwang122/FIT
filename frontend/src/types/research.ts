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

export interface VixThresholdModel {
  mode: 'max_return' | 'balanced'
  label: string
  threshold: number | null
  source_thresholds?: Array<{
    source_name: string
    qvix_code: string
    threshold: number
  }>
  episode_count: number
  event_date_count: number
  composite_score: number | null
  recommendation: VixOptionRecommendation | null
}

export interface VixIndexSummary {
  index_name: string
  qvix_code: string
  absolute_vix_floor: number | null
  data_start: string
  data_end: string
  event_count: number
  episode_count?: number
  display_event_count?: number
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
  threshold_models: VixThresholdModel[]
  reference_checks: Array<{
    signal_date: string
    selected: boolean
    vix_close: number | null
    vix_high?: number | null
    rule_labels: string
    trade_direction: string
    direction_reason: string
  }>
}

export interface VixEventTopTrade {
  entry_date?: string | null
  exit_date?: string | null
  product_code: string
  product_name: string
  exchange: string
  strategy_type: 'long_call' | 'long_put'
  option_type: 'CALL' | 'PUT'
  expiry_bucket?: string | null
  expiry_bucket_label?: string | null
  dte_bucket?: string | null
  contract_month_label?: string | null
  moneyness?: string | null
  moneyness_label?: string | null
  holding_days: number
  long_contract_code: string
  long_contract_month?: string | null
  long_strike: number
  long_strike_label?: string | null
  underlying_entry_price?: number | null
  entry_debit?: number | null
  exit_value?: number | null
  gross_return?: number | null
  net_return: number
  mae: number
  mfe: number
}

export interface VixOptionContractCandle {
  trade_date: string
  open: number
  high: number
  low: number
  close: number
  volume: number | null
  turnover: number | null
  open_interest: number | null
}

export interface VixOptionContractKline {
  exchange: string
  contract_code: string
  underlying_code: string | null
  candles: VixOptionContractCandle[]
}

export interface VixOptionEvent {
  index_name: string
  signal_date: string
  threshold_mode: 'max_return' | 'balanced'
  threshold_mode_label: string
  episode_id: string
  episode_start_date: string
  episode_peak_date: string
  event_type: 'first_cross' | 'range_peak'
  event_type_label: string
  vix_source?: string
  vix_source_label?: string
  rule_ids: string
  rule_labels: string
  vix_high: number
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
  hindsight_product_name?: string | null
  hindsight_exchange?: string | null
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
  top_trades: VixEventTopTrade[]
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
      product_name?: string | null
      exchange?: string | null
      strategy_type?: string | null
      expiry_bucket_label?: string | null
      moneyness_label?: string | null
      holding_days?: number | null
      trade_count?: number | null
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

export interface Csi1000FuturesContractHolding {
  contract: string
  start_date: string
  end_date: string
  entry_price: number | null
  exit_price: number | null
  end_action: 'expiry' | 'wave_end' | 'provisional_end'
}

export interface Csi1000FuturesContractResult {
  result_id: string
  valid: boolean
  reason?: string
  rank: number | null
  tenor_index: number
  tenor_label: string
  start_contract: string
  start_expiry: string
  entry_contract: string
  entry_date: string
  entry_price: number
  exit_contract: string
  exit_date: string
  exit_price: number
  direction: 'up' | 'down'
  holding_days: number
  roll_count: number
  rolls: Array<{
    expired_contract: string
    expiry_date: string
    next_contract: string
    next_entry_date: string
    expiry_price: number
    next_entry_price: number
  }>
  contract_path: Csi1000FuturesContractHolding[]
  gross_points: number
  gross_pnl: number
  fee: number
  net_pnl: number
  notional_return_pct: number
}

export interface Csi1000FuturesWave {
  wave_id: number
  direction: 'up' | 'down'
  direction_label: string
  complete: boolean
  start_date: string
  start_value: number
  start_kind: 'low' | 'high'
  end_date: string
  end_value: number
  end_kind: 'low' | 'high'
  confirmation_date: string | null
  low_date: string
  low_value: number
  high_date: string
  high_value: number
  index_change_pct: number
  amplitude_pct: number
  best_tenor_index: number | null
  best_start_contract: string | null
  best_result_id: string | null
  contract_results: Csi1000FuturesContractResult[]
}

export interface Csi1000FuturesReport {
  generated_at: string
  title: string
  underlying: { code: string; name: string }
  data_range: { start: string; end: string }
  methodology: {
    zigzag_threshold: number
    entry_exit: string
    roll: string
    multiplier: number
    fee_rate: number
    slippage: number
    hindsight_only: boolean
  }
  sample: {
    wave_count: number
    completed_wave_count: number
    up_wave_count: number
    down_wave_count: number
    provisional_wave_count: number
  }
  direction_summaries: Record<'up' | 'down', {
    direction: 'up' | 'down'
    wave_count: number
    best_tenor_index: number | null
    tenors: Array<{
      tenor_index: number
      tenor_label: string
      wave_count: number
      total_net_pnl: number
      average_net_pnl: number | null
      median_net_pnl: number | null
      win_rate: number | null
      best_wave_count: number
    }>
  }>
  waves: Csi1000FuturesWave[]
  index_candles: Array<{
    trade_date: string
    open: number
    high: number
    low: number
    close: number
    pivot: string | null
  }>
}
