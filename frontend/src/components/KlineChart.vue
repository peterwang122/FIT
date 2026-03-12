<script setup lang="ts">
import { createChart, ColorType, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { StockCandle } from '../types/stock'

const props = defineProps<{ candles: StockCandle[] }>()

const containerRef = ref<HTMLDivElement | null>(null)
let chart: ReturnType<typeof createChart> | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null

const klineData = computed(() =>
  props.candles.map((item) => ({
    time: Math.floor(new Date(item.trade_date).getTime() / 1000) as UTCTimestamp,
    open: Number(item.open),
    high: Number(item.high),
    low: Number(item.low),
    close: Number(item.close),
  })),
)

function renderChart() {
  if (!containerRef.value) return

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

  candleSeries = (chart as any).addCandlestickSeries({
    upColor: '#ef4444',
    downColor: '#10b981',
    borderVisible: false,
    wickUpColor: '#ef4444',
    wickDownColor: '#10b981',
  })

  if (candleSeries) candleSeries.setData(klineData.value)
}

watch(klineData, (next) => {
  if (!candleSeries) return
  candleSeries.setData(next)
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
</style>
