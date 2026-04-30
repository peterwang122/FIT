<script setup lang="ts">
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineWidth,
  type LogicalRange,
  type MouseEventParams,
  type SeriesType,
  type Time,
  type WhitespaceData,
} from 'lightweight-charts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type {
  QuantHighlightBand,
  QuantHistogramPoint,
  QuantIndicatorParams,
  QuantLinePoint,
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
  KlineCandle,
  MarketOption,
} from '../types/stock'
import { DateHighlightPrimitive } from '../utils/dateHighlightPrimitive'
import { buildQuantFilterDataset } from '../utils/quantIndicators'

type PanelKey =
  | 'main'
  | 'macd'
  | 'kdj'
  | 'wr'
  | 'rsi'
  | 'emotion'
  | 'basis'
  | 'breadth'
  | 'vix'
  | 'usVix'
  | 'usFearGreed'
  | 'usHedge'
  | 'usPutCall'
  | 'usTreasury'
  | 'usCredit'
type SubPanelKey = Exclude<PanelKey, 'main'>
type MainOverlayMode = 'ma' | 'boll'
type UsPutCallMetricKey = 'total' | 'index' | 'equity' | 'etf'
type UsCreditMetricKey = 'hyOas' | 'change5d'
type BasisMetricKey = 'adjusted' | 'main'
type AnySeries = ISeriesApi<SeriesType, Time>
type LineSeriesApi = ISeriesApi<'Line', Time>
type HistogramSeriesApi = ISeriesApi<'Histogram', Time>
type CandleSeriesApi = ISeriesApi<'Candlestick', Time>
type PrimitiveBinding = {
  series: AnySeries
  primitive: DateHighlightPrimitive
  getHighlights: () => QuantHighlightBand[]
}
type SummaryRow = { label: string; value: string; placeholder?: boolean }
type SummaryCard = { key: string; title: string; hint?: string; rows: SummaryRow[] }
type SubPanelOption = { key: SubPanelKey; label: string; available: boolean }
const HISTORY_REQUEST_THRESHOLD = 15
const ALL_PANEL_KEYS: PanelKey[] = [
  'main',
  'macd',
  'kdj',
  'wr',
  'rsi',
  'emotion',
  'basis',
  'breadth',
  'vix',
  'usVix',
  'usFearGreed',
  'usHedge',
  'usPutCall',
  'usTreasury',
  'usCredit',
]
const ALL_SUB_PANEL_KEYS: SubPanelKey[] = ALL_PANEL_KEYS.filter((item): item is SubPanelKey => item !== 'main')

const props = withDefaults(
  defineProps<{
    candles: KlineCandle[]
    emotionPoints?: IndexEmotionPoint[]
    emotionLoading?: boolean
    emotionErrorMessage?: string
    futuresBasisPoints?: FuturesBasisPoint[]
    futuresBasisLoading?: boolean
    futuresBasisErrorMessage?: string
    breadthPoints?: IndexBreadthPoint[]
    breadthLoading?: boolean
    breadthErrorMessage?: string
    vixPoints?: IndexVixPoint[]
    supportsVixPanel?: boolean
    usVixPoints?: IndexUsVixPoint[]
    usFearGreedPoints?: IndexUsFearGreedPoint[]
    usHedgeProxyPoints?: IndexUsHedgeProxyPoint[]
    usPutCallPoints?: IndexUsPutCallPoint[]
    usTreasuryYieldPoints?: IndexUsTreasuryYieldPoint[]
    usCreditSpreadPoints?: IndexUsCreditSpreadPoint[]
    supportsUsVixPanel?: boolean
    supportsUsFearGreedPanel?: boolean
    supportsUsHedgeProxyPanel?: boolean
    supportsUsPutCallPanel?: boolean
    supportsUsTreasuryYieldPanel?: boolean
    supportsUsCreditSpreadPanel?: boolean
    highlightBands?: QuantHighlightBand[]
    marketOptions?: MarketOption[]
    symbolName: string
    symbolCode: string
    params: QuantIndicatorParams
    supportsAuxiliaryPanels?: boolean
    supportsBasisPanel?: boolean
    showBasisMonthLine?: boolean
    loading?: boolean
    defaultVisibleDays?: number
    zoomStep?: number
    hasMoreHistory?: boolean
    loadingMoreHistory?: boolean
  }>(),
  {
    emotionPoints: () => [],
    emotionLoading: false,
    emotionErrorMessage: '',
    futuresBasisPoints: () => [],
    futuresBasisLoading: false,
    futuresBasisErrorMessage: '',
    breadthPoints: () => [],
    breadthLoading: false,
    breadthErrorMessage: '',
    vixPoints: () => [],
    supportsVixPanel: false,
    usVixPoints: () => [],
    usFearGreedPoints: () => [],
    usHedgeProxyPoints: () => [],
    usPutCallPoints: () => [],
    usTreasuryYieldPoints: () => [],
    usCreditSpreadPoints: () => [],
    supportsUsVixPanel: false,
    supportsUsFearGreedPanel: false,
    supportsUsHedgeProxyPanel: false,
    supportsUsPutCallPanel: false,
    supportsUsTreasuryYieldPanel: false,
    supportsUsCreditSpreadPanel: false,
    highlightBands: () => [],
    supportsAuxiliaryPanels: true,
    supportsBasisPanel: true,
    showBasisMonthLine: true,
    loading: false,
    defaultVisibleDays: 90,
    zoomStep: 0.18,
    hasMoreHistory: false,
    loadingMoreHistory: false,
  },
)

const emit = defineEmits<{
  selectIndex: [code: string]
  openSettings: []
  requestMoreHistory: [earliestTradeDate: string]
}>()

const mainContainerRef = ref<HTMLDivElement | null>(null)
const macdContainerRef = ref<HTMLDivElement | null>(null)
const kdjContainerRef = ref<HTMLDivElement | null>(null)
const wrContainerRef = ref<HTMLDivElement | null>(null)
const rsiContainerRef = ref<HTMLDivElement | null>(null)
const emotionContainerRef = ref<HTMLDivElement | null>(null)
const basisContainerRef = ref<HTMLDivElement | null>(null)
const breadthContainerRef = ref<HTMLDivElement | null>(null)
const vixContainerRef = ref<HTMLDivElement | null>(null)
const usVixContainerRef = ref<HTMLDivElement | null>(null)
const usFearGreedContainerRef = ref<HTMLDivElement | null>(null)
const usHedgeContainerRef = ref<HTMLDivElement | null>(null)
const usPutCallContainerRef = ref<HTMLDivElement | null>(null)
const usTreasuryContainerRef = ref<HTMLDivElement | null>(null)
const usCreditContainerRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')
const overlayMode = ref<MainOverlayMode>('ma')
const hoveredTradeDate = ref<string | null>(null)
const visibleSubPanels = ref<SubPanelKey[]>([...ALL_SUB_PANEL_KEYS])
const activeUsPutCallKey = ref<UsPutCallMetricKey>('total')
const activeUsCreditKey = ref<UsCreditMetricKey>('hyOas')
const activeBasisKey = ref<BasisMetricKey>('adjusted')

const charts: Partial<Record<PanelKey, IChartApi>> = {}
const primarySeriesMap = new Map<PanelKey, AnySeries>()
const panelValueMaps = new Map<PanelKey, Map<string, number>>()
let mainCandleSeries: CandleSeriesApi | null = null
let mainMaSeries: LineSeriesApi[] = []
let bollSeriesRefs: LineSeriesApi[] = []
let macdDifSeries: LineSeriesApi | null = null
let macdDeaSeries: LineSeriesApi | null = null
let macdHistogramSeries: HistogramSeriesApi | null = null
let kdjSeriesRefs: LineSeriesApi[] = []
let wrSeries: LineSeriesApi | null = null
let rsiSeries: LineSeriesApi | null = null
let emotionSeries: LineSeriesApi | null = null
let basisMainSeries: LineSeriesApi | null = null
let basisMonthSeries: LineSeriesApi | null = null
let breadthSeries: LineSeriesApi | null = null
let breadthCountSeries: LineSeriesApi | null = null
let vixSeries: CandleSeriesApi | null = null
let usVixSeries: CandleSeriesApi | null = null
let usFearGreedSeries: LineSeriesApi | null = null
let usHedgeSeries: LineSeriesApi | null = null
let usPutCallSeries: LineSeriesApi | null = null
let usTreasurySpread10y2ySeries: LineSeriesApi | null = null
let usTreasurySpread10y3mSeries: LineSeriesApi | null = null
let usCreditSeries: LineSeriesApi | null = null
let highlightBindings: PrimitiveBinding[] = []
let isSyncingRange = false
let isSyncingCrosshair = false
let shouldResetVisibleRange = true
let unsubs: Array<() => void> = []
let lastRequestedHistoryBoundary: string | null = null

const visibleSubPanelSet = computed(() => new Set(visibleSubPanels.value))
const visiblePanelOptions = computed<SubPanelOption[]>(() => [
  { key: 'macd', label: 'MACD', available: true },
  { key: 'kdj', label: 'KDJ', available: true },
  { key: 'wr', label: 'WR', available: true },
  { key: 'rsi', label: 'RSI', available: true },
  { key: 'emotion', label: '情绪', available: props.supportsAuxiliaryPanels },
  { key: 'basis', label: '期现差', available: props.supportsBasisPanel },
  { key: 'breadth', label: '涨跌家数', available: props.supportsAuxiliaryPanels },
  { key: 'vix', label: 'VIX', available: props.supportsVixPanel },
  { key: 'usVix', label: '美股VIX', available: props.supportsUsVixPanel },
  { key: 'usFearGreed', label: '恐贪', available: props.supportsUsFearGreedPanel },
  { key: 'usHedge', label: '对冲代理', available: props.supportsUsHedgeProxyPanel },
  { key: 'usPutCall', label: 'Put/Call', available: props.supportsUsPutCallPanel },
  { key: 'usTreasury', label: '美债利差', available: props.supportsUsTreasuryYieldPanel },
  { key: 'usCredit', label: '信用利差', available: props.supportsUsCreditSpreadPanel },
])
const availableSubPanelOptions = computed(() => visiblePanelOptions.value.filter((item) => item.available))

function isSubPanelAvailable(panelKey: SubPanelKey) {
  return availableSubPanelOptions.value.some((item) => item.key === panelKey)
}

function isSubPanelVisible(panelKey: SubPanelKey) {
  return isSubPanelAvailable(panelKey) && visibleSubPanelSet.value.has(panelKey)
}

function getActivePanelKeys(): PanelKey[] {
  return ['main', ...availableSubPanelOptions.value.filter((item) => isSubPanelVisible(item.key)).map((item) => item.key)]
}

function getPanelContainer(panelKey: PanelKey): HTMLDivElement | null {
  if (panelKey === 'main') return mainContainerRef.value
  if (panelKey === 'macd') return macdContainerRef.value
  if (panelKey === 'kdj') return kdjContainerRef.value
  if (panelKey === 'wr') return wrContainerRef.value
  if (panelKey === 'rsi') return rsiContainerRef.value
  if (panelKey === 'emotion') return emotionContainerRef.value
  if (panelKey === 'basis') return basisContainerRef.value
  if (panelKey === 'breadth') return breadthContainerRef.value
  if (panelKey === 'vix') return vixContainerRef.value
  if (panelKey === 'usVix') return usVixContainerRef.value
  if (panelKey === 'usFearGreed') return usFearGreedContainerRef.value
  if (panelKey === 'usHedge') return usHedgeContainerRef.value
  if (panelKey === 'usPutCall') return usPutCallContainerRef.value
  if (panelKey === 'usTreasury') return usTreasuryContainerRef.value
  if (panelKey === 'usCredit') return usCreditContainerRef.value
  return null
}

async function rebuildChartsPreservingRange() {
  const visibleRange = charts.main?.timeScale().getVisibleLogicalRange() ?? null
  const shouldResetAfterRender = shouldResetVisibleRange && !visibleRange
  shouldResetVisibleRange = shouldResetAfterRender
  disposeCharts()
  await nextTick()
  renderCharts()
  if (visibleRange) {
    shouldResetVisibleRange = false
    charts.main?.timeScale().setVisibleLogicalRange(visibleRange)
  }
}

function toggleSubPanel(panelKey: SubPanelKey) {
  const current = new Set(visibleSubPanels.value)
  if (current.has(panelKey)) {
    current.delete(panelKey)
  } else {
    current.add(panelKey)
  }
  visibleSubPanels.value = ALL_SUB_PANEL_KEYS.filter((item) => current.has(item))
  void rebuildChartsPreservingRange()
}

function formatDateText(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseDateText(value: string): number {
  return new Date(`${value}T00:00:00`).getTime()
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

const sortedCandles = computed(() =>
  [...props.candles]
    .map((item) => ({
      ...item,
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
      pct_chg: Number(item.pct_chg),
    }))
    .filter(
      (item) =>
        Number.isFinite(item.open) &&
        Number.isFinite(item.high) &&
        Number.isFinite(item.low) &&
        Number.isFinite(item.close),
    )
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)

const latestSnapshot = computed(() =>
  sortedCandles.value.length ? sortedCandles.value[sortedCandles.value.length - 1] : undefined,
)

const candleSnapshotMap = computed(
  () => new Map(sortedCandles.value.map((item) => [item.trade_date, item])),
)

const activeSnapshot = computed(() => {
  if (hoveredTradeDate.value) {
    return candleSnapshotMap.value.get(hoveredTradeDate.value) ?? latestSnapshot.value
  }
  return latestSnapshot.value
})

const mainCandles = computed(() =>
  sortedCandles.value.map((item) => ({
    time: item.trade_date as Time,
    open: item.open,
    high: item.high,
    low: item.low,
    close: item.close,
  })),
)

const supportsAdjustedBasisForSymbol = computed(
  () =>
    !props.showBasisMonthLine &&
    (String(props.symbolCode || '').trim().toUpperCase() === '.NDX' || String(props.symbolName || '').trim() === '纳斯达克100指数'),
)

const quantDataset = computed(() =>
  buildQuantFilterDataset(
    sortedCandles.value,
    props.params,
    props.symbolName,
    props.emotionPoints,
    props.futuresBasisPoints,
    props.breadthPoints,
    props.vixPoints,
    props.supportsVixPanel,
    {
      includeCnAuxiliary: props.supportsAuxiliaryPanels,
      includeBasis: props.supportsBasisPanel,
      includeBasisMonth: props.showBasisMonthLine,
      includeBasisAdjusted: supportsAdjustedBasisForSymbol.value,
      basisMainLabel: props.showBasisMonthLine ? '主连期现差' : '连续期现差',
      basisAdjustedLabel: '换月调整期现差',
      basisMonthLabel: '月连期现差',
      includeCnVix: props.supportsVixPanel,
      includeUsVix: props.supportsUsVixPanel,
      includeUsFearGreed: props.supportsUsFearGreedPanel,
      includeUsHedge: props.supportsUsHedgeProxyPanel,
      includeUsPutCall: props.supportsUsPutCallPanel,
      includeUsTreasuryYield: props.supportsUsTreasuryYieldPanel,
      includeUsCreditSpread: props.supportsUsCreditSpreadPanel,
      usVixPoints: props.usVixPoints,
      usFearGreedPoints: props.usFearGreedPoints,
      usHedgeProxyPoints: props.usHedgeProxyPoints,
      usPutCallPoints: props.usPutCallPoints,
      usTreasuryYieldPoints: props.usTreasuryYieldPoints,
      usCreditSpreadPoints: props.usCreditSpreadPoints,
    },
  ),
)

const indicatorPayload = computed(() => quantDataset.value.chart)

const emotionSeriesData = computed(() =>
  (quantDataset.value.emotion?.data ?? []).map((item) => ({
    time: item.time as Time,
    rawDate: item.time,
    value: item.value ?? 50,
  })),
)

const breadthSeriesData = computed(() =>
  (quantDataset.value.breadth?.data ?? []).map((item) => ({
    time: item.time as Time,
    rawDate: item.time,
    value: item.value ?? 0,
  })),
)

const breadthCountSeriesData = computed(() => {
  const upCountByDate = new Map(props.breadthPoints.map((item) => [item.trade_date, Number(item.up_count) || 0]))
  return sortedCandles.value.map((item) => ({
    time: item.trade_date as Time,
    rawDate: item.trade_date,
    value: upCountByDate.get(item.trade_date) ?? 0,
  }))
})

const vixSeriesData = computed(() =>
  {
    const pointByDate = new Map(
      props.vixPoints.map((item) => [
        item.trade_date,
        {
          open: toNullableNumber(item.open_price),
          high: toNullableNumber(item.high_price),
          low: toNullableNumber(item.low_price),
          close: toNullableNumber(item.close_price),
        },
      ]),
    )
    return sortedCandles.value.map((item) => ({
      trade_date: item.trade_date,
      open: pointByDate.get(item.trade_date)?.open ?? null,
      high: pointByDate.get(item.trade_date)?.high ?? null,
      low: pointByDate.get(item.trade_date)?.low ?? null,
      close: pointByDate.get(item.trade_date)?.close ?? null,
    }))
  },
)

const usVixSeriesData = computed(() =>
  {
    const pointByDate = new Map(
      props.usVixPoints.map((item) => [
        item.trade_date,
        {
          open: toNullableNumber(item.open_value),
          high: toNullableNumber(item.high_value),
          low: toNullableNumber(item.low_value),
          close: toNullableNumber(item.close_value),
        },
      ]),
    )
    return sortedCandles.value.map((item) => ({
      trade_date: item.trade_date,
      open: pointByDate.get(item.trade_date)?.open ?? null,
      high: pointByDate.get(item.trade_date)?.high ?? null,
      low: pointByDate.get(item.trade_date)?.low ?? null,
      close: pointByDate.get(item.trade_date)?.close ?? null,
    }))
  },
)

const usFearGreedSeriesData = computed(() =>
  (quantDataset.value.usFearGreed?.data ?? []).map((item) => ({
    time: item.time as Time,
    rawDate: item.time,
    value: item.value ?? null,
  })),
)

const usHedgeSeriesData = computed(() =>
  (quantDataset.value.usHedgeProxy?.data ?? []).map((item) => ({
    time: item.time as Time,
    rawDate: item.time,
    value: item.value ?? null,
  })),
)

const usPutCallMetricConfig: Record<UsPutCallMetricKey, { label: string; color: string }> = {
  total: { label: '总Put/Call', color: '#9333ea' },
  index: { label: '指数Put/Call', color: '#2563eb' },
  equity: { label: '股票Put/Call', color: '#f97316' },
  etf: { label: 'ETF Put/Call', color: '#0f766e' },
}

const usCreditMetricConfig: Record<UsCreditMetricKey, { label: string; color: string }> = {
  hyOas: { label: 'HY OAS', color: '#be123c' },
  change5d: { label: '5日变化', color: '#2563eb' },
}

function getUsPutCallMetricValue(item: IndexUsPutCallPoint | undefined, key: UsPutCallMetricKey) {
  if (!item) return null
  const value =
    key === 'total'
      ? item.total_put_call_ratio
      : key === 'index'
        ? item.index_put_call_ratio
        : key === 'equity'
          ? item.equity_put_call_ratio
          : item.etf_put_call_ratio
  return toNullableNumber(value)
}

const usPutCallSeriesData = computed(() => {
  const rowByDate = new Map(props.usPutCallPoints.map((item) => [item.trade_date, item]))
  const activeKey = activeUsPutCallKey.value
  return sortedCandles.value.map((item) => ({
    time: item.trade_date as Time,
    rawDate: item.trade_date,
    value: getUsPutCallMetricValue(rowByDate.get(item.trade_date), activeKey),
  }))
})

const usTreasurySpread10y2ySeriesData = computed(() =>
  (quantDataset.value.usTreasuryYield?.spread10y2y.data ?? []).map((item) => ({
    time: item.time as Time,
    rawDate: item.time,
    value: item.value ?? null,
  })),
)

const usTreasurySpread10y3mSeriesData = computed(() =>
  (quantDataset.value.usTreasuryYield?.spread10y3m.data ?? []).map((item) => ({
    time: item.time as Time,
    rawDate: item.time,
    value: item.value ?? null,
  })),
)

const usCreditSeriesData = computed(() => {
  const activeKey = activeUsCreditKey.value
  return sortedCandles.value.map((item) => {
    const point = usCreditSpreadPointByDate.value.get(item.trade_date)
    return {
      time: item.trade_date as Time,
      rawDate: item.trade_date,
      value: activeKey === 'hyOas' ? point?.highYieldOas ?? null : point?.change5d ?? null,
    }
  })
})

const basisPointByDate = computed(
  () =>
    new Map(
      props.futuresBasisPoints.map((item) => [
        item.trade_date,
        {
          rollFlag: Boolean(item.basis_roll_flag),
          rollDelta:
            item.basis_roll_delta === null || item.basis_roll_delta === undefined
              ? null
              : Number.isFinite(Number(item.basis_roll_delta))
                ? Number(item.basis_roll_delta)
                : null,
        },
      ]),
    ),
)

const basisRollHighlights = computed<QuantHighlightBand[]>(() =>
  props.futuresBasisPoints
    .filter((item) => Boolean(item.basis_roll_flag))
    .map((item) => ({
      tradeDate: item.trade_date,
      color: 'purple',
      variant: 'striped',
    })),
)

const breadthPointByDate = computed(
  () =>
    new Map(
      props.breadthPoints.map((item) => [
        item.trade_date,
        {
          up_ratio_pct: Number(item.up_ratio_pct) || 0,
          up_count: Number(item.up_count) || 0,
          total_count: Number(item.total_count) || 0,
        },
      ]),
    ),
)

const vixPointByDate = computed(
  () =>
    new Map(
      props.vixPoints.map((item) => [
        item.trade_date,
        {
          open_price: Number(item.open_price) || 0,
          high_price: Number(item.high_price) || 0,
          low_price: Number(item.low_price) || 0,
          close_price: Number(item.close_price) || 0,
        },
      ]),
    ),
)

const usVixPointByDate = computed(
  () =>
    new Map(
      props.usVixPoints.map((item) => [
        item.trade_date,
        {
          open_value: Number(item.open_value) || 0,
          high_value: Number(item.high_value) || 0,
          low_value: Number(item.low_value) || 0,
          close_value: Number(item.close_value) || 0,
        },
      ]),
    ),
)

const usFearGreedPointByDate = computed(
  () =>
    new Map(
      props.usFearGreedPoints.map((item) => [
        item.trade_date,
        {
          fear_greed_value: Number(item.fear_greed_value) || 0,
          sentiment_label: String(item.sentiment_label || '').trim(),
        },
      ]),
    ),
)

const usHedgeProxyPointByDate = computed(() => {
  const alignedRows = alignSparseRowsToTradeDates(
    sortedCandles.value.map((item) => item.trade_date),
    props.usHedgeProxyPoints,
    (item) => item.release_date,
  )
  return new Map(
    [...alignedRows.entries()].map(([tradeDate, item]) => [
      tradeDate,
      {
        contract_scope: String(item.contract_scope || '').trim().toUpperCase(),
        long_value: item.long_value,
        short_value: item.short_value,
        ratio_value: item.ratio_value,
        report_date: item.report_date,
        release_date: item.release_date,
      },
    ]),
  )
})

const usPutCallPointByDate = computed(
  () =>
    new Map(
      props.usPutCallPoints.map((item) => [
        item.trade_date,
        {
          total: item.total_put_call_ratio,
          index: item.index_put_call_ratio,
          equity: item.equity_put_call_ratio,
          etf: item.etf_put_call_ratio,
        },
      ]),
    ),
)

const usTreasuryYieldPointByDate = computed(
  () =>
    new Map(
      props.usTreasuryYieldPoints.map((item) => [
        item.trade_date,
        {
          yield3m: item.yield_3m,
          yield2y: item.yield_2y,
          yield10y: item.yield_10y,
          spread10y2y: item.spread_10y_2y,
          spread10y3m: item.spread_10y_3m,
        },
      ]),
    ),
)

const usCreditSpreadPointByDate = computed(() => {
  const sortedPoints = [...props.usCreditSpreadPoints]
    .filter((item) => item.trade_date)
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date))
  return new Map(
    sortedPoints.map((item, index) => {
      const value = Number.isFinite(Number(item.high_yield_oas)) ? Number(item.high_yield_oas) : null
      const previous = index >= 5 ? sortedPoints[index - 5] : null
      const previousValue =
        previous && Number.isFinite(Number(previous.high_yield_oas)) ? Number(previous.high_yield_oas) : null
      return [
        item.trade_date,
        {
          highYieldOas: value,
          change5d: value !== null && previousValue !== null ? value - previousValue : null,
        },
      ]
    }),
  )
})

const mainLegend = computed(() =>
  overlayMode.value === 'boll'
    ? [
        { label: indicatorPayload.value.boll.upper.label, color: indicatorPayload.value.boll.upper.color },
        { label: indicatorPayload.value.boll.middle.label, color: indicatorPayload.value.boll.middle.color },
        { label: indicatorPayload.value.boll.lower.label, color: indicatorPayload.value.boll.lower.color },
      ]
    : indicatorPayload.value.ma.map((item) => ({ label: item.label, color: item.color })),
)

const macdLegend = computed(() => [
  { label: indicatorPayload.value.macd.dif.label, color: indicatorPayload.value.macd.dif.color },
  { label: indicatorPayload.value.macd.dea.label, color: indicatorPayload.value.macd.dea.color },
  { label: 'MACD柱值', color: '#94a3b8' },
])

const kdjLegend = computed(() => [
  { label: indicatorPayload.value.kdj.k.label, color: indicatorPayload.value.kdj.k.color },
  { label: indicatorPayload.value.kdj.d.label, color: indicatorPayload.value.kdj.d.color },
  { label: indicatorPayload.value.kdj.j.label, color: indicatorPayload.value.kdj.j.color },
])

const wrLegend = computed(() => [{ label: indicatorPayload.value.wr.label, color: indicatorPayload.value.wr.color }])
const rsiLegend = computed(() => [{ label: indicatorPayload.value.rsi.label, color: indicatorPayload.value.rsi.color }])


const emotionLegend = computed(() => [
  {
    label: quantDataset.value.emotion?.label ?? '情绪指标',
    color: quantDataset.value.emotion?.color ?? '#0f4c75',
  },
])

const supportsAdjustedBasisSeries = computed(
  () => !props.showBasisMonthLine && Boolean(quantDataset.value.basis?.adjusted?.data?.length),
)

const activeBasisSeries = computed(() => {
  if (supportsAdjustedBasisSeries.value && activeBasisKey.value === 'adjusted') {
    return quantDataset.value.basis?.adjusted ?? quantDataset.value.basis?.main ?? null
  }
  return quantDataset.value.basis?.main ?? null
})

const basisLegend = computed(() => {
  if (supportsAdjustedBasisSeries.value) {
    return [
      {
        key: 'adjusted' as const,
        label: quantDataset.value.basis?.adjusted?.label ?? '换月调整期现差',
        color: quantDataset.value.basis?.adjusted?.color ?? '#2563eb',
        active: activeBasisKey.value === 'adjusted',
      },
      {
        key: 'main' as const,
        label: quantDataset.value.basis?.main.label ?? '原始连续期现差',
        color: quantDataset.value.basis?.main.color ?? '#dc2626',
        active: activeBasisKey.value === 'main',
      },
    ]
  }
  const items = [
    {
      key: 'main' as const,
      label: quantDataset.value.basis?.main.label ?? '主连期现差',
      color: quantDataset.value.basis?.main.color ?? '#dc2626',
      active: true,
    },
  ]
  if (props.showBasisMonthLine) {
    items.push({
      key: 'main' as const,
      label: quantDataset.value.basis?.month.label ?? '月连期现差',
      color: quantDataset.value.basis?.month.color ?? '#2563eb',
      active: true,
    })
  }
  return items
})

const breadthLegend = computed(() => [
  {
    label: quantDataset.value.breadth?.label ?? '上涨家数百分比',
    color: quantDataset.value.breadth?.color ?? '#0ea5e9',
  },
  {
    label: '上涨家数',
    color: '#f97316',
  },
])

const vixLegend = computed(() => [
  {
    label: 'VIX蜡烛',
    color: '#7c3aed',
  },
])

const usVixLegend = computed(() => [
  {
    label: '美股VIX蜡烛',
    color: '#b45309',
  },
])

const usFearGreedLegend = computed(() => [
  {
    label: quantDataset.value.usFearGreed?.label ?? '恐贪指数',
    color: quantDataset.value.usFearGreed?.color ?? '#dc2626',
  },
])

const usHedgeLegend = computed(() => [
  {
    label: quantDataset.value.usHedgeProxy?.label ?? '对冲代理多空比',
    color: quantDataset.value.usHedgeProxy?.color ?? '#0f766e',
  },
])

const usPutCallLegend = computed(() =>
  (Object.entries(usPutCallMetricConfig) as Array<[UsPutCallMetricKey, { label: string; color: string }]>).map(
    ([key, item]) => ({
      key,
      label: item.label,
      color: item.color,
      active: activeUsPutCallKey.value === key,
    }),
  ),
)

const usTreasuryLegend = computed(() => [
  {
    label: quantDataset.value.usTreasuryYield?.spread10y2y.label ?? '10Y-2Y利差',
    color: quantDataset.value.usTreasuryYield?.spread10y2y.color ?? '#2563eb',
  },
  {
    label: quantDataset.value.usTreasuryYield?.spread10y3m.label ?? '10Y-3M利差',
    color: quantDataset.value.usTreasuryYield?.spread10y3m.color ?? '#f97316',
  },
])

const usCreditLegend = computed(() =>
  (Object.entries(usCreditMetricConfig) as Array<[UsCreditMetricKey, { label: string; color: string }]>).map(([key, item]) => ({
    key,
    label: item.label,
    color: item.color,
    active: activeUsCreditKey.value === key,
  })),
)

const activeTradeDate = computed(() => hoveredTradeDate.value ?? latestSnapshot.value?.trade_date ?? '')


function handleIndexSelect(event: Event) {
  const target = event.target as HTMLSelectElement | null
  const nextCode = target?.value?.trim()
  if (!nextCode) {
    return
  }
  emit('selectIndex', nextCode)
}

function selectUsPutCallMetric(key: UsPutCallMetricKey) {
  activeUsPutCallKey.value = key
  updateAllSeries()
}

function selectUsCreditMetric(key: UsCreditMetricKey) {
  activeUsCreditKey.value = key
  updateAllSeries()
}

function selectBasisMetric(key: BasisMetricKey) {
  if (!supportsAdjustedBasisSeries.value && key === 'adjusted') {
    return
  }
  activeBasisKey.value = key
  updateAllSeries()
}

function formatMetric(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return '-'
  }
  const rounded = value.toFixed(4)
  return rounded.replace(/\.?0+$/, '')
}

function formatMetricWithSuffix(value: number | null | undefined, suffix: string) {
  const formatted = formatMetric(value)
  return formatted === '-' ? '-' : `${formatted}${suffix}`
}


function formatRuleGroupList(prefix: string, groups: number[] | undefined) {
  if (!groups?.length) {
    return '-'
  }
  const visibleGroups = groups.slice(0, 3)
  const base = `${prefix}规则 ${visibleGroups.join(' / ')}`
  return groups.length > 3 ? `${base} +${groups.length - 3}` : base
}


function formatPairValue(left: number | null | undefined, right: number | null | undefined) {
  if (left === null || left === undefined || !Number.isFinite(left) || right === null || right === undefined || !Number.isFinite(right)) {
    return '-'
  }
  return `${formatMetric(left)}/${formatMetric(right)}`
}

function buildPlaceholderRow(): SummaryRow {
  return { label: '', value: '-', placeholder: true }
}

function toLineData(points: QuantLinePoint[]) {
  return points.map((item) =>
    item.value === null
      ? ({ time: item.time as Time } as WhitespaceData<Time>)
      : ({ time: item.time as Time, value: item.value }),
  )
}

function toNullableNumber(value: unknown) {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

function toHistogramData(points: QuantHistogramPoint[]) {
  return points.map((item) =>
    item.value === null
      ? ({ time: item.time as Time } as WhitespaceData<Time>)
      : ({ time: item.time as Time, value: item.value, color: item.color }),
  )
}

function toVixCandleData(
  points: Array<{
    trade_date: string
    open: number | null
    high: number | null
    low: number | null
    close: number | null
  }>,
) {
  return points.map((item) =>
    item.open === null || item.high === null || item.low === null || item.close === null
      ? ({ time: item.trade_date as Time } as WhitespaceData<Time>)
      : {
          time: item.trade_date as Time,
          open: item.open,
          high: item.high,
          low: item.low,
          close: item.close,
        },
  )
}

function buildValueMap(points: QuantLinePoint[]) {
  const result = new Map<string, number>()
  for (const item of points) {
    if (item.value !== null && Number.isFinite(item.value)) {
      result.set(item.time, item.value)
    }
  }
  return result
}

function buildHistogramValueMap(points: QuantHistogramPoint[]) {
  const result = new Map<string, number>()
  for (const item of points) {
    if (item.value !== null && Number.isFinite(item.value)) {
      result.set(item.time, item.value)
    }
  }
  return result
}

const indicatorValueMaps = computed(() => {
  const payload = indicatorPayload.value
  return {
    ma: payload.ma.map((series) => buildValueMap(series.data)),
    boll: {
      upper: buildValueMap(payload.boll.upper.data),
      middle: buildValueMap(payload.boll.middle.data),
      lower: buildValueMap(payload.boll.lower.data),
    },
    macd: {
      dif: buildValueMap(payload.macd.dif.data),
      dea: buildValueMap(payload.macd.dea.data),
      histogram: buildHistogramValueMap(payload.macd.histogram),
    },
    kdj: {
      k: buildValueMap(payload.kdj.k.data),
      d: buildValueMap(payload.kdj.d.data),
      j: buildValueMap(payload.kdj.j.data),
    },
    rsi: buildValueMap(payload.rsi.data),
    wr: buildValueMap(payload.wr.data),
    emotion: buildValueMap(quantDataset.value.emotion?.data ?? []),
    basis: {
      main: buildValueMap(quantDataset.value.basis?.main.data ?? []),
      adjusted: buildValueMap(quantDataset.value.basis?.adjusted?.data ?? []),
      month: buildValueMap(quantDataset.value.basis?.month.data ?? []),
    },
    breadth: buildValueMap(quantDataset.value.breadth?.data ?? []),
    vix: buildValueMap(quantDataset.value.vix?.data ?? []),
    usVix: buildValueMap(quantDataset.value.usVix?.data ?? []),
    usFearGreed: buildValueMap(quantDataset.value.usFearGreed?.data ?? []),
    usHedge: buildValueMap(quantDataset.value.usHedgeProxy?.data ?? []),
    usPutCall: buildValueMap(quantDataset.value.usPutCall?.data ?? []),
    usTreasury: {
      spread10y2y: buildValueMap(quantDataset.value.usTreasuryYield?.spread10y2y.data ?? []),
      spread10y3m: buildValueMap(quantDataset.value.usTreasuryYield?.spread10y3m.data ?? []),
    },
    usCredit: buildValueMap(quantDataset.value.usCreditSpread?.data ?? []),
  }
})

const activeIndicatorSnapshot = computed(() => {
  if (!activeTradeDate.value) {
    return null
  }

  const tradeDate = activeTradeDate.value
  const maps = indicatorValueMaps.value
  return {
    tradeDate,
    ma: maps.ma.map((map) => map.get(tradeDate)),
    boll: {
      upper: maps.boll.upper.get(tradeDate),
      middle: maps.boll.middle.get(tradeDate),
      lower: maps.boll.lower.get(tradeDate),
    },
    macd: {
      dif: maps.macd.dif.get(tradeDate),
      dea: maps.macd.dea.get(tradeDate),
      histogram: maps.macd.histogram.get(tradeDate),
    },
    kdj: {
      k: maps.kdj.k.get(tradeDate),
      d: maps.kdj.d.get(tradeDate),
      j: maps.kdj.j.get(tradeDate),
    },
    rsi: maps.rsi.get(tradeDate),
    wr: maps.wr.get(tradeDate),
    emotion: maps.emotion.get(tradeDate),
    basis: {
      main: maps.basis.main.get(tradeDate),
      adjusted: maps.basis.adjusted.get(tradeDate),
      month: maps.basis.month.get(tradeDate),
      rollFlag: basisPointByDate.value.get(tradeDate)?.rollFlag ?? false,
      rollDelta: basisPointByDate.value.get(tradeDate)?.rollDelta ?? null,
    },
    breadth: {
      pct: maps.breadth.get(tradeDate),
      upCount: breadthPointByDate.value.get(tradeDate)?.up_count ?? 0,
      totalCount: breadthPointByDate.value.get(tradeDate)?.total_count ?? 0,
    },
    vix: {
      open: vixPointByDate.value.get(tradeDate)?.open_price ?? null,
      high: vixPointByDate.value.get(tradeDate)?.high_price ?? null,
      low: vixPointByDate.value.get(tradeDate)?.low_price ?? null,
      close: maps.vix.get(tradeDate) ?? null,
    },
    usVix: {
      open: usVixPointByDate.value.get(tradeDate)?.open_value ?? null,
      high: usVixPointByDate.value.get(tradeDate)?.high_value ?? null,
      low: usVixPointByDate.value.get(tradeDate)?.low_value ?? null,
      close: maps.usVix.get(tradeDate) ?? null,
    },
    usFearGreed: {
      value: maps.usFearGreed.get(tradeDate) ?? null,
      label: usFearGreedPointByDate.value.get(tradeDate)?.sentiment_label ?? '',
    },
    usHedge: {
      long: usHedgeProxyPointByDate.value.get(tradeDate)?.long_value ?? null,
      short: usHedgeProxyPointByDate.value.get(tradeDate)?.short_value ?? null,
      ratio: maps.usHedge.get(tradeDate) ?? null,
      scope: usHedgeProxyPointByDate.value.get(tradeDate)?.contract_scope ?? '',
      releaseDate: usHedgeProxyPointByDate.value.get(tradeDate)?.release_date ?? null,
    },
    usPutCall: {
      total: maps.usPutCall.get(tradeDate) ?? null,
      index: usPutCallPointByDate.value.get(tradeDate)?.index ?? null,
      equity: usPutCallPointByDate.value.get(tradeDate)?.equity ?? null,
      etf: usPutCallPointByDate.value.get(tradeDate)?.etf ?? null,
    },
    usTreasury: {
      yield3m: usTreasuryYieldPointByDate.value.get(tradeDate)?.yield3m ?? null,
      yield2y: usTreasuryYieldPointByDate.value.get(tradeDate)?.yield2y ?? null,
      yield10y: usTreasuryYieldPointByDate.value.get(tradeDate)?.yield10y ?? null,
      spread10y2y: maps.usTreasury.spread10y2y.get(tradeDate) ?? null,
      spread10y3m: maps.usTreasury.spread10y3m.get(tradeDate) ?? null,
    },
    usCredit: {
      highYieldOas: maps.usCredit.get(tradeDate) ?? null,
      change5d: usCreditSpreadPointByDate.value.get(tradeDate)?.change5d ?? null,
    },
  }
})

const activeHighlightBand = computed(() => {
  if (!activeTradeDate.value) {
    return null
  }
  return props.highlightBands.find((item) => item.tradeDate === activeTradeDate.value) ?? null
})

const summaryCards = computed<SummaryCard[]>(() => {
  if (!activeSnapshot.value || !activeIndicatorSnapshot.value) {
    return []
  }

  const snapshot = activeSnapshot.value
  const indicator = activeIndicatorSnapshot.value
  const overlayRows =
    overlayMode.value === 'ma'
      ? indicatorPayload.value.ma.map((item, index) => ({
          label: item.label,
          value: formatMetric(indicator.ma[index]),
        }))
      : [
          { label: indicatorPayload.value.boll.upper.label, value: formatMetric(indicator.boll.upper) },
          { label: indicatorPayload.value.boll.middle.label, value: formatMetric(indicator.boll.middle) },
          { label: indicatorPayload.value.boll.lower.label, value: formatMetric(indicator.boll.lower) },
          buildPlaceholderRow(),
        ]

  return [
    {
      key: 'market',
      title: '行情',
      hint: snapshot.trade_date,
      rows: [
        { label: '开盘', value: formatMetric(snapshot.open) },
        { label: '最高', value: formatMetric(snapshot.high) },
        { label: '最低', value: formatMetric(snapshot.low) },
        { label: '收盘', value: formatMetric(snapshot.close) },
        { label: '涨跌幅', value: formatMetricWithSuffix(snapshot.pct_chg, '%') },
      ],
    },
    {
      key: 'overlay',
      title: '主图指标',
      hint: overlayMode.value === 'ma' ? '均线' : 'BOLL',
      rows: overlayRows,
    },
    {
      key: 'macd',
      title: 'MACD',
      rows: [
        { label: 'DIF', value: formatMetric(indicator.macd.dif) },
        { label: 'DEA', value: formatMetric(indicator.macd.dea) },
        { label: '柱值', value: formatMetric(indicator.macd.histogram) },
      ],
    },
    {
      key: 'kdj-wr-rsi',
      title: 'KDJ / WR / RSI',
      rows: [
        { label: 'K', value: formatMetric(indicator.kdj.k) },
        { label: 'D', value: formatMetric(indicator.kdj.d) },
        { label: 'J', value: formatMetric(indicator.kdj.j) },
        { label: 'WR', value: formatMetric(indicator.wr) },
        { label: indicatorPayload.value.rsi.label, value: formatMetric(indicator.rsi) },
      ],
    },
    ...(props.supportsAuxiliaryPanels
      ? [
          {
            key: 'extended',
            title: '情绪 / 期现差 / 涨跌家数',
            rows: [
              { label: '情绪指标', value: formatMetric(indicator.emotion) },
              { label: '主连期现差', value: formatMetric(indicator.basis.main) },
              { label: '月连期现差', value: formatMetric(indicator.basis.month) },
              { label: '上涨家数百分比', value: formatMetricWithSuffix(indicator.breadth.pct, '%') },
              { label: '上涨家数', value: formatPairValue(indicator.breadth.upCount, indicator.breadth.totalCount) },
            ],
          },
        ]
      : []),
    ...(props.supportsBasisPanel && !props.supportsAuxiliaryPanels
      ? [
          {
            key: 'basis-summary',
            title: '期现差',
            rows: [
              ...(supportsAdjustedBasisSeries.value
                ? [{ label: '换月调整期现差', value: formatMetric(indicator.basis.adjusted) }]
                : []),
              {
                label: props.showBasisMonthLine ? '主连期现差' : '连续期现差',
                value: formatMetric(indicator.basis.main),
              },
              ...(props.showBasisMonthLine
                ? [{ label: '月连期现差', value: formatMetric(indicator.basis.month) }]
                : []),
              ...(indicator.basis.rollFlag
                ? [{ label: '换月调整幅度', value: formatMetric(indicator.basis.rollDelta) }]
                : []),
            ],
          },
        ]
      : []),
    ...(props.supportsVixPanel
      ? [
          {
            key: 'vix',
            title: 'VIX',
            rows: [
              { label: 'VIX开', value: formatMetric(indicator.vix.open) },
              { label: 'VIX高', value: formatMetric(indicator.vix.high) },
              { label: 'VIX低', value: formatMetric(indicator.vix.low) },
              { label: 'VIX收', value: formatMetric(indicator.vix.close) },
            ],
          },
        ]
      : []),
    ...(props.supportsUsVixPanel
      ? [
          {
            key: 'us-vix',
            title: '美股 VIX',
            rows: [
              { label: 'VIX开', value: formatMetric(indicator.usVix.open) },
              { label: 'VIX高', value: formatMetric(indicator.usVix.high) },
              { label: 'VIX低', value: formatMetric(indicator.usVix.low) },
              { label: 'VIX收', value: formatMetric(indicator.usVix.close) },
            ],
          },
        ]
      : []),
    ...(props.supportsUsFearGreedPanel
      ? [
          {
            key: 'fear-greed',
            title: '恐贪指数',
            rows: [
              { label: '指数值', value: formatMetric(indicator.usFearGreed.value) },
              { label: '情绪标签', value: indicator.usFearGreed.label || '-' },
            ],
          },
        ]
      : []),
    ...(props.supportsUsHedgeProxyPanel
      ? [
          {
            key: 'us-hedge',
            title: '对冲基金代理',
            hint: indicator.usHedge.scope || undefined,
            rows: [
              { label: '代理多头', value: formatMetric(indicator.usHedge.long) },
              { label: '代理空头', value: formatMetric(indicator.usHedge.short) },
              { label: '多空比', value: formatMetric(indicator.usHedge.ratio) },
              { label: '发布日期', value: indicator.usHedge.releaseDate || '-' },
            ],
          },
        ]
      : []),
    ...(props.supportsUsPutCallPanel
      ? [
          {
            key: 'us-put-call',
            title: 'Put/Call',
            rows: [
              { label: '总Put/Call', value: formatMetric(indicator.usPutCall.total) },
              { label: '指数Put/Call', value: formatMetric(indicator.usPutCall.index) },
              { label: '股票Put/Call', value: formatMetric(indicator.usPutCall.equity) },
              { label: 'ETF Put/Call', value: formatMetric(indicator.usPutCall.etf) },
            ],
          },
        ]
      : []),
    ...(props.supportsUsTreasuryYieldPanel
      ? [
          {
            key: 'us-treasury',
            title: '美债收益率 / 利差',
            rows: [
              { label: '3M收益率', value: formatMetric(indicator.usTreasury.yield3m) },
              { label: '2Y收益率', value: formatMetric(indicator.usTreasury.yield2y) },
              { label: '10Y收益率', value: formatMetric(indicator.usTreasury.yield10y) },
              { label: '10Y-2Y利差', value: formatMetric(indicator.usTreasury.spread10y2y) },
              { label: '10Y-3M利差', value: formatMetric(indicator.usTreasury.spread10y3m) },
            ],
          },
        ]
      : []),
    ...(props.supportsUsCreditSpreadPanel
      ? [
          {
            key: 'us-credit',
            title: '高收益债利差',
            rows: [
              { label: 'HY OAS', value: formatMetric(indicator.usCredit.highYieldOas) },
              { label: '5日变化', value: formatMetric(indicator.usCredit.change5d) },
            ],
          },
        ]
      : []),
    {
      key: 'rule-hits',
      title: '命中规则',
      rows: [
        { label: '蓝色命中', value: formatRuleGroupList('蓝色', activeHighlightBand.value?.blueHitGroups) },
        { label: '红色命中', value: formatRuleGroupList('红色', activeHighlightBand.value?.redHitGroups) },
        {
          label: '状态',
          value:
            !activeHighlightBand.value
              ? '-'
              : activeHighlightBand.value.color === 'purple'
                ? '紫色重叠'
                : activeHighlightBand.value.variant === 'striped'
                  ? '同色多组'
                  : '单组命中',
        },
        {
          label: '说明',
          value:
            !activeHighlightBand.value
              ? '-'
              : activeHighlightBand.value.variant === 'striped'
                ? '条纹表示该日存在多组同时命中'
                : '纯色表示该日仅单个规则组命中',
        },
      ],
    },
  ]
})

function createBaseChart(container: HTMLDivElement, showTimeScale: boolean) {
  return createChart(container, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: '#ffffff' },
      textColor: '#14213d',
    },
    rightPriceScale: {
      borderColor: '#e2e8f0',
      autoScale: true,
    },
    leftPriceScale: {
      visible: false,
      borderColor: '#e2e8f0',
      autoScale: true,
    },
    timeScale: {
      borderColor: '#e2e8f0',
      timeVisible: true,
      visible: showTimeScale,
    },
    grid: {
      vertLines: { color: '#f3f4f6' },
      horzLines: { color: '#eef2f7' },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: {
        color: '#94a3b8',
        labelBackgroundColor: '#0f4c75',
      },
      horzLine: {
        color: '#94a3b8',
        labelBackgroundColor: '#0f4c75',
      },
    },
    localization: {
      locale: 'zh-CN',
    },
  })
}

function addLineSeries(chart: IChartApi, color: string, lineWidth: LineWidth = 2, priceScaleId?: string) {
  return chart.addSeries(LineSeries, {
    color,
    lineWidth,
    lastValueVisible: false,
    priceLineVisible: false,
    crosshairMarkerRadius: 3,
    priceScaleId,
  })
}

function addHistogramSeries(chart: IChartApi) {
  return chart.addSeries(HistogramSeries, {
    priceLineVisible: false,
    lastValueVisible: false,
    base: 0,
  })
}

function addCandles(chart: IChartApi) {
  return chart.addSeries(CandlestickSeries, {
    upColor: '#ef4444',
    downColor: '#10b981',
    borderVisible: false,
    wickUpColor: '#ef4444',
    wickDownColor: '#10b981',
  })
}

function addVixCandles(chart: IChartApi) {
  return chart.addSeries(CandlestickSeries, {
    upColor: '#ef4444',
    downColor: '#10b981',
    borderVisible: false,
    wickUpColor: '#ef4444',
    wickDownColor: '#10b981',
    lastValueVisible: false,
    priceLineVisible: false,
  })
}

function syncVisibleRange(sourceKey: PanelKey, range: LogicalRange | null) {
  if (!range || isSyncingRange) {
    return
  }

  isSyncingRange = true
  try {
    getActivePanelKeys().forEach((panelKey) => {
      if (panelKey !== sourceKey) {
        charts[panelKey]?.timeScale().setVisibleLogicalRange(range)
      }
    })
  } finally {
    isSyncingRange = false
  }
}

function syncCrosshair(sourceKey: PanelKey, param: MouseEventParams<Time>) {
  if (isSyncingCrosshair) {
    return
  }

  hoveredTradeDate.value = param.time ? String(param.time) : null
  isSyncingCrosshair = true
  try {
    const time = param.time ? String(param.time) : null
    getActivePanelKeys().forEach((panelKey) => {
      if (panelKey === sourceKey) {
        return
      }

      const chart = charts[panelKey]
      const series = primarySeriesMap.get(panelKey)
      if (!chart || !series || !time) {
        chart?.clearCrosshairPosition()
        return
      }

      const price = panelValueMaps.get(panelKey)?.get(time)
      if (price === undefined) {
        chart.clearCrosshairPosition()
        return
      }

      chart.setCrosshairPosition(price, time as Time, series)
    })
  } finally {
    isSyncingCrosshair = false
  }
}

function maybeRequestMoreHistory(range: LogicalRange | null) {
  if (!range || !props.hasMoreHistory || props.loadingMoreHistory || !mainCandles.value.length) {
    return
  }
  if (range.from > HISTORY_REQUEST_THRESHOLD) {
    return
  }
  const earliestTradeDate = String(mainCandles.value[0]?.time ?? '')
  if (!earliestTradeDate || lastRequestedHistoryBoundary === earliestTradeDate) {
    return
  }
  lastRequestedHistoryBoundary = earliestTradeDate
  emit('requestMoreHistory', earliestTradeDate)
}

function attachSync(panelKey: PanelKey, chart: IChartApi) {
  const visibleRangeHandler = (range: LogicalRange | null) => {
    syncVisibleRange(panelKey, range)
    maybeRequestMoreHistory(range)
  }
  const crosshairHandler = (param: MouseEventParams<Time>) => syncCrosshair(panelKey, param)
  chart.timeScale().subscribeVisibleLogicalRangeChange(visibleRangeHandler)
  chart.subscribeCrosshairMove(crosshairHandler)
  unsubs.push(() => chart.timeScale().unsubscribeVisibleLogicalRangeChange(visibleRangeHandler))
  unsubs.push(() => chart.unsubscribeCrosshairMove(crosshairHandler))
}

function applyDefaultVisibleRange() {
  if (!charts.main) {
    return
  }

  if (!props.defaultVisibleDays || !mainCandles.value.length) {
    charts.main.timeScale().fitContent()
    return
  }

  const lastTime = String(mainCandles.value[mainCandles.value.length - 1].time)
  const lastDate = new Date(parseDateText(lastTime))
  if (Number.isNaN(lastDate.getTime())) {
    charts.main.timeScale().fitContent()
    return
  }

  const startDate = new Date(lastDate)
  startDate.setDate(startDate.getDate() - props.defaultVisibleDays + 1)

  charts.main.timeScale().setVisibleRange({
    from: formatDateText(startDate) as Time,
    to: lastTime as Time,
  })
}

function zoomChart(direction: 'in' | 'out') {
  const mainChart = charts.main
  if (!mainChart || !mainCandles.value.length) {
    return
  }

  const visibleRange = mainChart.timeScale().getVisibleLogicalRange()
  if (!visibleRange) {
    applyDefaultVisibleRange()
    return
  }

  const currentSpan = Math.max(visibleRange.to - visibleRange.from, 8)
  const nextSpan = direction === 'in' ? currentSpan * (1 - props.zoomStep) : currentSpan * (1 + props.zoomStep)
  const minSpan = 8
  const maxSpan = Math.max(mainCandles.value.length + 20, props.defaultVisibleDays)
  const clampedSpan = Math.min(maxSpan, Math.max(minSpan, nextSpan))
  const center = (visibleRange.from + visibleRange.to) / 2

  shouldResetVisibleRange = false
  mainChart.timeScale().setVisibleLogicalRange({
    from: center - clampedSpan / 2,
    to: center + clampedSpan / 2,
  })
}

function cleanupHighlightBindings() {
  highlightBindings.forEach(({ series, primitive }) => {
    series.detachPrimitive(primitive)
  })
  highlightBindings = []
}

function attachHighlightPrimitive(series: AnySeries | null, getHighlights: () => QuantHighlightBand[] = () => props.highlightBands) {
  if (!series) {
    return
  }

  const primitive = new DateHighlightPrimitive(getHighlights())
  series.attachPrimitive(primitive)
  highlightBindings.push({ series, primitive, getHighlights })
}

function syncHighlightBindings() {
  highlightBindings.forEach(({ primitive, getHighlights }) => primitive.setHighlights(getHighlights()))
}

function updateAllSeries() {
  if (!mainCandleSeries) return

  const payload = indicatorPayload.value
  mainCandleSeries.setData(mainCandles.value)

  if (overlayMode.value === 'boll') {
    mainMaSeries.forEach((series) => {
      series.setData([])
    })
    bollSeriesRefs[0]?.setData(toLineData(payload.boll.upper.data))
    bollSeriesRefs[1]?.setData(toLineData(payload.boll.middle.data))
    bollSeriesRefs[2]?.setData(toLineData(payload.boll.lower.data))
  } else {
    mainMaSeries.forEach((series, index) => {
      series.setData(toLineData(payload.ma[index]?.data ?? []))
    })
    bollSeriesRefs[0]?.setData([])
    bollSeriesRefs[1]?.setData([])
    bollSeriesRefs[2]?.setData([])
  }

  panelValueMaps.set('main', new Map(sortedCandles.value.map((item) => [item.trade_date, item.close])))

  if (isSubPanelVisible('macd')) {
    if (!macdDifSeries || !macdDeaSeries || !macdHistogramSeries) return
    macdDifSeries.setData(toLineData(payload.macd.dif.data))
    macdDeaSeries.setData(toLineData(payload.macd.dea.data))
    macdHistogramSeries.setData(toHistogramData(payload.macd.histogram))
    panelValueMaps.set('macd', buildValueMap(payload.macd.dif.data))
  } else {
    panelValueMaps.delete('macd')
  }

  if (isSubPanelVisible('kdj')) {
    if (!kdjSeriesRefs.length) return
    kdjSeriesRefs[0]?.setData(toLineData(payload.kdj.k.data))
    kdjSeriesRefs[1]?.setData(toLineData(payload.kdj.d.data))
    kdjSeriesRefs[2]?.setData(toLineData(payload.kdj.j.data))
    panelValueMaps.set('kdj', buildValueMap(payload.kdj.k.data))
  } else {
    panelValueMaps.delete('kdj')
  }

  if (isSubPanelVisible('wr')) {
    if (!wrSeries) return
    wrSeries.setData(toLineData(payload.wr.data))
    panelValueMaps.set('wr', buildValueMap(payload.wr.data))
  } else {
    panelValueMaps.delete('wr')
  }

  if (isSubPanelVisible('rsi')) {
    if (!rsiSeries) return
    rsiSeries.setData(toLineData(payload.rsi.data))
    panelValueMaps.set('rsi', buildValueMap(payload.rsi.data))
  } else {
    panelValueMaps.delete('rsi')
  }

  if (isSubPanelVisible('emotion')) {
    if (!emotionSeries) return
    emotionSeries.setData(toLineData(quantDataset.value.emotion?.data ?? []))
    panelValueMaps.set('emotion', new Map(emotionSeriesData.value.map((item) => [item.rawDate, item.value])))
  } else {
    panelValueMaps.delete('emotion')
  }

  if (isSubPanelVisible('basis')) {
    if (!basisMainSeries) return
    const activeSeries = activeBasisSeries.value
    basisMainSeries.applyOptions({ color: activeSeries?.color ?? '#dc2626' })
    basisMainSeries.setData(toLineData(activeSeries?.data ?? []))
    if (props.showBasisMonthLine && basisMonthSeries) {
      basisMonthSeries.setData(toLineData(quantDataset.value.basis?.month.data ?? []))
    }
    panelValueMaps.set('basis', buildValueMap(activeSeries?.data ?? []))
  } else {
    panelValueMaps.delete('basis')
  }

  if (isSubPanelVisible('breadth')) {
    if (!breadthSeries || !breadthCountSeries) return
    breadthSeries.setData(toLineData(quantDataset.value.breadth?.data ?? []))
    breadthCountSeries.setData(
      breadthCountSeriesData.value.map((item) => ({
        time: item.time,
        value: item.value,
      })),
    )
    panelValueMaps.set('breadth', new Map(breadthSeriesData.value.map((item) => [item.rawDate, item.value])))
  } else {
    panelValueMaps.delete('breadth')
  }

  if (isSubPanelVisible('vix')) {
    if (!vixSeries) return
    vixSeries.setData(toVixCandleData(vixSeriesData.value))
    panelValueMaps.set(
      'vix',
      new Map(
        vixSeriesData.value
          .filter((item) => item.close !== null)
          .map((item) => [item.trade_date, item.close as number]),
      ),
    )
  } else {
    panelValueMaps.delete('vix')
  }

  if (isSubPanelVisible('usVix')) {
    if (!usVixSeries) return
    usVixSeries.setData(toVixCandleData(usVixSeriesData.value))
    panelValueMaps.set(
      'usVix',
      new Map(
        usVixSeriesData.value
          .filter((item) => item.close !== null)
          .map((item) => [item.trade_date, item.close as number]),
      ),
    )
  } else {
    panelValueMaps.delete('usVix')
  }

  if (isSubPanelVisible('usFearGreed')) {
    if (!usFearGreedSeries) return
    usFearGreedSeries.setData(toLineData(quantDataset.value.usFearGreed?.data ?? []))
    panelValueMaps.set(
      'usFearGreed',
      new Map(usFearGreedSeriesData.value.filter((item) => item.value !== null).map((item) => [item.rawDate, item.value as number])),
    )
  } else {
    panelValueMaps.delete('usFearGreed')
  }

  if (isSubPanelVisible('usHedge')) {
    if (!usHedgeSeries) return
    usHedgeSeries.setData(toLineData(quantDataset.value.usHedgeProxy?.data ?? []))
    panelValueMaps.set(
      'usHedge',
      new Map(usHedgeSeriesData.value.filter((item) => item.value !== null).map((item) => [item.rawDate, item.value as number])),
    )
  } else {
    panelValueMaps.delete('usHedge')
  }

  if (isSubPanelVisible('usPutCall')) {
    if (!usPutCallSeries) return
    const metricConfig = usPutCallMetricConfig[activeUsPutCallKey.value]
    usPutCallSeries.applyOptions({ color: metricConfig.color })
    usPutCallSeries.setData(
      usPutCallSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    panelValueMaps.set(
      'usPutCall',
      new Map(usPutCallSeriesData.value.filter((item) => item.value !== null).map((item) => [item.rawDate, item.value as number])),
    )
  } else {
    panelValueMaps.delete('usPutCall')
  }

  if (isSubPanelVisible('usTreasury')) {
    if (!usTreasurySpread10y2ySeries || !usTreasurySpread10y3mSeries) return
    usTreasurySpread10y2ySeries.setData(toLineData(quantDataset.value.usTreasuryYield?.spread10y2y.data ?? []))
    usTreasurySpread10y3mSeries.setData(toLineData(quantDataset.value.usTreasuryYield?.spread10y3m.data ?? []))
    panelValueMaps.set(
      'usTreasury',
      new Map(
        usTreasurySpread10y2ySeriesData.value
          .filter((item) => item.value !== null)
          .map((item) => [item.rawDate, item.value as number]),
      ),
    )
  } else {
    panelValueMaps.delete('usTreasury')
  }

  if (isSubPanelVisible('usCredit')) {
    if (!usCreditSeries) return
    const metricConfig = usCreditMetricConfig[activeUsCreditKey.value]
    usCreditSeries.applyOptions({ color: metricConfig.color })
    usCreditSeries.setData(
      usCreditSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    panelValueMaps.set(
      'usCredit',
      new Map(usCreditSeriesData.value.filter((item) => item.value !== null).map((item) => [item.rawDate, item.value as number])),
    )
  } else {
    panelValueMaps.delete('usCredit')
  }
}

function renderCharts() {
  const activePanelKeys = getActivePanelKeys()
  if (activePanelKeys.some((panelKey) => !getPanelContainer(panelKey))) return

  try {
    renderError.value = ''

    charts.main = createBaseChart(mainContainerRef.value!, false)
    if (isSubPanelVisible('macd')) charts.macd = createBaseChart(macdContainerRef.value!, false)
    if (isSubPanelVisible('kdj')) charts.kdj = createBaseChart(kdjContainerRef.value!, false)
    if (isSubPanelVisible('wr')) charts.wr = createBaseChart(wrContainerRef.value!, false)
    if (isSubPanelVisible('rsi')) charts.rsi = createBaseChart(rsiContainerRef.value!, false)
    if (isSubPanelVisible('emotion')) {
      charts.emotion = createBaseChart(emotionContainerRef.value!, false)
    }
    if (isSubPanelVisible('basis')) {
      charts.basis = createBaseChart(basisContainerRef.value!, false)
    }
    if (isSubPanelVisible('breadth')) {
      charts.breadth = createBaseChart(breadthContainerRef.value!, true)
      charts.breadth.priceScale('left').applyOptions({
        visible: true,
        borderColor: '#e2e8f0',
        autoScale: true,
      })
    }
    if (isSubPanelVisible('vix')) {
      charts.vix = createBaseChart(vixContainerRef.value!, true)
    }
    if (isSubPanelVisible('usVix')) {
      charts.usVix = createBaseChart(usVixContainerRef.value!, true)
    }
    if (isSubPanelVisible('usFearGreed')) {
      charts.usFearGreed = createBaseChart(usFearGreedContainerRef.value!, true)
    }
    if (isSubPanelVisible('usHedge')) {
      charts.usHedge = createBaseChart(usHedgeContainerRef.value!, true)
    }
    if (isSubPanelVisible('usPutCall')) {
      charts.usPutCall = createBaseChart(usPutCallContainerRef.value!, true)
    }
    if (isSubPanelVisible('usTreasury')) {
      charts.usTreasury = createBaseChart(usTreasuryContainerRef.value!, true)
    }
    if (isSubPanelVisible('usCredit')) {
      charts.usCredit = createBaseChart(usCreditContainerRef.value!, true)
    }

    mainCandleSeries = addCandles(charts.main)
    mainMaSeries = indicatorPayload.value.ma.map((item) => addLineSeries(charts.main!, item.color, 2))
    bollSeriesRefs = [
      addLineSeries(charts.main, indicatorPayload.value.boll.upper.color, 1),
      addLineSeries(charts.main, indicatorPayload.value.boll.middle.color, 1),
      addLineSeries(charts.main, indicatorPayload.value.boll.lower.color, 1),
    ]

    macdDifSeries = charts.macd ? addLineSeries(charts.macd, indicatorPayload.value.macd.dif.color, 2) : null
    macdDeaSeries = charts.macd ? addLineSeries(charts.macd, indicatorPayload.value.macd.dea.color, 2) : null
    macdHistogramSeries = charts.macd ? addHistogramSeries(charts.macd) : null

    kdjSeriesRefs = charts.kdj
      ? [
          addLineSeries(charts.kdj, indicatorPayload.value.kdj.k.color, 2),
          addLineSeries(charts.kdj, indicatorPayload.value.kdj.d.color, 2),
          addLineSeries(charts.kdj, indicatorPayload.value.kdj.j.color, 2),
        ]
      : []

    wrSeries = charts.wr ? addLineSeries(charts.wr, indicatorPayload.value.wr.color, 2) : null
    rsiSeries = charts.rsi ? addLineSeries(charts.rsi, indicatorPayload.value.rsi.color, 2) : null
    emotionSeries = charts.emotion ? addLineSeries(charts.emotion, quantDataset.value.emotion?.color ?? '#0f4c75', 2) : null
    basisMainSeries = charts.basis ? addLineSeries(charts.basis, activeBasisSeries.value?.color ?? '#dc2626', 2) : null
    basisMonthSeries =
      charts.basis && props.showBasisMonthLine
        ? addLineSeries(charts.basis, quantDataset.value.basis?.month.color ?? '#2563eb', 2)
        : null
    breadthSeries = charts.breadth ? addLineSeries(charts.breadth, quantDataset.value.breadth?.color ?? '#0ea5e9', 2) : null
    breadthCountSeries = charts.breadth ? addLineSeries(charts.breadth, '#f97316', 2, 'left') : null
    vixSeries = charts.vix ? addVixCandles(charts.vix) : null
    usVixSeries = charts.usVix ? addVixCandles(charts.usVix) : null
    usFearGreedSeries = charts.usFearGreed ? addLineSeries(charts.usFearGreed, quantDataset.value.usFearGreed?.color ?? '#dc2626', 2) : null
    usHedgeSeries = charts.usHedge ? addLineSeries(charts.usHedge, quantDataset.value.usHedgeProxy?.color ?? '#0f766e', 2) : null
    usPutCallSeries = charts.usPutCall ? addLineSeries(charts.usPutCall, usPutCallMetricConfig[activeUsPutCallKey.value].color, 2) : null
    usTreasurySpread10y2ySeries = charts.usTreasury
      ? addLineSeries(charts.usTreasury, quantDataset.value.usTreasuryYield?.spread10y2y.color ?? '#2563eb', 2)
      : null
    usTreasurySpread10y3mSeries = charts.usTreasury
      ? addLineSeries(charts.usTreasury, quantDataset.value.usTreasuryYield?.spread10y3m.color ?? '#f97316', 2)
      : null
    usCreditSeries = charts.usCredit ? addLineSeries(charts.usCredit, usCreditMetricConfig[activeUsCreditKey.value].color, 2) : null

    primarySeriesMap.set('main', mainCandleSeries)
    if (macdDifSeries) primarySeriesMap.set('macd', macdDifSeries)
    if (kdjSeriesRefs[0]) primarySeriesMap.set('kdj', kdjSeriesRefs[0])
    if (wrSeries) primarySeriesMap.set('wr', wrSeries)
    if (rsiSeries) primarySeriesMap.set('rsi', rsiSeries)
    if (emotionSeries) primarySeriesMap.set('emotion', emotionSeries)
    if (basisMainSeries) primarySeriesMap.set('basis', basisMainSeries)
    if (breadthSeries) primarySeriesMap.set('breadth', breadthSeries)
    if (vixSeries) primarySeriesMap.set('vix', vixSeries)
    if (usVixSeries) primarySeriesMap.set('usVix', usVixSeries)
    if (usFearGreedSeries) primarySeriesMap.set('usFearGreed', usFearGreedSeries)
    if (usHedgeSeries) primarySeriesMap.set('usHedge', usHedgeSeries)
    if (usPutCallSeries) primarySeriesMap.set('usPutCall', usPutCallSeries)
    if (usTreasurySpread10y2ySeries) primarySeriesMap.set('usTreasury', usTreasurySpread10y2ySeries)
    if (usCreditSeries) primarySeriesMap.set('usCredit', usCreditSeries)

    getActivePanelKeys().forEach((panelKey) => {
      const chart = charts[panelKey]
      if (chart) {
        attachSync(panelKey, chart)
      }
    })

    cleanupHighlightBindings()
    attachHighlightPrimitive(mainCandleSeries)
    attachHighlightPrimitive(macdDifSeries)
    attachHighlightPrimitive(kdjSeriesRefs[0] ?? null)
    attachHighlightPrimitive(wrSeries)
    attachHighlightPrimitive(rsiSeries)
    if (props.supportsAuxiliaryPanels) {
      attachHighlightPrimitive(emotionSeries)
      attachHighlightPrimitive(breadthSeries)
    }
    if (props.supportsBasisPanel) {
      attachHighlightPrimitive(basisMainSeries, () => [...props.highlightBands, ...basisRollHighlights.value])
    }
    if (props.supportsVixPanel) {
      attachHighlightPrimitive(vixSeries)
    }
    if (props.supportsUsVixPanel) {
      attachHighlightPrimitive(usVixSeries)
    }
    if (props.supportsUsFearGreedPanel) {
      attachHighlightPrimitive(usFearGreedSeries)
    }
    if (props.supportsUsHedgeProxyPanel) {
      attachHighlightPrimitive(usHedgeSeries)
    }
    if (props.supportsUsPutCallPanel) {
      attachHighlightPrimitive(usPutCallSeries)
    }
    if (props.supportsUsTreasuryYieldPanel) {
      attachHighlightPrimitive(usTreasurySpread10y2ySeries)
    }
    if (props.supportsUsCreditSpreadPanel) {
      attachHighlightPrimitive(usCreditSeries)
    }

    updateAllSeries()
    syncHighlightBindings()
    if (shouldResetVisibleRange && mainCandles.value.length) {
      applyDefaultVisibleRange()
      shouldResetVisibleRange = false
    }
  } catch (error) {
    renderError.value = `量化图表渲染失败：${String(error)}`
    console.error(error)
  }
}

function disposeCharts() {
  unsubs.forEach((dispose) => dispose())
  unsubs = []

  cleanupHighlightBindings()

  ALL_PANEL_KEYS.forEach((panelKey) => {
    charts[panelKey]?.remove()
    delete charts[panelKey]
  })

  primarySeriesMap.clear()
  panelValueMaps.clear()
  mainCandleSeries = null
  mainMaSeries = []
  bollSeriesRefs = []
  macdDifSeries = null
  macdDeaSeries = null
  macdHistogramSeries = null
  kdjSeriesRefs = []
  wrSeries = null
  rsiSeries = null
  emotionSeries = null
  basisMainSeries = null
  basisMonthSeries = null
  breadthSeries = null
  breadthCountSeries = null
  vixSeries = null
  usVixSeries = null
  usFearGreedSeries = null
  usHedgeSeries = null
  usPutCallSeries = null
  usTreasurySpread10y2ySeries = null
  usTreasurySpread10y3mSeries = null
  usCreditSeries = null
}

watch(mainCandles, (next, previous) => {
  const previousVisibleRange = charts.main?.timeScale().getVisibleLogicalRange() ?? null
  const previousEarliest = String(previous[0]?.time ?? '')
  updateAllSeries()
  if (shouldResetVisibleRange && mainCandles.value.length) {
    applyDefaultVisibleRange()
    shouldResetVisibleRange = false
    return
  }

  const nextEarliest = String(next[0]?.time ?? '')
  const prependedBars =
    previousVisibleRange && previousEarliest && nextEarliest && nextEarliest < previousEarliest
      ? next.filter((item) => String(item.time) < previousEarliest).length
      : 0

  if (previousVisibleRange && prependedBars > 0) {
    charts.main?.timeScale().setVisibleLogicalRange({
      from: previousVisibleRange.from + prependedBars,
      to: previousVisibleRange.to + prependedBars,
    })
  }
})

watch(emotionSeriesData, () => {
  if (props.supportsAuxiliaryPanels) updateAllSeries()
})

watch(breadthSeriesData, () => {
  if (props.supportsAuxiliaryPanels) updateAllSeries()
})

watch(breadthCountSeriesData, () => {
  if (props.supportsAuxiliaryPanels) updateAllSeries()
})

watch(vixSeriesData, () => {
  if (props.supportsVixPanel) updateAllSeries()
})

watch(usVixSeriesData, () => {
  if (props.supportsUsVixPanel) updateAllSeries()
})

watch(usFearGreedSeriesData, () => {
  if (props.supportsUsFearGreedPanel) updateAllSeries()
})

watch(usHedgeSeriesData, () => {
  if (props.supportsUsHedgeProxyPanel) updateAllSeries()
})

watch(usPutCallSeriesData, () => {
  if (props.supportsUsPutCallPanel) updateAllSeries()
})

watch(usTreasurySpread10y2ySeriesData, () => {
  if (props.supportsUsTreasuryYieldPanel) updateAllSeries()
})

watch(usTreasurySpread10y3mSeriesData, () => {
  if (props.supportsUsTreasuryYieldPanel) updateAllSeries()
})

watch(usCreditSeriesData, () => {
  if (props.supportsUsCreditSpreadPanel) updateAllSeries()
})

watch(
  () =>
    `${props.supportsAuxiliaryPanels}:${props.supportsBasisPanel}:${props.showBasisMonthLine}:${props.supportsVixPanel}:${props.supportsUsVixPanel}:${props.supportsUsFearGreedPanel}:${props.supportsUsHedgeProxyPanel}:${props.supportsUsPutCallPanel}:${props.supportsUsTreasuryYieldPanel}:${props.supportsUsCreditSpreadPanel}`,
  async () => {
    await rebuildChartsPreservingRange()
  },
)

watch(
  () => props.symbolCode,
  () => {
    hoveredTradeDate.value = null
    shouldResetVisibleRange = true
    lastRequestedHistoryBoundary = null
    activeBasisKey.value = supportsAdjustedBasisSeries.value ? 'adjusted' : 'main'
  },
)

watch(
  () => props.candles[0]?.trade_date ?? null,
  (nextEarliest, previousEarliest) => {
    if (nextEarliest && nextEarliest !== previousEarliest) {
      lastRequestedHistoryBoundary = null
    }
  },
)

watch(
  () => props.futuresBasisPoints,
  () => {
    if (!supportsAdjustedBasisSeries.value) {
      activeBasisKey.value = 'main'
    } else if (activeBasisKey.value !== 'main') {
      activeBasisKey.value = 'adjusted'
    }
    if (props.supportsBasisPanel) updateAllSeries()
    syncHighlightBindings()
  },
  { deep: true },
)

watch(
  () => activeBasisKey.value,
  () => {
    if (props.supportsBasisPanel) updateAllSeries()
  },
)

watch(
  () => props.params,
  () => {
    updateAllSeries()
  },
  { deep: true },
)

watch(
  () => overlayMode.value,
  () => {
    updateAllSeries()
  },
)

watch(
  () => props.highlightBands,
  () => {
    syncHighlightBindings()
  },
  { deep: true },
)

onMounted(() => {
  renderCharts()
})

onBeforeUnmount(() => {
  disposeCharts()
  hoveredTradeDate.value = null
  shouldResetVisibleRange = true
  lastRequestedHistoryBoundary = null
})
</script>

<template>
  <section class="quant-chart-shell">
    <div class="quant-chart-summary">
      <div class="quant-chart-summary-head">
        <div class="quant-chart-symbol-row">
          <select class="input quant-chart-symbol-select" :value="symbolCode" @change="handleIndexSelect" :disabled="loading || !marketOptions?.length">
            <option v-for="option in marketOptions" :key="option.code" :value="option.code">
              {{ option.name }}
            </option>
          </select>
          <span class="quant-chart-symbol-code">({{ symbolCode }})</span>
        </div>

        <div class="quant-chart-head-actions">
          <button type="button" class="quant-chart-tool-btn" title="放大" :disabled="loading || !sortedCandles.length" @click="zoomChart('in')">+
          </button>
          <button type="button" class="quant-chart-tool-btn" title="缩小" :disabled="loading || !sortedCandles.length" @click="zoomChart('out')">-
          </button>
          <button type="button" class="quant-chart-tool-btn quant-chart-tool-btn-gear" title="调整指标参数" :disabled="loading" @click="emit('openSettings')">⚙
          </button>
        </div>
      </div>

      <div class="quant-chart-switches">
        <button type="button" class="quant-switch" :class="{ active: overlayMode === 'ma' }" @click="overlayMode = 'ma'">
          均线
        </button>
        <button type="button" class="quant-switch" :class="{ active: overlayMode === 'boll' }" @click="overlayMode = 'boll'">
          BOLL
        </button>
      </div>

      <div v-if="summaryCards.length" class="quant-kpi-grid">
        <article v-for="card in summaryCards" :key="card.key" class="quant-kpi-card">
          <div class="quant-kpi-head">
            <h4 class="quant-kpi-title">{{ card.title }}</h4>
            <span v-if="card.hint" class="quant-kpi-hint">{{ card.hint }}</span>
          </div>
          <div class="quant-kpi-list">
            <div v-for="(row, index) in card.rows" :key="`${card.key}-${index}`" class="quant-kpi-row" :class="{ 'quant-kpi-placeholder': row.placeholder }">
              <span class="quant-kpi-label">{{ row.label || '\u00A0' }}</span>
              <strong class="quant-kpi-value">{{ row.value }}</strong>
            </div>
          </div>
        </article>
      </div>
    </div>

    <p v-if="loading" class="muted">量化图表加载中...</p>
    <p v-if="renderError" class="error">{{ renderError }}</p>
    <p v-if="!loading && !sortedCandles.length" class="muted">当前没有可展示的指数历史数据。</p>

    <div class="quant-panel"><div class="quant-panel-head"><h3>主图</h3><div class="quant-legend"><span v-for="item in mainLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><div ref="mainContainerRef" class="quant-panel-chart quant-panel-chart-main"></div></div>

    <div class="quant-subpanel-switches"><span class="quant-subpanel-switches-label">副图指标</span><button v-for="option in availableSubPanelOptions" :key="option.key" type="button" class="quant-switch" :class="{ active: isSubPanelVisible(option.key) }" @click="toggleSubPanel(option.key)">{{ option.label }}</button></div>

    <div v-if="isSubPanelVisible('macd')" class="quant-panel"><div class="quant-panel-head"><h3>MACD</h3><div class="quant-legend"><span v-for="item in macdLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><div ref="macdContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('kdj')" class="quant-panel"><div class="quant-panel-head"><h3>KDJ</h3><div class="quant-legend"><span v-for="item in kdjLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><div ref="kdjContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('wr')" class="quant-panel"><div class="quant-panel-head"><h3>WR</h3><div class="quant-legend"><span v-for="item in wrLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><div ref="wrContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('rsi')" class="quant-panel"><div class="quant-panel-head"><h3>RSI</h3><div class="quant-legend"><span v-for="item in rsiLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><div ref="rsiContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('emotion')" class="quant-panel"><div class="quant-panel-head"><h3>情绪指标</h3><div class="quant-legend"><span v-for="item in emotionLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><p v-if="emotionLoading" class="muted">情绪指标加载中...</p><p v-else-if="emotionErrorMessage" class="error">{{ emotionErrorMessage }}</p><div ref="emotionContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('basis')" class="quant-panel"><div class="quant-panel-head"><h3>期现差</h3><div class="quant-legend"><button v-for="item in basisLegend" :key="item.label" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectBasisMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button></div></div><p v-if="futuresBasisLoading" class="muted">期现差指标加载中...</p><p v-else-if="futuresBasisErrorMessage" class="error">{{ futuresBasisErrorMessage }}</p><div ref="basisContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('breadth')" class="quant-panel"><div class="quant-panel-head"><h3>涨跌家数</h3><div class="quant-legend"><span v-for="item in breadthLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><p v-if="breadthLoading" class="muted">涨跌家数加载中...</p><p v-else-if="breadthErrorMessage" class="error">{{ breadthErrorMessage }}</p><div ref="breadthContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('vix')" class="quant-panel"><div class="quant-panel-head"><h3>VIX</h3><div class="quant-legend"><span v-for="item in vixLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><p v-if="!vixPoints.length" class="muted">当前范围暂无 VIX 数据</p><div ref="vixContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('usVix')" class="quant-panel"><div class="quant-panel-head"><h3>美股 VIX</h3><div class="quant-legend"><span v-for="item in usVixLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><p v-if="!usVixPoints.length" class="muted">当前范围暂无美股 VIX 数据</p><div ref="usVixContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('usFearGreed')" class="quant-panel"><div class="quant-panel-head"><h3>恐贪指数</h3><div class="quant-legend"><span v-for="item in usFearGreedLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><p v-if="!usFearGreedPoints.length" class="muted">当前范围暂无恐贪指数数据</p><div ref="usFearGreedContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('usHedge')" class="quant-panel"><div class="quant-panel-head"><h3>对冲基金代理</h3><div class="quant-legend"><span v-for="item in usHedgeLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><p v-if="!usHedgeProxyPoints.length" class="muted">当前范围暂无对冲基金代理数据</p><div ref="usHedgeContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>
    <div v-if="isSubPanelVisible('usPutCall')" class="quant-panel"><div class="quant-panel-head"><h3>Put/Call</h3><div class="quant-legend"><button v-for="item in usPutCallLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectUsPutCallMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button></div></div><p v-if="!usPutCallPoints.length" class="muted">当前范围暂无 Put/Call 数据</p><div ref="usPutCallContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>
    <div v-if="isSubPanelVisible('usTreasury')" class="quant-panel"><div class="quant-panel-head"><h3>美债利差</h3><div class="quant-legend"><span v-for="item in usTreasuryLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span></div></div><p v-if="!usTreasuryYieldPoints.length" class="muted">当前范围暂无美债收益率数据</p><div ref="usTreasuryContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>
    <div v-if="isSubPanelVisible('usCredit')" class="quant-panel"><div class="quant-panel-head"><h3>高收益债利差</h3><div class="quant-legend"><button v-for="item in usCreditLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectUsCreditMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button></div></div><p v-if="!usCreditSpreadPoints.length" class="muted">当前范围暂无高收益债利差数据</p><div ref="usCreditContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>
  </section>
</template>

<style scoped>
.quant-chart-shell {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.quant-chart-summary {
  display: grid;
  gap: 10px;
}

.quant-chart-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.quant-chart-head-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
}

.quant-chart-symbol-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.quant-chart-symbol-select {
  width: auto;
  min-width: 180px;
  max-width: 240px;
  font-size: 22px;
  font-weight: 700;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  color: #14213d;
}

.quant-chart-symbol-select:focus {
  box-shadow: none;
}

.quant-chart-symbol-code {
  font-size: 22px;
  font-weight: 700;
  color: #14213d;
}

.quant-chart-tool-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(20, 33, 61, 0.12);
  border-radius: 12px;
  background: rgba(20, 33, 61, 0.04);
  color: #14213d;
  font: inherit;
  font-size: 20px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.quant-chart-tool-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(15, 76, 117, 0.1);
  box-shadow: 0 8px 16px rgba(20, 33, 61, 0.08);
}

.quant-chart-tool-btn:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.quant-chart-tool-btn-gear {
  font-size: 18px;
}

.quant-chart-details {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  color: #475569;
  font-size: 13px;
}

.quant-chart-detail {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 76, 117, 0.08);
  color: #0f4c75;
  font-weight: 600;
}

.quant-chart-switches,
.quant-subpanel-switches {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.quant-subpanel-switches {
  padding: 2px 0;
}

.quant-subpanel-switches-label {
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}

.quant-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.quant-detail-card {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.92);
  border: 1px solid rgba(20, 33, 61, 0.08);
}

.quant-detail-card h4 {
  margin: 0;
  font-size: 13px;
  color: #334155;
}

.quant-detail-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quant-switch {
  border: 1px solid rgba(20, 33, 61, 0.12);
  background: rgba(20, 33, 61, 0.04);
  color: #14213d;
  border-radius: 999px;
  padding: 8px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.quant-switch.active {
  background: linear-gradient(135deg, #0f4c75, #2563eb);
  border-color: transparent;
  color: #fff;
}

.quant-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 12px 14px;
  border-radius: 20px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  background: rgba(255, 255, 255, 0.72);
}

.quant-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.quant-panel-head h3 {
  margin: 0;
  font-size: 15px;
}

.quant-legend {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.quant-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.quant-legend-button {
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.quant-legend-button.is-muted {
  color: #94a3b8;
}

.quant-legend-button:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.35);
  outline-offset: 3px;
  border-radius: 999px;
}

.quant-legend-item i {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
}

.quant-panel-chart {
  width: 100%;
}

.quant-panel-chart-main {
  min-height: 420px;
  height: 420px;
}

.quant-panel-chart-sub {
  min-height: 160px;
  height: 160px;
}

.muted,
.error {
  margin: 0;
  font-size: 13px;
}

.muted {
  color: #64748b;
}

.error {
  color: #b91c1c;
}

@media (max-width: 900px) {
  .quant-chart-summary-head {
    align-items: flex-start;
  }

  .quant-chart-head-actions {
    margin-left: 0;
  }

  .quant-chart-symbol-select,
  .quant-chart-symbol-code {
    font-size: 18px;
  }

  .quant-chart-details {
    justify-content: flex-start;
  }

  .quant-panel-chart-main {
    min-height: 340px;
    height: 340px;
  }

  .quant-panel-chart-sub {
    min-height: 140px;
    height: 140px;
  }
}
</style>
