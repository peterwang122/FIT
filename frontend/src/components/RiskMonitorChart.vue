<script setup lang="ts">
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type BusinessDay,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { KlineCandle } from '../types/stock'
import type { QuantRiskDashboardPoint, QuantRiskStrategyKey } from '../types/risk'

type TrackVisibility = Record<QuantRiskStrategyKey, boolean>

const props = defineProps<{
  candles: KlineCandle[]
  points: QuantRiskDashboardPoint[]
  selectedDate: string | null
  visibleTracks: TrackVisibility
}>()

const emit = defineEmits<{
  (event: 'select-date', tradeDate: string): void
}>()

const TRACKS: Array<{
  key: QuantRiskStrategyKey
  label: string
  color: string
}> = [
  { key: 'yellow_vulnerability', label: '黄色脆弱期', color: '#d89a18' },
  { key: 'red_escalation', label: '红色风险升级', color: '#dc4f4f' },
  { key: 'global_shock', label: '全球冲击', color: '#7657c8' },
]

const PRICE_PANE_HEIGHT = 246
const SCORE_PANE_HEIGHT = 82
const TRACK_PANE_HEIGHT = 34

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
let scoreSeries: ISeriesApi<'Line'> | null = null

const sortedCandles = computed(() =>
  [...props.candles].sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)
const sortedPoints = computed(() =>
  [...props.points].sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)
const candleMap = computed(() => new Map(sortedCandles.value.map((item) => [item.trade_date, item])))
const pointMap = computed(() => new Map(sortedPoints.value.map((item) => [item.trade_date, item])))
const enabledTracks = computed(() => TRACKS.filter((item) => props.visibleTracks[item.key]))
const chartHeight = computed(
  () => PRICE_PANE_HEIGHT + SCORE_PANE_HEIGHT + enabledTracks.value.length * TRACK_PANE_HEIGHT + 28,
)

function toDateString(time: Time) {
  if (typeof time === 'string') return time
  if (typeof time === 'number') return new Date(time * 1000).toISOString().slice(0, 10)
  const businessDay = time as BusinessDay
  return `${businessDay.year}-${String(businessDay.month).padStart(2, '0')}-${String(businessDay.day).padStart(2, '0')}`
}

function formatNumber(value: number) {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function stateText(value: boolean | null) {
  if (value === true) return '命中'
  if (value === false) return '未命中'
  return '数据缺失'
}

function applySelectedCrosshair() {
  if (!chart || !candleSeries || !props.selectedDate) return
  const candle = candleMap.value.get(props.selectedDate)
  if (!candle) return
  chart.setCrosshairPosition(candle.close, props.selectedDate as Time, candleSeries)
}

function updateData() {
  if (!chart || !candleSeries || !scoreSeries) return
  candleSeries.setData(
    sortedCandles.value.map((item) => ({
      time: item.trade_date as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    })),
  )
  scoreSeries.setData(
    sortedPoints.value.map((item) =>
      item.composite_score == null
        ? { time: item.trade_date as Time }
        : { time: item.trade_date as Time, value: item.composite_score },
    ),
  )
  chart.timeScale().fitContent()
  window.requestAnimationFrame(applySelectedCrosshair)
}

function destroyChart() {
  chart?.remove()
  chart = null
  candleSeries = null
  scoreSeries = null
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

  enabledTracks.value.forEach((track, index) => {
    const paneIndex = index + 2
    const series = chart!.addSeries(
      HistogramSeries,
      {
        base: 0,
        priceLineVisible: false,
        lastValueVisible: false,
        priceFormat: { type: 'custom', formatter: () => '' },
      },
      paneIndex,
    )
    series.setData(
      sortedPoints.value.map((item) => {
        const state = item[track.key]
        if (state == null) {
          return { time: item.trade_date as Time, value: 1, color: '#d9dee7' }
        }
        return {
          time: item.trade_date as Time,
          value: state ? 1 : 0,
          color: state ? track.color : 'rgba(255,255,255,0)',
        }
      }),
    )
    chart!.priceScale('right', paneIndex).applyOptions({
      borderVisible: false,
      scaleMargins: { top: 0, bottom: 0 },
    })
  })

  chart.priceScale('right', 1).applyOptions({
    visible: true,
    scaleMargins: { top: 0.12, bottom: 0.12 },
  })

  chart.subscribeCrosshairMove((param) => {
    if (!param.time) {
      tooltip.value.visible = false
      return
    }
    const tradeDate = toDateString(param.time)
    const candle = candleMap.value.get(tradeDate)
    const point = pointMap.value.get(tradeDate)
    if (!candle) {
      tooltip.value.visible = false
      return
    }
    emit('select-date', tradeDate)
    const width = containerRef.value?.clientWidth ?? 600
    const x = param.point?.x ?? 0
    const y = param.point?.y ?? 0
    tooltip.value = {
      visible: true,
      left: Math.min(Math.max(8, x + 14), Math.max(8, width - 238)),
      top: Math.max(8, Math.min(y - 60, PRICE_PANE_HEIGHT - 100)),
      date: tradeDate,
      price: `开 ${formatNumber(candle.open)}　高 ${formatNumber(candle.high)}　低 ${formatNumber(candle.low)}　收 ${formatNumber(candle.close)}`,
      score: point?.composite_score == null
        ? '综合风险：数据不完整'
        : `综合风险 ${point.composite_score.toFixed(1)} · ${point.risk_level_label ?? ''}`,
    }
  })
  chart.subscribeClick((param) => {
    if (param.time) emit('select-date', toDateString(param.time))
  })
  updateData()
  const builtChart = chart
  window.requestAnimationFrame(() => {
    if (chart !== builtChart) return
    const panes = builtChart.panes()
    panes[0]?.setStretchFactor(PRICE_PANE_HEIGHT)
    panes[1]?.setStretchFactor(SCORE_PANE_HEIGHT)
    for (let index = 2; index < panes.length; index += 1) {
      panes[index]?.setStretchFactor(TRACK_PANE_HEIGHT)
    }
  })
}

onMounted(buildChart)

watch([sortedCandles, sortedPoints], updateData, { deep: true })
watch(
  () => props.visibleTracks,
  () => nextTick(buildChart),
  { deep: true },
)
watch(() => props.selectedDate, () => {
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
      v-for="(track, index) in enabledTracks"
      :key="track.key"
      class="track-pane-label"
      :style="{ top: `${PRICE_PANE_HEIGHT + SCORE_PANE_HEIGHT + index * TRACK_PANE_HEIGHT + 7}px` }"
    >
      <span class="track-dot" :style="{ backgroundColor: track.color }"></span>
      {{ track.label }}
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
        黄 {{ stateText(pointMap.get(tooltip.date)!.yellow_vulnerability) }} ·
        红 {{ stateText(pointMap.get(tooltip.date)!.red_escalation) }} ·
        全球 {{ stateText(pointMap.get(tooltip.date)!.global_shock) }}
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
