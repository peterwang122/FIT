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
  | 'basis-month'
  | 'breadth-up-pct'
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

export type QuantFilterGroupKey = 'emotion' | 'basis' | 'breadth' | 'turnover' | 'rsi' | 'wr' | 'macd' | 'kdj' | 'ma' | 'boll'

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

export interface QuantHighlightBand {
  tradeDate: string
  color: QuantHighlightColor
}

export interface QuantFilterDataset {
  chart: QuantChartPayload
  emotion: QuantLineSeries | null
  basis: {
    main: QuantLineSeries
    month: QuantLineSeries
  } | null
  breadth: QuantLineSeries | null
  fields: QuantFilterFieldMeta[]
  snapshots: QuantDailyIndicatorSnapshot[]
}

export type QuantStrategyType = 'index' | 'stock'
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

export interface QuantStrategyConfig {
  id: number
  name: string
  notes: string
  strategy_type: QuantStrategyType
  target_code: string
  target_name: string
  indicator_params: QuantIndicatorParams
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
  buy_position_pct: number
  sell_position_pct: number
  execution_price_mode: QuantExecutionPriceMode
  created_at: string | null
  updated_at: string | null
}

export interface QuantStrategyPayload {
  name: string
  notes: string
  strategy_type: QuantStrategyType
  target_code: string
  target_name: string
  indicator_params: QuantIndicatorParams
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
}

export interface QuantEquityCurveResponse {
  strategy: QuantStrategyConfig
  cumulative_return_pct: number
  annualized_return_pct: number
  max_drawdown_pct: number
  points: QuantEquityCurvePoint[]
}
