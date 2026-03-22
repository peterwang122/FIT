<script setup lang="ts">
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type WhitespaceData,
} from 'lightweight-charts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { IndexEmotionPoint } from '../types/stock'

const SERIES_CONFIG = [
  { name: '上证50', color: '#2563eb' },
  { name: '沪深300', color: '#ef4444' },
  { name: '中证500', color: '#10b981' },
  { name: '中证1000', color: '#f59e0b' },
] as const

const props = defineProps<{
  points: IndexEmotionPoint[]
  loading?: boolean
  height?: number | string
  defaultVisibleDays?: number
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')

let chart: IChartApi | null = null
const seriesMap = new Map<string, ISeriesApi<'Line'>>()

const panelStyle = computed(() => {
  if (props.height === undefined) return undefined
  return { height: typeof props.height === 'number' ? `${props.height}px` : props.height }
})

function parseDateText(value: string): number {
  return new Date(`${value}T00:00:00`).getTime()
}

function formatDateText(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const groupedSeries = computed(() =>
  SERIES_CONFIG.map((series) => {
    const points = [...props.points]
      .filter((item) => item.index_name === series.name)
      .sort((left, right) => left.emotion_date.localeCompare(right.emotion_date))
      .map((item) => ({
        time: item.emotion_date as Time,
        value: Number(item.emotion_value),
        rawDate: item.emotion_date,
      }))
      .filter((item) => Number.isFinite(item.value))

    return {
      ...series,
      points,
      latest: points.length ? points[points.length - 1] : null,
    }
  }),
)

const latestDate = computed(() => {
  const dates = groupedSeries.value
    .map((item) => item.latest?.rawDate ?? '')
    .filter((item) => Boolean(item))
    .sort()
  return dates.length ? dates[dates.length - 1] : ''
})

function applyVisibleRange() {
  if (!chart) return

  const allDates = groupedSeries.value
    .flatMap((item) => item.points.map((point) => point.rawDate))
    .filter((item) => Boolean(item))
    .sort()

  if (!props.defaultVisibleDays || allDates.length === 0) {
    chart.timeScale().fitContent()
    return
  }

  const lastDate = new Date(parseDateText(allDates[allDates.length - 1]))
  if (Number.isNaN(lastDate.getTime())) {
    chart.timeScale().fitContent()
    return
  }

  const startDate = new Date(lastDate)
  startDate.setDate(startDate.getDate() - props.defaultVisibleDays + 1)
  chart.timeScale().setVisibleRange({
    from: formatDateText(startDate) as Time,
    to: allDates[allDates.length - 1] as Time,
  })
}

function buildSeries(targetChart: IChartApi, color: string): ISeriesApi<'Line'> {
  const anyChart = targetChart as any
  if (typeof anyChart.addLineSeries === 'function') {
    return anyChart.addLineSeries({
      color,
      lineWidth: 2,
      crosshairMarkerRadius: 4,
      lastValueVisible: false,
      priceLineVisible: false,
    })
  }

  return anyChart.addSeries(LineSeries, {
    color,
    lineWidth: 2,
    crosshairMarkerRadius: 4,
    lastValueVisible: false,
    priceLineVisible: false,
  })
}

function updateSeries() {
  if (!chart) return

  for (const item of groupedSeries.value) {
    let series = seriesMap.get(item.name)
    if (!series) {
      series = buildSeries(chart, item.color)
      seriesMap.set(item.name, series)
    }
    series.setData(item.points as (WhitespaceData<Time> | any)[])
  }

  applyVisibleRange()
}

function renderChart() {
  if (!containerRef.value) return

  try {
    renderError.value = ''
    chart = createChart(containerRef.value, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#111827',
      },
      rightPriceScale: {
        borderColor: '#e5e7eb',
      },
      timeScale: {
        borderColor: '#e5e7eb',
        timeVisible: true,
      },
      grid: {
        vertLines: { color: '#f8fafc' },
        horzLines: { color: '#f1f5f9' },
      },
      localization: {
        locale: 'zh-CN',
      },
    })

    updateSeries()
  } catch (error) {
    renderError.value = `指数情绪图渲染失败：${String(error)}`
    console.error(error)
  }
}

watch(groupedSeries, () => {
  updateSeries()
})

onMounted(() => {
  renderChart()
})

onBeforeUnmount(() => {
  chart?.remove()
  chart = null
  seriesMap.clear()
})
</script>

<template>
  <section class="card emotion-panel" :style="panelStyle">
    <div class="emotion-head">
      <h3>指数情绪指标</h3>
      <div v-if="latestDate" class="emotion-date">最新日期：{{ latestDate }}</div>
    </div>

    <p v-if="loading" class="muted">指数情绪图加载中...</p>
    <p v-if="renderError" class="error">{{ renderError }}</p>
    <p v-if="!loading && points.length === 0" class="muted">当前没有可展示的指数情绪数据。</p>

    <div class="emotion-layout">
      <div ref="containerRef" class="emotion-chart"></div>

      <div class="emotion-legend">
        <div v-for="item in groupedSeries" :key="item.name" class="emotion-legend-item">
          <div class="emotion-legend-name" :style="{ color: item.color }">{{ item.name }}</div>
          <div class="emotion-legend-value">{{ item.latest ? item.latest.value.toFixed(2) : '--' }}</div>
          <div class="emotion-legend-date">{{ item.latest?.rawDate ?? '--' }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.emotion-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.emotion-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.emotion-head h3 {
  margin: 0;
  font-size: 22px;
}

.emotion-date {
  color: #475569;
  font-size: 13px;
  white-space: nowrap;
}

.emotion-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 200px;
  gap: 14px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.emotion-chart {
  width: 100%;
  min-height: 220px;
}

.emotion-legend {
  display: grid;
  gap: 8px;
  align-content: start;
}

.emotion-legend-item {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
  background: #f8fafc;
}

.emotion-legend-name {
  font-size: 13px;
  font-weight: 700;
}

.emotion-legend-value {
  margin-top: 4px;
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
}

.emotion-legend-date {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
}

.muted {
  color: #64748b;
  font-size: 13px;
}

.error {
  color: #dc2626;
  font-size: 13px;
}

@media (max-width: 1024px) {
  .emotion-layout {
    grid-template-columns: 1fr;
  }

  .emotion-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .emotion-chart {
    min-height: 280px;
  }
}
</style>
