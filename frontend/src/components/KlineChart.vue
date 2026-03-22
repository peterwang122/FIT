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

import type { KlineCandle } from '../types/stock'

const props = defineProps<{
  candles: KlineCandle[]
  symbolName: string
  symbolCode: string
  height?: number | string
  defaultVisibleDays?: number
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const tooltipRef = ref<HTMLDivElement | null>(null)
const renderError = ref('')

let chart: IChartApi | null = null
let candleSeries: ISeriesApi<'Candlestick'> | null = null

function parseDateText(value: string): number {
  return new Date(`${value}T00:00:00`).getTime()
}

function formatDateText(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const klineData = computed(() =>
  [...props.candles]
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date))
    .map((item) => ({
      time: item.trade_date as Time,
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
    }))
    .filter(
      (item) =>
        Number.isFinite(item.open) &&
        Number.isFinite(item.high) &&
        Number.isFinite(item.low) &&
        Number.isFinite(item.close),
    ),
)

const dataMap = computed(() => {
  const result = new Map<string, KlineCandle>()
  for (const item of props.candles) result.set(item.trade_date, item)
  return result
})

const hasFixedHeight = computed(() => typeof props.height === 'number')

const shellStyle = computed(() => {
  if (!hasFixedHeight.value) return undefined
  const value = `${props.height}px`
  return { height: value, minHeight: value }
})

function applyVisibleRange() {
  if (!chart) return

  if (!props.defaultVisibleDays || klineData.value.length === 0) {
    chart.timeScale().fitContent()
    return
  }

  const lastItem = klineData.value[klineData.value.length - 1]
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

const containerStyle = computed(() => {
  if (!hasFixedHeight.value) return undefined
  const value = `${props.height}px`
  return { height: value, minHeight: value }
})

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

function bindCrosshairTooltip() {
  if (!chart || !tooltipRef.value || !containerRef.value) return

  chart.subscribeCrosshairMove((param: any) => {
    if (!param?.time || !param?.point) {
      tooltipRef.value!.style.display = 'none'
      return
    }

    const key = String(param.time)
    const row = dataMap.value.get(key)
    if (!row) {
      tooltipRef.value!.style.display = 'none'
      return
    }

    tooltipRef.value!.style.display = 'block'
    tooltipRef.value!.style.left = `${Math.min(param.point.x + 16, containerRef.value!.clientWidth - 220)}px`
    tooltipRef.value!.style.top = `${Math.max(param.point.y - 10, 10)}px`
    tooltipRef.value!.innerHTML = `
      <div><b>${props.symbolName} (${props.symbolCode})</b></div>
      <div>日期: ${row.trade_date}</div>
      <div>开: ${row.open} 高: ${row.high} 低: ${row.low} 收: ${row.close}</div>
      <div>涨跌幅: ${row.pct_chg}% 成交量: ${row.vol}</div>
      <div>PE: ${row.pe_ttm} PB: ${row.pb}</div>
      <div>总市值: ${row.total_market_value}</div>
      <div>流通市值: ${row.circulating_market_value}</div>
    `
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
    applyVisibleRange()
    bindCrosshairTooltip()
  } catch (error) {
    renderError.value = `K 线渲染失败：${String(error)}`
    console.error(error)
  }
}

watch(klineData, (next) => {
  if (!candleSeries) return
  candleSeries.setData(next as (WhitespaceData<Time> | any)[])
  applyVisibleRange()
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
  <div class="kline-shell" :class="{ 'has-explicit-height': hasFixedHeight }" :style="shellStyle">
    <p v-if="candles.length === 0" class="muted">当前没有查到 K 线数据，请检查代码和数据表内容。</p>
    <p v-if="renderError" class="error">{{ renderError }}</p>
    <div ref="containerRef" class="kline-container" :style="containerStyle">
      <div ref="tooltipRef" class="kline-tooltip"></div>
    </div>
  </div>
</template>

<style scoped>
.kline-shell {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}

.kline-shell.has-explicit-height {
  flex: 0 0 auto;
}

.kline-container {
  position: relative;
  width: 100%;
  min-height: 220px;
  flex: 1;
}

.kline-shell.has-explicit-height .kline-container {
  flex: 0 0 auto;
}

.kline-tooltip {
  position: absolute;
  z-index: 10;
  min-width: 220px;
  max-width: 280px;
  padding: 8px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.96);
  font-size: 12px;
  line-height: 1.5;
  display: none;
  pointer-events: none;
}

.muted {
  color: #64748b;
  font-size: 13px;
}

.error {
  color: #dc2626;
  font-size: 13px;
}
</style>
