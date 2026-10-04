<script setup lang="ts">
import { CandlestickSeries, ColorType, createChart, LineSeries, LineStyle, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AshareOutlookIndex, AshareOutlookCandle } from '../types/research'

const props = defineProps<{ index: AshareOutlookIndex }>()
const host = ref<HTMLDivElement | null>(null)
const hovered = ref<AshareOutlookCandle | null>(null)
const showMA60 = ref(true)
const showMA250 = ref(true)
const showAnchor = ref(true)
let chart: IChartApi | null = null
let candles: ISeriesApi<'Candlestick'> | null = null
let ma60: ISeriesApi<'Line'> | null = null
let ma250: ISeriesApi<'Line'> | null = null
let anchor: ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']> | null = null
const current = computed(() => hovered.value ?? props.index.candles[props.index.candles.length - 1])
const format = (value: number | null | undefined) => value == null ? '-' : value.toFixed(2)

function dateKey(time: Time) {
  if (typeof time === 'string') return time
  if (typeof time === 'number') return new Date(time * 1000).toISOString().slice(0, 10)
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`
}

function update() {
  if (!chart || !candles || !ma60 || !ma250) return
  hovered.value = null
  candles.setData(props.index.candles.map(c => ({ time: c.date as Time, open: c.open, high: c.high, low: c.low, close: c.close })))
  ma60.setData(props.index.candles.filter(c => c.ma60 != null).map(c => ({ time: c.date as Time, value: c.ma60! })))
  ma250.setData(props.index.candles.filter(c => c.ma250 != null).map(c => ({ time: c.date as Time, value: c.ma250! })))
  if (anchor) candles.removePriceLine(anchor)
  const july = props.index.anchors.find(a => a.label.startsWith('2026年7月'))
  anchor = july ? candles.createPriceLine({ price: july.value, color: '#d97706', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: props.index.close < july.value ? '7月低点已失守' : '7月低点' }) : null
  visibility()
  chart.timeScale().fitContent()
}

function visibility() {
  ma60?.applyOptions({ visible: showMA60.value })
  ma250?.applyOptions({ visible: showMA250.value })
  anchor?.applyOptions({ lineVisible: showAnchor.value, axisLabelVisible: showAnchor.value })
}

onMounted(() => {
  if (!host.value) return
  chart = createChart(host.value, { autoSize: true, height: 360,
    layout: { background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#475569' },
    grid: { vertLines: { color: '#eef2f7' }, horzLines: { color: '#eef2f7' } },
    timeScale: { borderColor: '#dbe3ec', rightOffset: 3 }, rightPriceScale: { borderColor: '#dbe3ec' },
  })
  candles = chart.addSeries(CandlestickSeries, { upColor: '#ef4444', downColor: '#10b981', wickUpColor: '#ef4444', wickDownColor: '#10b981', borderVisible: false, priceLineVisible: false })
  ma60 = chart.addSeries(LineSeries, { color: '#2563eb', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
  ma250 = chart.addSeries(LineSeries, { color: '#64748b', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
  chart.subscribeCrosshairMove(param => {
    hovered.value = param.time ? props.index.candles.find(c => c.date === dateKey(param.time!)) ?? null : null
  })
  update()
})
watch(() => props.index, update)
watch([showMA60, showMA250, showAnchor], visibility)
onBeforeUnmount(() => { chart?.remove(); chart = null })
</script>

<template>
  <div class="outlook-chart">
    <div class="chart-legend">
      <span>{{ current?.date }} · 收 {{ format(current?.close) }}</span>
      <label><input v-model="showMA60" type="checkbox" /><i class="blue"></i>MA60 {{ format(current?.ma60) }}</label>
      <label><input v-model="showMA250" type="checkbox" /><i class="gray"></i>MA250 {{ format(current?.ma250) }}</label>
      <label><input v-model="showAnchor" type="checkbox" /><i class="amber"></i>7月低点</label>
    </div>
    <div ref="host" class="chart-canvas"></div>
  </div>
</template>

<style scoped>
.outlook-chart { width: 100%; min-width: 0; }
.chart-canvas { height: 360px; width: 100%; }
.chart-legend { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 18px; min-height: 36px; margin-bottom: 8px; color: #475569; font-size: 12px; font-variant-numeric: tabular-nums; }
label { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }
input { accent-color: #2563eb; }
i { width: 12px; height: 3px; display: inline-block; }
.blue { background: #2563eb; } .gray { background: #64748b; } .amber { background: #d97706; }
</style>
