<script setup lang="ts">
import { LineSeries, createChart, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import type { MacroPoint } from '../types/macro'

interface SeriesDefinition {
  key: keyof MacroPoint
  label: string
  color: string
}

const props = defineProps<{
  points: MacroPoint[]
  series: SeriesDefinition[]
  unit: string
  visibleStartDate?: string
}>()

const containerRef = ref<HTMLElement | null>(null)
const hoverDate = ref('')
const hoverValues = ref<Array<{ label: string; color: string; value: number | null }>>([])
let chart: IChartApi | null = null
let resizeObserver: ResizeObserver | null = null
let lineSeries: ISeriesApi<'Line', Time>[] = []

function applyVisibleRange() {
  if (!chart || !props.points.length) return
  const lastDate = props.points[props.points.length - 1]?.trade_date
  if (props.visibleStartDate && lastDate) {
    chart.timeScale().setVisibleRange({
      from: props.visibleStartDate as Time,
      to: lastDate as Time,
    })
    return
  }
  chart.timeScale().fitContent()
}

function disposeChart() {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.remove()
  chart = null
  lineSeries = []
}

function updateHover(point?: MacroPoint) {
  const current = point ?? props.points[props.points.length - 1]
  hoverDate.value = current?.trade_date ?? ''
  hoverValues.value = props.series.map((item) => {
    const rawValue = current?.[item.key]
    return {
      label: item.label,
      color: item.color,
      value: typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : null,
    }
  })
}

async function renderChart() {
  await nextTick()
  if (!containerRef.value) return
  disposeChart()
  chart = createChart(containerRef.value, {
    width: containerRef.value.clientWidth,
    height: 390,
    layout: { background: { color: '#ffffff' }, textColor: '#475569' },
    grid: {
      vertLines: { color: '#eef2f6' },
      horzLines: { color: '#e5eaf0' },
    },
    rightPriceScale: { borderColor: '#dce3eb' },
    timeScale: { borderColor: '#dce3eb', timeVisible: false },
    crosshair: {
      vertLine: { color: '#94a3b8', labelBackgroundColor: '#334155' },
      horzLine: { color: '#94a3b8', labelBackgroundColor: '#334155' },
    },
    localization: {
      priceFormatter: (value: number) => `${value.toFixed(2)}${props.unit}`,
    },
  })

  lineSeries = props.series.map((item) => {
    const series = chart!.addSeries(LineSeries, {
      color: item.color,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    })
    series.setData(
      props.points.flatMap((point) => {
        const rawValue = point[item.key]
        return typeof rawValue === 'number' && Number.isFinite(rawValue)
          ? [{ time: point.trade_date as Time, value: rawValue }]
          : []
      }),
    )
    return series
  })
  applyVisibleRange()
  chart.subscribeCrosshairMove((param) => {
    if (!param.time) {
      updateHover()
      return
    }
    const target = props.points.find((item) => item.trade_date === String(param.time))
    updateHover(target)
  })
  resizeObserver = new ResizeObserver(() => {
    if (containerRef.value && chart) chart.applyOptions({ width: containerRef.value.clientWidth })
  })
  resizeObserver.observe(containerRef.value)
  updateHover()
}

watch(() => [props.points, props.series, props.unit], renderChart, { deep: true, immediate: true })
watch(() => props.visibleStartDate, applyVisibleRange)
onBeforeUnmount(disposeChart)
</script>

<template>
  <div class="macro-chart-shell">
    <div class="macro-chart-legend">
      <span class="macro-chart-date">{{ hoverDate || '暂无数据' }}</span>
      <span v-for="item in hoverValues" :key="item.label" class="macro-chart-legend-item">
        <i :style="{ backgroundColor: item.color }"></i>
        {{ item.label }}
        <strong>{{ item.value == null ? '-' : `${item.value.toFixed(2)}${unit}` }}</strong>
      </span>
    </div>
    <div ref="containerRef" class="macro-chart"></div>
  </div>
</template>

<style scoped>
.macro-chart-shell { position: relative; min-width: 0; }
.macro-chart-legend { min-height: 42px; display: flex; align-items: center; gap: 20px; flex-wrap: wrap; padding: 0 4px 10px; color: #64748b; font-size: 13px; }
.macro-chart-date { font-weight: 700; color: #334155; }
.macro-chart-legend-item { display: inline-flex; align-items: center; gap: 6px; }
.macro-chart-legend-item i { width: 10px; height: 10px; border-radius: 2px; }
.macro-chart-legend-item strong { color: #172033; font-variant-numeric: tabular-nums; }
.macro-chart { width: 100%; height: 390px; }
</style>
