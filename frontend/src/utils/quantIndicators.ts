import type {
  QuantChartPayload,
  QuantDailyIndicatorSnapshot,
  QuantFilterDataset,
  QuantFilterDraft,
  QuantFilterFieldKey,
  QuantFilterFieldMeta,
  QuantHistogramPoint,
  QuantIndicatorParams,
  QuantLinePoint,
  QuantLineSeries,
} from '../types/quant'
import type { FuturesBasisPoint, IndexEmotionPoint } from '../types/stock'

export type QuantIndicatorCandle = {
  trade_date: string
  high: number
  low: number
  close: number
}

const CORE_EMOTION_INDEX_NAMES = ['上证50', '沪深300', '中证500', '中证1000'] as const

export const QUANT_FILTER_FIELD_KEYS: QuantFilterFieldKey[] = [
  'emotion',
  'basis-main',
  'basis-month',
  'wr',
  'macd-dif',
  'macd-dea',
  'macd-histogram',
  'kdj-k',
  'kdj-d',
  'kdj-j',
]

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function sortCandles(candles: QuantIndicatorCandle[]): QuantIndicatorCandle[] {
  return [...candles]
    .map((item) => ({
      trade_date: item.trade_date,
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
    }))
    .filter((item) => isFiniteNumber(item.high) && isFiniteNumber(item.low) && isFiniteNumber(item.close))
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date))
}

function createLinePoint(time: string, value: number | null): QuantLinePoint {
  return {
    time,
    value: isFiniteNumber(value) ? value : null,
  }
}

function calculateSma(values: number[], period: number): Array<number | null> {
  const result: Array<number | null> = new Array(values.length).fill(null)
  let rollingSum = 0

  for (let index = 0; index < values.length; index += 1) {
    rollingSum += values[index]
    if (index >= period) {
      rollingSum -= values[index - period]
    }
    if (index >= period - 1) {
      result[index] = rollingSum / period
    }
  }

  return result
}

function calculateStdDev(values: number[], period: number, means: Array<number | null>): Array<number | null> {
  const result: Array<number | null> = new Array(values.length).fill(null)

  for (let index = period - 1; index < values.length; index += 1) {
    const mean = means[index]
    if (!isFiniteNumber(mean)) {
      continue
    }
    let varianceSum = 0
    for (let offset = index - period + 1; offset <= index; offset += 1) {
      const diff = values[offset] - mean
      varianceSum += diff * diff
    }
    result[index] = Math.sqrt(varianceSum / period)
  }

  return result
}

function calculateEma(values: number[], period: number): number[] {
  const multiplier = 2 / (period + 1)
  const result: number[] = new Array(values.length).fill(0)
  if (!values.length) {
    return result
  }

  result[0] = values[0]
  for (let index = 1; index < values.length; index += 1) {
    result[index] = values[index] * multiplier + result[index - 1] * (1 - multiplier)
  }
  return result
}

function buildLineSeries(
  key: string,
  label: string,
  color: string,
  times: string[],
  values: Array<number | null>,
): QuantLineSeries {
  return {
    key,
    label,
    color,
    data: times.map((time, index) => createLinePoint(time, values[index] ?? null)),
  }
}

function calculateMa(times: string[], closes: number[], periods: number[]): QuantLineSeries[] {
  const palette = ['#2563eb', '#f97316', '#8b5cf6', '#0f766e']
  return periods.map((period, index) =>
    buildLineSeries(`ma-${period}`, `MA${period}`, palette[index] ?? '#2563eb', times, calculateSma(closes, period)),
  )
}

function calculateBoll(times: string[], closes: number[], period: number, multiplier: number) {
  const middle = calculateSma(closes, period)
  const stdDev = calculateStdDev(closes, period, middle)
  const upper = middle.map((value, index) =>
    isFiniteNumber(value) && isFiniteNumber(stdDev[index]) ? value + multiplier * (stdDev[index] as number) : null,
  )
  const lower = middle.map((value, index) =>
    isFiniteNumber(value) && isFiniteNumber(stdDev[index]) ? value - multiplier * (stdDev[index] as number) : null,
  )

  return {
    upper: buildLineSeries('boll-upper', 'BOLL上轨', '#ef4444', times, upper),
    middle: buildLineSeries('boll-middle', 'BOLL中轨', '#0f172a', times, middle),
    lower: buildLineSeries('boll-lower', 'BOLL下轨', '#22c55e', times, lower),
  }
}

function calculateMacd(times: string[], closes: number[], fast: number, slow: number, signal: number) {
  const emaFast = calculateEma(closes, fast)
  const emaSlow = calculateEma(closes, slow)
  const dif: Array<number | null> = closes.map((_, index) => (index >= slow - 1 ? emaFast[index] - emaSlow[index] : null))

  const dea: Array<number | null> = new Array(closes.length).fill(null)
  let seedIndex = -1
  let seedValue = 0

  for (let index = slow - 1; index < dif.length; index += 1) {
    const slice = dif.slice(index - signal + 1, index + 1)
    if (slice.length === signal && slice.every((item) => isFiniteNumber(item))) {
      seedIndex = index
      seedValue = slice.reduce((sum, item) => sum + (item as number), 0) / signal
      dea[index] = seedValue
      break
    }
  }

  if (seedIndex >= 0) {
    const multiplier = 2 / (signal + 1)
    for (let index = seedIndex + 1; index < dif.length; index += 1) {
      const currentDif = dif[index]
      const prevDea = dea[index - 1]
      if (!isFiniteNumber(currentDif) || !isFiniteNumber(prevDea)) {
        continue
      }
      dea[index] = currentDif * multiplier + prevDea * (1 - multiplier)
    }
  }

  const histogram: QuantHistogramPoint[] = times.map((time, index) => {
    const currentDif = dif[index]
    const currentDea = dea[index]
    const value = isFiniteNumber(currentDif) && isFiniteNumber(currentDea) ? 2 * (currentDif - currentDea) : null
    return {
      time,
      value,
      color: isFiniteNumber(value) ? (value >= 0 ? '#ef4444' : '#10b981') : undefined,
    }
  })

  return {
    dif: buildLineSeries('macd-dif', 'DIF', '#2563eb', times, dif),
    dea: buildLineSeries('macd-dea', 'DEA', '#f59e0b', times, dea),
    histogram,
  }
}

function calculateKdj(
  times: string[],
  candles: QuantIndicatorCandle[],
  period: number,
  kSmoothing: number,
  dSmoothing: number,
) {
  const kValues: Array<number | null> = new Array(candles.length).fill(null)
  const dValues: Array<number | null> = new Array(candles.length).fill(null)
  const jValues: Array<number | null> = new Array(candles.length).fill(null)
  let previousK = 50
  let previousD = 50

  for (let index = period - 1; index < candles.length; index += 1) {
    const window = candles.slice(index - period + 1, index + 1)
    const highestHigh = Math.max(...window.map((item) => item.high))
    const lowestLow = Math.min(...window.map((item) => item.low))
    const denominator = highestHigh - lowestLow
    const rsv = denominator === 0 ? 50 : ((candles[index].close - lowestLow) / denominator) * 100
    const currentK = ((kSmoothing - 1) * previousK + rsv) / kSmoothing
    const currentD = ((dSmoothing - 1) * previousD + currentK) / dSmoothing
    const currentJ = 3 * currentK - 2 * currentD

    kValues[index] = currentK
    dValues[index] = currentD
    jValues[index] = currentJ
    previousK = currentK
    previousD = currentD
  }

  return {
    k: buildLineSeries('kdj-k', 'K', '#2563eb', times, kValues),
    d: buildLineSeries('kdj-d', 'D', '#ef4444', times, dValues),
    j: buildLineSeries('kdj-j', 'J', '#0f766e', times, jValues),
  }
}

function calculateWr(times: string[], candles: QuantIndicatorCandle[], period: number) {
  const wrValues: Array<number | null> = new Array(candles.length).fill(null)

  for (let index = period - 1; index < candles.length; index += 1) {
    const window = candles.slice(index - period + 1, index + 1)
    const highestHigh = Math.max(...window.map((item) => item.high))
    const lowestLow = Math.min(...window.map((item) => item.low))
    const denominator = highestHigh - lowestLow
    wrValues[index] = denominator === 0 ? 0 : ((highestHigh - candles[index].close) / denominator) * 100
  }

  return buildLineSeries('wr', 'WR', '#7c3aed', times, wrValues)
}

export function calculateQuantIndicators(candles: QuantIndicatorCandle[], params: QuantIndicatorParams): QuantChartPayload {
  const sortedCandles = sortCandles(candles)
  const times = sortedCandles.map((item) => item.trade_date)
  const closes = sortedCandles.map((item) => item.close)

  return {
    ma: calculateMa(times, closes, [...params.ma.periods]),
    boll: calculateBoll(times, closes, params.boll.period, params.boll.multiplier),
    macd: calculateMacd(times, closes, params.macd.fast, params.macd.slow, params.macd.signal),
    kdj: calculateKdj(times, sortedCandles, params.kdj.period, params.kdj.kSmoothing, params.kdj.dSmoothing),
    wr: calculateWr(times, sortedCandles, params.wr.period),
  }
}

export function calculateSmaValueByDate(candles: QuantIndicatorCandle[], period: number) {
  const sortedCandles = sortCandles(candles)
  const closes = sortedCandles.map((item) => item.close)
  const smaValues = calculateSma(closes, period)

  return new Map(sortedCandles.map((item, index) => [item.trade_date, smaValues[index] ?? null]))
}

export function createEmptyQuantFilterDraft(): QuantFilterDraft {
  return QUANT_FILTER_FIELD_KEYS.reduce(
    (draft, key) => {
      draft[key] = { gt: '', lt: '' }
      return draft
    },
    {} as QuantFilterDraft,
  )
}

function buildEmotionValueByDate(symbolName: string, emotionPoints: IndexEmotionPoint[]) {
  const grouped = new Map<string, { sum: number; count: number }>()

  for (const point of emotionPoints) {
    const value = Number(point.emotion_value)
    if (!Number.isFinite(value)) {
      continue
    }

    if (symbolName === '上证指数') {
      if (!CORE_EMOTION_INDEX_NAMES.includes(point.index_name as (typeof CORE_EMOTION_INDEX_NAMES)[number])) {
        continue
      }
    } else if (point.index_name !== symbolName) {
      continue
    }

    const current = grouped.get(point.emotion_date) ?? { sum: 0, count: 0 }
    current.sum += value
    current.count += 1
    grouped.set(point.emotion_date, current)
  }

  return new Map(
    [...grouped.entries()].map(([date, info]) => [date, info.count ? info.sum / info.count : 50]),
  )
}

export function calculateQuantEmotionSeries(
  candles: QuantIndicatorCandle[],
  symbolName: string,
  emotionPoints: IndexEmotionPoint[],
): QuantLineSeries {
  const sortedCandles = sortCandles(candles)
  const emotionValueByDate = buildEmotionValueByDate(symbolName, emotionPoints)

  return {
    key: 'emotion',
    label: symbolName === '上证指数' ? '四大指数平均情绪' : `${symbolName}情绪`,
    color: '#0f4c75',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, emotionValueByDate.get(item.trade_date) ?? 50)),
  }
}

export function calculateQuantFuturesBasisSeries(
  candles: QuantIndicatorCandle[],
  symbolName: string,
  basisPoints: FuturesBasisPoint[],
) {
  const sortedCandles = sortCandles(candles)
  const grouped = new Map<string, Map<string, { main_basis: number | null; month_basis: number | null }>>()

  for (const point of basisPoints) {
    const indexName = String(point.index_name ?? '').trim()
    const tradeDate = String(point.trade_date ?? '').trim()
    if (!indexName || !tradeDate) {
      continue
    }

    const rowsByDate = grouped.get(indexName) ?? new Map<string, { main_basis: number | null; month_basis: number | null }>()
    rowsByDate.set(tradeDate, {
      main_basis: isFiniteNumber(point.main_basis) ? point.main_basis : null,
      month_basis: isFiniteNumber(point.month_basis) ? point.month_basis : null,
    })
    grouped.set(indexName, rowsByDate)
  }

  const mainValues = sortedCandles.map((item) => {
    if (symbolName === '上证指数') {
      const total = CORE_EMOTION_INDEX_NAMES.reduce((sum, indexName) => {
        const value = grouped.get(indexName)?.get(item.trade_date)?.main_basis
        return sum + (isFiniteNumber(value) ? value : 0)
      }, 0)
      return total / CORE_EMOTION_INDEX_NAMES.length
    }

    const value = grouped.get(symbolName)?.get(item.trade_date)?.main_basis
    return isFiniteNumber(value) ? value : 0
  })

  const monthValues = sortedCandles.map((item) => {
    if (symbolName === '上证指数') {
      const total = CORE_EMOTION_INDEX_NAMES.reduce((sum, indexName) => {
        const value = grouped.get(indexName)?.get(item.trade_date)?.month_basis
        return sum + (isFiniteNumber(value) ? value : 0)
      }, 0)
      return total / CORE_EMOTION_INDEX_NAMES.length
    }

    const value = grouped.get(symbolName)?.get(item.trade_date)?.month_basis
    return isFiniteNumber(value) ? value : 0
  })

  const times = sortedCandles.map((item) => item.trade_date)
  return {
    main: buildLineSeries('basis-main', '主连期现差', '#dc2626', times, mainValues),
    month: buildLineSeries('basis-month', '月连期现差', '#2563eb', times, monthValues),
  }
}

function buildQuantFilterFields(payload: QuantChartPayload): QuantFilterFieldMeta[] {
  return [
    { key: 'emotion', group: 'emotion', label: '情绪指标' },
    { key: 'basis-main', group: 'basis', label: '主连期现差' },
    { key: 'basis-month', group: 'basis', label: '月连期现差' },
    { key: 'wr', group: 'wr', label: payload.wr.label },
    { key: 'macd-dif', group: 'macd', label: payload.macd.dif.label },
    { key: 'macd-dea', group: 'macd', label: payload.macd.dea.label },
    { key: 'macd-histogram', group: 'macd', label: 'MACD柱' },
    { key: 'kdj-k', group: 'kdj', label: payload.kdj.k.label },
    { key: 'kdj-d', group: 'kdj', label: payload.kdj.d.label },
    { key: 'kdj-j', group: 'kdj', label: payload.kdj.j.label },
    { key: 'ma-1', group: 'ma', label: payload.ma[0]?.label ?? 'MA1' },
    { key: 'ma-2', group: 'ma', label: payload.ma[1]?.label ?? 'MA2' },
    { key: 'ma-3', group: 'ma', label: payload.ma[2]?.label ?? 'MA3' },
    { key: 'ma-4', group: 'ma', label: payload.ma[3]?.label ?? 'MA4' },
    { key: 'boll-upper', group: 'boll', label: payload.boll.upper.label },
    { key: 'boll-middle', group: 'boll', label: payload.boll.middle.label },
    { key: 'boll-lower', group: 'boll', label: payload.boll.lower.label },
  ]
}

function buildQuantDailySnapshots(
  payload: QuantChartPayload,
  emotionSeries: QuantLineSeries,
  basisSeries: QuantFilterDataset['basis'],
  candles: QuantIndicatorCandle[],
): QuantDailyIndicatorSnapshot[] {
  const sortedCandles = sortCandles(candles)
  const times = payload.ma[0]?.data.map((item) => item.time) ?? []

  return times.map((tradeDate, index) => ({
    tradeDate,
    close: sortedCandles[index]?.close ?? null,
    values: {
      emotion: emotionSeries.data[index]?.value ?? null,
      'basis-main': basisSeries.main.data[index]?.value ?? null,
      'basis-month': basisSeries.month.data[index]?.value ?? null,
      wr: payload.wr.data[index]?.value ?? null,
      'macd-dif': payload.macd.dif.data[index]?.value ?? null,
      'macd-dea': payload.macd.dea.data[index]?.value ?? null,
      'macd-histogram': payload.macd.histogram[index]?.value ?? null,
      'kdj-k': payload.kdj.k.data[index]?.value ?? null,
      'kdj-d': payload.kdj.d.data[index]?.value ?? null,
      'kdj-j': payload.kdj.j.data[index]?.value ?? null,
      'ma-1': payload.ma[0]?.data[index]?.value ?? null,
      'ma-2': payload.ma[1]?.data[index]?.value ?? null,
      'ma-3': payload.ma[2]?.data[index]?.value ?? null,
      'ma-4': payload.ma[3]?.data[index]?.value ?? null,
      'boll-upper': payload.boll.upper.data[index]?.value ?? null,
      'boll-middle': payload.boll.middle.data[index]?.value ?? null,
      'boll-lower': payload.boll.lower.data[index]?.value ?? null,
    },
  }))
}

export function buildQuantFilterDataset(
  candles: QuantIndicatorCandle[],
  params: QuantIndicatorParams,
  symbolName: string,
  emotionPoints: IndexEmotionPoint[],
  basisPoints: FuturesBasisPoint[],
): QuantFilterDataset {
  const chart = calculateQuantIndicators(candles, params)
  const emotion = calculateQuantEmotionSeries(candles, symbolName, emotionPoints)
  const basis = calculateQuantFuturesBasisSeries(candles, symbolName, basisPoints)

  return {
    chart,
    emotion,
    basis,
    fields: buildQuantFilterFields(chart),
    snapshots: buildQuantDailySnapshots(chart, emotion, basis, candles),
  }
}
