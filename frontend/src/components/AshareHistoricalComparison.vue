<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createChart, LineSeries, LineStyle, type IChartApi, type ISeriesApi, type Time } from 'lightweight-charts'
import type { AshareOutlookHistory } from '../types/research'

const props = defineProps<{ comparison: AshareOutlookHistory['spring_2021'] }>()
const host = ref<HTMLDivElement | null>(null)
const selected = ref(props.comparison.paths.map(p => p.code))
const hoverDate = ref('')
const colors = ['#64748b', '#2563eb', '#dc2626', '#16a34a', '#9333ea', '#d97706']
let chart: IChartApi | null = null
let resize: ResizeObserver | null = null
const lines = new Map<string, ISeriesApi<'Line'>>()
const date = computed(() => hoverDate.value || props.comparison.end_date)
const value = (code: string) => props.comparison.paths.find(p => p.code === code)?.points.find(p => p.date === date.value)?.value

function toggle(code: string) {
  selected.value = selected.value.includes(code) ? selected.value.filter(c => c !== code) : [...selected.value, code]
}
function draw() {
  if (!chart) return
  for (const line of lines.values()) chart.removeSeries(line)
  lines.clear()
  props.comparison.paths.forEach((path, i) => {
    if (!selected.value.includes(path.code)) return
    const line = chart!.addSeries(LineSeries, { color: colors[i % colors.length], lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
    line.setData(path.points.map(p => ({ time: p.date as Time, value: p.value })))
    if (lines.size === 0) line.createPriceLine({ price: 100, color: '#94a3b8', lineStyle: LineStyle.Dashed, axisLabelVisible: false })
    lines.set(path.code, line)
  })
}
onMounted(() => {
  if (!host.value) return
  chart = createChart(host.value, { width: host.value.clientWidth, height: 270,
    layout: { background: { color: '#ffffff' }, textColor: '#64748b', fontSize: 11 },
    grid: { vertLines: { color: '#f1f5f9' }, horzLines: { color: '#f1f5f9' } },
    rightPriceScale: { borderColor: '#dbe3ec' }, timeScale: { borderColor: '#dbe3ec' } })
  chart.subscribeCrosshairMove(p => { hoverDate.value = typeof p.time === 'string' ? p.time : '' })
  draw()
  chart.timeScale().fitContent()
  resize = new ResizeObserver(() => { if (host.value && chart) chart.applyOptions({ width: host.value.clientWidth }) })
  resize.observe(host.value)
})
watch(selected, draw)
onBeforeUnmount(() => { resize?.disconnect(); chart?.remove() })
</script>

<template>
  <div class="historical-chart">
    <p class="chart-date">{{ date }} · 春节前收盘 = 100</p>
    <div class="historical-legend" role="group" aria-label="2021年对照曲线">
      <label v-for="(path, i) in comparison.paths" :key="path.code" :class="{ muted: !selected.includes(path.code) }">
        <input type="checkbox" :checked="selected.includes(path.code)" :disabled="selected.length === 1 && selected.includes(path.code)" @change="toggle(path.code)">
        <span class="swatch" :style="{ background: colors[i % colors.length] }"></span>{{ path.name }}
        <b>{{ value(path.code)?.toFixed(2) ?? '缺失' }}</b>
      </label>
    </div>
    <div ref="host" class="historical-canvas" aria-label="2021年茅台与五条宽基的春节后价格对照"></div>
    <p class="chart-note">{{ comparison.note }}</p>
  </div>
</template>

<style scoped>
.historical-chart { min-width: 0; margin: 18px 0 24px; }
.chart-date { color: #64748b; font-size: 12px; margin: 0 0 9px; }
.historical-legend { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 10px; font-size: 12px; }
.historical-legend label { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }
.historical-legend label.muted { opacity: .45; }
.historical-legend input { accent-color: #2563eb; margin: 0; }
.historical-legend b { font-variant-numeric: tabular-nums; font-weight: 500; min-width: 43px; }
.swatch { width: 12px; height: 3px; flex: 0 0 auto; }
.historical-canvas { width: 100%; height: 270px; overflow: hidden; }
.chart-note { color: #64748b; font-size: 11px; line-height: 1.8; }
</style>
