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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { Csi1000FuturesReport, Csi1000FuturesWave } from '../types/research'

const props = defineProps<{
  candles: Csi1000FuturesReport['index_candles']
  wave?: Csi1000FuturesWave | null
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const tooltipRef = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null
let markers: ISeriesMarkersPluginApi<Time> | null = null
let resizeObserver: ResizeObserver | null = null

const sortedCandles = computed(() =>
  [...props.candles].sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)
const candleMap = computed(() => new Map(sortedCandles.value.map((item) => [item.trade_date, item])))

function formatNumber(value: number) {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function applyVisibleRange() {
  if (!chart) return
  if (props.wave?.start_date && props.wave.end_date) {
    chart.timeScale().setVisibleRange({
      from: props.wave.start_date as Time,
      to: props.wave.end_date as Time,
    })
    return
  }
  chart.timeScale().fitContent()
}

function updateData() {
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
  const waveMarkers = props.wave
    ? [
        props.wave.low_date
          ? {
              time: props.wave.low_date as Time,
              position: 'belowBar' as const,
              color: '#059669',
              shape: 'circle' as const,
              text: `20%波段低点 ${formatNumber(props.wave.low_value)}`,
              size: 1.4,
            }
          : null,
        props.wave.high_date
          ? {
              time: props.wave.high_date as Time,
              position: 'aboveBar' as const,
              color: '#d97706',
              shape: 'circle' as const,
              text: `20%波段高点 ${formatNumber(props.wave.high_value)}`,
              size: 1.4,
            }
          : null,
      ].filter((item) => item != null)
    : []
  markers?.setMarkers(waveMarkers.sort((left, right) => String(left.time).localeCompare(String(right.time))))
  applyVisibleRange()
}

onMounted(() => {
  if (!containerRef.value) return
  chart = createChart(containerRef.value, {
    autoSize: true,
    height: 390,
    layout: {
      background: { type: ColorType.Solid, color: '#ffffff' },
      textColor: '#475569',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    },
    grid: {
      vertLines: { color: '#eef2f7' },
      horzLines: { color: '#eef2f7' },
    },
    rightPriceScale: { borderColor: '#dbe3ec', scaleMargins: { top: 0.12, bottom: 0.1 } },
    timeScale: { borderColor: '#dbe3ec', rightOffset: 4 },
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
  resizeObserver = new ResizeObserver(applyVisibleRange)
  resizeObserver.observe(containerRef.value)
  chart.subscribeCrosshairMove((param) => {
    if (!tooltipRef.value || !param.time || !param.point) return
    const item = candleMap.value.get(String(param.time))
    if (!item) {
      tooltipRef.value.style.display = 'none'
      return
    }
    tooltipRef.value.style.display = 'block'
    tooltipRef.value.style.left = `${Math.min(param.point.x + 14, Math.max(8, (containerRef.value?.clientWidth ?? 400) - 220))}px`
    tooltipRef.value.style.top = `${Math.max(8, param.point.y - 54)}px`
    const pivot = item.pivot ? `20% ZigZag ${item.pivot === 'low' ? '低点' : item.pivot === 'high' ? '高点' : item.pivot}` : ''
    tooltipRef.value.innerHTML = `<strong>${item.trade_date}</strong><span>开 ${formatNumber(item.open)}　高 ${formatNumber(item.high)}</span><span>低 ${formatNumber(item.low)}　收 ${formatNumber(item.close)}</span><em>${pivot}</em>`
  })
  updateData()
})

watch([sortedCandles, () => props.wave], updateData, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  markers?.detach()
  chart?.remove()
  markers = null
  candleSeries = null
  chart = null
})
</script>

<template>
  <div class="futures-signal-chart">
    <div ref="containerRef" class="futures-signal-canvas"></div>
    <div ref="tooltipRef" class="futures-signal-tooltip"></div>
  </div>
</template>

<style scoped>
.futures-signal-chart { position: relative; width: 100%; min-width: 0; height: 390px; background: #fff; }
.futures-signal-canvas { width: 100%; height: 390px; }
.futures-signal-tooltip { display: none; position: absolute; z-index: 3; width: 205px; padding: 8px 10px; border: 1px solid #bfdbfe; border-radius: 5px; background: rgba(255, 255, 255, .97); box-shadow: 0 5px 18px rgba(15, 23, 42, .13); pointer-events: none; color: #334155; font-size: 12px; }
.futures-signal-tooltip strong, .futures-signal-tooltip span, .futures-signal-tooltip em { display: block; }
.futures-signal-tooltip strong { margin-bottom: 4px; color: #1e3a8a; }
.futures-signal-tooltip em { margin-top: 4px; color: #64748b; font-style: normal; }
</style>
