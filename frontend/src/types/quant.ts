export interface MaParams {
  periods: [number, number, number, number]
}

export interface MacdParams {
  fast: number
  slow: number
  signal: number
}

export interface KdjParams {
  period: number
  kSmoothing: number
  dSmoothing: number
}

export interface WrParams {
  period: number
}

export interface RsiParams {
  period: number
}

export interface BollParams {
  period: number
  multiplier: number
}

export interface QuantIndicatorParams {
  ma: MaParams
  macd: MacdParams
  kdj: KdjParams
  wr: WrParams
  rsi: RsiParams
  boll: BollParams
}

export interface QuantLinePoint {
  time: string
  value: number | null
}

export interface QuantHistogramPoint {
  time: string
  value: number | null
  color?: string
}

export interface QuantLineSeries {
  key: string
  label: string
  color: string
  data: QuantLinePoint[]
}

export interface QuantChartPayload {
  ma: QuantLineSeries[]
  boll: {
    upper: QuantLineSeries
    middle: QuantLineSeries
    lower: QuantLineSeries
  }
  macd: {
    dif: QuantLineSeries
    dea: QuantLineSeries
    histogram: QuantHistogramPoint[]
  }
  kdj: {
    k: QuantLineSeries
    d: QuantLineSeries
    j: QuantLineSeries
  }
  wr: QuantLineSeries
  rsi: QuantLineSeries
}

export type QuantFilterFieldKey =
  | 'emotion'
  | 'basis-main'
  | 'basis-main-adjusted'
  | 'basis-month'
  | 'breadth-up-pct'
  | 'vix-open'
  | 'vix-high'
  | 'vix-low'
  | 'vix-close'
  | 'us-vix-open'
  | 'us-vix-high'
  | 'us-vix-low'
  | 'us-vix-close'
  | 'us-fear-greed'
  | 'us-hedge-long'
  | 'us-hedge-short'
  | 'us-hedge-ratio'
  | 'us-put-call-total'
  | 'us-put-call-index'
  | 'us-put-call-equity'
  | 'us-put-call-etf'
  | 'us-yield-3m'
  | 'us-yield-2y'
  | 'us-yield-10y'
  | 'us-yield-spread-10y-2y'
  | 'us-yield-spread-10y-3m'
  | 'us-hy-oas'
  | 'us-hy-oas-change-5d'
  | 'pct-chg'
  | 'turnover-rate'
  | 'rsi'
  | 'wr'
  | 'macd-dif'
  | 'macd-dea'
  | 'macd-histogram'
  | 'kdj-k'
  | 'kdj-d'
  | 'kdj-j'
  | 'ma-1'
  | 'ma-2'
  | 'ma-3'
  | 'ma-4'
  | 'boll-upper'
  | 'boll-middle'
  | 'boll-lower'

export type QuantFilterGroupKey =
  | 'emotion'
  | 'basis'
  | 'breadth'
  | 'vix'
  | 'us-vix'
  | 'fear-greed'
  | 'hedge'
  | 'put-call'
  | 'treasury'
  | 'credit'
  | 'change'
  | 'turnover'
  | 'rsi'
  | 'wr'
  | 'macd'
  | 'kdj'
  | 'ma'
  | 'boll'

export interface QuantFilterFieldMeta {
  key: QuantFilterFieldKey
  group: QuantFilterGroupKey
  label: string
}

export interface QuantFilterValueInput {
  gt: string
  lt: string
}

export type QuantFilterDraft = Record<QuantFilterFieldKey, QuantFilterValueInput>

export interface QuantFilterThreshold {
  gt: number | null
  lt: number | null
}

export type QuantFilterApplied = Partial<Record<QuantFilterFieldKey, QuantFilterThreshold>>

export interface QuantDailyIndicatorSnapshot {
  tradeDate: string
  close: number | null
  high: number | null
  low: number | null
  values: Partial<Record<QuantFilterFieldKey, number | null>>
}

export type QuantHighlightColor = 'blue' | 'red' | 'purple'
export type QuantHighlightVariant = 'solid' | 'striped'

export interface QuantHighlightBand {
  tradeDate: string
  color: QuantHighlightColor
  variant?: QuantHighlightVariant
  blueHitGroups?: number[]
  redHitGroups?: number[]
}

export interface QuantFilterDataset {
  chart: QuantChartPayload
  emotion: QuantLineSeries | null
  basis: {
    main: QuantLineSeries
    adjusted?: QuantLineSeries
    month: QuantLineSeries
  } | null
  breadth: QuantLineSeries | null
  vix: QuantLineSeries | null
  usVix: QuantLineSeries | null
  usFearGreed: QuantLineSeries | null
  usHedgeProxy: QuantLineSeries | null
  usPutCall: QuantLineSeries | null
  usTreasuryYield: {
    spread10y2y: QuantLineSeries
    spread10y3m: QuantLineSeries
  } | null
  usCreditSpread: QuantLineSeries | null
  fields: QuantFilterFieldMeta[]
  snapshots: QuantDailyIndicatorSnapshot[]
}

export type QuantStrategyType = 'index' | 'stock' | 'etf'
export type QuantStrategyEngine = 'snapshot' | 'sequence'
export type QuantTargetMarket = 'cn' | 'hk' | 'us'
export type QuantExecutionPriceMode = 'next_open' | 'next_close' | 'next_best'
export type QuantConflictMode = 'sell_first' | 'buy_first' | 'skip'
export type QuantSignalColor = 'blue' | 'red'
export type QuantBollFilterKey = 'boll-upper' | 'boll-middle' | 'boll-lower'
export type QuantRuleOperator = 'gt' | 'lt'
export type QuantRuleTargetKey = `field:${QuantFilterFieldKey}` | 'boll:close' | 'boll:intraday'

export interface QuantSavedBollFilter {
  gt: QuantBollFilterKey | null
  lt: QuantBollFilterKey | null
  intraday_gt: QuantBollFilterKey | null
  intraday_lt: QuantBollFilterKey | null
}

export interface QuantRuleConditionDraft {
  id: string
  target: QuantRuleTargetKey | ''
  operator: QuantRuleOperator
  value: string
  track: QuantBollFilterKey | ''
}

export interface QuantRuleGroupDraft {
  id: string
  conditions: QuantRuleConditionDraft[]
}

export interface QuantNumericRuleCondition {
  type: 'numeric'
  field: QuantFilterFieldKey
  operator: QuantRuleOperator
  value: number
}

export interface QuantBollRuleCondition {
  type: 'boll'
  mode: 'close' | 'intraday'
  operator: QuantRuleOperator
  track: QuantBollFilterKey
}

export type QuantRuleCondition = QuantNumericRuleCondition | QuantBollRuleCondition

export interface QuantRuleGroup {
  conditions: QuantRuleCondition[]
}

export type QuantFilterGroupSet = QuantRuleGroup[]

export type QuantSequenceSeriesKey = 'market-breadth-up-pct' | 'target-up-pct' | 'target-down-pct'
export type QuantSequenceOperator = 'gt' | 'lt'
export type QuantSequenceMode = 'single_target' | 'market_scan'
export type QuantScanPriceBasis = 'open' | 'close'

export interface QuantSequenceConditionDraft {
  id: string
  series_key: QuantSequenceSeriesKey | ''
  operator: QuantSequenceOperator
  threshold: string
  consecutive_days: string
}

export interface QuantSequenceGroupDraft {
  id: string
  conditions: QuantSequenceConditionDraft[]
}

export interface QuantSequenceCondition {
  series_key: QuantSequenceSeriesKey
  operator: QuantSequenceOperator
  threshold: number
  consecutive_days: number
}

export interface QuantSequenceGroup {
  conditions: QuantSequenceCondition[]
}

export type QuantSequenceGroupSet = QuantSequenceGroup[]

export interface QuantScanTradeConfig {
  initial_capital: number
  buy_amount_per_event: number
  buy_offset_trading_days: number
  sell_offset_trading_days: number
  buy_price_basis: QuantScanPriceBasis
  sell_price_basis: QuantScanPriceBasis
}

export interface QuantScanEvent {
  event_id: string
  target_type: QuantStrategyType
  target_code: string
  target_name: string
  signal_date: string
  buy_date: string | null
  sell_date: string | null
  hit_buy_groups: number[]
  tradable: boolean
  disabled_reason: string | null
  board: string | null
  lot_rule: string | null
  buy_price: number | null
  sell_price: number | null
  planned_quantity: number | null
  planned_buy_amount: number | null
  selected?: boolean | null
  executed?: boolean | null
  skip_reason?: string | null
  actual_quantity?: number | null
  actual_buy_amount?: number | null
  actual_sell_amount?: number | null
  pnl_amount?: number | null
  return_pct?: number | null
}

export interface QuantSequenceSnapshot {
  tradeDate: string
  values: Partial<Record<QuantSequenceSeriesKey, number | null>>
}

export interface QuantStrategyConfig {
  id: number
  name: string
  notes: string
  strategy_engine: QuantStrategyEngine
  sequence_mode: QuantSequenceMode
  strategy_type: QuantStrategyType
  target_market: QuantTargetMarket
  target_code: string
  target_name: string
  indicator_params: QuantIndicatorParams
  buy_sequence_groups: QuantSequenceGroupSet
  sell_sequence_groups: QuantSequenceGroupSet
  scan_trade_config: QuantScanTradeConfig
  blue_filter_groups: QuantFilterGroupSet
  red_filter_groups: QuantFilterGroupSet
  blue_filters: QuantFilterApplied
  red_filters: QuantFilterApplied
  blue_boll_filter: QuantSavedBollFilter
  red_boll_filter: QuantSavedBollFilter
  signal_buy_color: QuantSignalColor
  signal_sell_color: QuantSignalColor
  purple_conflict_mode: QuantConflictMode
  start_date: string | null
  scan_start_date: string | null
  scan_end_date: string | null
  buy_position_pct: number
  sell_position_pct: number
  execution_price_mode: QuantExecutionPriceMode
  created_at: string | null
  updated_at: string | null
}

export interface QuantStrategyPayload {
  name: string
  notes: string
  strategy_engine: QuantStrategyEngine
  sequence_mode: QuantSequenceMode
  strategy_type: QuantStrategyType
  target_market: QuantTargetMarket
  target_code: string
  target_name: string
  indicator_params: QuantIndicatorParams
  buy_sequence_groups: QuantSequenceGroupSet
  sell_sequence_groups: QuantSequenceGroupSet
  scan_trade_config: QuantScanTradeConfig
  blue_filter_groups: QuantFilterGroupSet
  red_filter_groups: QuantFilterGroupSet
  blue_filters: QuantFilterApplied
  red_filters: QuantFilterApplied
  blue_boll_filter: QuantSavedBollFilter
  red_boll_filter: QuantSavedBollFilter
  signal_buy_color: QuantSignalColor
  signal_sell_color: QuantSignalColor
  purple_conflict_mode: QuantConflictMode
  start_date: string | null
  scan_start_date: string | null
  scan_end_date: string | null
  buy_position_pct: number
  sell_position_pct: number
  execution_price_mode: QuantExecutionPriceMode
}

export interface QuantEquityCurvePoint {
  trade_date: string
  nav: number
  benchmark_nav: number | null
  signal: string | null
  close_price: number | null
  position_pct: number
  position_bucket: 'flat' | 'light' | 'medium' | 'heavy' | 'full' | null
}

export interface QuantPositionPair {
  buy_position_pct: number
  sell_position_pct: number
  cumulative_return_pct?: number | null
}

export interface QuantPositionOptimizationTarget {
  value_pct: number
  combinations: QuantPositionPair[]
}

export interface QuantPositionOptimizationResult {
  max_total_return: QuantPositionOptimizationTarget
  min_drawdown: QuantPositionOptimizationTarget
}

export interface QuantEquityCurveResponse {
  strategy: QuantStrategyConfig
  cumulative_return_pct: number
  annualized_return_pct: number
  max_drawdown_pct: number
  points: QuantEquityCurvePoint[]
  position_optimization: QuantPositionOptimizationResult
}

export interface QuantSequenceScanPreviewResponse {
  scan_result_id: string
  strategy_type: QuantStrategyType
  matched_events: QuantScanEvent[]
  matched_event_count: number
  tradable_event_count: number
  total_event_count: number
  page: number
  page_size: number
}

export interface QuantScanResultRef {
  scan_result_id: string
  strategy_type: QuantStrategyType
}

export interface QuantScanEventPage {
  scan_result_id: string
  strategy_type: QuantStrategyType
  matched_events: QuantScanEvent[]
  matched_event_count: number
  tradable_event_count: number
  total_event_count: number
  page: number
  page_size: number
}

export interface QuantScanTargetHits {
  scan_result_id: string
  target_code: string
  target_name: string
  hit_dates: string[]
}

export interface QuantScanBacktestSelection {
  use_all_events: boolean
  excluded_event_ids: string[]
}

export interface QuantSequenceScanBacktestSummary {
  matched_event_count: number
  tradable_event_count: number
  selected_event_count: number
  executed_event_count: number
  skipped_event_count: number
}

export interface QuantSequenceScanBacktestResponse {
  scan_result_id: string
  strategy_type: QuantStrategyType
  matched_events: QuantScanEvent[]
  total_event_count: number
  page: number
  page_size: number
  cumulative_return_pct: number
  annualized_return_pct: number
  max_drawdown_pct: number
  points: QuantEquityCurvePoint[]
  summary: QuantSequenceScanBacktestSummary
}

export interface QuantTargetOption {
  code: string
  name: string
}
