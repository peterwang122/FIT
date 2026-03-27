<script setup lang="ts">
import { ColorType, LineSeries, createChart, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { QuantEquityCurvePoint } from '../types/quant'

const props = withDefaults(
  defineProps<{
    points: QuantEquityCurvePoint[]
    loading?: boolean
  }>(),
  {
    loading: false,
  },
)

const containerRef = ref<HTMLDivElement | null>(null)
let chart: IChartApi | null = null
let navSeries: ISeriesApi<'Line', Time> | null = null
let benchmarkSeries: ISeriesApi<'Line', Time> | null = null

const navData = computed(() =>
  props.points
    .filter((item) => Number.isFinite(item.nav))
    .map((item) => ({
      time: item.trade_date as Time,
      value: item.nav,
    })),
)

const benchmarkData = computed(() =>
  props.points
    .filter((item) => item.benchmark_nav !== null && Number.isFinite(item.benchmark_nav))
    .map((item) => ({
      time: item.trade_date as Time,
      value: item.benchmark_nav as number,
    })),
)

function renderChart() {
  if (!containerRef.value) return
  chart = createChart(containerRef.value, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: '#ffffff' },
      textColor: '#14213d',
    },
    rightPriceScale: {
      borderColor: '#e2e8f0',
      autoScale: true,
    },
    timeScale: {
      borderColor: '#e2e8f0',
      timeVisible: true,
    },
    grid: {
      vertLines: { color: '#f3f4f6' },
      horzLines: { color: '#eef2f7' },
    },
    localization: {
      locale: 'zh-CN',
    },
  })
  navSeries = chart.addSeries(LineSeries, {
    color: '#0f4c75',
    lineWidth: 2,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  benchmarkSeries = chart.addSeries(LineSeries, {
    color: '#f97316',
    lineWidth: 2,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  updateSeries()
}

function updateSeries() {
  navSeries?.setData(navData.value)
  benchmarkSeries?.setData(benchmarkData.value)
  chart?.timeScale().fitContent()
}

watch([navData, benchmarkData], updateSeries)

onMounted(renderChart)

onBeforeUnmount(() => {
  chart?.remove()
  chart = null
  navSeries = null
  benchmarkSeries = null
})
</script>

<template>
  <section class="strategy-curve-chart">
    <p v-if="loading" class="muted">收益曲线加载中...</p>
    <p v-else-if="!points.length" class="muted">当前策略暂无可展示的收益曲线。</p>
    <div ref="containerRef" class="strategy-curve-canvas"></div>
  </section>
</template>

<style scoped>
.strategy-curve-chart {
  display: grid;
  gap: 10px;
}

.strategy-curve-canvas {
  min-height: 360px;
  height: 360px;
  width: 100%;
}

.muted {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}
</style>
