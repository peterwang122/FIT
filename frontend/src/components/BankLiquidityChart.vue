<script setup lang="ts">
import {
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from 'lightweight-charts'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import type { BankLiquidityDailyPoint } from '../types/macro'

export interface BankLiquiditySeriesDefinition {
  key: keyof BankLiquidityDailyPoint
  label: string
  color: string
  type?: 'line' | 'histogram'
  unit: string
  precision?: number
  priceScaleId?: 'left' | 'right'
  sourceDateKey?: keyof BankLiquidityDailyPoint
  availableAtKey?: keyof BankLiquidityDailyPoint
  sourceUrlKey?: keyof BankLiquidityDailyPoint
  sourceLabel?: string
}

const props = defineProps<{
  points: BankLiquidityDailyPoint[]
  series: BankLiquiditySeriesDefinition[]
  visibleStartDate?: string
  selectable?: boolean
  selectedKeys?: string[]
}>()

const emit = defineEmits<{
  'update:selectedKeys': [keys: string[]]
}>()

const containerRef = ref<HTMLElement | null>(null)
const hoverDate = ref('')
const hoverPoint = ref<BankLiquidityDailyPoint | null>(null)
let chart: IChartApi | null = null
let resizeObserver: ResizeObserver | null = null
let lineSeries: ISeriesApi<'Line', Time>[] = []
let histogramSeries: ISeriesApi<'Histogram', Time>[] = []

const availableSeriesKeys = computed(() => props.series.map((item) => String(item.key)))

const selectedSeriesKeys = computed(() => {
  if (!props.selectable) return availableSeriesKeys.value
  const requestedKeys = new Set(props.selectedKeys ?? [])
  const validKeys = availableSeriesKeys.value.filter((key) => requestedKeys.has(key))
  return validKeys.length ? validKeys : availableSeriesKeys.value
})

const selectedSeriesKeySet = computed(() => new Set(selectedSeriesKeys.value))

const displayedSeries = computed(() => (
  props.series.filter((item) => selectedSeriesKeySet.value.has(String(item.key)))
))

const selectedSourceSeries = computed(() => (
  displayedSeries.value.filter((definition) => definition.sourceDateKey)
))

function numericValue(point: BankLiquidityDailyPoint | null, key: keyof BankLiquidityDailyPoint) {
  const value = point?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function stringValue(point: BankLiquidityDailyPoint | null, key?: keyof BankLiquidityDailyPoint) {
  if (!key) return null
  const value = point?.[key]
  return typeof value === 'string' && value ? value : null
}

function formatValue(point: BankLiquidityDailyPoint | null, definition: BankLiquiditySeriesDefinition) {
  const value = numericValue(point, definition.key)
  return value == null ? '-' : `${value.toFixed(definition.precision ?? 2)}${definition.unit}`
}

function isSeriesSelected(definition: BankLiquiditySeriesDefinition) {
  return selectedSeriesKeySet.value.has(String(definition.key))
}

function toggleSeries(definition: BankLiquiditySeriesDefinition) {
  if (!props.selectable) return
  const key = String(definition.key)
  const currentKeys = selectedSeriesKeys.value
  if (currentKeys.includes(key) && currentKeys.length === 1) return
  const nextKeySet = new Set(currentKeys)
  if (nextKeySet.has(key)) nextKeySet.delete(key)
  else nextKeySet.add(key)
  emit(
    'update:selectedKeys',
    availableSeriesKeys.value.filter((availableKey) => nextKeySet.has(availableKey)),
  )
}

function applyVisibleRange() {
  if (!chart || !props.points.length) return
  const lastDate = props.points[props.points.length - 1]?.trade_date
  if (props.visibleStartDate && lastDate) {
    chart.timeScale().setVisibleRange({
      from: props.visibleStartDate as Time,
      to: lastDate as Time,
    })
  } else {
    chart.timeScale().fitContent()
  }
}

function updateHover(point?: BankLiquidityDailyPoint) {
  const current = point ?? props.points[props.points.length - 1] ?? null
  hoverPoint.value = current
  hoverDate.value = current?.trade_date ?? ''
}

function disposeChart() {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.remove()
  chart = null
  lineSeries = []
  histogramSeries = []
}

async function renderChart() {
  await nextTick()
  if (!containerRef.value) return
  disposeChart()
  chart = createChart(containerRef.value, {
    width: containerRef.value.clientWidth,
    height: 380,
    layout: { background: { color: '#ffffff' }, textColor: '#475569' },
    grid: {
      vertLines: { color: '#eef2f6' },
      horzLines: { color: '#e5eaf0' },
    },
    leftPriceScale: { visible: displayedSeries.value.some((item) => item.priceScaleId === 'left'), borderColor: '#dce3eb' },
    rightPriceScale: { borderColor: '#dce3eb' },
    timeScale: { borderColor: '#dce3eb', timeVisible: false },
    crosshair: {
      vertLine: { color: '#94a3b8', labelBackgroundColor: '#334155' },
      horzLine: { color: '#94a3b8', labelBackgroundColor: '#334155' },
    },
  })

  for (const definition of displayedSeries.value) {
    const priceFormat = {
      type: 'custom' as const,
      minMove: 10 ** -(definition.precision ?? 2),
      formatter: (value: number) => `${value.toFixed(definition.precision ?? 2)}${definition.unit}`,
    }
    if (definition.type === 'histogram') {
      const api = chart.addSeries(HistogramSeries, {
        color: definition.color,
        base: 0,
        priceLineVisible: false,
        lastValueVisible: false,
        priceScaleId: definition.priceScaleId ?? 'right',
        priceFormat,
      })
      api.setData(
        props.points.flatMap((point) => {
          const value = numericValue(point, definition.key)
          if (value == null) return []
          return [{
            time: point.trade_date as Time,
            value,
            color: value < 0 ? '#dc2626' : definition.color,
          }]
        }),
      )
      histogramSeries.push(api)
    } else {
      const api = chart.addSeries(LineSeries, {
        color: definition.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        priceScaleId: definition.priceScaleId ?? 'right',
        priceFormat,
      })
      api.setData(
        props.points.flatMap((point) => {
          const value = numericValue(point, definition.key)
          return value == null ? [] : [{ time: point.trade_date as Time, value }]
        }),
      )
      lineSeries.push(api)
    }
  }

  const pointByDate = new Map(props.points.map((point) => [point.trade_date, point]))
  chart.subscribeCrosshairMove((param) => {
    if (!param.time) {
      updateHover()
      return
    }
    updateHover(pointByDate.get(String(param.time)))
  })
  resizeObserver = new ResizeObserver(() => {
    if (containerRef.value && chart) chart.applyOptions({ width: containerRef.value.clientWidth })
  })
  resizeObserver.observe(containerRef.value)
  applyVisibleRange()
  updateHover()
}

watch(
  () => [props.points, props.series, props.selectedKeys],
  renderChart,
  { deep: true, immediate: true },
)
watch(() => props.visibleStartDate, applyVisibleRange)
onBeforeUnmount(disposeChart)
</script>

<template>
  <div class="liquidity-chart-shell">
    <div class="liquidity-chart-legend">
      <span class="liquidity-chart-date">{{ hoverDate || '暂无数据' }}</span>
      <template v-for="item in series" :key="String(item.key)">
        <label
          v-if="selectable"
          :class="[
            'liquidity-chart-legend-item',
            'liquidity-chart-legend-choice',
            { 'is-hidden': !isSeriesSelected(item), 'is-locked': isSeriesSelected(item) && selectedSeriesKeys.length === 1 },
          ]"
          :title="isSeriesSelected(item) && selectedSeriesKeys.length === 1 ? '至少保留一条曲线' : undefined"
        >
          <input
            type="checkbox"
            :checked="isSeriesSelected(item)"
            :disabled="isSeriesSelected(item) && selectedSeriesKeys.length === 1"
            :aria-label="`${isSeriesSelected(item) ? '隐藏' : '显示'}${item.label}曲线`"
            @change="toggleSeries(item)"
          >
          <i class="liquidity-chart-swatch" :style="{ backgroundColor: item.color }"></i>
          <span>{{ item.label }}</span>
          <strong>{{ formatValue(hoverPoint, item) }}</strong>
        </label>
        <span v-else class="liquidity-chart-legend-item">
          <i class="liquidity-chart-swatch" :style="{ backgroundColor: item.color }"></i>
          {{ item.label }}
          <strong>{{ formatValue(hoverPoint, item) }}</strong>
        </span>
      </template>
    </div>
    <div v-if="selectedSourceSeries.length" class="liquidity-source-line">
      <span
        v-for="item in selectedSourceSeries"
        :key="`${String(item.key)}-source`"
      >
        {{ item.sourceLabel || item.label }}：数据日 {{ stringValue(hoverPoint, item.sourceDateKey) || '-' }} · 发布 {{ stringValue(hoverPoint, item.availableAtKey) || '-' }}
        <a
          v-if="stringValue(hoverPoint, item.sourceUrlKey)"
          :href="stringValue(hoverPoint, item.sourceUrlKey) || undefined"
          target="_blank"
          rel="noreferrer"
        >官方来源</a>
      </span>
    </div>
    <div ref="containerRef" class="liquidity-chart"></div>
  </div>
</template>

<style scoped>
.liquidity-chart-shell { position: relative; min-width: 0; }
.liquidity-chart-legend { min-height: 38px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 0 4px 7px; color: #64748b; font-size: 12px; }
.liquidity-chart-date { color: #334155; font-weight: 800; }
.liquidity-chart-legend-item { display: inline-flex; align-items: center; gap: 5px; }
.liquidity-chart-legend-choice { cursor: pointer; transition: opacity .15s ease; user-select: none; }
.liquidity-chart-legend-choice.is-hidden { opacity: .5; }
.liquidity-chart-legend-choice.is-locked { cursor: not-allowed; }
.liquidity-chart-legend-choice input { width: 14px; height: 14px; margin: 0 1px 0 0; accent-color: #2563eb; }
.liquidity-chart-swatch { width: 9px; height: 9px; border-radius: 2px; flex: 0 0 auto; }
.liquidity-chart-legend-item strong { color: #172033; font-variant-numeric: tabular-nums; }
.liquidity-source-line { min-height: 22px; display: flex; gap: 14px; flex-wrap: wrap; padding: 0 4px 8px; color: #94a3b8; font-size: 11px; }
.liquidity-source-line a { margin-left: 4px; color: #2563eb; text-decoration: none; }
.liquidity-chart { width: 100%; height: 380px; }
</style>
