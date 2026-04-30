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
import type {
  FuturesBasisPoint,
  IndexBreadthPoint,
  IndexEmotionPoint,
  IndexUsCreditSpreadPoint,
  IndexUsFearGreedPoint,
  IndexUsHedgeProxyPoint,
  IndexUsPutCallPoint,
  IndexUsTreasuryYieldPoint,
  IndexUsVixPoint,
  IndexVixPoint,
} from '../types/stock'

export type QuantIndicatorCandle = {
  trade_date: string
  high: number
  low: number
  close: number
  pct_chg?: number | null
  turnover_rate?: number | null
}

const SHANGHAI_INDEX_NAME = '上证指数'
const BEIJING50_INDEX_NAME = '北证50'
const CORE_EMOTION_INDEX_NAMES = ['上证50', '沪深300', '中证500', '中证1000'] as const
const SHARED_AUXILIARY_INDEX_NAMES = [SHANGHAI_INDEX_NAME, BEIJING50_INDEX_NAME] as const
const VIX_INDEX_NAMES = ['上证50', '沪深300', '中证500'] as const

function usesSharedAuxiliarySeries(symbolName: string) {
  return SHARED_AUXILIARY_INDEX_NAMES.includes(symbolName as (typeof SHARED_AUXILIARY_INDEX_NAMES)[number])
}

function supportsVixSeries(symbolName: string) {
  return VIX_INDEX_NAMES.includes(symbolName as (typeof VIX_INDEX_NAMES)[number])
}

export const INDEX_QUANT_FILTER_FIELD_KEYS: QuantFilterFieldKey[] = [
  'emotion',
  'basis-main',
  'basis-month',
  'breadth-up-pct',
  'vix-open',
  'vix-high',
  'vix-low',
  'vix-close',
  'rsi',
  'wr',
  'macd-dif',
  'macd-dea',
  'macd-histogram',
  'kdj-k',
  'kdj-d',
  'kdj-j',
]

export const US_INDEX_QUANT_FILTER_FIELD_KEYS: QuantFilterFieldKey[] = [
  'basis-main',
  'basis-main-adjusted',
  'us-vix-open',
  'us-vix-high',
  'us-vix-low',
  'us-vix-close',
  'us-fear-greed',
  'us-hedge-long',
  'us-hedge-short',
  'us-hedge-ratio',
  'us-put-call-total',
  'us-put-call-index',
  'us-put-call-equity',
  'us-put-call-etf',
  'us-yield-3m',
  'us-yield-2y',
  'us-yield-10y',
  'us-yield-spread-10y-2y',
  'us-yield-spread-10y-3m',
  'us-hy-oas',
  'us-hy-oas-change-5d',
  'pct-chg',
  'turnover-rate',
  'rsi',
  'wr',
  'macd-dif',
  'macd-dea',
  'macd-histogram',
  'kdj-k',
  'kdj-d',
  'kdj-j',
  'ma-1',
  'ma-2',
  'ma-3',
  'ma-4',
]

export const STOCK_QUANT_FILTER_FIELD_KEYS: QuantFilterFieldKey[] = [
  'pct-chg',
  'turnover-rate',
  'rsi',
  'wr',
  'macd-dif',
  'macd-dea',
  'macd-histogram',
  'kdj-k',
  'kdj-d',
  'kdj-j',
  'ma-1',
  'ma-2',
  'ma-3',
  'ma-4',
]

export const ALL_QUANT_FILTER_FIELD_KEYS: QuantFilterFieldKey[] = [
  ...new Set([...INDEX_QUANT_FILTER_FIELD_KEYS, ...US_INDEX_QUANT_FILTER_FIELD_KEYS, ...STOCK_QUANT_FILTER_FIELD_KEYS]),
]

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function alignSparseRowsToTradeDates<T>(
  tradeDates: string[],
  rows: T[],
  dateSelector: (row: T) => string | null | undefined,
) {
  const sortedTradeDates = [...tradeDates].filter(Boolean).sort((left, right) => left.localeCompare(right))
  if (!sortedTradeDates.length || !rows.length) {
    return new Map<string, T>()
  }

  const sortedRows = [...rows]
    .filter((row) => Boolean(dateSelector(row)))
    .sort((left, right) => String(dateSelector(left)).localeCompare(String(dateSelector(right))))

  const aligned = new Map<string, T>()
  let tradeIndex = 0
  for (const row of sortedRows) {
    const rowDate = String(dateSelector(row))
    while (tradeIndex < sortedTradeDates.length && sortedTradeDates[tradeIndex] < rowDate) {
      tradeIndex += 1
    }
    if (tradeIndex < sortedTradeDates.length) {
      aligned.set(sortedTradeDates[tradeIndex], row)
    }
  }
  return aligned
}

function sortCandles(candles: QuantIndicatorCandle[]): QuantIndicatorCandle[] {
  return [...candles]
    .map((item) => ({
      trade_date: item.trade_date,
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
      pct_chg:
        item.pct_chg === null || item.pct_chg === undefined
          ? null
          : isFiniteNumber(Number(item.pct_chg))
            ? Number(item.pct_chg)
            : null,
      turnover_rate:
        item.turnover_rate === null || item.turnover_rate === undefined
          ? null
          : isFiniteNumber(Number(item.turnover_rate))
            ? Number(item.turnover_rate)
            : null,
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

  for (let index = slow - 1; index < dif.length; index += 1) {
    const slice = dif.slice(index - signal + 1, index + 1)
    if (slice.length === signal && slice.every((item) => isFiniteNumber(item))) {
      dea[index] = slice.reduce((sum, item) => sum + (item as number), 0) / signal
      seedIndex = index
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

function calculateRsi(times: string[], closes: number[], period: number) {
  const rsiValues: Array<number | null> = new Array(closes.length).fill(null)
  if (closes.length <= period) {
    return buildLineSeries('rsi', `RSI${period}`, '#db2777', times, rsiValues)
  }

  let gainSum = 0
  let lossSum = 0
  for (let index = 1; index <= period; index += 1) {
    const change = closes[index] - closes[index - 1]
    if (change >= 0) gainSum += change
    else lossSum += Math.abs(change)
  }

  let averageGain = gainSum / period
  let averageLoss = lossSum / period
  rsiValues[period] = averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss)

  for (let index = period + 1; index < closes.length; index += 1) {
    const change = closes[index] - closes[index - 1]
    const gain = change > 0 ? change : 0
    const loss = change < 0 ? Math.abs(change) : 0
    averageGain = (averageGain * (period - 1) + gain) / period
    averageLoss = (averageLoss * (period - 1) + loss) / period
    rsiValues[index] = averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss)
  }

  return buildLineSeries('rsi', `RSI${period}`, '#db2777', times, rsiValues)
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
    rsi: calculateRsi(times, closes, params.rsi.period),
  }
}

export function calculateSmaValueByDate(candles: QuantIndicatorCandle[], period: number) {
  const sortedCandles = sortCandles(candles)
  const closes = sortedCandles.map((item) => item.close)
  const smaValues = calculateSma(closes, period)

  return new Map(sortedCandles.map((item, index) => [item.trade_date, smaValues[index] ?? null]))
}

export function createEmptyQuantFilterDraft(keys: QuantFilterFieldKey[] = ALL_QUANT_FILTER_FIELD_KEYS): QuantFilterDraft {
  const draft = {} as QuantFilterDraft
  ALL_QUANT_FILTER_FIELD_KEYS.forEach((key) => {
    draft[key] = { gt: '', lt: '' }
  })
  keys.forEach((key) => {
    if (!draft[key]) {
      draft[key] = { gt: '', lt: '' }
    }
  })
  return draft
}

function buildEmotionValueByDate(symbolName: string, emotionPoints: IndexEmotionPoint[]) {
  const grouped = new Map<string, { sum: number; count: number }>()

  for (const point of emotionPoints) {
    const value = Number(point.emotion_value)
    if (!Number.isFinite(value)) {
      continue
    }

    if (usesSharedAuxiliarySeries(symbolName)) {
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

  return new Map([...grouped.entries()].map(([date, info]) => [date, info.count ? info.sum / info.count : 50]))
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
    label: usesSharedAuxiliarySeries(symbolName) ? '四大指数平均情绪' : `${symbolName}情绪`,
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
  const grouped = new Map<
    string,
    Map<string, { main_basis: number | null; main_basis_adjusted: number | null; month_basis: number | null }>
  >()

  for (const point of basisPoints) {
    const indexName = String(point.index_name ?? '').trim()
    const tradeDate = String(point.trade_date ?? '').trim()
    if (!indexName || !tradeDate) {
      continue
    }

    const rowsByDate =
      grouped.get(indexName) ??
      new Map<string, { main_basis: number | null; main_basis_adjusted: number | null; month_basis: number | null }>()
    rowsByDate.set(tradeDate, {
      main_basis: isFiniteNumber(point.main_basis) ? point.main_basis : null,
      main_basis_adjusted: isFiniteNumber(point.main_basis_adjusted) ? point.main_basis_adjusted : null,
      month_basis: isFiniteNumber(point.month_basis) ? point.month_basis : null,
    })
    grouped.set(indexName, rowsByDate)
  }

  const mainValues = sortedCandles.map((item) => {
    if (usesSharedAuxiliarySeries(symbolName)) {
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
    if (usesSharedAuxiliarySeries(symbolName)) {
      const total = CORE_EMOTION_INDEX_NAMES.reduce((sum, indexName) => {
        const value = grouped.get(indexName)?.get(item.trade_date)?.month_basis
        return sum + (isFiniteNumber(value) ? value : 0)
      }, 0)
      return total / CORE_EMOTION_INDEX_NAMES.length
    }

    const value = grouped.get(symbolName)?.get(item.trade_date)?.month_basis
    return isFiniteNumber(value) ? value : 0
  })

  const adjustedValues = sortedCandles.map((item) => {
    const value = grouped.get(symbolName)?.get(item.trade_date)?.main_basis_adjusted
    const fallback = grouped.get(symbolName)?.get(item.trade_date)?.main_basis
    return isFiniteNumber(value) ? value : isFiniteNumber(fallback) ? fallback : 0
  })

  const times = sortedCandles.map((item) => item.trade_date)
  return {
    main: buildLineSeries('basis-main', '主连期现差', '#dc2626', times, mainValues),
    adjusted: buildLineSeries('basis-main-adjusted', '换月调整期现差', '#2563eb', times, adjustedValues),
    month: buildLineSeries('basis-month', '月连期现差', '#2563eb', times, monthValues),
  }
}

export function calculateQuantBreadthSeries(
  candles: QuantIndicatorCandle[],
  breadthPoints: IndexBreadthPoint[],
): QuantLineSeries {
  const sortedCandles = sortCandles(candles)
  const breadthByDate = new Map(
    breadthPoints
      .filter((item) => Number.isFinite(Number(item.up_ratio_pct)))
      .map((item) => [item.trade_date, Number(item.up_ratio_pct)]),
  )

  return {
    key: 'breadth-up-pct',
    label: '上涨家数百分比',
    color: '#0ea5e9',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, breadthByDate.get(item.trade_date) ?? 0)),
  }
}

export function calculateQuantVixSeries(
  candles: QuantIndicatorCandle[],
  supportsVix: boolean,
  vixPoints: IndexVixPoint[],
): QuantLineSeries | null {
  if (!supportsVix) {
    return null
  }

  const sortedCandles = sortCandles(candles)
  const closeByDate = new Map(
    vixPoints
      .filter((item) => Number.isFinite(Number(item.close_price)))
      .map((item) => [item.trade_date, Number(item.close_price)]),
  )

  return {
    key: 'vix-close',
    label: 'VIX收',
    color: '#7c3aed',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, closeByDate.get(item.trade_date) ?? null)),
  }
}

export function calculateQuantUsVixSeries(
  candles: QuantIndicatorCandle[],
  includeUsVix: boolean,
  usVixPoints: IndexUsVixPoint[],
): QuantLineSeries | null {
  if (!includeUsVix) {
    return null
  }

  const sortedCandles = sortCandles(candles)
  const closeByDate = new Map(
    usVixPoints
      .filter((item) => Number.isFinite(Number(item.close_value)))
      .map((item) => [item.trade_date, Number(item.close_value)]),
  )

  return {
    key: 'us-vix-close',
    label: '美股VIX收',
    color: '#b45309',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, closeByDate.get(item.trade_date) ?? null)),
  }
}

export function calculateQuantUsFearGreedSeries(
  candles: QuantIndicatorCandle[],
  includeFearGreed: boolean,
  usFearGreedPoints: IndexUsFearGreedPoint[],
): QuantLineSeries | null {
  if (!includeFearGreed) {
    return null
  }

  const sortedCandles = sortCandles(candles)
  const valueByDate = new Map(
    usFearGreedPoints
      .filter((item) => Number.isFinite(Number(item.fear_greed_value)))
      .map((item) => [item.trade_date, Number(item.fear_greed_value)]),
  )

  return {
    key: 'us-fear-greed',
    label: '恐贪指数',
    color: '#dc2626',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, valueByDate.get(item.trade_date) ?? null)),
  }
}

export function calculateQuantUsHedgeProxySeries(
  candles: QuantIndicatorCandle[],
  includeHedgeProxy: boolean,
  usHedgeProxyPoints: IndexUsHedgeProxyPoint[],
): QuantLineSeries | null {
  if (!includeHedgeProxy) {
    return null
  }

  const sortedCandles = sortCandles(candles)
  const alignedRows = alignSparseRowsToTradeDates(
    sortedCandles.map((item) => item.trade_date),
    usHedgeProxyPoints,
    (item) => item.release_date,
  )
  const ratioByDate = new Map(
    [...alignedRows.entries()]
      .filter(([, item]) => Number.isFinite(Number(item.ratio_value)))
      .map(([tradeDate, item]) => [tradeDate, Number(item.ratio_value)]),
  )
  const scopeLabel =
    usHedgeProxyPoints.find((item) => String(item.contract_scope || '').trim())?.contract_scope?.trim().toUpperCase() || '代理'

  return {
    key: 'us-hedge-ratio',
    label: `${scopeLabel}对冲代理多空比`,
    color: '#0f766e',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, ratioByDate.get(item.trade_date) ?? null)),
  }
}

export function calculateQuantUsPutCallSeries(
  candles: QuantIndicatorCandle[],
  includePutCall: boolean,
  usPutCallPoints: IndexUsPutCallPoint[],
): QuantLineSeries | null {
  if (!includePutCall) {
    return null
  }

  const sortedCandles = sortCandles(candles)
  const valueByDate = new Map(
    usPutCallPoints
      .filter((item) => Number.isFinite(Number(item.total_put_call_ratio)))
      .map((item) => [item.trade_date, Number(item.total_put_call_ratio)]),
  )

  return {
    key: 'us-put-call-total',
    label: '总Put/Call',
    color: '#9333ea',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, valueByDate.get(item.trade_date) ?? null)),
  }
}

export function calculateQuantUsTreasuryYieldSeries(
  candles: QuantIndicatorCandle[],
  includeTreasuryYield: boolean,
  usTreasuryYieldPoints: IndexUsTreasuryYieldPoint[],
): { spread10y2y: QuantLineSeries; spread10y3m: QuantLineSeries } | null {
  if (!includeTreasuryYield) {
    return null
  }

  const sortedCandles = sortCandles(candles)
  const rowByDate = new Map(usTreasuryYieldPoints.map((item) => [item.trade_date, item]))

  return {
    spread10y2y: {
      key: 'us-yield-spread-10y-2y',
      label: '10Y-2Y利差',
      color: '#2563eb',
      data: sortedCandles.map((item) =>
        createLinePoint(
          item.trade_date,
          Number.isFinite(Number(rowByDate.get(item.trade_date)?.spread_10y_2y))
            ? Number(rowByDate.get(item.trade_date)?.spread_10y_2y)
            : null,
        ),
      ),
    },
    spread10y3m: {
      key: 'us-yield-spread-10y-3m',
      label: '10Y-3M利差',
      color: '#f97316',
      data: sortedCandles.map((item) =>
        createLinePoint(
          item.trade_date,
          Number.isFinite(Number(rowByDate.get(item.trade_date)?.spread_10y_3m))
            ? Number(rowByDate.get(item.trade_date)?.spread_10y_3m)
            : null,
        ),
      ),
    },
  }
}

export function calculateQuantUsCreditSpreadSeries(
  candles: QuantIndicatorCandle[],
  includeCreditSpread: boolean,
  usCreditSpreadPoints: IndexUsCreditSpreadPoint[],
): QuantLineSeries | null {
  if (!includeCreditSpread) {
    return null
  }

  const sortedCandles = sortCandles(candles)
  const valueByDate = new Map(
    usCreditSpreadPoints
      .filter((item) => Number.isFinite(Number(item.high_yield_oas)))
      .map((item) => [item.trade_date, Number(item.high_yield_oas)]),
  )

  return {
    key: 'us-hy-oas',
    label: 'HY OAS',
    color: '#be123c',
    data: sortedCandles.map((item) => createLinePoint(item.trade_date, valueByDate.get(item.trade_date) ?? null)),
  }
}

type IndexDatasetOptions = {
  includeCnAuxiliary?: boolean
  includeBasis?: boolean
  includeBasisMonth?: boolean
  includeBasisAdjusted?: boolean
  basisMainLabel?: string
  basisAdjustedLabel?: string
  basisMonthLabel?: string
  includeCnVix?: boolean
  includeUsVix?: boolean
  includeUsFearGreed?: boolean
  includeUsHedge?: boolean
  includeUsPutCall?: boolean
  includeUsTreasuryYield?: boolean
  includeUsCreditSpread?: boolean
  usVixPoints?: IndexUsVixPoint[]
  usFearGreedPoints?: IndexUsFearGreedPoint[]
  usHedgeProxyPoints?: IndexUsHedgeProxyPoint[]
  usPutCallPoints?: IndexUsPutCallPoint[]
  usTreasuryYieldPoints?: IndexUsTreasuryYieldPoint[]
  usCreditSpreadPoints?: IndexUsCreditSpreadPoint[]
}

function buildIndexQuantFilterFields(
  payload: QuantChartPayload,
  options: {
    includeCnAuxiliary: boolean
    includeBasis: boolean
    includeBasisMonth: boolean
    includeBasisAdjusted: boolean
    basisMainLabel: string
    basisAdjustedLabel: string
    basisMonthLabel: string
    includeCnVix: boolean
    includeUsVix: boolean
    includeUsFearGreed: boolean
    includeUsHedge: boolean
    includeUsPutCall: boolean
    includeUsTreasuryYield: boolean
    includeUsCreditSpread: boolean
  },
): QuantFilterFieldMeta[] {
  const fields: QuantFilterFieldMeta[] = [
    { key: 'rsi', group: 'rsi', label: payload.rsi.label },
    { key: 'wr', group: 'wr', label: payload.wr.label },
    { key: 'macd-dif', group: 'macd', label: payload.macd.dif.label },
    { key: 'macd-dea', group: 'macd', label: payload.macd.dea.label },
    { key: 'macd-histogram', group: 'macd', label: 'MACD柱' },
    { key: 'kdj-k', group: 'kdj', label: payload.kdj.k.label },
    { key: 'kdj-d', group: 'kdj', label: payload.kdj.d.label },
    { key: 'kdj-j', group: 'kdj', label: payload.kdj.j.label },
  ]

  if (options.includeCnAuxiliary) {
    fields.unshift(
      { key: 'emotion', group: 'emotion', label: '情绪指标' },
      { key: 'breadth-up-pct', group: 'breadth', label: '上涨家数百分比' },
    )
  }
  if (options.includeBasis) {
    const basisFields: QuantFilterFieldMeta[] = [{ key: 'basis-main', group: 'basis', label: options.basisMainLabel }]
    if (options.includeBasisAdjusted) {
      basisFields.unshift({ key: 'basis-main-adjusted', group: 'basis', label: options.basisAdjustedLabel })
    }
    if (options.includeBasisMonth) {
      basisFields.push({ key: 'basis-month', group: 'basis', label: options.basisMonthLabel })
    }
    fields.unshift(...basisFields)
  }
  if (options.includeCnVix) {
    fields.splice(
      options.includeCnAuxiliary ? 4 : 0,
      0,
      { key: 'vix-open', group: 'vix', label: 'VIX开' },
      { key: 'vix-high', group: 'vix', label: 'VIX高' },
      { key: 'vix-low', group: 'vix', label: 'VIX低' },
      { key: 'vix-close', group: 'vix', label: 'VIX收' },
    )
  }
  if (options.includeUsVix) {
    fields.unshift(
      { key: 'us-vix-open', group: 'us-vix', label: '美股VIX开' },
      { key: 'us-vix-high', group: 'us-vix', label: '美股VIX高' },
      { key: 'us-vix-low', group: 'us-vix', label: '美股VIX低' },
      { key: 'us-vix-close', group: 'us-vix', label: '美股VIX收' },
    )
  }
  if (options.includeUsFearGreed) {
    fields.unshift({ key: 'us-fear-greed', group: 'fear-greed', label: '恐贪指数' })
  }
  if (options.includeUsHedge) {
    fields.unshift(
      { key: 'us-hedge-long', group: 'hedge', label: '对冲代理多头' },
      { key: 'us-hedge-short', group: 'hedge', label: '对冲代理空头' },
      { key: 'us-hedge-ratio', group: 'hedge', label: '对冲代理多空比' },
    )
  }
  if (options.includeUsPutCall) {
    fields.unshift(
      { key: 'us-put-call-total', group: 'put-call', label: '总Put/Call' },
      { key: 'us-put-call-index', group: 'put-call', label: '指数Put/Call' },
      { key: 'us-put-call-equity', group: 'put-call', label: '股票Put/Call' },
      { key: 'us-put-call-etf', group: 'put-call', label: 'ETF Put/Call' },
    )
  }
  if (options.includeUsTreasuryYield) {
    fields.unshift(
      { key: 'us-yield-3m', group: 'treasury', label: '3M收益率' },
      { key: 'us-yield-2y', group: 'treasury', label: '2Y收益率' },
      { key: 'us-yield-10y', group: 'treasury', label: '10Y收益率' },
      { key: 'us-yield-spread-10y-2y', group: 'treasury', label: '10Y-2Y利差' },
      { key: 'us-yield-spread-10y-3m', group: 'treasury', label: '10Y-3M利差' },
    )
  }
  if (options.includeUsCreditSpread) {
    fields.unshift(
      { key: 'us-hy-oas', group: 'credit', label: 'HY OAS' },
      { key: 'us-hy-oas-change-5d', group: 'credit', label: 'HY OAS 5日变化' },
    )
  }
  return fields
}

function buildStockQuantFilterFields(payload: QuantChartPayload): QuantFilterFieldMeta[] {
  return [
    { key: 'ma-1', group: 'ma', label: payload.ma[0]?.label ?? 'MA1' },
    { key: 'ma-2', group: 'ma', label: payload.ma[1]?.label ?? 'MA2' },
    { key: 'ma-3', group: 'ma', label: payload.ma[2]?.label ?? 'MA3' },
    { key: 'ma-4', group: 'ma', label: payload.ma[3]?.label ?? 'MA4' },
    { key: 'pct-chg', group: 'change', label: '涨跌幅(%)' },
    { key: 'turnover-rate', group: 'turnover', label: '换手率(%)' },
    { key: 'rsi', group: 'rsi', label: payload.rsi.label },
    { key: 'wr', group: 'wr', label: payload.wr.label },
    { key: 'macd-dif', group: 'macd', label: payload.macd.dif.label },
    { key: 'macd-dea', group: 'macd', label: payload.macd.dea.label },
    { key: 'macd-histogram', group: 'macd', label: 'MACD柱' },
    { key: 'kdj-k', group: 'kdj', label: payload.kdj.k.label },
    { key: 'kdj-d', group: 'kdj', label: payload.kdj.d.label },
    { key: 'kdj-j', group: 'kdj', label: payload.kdj.j.label },
  ]
}

function buildBaseSnapshots(payload: QuantChartPayload, candles: QuantIndicatorCandle[]) {
  const sortedCandles = sortCandles(candles)
  const times = sortedCandles.map((item) => item.trade_date)
  return times.map((tradeDate, index) => ({
    tradeDate,
    close: sortedCandles[index]?.close ?? null,
    high: sortedCandles[index]?.high ?? null,
    low: sortedCandles[index]?.low ?? null,
    values: {
      'pct-chg': sortedCandles[index]?.pct_chg ?? null,
      'turnover-rate':
        sortedCandles[index]?.turnover_rate === null || sortedCandles[index]?.turnover_rate === undefined
          ? null
          : (sortedCandles[index]?.turnover_rate ?? 0) * 100,
      rsi: payload.rsi.data[index]?.value ?? null,
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

export function buildIndexQuantFilterDataset(
  candles: QuantIndicatorCandle[],
  params: QuantIndicatorParams,
  symbolName: string,
  emotionPoints: IndexEmotionPoint[],
  basisPoints: FuturesBasisPoint[],
  breadthPoints: IndexBreadthPoint[],
  vixPoints: IndexVixPoint[] = [],
  supportsVix = false,
  options: IndexDatasetOptions = {},
): QuantFilterDataset {
  const chart = calculateQuantIndicators(candles, params)
  const includeCnAuxiliary = options.includeCnAuxiliary ?? true
  const includeBasis = options.includeBasis ?? includeCnAuxiliary
  const includeBasisMonth = options.includeBasisMonth ?? includeCnAuxiliary
  const includeBasisAdjusted = options.includeBasisAdjusted ?? false
  const basisMainLabel = options.basisMainLabel ?? '主连期现差'
  const basisAdjustedLabel = options.basisAdjustedLabel ?? '换月调整期现差'
  const basisMonthLabel = options.basisMonthLabel ?? '月连期现差'
  const includeCnVix = options.includeCnVix ?? supportsVix
  const includeUsVix = options.includeUsVix ?? false
  const includeUsFearGreed = options.includeUsFearGreed ?? false
  const includeUsHedge = options.includeUsHedge ?? false
  const includeUsPutCall = options.includeUsPutCall ?? false
  const includeUsTreasuryYield = options.includeUsTreasuryYield ?? false
  const includeUsCreditSpread = options.includeUsCreditSpread ?? false
  const usVixPoints = options.usVixPoints ?? []
  const usFearGreedPoints = options.usFearGreedPoints ?? []
  const usHedgeProxyPoints = options.usHedgeProxyPoints ?? []
  const usPutCallPoints = options.usPutCallPoints ?? []
  const usTreasuryYieldPoints = options.usTreasuryYieldPoints ?? []
  const usCreditSpreadPoints = options.usCreditSpreadPoints ?? []

  const emotion = includeCnAuxiliary ? calculateQuantEmotionSeries(candles, symbolName, emotionPoints) : null
  const basis = includeBasis ? calculateQuantFuturesBasisSeries(candles, symbolName, basisPoints) : null
  const breadth = includeCnAuxiliary ? calculateQuantBreadthSeries(candles, breadthPoints) : null
  if (basis) {
    basis.main.label = basisMainLabel
    if (includeBasisAdjusted && basis.adjusted) {
      basis.adjusted.label = basisAdjustedLabel
    } else {
      delete (basis as { adjusted?: QuantLineSeries }).adjusted
    }
    basis.month.label = basisMonthLabel
  }
  const vix = includeCnVix ? calculateQuantVixSeries(candles, true, vixPoints) : null
  const usVix = includeUsVix ? calculateQuantUsVixSeries(candles, true, usVixPoints) : null
  const usFearGreed = includeUsFearGreed
    ? calculateQuantUsFearGreedSeries(candles, true, usFearGreedPoints)
    : null
  const usHedgeProxy = includeUsHedge
    ? calculateQuantUsHedgeProxySeries(candles, true, usHedgeProxyPoints)
    : null
  const usPutCall = includeUsPutCall ? calculateQuantUsPutCallSeries(candles, true, usPutCallPoints) : null
  const usTreasuryYield = includeUsTreasuryYield
    ? calculateQuantUsTreasuryYieldSeries(candles, true, usTreasuryYieldPoints)
    : null
  const usCreditSpread = includeUsCreditSpread
    ? calculateQuantUsCreditSpreadSeries(candles, true, usCreditSpreadPoints)
    : null
  const vixByDate = new Map(
    vixPoints.map((item) => [
      item.trade_date,
      {
        'vix-open': Number.isFinite(Number(item.open_price)) ? Number(item.open_price) : null,
        'vix-high': Number.isFinite(Number(item.high_price)) ? Number(item.high_price) : null,
        'vix-low': Number.isFinite(Number(item.low_price)) ? Number(item.low_price) : null,
        'vix-close': Number.isFinite(Number(item.close_price)) ? Number(item.close_price) : null,
      },
    ]),
  )
  const usVixByDate = new Map(
    usVixPoints.map((item) => [
      item.trade_date,
      {
        'us-vix-open': Number.isFinite(Number(item.open_value)) ? Number(item.open_value) : null,
        'us-vix-high': Number.isFinite(Number(item.high_value)) ? Number(item.high_value) : null,
        'us-vix-low': Number.isFinite(Number(item.low_value)) ? Number(item.low_value) : null,
        'us-vix-close': Number.isFinite(Number(item.close_value)) ? Number(item.close_value) : null,
      },
    ]),
  )
  const usFearGreedByDate = new Map(
    usFearGreedPoints.map((item) => [
      item.trade_date,
      Number.isFinite(Number(item.fear_greed_value)) ? Number(item.fear_greed_value) : null,
    ]),
  )
  const usPutCallByDate = new Map(
    usPutCallPoints.map((item) => [
      item.trade_date,
      {
        'us-put-call-total': Number.isFinite(Number(item.total_put_call_ratio)) ? Number(item.total_put_call_ratio) : null,
        'us-put-call-index': Number.isFinite(Number(item.index_put_call_ratio)) ? Number(item.index_put_call_ratio) : null,
        'us-put-call-equity': Number.isFinite(Number(item.equity_put_call_ratio)) ? Number(item.equity_put_call_ratio) : null,
        'us-put-call-etf': Number.isFinite(Number(item.etf_put_call_ratio)) ? Number(item.etf_put_call_ratio) : null,
      },
    ]),
  )
  const usTreasuryByDate = new Map(
    usTreasuryYieldPoints.map((item) => [
      item.trade_date,
      {
        'us-yield-3m': Number.isFinite(Number(item.yield_3m)) ? Number(item.yield_3m) : null,
        'us-yield-2y': Number.isFinite(Number(item.yield_2y)) ? Number(item.yield_2y) : null,
        'us-yield-10y': Number.isFinite(Number(item.yield_10y)) ? Number(item.yield_10y) : null,
        'us-yield-spread-10y-2y': Number.isFinite(Number(item.spread_10y_2y)) ? Number(item.spread_10y_2y) : null,
        'us-yield-spread-10y-3m': Number.isFinite(Number(item.spread_10y_3m)) ? Number(item.spread_10y_3m) : null,
      },
    ]),
  )
  const sortedCreditPoints = [...usCreditSpreadPoints]
    .filter((item) => item.trade_date)
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date))
  const usCreditByDate = new Map(
    sortedCreditPoints.map((item, index) => {
      const value = Number.isFinite(Number(item.high_yield_oas)) ? Number(item.high_yield_oas) : null
      const previous = index >= 5 ? sortedCreditPoints[index - 5] : null
      const previousValue =
        previous && Number.isFinite(Number(previous.high_yield_oas)) ? Number(previous.high_yield_oas) : null
      return [
        item.trade_date,
        {
          'us-hy-oas': value,
          'us-hy-oas-change-5d': value !== null && previousValue !== null ? value - previousValue : null,
        },
      ]
    }),
  )
  const baseSnapshots = buildBaseSnapshots(chart, candles)
  const alignedUsHedgeRows = alignSparseRowsToTradeDates(
    baseSnapshots.map((item) => item.tradeDate),
    usHedgeProxyPoints,
    (item) => item.release_date,
  )
  const usHedgeByDate = new Map(
    [...alignedUsHedgeRows.entries()].map(([tradeDate, item]) => [
      tradeDate,
      {
        'us-hedge-long': Number.isFinite(Number(item.long_value)) ? Number(item.long_value) : null,
        'us-hedge-short': Number.isFinite(Number(item.short_value)) ? Number(item.short_value) : null,
        'us-hedge-ratio': Number.isFinite(Number(item.ratio_value)) ? Number(item.ratio_value) : null,
      },
    ]),
  )
  const snapshots = baseSnapshots.map((snapshot, index) => ({
    ...snapshot,
    values: {
      ...snapshot.values,
      emotion: emotion?.data[index]?.value ?? null,
      'basis-main': basis?.main.data[index]?.value ?? null,
      'basis-main-adjusted': includeBasisAdjusted ? (basis?.adjusted?.data[index]?.value ?? null) : null,
      'basis-month': basis?.month.data[index]?.value ?? null,
      'breadth-up-pct': breadth?.data[index]?.value ?? null,
      'vix-open': vixByDate.get(snapshot.tradeDate)?.['vix-open'] ?? null,
      'vix-high': vixByDate.get(snapshot.tradeDate)?.['vix-high'] ?? null,
      'vix-low': vixByDate.get(snapshot.tradeDate)?.['vix-low'] ?? null,
      'vix-close': vixByDate.get(snapshot.tradeDate)?.['vix-close'] ?? null,
      'us-vix-open': usVixByDate.get(snapshot.tradeDate)?.['us-vix-open'] ?? null,
      'us-vix-high': usVixByDate.get(snapshot.tradeDate)?.['us-vix-high'] ?? null,
      'us-vix-low': usVixByDate.get(snapshot.tradeDate)?.['us-vix-low'] ?? null,
      'us-vix-close': usVixByDate.get(snapshot.tradeDate)?.['us-vix-close'] ?? null,
      'us-fear-greed': usFearGreedByDate.get(snapshot.tradeDate) ?? null,
      'us-hedge-long': usHedgeByDate.get(snapshot.tradeDate)?.['us-hedge-long'] ?? null,
      'us-hedge-short': usHedgeByDate.get(snapshot.tradeDate)?.['us-hedge-short'] ?? null,
      'us-hedge-ratio': usHedgeByDate.get(snapshot.tradeDate)?.['us-hedge-ratio'] ?? null,
      'us-put-call-total': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-total'] ?? null,
      'us-put-call-index': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-index'] ?? null,
      'us-put-call-equity': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-equity'] ?? null,
      'us-put-call-etf': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-etf'] ?? null,
      'us-yield-3m': usTreasuryByDate.get(snapshot.tradeDate)?.['us-yield-3m'] ?? null,
      'us-yield-2y': usTreasuryByDate.get(snapshot.tradeDate)?.['us-yield-2y'] ?? null,
      'us-yield-10y': usTreasuryByDate.get(snapshot.tradeDate)?.['us-yield-10y'] ?? null,
      'us-yield-spread-10y-2y': usTreasuryByDate.get(snapshot.tradeDate)?.['us-yield-spread-10y-2y'] ?? null,
      'us-yield-spread-10y-3m': usTreasuryByDate.get(snapshot.tradeDate)?.['us-yield-spread-10y-3m'] ?? null,
      'us-hy-oas': usCreditByDate.get(snapshot.tradeDate)?.['us-hy-oas'] ?? null,
      'us-hy-oas-change-5d': usCreditByDate.get(snapshot.tradeDate)?.['us-hy-oas-change-5d'] ?? null,
    },
  }))

  return {
    chart,
    emotion,
    basis,
    breadth,
    vix,
    usVix,
    usFearGreed,
    usHedgeProxy,
    usPutCall,
    usTreasuryYield,
    usCreditSpread,
    fields: buildIndexQuantFilterFields(chart, {
      includeCnAuxiliary,
      includeBasis,
      includeBasisMonth,
      includeBasisAdjusted,
      basisMainLabel,
      basisAdjustedLabel,
      basisMonthLabel,
      includeCnVix,
      includeUsVix,
      includeUsFearGreed,
      includeUsHedge,
      includeUsPutCall,
      includeUsTreasuryYield,
      includeUsCreditSpread,
    }),
    snapshots,
  }
}

export function buildStockQuantFilterDataset(
  candles: QuantIndicatorCandle[],
  params: QuantIndicatorParams,
): QuantFilterDataset {
  const chart = calculateQuantIndicators(candles, params)
  const snapshots = buildBaseSnapshots(chart, candles)

  return {
    chart,
    emotion: null,
    basis: null,
    breadth: null,
    vix: null,
    usVix: null,
    usFearGreed: null,
    usHedgeProxy: null,
    usPutCall: null,
    usTreasuryYield: null,
    usCreditSpread: null,
    fields: buildStockQuantFilterFields(chart),
    snapshots,
  }
}

export function buildQuantFilterDataset(
  candles: QuantIndicatorCandle[],
  params: QuantIndicatorParams,
  symbolName: string,
  emotionPoints: IndexEmotionPoint[],
  basisPoints: FuturesBasisPoint[],
  breadthPoints: IndexBreadthPoint[] = [],
  vixPoints: IndexVixPoint[] = [],
  supportsVix = false,
  options: IndexDatasetOptions = {},
): QuantFilterDataset {
  return buildIndexQuantFilterDataset(
    candles,
    params,
    symbolName,
    emotionPoints,
    basisPoints,
    breadthPoints,
    vixPoints,
    supportsVix,
    options,
  )
}

