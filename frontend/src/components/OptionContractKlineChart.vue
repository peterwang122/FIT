<script setup lang="ts">
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
} from 'lightweight-charts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { VixOptionContractCandle } from '../types/research'

const props = defineProps<{
  candles: VixOptionContractCandle[]
  signalDate: string
  exitDate?: string | null
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const tooltipRef = ref<HTMLDivElement | null>(null)
const signalOverlayRef = ref<HTMLDivElement | null>(null)
const exitOverlayRef = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let markers: ISeriesMarkersPluginApi<Time> | null = null
let resizeObserver: ResizeObserver | null = null
let visibleRangeUnsubscribe: (() => void) | null = null

const sortedCandles = computed(() =>
  [...props.candles].sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)
const candleMap = computed(() => new Map(sortedCandles.value.map((item) => [item.trade_date, item])))

function number(value: number | null | undefined, digits = 4) {
  if (value == null || !Number.isFinite(value)) return '-'
  return value.toLocaleString('zh-CN', { maximumFractionDigits: digits })
}

function markerDate(targetDate: string | null | undefined) {
  const date = targetDate?.slice(0, 10)
  if (!date) return null
  if (candleMap.value.has(date)) return date
  return sortedCandles.value.find((item) => item.trade_date >= date)?.trade_date ?? null
}

function updateOverlay(element: HTMLDivElement | null, targetDate: string | null | undefined) {
  if (!chart || !element) return
  const markedDate = markerDate(targetDate)
  if (!markedDate) {
    element.style.display = 'none'
    return
  }
  const coordinate = chart.timeScale().timeToCoordinate(markedDate as Time)
  if (coordinate == null) {
    element.style.display = 'none'
    return
  }
  element.style.display = 'block'
  element.style.left = `${coordinate}px`
}

function updateDateOverlays() {
  updateOverlay(signalOverlayRef.value, props.signalDate)
  updateOverlay(exitOverlayRef.value, props.exitDate)
}

function updateChartData() {
  if (!chart || !candleSeries) return
  candleSeries.setData(
    sortedCandles.value.map((item) => ({
      time: item.trade_date as Time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    })),
  )
  const markedSignalDate = markerDate(props.signalDate)
  const markedExitDate = markerDate(props.exitDate)
  const signalDate = props.signalDate.slice(0, 10)
  const exitDate = props.exitDate?.slice(0, 10) ?? ''
  const nextMarkers = []
  if (markedSignalDate) {
    nextMarkers.push({
      time: markedSignalDate as Time,
      position: 'aboveBar' as const,
      color: '#d97706',
      shape: 'arrowDown' as const,
      text: `信号日 ${signalDate}`,
      size: 1.5,
    })
  }
  if (markedExitDate && exitDate) {
    nextMarkers.push({
      time: markedExitDate as Time,
      position: 'belowBar' as const,
      color: '#2563eb',
      shape: 'arrowUp' as const,
      text: `卖出日 ${exitDate}`,
      size: 1.5,
    })
  }
  nextMarkers.sort((left, right) => String(left.time).localeCompare(String(right.time)))
  markers?.setMarkers(nextMarkers)
  chart.timeScale().fitContent()
  void nextTick(updateDateOverlays)
}

onMounted(() => {
  if (!containerRef.value) return
  chart = createChart(containerRef.value, {
    autoSize: true,
    height: 320,
    layout: {
      background: { type: ColorType.Solid, color: '#ffffff' },
      textColor: '#475569',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    },
    grid: {
      vertLines: { color: '#eef2f7' },
      horzLines: { color: '#eef2f7' },
    },
    rightPriceScale: {
      borderColor: '#dbe3ec',
      scaleMargins: { top: 0.18, bottom: 0.08 },
    },
    timeScale: {
      borderColor: '#dbe3ec',
      timeVisible: false,
      rightOffset: 4,
    },
    crosshair: {
      vertLine: { labelBackgroundColor: '#1d4ed8' },
      horzLine: { labelBackgroundColor: '#1d4ed8' },
    },
  })
  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#ef4444',
    downColor: '#10b981',
    borderVisible: false,
    wickUpColor: '#ef4444',
    wickDownColor: '#10b981',
    priceLineVisible: false,
  })
  markers = createSeriesMarkers(candleSeries, [])
  const updateOnRangeChange = () => updateDateOverlays()
  chart.timeScale().subscribeVisibleTimeRangeChange(updateOnRangeChange)
  visibleRangeUnsubscribe = () => chart?.timeScale().unsubscribeVisibleTimeRangeChange(updateOnRangeChange)
  resizeObserver = new ResizeObserver(updateDateOverlays)
  resizeObserver.observe(containerRef.value)
  chart.subscribeCrosshairMove((param) => {
    if (!tooltipRef.value) return
    const date = param.time ? String(param.time) : ''
    const candle = candleMap.value.get(date)
    if (!candle || !param.point) {
      tooltipRef.value.style.display = 'none'
      return
    }
    tooltipRef.value.style.display = 'block'
    tooltipRef.value.style.left = `${Math.min(param.point.x + 14, Math.max(8, (containerRef.value?.clientWidth ?? 300) - 205))}px`
    tooltipRef.value.style.top = `${Math.max(8, param.point.y - 58)}px`
    tooltipRef.value.innerHTML = `<strong>${date}</strong><span>开 ${number(candle.open)}　高 ${number(candle.high)}</span><span>低 ${number(candle.low)}　收 ${number(candle.close)}</span><span>成交量 ${number(candle.volume, 0)}</span>`
  })
  updateChartData()
})

watch([sortedCandles, () => props.signalDate, () => props.exitDate], updateChartData)

onBeforeUnmount(() => {
  visibleRangeUnsubscribe?.()
  resizeObserver?.disconnect()
  markers?.detach()
  chart?.remove()
  markers = null
  candleSeries = null
  chart = null
  visibleRangeUnsubscribe = null
  resizeObserver = null
})
</script>

<template>
  <div class="option-kline-chart">
    <div ref="containerRef" class="option-kline-canvas"></div>
    <div ref="signalOverlayRef" class="option-signal-overlay">
      <span>信号日 {{ signalDate.slice(0, 10) }}</span>
    </div>
    <div v-if="exitDate" ref="exitOverlayRef" class="option-exit-overlay">
      <span>卖出日 {{ exitDate.slice(0, 10) }}</span>
    </div>
    <div ref="tooltipRef" class="option-kline-tooltip"></div>
  </div>
</template>

<style scoped>
.option-kline-chart { position: relative; width: 100%; min-width: 0; height: 320px; background: #fff; }
.option-kline-canvas { width: 100%; height: 320px; }
.option-signal-overlay { display: none; position: absolute; z-index: 2; top: 6px; bottom: 26px; width: 0; border-left: 2px dashed #d97706; pointer-events: none; }
.option-signal-overlay span { position: absolute; top: 0; left: 5px; padding: 3px 6px; border: 1px solid #f59e0b; border-radius: 4px; background: #fffbeb; color: #92400e; font-size: 11px; font-weight: 800; white-space: nowrap; }
.option-exit-overlay { display: none; position: absolute; z-index: 2; top: 6px; bottom: 26px; width: 0; border-left: 2px dashed #2563eb; pointer-events: none; }
.option-exit-overlay span { position: absolute; top: 28px; left: 5px; padding: 3px 6px; border: 1px solid #60a5fa; border-radius: 4px; background: #eff6ff; color: #1e40af; font-size: 11px; font-weight: 800; white-space: nowrap; }
.option-kline-tooltip { display: none; position: absolute; z-index: 3; width: 190px; padding: 8px 10px; border: 1px solid #bfdbfe; border-radius: 5px; background: rgba(255, 255, 255, .96); box-shadow: 0 5px 18px rgba(15, 23, 42, .13); pointer-events: none; color: #334155; font-size: 12px; }
.option-kline-tooltip strong, .option-kline-tooltip span { display: block; }
.option-kline-tooltip strong { margin-bottom: 4px; color: #1e3a8a; }
</style>
