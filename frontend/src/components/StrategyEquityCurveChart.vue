<script setup lang="ts">
import {
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LogicalRange,
  type MouseEventParams,
  type Time,
} from 'lightweight-charts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { QuantEquityCurvePoint } from '../types/quant'

type PanelKey = 'nav' | 'position'
type PositionBucket = 'flat' | 'light' | 'medium' | 'heavy' | 'full'
type SummaryItem = { label: string; value: string }

const POSITION_BUCKET_COLORS: Record<PositionBucket, string> = {
  flat: '#cbd5e1',
  light: '#bfdbfe',
  medium: '#60a5fa',
  heavy: '#2563eb',
  full: '#1d4ed8',
}

const POSITION_BUCKET_LABELS: Record<PositionBucket, string> = {
  flat: '空仓',
  light: '轻仓(0-25%)',
  medium: '半仓(25-50%)',
  heavy: '重仓(50-75%)',
  full: '满仓区(75-100%)',
}

const SIGNAL_LABELS: Record<string, string> = {
  blue: '蓝色信号',
  red: '红色信号',
  purple: '紫色信号',
}

const props = withDefaults(
  defineProps<{
    points: QuantEquityCurvePoint[]
    loading?: boolean
  }>(),
  {
    loading: false,
  },
)

const navContainerRef = ref<HTMLDivElement | null>(null)
const positionContainerRef = ref<HTMLDivElement | null>(null)
const activeTradeDate = ref<string | null>(null)

const charts: Partial<Record<PanelKey, IChartApi>> = {}
const primarySeriesMap = new Map<PanelKey, ISeriesApi<'Line' | 'Histogram', Time>>()
const panelValueMaps = new Map<PanelKey, Map<string, number>>()
let navSeries: ISeriesApi<'Line', Time> | null = null
let benchmarkSeries: ISeriesApi<'Line', Time> | null = null
let positionSeries: ISeriesApi<'Histogram', Time> | null = null
let unsubs: Array<() => void> = []
let isSyncingRange = false
let isSyncingCrosshair = false

function disposeCharts() {
  unsubs.forEach((stop) => stop())
  unsubs = []
  charts.nav?.remove()
  charts.position?.remove()
  delete charts.nav
  delete charts.position
  navSeries = null
  benchmarkSeries = null
  positionSeries = null
  primarySeriesMap.clear()
  panelValueMaps.clear()
}

function normalizeBucket(bucket: QuantEquityCurvePoint['position_bucket'], positionPct: number): PositionBucket {
  if (bucket === 'flat' || bucket === 'light' || bucket === 'medium' || bucket === 'heavy' || bucket === 'full') {
    return bucket
  }
  if (positionPct <= 0) return 'flat'
  if (positionPct <= 0.25) return 'light'
  if (positionPct <= 0.5) return 'medium'
  if (positionPct <= 0.75) return 'heavy'
  return 'full'
}

function clampPositionPct(value: number | null | undefined) {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, Number(value)))
}

function formatNumber(value: number | null | undefined, digits = 4) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return Number(value).toFixed(digits)
}

function formatPercent(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

const lastPoint = computed(() => (props.points.length ? props.points[props.points.length - 1] : null))

const pointMap = computed(() => new Map(props.points.map((item) => [item.trade_date, item])))

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

const positionData = computed<HistogramData<Time>[]>(() =>
  props.points.map((item) => {
    const positionPct = clampPositionPct(item.position_pct)
    const bucket = normalizeBucket(item.position_bucket, positionPct)
    return {
      time: item.trade_date as Time,
      value: Number((positionPct * 100).toFixed(4)),
      color: POSITION_BUCKET_COLORS[bucket],
    }
  }),
)

const activePoint = computed(() => {
  const tradeDate = activeTradeDate.value ?? lastPoint.value?.trade_date ?? null
  return tradeDate ? pointMap.value.get(tradeDate) ?? lastPoint.value : lastPoint.value
})

const activePositionBucket = computed<PositionBucket>(() => {
  const point = activePoint.value
  return normalizeBucket(point?.position_bucket ?? null, clampPositionPct(point?.position_pct))
})

const summaryItems = computed<SummaryItem[]>(() => {
  const point = activePoint.value
  return [
    { label: '日期', value: point?.trade_date ?? '-' },
    { label: '策略净值', value: formatNumber(point?.nav, 4) },
    { label: '基准净值', value: point?.benchmark_nav === null ? '-' : formatNumber(point?.benchmark_nav, 4) },
    { label: '仓位', value: formatPercent(point?.position_pct, 2) },
    { label: '仓位档位', value: POSITION_BUCKET_LABELS[activePositionBucket.value] },
    { label: '信号', value: point?.signal ? SIGNAL_LABELS[point.signal] ?? point.signal : '-' },
  ]
})

function buildLineValueMap(data: Array<{ time: Time; value: number }>) {
  return new Map(data.map((item) => [String(item.time), item.value]))
}

function buildHistogramValueMap(data: HistogramData<Time>[]) {
  return new Map(
    data
      .filter((item) => item.value !== undefined)
      .map((item) => [String(item.time), Number(item.value)]),
  )
}

function createBaseChart(container: HTMLDivElement, options?: { hideTimeScale?: boolean }) {
  return createChart(container, {
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
      visible: !options?.hideTimeScale,
      ticksVisible: !options?.hideTimeScale,
    },
    grid: {
      vertLines: { color: '#f3f4f6' },
      horzLines: { color: '#eef2f7' },
    },
    localization: {
      locale: 'zh-CN',
    },
    crosshair: {
      vertLine: {
        color: '#94a3b8',
        width: 1,
        labelBackgroundColor: '#1d4ed8',
      },
      horzLine: {
        color: '#94a3b8',
        width: 1,
        labelBackgroundColor: '#1d4ed8',
      },
    },
  })
}

function syncVisibleRange(sourceKey: PanelKey, range: LogicalRange | null) {
  if (!range || isSyncingRange) return
  isSyncingRange = true
  try {
    ;(['nav', 'position'] as PanelKey[]).forEach((panelKey) => {
      if (panelKey !== sourceKey) {
        charts[panelKey]?.timeScale().setVisibleLogicalRange(range)
      }
    })
  } finally {
    isSyncingRange = false
  }
}

function syncCrosshair(sourceKey: PanelKey, param: MouseEventParams<Time>) {
  if (isSyncingCrosshair) return
  const time = param.time ? String(param.time) : null
  activeTradeDate.value = time ?? lastPoint.value?.trade_date ?? null
  isSyncingCrosshair = true
  try {
    ;(['nav', 'position'] as PanelKey[]).forEach((panelKey) => {
      if (panelKey === sourceKey) return
      const chart = charts[panelKey]
      const series = primarySeriesMap.get(panelKey)
      if (!chart || !series || !time) {
        chart?.clearCrosshairPosition()
        return
      }
      const price = panelValueMaps.get(panelKey)?.get(time)
      if (price === undefined) {
        chart.clearCrosshairPosition()
        return
      }
      chart.setCrosshairPosition(price, time as Time, series)
    })
  } finally {
    isSyncingCrosshair = false
  }
}

function attachSync(panelKey: PanelKey, chart: IChartApi) {
  const visibleRangeHandler = (range: LogicalRange | null) => syncVisibleRange(panelKey, range)
  const crosshairHandler = (param: MouseEventParams<Time>) => syncCrosshair(panelKey, param)
  chart.timeScale().subscribeVisibleLogicalRangeChange(visibleRangeHandler)
  chart.subscribeCrosshairMove(crosshairHandler)
  unsubs.push(() => chart.timeScale().unsubscribeVisibleLogicalRangeChange(visibleRangeHandler))
  unsubs.push(() => chart.unsubscribeCrosshairMove(crosshairHandler))
}

function fitCharts() {
  charts.nav?.timeScale().fitContent()
  charts.position?.timeScale().fitContent()
}

function updateSeries() {
  navSeries?.setData(navData.value)
  benchmarkSeries?.setData(benchmarkData.value)
  positionSeries?.setData(positionData.value)
  panelValueMaps.set('nav', buildLineValueMap(navData.value))
  panelValueMaps.set('position', buildHistogramValueMap(positionData.value))
  fitCharts()
  activeTradeDate.value = lastPoint.value?.trade_date ?? null
}

function renderCharts() {
  disposeCharts()
  if (!navContainerRef.value || !positionContainerRef.value) return

  const navChart = createBaseChart(navContainerRef.value, { hideTimeScale: true })
  const positionChart = createBaseChart(positionContainerRef.value)

  charts.nav = navChart
  charts.position = positionChart

  navSeries = navChart.addSeries(LineSeries, {
    color: '#0f4c75',
    lineWidth: 2,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  benchmarkSeries = navChart.addSeries(LineSeries, {
    color: '#f97316',
    lineWidth: 2,
    lastValueVisible: false,
    priceLineVisible: false,
  })
  positionSeries = positionChart.addSeries(HistogramSeries, {
    priceLineVisible: false,
    lastValueVisible: false,
    autoscaleInfoProvider: () => ({
      priceRange: {
        minValue: 0,
        maxValue: 100,
      },
    }),
  })

  primarySeriesMap.set('nav', navSeries)
  primarySeriesMap.set('position', positionSeries)

  attachSync('nav', navChart)
  attachSync('position', positionChart)
  updateSeries()
}

async function ensureChartsReady() {
  if (props.loading || !props.points.length) return
  await nextTick()
  if (!navContainerRef.value || !positionContainerRef.value) return
  if (!charts.nav || !charts.position) {
    renderCharts()
    return
  }
  updateSeries()
}

watch([navData, benchmarkData, positionData], updateSeries)

watch(
  [() => props.loading, () => props.points.length],
  async ([loading]) => {
    if (!loading) {
      await ensureChartsReady()
    }
    if (!props.points.length) {
      activeTradeDate.value = null
      charts.nav?.clearCrosshairPosition()
      charts.position?.clearCrosshairPosition()
      return
    }
    activeTradeDate.value = lastPoint.value?.trade_date ?? null
  },
  { flush: 'post' },
)

onMounted(async () => {
  await ensureChartsReady()
})

onBeforeUnmount(() => {
  disposeCharts()
})
</script>

<template>
  <section class="strategy-curve-chart">
    <p v-if="loading" class="muted">收益曲线加载中...</p>
    <p v-else-if="!points.length" class="muted">当前策略暂无可展示的收益曲线。</p>
    <template v-else>
      <div class="strategy-curve-hoverbar">
        <article v-for="item in summaryItems" :key="item.label" class="strategy-curve-hoveritem">
          <span class="strategy-curve-hoverlabel">{{ item.label }}</span>
          <strong class="strategy-curve-hovervalue">{{ item.value }}</strong>
        </article>
      </div>

      <div class="strategy-curve-panel">
        <div class="strategy-curve-panel-head">
          <h4>收益曲线</h4>
          <p>策略净值与基准净值</p>
        </div>
        <div ref="navContainerRef" class="strategy-curve-canvas strategy-curve-canvas-main"></div>
      </div>

      <div class="strategy-curve-panel">
        <div class="strategy-curve-panel-head">
          <h4>仓位面板</h4>
          <p>分档颜色展示每日收盘后的持仓比例</p>
        </div>
        <div ref="positionContainerRef" class="strategy-curve-canvas strategy-curve-canvas-position"></div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.strategy-curve-chart {
  display: grid;
  gap: 14px;
}

.strategy-curve-hoverbar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.strategy-curve-hoveritem {
  display: grid;
  gap: 4px;
  min-height: 74px;
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}

.strategy-curve-hoverlabel {
  font-size: 12px;
  color: #64748b;
}

.strategy-curve-hovervalue {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
}

.strategy-curve-panel {
  display: grid;
  gap: 8px;
}

.strategy-curve-panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.strategy-curve-panel-head h4 {
  margin: 0;
  font-size: 15px;
  color: #14213d;
}

.strategy-curve-panel-head p {
  margin: 0;
  font-size: 12px;
  color: #64748b;
}

.strategy-curve-canvas {
  width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  overflow: hidden;
}

.strategy-curve-canvas-main {
  min-height: 360px;
  height: 360px;
}

.strategy-curve-canvas-position {
  min-height: 180px;
  height: 180px;
}

.muted {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

@media (max-width: 900px) {
  .strategy-curve-hoverbar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .strategy-curve-panel-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
