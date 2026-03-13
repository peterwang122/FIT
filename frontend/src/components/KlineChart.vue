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

const props = defineProps<{ candles: StockCandle[]; symbolName: string; symbolCode: string }>()

const containerRef = ref<HTMLDivElement | null>(null)
const tooltipRef = ref<HTMLDivElement | null>(null)
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

const dataMap = computed(() => {
  const result = new Map<string, StockCandle>()
  for (const item of props.candles) result.set(item.trade_date, item)
  return result
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
    chart.timeScale().fitContent()
    bindCrosshairTooltip()
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
    <div class="chart-head">{{ symbolName }}（{{ symbolCode }}）</div>
    <p v-if="candles.length === 0" class="muted">当前没有查到K线数据，请检查股票代码与数据库字段映射配置。</p>
    <p v-if="renderError" class="error">{{ renderError }}</p>
    <div ref="containerRef" class="kline-container">
      <div ref="tooltipRef" class="kline-tooltip"></div>
    </div>
  </div>
</template>

<style scoped>
.chart-head {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 8px;
}

.kline-container {
  position: relative;
  width: 100%;
  height: 520px;
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
  margin-bottom: 8px;
}

.error {
  color: #dc2626;
  font-size: 13px;
  margin-bottom: 8px;
}
</style>
