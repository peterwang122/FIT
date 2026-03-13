<script setup lang="ts">
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type WhitespaceData,
} from 'lightweight-charts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { StockCandle } from '../types/stock'

const props = defineProps<{ candles: StockCandle[] }>()

const containerRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')

let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null

const klineData = computed(() =>
  props.candles
    .map((item) => ({
      time: item.trade_date as Time,
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
    }))
    .filter((item) => Number.isFinite(item.open) && Number.isFinite(item.high) && Number.isFinite(item.low) && Number.isFinite(item.close)),
)

function buildSeries(targetChart: IChartApi): ISeriesApi<'Candlestick'> {
  const anyChart = targetChart as any
  if (typeof anyChart.addCandlestickSeries === 'function') {
    return anyChart.addCandlestickSeries({
      upColor: '#ef4444',
      downColor: '#10b981',
      borderVisible: false,
      wickUpColor: '#ef4444',
      wickDownColor: '#10b981',
    })
  }

  return anyChart.addSeries(CandlestickSeries, {
    upColor: '#ef4444',
    downColor: '#10b981',
    borderVisible: false,
    wickUpColor: '#ef4444',
    wickDownColor: '#10b981',
  })
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
        vertLines: { color: '#f3f4f6' },
        horzLines: { color: '#f3f4f6' },
      },
      localization: {
        locale: 'zh-CN',
      },
    })

    candleSeries = buildSeries(chart)
    candleSeries.setData(klineData.value as (WhitespaceData<Time> | any)[])
    chart.timeScale().fitContent()
  } catch (error) {
    renderError.value = `K线渲染失败：${String(error)}`
    console.error(error)
  }
}

watch(klineData, (next) => {
  if (!candleSeries) return
  candleSeries.setData(next as (WhitespaceData<Time> | any)[])
  chart?.timeScale().fitContent()
})

onMounted(() => {
  renderChart()
})

onBeforeUnmount(() => {
  chart?.remove()
  chart = null
  candleSeries = null
})
</script>

<template>
  <div class="card">
    <h3>股票日K线图（Lightweight Charts）</h3>
    <p v-if="candles.length === 0" class="muted">当前没有查到K线数据，请检查股票代码与数据库字段映射配置。</p>
    <p v-if="renderError" class="error">{{ renderError }}</p>
    <div ref="containerRef" class="kline-container" />
  </div>
</template>

<style scoped>
.kline-container {
  width: 100%;
  height: 520px;
}

.muted {
  color: #64748b;
  font-size: 13px;
  margin-bottom: 8px;
}

.error {
  color: #dc2626;
  font-size: 13px;
  margin-bottom: 8px;
}
</style>
