<script setup lang="ts">
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  type BusinessDay,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LogicalRange,
  type Time,
} from 'lightweight-charts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { KlineCandle } from '../types/stock'
import type { QuantRiskDashboardPoint, QuantRiskDisplayState } from '../types/risk'

const props = withDefaults(
  defineProps<{
    candles: KlineCandle[]
    points: QuantRiskDashboardPoint[]
    committedDate: string | null
    hasMoreHistory?: boolean
    loadingMoreHistory?: boolean
  }>(),
  {
    hasMoreHistory: false,
    loadingMoreHistory: false,
  },
)

const emit = defineEmits<{
  (event: 'preview-date', tradeDate: string): void
  (event: 'preview-clear'): void
  (event: 'commit-date', tradeDate: string): void
  (event: 'request-more-history', earliestTradeDate: string): void
}>()

const STATE_COLORS: Record<QuantRiskDisplayState, string> = {
  stable: 'rgba(44, 167, 122, 0.28)',
  global: '#7657c8',
  yellow: '#d89a18',
  yellow_global: '#d56b2f',
  red: '#dc4f4f',
  red_global: '#762d58',
  incomplete: '#d9dee7',
}

const PRICE_PANE_HEIGHT = 246
const SCORE_PANE_HEIGHT = 82
const TRACK_PANE_HEIGHT = 38
const HISTORY_REQUEST_THRESHOLD = 15

const containerRef = ref<HTMLDivElement | null>(null)
const tooltip = ref({
  visible: false,
  left: 0,
  top: 0,
  date: '',
  price: '',
  score: '',
})
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let leadingMarkers: ISeriesMarkersPluginApi<Time> | null = null
let scoreSeries: ISeriesApi<'Line'> | null = null
let stateSeries: ISeriesApi<'Histogram'> | null = null
let hasRenderedData = false
let renderedEarliestDate: string | null = null
let lastRequestedHistoryBoundary: string | null = null
let visibleRangeUnsubscribe: (() => void) | null = null

const sortedCandles = computed(() =>
  [...props.candles].sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)
const sortedPoints = computed(() =>
  [...props.points].sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)
const candleMap = computed(() => new Map(sortedCandles.value.map((item) => [item.trade_date, item])))
const pointMap = computed(() => new Map(sortedPoints.value.map((item) => [item.trade_date, item])))
const chartHeight = computed(() => PRICE_PANE_HEIGHT + SCORE_PANE_HEIGHT + TRACK_PANE_HEIGHT + 28)

function toDateString(time: Time) {
  if (typeof time === 'string') return time
  if (typeof time === 'number') return new Date(time * 1000).toISOString().slice(0, 10)
  const businessDay = time as BusinessDay
  return `${businessDay.year}-${String(businessDay.month).padStart(2, '0')}-${String(businessDay.day).padStart(2, '0')}`
}

function formatNumber(value: number) {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function displayStateText(value: QuantRiskDisplayState | null) {
  return {
    stable: '平稳',
    global: '全球风险',
    yellow: '黄色',
    yellow_global: '黄色+全球',
    red: '红色',
    red_global: '红色+全球',
    incomplete: '数据不完整',
  }[value ?? 'incomplete']
}

function scoreDisplayState(point: QuantRiskDashboardPoint | undefined): QuantRiskDisplayState {
  if (point?.overall_score == null) return 'incomplete'
  const baseState = point.overall_score > 50
    ? 'red'
    : point.overall_score >= 40
      ? 'yellow'
      : 'stable'
  const hasGlobalOverlay = point.global_shock === true
    || (point.scoring_mode !== 'flat' && point.global_leading === true)
  if (!hasGlobalOverlay) return baseState
  if (baseState === 'red') return 'red_global'
  if (baseState === 'yellow') return 'yellow_global'
  return 'global'
}

function applySelectedCrosshair() {
  if (!chart || !candleSeries || !props.committedDate) return
  const candle = candleMap.value.get(props.committedDate)
  if (!candle) return
  chart.setCrosshairPosition(candle.close, props.committedDate as Time, candleSeries)
}

function updateData() {
  if (!chart || !candleSeries || !scoreSeries || !stateSeries) return
  const previousVisibleRange = hasRenderedData
    ? chart.timeScale().getVisibleLogicalRange()
    : null
  const previousEarliestDate = renderedEarliestDate
  candleSeries.setData(
    sortedCandles.value.map((item) => ({
      time: item.trade_date as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    })),
  )
  leadingMarkers?.setMarkers(
    [
      ...sortedPoints.value
        .filter((item, index, items) => (
          item.global_raw_leading === true
          && items[index - 1]?.global_raw_leading !== true
          && candleMap.value.has(item.trade_date)
        ))
        .map((item) => ({
          time: item.trade_date as Time,
          position: 'belowBar' as const,
          color: '#a894df',
          shape: 'arrowUp' as const,
          text: '全球原始前兆',
          size: 1.1,
        })),
      ...sortedPoints.value
        .filter((item) => (
          item.global_leading === true
          && item.global_leading_trigger_date === item.trade_date
          && candleMap.value.has(item.trade_date)
        ))
        .map((item) => ({
          time: item.trade_date as Time,
          position: 'aboveBar' as const,
          color: '#7657c8',
          shape: 'circle' as const,
          text: item.scoring_mode === 'flat' ? '沪深300有效前兆' : 'A股有效前兆',
          size: 1.2,
        })),
    ].sort((left, right) => String(left.time).localeCompare(String(right.time))),
  )
  scoreSeries.setData(
    sortedPoints.value.map((item) =>
      item.overall_score == null
        ? { time: item.trade_date as Time }
        : { time: item.trade_date as Time, value: item.overall_score },
    ),
  )
  stateSeries.setData(
    sortedPoints.value.map((item) => ({
      time: item.trade_date as Time,
      value: 1,
      color: STATE_COLORS[scoreDisplayState(item)],
    })),
  )
  const nextEarliestDate = sortedCandles.value[0]?.trade_date ?? null
  const prependedBars =
    previousVisibleRange && previousEarliestDate && nextEarliestDate && nextEarliestDate < previousEarliestDate
      ? sortedCandles.value.filter((item) => item.trade_date < previousEarliestDate).length
      : 0
  if (!hasRenderedData) {
    chart.timeScale().fitContent()
    hasRenderedData = true
  } else if (previousVisibleRange && prependedBars > 0) {
    chart.timeScale().setVisibleLogicalRange({
      from: previousVisibleRange.from + prependedBars,
      to: previousVisibleRange.to + prependedBars,
    })
  }
  renderedEarliestDate = nextEarliestDate
  window.requestAnimationFrame(applySelectedCrosshair)
}

function maybeRequestMoreHistory(range: LogicalRange | null) {
  if (
    !range
    || !props.hasMoreHistory
    || props.loadingMoreHistory
    || !sortedCandles.value.length
    || range.from > HISTORY_REQUEST_THRESHOLD
  ) {
    return
  }
  const earliestTradeDate = sortedCandles.value[0]?.trade_date
  if (!earliestTradeDate || earliestTradeDate === lastRequestedHistoryBoundary) return
  lastRequestedHistoryBoundary = earliestTradeDate
  emit('request-more-history', earliestTradeDate)
}

function destroyChart() {
  visibleRangeUnsubscribe?.()
  visibleRangeUnsubscribe = null
  leadingMarkers?.detach()
  chart?.remove()
  chart = null
  candleSeries = null
  leadingMarkers = null
  scoreSeries = null
  stateSeries = null
  hasRenderedData = false
  renderedEarliestDate = null
  lastRequestedHistoryBoundary = null
}

function buildChart() {
  destroyChart()
  if (!containerRef.value) return
  chart = createChart(containerRef.value, {
    autoSize: true,
    height: chartHeight.value,
    layout: {
      background: { type: ColorType.Solid, color: '#ffffff' },
      textColor: '#64748b',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      panes: {
        separatorColor: '#e6ebf2',
        separatorHoverColor: '#cbd5e1',
        enableResize: false,
      },
    },
    grid: {
      vertLines: { color: '#eef2f7' },
      horzLines: { color: '#eef2f7' },
    },
    rightPriceScale: {
      borderColor: '#dce3ec',
      scaleMargins: { top: 0.1, bottom: 0.08 },
    },
    timeScale: {
      borderColor: '#dce3ec',
      rightOffset: 2,
      barSpacing: 6,
      minBarSpacing: 1.2,
    },
    crosshair: {
      vertLine: { color: '#718096', labelBackgroundColor: '#315fa8' },
      horzLine: { color: '#94a3b8', labelBackgroundColor: '#315fa8' },
    },
  })

  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#df5a5a',
    downColor: '#2ca77a',
    wickUpColor: '#df5a5a',
    wickDownColor: '#2ca77a',
    borderVisible: false,
    priceLineVisible: false,
    lastValueVisible: false,
  })
  leadingMarkers = createSeriesMarkers(candleSeries, [])
  scoreSeries = chart.addSeries(
    LineSeries,
    {
      color: '#315fa8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerRadius: 3,
      priceFormat: { type: 'custom', formatter: (value: number) => `${value.toFixed(1)}` },
    },
    1,
  )

  stateSeries = chart.addSeries(
    HistogramSeries,
    {
      base: 0,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: () => '' },
    },
    2,
  )
  chart.priceScale('right', 2).applyOptions({
    borderVisible: false,
    scaleMargins: { top: 0, bottom: 0 },
  })

  chart.priceScale('right', 1).applyOptions({
    visible: true,
    scaleMargins: { top: 0.12, bottom: 0.12 },
  })

  chart.subscribeCrosshairMove((param) => {
    if (!param.time) {
      tooltip.value.visible = false
      emit('preview-clear')
      return
    }
    const tradeDate = toDateString(param.time)
    const candle = candleMap.value.get(tradeDate)
    const point = pointMap.value.get(tradeDate)
    if (!candle) {
      tooltip.value.visible = false
      emit('preview-clear')
      return
    }
    emit('preview-date', tradeDate)
    const width = containerRef.value?.clientWidth ?? 600
    const x = param.point?.x ?? 0
    const y = param.point?.y ?? 0
    tooltip.value = {
      visible: true,
      left: Math.min(Math.max(8, x + 14), Math.max(8, width - 238)),
      top: Math.max(8, Math.min(y - 60, PRICE_PANE_HEIGHT - 100)),
      date: tradeDate,
      price: `开 ${formatNumber(candle.open)}　高 ${formatNumber(candle.high)}　低 ${formatNumber(candle.low)}　收 ${formatNumber(candle.close)}`,
      score: point?.overall_score == null
        ? '综合风险：数据不完整'
        : `综合风险 ${point.overall_score.toFixed(1)} · ${displayStateText(scoreDisplayState(point))}`,
    }
  })
  chart.subscribeClick((param) => {
    if (param.time) emit('commit-date', toDateString(param.time))
  })
  updateData()
  const visibleRangeHandler = (range: LogicalRange | null) => maybeRequestMoreHistory(range)
  chart.timeScale().subscribeVisibleLogicalRangeChange(visibleRangeHandler)
  visibleRangeUnsubscribe = () => chart?.timeScale().unsubscribeVisibleLogicalRangeChange(visibleRangeHandler)
  const builtChart = chart
  window.requestAnimationFrame(() => {
    if (chart !== builtChart) return
    const panes = builtChart.panes()
    panes[0]?.setStretchFactor(PRICE_PANE_HEIGHT)
    panes[1]?.setStretchFactor(SCORE_PANE_HEIGHT)
    panes[2]?.setStretchFactor(TRACK_PANE_HEIGHT)
  })
}

onMounted(buildChart)

watch([sortedCandles, sortedPoints], updateData, { deep: true })
watch(
  () => sortedCandles.value[0]?.trade_date ?? null,
  (nextEarliest, previousEarliest) => {
    if (nextEarliest && nextEarliest !== previousEarliest) lastRequestedHistoryBoundary = null
  },
)
watch(
  () => props.loadingMoreHistory,
  (loading, previousLoading) => {
    if (previousLoading && !loading) lastRequestedHistoryBoundary = null
  },
)
watch(() => props.committedDate, () => {
  tooltip.value.visible = false
  applySelectedCrosshair()
})

onBeforeUnmount(destroyChart)
</script>

<template>
  <div class="risk-monitor-chart" :style="{ height: `${chartHeight}px` }">
    <div ref="containerRef" class="risk-monitor-canvas"></div>

    <div class="score-pane-label">综合风险完成度</div>
    <div
      class="track-pane-label"
      :style="{ top: `${PRICE_PANE_HEIGHT + SCORE_PANE_HEIGHT + 7}px` }"
    >
      最终风险状态
    </div>

    <div
      v-if="tooltip.visible"
      class="risk-monitor-tooltip"
      :style="{ left: `${tooltip.left}px`, top: `${tooltip.top}px` }"
    >
      <strong>{{ tooltip.date }}</strong>
      <span>{{ tooltip.price }}</span>
      <em>{{ tooltip.score }}</em>
      <small v-if="pointMap.get(tooltip.date)">
        状态 {{ displayStateText(scoreDisplayState(pointMap.get(tooltip.date))) }}
        <template v-if="pointMap.get(tooltip.date)?.global_raw_leading === true"> · 原始前兆</template>
        <template v-if="pointMap.get(tooltip.date)?.global_leading === true">
          · {{ pointMap.get(tooltip.date)?.scoring_mode === 'flat' ? '沪深300生效' : 'A股生效' }}
        </template>
        <template v-if="pointMap.get(tooltip.date)?.global_shock === true"> · 确认</template>
      </small>
    </div>
  </div>
</template>

<style scoped>
.risk-monitor-chart {
  position: relative;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  background: #fff;
}

.risk-monitor-canvas {
  width: 100%;
  height: 100%;
}

.score-pane-label,
.track-pane-label {
  position: absolute;
  z-index: 2;
  left: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.9);
  color: #526174;
  font-size: 11px;
  line-height: 16px;
  pointer-events: none;
}

.score-pane-label {
  top: 255px;
  color: #315fa8;
  font-weight: 600;
}

.track-pane-label {
  display: flex;
  align-items: center;
  gap: 5px;
}

.track-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.risk-monitor-tooltip {
  position: absolute;
  z-index: 5;
  width: 224px;
  padding: 9px 10px;
  border: 1px solid #bfd0e6;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 7px 20px rgba(15, 23, 42, 0.14);
  color: #334155;
  font-size: 11px;
  line-height: 1.55;
  pointer-events: none;
}

.risk-monitor-tooltip strong,
.risk-monitor-tooltip span,
.risk-monitor-tooltip em,
.risk-monitor-tooltip small {
  display: block;
}

.risk-monitor-tooltip strong { color: #1f4d8c; }
.risk-monitor-tooltip em { color: #315fa8; font-style: normal; font-weight: 600; }
.risk-monitor-tooltip small { color: #64748b; }
</style>
