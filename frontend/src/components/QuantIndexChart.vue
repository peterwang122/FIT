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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type {
  QuantHighlightBand,
  QuantHistogramPoint,
  QuantIndicatorParams,
  QuantLinePoint,
} from '../types/quant'
import type { FuturesBasisPoint, IndexBreadthPoint, IndexEmotionPoint, KlineCandle, MarketOption } from '../types/stock'
import { DateHighlightPrimitive } from '../utils/dateHighlightPrimitive'
import { buildQuantFilterDataset } from '../utils/quantIndicators'

type PanelKey = 'main' | 'macd' | 'kdj' | 'wr' | 'emotion' | 'basis' | 'breadth'
type MainOverlayMode = 'ma' | 'boll'
type AnySeries = ISeriesApi<SeriesType, Time>
type LineSeriesApi = ISeriesApi<'Line', Time>
type HistogramSeriesApi = ISeriesApi<'Histogram', Time>
type CandleSeriesApi = ISeriesApi<'Candlestick', Time>
type PrimitiveBinding = {
  series: AnySeries
  primitive: DateHighlightPrimitive
}
type SummaryRow = { label: string; value: string; placeholder?: boolean }
type SummaryCard = { key: string; title: string; hint?: string; rows: SummaryRow[] }

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
    highlightBands?: QuantHighlightBand[]
    marketOptions?: MarketOption[]
    symbolName: string
    symbolCode: string
    params: QuantIndicatorParams
    loading?: boolean
    defaultVisibleDays?: number
    zoomStep?: number
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
    highlightBands: () => [],
    loading: false,
    defaultVisibleDays: 90,
    zoomStep: 0.18,
  },
)

const emit = defineEmits<{
  selectIndex: [code: string]
  openSettings: []
}>()

const mainContainerRef = ref<HTMLDivElement | null>(null)
const macdContainerRef = ref<HTMLDivElement | null>(null)
const kdjContainerRef = ref<HTMLDivElement | null>(null)
const wrContainerRef = ref<HTMLDivElement | null>(null)
const emotionContainerRef = ref<HTMLDivElement | null>(null)
const basisContainerRef = ref<HTMLDivElement | null>(null)
const breadthContainerRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')
const overlayMode = ref<MainOverlayMode>('ma')
const hoveredTradeDate = ref<string | null>(null)

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
let emotionSeries: LineSeriesApi | null = null
let basisMainSeries: LineSeriesApi | null = null
let basisMonthSeries: LineSeriesApi | null = null
let breadthSeries: LineSeriesApi | null = null
let breadthCountSeries: LineSeriesApi | null = null
let highlightBindings: PrimitiveBinding[] = []
let isSyncingRange = false
let isSyncingCrosshair = false
let shouldResetVisibleRange = true
let unsubs: Array<() => void> = []

function formatDateText(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function parseDateText(value: string): number {
  return new Date(`${value}T00:00:00`).getTime()
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

const quantDataset = computed(() =>
  buildQuantFilterDataset(
    sortedCandles.value,
    props.params,
    props.symbolName,
    props.emotionPoints,
    props.futuresBasisPoints,
    props.breadthPoints,
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
  { label: 'MACD柱', color: '#94a3b8' },
])

const kdjLegend = computed(() => [
  { label: indicatorPayload.value.kdj.k.label, color: indicatorPayload.value.kdj.k.color },
  { label: indicatorPayload.value.kdj.d.label, color: indicatorPayload.value.kdj.d.color },
  { label: indicatorPayload.value.kdj.j.label, color: indicatorPayload.value.kdj.j.color },
])

const wrLegend = computed(() => [{ label: indicatorPayload.value.wr.label, color: indicatorPayload.value.wr.color }])

const emotionLegend = computed(() => [
  {
    label: quantDataset.value.emotion?.label ?? '情绪指标',
    color: quantDataset.value.emotion?.color ?? '#0f4c75',
  },
])

const basisLegend = computed(() => [
  { label: quantDataset.value.basis?.main.label ?? '主连期现差', color: quantDataset.value.basis?.main.color ?? '#dc2626' },
  { label: quantDataset.value.basis?.month.label ?? '月连期现差', color: quantDataset.value.basis?.month.color ?? '#2563eb' },
])

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

const activeTradeDate = computed(() => hoveredTradeDate.value ?? latestSnapshot.value?.trade_date ?? '')

function handleIndexSelect(event: Event) {
  const target = event.target as HTMLSelectElement | null
  const nextCode = target?.value?.trim()
  if (!nextCode) {
    return
  }
  emit('selectIndex', nextCode)
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

function toHistogramData(points: QuantHistogramPoint[]) {
  return points.map((item) =>
    item.value === null
      ? ({ time: item.time as Time } as WhitespaceData<Time>)
      : ({ time: item.time as Time, value: item.value, color: item.color }),
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
    wr: buildValueMap(payload.wr.data),
    emotion: buildValueMap(quantDataset.value.emotion?.data ?? []),
    basis: {
      main: buildValueMap(quantDataset.value.basis?.main.data ?? []),
      month: buildValueMap(quantDataset.value.basis?.month.data ?? []),
    },
    breadth: buildValueMap(quantDataset.value.breadth?.data ?? []),
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
    wr: maps.wr.get(tradeDate),
    emotion: maps.emotion.get(tradeDate),
    basis: {
      main: maps.basis.main.get(tradeDate),
      month: maps.basis.month.get(tradeDate),
    },
    breadth: {
      pct: maps.breadth.get(tradeDate),
      upCount: breadthPointByDate.value.get(tradeDate)?.up_count ?? 0,
      totalCount: breadthPointByDate.value.get(tradeDate)?.total_count ?? 0,
    },
  }
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
      key: 'kdj-wr',
      title: 'KDJ / WR',
      rows: [
        { label: 'K', value: formatMetric(indicator.kdj.k) },
        { label: 'D', value: formatMetric(indicator.kdj.d) },
        { label: 'J', value: formatMetric(indicator.kdj.j) },
        { label: 'WR', value: formatMetric(indicator.wr) },
      ],
    },
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

function syncVisibleRange(sourceKey: PanelKey, range: LogicalRange | null) {
  if (!range || isSyncingRange) {
    return
  }

  isSyncingRange = true
  try {
    ;(['main', 'macd', 'kdj', 'wr', 'emotion', 'basis', 'breadth'] as PanelKey[]).forEach((panelKey) => {
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
    ;(['main', 'macd', 'kdj', 'wr', 'emotion', 'basis', 'breadth'] as PanelKey[]).forEach((panelKey) => {
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

function attachSync(panelKey: PanelKey, chart: IChartApi) {
  const visibleRangeHandler = (range: LogicalRange | null) => syncVisibleRange(panelKey, range)
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

function attachHighlightPrimitive(series: AnySeries | null) {
  if (!series) {
    return
  }

  const primitive = new DateHighlightPrimitive(props.highlightBands)
  series.attachPrimitive(primitive)
  highlightBindings.push({ series, primitive })
}

function syncHighlightBindings() {
  highlightBindings.forEach(({ primitive }) => primitive.setHighlights(props.highlightBands))
}

function updateAllSeries() {
  if (
    !mainCandleSeries ||
    !macdDifSeries ||
    !macdDeaSeries ||
    !macdHistogramSeries ||
    !wrSeries ||
    !emotionSeries ||
    !basisMainSeries ||
    !basisMonthSeries ||
    !breadthSeries ||
    !breadthCountSeries ||
    !kdjSeriesRefs.length
  ) {
    return
  }

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

  macdDifSeries.setData(toLineData(payload.macd.dif.data))
  macdDeaSeries.setData(toLineData(payload.macd.dea.data))
  macdHistogramSeries.setData(toHistogramData(payload.macd.histogram))

  kdjSeriesRefs[0]?.setData(toLineData(payload.kdj.k.data))
  kdjSeriesRefs[1]?.setData(toLineData(payload.kdj.d.data))
  kdjSeriesRefs[2]?.setData(toLineData(payload.kdj.j.data))
  wrSeries.setData(toLineData(payload.wr.data))
  emotionSeries.setData(toLineData(quantDataset.value.emotion?.data ?? []))
  basisMainSeries.setData(toLineData(quantDataset.value.basis?.main.data ?? []))
  basisMonthSeries.setData(toLineData(quantDataset.value.basis?.month.data ?? []))
  breadthSeries.setData(toLineData(quantDataset.value.breadth?.data ?? []))
  breadthCountSeries.setData(
    breadthCountSeriesData.value.map((item) => ({
      time: item.time,
      value: item.value,
    })),
  )

  panelValueMaps.set('main', new Map(sortedCandles.value.map((item) => [item.trade_date, item.close])))
  panelValueMaps.set('macd', buildValueMap(payload.macd.dif.data))
  panelValueMaps.set('kdj', buildValueMap(payload.kdj.k.data))
  panelValueMaps.set('wr', buildValueMap(payload.wr.data))
  panelValueMaps.set('emotion', new Map(emotionSeriesData.value.map((item) => [item.rawDate, item.value])))
  panelValueMaps.set('basis', buildValueMap(quantDataset.value.basis?.main.data ?? []))
  panelValueMaps.set('breadth', new Map(breadthSeriesData.value.map((item) => [item.rawDate, item.value])))
}

function renderCharts() {
  if (
    !mainContainerRef.value ||
    !macdContainerRef.value ||
    !kdjContainerRef.value ||
    !wrContainerRef.value ||
    !emotionContainerRef.value ||
    !basisContainerRef.value ||
    !breadthContainerRef.value
  ) {
    return
  }

  try {
    renderError.value = ''

    charts.main = createBaseChart(mainContainerRef.value, false)
    charts.macd = createBaseChart(macdContainerRef.value, false)
    charts.kdj = createBaseChart(kdjContainerRef.value, false)
    charts.wr = createBaseChart(wrContainerRef.value, false)
    charts.emotion = createBaseChart(emotionContainerRef.value, false)
    charts.basis = createBaseChart(basisContainerRef.value, false)
    charts.breadth = createBaseChart(breadthContainerRef.value, true)
    charts.breadth.priceScale('left').applyOptions({
      visible: true,
      borderColor: '#e2e8f0',
      autoScale: true,
    })

    mainCandleSeries = addCandles(charts.main)
    mainMaSeries = indicatorPayload.value.ma.map((item) => addLineSeries(charts.main!, item.color, 2))
    bollSeriesRefs = [
      addLineSeries(charts.main, indicatorPayload.value.boll.upper.color, 1),
      addLineSeries(charts.main, indicatorPayload.value.boll.middle.color, 1),
      addLineSeries(charts.main, indicatorPayload.value.boll.lower.color, 1),
    ]

    macdDifSeries = addLineSeries(charts.macd, indicatorPayload.value.macd.dif.color, 2)
    macdDeaSeries = addLineSeries(charts.macd, indicatorPayload.value.macd.dea.color, 2)
    macdHistogramSeries = addHistogramSeries(charts.macd)

    kdjSeriesRefs = [
      addLineSeries(charts.kdj, indicatorPayload.value.kdj.k.color, 2),
      addLineSeries(charts.kdj, indicatorPayload.value.kdj.d.color, 2),
      addLineSeries(charts.kdj, indicatorPayload.value.kdj.j.color, 2),
    ]

    wrSeries = addLineSeries(charts.wr, indicatorPayload.value.wr.color, 2)
    emotionSeries = addLineSeries(charts.emotion, quantDataset.value.emotion?.color ?? '#0f4c75', 2)
    basisMainSeries = addLineSeries(charts.basis, quantDataset.value.basis?.main.color ?? '#dc2626', 2)
    basisMonthSeries = addLineSeries(charts.basis, quantDataset.value.basis?.month.color ?? '#2563eb', 2)
    breadthSeries = addLineSeries(charts.breadth, quantDataset.value.breadth?.color ?? '#0ea5e9', 2)
    breadthCountSeries = addLineSeries(charts.breadth, '#f97316', 2, 'left')

    primarySeriesMap.set('main', mainCandleSeries)
    primarySeriesMap.set('macd', macdDifSeries)
    primarySeriesMap.set('kdj', kdjSeriesRefs[0])
    primarySeriesMap.set('wr', wrSeries)
    primarySeriesMap.set('emotion', emotionSeries)
    primarySeriesMap.set('basis', basisMainSeries)
    primarySeriesMap.set('breadth', breadthSeries)

    ;(['main', 'macd', 'kdj', 'wr', 'emotion', 'basis', 'breadth'] as PanelKey[]).forEach((panelKey) => {
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
    attachHighlightPrimitive(emotionSeries)
    attachHighlightPrimitive(basisMainSeries)
    attachHighlightPrimitive(breadthSeries)

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

watch(mainCandles, () => {
  updateAllSeries()
  if (shouldResetVisibleRange && mainCandles.value.length) {
    applyDefaultVisibleRange()
    shouldResetVisibleRange = false
  }
})

watch(emotionSeriesData, () => {
  updateAllSeries()
})

watch(breadthSeriesData, () => {
  updateAllSeries()
})

watch(breadthCountSeriesData, () => {
  updateAllSeries()
})

watch(
  () => props.symbolCode,
  () => {
    hoveredTradeDate.value = null
    shouldResetVisibleRange = true
  },
)

watch(
  () => props.futuresBasisPoints,
  () => {
    updateAllSeries()
  },
  { deep: true },
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
  unsubs.forEach((dispose) => dispose())
  unsubs = []

  cleanupHighlightBindings()

  ;(['main', 'macd', 'kdj', 'wr', 'emotion', 'basis', 'breadth'] as PanelKey[]).forEach((panelKey) => {
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
  emotionSeries = null
  basisMainSeries = null
  basisMonthSeries = null
  breadthSeries = null
  breadthCountSeries = null
  hoveredTradeDate.value = null
  shouldResetVisibleRange = true
})
</script>

<template>
  <section class="quant-chart-shell">
    <div class="quant-chart-summary">
      <div class="quant-chart-summary-head">
        <div class="quant-chart-symbol-row">
          <select
            class="input quant-chart-symbol-select"
            :value="symbolCode"
            :disabled="loading || !marketOptions?.length"
            @change="handleIndexSelect"
          >
            <option v-for="item in marketOptions" :key="item.code" :value="item.code">
              {{ item.name }}
            </option>
          </select>
          <span class="quant-chart-symbol-code">（{{ symbolCode }}）</span>
        </div>
        <div class="quant-chart-head-actions">
          <button
            type="button"
            class="quant-chart-tool-btn"
            :disabled="loading || !sortedCandles.length"
            aria-label="Zoom in"
            @click="zoomChart('in')"
          >
            +
          </button>
          <button
            type="button"
            class="quant-chart-tool-btn"
            :disabled="loading || !sortedCandles.length"
            aria-label="Zoom out"
            @click="zoomChart('out')"
          >
            -
          </button>
          <button
            type="button"
            class="quant-chart-tool-btn quant-chart-tool-btn-gear"
            :disabled="loading"
            aria-label="Open parameter modal"
            @click="emit('openSettings')"
          >
            <span aria-hidden="true">&#9881;</span>
          </button>
        </div>
      </div>

      <div class="quant-chart-switches">
        <button
          type="button"
          class="quant-switch"
          :class="{ active: overlayMode === 'ma' }"
          @click="overlayMode = 'ma'"
        >
          均线
        </button>
        <button
          type="button"
          class="quant-switch"
          :class="{ active: overlayMode === 'boll' }"
          @click="overlayMode = 'boll'"
        >
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
            <div
              v-for="(row, index) in card.rows"
              :key="`${card.key}-${index}`"
              class="quant-kpi-row"
              :class="{ 'quant-kpi-placeholder': row.placeholder }"
            >
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

    <div class="quant-panel">
      <div class="quant-panel-head">
        <h3>主图</h3>
        <div class="quant-legend">
          <span v-for="item in mainLegend" :key="item.label" class="quant-legend-item">
            <i :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
      </div>
      <div ref="mainContainerRef" class="quant-panel-chart quant-panel-chart-main"></div>
    </div>

    <div class="quant-panel">
      <div class="quant-panel-head">
        <h3>MACD</h3>
        <div class="quant-legend">
          <span v-for="item in macdLegend" :key="item.label" class="quant-legend-item">
            <i :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
      </div>
      <div ref="macdContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel">
      <div class="quant-panel-head">
        <h3>KDJ</h3>
        <div class="quant-legend">
          <span v-for="item in kdjLegend" :key="item.label" class="quant-legend-item">
            <i :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
      </div>
      <div ref="kdjContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel">
      <div class="quant-panel-head">
        <h3>WR</h3>
        <div class="quant-legend">
          <span v-for="item in wrLegend" :key="item.label" class="quant-legend-item">
            <i :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
      </div>
      <div ref="wrContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel">
      <div class="quant-panel-head">
        <h3>情绪指标</h3>
        <div class="quant-legend">
          <span v-for="item in emotionLegend" :key="item.label" class="quant-legend-item">
            <i :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
      </div>
      <p v-if="emotionLoading" class="muted">情绪指标加载中...</p>
      <p v-else-if="emotionErrorMessage" class="error">{{ emotionErrorMessage }}</p>
      <div ref="emotionContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel">
      <div class="quant-panel-head">
        <h3>期现差</h3>
        <div class="quant-legend">
          <span v-for="item in basisLegend" :key="item.label" class="quant-legend-item">
            <i :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
      </div>
      <p v-if="futuresBasisLoading" class="muted">期现差指标加载中...</p>
      <p v-else-if="futuresBasisErrorMessage" class="error">{{ futuresBasisErrorMessage }}</p>
      <div ref="basisContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel">
      <div class="quant-panel-head">
        <h3>涨跌家数</h3>
        <div class="quant-legend">
          <span v-for="item in breadthLegend" :key="item.label" class="quant-legend-item">
            <i :style="{ background: item.color }"></i>{{ item.label }}
          </span>
        </div>
      </div>
      <p v-if="breadthLoading" class="muted">涨跌家数加载中...</p>
      <p v-else-if="breadthErrorMessage" class="error">{{ breadthErrorMessage }}</p>
      <div ref="breadthContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>
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

.quant-chart-switches {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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
