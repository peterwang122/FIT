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
  type Logical,
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
  IndexBasisDeltaPoint,
  IndexBreadthPoint,
  IndexCffexNetShortDeltaPoint,
  IndexCnOptionFlowPutCallPoint,
  IndexCnOptionPutCallPoint,
  IndexCnOptionSeries,
  IndexCnOptionVixPoint,
  IndexEmotionPoint,
  IndexFundPurchaseLimitPoint,
  IndexMarginTradingPoint,
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
  | 'cnPutCall'
  | 'cnFlowPutCall'
  | 'cnOptionVix'
  | 'cffexNetShortDelta'
  | 'basisDelta'
  | 'fundPurchaseLimit'
  | 'marginTrading'
  | 'usVix'
  | 'usFearGreed'
  | 'usHedge'
  | 'usPutCall'
  | 'usTreasury'
  | 'usCredit'
type SubPanelKey = Exclude<PanelKey, 'main'>
type MainOverlayMode = 'ma' | 'boll'
type UsPutCallMetricKey = 'total' | 'index' | 'equity' | 'etf'
type CnOptionPutCallMetricKey = 'currentMonth' | 'nextMonth' | 'quarter1' | 'quarter2'
type CnOptionFlowPutCallMetricKey = 'volume' | 'turnover' | 'turnoverCallPut'
const CFFEX_NET_SHORT_DELTA_WINDOWS = [5, 7, 14, 20, 30, 60, 120] as const
type CffexNetShortDeltaWindow = (typeof CFFEX_NET_SHORT_DELTA_WINDOWS)[number]
type CffexNetShortDeltaSource = 'top20' | 'citic'
type CffexNetShortDeltaPayloadKey =
  | `top20_delta_${CffexNetShortDeltaWindow}d`
  | `citic_delta_${CffexNetShortDeltaWindow}d`
type BasisDeltaWindow = CffexNetShortDeltaWindow
type BasisDeltaMetricKey = 'main' | 'month'
type BasisDeltaPayloadKey = `${BasisDeltaMetricKey}_delta_${BasisDeltaWindow}d`
type FundPurchaseLimitMetricKey = 'count' | 'pct'
type MarginTradingMetricKey = 'financing' | 'securitiesLending' | 'total' | 'netBuy' | 'leverage'
type MarginTradingMetricUnit = 'cnyYi' | 'percent'
type UsCreditMetricKey = 'hyOas' | 'change5d'
type BasisMetricKey = 'adjusted' | 'main'
const CNY_PER_YI = 100_000_000
type AnySeries = ISeriesApi<SeriesType, Time>
type LineSeriesApi = ISeriesApi<'Line', Time>
type HistogramSeriesApi = ISeriesApi<'Histogram', Time>
type CandleSeriesApi = ISeriesApi<'Candlestick', Time>
type PrimitiveBinding = {
  series: AnySeries
  primitive: DateHighlightPrimitive
  getHighlights: () => QuantHighlightBand[]
}
type SummaryRow = { label: string; value: string; placeholder?: boolean; title?: string }
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
  'cnPutCall',
  'cnFlowPutCall',
  'cnOptionVix',
  'cffexNetShortDelta',
  'basisDelta',
  'fundPurchaseLimit',
  'marginTrading',
  'usVix',
  'usFearGreed',
  'usHedge',
  'usPutCall',
  'usTreasury',
  'usCredit',
]
const ALL_SUB_PANEL_KEYS: SubPanelKey[] = ALL_PANEL_KEYS.filter((item): item is SubPanelKey => item !== 'main')
const DEFAULT_HIDDEN_TECHNICAL_SUB_PANELS = new Set<SubPanelKey>(['macd', 'kdj', 'wr', 'rsi'])
const DEFAULT_VISIBLE_SUB_PANEL_KEYS: SubPanelKey[] = ALL_SUB_PANEL_KEYS.filter(
  (item) => !DEFAULT_HIDDEN_TECHNICAL_SUB_PANELS.has(item),
)

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
    cnOptionPutCallPoints?: IndexCnOptionPutCallPoint[]
    cnOptionFlowPutCallPoints?: IndexCnOptionFlowPutCallPoint[]
    cnOptionSeries?: IndexCnOptionSeries[]
    cffexNetShortDeltaPoints?: IndexCffexNetShortDeltaPoint[]
    basisDeltaPoints?: IndexBasisDeltaPoint[]
    fundPurchaseLimitPoints?: IndexFundPurchaseLimitPoint[]
    supportsFundPurchaseLimitPanel?: boolean
    marginTradingPoints?: IndexMarginTradingPoint[]
    supportsMarginTradingPanel?: boolean
    supportsCnOptionPutCallPanel?: boolean
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
    cnOptionPutCallPoints: () => [],
    cnOptionFlowPutCallPoints: () => [],
    cnOptionSeries: () => [],
    cffexNetShortDeltaPoints: () => [],
    basisDeltaPoints: () => [],
    fundPurchaseLimitPoints: () => [],
    supportsFundPurchaseLimitPanel: false,
    marginTradingPoints: () => [],
    supportsMarginTradingPanel: false,
    supportsCnOptionPutCallPanel: false,
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
const cnPutCallContainerRef = ref<HTMLDivElement | null>(null)
const cnFlowPutCallContainerRef = ref<HTMLDivElement | null>(null)
const cnOptionVixContainerRef = ref<HTMLDivElement | null>(null)
const cffexNetShortDeltaContainerRef = ref<HTMLDivElement | null>(null)
const basisDeltaContainerRef = ref<HTMLDivElement | null>(null)
const fundPurchaseLimitContainerRef = ref<HTMLDivElement | null>(null)
const marginTradingContainerRef = ref<HTMLDivElement | null>(null)
const usVixContainerRef = ref<HTMLDivElement | null>(null)
const usFearGreedContainerRef = ref<HTMLDivElement | null>(null)
const usHedgeContainerRef = ref<HTMLDivElement | null>(null)
const usPutCallContainerRef = ref<HTMLDivElement | null>(null)
const usTreasuryContainerRef = ref<HTMLDivElement | null>(null)
const usCreditContainerRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')
const overlayMode = ref<MainOverlayMode>('ma')
const hoveredTradeDate = ref<string | null>(null)
const visibleSubPanels = ref<SubPanelKey[]>([...DEFAULT_VISIBLE_SUB_PANEL_KEYS])
const activeUsPutCallKey = ref<UsPutCallMetricKey>('total')
const activeCnOptionPutCallKey = ref<CnOptionPutCallMetricKey>('currentMonth')
const activeCnOptionFlowPutCallKey = ref<CnOptionFlowPutCallMetricKey>('volume')
const activeCnOptionPriceSourceKey = ref('')
const activeCnOptionFlowSourceKey = ref('')
const activeCnOptionVixSourceKey = ref('')
const activeCffexNetShortDeltaSource = ref<CffexNetShortDeltaSource>('top20')
const activeCffexNetShortDeltaWindow = ref<CffexNetShortDeltaWindow>(7)
const activeBasisDeltaMetric = ref<BasisDeltaMetricKey>('main')
const activeBasisDeltaWindow = ref<BasisDeltaWindow>(7)
const activeFundPurchaseLimitMetric = ref<FundPurchaseLimitMetricKey>('count')
const activeMarginTradingMetric = ref<MarginTradingMetricKey>('financing')
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
let cnPutCallSeries: LineSeriesApi | null = null
let cnPutCallReferenceSeries: LineSeriesApi | null = null
let cnFlowPutCallSeries: LineSeriesApi | null = null
let cnFlowPutCallReferenceSeries: LineSeriesApi | null = null
let cnOptionVixSeries: CandleSeriesApi | null = null
let cffexNetShortDeltaSeries: LineSeriesApi | null = null
let cffexNetShortDeltaReferenceSeries: LineSeriesApi | null = null
let basisDeltaSeries: LineSeriesApi | null = null
let basisDeltaReferenceSeries: LineSeriesApi | null = null
let fundPurchaseLimitSeries: LineSeriesApi | null = null
let marginTradingSeries: LineSeriesApi | null = null
let usVixSeries: CandleSeriesApi | null = null
let usFearGreedSeries: LineSeriesApi | null = null
let usHedgeSeries: LineSeriesApi | null = null
let usPutCallSeries: LineSeriesApi | null = null
let usPutCallReferenceSeries: LineSeriesApi | null = null
let usTreasurySpread10y2ySeries: LineSeriesApi | null = null
let usTreasurySpread10y3mSeries: LineSeriesApi | null = null
let usCreditSeries: LineSeriesApi | null = null
let highlightBindings: PrimitiveBinding[] = []
let isSyncingRange = false
let isSyncingCrosshair = false
let shouldResetVisibleRange = true
let chartRebuildRequested = false
let chartRebuildPromise: Promise<void> | null = null
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
  { key: 'cnPutCall', label: 'Put/Call', available: props.supportsCnOptionPutCallPanel },
  { key: 'cnFlowPutCall', label: '成交P/C', available: props.supportsCnOptionPutCallPanel },
  {
    key: 'cnOptionVix',
    label: '自算VIX',
    available: props.cnOptionSeries.some((item) => (item.vix_points ?? []).length > 0),
  },
  { key: 'cffexNetShortDelta', label: '净空单增量', available: props.supportsAuxiliaryPanels },
  { key: 'basisDelta', label: '期现差变化', available: props.supportsAuxiliaryPanels },
  { key: 'fundPurchaseLimit', label: '公募限购', available: props.supportsFundPurchaseLimitPanel },
  { key: 'marginTrading', label: '融资融券', available: props.supportsMarginTradingPanel },
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
  if (panelKey === 'cnPutCall') return cnPutCallContainerRef.value
  if (panelKey === 'cnFlowPutCall') return cnFlowPutCallContainerRef.value
  if (panelKey === 'cnOptionVix') return cnOptionVixContainerRef.value
  if (panelKey === 'cffexNetShortDelta') return cffexNetShortDeltaContainerRef.value
  if (panelKey === 'basisDelta') return basisDeltaContainerRef.value
  if (panelKey === 'fundPurchaseLimit') return fundPurchaseLimitContainerRef.value
  if (panelKey === 'marginTrading') return marginTradingContainerRef.value
  if (panelKey === 'usVix') return usVixContainerRef.value
  if (panelKey === 'usFearGreed') return usFearGreedContainerRef.value
  if (panelKey === 'usHedge') return usHedgeContainerRef.value
  if (panelKey === 'usPutCall') return usPutCallContainerRef.value
  if (panelKey === 'usTreasury') return usTreasuryContainerRef.value
  if (panelKey === 'usCredit') return usCreditContainerRef.value
  return null
}

function rebuildChartsPreservingRange(): Promise<void> {
  chartRebuildRequested = true
  if (chartRebuildPromise) return chartRebuildPromise

  chartRebuildPromise = (async () => {
    try {
      while (chartRebuildRequested) {
        chartRebuildRequested = false
        const visibleRange = charts.main?.timeScale().getVisibleLogicalRange() ?? null
        const candleCount = mainCandles.value.length
        const shouldRestoreRange =
          visibleRange !== null &&
          Number.isFinite(visibleRange.from) &&
          Number.isFinite(visibleRange.to) &&
          visibleRange.to >= 0 &&
          visibleRange.from <= candleCount - 1

        shouldResetVisibleRange = false
        disposeCharts()
        await nextTick()
        renderCharts()

        if (!charts.main || !candleCount) continue
        if (shouldRestoreRange && visibleRange) {
          charts.main.timeScale().setVisibleLogicalRange(visibleRange)
        } else {
          applyDefaultVisibleRange()
        }
      }
    } finally {
      chartRebuildPromise = null
    }
  })()

  return chartRebuildPromise
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
      includeCnOptionPutCall: props.supportsCnOptionPutCallPanel,
      includeCnOptionFlowPutCall: props.supportsCnOptionPutCallPanel,
      includeCffexNetShortDelta: props.supportsAuxiliaryPanels,
      includeBasisDelta: props.supportsAuxiliaryPanels,
      includeFundPurchaseLimit: props.supportsFundPurchaseLimitPanel,
      includeMarginTrading: props.supportsMarginTradingPanel,
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
      cnOptionPutCallPoints: props.cnOptionPutCallPoints,
      cnOptionFlowPutCallPoints: props.cnOptionFlowPutCallPoints,
      cnOptionSeries: props.cnOptionSeries,
      cffexNetShortDeltaPoints: props.cffexNetShortDeltaPoints,
      basisDeltaPoints: props.basisDeltaPoints,
      fundPurchaseLimitPoints: props.fundPurchaseLimitPoints,
      marginTradingPoints: props.marginTradingPoints,
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

const cnOptionPutCallMetricConfig: Record<CnOptionPutCallMetricKey, { label: string; color: string }> = {
  currentMonth: { label: '当月', color: '#7c3aed' },
  nextMonth: { label: '下月', color: '#2563eb' },
  quarter1: { label: '季月1', color: '#f97316' },
  quarter2: { label: '季月2', color: '#0f766e' },
}

const cnOptionFlowPutCallMetricConfig: Record<CnOptionFlowPutCallMetricKey, { label: string; color: string }> = {
  volume: { label: '成交量P/C', color: '#2563eb' },
  turnover: { label: '成交额P/C', color: '#f97316' },
  turnoverCallPut: { label: '成交额C/P', color: '#0f766e' },
}

const cffexNetShortDeltaSourceConfig: Record<CffexNetShortDeltaSource, { label: string; color: string }> = {
  top20: { label: '前20', color: '#2563eb' },
  citic: { label: '中信', color: '#f97316' },
}
const cffexNetShortDeltaSources = ['top20', 'citic'] as const
const cffexNetShortDeltaWindowOptions = CFFEX_NET_SHORT_DELTA_WINDOWS.map((window) => ({
  key: window,
  label: `${window}D`,
}))
const basisDeltaMetricConfig: Record<BasisDeltaMetricKey, { label: string; color: string }> = {
  main: { label: '主连', color: '#dc2626' },
  month: { label: '月连', color: '#2563eb' },
}
const basisDeltaMetrics = ['main', 'month'] as const
const basisDeltaWindowOptions = CFFEX_NET_SHORT_DELTA_WINDOWS.map((window) => ({
  key: window,
  label: `${window}D`,
}))

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

function getCnOptionPutCallMetricValue(item: IndexCnOptionPutCallPoint | undefined, key: CnOptionPutCallMetricKey) {
  if (!item) return null
  const value =
    key === 'currentMonth'
      ? item.current_month_put_call_ratio
      : key === 'nextMonth'
        ? item.next_month_put_call_ratio
        : key === 'quarter1'
          ? item.quarter_1_put_call_ratio
          : item.quarter_2_put_call_ratio
  return toNullableNumber(value)
}

function getCnOptionFlowPutCallMetricValue(
  item: IndexCnOptionFlowPutCallPoint | undefined,
  key: CnOptionFlowPutCallMetricKey,
) {
  if (!item) return null
  const value =
    key === 'volume'
      ? item.volume_put_call_ratio
      : key === 'turnover'
        ? item.turnover_put_call_ratio
        : item.turnover_call_put_ratio
  return toNullableNumber(value)
}

function getCffexNetShortDeltaMetricValue(
  item: IndexCffexNetShortDeltaPoint | undefined,
  source: CffexNetShortDeltaSource,
  window: CffexNetShortDeltaWindow,
) {
  if (!item) return null
  const payloadKey = `${source}_delta_${window}d` as CffexNetShortDeltaPayloadKey
  const value = item[payloadKey]
  return toNullableNumber(value)
}

function getBasisDeltaMetricValue(
  item: IndexBasisDeltaPoint | undefined,
  metric: BasisDeltaMetricKey,
  window: BasisDeltaWindow,
) {
  if (!item) return null
  const payloadKey = `${metric}_delta_${window}d` as BasisDeltaPayloadKey
  return toNullableNumber(item[payloadKey])
}

function getCnOptionPutCallMetricMonth(item: IndexCnOptionPutCallPoint | undefined, key: CnOptionPutCallMetricKey) {
  if (!item) return null
  return key === 'currentMonth'
    ? item.current_month_contract_month
    : key === 'nextMonth'
      ? item.next_month_contract_month
      : key === 'quarter1'
      ? item.quarter_1_contract_month
      : item.quarter_2_contract_month
}

function getCnOptionPutCallSpecialFlag(item: IndexCnOptionPutCallPoint | undefined, key: CnOptionPutCallMetricKey) {
  if (!item) return false
  return key === 'currentMonth'
    ? item.current_month_special_calculation
    : key === 'nextMonth'
      ? item.next_month_special_calculation
      : key === 'quarter1'
        ? item.quarter_1_special_calculation
        : item.quarter_2_special_calculation
}

function getCnOptionPutCallSpecialNote(item: IndexCnOptionPutCallPoint | undefined, key: CnOptionPutCallMetricKey) {
  if (!item) return null
  const note =
    key === 'currentMonth'
      ? item.current_month_special_note
      : key === 'nextMonth'
        ? item.next_month_special_note
        : key === 'quarter1'
          ? item.quarter_1_special_note
          : item.quarter_2_special_note
  return typeof note === 'string' && note.trim() ? note.trim() : null
}

function getCnOptionPutCallSpecialNotes(item: IndexCnOptionPutCallPoint | undefined) {
  if (!item) return []
  return (Object.keys(cnOptionPutCallMetricConfig) as CnOptionPutCallMetricKey[])
    .map((key) => getCnOptionPutCallSpecialNote(item, key))
    .filter((note): note is string => Boolean(note))
}

function buildCnOptionPutCallSummaryRows(item: IndexCnOptionPutCallPoint | undefined): SummaryRow[] {
  const rows: SummaryRow[] = (Object.entries(cnOptionPutCallMetricConfig) as Array<[CnOptionPutCallMetricKey, { label: string }]>).map(
    ([key, config]) => {
      const contractMonth = getCnOptionPutCallMetricMonth(item, key)
      return {
        label: contractMonth ? `${config.label}(${contractMonth})` : config.label,
        value: formatMetric(getCnOptionPutCallMetricValue(item, key)),
      }
    },
  )
  const specialNotes = [...new Set(getCnOptionPutCallSpecialNotes(item))]
  const specialNoteText = specialNotes.length ? specialNotes.join('；') : '-'
  rows.push({
    label: '特殊计算',
    value: specialNotes.length ? '特殊点位' : '-',
    title: specialNotes.length ? specialNoteText : undefined,
  })
  return rows
}

function buildCnOptionFlowPutCallSummaryRows(item: IndexCnOptionFlowPutCallPoint | undefined): SummaryRow[] {
  return [
    { label: '成交量P/C', value: formatMetric(item?.volume_put_call_ratio) },
    { label: '成交额P/C', value: formatMetric(item?.turnover_put_call_ratio) },
    { label: '成交额C/P', value: formatMetric(item?.turnover_call_put_ratio) },
  ]
}

function buildCnOptionVixSummaryRows(item: IndexCnOptionVixPoint | undefined): SummaryRow[] {
  const nearLabel = item?.near_contract_month
    ? `${item.near_contract_month} / ${item.near_strike_count ?? '-'}档`
    : '-'
  const nextLabel = item?.next_contract_month
    ? `${item.next_contract_month} / ${item.next_strike_count ?? '-'}档`
    : '-'
  const comparisonRow = (
    label: string,
    calculated: number | null | undefined,
    reference: number | null | undefined,
    error: number | null | undefined,
    errorPct: number | null | undefined,
  ): SummaryRow => ({
    label,
    value: `${formatMetric(calculated)} / ${formatMetric(reference)}`,
    title: error === null || error === undefined
      ? undefined
      : `自算减采集：${formatSignedMetric(error)}（${formatSignedPercent(errorPct)}）`,
  })
  const validationLabel = !item?.uses_minute_ohlc
    ? '未用分钟线'
    : item.reference_match_type === 'direct_product'
      ? '同ETF直接校验'
      : item.reference_match_type === 'same_index_proxy'
        ? '同指数代理校验'
        : '无采集参照'
  const minuteCoverage = item?.uses_minute_ohlc
    ? `${item.minute_mid_quote_count ?? '-'}/${item.minute_count ?? '-'}`
    : '-'
  return [
    comparisonRow('开盘(算/采)', item?.vix_open, item?.reference_vix_open, item?.open_error, item?.open_error_pct),
    comparisonRow('最高(算/采)', item?.vix_high, item?.reference_vix_high, item?.high_error, item?.high_error_pct),
    comparisonRow('最低(算/采)', item?.vix_low, item?.reference_vix_low, item?.low_error, item?.low_error_pct),
    comparisonRow('收盘(算/采)', item?.vix_close, item?.reference_vix_close, item?.close_error, item?.close_error_pct),
    {
      label: '平均绝对误差',
      value: item?.ohlc_mean_abs_error === null || item?.ohlc_mean_abs_error === undefined
        ? '-'
        : `${formatMetric(item.ohlc_mean_abs_error)} / ${formatPercent(item.ohlc_mean_abs_pct_error)}`,
    },
    { label: '分钟双边/总数', value: minuteCoverage },
    { label: '校验口径', value: validationLabel },
    { label: '近月', value: nearLabel },
    { label: '次月', value: nextLabel },
  ]
}

function buildCffexNetShortDeltaSummaryRows(
  item: IndexCffexNetShortDeltaPoint | undefined,
  window: CffexNetShortDeltaWindow,
  emotionValue: number | undefined,
): SummaryRow[] {
  return [
    {
      label: `前20 ${window}D`,
      value: formatMetric(item?.[`top20_delta_${window}d` as CffexNetShortDeltaPayloadKey]),
    },
    {
      label: `中信 ${window}D`,
      value: formatMetric(item?.[`citic_delta_${window}d` as CffexNetShortDeltaPayloadKey]),
    },
    { label: '情绪指标', value: formatMetric(emotionValue) },
  ]
}

function buildBasisDeltaSummaryRows(item: IndexBasisDeltaPoint | undefined, window: BasisDeltaWindow): SummaryRow[] {
  return [
    {
      label: `主连 ${window}D`,
      value: formatMetric(item?.[`main_delta_${window}d` as BasisDeltaPayloadKey]),
    },
    {
      label: `月连 ${window}D`,
      value: formatMetric(item?.[`month_delta_${window}d` as BasisDeltaPayloadKey]),
    },
  ]
}

const availableCnOptionSeries = computed<IndexCnOptionSeries[]>(() => {
  if (props.cnOptionSeries.length) return props.cnOptionSeries
  if (!props.cnOptionPutCallPoints.length && !props.cnOptionFlowPutCallPoints.length) return []
  return [{
    source_key: 'cffex:legacy',
    exchange: 'CFFEX',
    exchange_label: '中金所',
    product_code: '',
    product_name: '股指期权',
    put_call_points: props.cnOptionPutCallPoints,
    flow_points: props.cnOptionFlowPutCallPoints,
    vix_points: [],
  }]
})

function preferredCnOptionSourceKey(series: IndexCnOptionSeries[]) {
  const prefersCffex = ['上证50', '沪深300', '中证1000'].includes(props.symbolName)
  if (prefersCffex) {
    const cffex = series.find((item) => item.exchange === 'CFFEX')
    if (cffex) return cffex.source_key
  }
  if (props.symbolName === '科创50') {
    const star = series.find((item) => item.exchange === 'SSE' && item.product_code === '588000')
    if (star) return star.source_key
  }
  return series.find((item) => item.exchange === 'SSE')?.source_key ?? series[0]?.source_key ?? ''
}

function ensureCnOptionSourceSelections() {
  const series = availableCnOptionSeries.value
  const preferred = preferredCnOptionSourceKey(series)
  if (!series.some((item) => item.source_key === activeCnOptionPriceSourceKey.value)) {
    activeCnOptionPriceSourceKey.value = preferred
  }
  if (!series.some((item) => item.source_key === activeCnOptionFlowSourceKey.value)) {
    activeCnOptionFlowSourceKey.value = preferred
  }
  const vixSeries = series.filter((item) => (item.vix_points ?? []).length > 0)
  if (!vixSeries.some((item) => item.source_key === activeCnOptionVixSourceKey.value)) {
    activeCnOptionVixSourceKey.value = preferredCnOptionSourceKey(vixSeries)
  }
}

watch(
  () => `${props.symbolCode}:${availableCnOptionSeries.value.map((item) => item.source_key).join('|')}`,
  ensureCnOptionSourceSelections,
  { immediate: true },
)

const activeCnOptionPriceSeries = computed(
  () => availableCnOptionSeries.value.find((item) => item.source_key === activeCnOptionPriceSourceKey.value),
)
const activeCnOptionFlowSeries = computed(
  () => availableCnOptionSeries.value.find((item) => item.source_key === activeCnOptionFlowSourceKey.value),
)
const availableCnOptionVixSeries = computed(() =>
  availableCnOptionSeries.value.filter((item) => (item.vix_points ?? []).length > 0),
)
const activeCnOptionVixSeries = computed(
  () => availableCnOptionVixSeries.value.find((item) => item.source_key === activeCnOptionVixSourceKey.value),
)
const cnOptionExchangeOptions = computed(() => {
  const seen = new Set<string>()
  return availableCnOptionSeries.value
    .filter((item) => {
      if (seen.has(item.exchange)) return false
      seen.add(item.exchange)
      return true
    })
    .map((item) => ({ value: item.exchange, label: item.exchange_label }))
})
const activeCnOptionPriceExchange = computed(() => activeCnOptionPriceSeries.value?.exchange ?? '')
const activeCnOptionFlowExchange = computed(() => activeCnOptionFlowSeries.value?.exchange ?? '')
const activeCnOptionVixExchange = computed(() => activeCnOptionVixSeries.value?.exchange ?? '')
const cnOptionPriceProductOptions = computed(() =>
  availableCnOptionSeries.value.filter((item) => item.exchange === activeCnOptionPriceExchange.value),
)
const cnOptionFlowProductOptions = computed(() =>
  availableCnOptionSeries.value.filter((item) => item.exchange === activeCnOptionFlowExchange.value),
)
const cnOptionVixExchangeOptions = computed(() => {
  const seen = new Set<string>()
  return availableCnOptionVixSeries.value
    .filter((item) => {
      if (seen.has(item.exchange)) return false
      seen.add(item.exchange)
      return true
    })
    .map((item) => ({ value: item.exchange, label: item.exchange_label }))
})
const cnOptionVixProductOptions = computed(() =>
  availableCnOptionVixSeries.value.filter((item) => item.exchange === activeCnOptionVixExchange.value),
)

const cnOptionPutCallSeriesData = computed(() => {
  const rowByDate = new Map((activeCnOptionPriceSeries.value?.put_call_points ?? []).map((item) => [item.trade_date, item]))
  const activeKey = activeCnOptionPutCallKey.value
  return sortedCandles.value.map((item) => ({
    time: item.trade_date as Time,
    rawDate: item.trade_date,
    value: getCnOptionPutCallMetricValue(rowByDate.get(item.trade_date), activeKey),
  }))
})

const cnOptionFlowPutCallSeriesData = computed(() => {
  const rowByDate = new Map((activeCnOptionFlowSeries.value?.flow_points ?? []).map((item) => [item.trade_date, item]))
  const activeKey = activeCnOptionFlowPutCallKey.value
  return sortedCandles.value.map((item) => ({
    time: item.trade_date as Time,
    rawDate: item.trade_date,
    value: getCnOptionFlowPutCallMetricValue(rowByDate.get(item.trade_date), activeKey),
  }))
})

const cnOptionVixSeriesData = computed(() => {
  const rowByDate = new Map(
    (activeCnOptionVixSeries.value?.vix_points ?? []).map((item) => [item.trade_date, item]),
  )
  return sortedCandles.value.map((item) => {
    const point = rowByDate.get(item.trade_date)
    return {
      trade_date: item.trade_date,
      open: toNullableNumber(point?.vix_open),
      high: toNullableNumber(point?.vix_high),
      low: toNullableNumber(point?.vix_low),
      close: toNullableNumber(point?.vix_close),
    }
  })
})

const cffexNetShortDeltaSeriesData = computed(() => {
  const rowByDate = new Map(props.cffexNetShortDeltaPoints.map((item) => [item.trade_date, item]))
  const activeSource = activeCffexNetShortDeltaSource.value
  const activeWindow = activeCffexNetShortDeltaWindow.value
  return sortedCandles.value.map((item) => ({
    time: item.trade_date as Time,
    rawDate: item.trade_date,
    value: getCffexNetShortDeltaMetricValue(rowByDate.get(item.trade_date), activeSource, activeWindow),
  }))
})

const basisDeltaSeriesData = computed(() => {
  const rowByDate = new Map(props.basisDeltaPoints.map((item) => [item.trade_date, item]))
  const activeMetric = activeBasisDeltaMetric.value
  const activeWindow = activeBasisDeltaWindow.value
  return sortedCandles.value.map((item) => ({
    time: item.trade_date as Time,
    rawDate: item.trade_date,
    value: getBasisDeltaMetricValue(rowByDate.get(item.trade_date), activeMetric, activeWindow),
  }))
})

const fundPurchaseLimitMetricConfig: Record<FundPurchaseLimitMetricKey, { label: string; color: string }> = {
  count: { label: '大额限购家数', color: '#2563eb' },
  pct: { label: '大额限购比例', color: '#f97316' },
}

const fundPurchaseLimitPointByDate = computed(
  () => new Map(props.fundPurchaseLimitPoints.map((item) => [item.trade_date, item])),
)

const fundPurchaseLimitSeriesData = computed(() => {
  const activeMetric = activeFundPurchaseLimitMetric.value
  return sortedCandles.value.map((item) => {
    const point = fundPurchaseLimitPointByDate.value.get(item.trade_date)
    return {
      time: item.trade_date as Time,
      rawDate: item.trade_date,
      value: toNullableNumber(activeMetric === 'count' ? point?.limited_fund_count : point?.limited_fund_pct),
    }
  })
})

const marginTradingMetricConfig: Record<MarginTradingMetricKey, {
  label: string
  color: string
  field: keyof IndexMarginTradingPoint
  unit: MarginTradingMetricUnit
}> = {
  financing: { label: '融资余额', color: '#2563eb', field: 'financing_balance', unit: 'cnyYi' },
  securitiesLending: { label: '融券余额', color: '#7c3aed', field: 'securities_lending_balance', unit: 'cnyYi' },
  total: { label: '两融余额', color: '#0f766e', field: 'total_balance', unit: 'cnyYi' },
  netBuy: { label: '融资净买入', color: '#dc2626', field: 'financing_net_buy_amount', unit: 'cnyYi' },
  leverage: { label: '杠杆率', color: '#d97706', field: 'leverage_ratio_pct', unit: 'percent' },
}

const marginTradingPanelTitle = computed(() =>
  marginTradingMetricConfig[activeMarginTradingMetric.value].unit === 'percent'
    ? 'A股融资融券（%）'
    : 'A股融资融券（亿元）',
)

const marginTradingPointByDate = computed(
  () => new Map(props.marginTradingPoints.map((item) => [item.trade_date, item])),
)

const marginTradingSeriesData = computed(() => {
  const metric = marginTradingMetricConfig[activeMarginTradingMetric.value]
  const field = metric.field
  return sortedCandles.value.map((item) => {
    const point = marginTradingPointByDate.value.get(item.trade_date)
    const rawValue = toNullableNumber(point?.[field] as number | null | undefined)
    return {
      time: item.trade_date as Time,
      rawDate: item.trade_date,
      value: rawValue === null || metric.unit === 'percent' ? rawValue : rawValue / CNY_PER_YI,
    }
  })
})

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
          rollType:
            typeof item.basis_roll_type === 'string' && item.basis_roll_type.trim()
              ? item.basis_roll_type.trim()
              : '',
          rollContracts: Array.isArray(item.basis_roll_contracts)
            ? item.basis_roll_contracts.map((contract) => String(contract).trim().toUpperCase()).filter(Boolean)
            : [],
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

const cnOptionPutCallPointByDate = computed(
  () => new Map((activeCnOptionPriceSeries.value?.put_call_points ?? []).map((item) => [item.trade_date, item])),
)

const cnOptionFlowPutCallPointByDate = computed(
  () => new Map((activeCnOptionFlowSeries.value?.flow_points ?? []).map((item) => [item.trade_date, item])),
)

const cnOptionVixPointByDate = computed(
  () => new Map((activeCnOptionVixSeries.value?.vix_points ?? []).map((item) => [item.trade_date, item])),
)

const cffexNetShortDeltaPointByDate = computed(
  () => new Map(props.cffexNetShortDeltaPoints.map((item) => [item.trade_date, item])),
)

const basisDeltaPointByDate = computed(
  () => new Map(props.basisDeltaPoints.map((item) => [item.trade_date, item])),
)

const cnOptionPutCallSpecialHighlights = computed<QuantHighlightBand[]>(() =>
  (activeCnOptionPriceSeries.value?.put_call_points ?? [])
    .filter((item) =>
      (Object.keys(cnOptionPutCallMetricConfig) as CnOptionPutCallMetricKey[]).some((key) =>
        getCnOptionPutCallSpecialFlag(item, key),
      ),
    )
    .map((item) => ({
      tradeDate: item.trade_date,
      color: 'amber',
      variant: 'solid',
    })),
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

const cnOptionPutCallLegend = computed(() =>
  (
    Object.entries(cnOptionPutCallMetricConfig) as Array<[CnOptionPutCallMetricKey, { label: string; color: string }]>
  ).map(([key, item]) => ({
    key,
    label: item.label,
    color: item.color,
    active: activeCnOptionPutCallKey.value === key,
  })),
)

const cnOptionFlowPutCallLegend = computed(() =>
  (
    Object.entries(cnOptionFlowPutCallMetricConfig) as Array<
      [CnOptionFlowPutCallMetricKey, { label: string; color: string }]
    >
  ).map(([key, item]) => ({
    key,
    label: item.label,
    color: item.color,
    active: activeCnOptionFlowPutCallKey.value === key,
  })),
)

const cffexNetShortDeltaSourceLegend = computed(() =>
  cffexNetShortDeltaSources.map((key) => ({
    key,
    label: cffexNetShortDeltaSourceConfig[key].label,
    color: cffexNetShortDeltaSourceConfig[key].color,
    active: activeCffexNetShortDeltaSource.value === key,
  })),
)

const cffexNetShortDeltaWindowLegend = computed(() =>
  cffexNetShortDeltaWindowOptions.map((item) => ({
    ...item,
    active: activeCffexNetShortDeltaWindow.value === item.key,
  })),
)

const basisDeltaMetricLegend = computed(() =>
  basisDeltaMetrics.map((key) => ({
    key,
    label: basisDeltaMetricConfig[key].label,
    color: basisDeltaMetricConfig[key].color,
    active: activeBasisDeltaMetric.value === key,
  })),
)

const basisDeltaWindowLegend = computed(() =>
  basisDeltaWindowOptions.map((item) => ({
    ...item,
    active: activeBasisDeltaWindow.value === item.key,
  })),
)

const fundPurchaseLimitLegend = computed(() =>
  (Object.entries(fundPurchaseLimitMetricConfig) as Array<
    [FundPurchaseLimitMetricKey, { label: string; color: string }]
  >).map(([key, item]) => ({
    key,
    label: item.label,
    color: item.color,
    active: activeFundPurchaseLimitMetric.value === key,
  })),
)

const marginTradingLegend = computed(() =>
  (Object.entries(marginTradingMetricConfig) as Array<
    [MarginTradingMetricKey, (typeof marginTradingMetricConfig)[MarginTradingMetricKey]]
  >).map(([key, item]) => ({
    key,
    label: item.label,
    color: item.color,
    active: activeMarginTradingMetric.value === key,
  })),
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

function selectCnOptionPutCallMetric(key: CnOptionPutCallMetricKey) {
  activeCnOptionPutCallKey.value = key
  updateAllSeries()
}

function selectCnOptionFlowPutCallMetric(key: CnOptionFlowPutCallMetricKey) {
  activeCnOptionFlowPutCallKey.value = key
  updateAllSeries()
}

function selectCnOptionExchange(event: Event, panel: 'price' | 'flow' | 'vix') {
  const exchange = (event.target as HTMLSelectElement | null)?.value
  if (!exchange) return
  const candidates = (
    panel === 'vix' ? availableCnOptionVixSeries.value : availableCnOptionSeries.value
  ).filter((item) => item.exchange === exchange)
  const preferred = (
    props.symbolName === '科创50'
      ? candidates.find((item) => item.product_code === '588000')
      : undefined
  ) ?? candidates[0]
  if (!preferred) return
  if (panel === 'price') activeCnOptionPriceSourceKey.value = preferred.source_key
  else if (panel === 'flow') activeCnOptionFlowSourceKey.value = preferred.source_key
  else activeCnOptionVixSourceKey.value = preferred.source_key
  updateAllSeries()
}

function selectCnOptionProduct(event: Event, panel: 'price' | 'flow' | 'vix') {
  const sourceKey = (event.target as HTMLSelectElement | null)?.value
  if (!sourceKey) return
  if (panel === 'price') activeCnOptionPriceSourceKey.value = sourceKey
  else if (panel === 'flow') activeCnOptionFlowSourceKey.value = sourceKey
  else activeCnOptionVixSourceKey.value = sourceKey
  updateAllSeries()
}

function selectCffexNetShortDeltaSource(source: CffexNetShortDeltaSource) {
  activeCffexNetShortDeltaSource.value = source
  updateAllSeries()
}

function selectCffexNetShortDeltaWindow(window: CffexNetShortDeltaWindow) {
  activeCffexNetShortDeltaWindow.value = window
  updateAllSeries()
}

function selectBasisDeltaMetric(metric: BasisDeltaMetricKey) {
  activeBasisDeltaMetric.value = metric
  updateAllSeries()
}

function selectBasisDeltaWindow(window: BasisDeltaWindow) {
  activeBasisDeltaWindow.value = window
  updateAllSeries()
}

function selectFundPurchaseLimitMetric(metric: FundPurchaseLimitMetricKey) {
  activeFundPurchaseLimitMetric.value = metric
  updateAllSeries()
}

function selectMarginTradingMetric(metric: MarginTradingMetricKey) {
  activeMarginTradingMetric.value = metric
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

function formatSignedMetric(value: number | null | undefined) {
  const formatted = formatMetric(value)
  if (formatted === '-') return '-'
  return value !== undefined && value !== null && value > 0 ? `+${formatted}` : formatted
}

function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? '-'
    : `${value.toFixed(2)}%`
}

function formatSignedPercent(value: number | null | undefined) {
  const formatted = formatPercent(value)
  if (formatted === '-') return '-'
  return value !== undefined && value !== null && value > 0 ? `+${formatted}` : formatted
}

function formatMetricWithSuffix(value: number | null | undefined, suffix: string) {
  const formatted = formatMetric(value)
  return formatted === '-' ? '-' : `${formatted}${suffix}`
}

function formatCnyYi(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  const amountYi = value / CNY_PER_YI
  return `${amountYi.toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}亿元`
}

function formatYiAxisValue(value: number) {
  return `${value.toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}亿`
}

function marginTradingPriceFormat(metric: MarginTradingMetricKey) {
  return marginTradingMetricConfig[metric].unit === 'percent'
    ? {
        type: 'custom' as const,
        minMove: 0.001,
        formatter: (value: number) => `${value.toFixed(2)}%`,
      }
    : {
        type: 'custom' as const,
        minMove: 0.01,
        formatter: formatYiAxisValue,
      }
}


function formatRuleGroupList(groups: number[] | undefined) {
  if (!groups?.length) {
    return '-'
  }
  return groups.join(' / ')
}


function formatPairValue(left: number | null | undefined, right: number | null | undefined) {
  if (left === null || left === undefined || !Number.isFinite(left) || right === null || right === undefined || !Number.isFinite(right)) {
    return '-'
  }
  return `${formatMetric(left)}/${formatMetric(right)}`
}

function formatContractCodes(contracts: string[] | null | undefined) {
  if (!contracts?.length) {
    return '-'
  }
  const visibleContracts = contracts.slice(0, 4)
  const base = visibleContracts.join(' / ')
  return contracts.length > 4 ? `${base} +${contracts.length - 4}` : base
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
    cnOptionPutCall: new Map(
      cnOptionPutCallSeriesData.value
        .filter((item) => item.value !== null)
        .map((item) => [item.rawDate, item.value as number]),
    ),
    cnOptionFlowPutCall: new Map(
      cnOptionFlowPutCallSeriesData.value
        .filter((item) => item.value !== null)
        .map((item) => [item.rawDate, item.value as number]),
    ),
    cnOptionVix: new Map(
      cnOptionVixSeriesData.value
        .filter((item) => item.close !== null)
        .map((item) => [item.trade_date, item.close as number]),
    ),
    cffexNetShortDelta: new Map(
      cffexNetShortDeltaSeriesData.value
        .filter((item) => item.value !== null)
        .map((item) => [item.rawDate, item.value as number]),
    ),
    basisDelta: new Map(
      basisDeltaSeriesData.value
        .filter((item) => item.value !== null)
        .map((item) => [item.rawDate, item.value as number]),
    ),
    fundPurchaseLimit: new Map(
      fundPurchaseLimitSeriesData.value
        .filter((item) => item.value !== null)
        .map((item) => [item.rawDate, item.value as number]),
    ),
    marginTrading: new Map(
      marginTradingSeriesData.value
        .filter((item) => item.value !== null)
        .map((item) => [item.rawDate, item.value as number]),
    ),
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
      rollType: basisPointByDate.value.get(tradeDate)?.rollType ?? '',
      rollContracts: basisPointByDate.value.get(tradeDate)?.rollContracts ?? [],
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
    cnOptionPutCall: {
      value: maps.cnOptionPutCall.get(tradeDate) ?? null,
      contractMonth:
        getCnOptionPutCallMetricMonth(cnOptionPutCallPointByDate.value.get(tradeDate), activeCnOptionPutCallKey.value) ?? '',
    },
    cnOptionFlowPutCall: {
      value: maps.cnOptionFlowPutCall.get(tradeDate) ?? null,
      volume: cnOptionFlowPutCallPointByDate.value.get(tradeDate)?.volume_put_call_ratio ?? null,
      turnover: cnOptionFlowPutCallPointByDate.value.get(tradeDate)?.turnover_put_call_ratio ?? null,
      turnoverCallPut: cnOptionFlowPutCallPointByDate.value.get(tradeDate)?.turnover_call_put_ratio ?? null,
    },
    cnOptionVix: {
      open: cnOptionVixPointByDate.value.get(tradeDate)?.vix_open ?? null,
      high: cnOptionVixPointByDate.value.get(tradeDate)?.vix_high ?? null,
      low: cnOptionVixPointByDate.value.get(tradeDate)?.vix_low ?? null,
      close: maps.cnOptionVix.get(tradeDate) ?? null,
    },
    cffexNetShortDelta: {
      value: maps.cffexNetShortDelta.get(tradeDate) ?? null,
      top20Delta7d: cffexNetShortDeltaPointByDate.value.get(tradeDate)?.top20_delta_7d ?? null,
      top20Delta30d: cffexNetShortDeltaPointByDate.value.get(tradeDate)?.top20_delta_30d ?? null,
      citicDelta7d: cffexNetShortDeltaPointByDate.value.get(tradeDate)?.citic_delta_7d ?? null,
      citicDelta30d: cffexNetShortDeltaPointByDate.value.get(tradeDate)?.citic_delta_30d ?? null,
    },
    basisDelta: {
      value: maps.basisDelta.get(tradeDate) ?? null,
    },
    fundPurchaseLimit: {
      value: maps.fundPurchaseLimit.get(tradeDate) ?? null,
      limitedCount: fundPurchaseLimitPointByDate.value.get(tradeDate)?.limited_fund_count ?? null,
      totalCount: fundPurchaseLimitPointByDate.value.get(tradeDate)?.total_fund_count ?? null,
      limitedPct: fundPurchaseLimitPointByDate.value.get(tradeDate)?.limited_fund_pct ?? null,
    },
    marginTrading: {
      value: maps.marginTrading.get(tradeDate) ?? null,
      financing: marginTradingPointByDate.value.get(tradeDate)?.financing_balance ?? null,
      securitiesLending:
        marginTradingPointByDate.value.get(tradeDate)?.securities_lending_balance ?? null,
      total: marginTradingPointByDate.value.get(tradeDate)?.total_balance ?? null,
      netBuy:
        marginTradingPointByDate.value.get(tradeDate)?.financing_net_buy_amount ?? null,
      leverage: marginTradingPointByDate.value.get(tradeDate)?.leverage_ratio_pct ?? null,
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
  const basisContractRollContracts =
    indicator.basis.rollType === 'contract_last_trade' && indicator.basis.rollContracts.length
      ? indicator.basis.rollContracts
      : []
  const basisContractRollTitle = formatContractCodes(basisContractRollContracts)
  const basisContractRollRows =
    props.supportsBasisPanel && props.showBasisMonthLine
      ? [
          {
            label: '合约最后交易日',
            value: basisContractRollContracts.length ? '合约到期' : '-',
            title: basisContractRollContracts.length ? basisContractRollTitle : undefined,
          },
        ]
      : []
  const basisAdjustmentRows =
    indicator.basis.rollFlag && indicator.basis.rollType !== 'contract_last_trade'
      ? [{ label: '换月调整幅度', value: formatMetric(indicator.basis.rollDelta) }]
      : []

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
            title: '期现差 / 涨跌家数',
            rows: [
              { label: '主连期现差', value: formatMetric(indicator.basis.main) },
              { label: '月连期现差', value: formatMetric(indicator.basis.month) },
              ...basisContractRollRows,
              { label: '上涨家数百分比', value: formatMetricWithSuffix(indicator.breadth.pct, '%') },
              { label: '上涨家数', value: formatPairValue(indicator.breadth.upCount, indicator.breadth.totalCount) },
            ],
          },
        ]
      : []),
    ...(props.supportsFundPurchaseLimitPanel
      ? [
          {
            key: 'fund-purchase-limit',
            title: 'A股公募基金大额限购',
            hint: fundPurchaseLimitMetricConfig[activeFundPurchaseLimitMetric.value].label,
            rows: [
              { label: '大额限购家数', value: formatMetric(indicator.fundPurchaseLimit.limitedCount) },
              { label: '基金总数', value: formatMetric(indicator.fundPurchaseLimit.totalCount) },
              { label: '大额限购比例', value: formatPercent(indicator.fundPurchaseLimit.limitedPct) },
            ],
          },
        ]
      : []),
    ...(props.supportsMarginTradingPanel
      ? [
          {
            key: 'margin-trading',
            title: 'A股融资融券',
            hint: marginTradingMetricConfig[activeMarginTradingMetric.value].label,
            rows: [
              { label: '融资余额', value: formatCnyYi(indicator.marginTrading.financing) },
              { label: '融券余额', value: formatCnyYi(indicator.marginTrading.securitiesLending) },
              { label: '两融余额', value: formatCnyYi(indicator.marginTrading.total) },
              { label: '融资净买入', value: formatCnyYi(indicator.marginTrading.netBuy) },
              { label: '杠杆率', value: formatPercent(indicator.marginTrading.leverage) },
            ],
          },
        ]
      : []),
    ...(props.supportsAuxiliaryPanels
      ? [
          {
            key: 'cffex-net-short-delta',
            title: '净空单增量',
            hint: `${activeCffexNetShortDeltaWindow.value}D`,
            rows: buildCffexNetShortDeltaSummaryRows(
              cffexNetShortDeltaPointByDate.value.get(indicator.tradeDate),
              activeCffexNetShortDeltaWindow.value,
              indicator.emotion,
            ),
          },
        ]
      : []),
    ...(props.supportsAuxiliaryPanels
      ? [
          {
            key: 'basis-delta',
            title: '期现差变化',
            hint: `${activeBasisDeltaWindow.value}D`,
            rows: buildBasisDeltaSummaryRows(
              basisDeltaPointByDate.value.get(indicator.tradeDate),
              activeBasisDeltaWindow.value,
            ),
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
              ...basisContractRollRows,
              ...basisAdjustmentRows,
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
    ...(props.supportsCnOptionPutCallPanel
      ? [
          {
            key: 'cn-option-put-call',
            title: 'Put/Call',
            hint: `${activeCnOptionPriceSeries.value?.exchange_label ?? '-'} ${activeCnOptionPriceSeries.value?.product_code ?? ''} · ${cnOptionPutCallMetricConfig[activeCnOptionPutCallKey.value].label}`,
            rows: buildCnOptionPutCallSummaryRows(cnOptionPutCallPointByDate.value.get(indicator.tradeDate)),
          },
          {
            key: 'cn-option-flow-put-call',
            title: '成交 Put/Call',
            hint: `${activeCnOptionFlowSeries.value?.exchange_label ?? '-'} ${activeCnOptionFlowSeries.value?.product_code ?? ''} · ${cnOptionFlowPutCallMetricConfig[activeCnOptionFlowPutCallKey.value].label}`,
            rows: buildCnOptionFlowPutCallSummaryRows(cnOptionFlowPutCallPointByDate.value.get(indicator.tradeDate)),
          },
          ...(availableCnOptionVixSeries.value.length
            ? [
                {
                  key: 'cn-option-vix',
                  title: '自算VIX',
                  hint: `${activeCnOptionVixSeries.value?.exchange_label ?? '-'} ${activeCnOptionVixSeries.value?.product_code ?? ''}`,
                  rows: buildCnOptionVixSummaryRows(cnOptionVixPointByDate.value.get(indicator.tradeDate)),
                },
              ]
            : []),
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
        { label: '蓝色命中', value: formatRuleGroupList(activeHighlightBand.value?.blueHitGroups) },
        { label: '红色命中', value: formatRuleGroupList(activeHighlightBand.value?.redHitGroups) },
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

function addReferenceLineSeries(chart: IChartApi, color: string) {
  return chart.addSeries(LineSeries, {
    color,
    lineWidth: 1,
    lastValueVisible: false,
    priceLineVisible: false,
    crosshairMarkerVisible: false,
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
  if (direction === 'out' && clampedSpan >= maxSpan - 0.5) {
    const fullLoadedRange: LogicalRange = {
      from: -10 as Logical,
      to: (mainCandles.value.length + 10) as Logical,
    }
    mainChart.timeScale().setVisibleLogicalRange(fullLoadedRange)
    maybeRequestMoreHistory({ from: 0 as Logical, to: 0 as Logical })
    return
  }
  mainChart.timeScale().setVisibleLogicalRange({
    from: center - clampedSpan / 2,
    to: center + clampedSpan / 2,
  })
  if (direction === 'out') {
    maybeRequestMoreHistory({ from: 0 as Logical, to: 0 as Logical })
  }
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

  if (isSubPanelVisible('cnPutCall')) {
    if (!cnPutCallSeries || !cnPutCallReferenceSeries) return
    const metricConfig = cnOptionPutCallMetricConfig[activeCnOptionPutCallKey.value]
    cnPutCallSeries.applyOptions({ color: metricConfig.color })
    cnPutCallSeries.setData(
      cnOptionPutCallSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    cnPutCallReferenceSeries.setData(mainCandles.value.map((item) => ({ time: item.time, value: 1 })))
    panelValueMaps.set(
      'cnPutCall',
      new Map(cnOptionPutCallSeriesData.value.filter((item) => item.value !== null).map((item) => [item.rawDate, item.value as number])),
    )
  } else {
    panelValueMaps.delete('cnPutCall')
  }

  if (isSubPanelVisible('cnFlowPutCall')) {
    if (!cnFlowPutCallSeries || !cnFlowPutCallReferenceSeries) return
    const metricConfig = cnOptionFlowPutCallMetricConfig[activeCnOptionFlowPutCallKey.value]
    cnFlowPutCallSeries.applyOptions({ color: metricConfig.color })
    cnFlowPutCallSeries.setData(
      cnOptionFlowPutCallSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    cnFlowPutCallReferenceSeries.setData(mainCandles.value.map((item) => ({ time: item.time, value: 1 })))
    panelValueMaps.set(
      'cnFlowPutCall',
      new Map(
        cnOptionFlowPutCallSeriesData.value
          .filter((item) => item.value !== null)
          .map((item) => [item.rawDate, item.value as number]),
      ),
    )
  } else {
    panelValueMaps.delete('cnFlowPutCall')
  }

  if (isSubPanelVisible('cnOptionVix')) {
    if (!cnOptionVixSeries) return
    cnOptionVixSeries.setData(toVixCandleData(cnOptionVixSeriesData.value))
    panelValueMaps.set(
      'cnOptionVix',
      new Map(
        cnOptionVixSeriesData.value
          .filter((item) => item.close !== null)
          .map((item) => [item.trade_date, item.close as number]),
      ),
    )
  } else {
    panelValueMaps.delete('cnOptionVix')
  }

  if (isSubPanelVisible('cffexNetShortDelta')) {
    if (!cffexNetShortDeltaSeries || !cffexNetShortDeltaReferenceSeries) return
    const sourceConfig = cffexNetShortDeltaSourceConfig[activeCffexNetShortDeltaSource.value]
    cffexNetShortDeltaSeries.applyOptions({ color: sourceConfig.color })
    cffexNetShortDeltaSeries.setData(
      cffexNetShortDeltaSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    cffexNetShortDeltaReferenceSeries.setData(mainCandles.value.map((item) => ({ time: item.time, value: 0 })))
    panelValueMaps.set(
      'cffexNetShortDelta',
      new Map(
        cffexNetShortDeltaSeriesData.value
          .filter((item) => item.value !== null)
          .map((item) => [item.rawDate, item.value as number]),
      ),
    )
  } else {
    panelValueMaps.delete('cffexNetShortDelta')
  }

  if (isSubPanelVisible('basisDelta')) {
    if (!basisDeltaSeries || !basisDeltaReferenceSeries) return
    const metricConfig = basisDeltaMetricConfig[activeBasisDeltaMetric.value]
    basisDeltaSeries.applyOptions({ color: metricConfig.color })
    basisDeltaSeries.setData(
      basisDeltaSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    basisDeltaReferenceSeries.setData(mainCandles.value.map((item) => ({ time: item.time, value: 0 })))
    panelValueMaps.set(
      'basisDelta',
      new Map(
        basisDeltaSeriesData.value
          .filter((item) => item.value !== null)
          .map((item) => [item.rawDate, item.value as number]),
      ),
    )
  } else {
    panelValueMaps.delete('basisDelta')
  }

  if (isSubPanelVisible('fundPurchaseLimit')) {
    if (!fundPurchaseLimitSeries) return
    const metricConfig = fundPurchaseLimitMetricConfig[activeFundPurchaseLimitMetric.value]
    fundPurchaseLimitSeries.applyOptions({ color: metricConfig.color })
    fundPurchaseLimitSeries.setData(
      fundPurchaseLimitSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    panelValueMaps.set(
      'fundPurchaseLimit',
      new Map(
        fundPurchaseLimitSeriesData.value
          .filter((item) => item.value !== null)
          .map((item) => [item.rawDate, item.value as number]),
      ),
    )
  } else {
    panelValueMaps.delete('fundPurchaseLimit')
  }

  if (isSubPanelVisible('marginTrading')) {
    if (!marginTradingSeries) return
    const metricConfig = marginTradingMetricConfig[activeMarginTradingMetric.value]
    marginTradingSeries.applyOptions({
      color: metricConfig.color,
      priceFormat: marginTradingPriceFormat(activeMarginTradingMetric.value),
    })
    marginTradingSeries.setData(
      marginTradingSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    panelValueMaps.set(
      'marginTrading',
      new Map(
        marginTradingSeriesData.value
          .filter((item) => item.value !== null)
          .map((item) => [item.rawDate, item.value as number]),
      ),
    )
  } else {
    panelValueMaps.delete('marginTrading')
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
    if (!usPutCallSeries || !usPutCallReferenceSeries) return
    const metricConfig = usPutCallMetricConfig[activeUsPutCallKey.value]
    usPutCallSeries.applyOptions({ color: metricConfig.color })
    usPutCallSeries.setData(
      usPutCallSeriesData.value.map((item) =>
        item.value === null
          ? ({ time: item.time } as WhitespaceData<Time>)
          : ({ time: item.time, value: item.value }),
      ),
    )
    usPutCallReferenceSeries.setData(mainCandles.value.map((item) => ({ time: item.time, value: 1 })))
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
    if (isSubPanelVisible('cnPutCall')) {
      charts.cnPutCall = createBaseChart(cnPutCallContainerRef.value!, true)
    }
    if (isSubPanelVisible('cnFlowPutCall')) {
      charts.cnFlowPutCall = createBaseChart(cnFlowPutCallContainerRef.value!, true)
    }
    if (isSubPanelVisible('cnOptionVix')) {
      charts.cnOptionVix = createBaseChart(cnOptionVixContainerRef.value!, true)
    }
    if (isSubPanelVisible('cffexNetShortDelta')) {
      charts.cffexNetShortDelta = createBaseChart(cffexNetShortDeltaContainerRef.value!, true)
    }
    if (isSubPanelVisible('basisDelta')) {
      charts.basisDelta = createBaseChart(basisDeltaContainerRef.value!, true)
    }
    if (isSubPanelVisible('fundPurchaseLimit')) {
      charts.fundPurchaseLimit = createBaseChart(fundPurchaseLimitContainerRef.value!, true)
    }
    if (isSubPanelVisible('marginTrading')) {
      charts.marginTrading = createBaseChart(marginTradingContainerRef.value!, true)
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
    cnPutCallSeries = charts.cnPutCall
      ? addLineSeries(charts.cnPutCall, cnOptionPutCallMetricConfig[activeCnOptionPutCallKey.value].color, 2)
      : null
    cnPutCallReferenceSeries = charts.cnPutCall ? addReferenceLineSeries(charts.cnPutCall, '#dc2626') : null
    cnFlowPutCallSeries = charts.cnFlowPutCall
      ? addLineSeries(
          charts.cnFlowPutCall,
          cnOptionFlowPutCallMetricConfig[activeCnOptionFlowPutCallKey.value].color,
          2,
        )
      : null
    cnFlowPutCallReferenceSeries = charts.cnFlowPutCall
      ? addReferenceLineSeries(charts.cnFlowPutCall, '#dc2626')
      : null
    cnOptionVixSeries = charts.cnOptionVix ? addVixCandles(charts.cnOptionVix) : null
    cffexNetShortDeltaSeries = charts.cffexNetShortDelta
      ? addLineSeries(
          charts.cffexNetShortDelta,
          cffexNetShortDeltaSourceConfig[activeCffexNetShortDeltaSource.value].color,
          2,
        )
      : null
    cffexNetShortDeltaReferenceSeries = charts.cffexNetShortDelta
      ? addReferenceLineSeries(charts.cffexNetShortDelta, '#dc2626')
      : null
    basisDeltaSeries = charts.basisDelta
      ? addLineSeries(charts.basisDelta, basisDeltaMetricConfig[activeBasisDeltaMetric.value].color, 2)
      : null
    basisDeltaReferenceSeries = charts.basisDelta ? addReferenceLineSeries(charts.basisDelta, '#dc2626') : null
    fundPurchaseLimitSeries = charts.fundPurchaseLimit
      ? addLineSeries(
          charts.fundPurchaseLimit,
          fundPurchaseLimitMetricConfig[activeFundPurchaseLimitMetric.value].color,
          2,
        )
      : null
    marginTradingSeries = charts.marginTrading
      ? addLineSeries(
          charts.marginTrading,
          marginTradingMetricConfig[activeMarginTradingMetric.value].color,
          2,
        )
      : null
    marginTradingSeries?.applyOptions({
      priceFormat: marginTradingPriceFormat(activeMarginTradingMetric.value),
    })
    usVixSeries = charts.usVix ? addVixCandles(charts.usVix) : null
    usFearGreedSeries = charts.usFearGreed ? addLineSeries(charts.usFearGreed, quantDataset.value.usFearGreed?.color ?? '#dc2626', 2) : null
    usHedgeSeries = charts.usHedge ? addLineSeries(charts.usHedge, quantDataset.value.usHedgeProxy?.color ?? '#0f766e', 2) : null
    usPutCallSeries = charts.usPutCall ? addLineSeries(charts.usPutCall, usPutCallMetricConfig[activeUsPutCallKey.value].color, 2) : null
    usPutCallReferenceSeries = charts.usPutCall ? addReferenceLineSeries(charts.usPutCall, '#dc2626') : null
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
    if (cnPutCallSeries) primarySeriesMap.set('cnPutCall', cnPutCallSeries)
    if (cnFlowPutCallSeries) primarySeriesMap.set('cnFlowPutCall', cnFlowPutCallSeries)
    if (cnOptionVixSeries) primarySeriesMap.set('cnOptionVix', cnOptionVixSeries)
    if (cffexNetShortDeltaSeries) primarySeriesMap.set('cffexNetShortDelta', cffexNetShortDeltaSeries)
    if (basisDeltaSeries) primarySeriesMap.set('basisDelta', basisDeltaSeries)
    if (fundPurchaseLimitSeries) primarySeriesMap.set('fundPurchaseLimit', fundPurchaseLimitSeries)
    if (marginTradingSeries) primarySeriesMap.set('marginTrading', marginTradingSeries)
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
    if (props.supportsCnOptionPutCallPanel) {
      attachHighlightPrimitive(cnPutCallSeries)
      attachHighlightPrimitive(cnPutCallSeries, () => cnOptionPutCallSpecialHighlights.value)
      attachHighlightPrimitive(cnFlowPutCallSeries)
      attachHighlightPrimitive(cnOptionVixSeries)
    }
    if (props.supportsAuxiliaryPanels) {
      attachHighlightPrimitive(cffexNetShortDeltaSeries)
    }
    if (props.supportsFundPurchaseLimitPanel) {
      attachHighlightPrimitive(fundPurchaseLimitSeries)
    }
    if (props.supportsMarginTradingPanel) {
      attachHighlightPrimitive(marginTradingSeries)
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
  cnPutCallSeries = null
  cnPutCallReferenceSeries = null
  cnFlowPutCallSeries = null
  cnFlowPutCallReferenceSeries = null
  cnOptionVixSeries = null
  cffexNetShortDeltaSeries = null
  cffexNetShortDeltaReferenceSeries = null
  basisDeltaSeries = null
  basisDeltaReferenceSeries = null
  fundPurchaseLimitSeries = null
  marginTradingSeries = null
  usVixSeries = null
  usFearGreedSeries = null
  usHedgeSeries = null
  usPutCallSeries = null
  usPutCallReferenceSeries = null
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

watch(cnOptionPutCallSeriesData, () => {
  if (props.supportsCnOptionPutCallPanel) updateAllSeries()
  syncHighlightBindings()
})

watch(cnOptionVixSeriesData, () => {
  if (availableCnOptionVixSeries.value.length) updateAllSeries()
})

watch(cnOptionFlowPutCallSeriesData, () => {
  if (props.supportsCnOptionPutCallPanel) updateAllSeries()
})

watch(cffexNetShortDeltaSeriesData, () => {
  if (props.supportsAuxiliaryPanels) updateAllSeries()
})

watch(basisDeltaSeriesData, () => {
  if (props.supportsAuxiliaryPanels) updateAllSeries()
})

watch(fundPurchaseLimitSeriesData, () => {
  if (props.supportsFundPurchaseLimitPanel) updateAllSeries()
})

watch(marginTradingSeriesData, () => {
  if (props.supportsMarginTradingPanel) updateAllSeries()
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
    `${props.supportsAuxiliaryPanels}:${props.supportsBasisPanel}:${props.showBasisMonthLine}:${props.supportsVixPanel}:${props.supportsCnOptionPutCallPanel}:${props.supportsFundPurchaseLimitPanel}:${props.supportsMarginTradingPanel}:${props.supportsUsVixPanel}:${props.supportsUsFearGreedPanel}:${props.supportsUsHedgeProxyPanel}:${props.supportsUsPutCallPanel}:${props.supportsUsTreasuryYieldPanel}:${props.supportsUsCreditSpreadPanel}:${availableSubPanelOptions.value.map((item) => item.key).join('|')}`,
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
              <strong class="quant-kpi-value" :title="row.title ?? row.value">{{ row.value }}</strong>
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

    <div v-if="isSubPanelVisible('cnPutCall')" class="quant-panel">
      <div class="quant-panel-head">
        <h3>Put/Call</h3>
        <div class="quant-legend quant-legend-groups">
          <div class="quant-legend-group">
            <span class="quant-legend-group-label">来源</span>
            <select class="quant-panel-select" :value="activeCnOptionPriceExchange" @change="selectCnOptionExchange($event, 'price')">
              <option v-for="item in cnOptionExchangeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <select v-if="cnOptionPriceProductOptions.length > 1" class="quant-panel-select" :value="activeCnOptionPriceSourceKey" @change="selectCnOptionProduct($event, 'price')">
              <option v-for="item in cnOptionPriceProductOptions" :key="item.source_key" :value="item.source_key">{{ item.product_code }}</option>
            </select>
          </div>
          <div class="quant-legend-group">
            <button v-for="item in cnOptionPutCallLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectCnOptionPutCallMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button>
          </div>
        </div>
      </div>
      <p v-if="!activeCnOptionPriceSeries?.put_call_points.length" class="muted">当前范围暂无 A 股期权 Put/Call 数据</p>
      <div ref="cnPutCallContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div v-if="isSubPanelVisible('cnFlowPutCall')" class="quant-panel">
      <div class="quant-panel-head">
        <h3>成交 Put/Call</h3>
        <div class="quant-legend quant-legend-groups">
          <div class="quant-legend-group">
            <span class="quant-legend-group-label">来源</span>
            <select class="quant-panel-select" :value="activeCnOptionFlowExchange" @change="selectCnOptionExchange($event, 'flow')">
              <option v-for="item in cnOptionExchangeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <select v-if="cnOptionFlowProductOptions.length > 1" class="quant-panel-select" :value="activeCnOptionFlowSourceKey" @change="selectCnOptionProduct($event, 'flow')">
              <option v-for="item in cnOptionFlowProductOptions" :key="item.source_key" :value="item.source_key">{{ item.product_code }}</option>
            </select>
          </div>
          <div class="quant-legend-group">
            <button v-for="item in cnOptionFlowPutCallLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectCnOptionFlowPutCallMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button>
          </div>
        </div>
      </div>
      <p v-if="!activeCnOptionFlowSeries?.flow_points.length" class="muted">当前范围暂无 A 股成交 Put/Call 数据</p>
      <div ref="cnFlowPutCallContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div v-if="isSubPanelVisible('cnOptionVix')" class="quant-panel">
      <div class="quant-panel-head">
        <h3>自算 VIX</h3>
        <div class="quant-legend quant-legend-groups">
          <div class="quant-legend-group">
            <span class="quant-legend-group-label">来源</span>
            <select class="quant-panel-select" :value="activeCnOptionVixExchange" @change="selectCnOptionExchange($event, 'vix')">
              <option v-for="item in cnOptionVixExchangeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
            <select v-if="cnOptionVixProductOptions.length > 1" class="quant-panel-select" :value="activeCnOptionVixSourceKey" @change="selectCnOptionProduct($event, 'vix')">
              <option v-for="item in cnOptionVixProductOptions" :key="item.source_key" :value="item.source_key">{{ item.product_code }}</option>
            </select>
          </div>
          <div class="quant-legend-group">
            <span class="quant-legend-item"><i style="background:#ef4444"></i>收高于开</span>
            <span class="quant-legend-item"><i style="background:#10b981"></i>收低于开</span>
          </div>
        </div>
      </div>
      <p v-if="!activeCnOptionVixSeries?.vix_points.length" class="muted">当前范围暂无自算 VIX 数据</p>
      <div ref="cnOptionVixContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div v-if="isSubPanelVisible('cffexNetShortDelta')" class="quant-panel"><div class="quant-panel-head"><h3>股指期货净空单增量</h3><div class="quant-legend quant-legend-groups"><div class="quant-legend-group"><span class="quant-legend-group-label">口径</span><button v-for="item in cffexNetShortDeltaSourceLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectCffexNetShortDeltaSource(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button></div><div class="quant-legend-group"><span class="quant-legend-group-label">窗口</span><button v-for="item in cffexNetShortDeltaWindowLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectCffexNetShortDeltaWindow(item.key)">{{ item.label }}</button></div></div></div><p v-if="!cffexNetShortDeltaPoints.length" class="muted">当前范围暂无中金所净空单增量数据</p><div ref="cffexNetShortDeltaContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('basisDelta')" class="quant-panel"><div class="quant-panel-head"><h3>期现差变化</h3><div class="quant-legend quant-legend-groups"><div class="quant-legend-group"><span class="quant-legend-group-label">口径</span><button v-for="item in basisDeltaMetricLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectBasisDeltaMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button></div><div class="quant-legend-group"><span class="quant-legend-group-label">窗口</span><button v-for="item in basisDeltaWindowLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectBasisDeltaWindow(item.key)">{{ item.label }}</button></div></div></div><p v-if="!basisDeltaPoints.length" class="muted">当前范围暂无期现差变化数据</p><div ref="basisDeltaContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div></div>

    <div v-if="isSubPanelVisible('fundPurchaseLimit')" class="quant-panel">
      <div class="quant-panel-head">
        <h3>A股公募基金大额限购</h3>
        <div class="quant-legend">
          <button v-for="item in fundPurchaseLimitLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectFundPurchaseLimitMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button>
        </div>
      </div>
      <p v-if="!fundPurchaseLimitPoints.length" class="muted">当前范围暂无公募基金大额限购数据</p>
      <div ref="fundPurchaseLimitContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div v-if="isSubPanelVisible('marginTrading')" class="quant-panel">
      <div class="quant-panel-head">
        <h3>{{ marginTradingPanelTitle }}</h3>
        <div class="quant-legend">
          <button v-for="item in marginTradingLegend" :key="item.key" type="button" class="quant-legend-item quant-legend-button" :class="{ 'is-muted': !item.active }" @click="selectMarginTradingMetric(item.key)"><i :style="{ background: item.active ? item.color : '#cbd5e1' }"></i>{{ item.label }}</button>
        </div>
      </div>
      <p v-if="!marginTradingPoints.length" class="muted">当前范围暂无融资融券统计数据</p>
      <div ref="marginTradingContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

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

.quant-legend-groups {
  gap: 14px;
}

.quant-legend-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.quant-legend-group-label {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.quant-panel-select {
  min-width: 78px;
  height: 30px;
  padding: 0 26px 0 8px;
  border: 1px solid rgba(100, 116, 139, 0.28);
  border-radius: 6px;
  background: #fff;
  color: #334155;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
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
