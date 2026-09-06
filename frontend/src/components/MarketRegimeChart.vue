<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CandlestickSeries, CrosshairMode, HistogramSeries, LineSeries, createChart,
  type IChartApi, type ISeriesApi, type Time,
} from 'lightweight-charts'
import { regimeColors, regimeLabels, type RegimePoint, type RegimeState } from '../types/marketRegime'

const props = defineProps<{ points: RegimePoint[]; committedDate: string; focusDate: string; focusRevision: number }>()
const emit = defineEmits<{ preview: [date: string | null]; confirm: [date: string] }>()
const container = ref<HTMLElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let middleSeries: ISeriesApi<'Line'> | null = null
let longSeries: ISeriesApi<'Line'> | null = null
let trackSeries: ISeriesApi<'Histogram'> | null = null
let observer: ResizeObserver | null = null
let disposed = false
const byDate = computed(() => new Map(props.points.map(point => [point.date, point])))
const states = Object.keys(regimeLabels) as RegimeState[]

function focusDate(date: string) {
  if (!chart || !date) return
  const index = props.points.findIndex(point => point.date === date)
  if (index < 0) return
  chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, index - 35), to: Math.min(props.points.length - 1, index + 60) })
}

function updateData() {
  if (!chart || !candleSeries || !middleSeries || !longSeries || !trackSeries) return
  chart.clearCrosshairPosition()
  candleSeries.setData(props.points.map(point => (
    point.open == null || point.high == null || point.low == null
      ? { time: point.date as Time }
      : { time: point.date as Time, open: point.open, high: point.high, low: point.low, close: point.close }
  )))
  middleSeries.setData(props.points.map(point => point.medium_ma == null
    ? { time: point.date as Time } : { time: point.date as Time, value: point.medium_ma }))
  longSeries.setData(props.points.map(point => point.long_ma == null
    ? { time: point.date as Time } : { time: point.date as Time, value: point.long_ma }))
  trackSeries.setData(props.points.map(point => ({ time: point.date as Time, value: 1, color: regimeColors[point.state] })))
  const last = props.points[props.points.length - 1]
  if (last) {
    const start = props.points.find(point => point.date >= '2024-09-18') ?? props.points[0]!
    chart.timeScale().setVisibleRange({ from: start.date as Time, to: last.date as Time })
  }
  if (props.focusDate) focusDate(props.focusDate)
}

onMounted(async () => {
  await nextTick()
  if (disposed || !container.value) return
  chart = createChart(container.value, {
    width: container.value.clientWidth, height: container.value.clientHeight,
    layout: { background: { color: '#ffffff' }, textColor: '#64748b', fontSize: 11, attributionLogo: false },
    grid: { vertLines: { color: '#f2f5f9' }, horzLines: { color: '#edf1f5' } },
    rightPriceScale: { borderColor: '#e2e8f0' },
    timeScale: { borderColor: '#e2e8f0', rightOffset: 1, minBarSpacing: .1, lockVisibleTimeRangeOnResize: true },
    crosshair: { mode: CrosshairMode.Normal },
  })
  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#d65959', downColor: '#27977c', borderVisible: false, wickUpColor: '#d65959', wickDownColor: '#27977c',
  })
  middleSeries = chart.addSeries(LineSeries, { color: '#2563eb', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
  longSeries = chart.addSeries(LineSeries, { color: '#c49a42', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
  trackSeries = chart.addSeries(HistogramSeries, {
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: 'custom', formatter: () => '', minMove: 1 },
  }, 1)
  chart.panes()[1]!.setHeight(50)
  // Keep the per-pane axis widget: this library version assumes all right axes exist.
  trackSeries.priceScale().applyOptions({ visible: true, ticksVisible: false, scaleMargins: { top: .15, bottom: .15 } })
  chart.subscribeCrosshairMove(param => {
    const date = typeof param.time === 'string' && byDate.value.has(param.time) ? param.time : null
    emit('preview', date)
  })
  chart.subscribeClick(param => {
    if (typeof param.time === 'string' && byDate.value.has(param.time)) emit('confirm', param.time)
  })
  observer = new ResizeObserver(() => {
    if (chart && container.value) chart.resize(container.value.clientWidth, container.value.clientHeight)
  })
  observer.observe(container.value)
  updateData()
})
watch(() => props.points, updateData)
watch(() => props.focusRevision, () => focusDate(props.focusDate))
onBeforeUnmount(() => { disposed = true; observer?.disconnect(); chart?.remove(); chart = null })
</script>

<template>
  <section class="market-regime-plot">
    <div class="plot-top"><h3>趋势与环境</h3><div class="legend"><span><i class="ma60" />MA60</span><span><i class="ma120" />MA120</span></div></div>
    <div ref="container" class="market-regime-chart" role="img" :aria-label="`指数K线与候选环境轨道，证据锁定日期${committedDate}`" @mouseleave="emit('preview', null)" />
    <div class="legend states"><span v-for="state in states" :key="state"><i :style="{ background: regimeColors[state] }" />{{ regimeLabels[state] }}</span></div>
  </section>
</template>

<style scoped>
.market-regime-plot { min-width: 0; background: #fff; padding: 12px; border: 1px solid #e2e8f0; border-radius: 8px; }
.plot-top { display: flex; justify-content: space-between; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
h3 { font-size: 16px; margin: 0; }
.legend { display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px; color: #64748b; }
.legend i { width: 14px; height: 3px; display: inline-block; vertical-align: middle; margin-right: 4px; }
.ma60 { background: #2563eb; } .ma120 { background: #c49a42; }
.market-regime-chart { height: 335px; width: 100%; position: relative; }
.states { margin-top: 9px; } .states i { width: 8px; height: 8px; }
@media (max-width: 1280px) { .market-regime-chart { height: 315px; } }
</style>
