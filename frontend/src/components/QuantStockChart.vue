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

import type { QuantHighlightBand, QuantHistogramPoint, QuantIndicatorParams, QuantLinePoint } from '../types/quant'
import type { KlineCandle } from '../types/stock'
import { DateHighlightPrimitive } from '../utils/dateHighlightPrimitive'
import { buildStockQuantFilterDataset } from '../utils/quantIndicators'

type PanelKey = 'main' | 'turnover' | 'macd' | 'kdj' | 'wr' | 'rsi'
type MainOverlayMode = 'ma' | 'boll'
type AnySeries = ISeriesApi<SeriesType, Time>
type LineSeriesApi = ISeriesApi<'Line', Time>
type HistogramSeriesApi = ISeriesApi<'Histogram', Time>
type CandleSeriesApi = ISeriesApi<'Candlestick', Time>
type SummaryRow = { label: string; value: string; placeholder?: boolean }
type SummaryCard = { key: string; title: string; hint?: string; rows: SummaryRow[] }

const props = withDefaults(
  defineProps<{
    candles: KlineCandle[]
    highlightBands?: QuantHighlightBand[]
    symbolName: string
    symbolCode: string
    params: QuantIndicatorParams
    loading?: boolean
    defaultVisibleDays?: number
    zoomStep?: number
  }>(),
  {
    highlightBands: () => [],
    loading: false,
    defaultVisibleDays: 90,
    zoomStep: 0.18,
  },
)

const emit = defineEmits<{
  openSettings: []
}>()

const mainContainerRef = ref<HTMLDivElement | null>(null)
const macdContainerRef = ref<HTMLDivElement | null>(null)
const kdjContainerRef = ref<HTMLDivElement | null>(null)
const wrContainerRef = ref<HTMLDivElement | null>(null)
const turnoverContainerRef = ref<HTMLDivElement | null>(null)
const rsiContainerRef = ref<HTMLDivElement | null>(null)
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
let turnoverSeries: LineSeriesApi | null = null
let rsiSeries: LineSeriesApi | null = null
let highlightBindings: Array<{ series: AnySeries; primitive: DateHighlightPrimitive }> = []
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
      turnover_rate: Number.isFinite(Number(item.turnover_rate)) ? Number(item.turnover_rate) * 100 : 0,
    }))
    .filter((item) => Number.isFinite(item.open) && Number.isFinite(item.high) && Number.isFinite(item.low) && Number.isFinite(item.close))
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)

const latestSnapshot = computed(() => (sortedCandles.value.length ? sortedCandles.value[sortedCandles.value.length - 1] : undefined))
const candleSnapshotMap = computed(() => new Map(sortedCandles.value.map((item) => [item.trade_date, item])))
const activeSnapshot = computed(() => (hoveredTradeDate.value ? candleSnapshotMap.value.get(hoveredTradeDate.value) ?? latestSnapshot.value : latestSnapshot.value))
const mainCandles = computed(() => sortedCandles.value.map((item) => ({ time: item.trade_date as Time, open: item.open, high: item.high, low: item.low, close: item.close })))
const quantDataset = computed(() => buildStockQuantFilterDataset(sortedCandles.value, props.params))
const indicatorPayload = computed(() => quantDataset.value.chart)

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
const turnoverLegend = computed(() => [{ label: '换手率', color: '#ec4899' }])
const rsiLegend = computed(() => [{ label: indicatorPayload.value.rsi.label, color: indicatorPayload.value.rsi.color }])

function formatMetric(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return value.toFixed(4).replace(/\.?0+$/, '')
}

function formatMetricWithSuffix(value: number | null | undefined, suffix: string) {
  const formatted = formatMetric(value)
  return formatted === '-' ? '-' : `${formatted}${suffix}`
}

function buildPlaceholderRow(): SummaryRow {
  return { label: '', value: '-', placeholder: true }
}

function toLineData(points: QuantLinePoint[]) {
  return points.map((item) => (item.value === null ? ({ time: item.time as Time } as WhitespaceData<Time>) : ({ time: item.time as Time, value: item.value })))
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
  points.forEach((item) => {
    if (item.value !== null && Number.isFinite(item.value)) result.set(item.time, item.value)
  })
  return result
}

function buildHistogramValueMap(points: QuantHistogramPoint[]) {
  const result = new Map<string, number>()
  points.forEach((item) => {
    if (item.value !== null && Number.isFinite(item.value)) result.set(item.time, item.value)
  })
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
  }
})

const activeTradeDate = computed(() => hoveredTradeDate.value ?? latestSnapshot.value?.trade_date ?? '')
const activeIndicatorSnapshot = computed(() => {
  if (!activeTradeDate.value) return null
  const tradeDate = activeTradeDate.value
  const maps = indicatorValueMaps.value
  return {
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
    turnover: candleSnapshotMap.value.get(tradeDate)?.turnover_rate,
  }
})

const summaryCards = computed<SummaryCard[]>(() => {
  if (!activeSnapshot.value || !activeIndicatorSnapshot.value) return []

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
      key: 'turnover',
      title: '换手率',
      rows: [{ label: '当日换手率', value: formatMetricWithSuffix(indicator.turnover, '%') }],
    },
    {
      key: 'rsi',
      title: 'RSI',
      rows: [{ label: indicatorPayload.value.rsi.label, value: formatMetric(indicator.rsi) }],
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
    rightPriceScale: { borderColor: '#e2e8f0', autoScale: true },
    timeScale: { borderColor: '#e2e8f0', timeVisible: true, visible: showTimeScale },
    grid: { vertLines: { color: '#f3f4f6' }, horzLines: { color: '#eef2f7' } },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: '#94a3b8', labelBackgroundColor: '#0f4c75' },
      horzLine: { color: '#94a3b8', labelBackgroundColor: '#0f4c75' },
    },
    localization: { locale: 'zh-CN' },
  })
}

function addLineSeries(chart: IChartApi, color: string, lineWidth: LineWidth = 2) {
  return chart.addSeries(LineSeries, { color, lineWidth, lastValueVisible: false, priceLineVisible: false, crosshairMarkerRadius: 3 })
}

function addHistogramSeries(chart: IChartApi) {
  return chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false, base: 0 })
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
  if (!range || isSyncingRange) return
  isSyncingRange = true
  try {
    ;(['main', 'turnover', 'macd', 'kdj', 'wr', 'rsi'] as PanelKey[]).forEach((panelKey) => {
      if (panelKey !== sourceKey) charts[panelKey]?.timeScale().setVisibleLogicalRange(range)
    })
  } finally {
    isSyncingRange = false
  }
}

function syncCrosshair(sourceKey: PanelKey, param: MouseEventParams<Time>) {
  if (isSyncingCrosshair) return
  hoveredTradeDate.value = param.time ? String(param.time) : null
  isSyncingCrosshair = true
  try {
    const time = param.time ? String(param.time) : null
    ;(['main', 'turnover', 'macd', 'kdj', 'wr', 'rsi'] as PanelKey[]).forEach((panelKey) => {
      if (panelKey === sourceKey) return
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
  if (!charts.main) return
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
  charts.main.timeScale().setVisibleRange({ from: formatDateText(startDate) as Time, to: lastTime as Time })
}

function zoomChart(direction: 'in' | 'out') {
  const mainChart = charts.main
  if (!mainChart || !mainCandles.value.length) return

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
  highlightBindings.forEach(({ series, primitive }) => series.detachPrimitive(primitive))
  highlightBindings = []
}

function attachHighlightPrimitive(series: AnySeries | null) {
  if (!series) return
  const primitive = new DateHighlightPrimitive(props.highlightBands)
  series.attachPrimitive(primitive)
  highlightBindings.push({ series, primitive })
}

function syncHighlightBindings() {
  highlightBindings.forEach(({ primitive }) => primitive.setHighlights(props.highlightBands))
}

function updateAllSeries() {
  if (!mainCandleSeries || !macdDifSeries || !macdDeaSeries || !macdHistogramSeries || !wrSeries || !turnoverSeries || !rsiSeries || !kdjSeriesRefs.length) return
  const payload = indicatorPayload.value
  mainCandleSeries.setData(mainCandles.value)
  if (overlayMode.value === 'boll') {
    mainMaSeries.forEach((series) => series.setData([]))
    bollSeriesRefs[0]?.setData(toLineData(payload.boll.upper.data))
    bollSeriesRefs[1]?.setData(toLineData(payload.boll.middle.data))
    bollSeriesRefs[2]?.setData(toLineData(payload.boll.lower.data))
  } else {
    mainMaSeries.forEach((series, index) => series.setData(toLineData(payload.ma[index]?.data ?? [])))
    bollSeriesRefs.forEach((series) => series.setData([]))
  }
  macdDifSeries.setData(toLineData(payload.macd.dif.data))
  macdDeaSeries.setData(toLineData(payload.macd.dea.data))
  macdHistogramSeries.setData(toHistogramData(payload.macd.histogram))
  kdjSeriesRefs[0]?.setData(toLineData(payload.kdj.k.data))
  kdjSeriesRefs[1]?.setData(toLineData(payload.kdj.d.data))
  kdjSeriesRefs[2]?.setData(toLineData(payload.kdj.j.data))
  wrSeries.setData(toLineData(payload.wr.data))
  rsiSeries.setData(toLineData(payload.rsi.data))
  turnoverSeries.setData(
    sortedCandles.value.map((item) => ({
      time: item.trade_date as Time,
      value: item.turnover_rate,
    })),
  )

  panelValueMaps.set('main', new Map(sortedCandles.value.map((item) => [item.trade_date, item.close])))
  panelValueMaps.set('macd', buildValueMap(payload.macd.dif.data))
  panelValueMaps.set('kdj', buildValueMap(payload.kdj.k.data))
  panelValueMaps.set('wr', buildValueMap(payload.wr.data))
  panelValueMaps.set('rsi', buildValueMap(payload.rsi.data))
  panelValueMaps.set('turnover', new Map(sortedCandles.value.map((item) => [item.trade_date, item.turnover_rate])))
}

function renderCharts() {
  if (!mainContainerRef.value || !macdContainerRef.value || !kdjContainerRef.value || !wrContainerRef.value || !turnoverContainerRef.value || !rsiContainerRef.value) return
  try {
    renderError.value = ''
    charts.main = createBaseChart(mainContainerRef.value, false)
    charts.turnover = createBaseChart(turnoverContainerRef.value, true)
    charts.macd = createBaseChart(macdContainerRef.value, false)
    charts.kdj = createBaseChart(kdjContainerRef.value, false)
    charts.wr = createBaseChart(wrContainerRef.value, false)
    charts.rsi = createBaseChart(rsiContainerRef.value, false)

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
    turnoverSeries = addLineSeries(charts.turnover, '#ec4899', 2)
    rsiSeries = addLineSeries(charts.rsi, indicatorPayload.value.rsi.color, 2)

    primarySeriesMap.set('main', mainCandleSeries)
    primarySeriesMap.set('turnover', turnoverSeries)
    primarySeriesMap.set('macd', macdDifSeries)
    primarySeriesMap.set('kdj', kdjSeriesRefs[0])
    primarySeriesMap.set('wr', wrSeries)
    primarySeriesMap.set('rsi', rsiSeries)

    ;(['main', 'turnover', 'macd', 'kdj', 'wr', 'rsi'] as PanelKey[]).forEach((panelKey) => {
      const chart = charts[panelKey]
      if (chart) attachSync(panelKey, chart)
    })

    cleanupHighlightBindings()
    attachHighlightPrimitive(mainCandleSeries)
    attachHighlightPrimitive(macdDifSeries)
    attachHighlightPrimitive(kdjSeriesRefs[0] ?? null)
    attachHighlightPrimitive(wrSeries)
    attachHighlightPrimitive(rsiSeries)
    attachHighlightPrimitive(turnoverSeries)

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
watch(
  () => props.symbolCode,
  () => {
    hoveredTradeDate.value = null
    shouldResetVisibleRange = true
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

onMounted(renderCharts)

onBeforeUnmount(() => {
  unsubs.forEach((dispose) => dispose())
  unsubs = []
  cleanupHighlightBindings()
  ;(['main', 'turnover', 'macd', 'kdj', 'wr', 'rsi'] as PanelKey[]).forEach((panelKey) => {
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
  turnoverSeries = null
  rsiSeries = null
  hoveredTradeDate.value = null
  shouldResetVisibleRange = true
})
</script>

<template>
  <section class="quant-chart-shell">
    <div class="quant-chart-summary">
      <div class="quant-chart-summary-head">
        <div class="quant-chart-symbol-row">
          <strong class="quant-chart-symbol-code">{{ symbolName || '未选择股票' }}</strong>
          <span v-if="symbolCode" class="quant-chart-symbol-code">（{{ symbolCode }}）</span>
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
        <button type="button" class="quant-switch" :class="{ active: overlayMode === 'ma' }" @click="overlayMode = 'ma'">均线</button>
        <button type="button" class="quant-switch" :class="{ active: overlayMode === 'boll' }" @click="overlayMode = 'boll'">BOLL</button>
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

    <p v-if="loading" class="muted">股票量化图表加载中...</p>
    <p v-if="renderError" class="error">{{ renderError }}</p>
    <p v-if="!loading && !sortedCandles.length" class="muted">当前没有可展示的复权股票历史数据。</p>

    <div class="quant-panel quant-panel-main-block">
      <div class="quant-panel-head">
        <h3>主图</h3>
        <div class="quant-legend">
          <span v-for="item in mainLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
        </div>
      </div>
      <div ref="mainContainerRef" class="quant-panel-chart quant-panel-chart-main"></div>
    </div>

    <div class="quant-panel quant-panel-macd-block">
      <div class="quant-panel-head">
        <h3>MACD</h3>
        <div class="quant-legend">
          <span v-for="item in macdLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
        </div>
      </div>
      <div ref="macdContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel quant-panel-kdj-block">
      <div class="quant-panel-head">
        <h3>KDJ</h3>
        <div class="quant-legend">
          <span v-for="item in kdjLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
        </div>
      </div>
      <div ref="kdjContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel quant-panel-wr-block">
      <div class="quant-panel-head">
        <h3>WR</h3>
        <div class="quant-legend">
          <span v-for="item in wrLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
        </div>
      </div>
      <div ref="wrContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel quant-panel-turnover-block">
      <div class="quant-panel-head">
        <h3>换手率</h3>
        <div class="quant-legend">
          <span v-for="item in turnoverLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
        </div>
      </div>
      <div ref="turnoverContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
    </div>

    <div class="quant-panel quant-panel-rsi-block">
      <div class="quant-panel-head">
        <h3>RSI</h3>
        <div class="quant-legend">
          <span v-for="item in rsiLegend" :key="item.label" class="quant-legend-item"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
        </div>
      </div>
      <div ref="rsiContainerRef" class="quant-panel-chart quant-panel-chart-sub"></div>
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

.quant-chart-switches,
.quant-detail-list,
.quant-legend {
  display: flex;
  align-items: center;
  gap: 8px;
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

.quant-detail-card h4,
.quant-panel-head h3 {
  margin: 0;
}

.quant-chart-detail {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 76, 117, 0.08);
  color: #0f4c75;
  font-weight: 600;
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

.quant-panel-main-block {
  order: 1;
}

.quant-panel-turnover-block {
  order: 2;
}

.quant-panel-macd-block {
  order: 3;
}

.quant-panel-kdj-block {
  order: 4;
}

.quant-panel-wr-block {
  order: 5;
}

.quant-panel-rsi-block {
  order: 6;
}

.quant-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
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
  .quant-chart-head-actions {
    margin-left: 0;
  }
}
</style>
