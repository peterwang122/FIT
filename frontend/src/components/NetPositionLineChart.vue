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

import type { NetPositionSeriesPoint } from '../types/stock'

const props = withDefaults(
  defineProps<{
    title: string
    points: NetPositionSeriesPoint[]
    loading?: boolean
    lineColor?: string
  }>(),
  {
    loading: false,
    lineColor: '#dc2626',
  },
)

const containerRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')

let chart: IChartApi | null = null
let series: ISeriesApi<'Line'> | null = null

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

function updateSeries() {
  if (!series) {
    return
  }
  series.applyOptions({
    color: props.lineColor,
  })
  series.setData(sortedPoints.value as (WhitespaceData<Time> | any)[])
  chart?.timeScale().fitContent()
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
  } catch (error) {
    renderError.value = `净空单折线图渲染失败：${String(error)}`
    console.error(error)
  }
}

watch(sortedPoints, () => {
  updateSeries()
})

watch(
  () => props.lineColor,
  () => {
    updateSeries()
  },
)

onMounted(() => {
  renderChart()
})

onBeforeUnmount(() => {
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
