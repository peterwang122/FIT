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

export interface BollParams {
  period: number
  multiplier: number
}

export interface QuantIndicatorParams {
  ma: MaParams
  macd: MacdParams
  kdj: KdjParams
  wr: WrParams
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
}

export type QuantFilterFieldKey =
  | 'emotion'
  | 'basis-main'
  | 'basis-month'
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

export type QuantFilterGroupKey = 'emotion' | 'basis' | 'wr' | 'macd' | 'kdj' | 'ma' | 'boll'

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
  values: Partial<Record<QuantFilterFieldKey, number | null>>
}

export type QuantHighlightColor = 'blue' | 'red' | 'purple'

export interface QuantHighlightBand {
  tradeDate: string
  color: QuantHighlightColor
}

export interface QuantFilterDataset {
  chart: QuantChartPayload
  emotion: QuantLineSeries
  basis: {
    main: QuantLineSeries
    month: QuantLineSeries
  }
  fields: QuantFilterFieldMeta[]
  snapshots: QuantDailyIndicatorSnapshot[]
}
