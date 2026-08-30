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
  IndexBasisDeltaPoint,
  IndexBreadthPoint,
  IndexCffexNetShortDeltaPoint,
  IndexCnBaifenweiFearGreedPoint,
  IndexCnMarketFearGreedPoint,
  IndexCnOptionFlowPutCallPoint,
  IndexCnOptionPutCallPoint,
  IndexCnOptionSeries,
  IndexEmotionPoint,
  IndexFundPurchaseLimitPoint,
  IndexMarginFinancingNetBuySumPoint,
  IndexMarginTradingPoint,
  IndexRelatedVixSeries,
  IndexRiskStrategyPoint,
  IndexSelfSentimentPoint,
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
  'cn-market-fear-greed',
  'cn-baifenwei-fear-greed',
  'cn-baifenwei-volatility',
  'cn-baifenwei-relative-turnover',
  'cn-baifenwei-margin-trading',
  'cn-baifenwei-market-breadth',
  'cn-baifenwei-rsi',
  'cn-baifenwei-limit-up-down-ratio',
  'self-sentiment-score',
  'self-sentiment-core-score',
  'self-sentiment-derivative-score',
  'basis-main',
  'basis-month',
  'breadth-up-pct',
  'vix-open',
  'vix-high',
  'vix-low',
  'vix-close',
  'reference-vix-hs300-high',
  'reference-vix-csi500-high',
  'cn-option-put-call-current',
  'cn-option-put-call-next',
  'cn-option-put-call-quarter-1',
  'cn-option-put-call-quarter-2',
  'cn-option-flow-pc-volume',
  'cn-option-flow-pc-turnover',
  'cn-option-flow-cp-turnover',
  'basis-main-delta-5d',
  'basis-main-delta-7d',
  'basis-main-delta-14d',
  'basis-main-delta-20d',
  'basis-main-delta-30d',
  'basis-main-delta-60d',
  'basis-main-delta-120d',
  'basis-month-delta-5d',
  'basis-month-delta-7d',
  'basis-month-delta-14d',
  'basis-month-delta-20d',
  'basis-month-delta-30d',
  'basis-month-delta-60d',
  'basis-month-delta-120d',
  'cffex-net-short-top20-delta-5d',
  'cffex-net-short-top20-delta-7d',
  'cffex-net-short-top20-delta-14d',
  'cffex-net-short-top20-delta-20d',
  'cffex-net-short-top20-delta-30d',
  'cffex-net-short-top20-delta-60d',
  'cffex-net-short-top20-delta-120d',
  'cffex-net-short-citic-delta-5d',
  'cffex-net-short-citic-delta-7d',
  'cffex-net-short-citic-delta-14d',
  'cffex-net-short-citic-delta-20d',
  'cffex-net-short-citic-delta-30d',
  'cffex-net-short-citic-delta-60d',
  'cffex-net-short-citic-delta-120d',
  'fund-purchase-limit-count',
  'fund-purchase-limit-pct',
  'margin-financing-balance',
  'margin-securities-lending-balance',
  'margin-total-balance',
  'margin-financing-net-buy',
  'margin-leverage-ratio',
  'margin-total-market-cap-leverage-ratio',
  'margin-financing-net-buy-sum-5d',
  'margin-financing-net-buy-sum-7d',
  'margin-financing-net-buy-sum-14d',
  'margin-financing-net-buy-sum-20d',
  'margin-financing-net-buy-sum-30d',
  'margin-financing-net-buy-sum-60d',
  'margin-financing-net-buy-sum-120d',
  'risk-yellow-vulnerability',
  'risk-red-escalation',
  'risk-global-shock',
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
  'us-put-call-premium',
  'us-put-call-price-current',
  'us-put-call-price-next',
  'us-put-call-price-quarter-1',
  'us-put-call-price-quarter-2',
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

function toFiniteNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
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
  relatedVixSeries?: IndexRelatedVixSeries[]
  includeCnOptionPutCall?: boolean
  includeCnOptionFlowPutCall?: boolean
  includeCffexNetShortDelta?: boolean
  includeBasisDelta?: boolean
  includeFundPurchaseLimit?: boolean
  includeMarginTrading?: boolean
  includeSelfSentiment?: boolean
  includeRiskStrategy?: boolean
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
  cnOptionPutCallPoints?: IndexCnOptionPutCallPoint[]
  cnOptionFlowPutCallPoints?: IndexCnOptionFlowPutCallPoint[]
  cnOptionSeries?: IndexCnOptionSeries[]
  cffexNetShortDeltaPoints?: IndexCffexNetShortDeltaPoint[]
  basisDeltaPoints?: IndexBasisDeltaPoint[]
  fundPurchaseLimitPoints?: IndexFundPurchaseLimitPoint[]
  marginTradingPoints?: IndexMarginTradingPoint[]
  marginFinancingNetBuySumPoints?: IndexMarginFinancingNetBuySumPoint[]
  selfSentimentPoints?: IndexSelfSentimentPoint[]
  riskStrategyPoints?: IndexRiskStrategyPoint[]
  cnMarketFearGreedPoints?: IndexCnMarketFearGreedPoint[]
  cnBaifenweiFearGreedPoints?: IndexCnBaifenweiFearGreedPoint[]
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
    includeCnOptionPutCall: boolean
    includeCnOptionFlowPutCall: boolean
    includeCffexNetShortDelta: boolean
    includeBasisDelta: boolean
    includeFundPurchaseLimit: boolean
    includeMarginTrading: boolean
    includeSelfSentiment: boolean
    includeRiskStrategy: boolean
    includeUsVix: boolean
    includeUsFearGreed: boolean
    includeUsHedge: boolean
    includeUsPutCall: boolean
    includeUsTreasuryYield: boolean
    includeUsCreditSpread: boolean
    cnOptionSeries: IndexCnOptionSeries[]
    relatedVixSeries: IndexRelatedVixSeries[]
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
      { key: 'cn-market-fear-greed', group: 'emotion', label: '大盘总体恐贪指数' },
      { key: 'cn-baifenwei-fear-greed', group: 'emotion', label: '百分位恐贪综合分' },
      { key: 'cn-baifenwei-volatility', group: 'emotion', label: '百分位恐贪·波动率' },
      { key: 'cn-baifenwei-relative-turnover', group: 'emotion', label: '百分位恐贪·相对换手率' },
      { key: 'cn-baifenwei-margin-trading', group: 'emotion', label: '百分位恐贪·融资融券' },
      { key: 'cn-baifenwei-market-breadth', group: 'emotion', label: '百分位恐贪·市场宽度' },
      { key: 'cn-baifenwei-rsi', group: 'emotion', label: '百分位恐贪·RSI' },
      { key: 'cn-baifenwei-limit-up-down-ratio', group: 'emotion', label: '百分位恐贪·涨跌停比' },
      { key: 'breadth-up-pct', group: 'breadth', label: '上涨家数百分比' },
    )
  }
  if (options.includeSelfSentiment) {
    fields.unshift(
      { key: 'self-sentiment-score', group: 'emotion', label: '自建情绪综合分' },
      { key: 'self-sentiment-core-score', group: 'emotion', label: '自建情绪核心分' },
      { key: 'self-sentiment-derivative-score', group: 'emotion', label: '自建情绪衍生分' },
    )
  }
  if (options.includeRiskStrategy) {
    fields.unshift(
      { key: 'risk-yellow-vulnerability', group: 'risk', label: '中证1000 黄色脆弱期' },
      { key: 'risk-red-escalation', group: 'risk', label: '中证1000 红色风险升级' },
      { key: 'risk-global-shock', group: 'risk', label: '中证1000 全球冲击' },
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
  for (const series of options.relatedVixSeries) {
    fields.unshift({
      key: series.source_key,
      group: 'vix',
      label: `${series.source_name} VIX高`,
    })
  }
  if (options.includeCnOptionPutCall) {
    fields.unshift(
      { key: 'cn-option-put-call-current', group: 'put-call', label: 'A股Put/Call 当月' },
      { key: 'cn-option-put-call-next', group: 'put-call', label: 'A股Put/Call 下月' },
      { key: 'cn-option-put-call-quarter-1', group: 'put-call', label: 'A股Put/Call 季月1' },
      { key: 'cn-option-put-call-quarter-2', group: 'put-call', label: 'A股Put/Call 季月2' },
    )
  }
  if (options.includeCnOptionFlowPutCall) {
    fields.unshift(
      { key: 'cn-option-flow-pc-volume', group: 'put-call', label: 'A股成交量 Put/Call' },
      { key: 'cn-option-flow-pc-turnover', group: 'put-call', label: 'A股成交额 Put/Call' },
      { key: 'cn-option-flow-cp-turnover', group: 'put-call', label: 'A股成交额 Call/Put' },
    )
  }
  for (const series of options.cnOptionSeries.filter((item) => item.exchange !== 'CFFEX')) {
    const sourceLabel = `${series.exchange_label}${series.product_code}`
    fields.unshift(
      {
        key: `cn-option-pc-${series.exchange.toLowerCase()}-${series.product_code}-current` as QuantFilterFieldKey,
        group: 'put-call',
        label: `${sourceLabel} Put/Call 当月`,
      },
      {
        key: `cn-option-pc-${series.exchange.toLowerCase()}-${series.product_code}-next` as QuantFilterFieldKey,
        group: 'put-call',
        label: `${sourceLabel} Put/Call 下月`,
      },
      {
        key: `cn-option-pc-${series.exchange.toLowerCase()}-${series.product_code}-quarter-1` as QuantFilterFieldKey,
        group: 'put-call',
        label: `${sourceLabel} Put/Call 季月1`,
      },
      {
        key: `cn-option-pc-${series.exchange.toLowerCase()}-${series.product_code}-quarter-2` as QuantFilterFieldKey,
        group: 'put-call',
        label: `${sourceLabel} Put/Call 季月2`,
      },
      {
        key: `cn-option-flow-pc-volume-${series.exchange.toLowerCase()}-${series.product_code}` as QuantFilterFieldKey,
        group: 'put-call',
        label: `${sourceLabel} 成交量 P/C`,
      },
      {
        key: `cn-option-flow-pc-turnover-${series.exchange.toLowerCase()}-${series.product_code}` as QuantFilterFieldKey,
        group: 'put-call',
        label: `${sourceLabel} 成交额 P/C`,
      },
      {
        key: `cn-option-flow-cp-turnover-${series.exchange.toLowerCase()}-${series.product_code}` as QuantFilterFieldKey,
        group: 'put-call',
        label: `${sourceLabel} 成交额 C/P`,
      },
    )
  }
  for (const series of options.cnOptionSeries.filter((item) => (item.vix_points ?? []).length > 0)) {
    const sourceLabel = `${series.exchange_label}${series.product_code}`
    const sourcePrefix = `${series.exchange.toLowerCase()}-${series.product_code.toLowerCase()}`
    fields.unshift(
      {
        key: `cn-option-vix-open-${sourcePrefix}` as QuantFilterFieldKey,
        group: 'vix',
        label: `${sourceLabel} 自算VIX开盘`,
      },
      {
        key: `cn-option-vix-close-${sourcePrefix}` as QuantFilterFieldKey,
        group: 'vix',
        label: `${sourceLabel} 自算VIX收盘`,
      },
    )
  }
  if (options.includeBasisDelta) {
    fields.unshift(
      { key: 'basis-main-delta-5d', group: 'basis-delta', label: '主连期现差变化 5D' },
      { key: 'basis-main-delta-7d', group: 'basis-delta', label: '主连期现差变化 7D' },
      { key: 'basis-main-delta-14d', group: 'basis-delta', label: '主连期现差变化 14D' },
      { key: 'basis-main-delta-20d', group: 'basis-delta', label: '主连期现差变化 20D' },
      { key: 'basis-main-delta-30d', group: 'basis-delta', label: '主连期现差变化 30D' },
      { key: 'basis-main-delta-60d', group: 'basis-delta', label: '主连期现差变化 60D' },
      { key: 'basis-main-delta-120d', group: 'basis-delta', label: '主连期现差变化 120D' },
      { key: 'basis-month-delta-5d', group: 'basis-delta', label: '月连期现差变化 5D' },
      { key: 'basis-month-delta-7d', group: 'basis-delta', label: '月连期现差变化 7D' },
      { key: 'basis-month-delta-14d', group: 'basis-delta', label: '月连期现差变化 14D' },
      { key: 'basis-month-delta-20d', group: 'basis-delta', label: '月连期现差变化 20D' },
      { key: 'basis-month-delta-30d', group: 'basis-delta', label: '月连期现差变化 30D' },
      { key: 'basis-month-delta-60d', group: 'basis-delta', label: '月连期现差变化 60D' },
      { key: 'basis-month-delta-120d', group: 'basis-delta', label: '月连期现差变化 120D' },
    )
  }
  if (options.includeCffexNetShortDelta) {
    fields.unshift(
      { key: 'cffex-net-short-top20-delta-5d', group: 'net-short', label: '前20净空增量 5D' },
      { key: 'cffex-net-short-top20-delta-7d', group: 'net-short', label: '前20净空增量 7D' },
      { key: 'cffex-net-short-top20-delta-14d', group: 'net-short', label: '前20净空增量 14D' },
      { key: 'cffex-net-short-top20-delta-20d', group: 'net-short', label: '前20净空增量 20D' },
      { key: 'cffex-net-short-top20-delta-30d', group: 'net-short', label: '前20净空增量 30D' },
      { key: 'cffex-net-short-top20-delta-60d', group: 'net-short', label: '前20净空增量 60D' },
      { key: 'cffex-net-short-top20-delta-120d', group: 'net-short', label: '前20净空增量 120D' },
      { key: 'cffex-net-short-citic-delta-5d', group: 'net-short', label: '中信净空增量 5D' },
      { key: 'cffex-net-short-citic-delta-7d', group: 'net-short', label: '中信净空增量 7D' },
      { key: 'cffex-net-short-citic-delta-14d', group: 'net-short', label: '中信净空增量 14D' },
      { key: 'cffex-net-short-citic-delta-20d', group: 'net-short', label: '中信净空增量 20D' },
      { key: 'cffex-net-short-citic-delta-30d', group: 'net-short', label: '中信净空增量 30D' },
      { key: 'cffex-net-short-citic-delta-60d', group: 'net-short', label: '中信净空增量 60D' },
      { key: 'cffex-net-short-citic-delta-120d', group: 'net-short', label: '中信净空增量 120D' },
    )
  }
  if (options.includeFundPurchaseLimit) {
    fields.unshift(
      { key: 'fund-purchase-limit-count', group: 'fund-limit', label: 'A股公募基金大额限购家数' },
      { key: 'fund-purchase-limit-pct', group: 'fund-limit', label: 'A股公募基金大额限购比例(%)' },
    )
  }
  if (options.includeMarginTrading) {
    fields.unshift(
      { key: 'margin-financing-balance', group: 'margin-trading', label: '融资余额' },
      { key: 'margin-securities-lending-balance', group: 'margin-trading', label: '融券余额' },
      { key: 'margin-total-balance', group: 'margin-trading', label: '两融余额' },
      { key: 'margin-financing-net-buy', group: 'margin-trading', label: '融资净买入额' },
      { key: 'margin-leverage-ratio', group: 'margin-trading', label: '两融流通市值杠杆率(%)' },
      { key: 'margin-total-market-cap-leverage-ratio', group: 'margin-trading', label: '两融总市值杠杆率(%)' },
      { key: 'margin-financing-net-buy-sum-5d', group: 'margin-trading', label: '融资净买入累计 5D（亿元）' },
      { key: 'margin-financing-net-buy-sum-7d', group: 'margin-trading', label: '融资净买入累计 7D（亿元）' },
      { key: 'margin-financing-net-buy-sum-14d', group: 'margin-trading', label: '融资净买入累计 14D（亿元）' },
      { key: 'margin-financing-net-buy-sum-20d', group: 'margin-trading', label: '融资净买入累计 20D（亿元）' },
      { key: 'margin-financing-net-buy-sum-30d', group: 'margin-trading', label: '融资净买入累计 30D（亿元）' },
      { key: 'margin-financing-net-buy-sum-60d', group: 'margin-trading', label: '融资净买入累计 60D（亿元）' },
      { key: 'margin-financing-net-buy-sum-120d', group: 'margin-trading', label: '融资净买入累计 120D（亿元）' },
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
      { key: 'us-put-call-premium', group: 'put-call', label: '成交额Put/Call（Optionomics）' },
      { key: 'us-put-call-price-current', group: 'put-call', label: 'ETF期权价格P/C 当月' },
      { key: 'us-put-call-price-next', group: 'put-call', label: 'ETF期权价格P/C 下月' },
      { key: 'us-put-call-price-quarter-1', group: 'put-call', label: 'ETF期权价格P/C 季月1' },
      { key: 'us-put-call-price-quarter-2', group: 'put-call', label: 'ETF期权价格P/C 季月2' },
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
  const includeCnOptionPutCall = options.includeCnOptionPutCall ?? false
  const includeCnOptionFlowPutCall = options.includeCnOptionFlowPutCall ?? false
  const includeCffexNetShortDelta = options.includeCffexNetShortDelta ?? includeCnAuxiliary
  const includeBasisDelta = options.includeBasisDelta ?? includeCnAuxiliary
  const includeFundPurchaseLimit = options.includeFundPurchaseLimit ?? false
  const includeMarginTrading = options.includeMarginTrading ?? false
  const includeSelfSentiment = options.includeSelfSentiment ?? false
  const includeRiskStrategy = options.includeRiskStrategy ?? symbolName === '中证1000'
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
  const cnOptionPutCallPoints = options.cnOptionPutCallPoints ?? []
  const cnOptionFlowPutCallPoints = options.cnOptionFlowPutCallPoints ?? []
  const cnOptionSeries = options.cnOptionSeries ?? []
  const cffexNetShortDeltaPoints = options.cffexNetShortDeltaPoints ?? []
  const basisDeltaPoints = options.basisDeltaPoints ?? []
  const fundPurchaseLimitPoints = options.fundPurchaseLimitPoints ?? []
  const marginTradingPoints = options.marginTradingPoints ?? []
  const marginFinancingNetBuySumPoints = options.marginFinancingNetBuySumPoints ?? []
  const selfSentimentPoints = options.selfSentimentPoints ?? []
  const riskStrategyPoints = options.riskStrategyPoints ?? []
  const cnMarketFearGreedPoints = options.cnMarketFearGreedPoints ?? []
  const cnBaifenweiFearGreedPoints = options.cnBaifenweiFearGreedPoints ?? []
  const usTreasuryYieldPoints = options.usTreasuryYieldPoints ?? []
  const usCreditSpreadPoints = options.usCreditSpreadPoints ?? []
  const relatedVixSeries = options.relatedVixSeries ?? []

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
  const relatedVixValuesByDate = new Map<string, Partial<Record<QuantFilterFieldKey, number | null>>>()
  for (const series of relatedVixSeries) {
    for (const point of series.points) {
      const values = relatedVixValuesByDate.get(point.trade_date) ?? {}
      values[series.source_key] = Number.isFinite(Number(point.high_price)) ? Number(point.high_price) : null
      relatedVixValuesByDate.set(point.trade_date, values)
    }
  }
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
        'us-put-call-premium': Number.isFinite(Number(item.premium_put_call_ratio))
          ? Number(item.premium_put_call_ratio)
          : null,
        'us-put-call-price-current': toFiniteNullableNumber(item.current_month_price_put_call_ratio),
        'us-put-call-price-next': toFiniteNullableNumber(item.next_month_price_put_call_ratio),
        'us-put-call-price-quarter-1': toFiniteNullableNumber(item.quarter_1_price_put_call_ratio),
        'us-put-call-price-quarter-2': toFiniteNullableNumber(item.quarter_2_price_put_call_ratio),
      },
    ]),
  )
  const cnOptionPutCallByDate = new Map(
    cnOptionPutCallPoints.map((item) => [
      item.trade_date,
      {
        'cn-option-put-call-current': toFiniteNullableNumber(item.current_month_put_call_ratio),
        'cn-option-put-call-next': toFiniteNullableNumber(item.next_month_put_call_ratio),
        'cn-option-put-call-quarter-1': toFiniteNullableNumber(item.quarter_1_put_call_ratio),
        'cn-option-put-call-quarter-2': toFiniteNullableNumber(item.quarter_2_put_call_ratio),
      },
    ]),
  )
  const cnOptionFlowPutCallByDate = new Map(
    cnOptionFlowPutCallPoints.map((item) => [
      item.trade_date,
      {
        'cn-option-flow-pc-volume': toFiniteNullableNumber(item.volume_put_call_ratio),
        'cn-option-flow-pc-turnover': toFiniteNullableNumber(item.turnover_put_call_ratio),
        'cn-option-flow-cp-turnover': toFiniteNullableNumber(item.turnover_call_put_ratio),
      },
    ]),
  )
  const exchangeOptionValuesByDate = new Map<string, Partial<Record<QuantFilterFieldKey, number | null>>>()
  for (const series of cnOptionSeries.filter((item) => item.exchange !== 'CFFEX')) {
    const sourcePrefix = `${series.exchange.toLowerCase()}-${series.product_code}`
    for (const item of series.put_call_points) {
      const values = exchangeOptionValuesByDate.get(item.trade_date) ?? {}
      values[`cn-option-pc-${sourcePrefix}-current` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.current_month_put_call_ratio)
      values[`cn-option-pc-${sourcePrefix}-next` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.next_month_put_call_ratio)
      values[`cn-option-pc-${sourcePrefix}-quarter-1` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.quarter_1_put_call_ratio)
      values[`cn-option-pc-${sourcePrefix}-quarter-2` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.quarter_2_put_call_ratio)
      exchangeOptionValuesByDate.set(item.trade_date, values)
    }
    for (const item of series.flow_points) {
      const values = exchangeOptionValuesByDate.get(item.trade_date) ?? {}
      values[`cn-option-flow-pc-volume-${sourcePrefix}` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.volume_put_call_ratio)
      values[`cn-option-flow-pc-turnover-${sourcePrefix}` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.turnover_put_call_ratio)
      values[`cn-option-flow-cp-turnover-${sourcePrefix}` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.turnover_call_put_ratio)
      exchangeOptionValuesByDate.set(item.trade_date, values)
    }
  }
  const optionVixValuesByDate = new Map<string, Partial<Record<QuantFilterFieldKey, number | null>>>()
  for (const series of cnOptionSeries) {
    const sourcePrefix = `${series.exchange.toLowerCase()}-${series.product_code.toLowerCase()}`
    for (const item of series.vix_points ?? []) {
      const values = optionVixValuesByDate.get(item.trade_date) ?? {}
      values[`cn-option-vix-open-${sourcePrefix}` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.vix_open)
      values[`cn-option-vix-close-${sourcePrefix}` as QuantFilterFieldKey] =
        toFiniteNullableNumber(item.vix_close)
      optionVixValuesByDate.set(item.trade_date, values)
    }
  }
  const cffexNetShortDeltaByDate = new Map(
    cffexNetShortDeltaPoints.map((item) => [
      item.trade_date,
      {
        'cffex-net-short-top20-delta-5d': toFiniteNullableNumber(item.top20_delta_5d),
        'cffex-net-short-top20-delta-7d': toFiniteNullableNumber(item.top20_delta_7d),
        'cffex-net-short-top20-delta-14d': toFiniteNullableNumber(item.top20_delta_14d),
        'cffex-net-short-top20-delta-20d': toFiniteNullableNumber(item.top20_delta_20d),
        'cffex-net-short-top20-delta-30d': toFiniteNullableNumber(item.top20_delta_30d),
        'cffex-net-short-top20-delta-60d': toFiniteNullableNumber(item.top20_delta_60d),
        'cffex-net-short-top20-delta-120d': toFiniteNullableNumber(item.top20_delta_120d),
        'cffex-net-short-citic-delta-5d': toFiniteNullableNumber(item.citic_delta_5d),
        'cffex-net-short-citic-delta-7d': toFiniteNullableNumber(item.citic_delta_7d),
        'cffex-net-short-citic-delta-14d': toFiniteNullableNumber(item.citic_delta_14d),
        'cffex-net-short-citic-delta-20d': toFiniteNullableNumber(item.citic_delta_20d),
        'cffex-net-short-citic-delta-30d': toFiniteNullableNumber(item.citic_delta_30d),
        'cffex-net-short-citic-delta-60d': toFiniteNullableNumber(item.citic_delta_60d),
        'cffex-net-short-citic-delta-120d': toFiniteNullableNumber(item.citic_delta_120d),
      },
    ]),
  )
  const basisDeltaByDate = new Map(
    basisDeltaPoints.map((item) => [
      item.trade_date,
      {
        'basis-main-delta-5d': toFiniteNullableNumber(item.main_delta_5d),
        'basis-main-delta-7d': toFiniteNullableNumber(item.main_delta_7d),
        'basis-main-delta-14d': toFiniteNullableNumber(item.main_delta_14d),
        'basis-main-delta-20d': toFiniteNullableNumber(item.main_delta_20d),
        'basis-main-delta-30d': toFiniteNullableNumber(item.main_delta_30d),
        'basis-main-delta-60d': toFiniteNullableNumber(item.main_delta_60d),
        'basis-main-delta-120d': toFiniteNullableNumber(item.main_delta_120d),
        'basis-month-delta-5d': toFiniteNullableNumber(item.month_delta_5d),
        'basis-month-delta-7d': toFiniteNullableNumber(item.month_delta_7d),
        'basis-month-delta-14d': toFiniteNullableNumber(item.month_delta_14d),
        'basis-month-delta-20d': toFiniteNullableNumber(item.month_delta_20d),
        'basis-month-delta-30d': toFiniteNullableNumber(item.month_delta_30d),
        'basis-month-delta-60d': toFiniteNullableNumber(item.month_delta_60d),
        'basis-month-delta-120d': toFiniteNullableNumber(item.month_delta_120d),
      },
    ]),
  )
  const fundPurchaseLimitByDate = new Map(
    fundPurchaseLimitPoints.map((item) => [
      item.trade_date,
      {
        'fund-purchase-limit-count': toFiniteNullableNumber(item.limited_fund_count),
        'fund-purchase-limit-pct': toFiniteNullableNumber(item.limited_fund_pct),
      },
    ]),
  )
  const marginTradingByDate = new Map(
    marginTradingPoints.map((item) => [
      item.trade_date,
      {
        'margin-financing-balance': toFiniteNullableNumber(item.financing_balance),
        'margin-securities-lending-balance': toFiniteNullableNumber(item.securities_lending_balance),
        'margin-total-balance': toFiniteNullableNumber(item.total_balance),
        'margin-financing-net-buy': toFiniteNullableNumber(item.financing_net_buy_amount),
        'margin-leverage-ratio': toFiniteNullableNumber(item.leverage_ratio_pct),
        'margin-total-market-cap-leverage-ratio': toFiniteNullableNumber(item.total_market_cap_leverage_ratio_pct),
      },
    ]),
  )
  const marginFinancingNetBuySumByDate = new Map(
    marginFinancingNetBuySumPoints.map((item) => [
      item.trade_date,
      {
        'margin-financing-net-buy-sum-5d': toFiniteNullableNumber(item.sum_5d) === null ? null : Number(item.sum_5d) / 100_000_000,
        'margin-financing-net-buy-sum-7d': toFiniteNullableNumber(item.sum_7d) === null ? null : Number(item.sum_7d) / 100_000_000,
        'margin-financing-net-buy-sum-14d': toFiniteNullableNumber(item.sum_14d) === null ? null : Number(item.sum_14d) / 100_000_000,
        'margin-financing-net-buy-sum-20d': toFiniteNullableNumber(item.sum_20d) === null ? null : Number(item.sum_20d) / 100_000_000,
        'margin-financing-net-buy-sum-30d': toFiniteNullableNumber(item.sum_30d) === null ? null : Number(item.sum_30d) / 100_000_000,
        'margin-financing-net-buy-sum-60d': toFiniteNullableNumber(item.sum_60d) === null ? null : Number(item.sum_60d) / 100_000_000,
        'margin-financing-net-buy-sum-120d': toFiniteNullableNumber(item.sum_120d) === null ? null : Number(item.sum_120d) / 100_000_000,
      },
    ]),
  )
  const selfSentimentByDate = new Map(
    selfSentimentPoints.map((item) => [
      item.trade_date,
      {
        'self-sentiment-score': toFiniteNullableNumber(item.score),
        'self-sentiment-core-score': toFiniteNullableNumber(item.core_score),
        'self-sentiment-derivative-score': toFiniteNullableNumber(item.derivative_score),
      },
    ]),
  )
  const riskStrategyByDate = new Map(
    riskStrategyPoints.map((item) => [
      item.trade_date,
      {
        'risk-yellow-vulnerability': item.yellow_vulnerability === null ? null : item.yellow_vulnerability ? 1 : 0,
        'risk-red-escalation': item.red_escalation === null ? null : item.red_escalation ? 1 : 0,
        'risk-global-shock': item.global_shock === null ? null : item.global_shock ? 1 : 0,
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
  const cnMarketFearGreedByDate = new Map(
    cnMarketFearGreedPoints.map((item) => [
      item.trade_date,
      Number.isFinite(Number(item.fear_greed_value)) ? Number(item.fear_greed_value) : null,
    ]),
  )
  const cnBaifenweiFearGreedByDate = new Map(
    cnBaifenweiFearGreedPoints.map((item) => [item.trade_date, item]),
  )
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
      'cn-market-fear-greed': cnMarketFearGreedByDate.get(snapshot.tradeDate) ?? null,
      'cn-baifenwei-fear-greed': cnBaifenweiFearGreedByDate.get(snapshot.tradeDate)?.fear_greed_value ?? null,
      'cn-baifenwei-volatility': cnBaifenweiFearGreedByDate.get(snapshot.tradeDate)?.volatility_score ?? null,
      'cn-baifenwei-relative-turnover':
        cnBaifenweiFearGreedByDate.get(snapshot.tradeDate)?.relative_turnover_score ?? null,
      'cn-baifenwei-margin-trading':
        cnBaifenweiFearGreedByDate.get(snapshot.tradeDate)?.margin_trading_score ?? null,
      'cn-baifenwei-market-breadth':
        cnBaifenweiFearGreedByDate.get(snapshot.tradeDate)?.market_breadth_score ?? null,
      'cn-baifenwei-rsi': cnBaifenweiFearGreedByDate.get(snapshot.tradeDate)?.rsi_score ?? null,
      'cn-baifenwei-limit-up-down-ratio':
        cnBaifenweiFearGreedByDate.get(snapshot.tradeDate)?.limit_up_down_ratio_score ?? null,
      'self-sentiment-score': selfSentimentByDate.get(snapshot.tradeDate)?.['self-sentiment-score'] ?? null,
      'self-sentiment-core-score':
        selfSentimentByDate.get(snapshot.tradeDate)?.['self-sentiment-core-score'] ?? null,
      'self-sentiment-derivative-score':
        selfSentimentByDate.get(snapshot.tradeDate)?.['self-sentiment-derivative-score'] ?? null,
      'risk-yellow-vulnerability':
        riskStrategyByDate.get(snapshot.tradeDate)?.['risk-yellow-vulnerability'] ?? null,
      'risk-red-escalation': riskStrategyByDate.get(snapshot.tradeDate)?.['risk-red-escalation'] ?? null,
      'risk-global-shock': riskStrategyByDate.get(snapshot.tradeDate)?.['risk-global-shock'] ?? null,
      'basis-main': basis?.main.data[index]?.value ?? null,
      'basis-main-adjusted': includeBasisAdjusted ? (basis?.adjusted?.data[index]?.value ?? null) : null,
      'basis-month': basis?.month.data[index]?.value ?? null,
      'breadth-up-pct': breadth?.data[index]?.value ?? null,
      'vix-open': vixByDate.get(snapshot.tradeDate)?.['vix-open'] ?? null,
      'vix-high': vixByDate.get(snapshot.tradeDate)?.['vix-high'] ?? null,
      'vix-low': vixByDate.get(snapshot.tradeDate)?.['vix-low'] ?? null,
      'vix-close': vixByDate.get(snapshot.tradeDate)?.['vix-close'] ?? null,
      ...(relatedVixValuesByDate.get(snapshot.tradeDate) ?? {}),
      'cn-option-put-call-current': cnOptionPutCallByDate.get(snapshot.tradeDate)?.['cn-option-put-call-current'] ?? null,
      'cn-option-put-call-next': cnOptionPutCallByDate.get(snapshot.tradeDate)?.['cn-option-put-call-next'] ?? null,
      'cn-option-put-call-quarter-1': cnOptionPutCallByDate.get(snapshot.tradeDate)?.['cn-option-put-call-quarter-1'] ?? null,
      'cn-option-put-call-quarter-2': cnOptionPutCallByDate.get(snapshot.tradeDate)?.['cn-option-put-call-quarter-2'] ?? null,
      'cn-option-flow-pc-volume': cnOptionFlowPutCallByDate.get(snapshot.tradeDate)?.['cn-option-flow-pc-volume'] ?? null,
      'cn-option-flow-pc-turnover': cnOptionFlowPutCallByDate.get(snapshot.tradeDate)?.['cn-option-flow-pc-turnover'] ?? null,
      'cn-option-flow-cp-turnover': cnOptionFlowPutCallByDate.get(snapshot.tradeDate)?.['cn-option-flow-cp-turnover'] ?? null,
      ...(exchangeOptionValuesByDate.get(snapshot.tradeDate) ?? {}),
      ...(optionVixValuesByDate.get(snapshot.tradeDate) ?? {}),
      'cffex-net-short-top20-delta-5d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-top20-delta-5d'] ?? null,
      'cffex-net-short-top20-delta-7d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-top20-delta-7d'] ?? null,
      'cffex-net-short-top20-delta-14d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-top20-delta-14d'] ?? null,
      'cffex-net-short-top20-delta-20d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-top20-delta-20d'] ?? null,
      'cffex-net-short-top20-delta-30d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-top20-delta-30d'] ?? null,
      'cffex-net-short-top20-delta-60d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-top20-delta-60d'] ?? null,
      'cffex-net-short-top20-delta-120d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-top20-delta-120d'] ?? null,
      'cffex-net-short-citic-delta-5d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-citic-delta-5d'] ?? null,
      'cffex-net-short-citic-delta-7d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-citic-delta-7d'] ?? null,
      'cffex-net-short-citic-delta-14d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-citic-delta-14d'] ?? null,
      'cffex-net-short-citic-delta-20d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-citic-delta-20d'] ?? null,
      'cffex-net-short-citic-delta-30d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-citic-delta-30d'] ?? null,
      'cffex-net-short-citic-delta-60d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-citic-delta-60d'] ?? null,
      'cffex-net-short-citic-delta-120d': cffexNetShortDeltaByDate.get(snapshot.tradeDate)?.['cffex-net-short-citic-delta-120d'] ?? null,
      'basis-main-delta-5d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-main-delta-5d'] ?? null,
      'basis-main-delta-7d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-main-delta-7d'] ?? null,
      'basis-main-delta-14d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-main-delta-14d'] ?? null,
      'basis-main-delta-20d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-main-delta-20d'] ?? null,
      'basis-main-delta-30d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-main-delta-30d'] ?? null,
      'basis-main-delta-60d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-main-delta-60d'] ?? null,
      'basis-main-delta-120d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-main-delta-120d'] ?? null,
      'basis-month-delta-5d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-month-delta-5d'] ?? null,
      'basis-month-delta-7d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-month-delta-7d'] ?? null,
      'basis-month-delta-14d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-month-delta-14d'] ?? null,
      'basis-month-delta-20d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-month-delta-20d'] ?? null,
      'basis-month-delta-30d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-month-delta-30d'] ?? null,
      'basis-month-delta-60d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-month-delta-60d'] ?? null,
      'basis-month-delta-120d': basisDeltaByDate.get(snapshot.tradeDate)?.['basis-month-delta-120d'] ?? null,
      'fund-purchase-limit-count': fundPurchaseLimitByDate.get(snapshot.tradeDate)?.['fund-purchase-limit-count'] ?? null,
      'fund-purchase-limit-pct': fundPurchaseLimitByDate.get(snapshot.tradeDate)?.['fund-purchase-limit-pct'] ?? null,
      'margin-financing-balance': marginTradingByDate.get(snapshot.tradeDate)?.['margin-financing-balance'] ?? null,
      'margin-securities-lending-balance': marginTradingByDate.get(snapshot.tradeDate)?.['margin-securities-lending-balance'] ?? null,
      'margin-total-balance': marginTradingByDate.get(snapshot.tradeDate)?.['margin-total-balance'] ?? null,
      'margin-financing-net-buy': marginTradingByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy'] ?? null,
      'margin-leverage-ratio': marginTradingByDate.get(snapshot.tradeDate)?.['margin-leverage-ratio'] ?? null,
      'margin-total-market-cap-leverage-ratio': marginTradingByDate.get(snapshot.tradeDate)?.['margin-total-market-cap-leverage-ratio'] ?? null,
      'margin-financing-net-buy-sum-5d': marginFinancingNetBuySumByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy-sum-5d'] ?? null,
      'margin-financing-net-buy-sum-7d': marginFinancingNetBuySumByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy-sum-7d'] ?? null,
      'margin-financing-net-buy-sum-14d': marginFinancingNetBuySumByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy-sum-14d'] ?? null,
      'margin-financing-net-buy-sum-20d': marginFinancingNetBuySumByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy-sum-20d'] ?? null,
      'margin-financing-net-buy-sum-30d': marginFinancingNetBuySumByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy-sum-30d'] ?? null,
      'margin-financing-net-buy-sum-60d': marginFinancingNetBuySumByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy-sum-60d'] ?? null,
      'margin-financing-net-buy-sum-120d': marginFinancingNetBuySumByDate.get(snapshot.tradeDate)?.['margin-financing-net-buy-sum-120d'] ?? null,
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
      'us-put-call-premium': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-premium'] ?? null,
      'us-put-call-price-current': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-price-current'] ?? null,
      'us-put-call-price-next': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-price-next'] ?? null,
      'us-put-call-price-quarter-1': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-price-quarter-1'] ?? null,
      'us-put-call-price-quarter-2': usPutCallByDate.get(snapshot.tradeDate)?.['us-put-call-price-quarter-2'] ?? null,
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
      includeCnOptionPutCall,
      includeCnOptionFlowPutCall,
      includeCffexNetShortDelta,
      includeBasisDelta,
      includeFundPurchaseLimit,
      includeMarginTrading,
      includeSelfSentiment,
      includeRiskStrategy,
      includeUsVix,
      includeUsFearGreed,
      includeUsHedge,
      includeUsPutCall,
      includeUsTreasuryYield,
      includeUsCreditSpread,
      cnOptionSeries,
      relatedVixSeries,
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
