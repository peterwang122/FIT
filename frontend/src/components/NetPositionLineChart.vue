<script setup lang="ts">
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
  type Time,
  type WhitespaceData,
} from 'lightweight-charts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { NetPositionSeriesPoint } from '../types/stock'

const HISTORY_REQUEST_THRESHOLD = 15

const props = withDefaults(
  defineProps<{
    title: string
    points: NetPositionSeriesPoint[]
    loading?: boolean
    lineColor?: string
    defaultVisibleDays?: number
    hasMoreHistory?: boolean
    loadingMoreHistory?: boolean
  }>(),
  {
    loading: false,
    lineColor: '#dc2626',
    hasMoreHistory: false,
    loadingMoreHistory: false,
    defaultVisibleDays: 180,
  },
)

const emit = defineEmits<{
  requestMoreHistory: [earliestTradeDate: string]
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')

let chart: IChartApi | null = null
let series: ISeriesApi<'Line'> | null = null
let shouldResetVisibleRange = true
let lastRequestedHistoryBoundary: string | null = null
let visibleRangeUnsubscribe: (() => void) | null = null

function parseDateText(value: string): number {
  return new Date(`${value}T00:00:00`).getTime()
}

function formatDateText(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const sortedPoints = computed(() =>
  [...props.points]
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date))
    .map((item) => ({
      time: item.trade_date as Time,
      value: Number(item.net_position),
    }))
    .filter((item) => Number.isFinite(item.value)),
)

function buildSeries(targetChart: IChartApi): ISeriesApi<'Line'> {
  const anyChart = targetChart as any
  if (typeof anyChart.addLineSeries === 'function') {
    return anyChart.addLineSeries({
      color: props.lineColor,
      lineWidth: 2,
      crosshairMarkerRadius: 4,
      priceLineVisible: true,
      lastValueVisible: true,
    })
  }

  return anyChart.addSeries(LineSeries, {
    color: props.lineColor,
    lineWidth: 2,
    crosshairMarkerRadius: 4,
    priceLineVisible: true,
    lastValueVisible: true,
  })
}

function applyVisibleRange() {
  if (!chart) return

  if (!props.defaultVisibleDays || sortedPoints.value.length === 0) {
    chart.timeScale().fitContent()
    return
  }

  const lastItem = sortedPoints.value[sortedPoints.value.length - 1]
  const lastDate = new Date(parseDateText(String(lastItem.time)))
  if (Number.isNaN(lastDate.getTime())) {
    chart.timeScale().fitContent()
    return
  }

  const startDate = new Date(lastDate)
  startDate.setDate(startDate.getDate() - props.defaultVisibleDays + 1)
  chart.timeScale().setVisibleRange({
    from: formatDateText(startDate) as Time,
    to: lastItem.time,
  })
}

function updateSeries() {
  if (!series) {
    return
  }

  series.applyOptions({
    color: props.lineColor,
  })
  series.setData(sortedPoints.value as (WhitespaceData<Time> | any)[])

  if (shouldResetVisibleRange) {
    applyVisibleRange()
    shouldResetVisibleRange = false
  }
}

function maybeRequestMoreHistory(range: LogicalRange | null) {
  if (!range || !props.hasMoreHistory || props.loadingMoreHistory || !sortedPoints.value.length) {
    return
  }

  if (range.from > HISTORY_REQUEST_THRESHOLD) {
    return
  }

  const earliestTradeDate = String(sortedPoints.value[0]?.time ?? '')
  if (!earliestTradeDate || lastRequestedHistoryBoundary === earliestTradeDate) {
    return
  }

  lastRequestedHistoryBoundary = earliestTradeDate
  emit('requestMoreHistory', earliestTradeDate)
}

function renderChart() {
  if (!containerRef.value) {
    return
  }

  try {
    renderError.value = ''
    chart = createChart(containerRef.value, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#14213d',
      },
      rightPriceScale: {
        borderColor: '#e2e8f0',
      },
      timeScale: {
        borderColor: '#e2e8f0',
        timeVisible: true,
      },
      grid: {
        vertLines: { color: '#f8fafc' },
        horzLines: { color: '#eef2f7' },
      },
      localization: {
        locale: 'zh-CN',
      },
      crosshair: {
        vertLine: {
          color: '#94a3b8',
        },
        horzLine: {
          color: '#94a3b8',
        },
      },
    })

    series = buildSeries(chart)
    updateSeries()

    const visibleRangeHandler = (range: LogicalRange | null) => maybeRequestMoreHistory(range)
    chart.timeScale().subscribeVisibleLogicalRangeChange(visibleRangeHandler)
    visibleRangeUnsubscribe = () => chart?.timeScale().unsubscribeVisibleLogicalRangeChange(visibleRangeHandler)
  } catch (error) {
    renderError.value = `净空单折线图渲染失败：${String(error)}`
    console.error(error)
  }
}

watch(
  sortedPoints,
  (next, previous) => {
    if (!series || !chart) return

    const previousEarliest = String(previous[0]?.time ?? '')
    const previousLatest = String(previous[previous.length - 1]?.time ?? '')
    const previousVisibleRange = chart.timeScale().getVisibleLogicalRange()
    series.setData(next as (WhitespaceData<Time> | any)[])

    const nextLatest = String(next[next.length - 1]?.time ?? '')
    if (shouldResetVisibleRange) {
      applyVisibleRange()
      shouldResetVisibleRange = false
      return
    }

    const nextEarliest = String(next[0]?.time ?? '')
    const prependedBars =
      previousVisibleRange && previousEarliest && nextEarliest && nextEarliest < previousEarliest
        ? next.filter((item) => String(item.time) < previousEarliest).length
        : 0

    const appendedNewerData = Boolean(previousLatest && nextLatest && nextLatest > previousLatest)
    if (appendedNewerData && prependedBars === 0) {
      applyVisibleRange()
      return
    }

    if (previousVisibleRange && prependedBars > 0) {
      chart.timeScale().setVisibleLogicalRange({
        from: previousVisibleRange.from + prependedBars,
        to: previousVisibleRange.to + prependedBars,
      })
    }
  },
  { deep: false },
)

watch(
  () => props.lineColor,
  () => {
    updateSeries()
  },
)

watch(
  () => props.points[0]?.trade_date ?? null,
  (nextEarliest, previousEarliest) => {
    if (nextEarliest && nextEarliest !== previousEarliest) {
      lastRequestedHistoryBoundary = null
    }
  },
)

watch(
  () => props.title,
  () => {
    shouldResetVisibleRange = true
    lastRequestedHistoryBoundary = null
  },
)

onMounted(() => {
  renderChart()
})

onBeforeUnmount(() => {
  visibleRangeUnsubscribe?.()
  visibleRangeUnsubscribe = null
  chart?.remove()
  chart = null
  series = null
})
</script>

<template>
  <section class="net-line-panel">
    <div class="net-line-head">
      <h3>{{ title }}</h3>
    </div>

    <p v-if="loading" class="muted">净空单折线图加载中...</p>
    <p v-else-if="loadingMoreHistory" class="muted">正在加载更早的中金所净持仓历史...</p>
    <p v-else-if="renderError" class="error">{{ renderError }}</p>
    <p v-else-if="!points.length" class="muted">当前没有可展示的净空单历史数据。</p>

    <div ref="containerRef" class="net-line-chart"></div>
  </section>
</template>

<style scoped>
.net-line-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  min-height: 0;
  padding: 12px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
}

.net-line-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.net-line-head h3 {
  margin: 0;
  font-size: 16px;
}

.net-line-chart {
  width: 100%;
  min-height: 270px;
  flex: 1;
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
  .net-line-head {
    flex-direction: column;
  }
}
</style>
