<script setup lang="ts">
import { LineStyle } from 'lightweight-charts'
import { computed, onMounted, ref } from 'vue'

import { fetchMacroDashboard } from '../api/macro'
import AppSidebar from '../components/AppSidebar.vue'
import MacroLineChart from '../components/MacroLineChart.vue'
import type { MacroDashboard, MacroPoint } from '../types/macro'

type MetricTab = 'spread' | 'buffett' | 'deposit' | 'style'
type RangeKey = '1y' | '3y' | 'all'
type SpreadSeriesKey = 'hs300' | 'csi1000'
type StylePairKey = 'chinext' | 'star50'
type StyleSignal = 'growth' | 'dividend' | 'neutral' | 'unavailable'
type BollPosition = 'above' | 'below' | 'inside' | 'unavailable'

interface BollDefinition {
  label: string
  seriesLabel: string
  valueKey: keyof MacroPoint
  middleKey: keyof MacroPoint
  upperKey: keyof MacroPoint
  lowerKey: keyof MacroPoint
  color: string
}

interface SpreadSeriesDefinition extends BollDefinition {
  key: SpreadSeriesKey
}

interface BollSnapshot {
  value: number | null
  middle: number | null
  upper: number | null
  lower: number | null
  position: BollPosition
  positionLabel: string
}

interface StylePairDefinition {
  key: StylePairKey
  label: string
  sampleLabel: string
  ratioKey: keyof MacroPoint
  maKey: keyof MacroPoint
  upperKey: keyof MacroPoint
  lowerKey: keyof MacroPoint
  bollUpperKey: keyof MacroPoint
  bollLowerKey: keyof MacroPoint
}

interface StyleSnapshot {
  ratio: number | null
  movingAverage: number | null
  bollUpper: number | null
  bollLower: number | null
  bollPositionLabel: string
  distancePct: number | null
  signal: StyleSignal
  signalLabel: string
  tradeDate: string
  confirmation: string
}

const dashboard = ref<MacroDashboard | null>(null)
const loading = ref(false)
const error = ref('')
const activeMetric = ref<MetricTab>('spread')
const activeRange = ref<RangeKey>('3y')
const activeSpreadSeries = ref<SpreadSeriesKey>('hs300')
const activeStylePair = ref<StylePairKey>('chinext')

const tabs = [
  { key: 'spread' as const, label: '股债利差' },
  { key: 'buffett' as const, label: '巴菲特指标' },
  { key: 'deposit' as const, label: '居民存款 / 股市市值' },
  { key: 'style' as const, label: '成长 / 红利' },
]

const spreadSeriesList: SpreadSeriesDefinition[] = [
  {
    key: 'hs300',
    label: '沪深300股债利差',
    seriesLabel: '沪深300',
    valueKey: 'hs300_equity_bond_spread_pp',
    middleKey: 'hs300_equity_bond_spread_pp_boll_mid',
    upperKey: 'hs300_equity_bond_spread_pp_boll_upper',
    lowerKey: 'hs300_equity_bond_spread_pp_boll_lower',
    color: '#2563eb',
  },
  {
    key: 'csi1000',
    label: '中证1000股债利差',
    seriesLabel: '中证1000',
    valueKey: 'csi1000_equity_bond_spread_pp',
    middleKey: 'csi1000_equity_bond_spread_pp_boll_mid',
    upperKey: 'csi1000_equity_bond_spread_pp_boll_upper',
    lowerKey: 'csi1000_equity_bond_spread_pp_boll_lower',
    color: '#e11d48',
  },
]

const spreadSeries = Object.fromEntries(spreadSeriesList.map((item) => [item.key, item])) as Record<SpreadSeriesKey, SpreadSeriesDefinition>

const buffettBollDefinition: BollDefinition = {
  label: '巴菲特指标',
  seriesLabel: 'A股总市值 / 名义GDP',
  valueKey: 'buffett_indicator_pct',
  middleKey: 'buffett_indicator_pct_boll_mid',
  upperKey: 'buffett_indicator_pct_boll_upper',
  lowerKey: 'buffett_indicator_pct_boll_lower',
  color: '#0f766e',
}

const depositBollDefinition: BollDefinition = {
  label: '居民存款与股市市值比',
  seriesLabel: '住户存款 / A股总市值',
  valueKey: 'household_deposit_market_cap_ratio_pct',
  middleKey: 'household_deposit_market_cap_ratio_pct_boll_mid',
  upperKey: 'household_deposit_market_cap_ratio_pct_boll_upper',
  lowerKey: 'household_deposit_market_cap_ratio_pct_boll_lower',
  color: '#c2410c',
}

const stylePairList: StylePairDefinition[] = [
  {
    key: 'chinext',
    label: '创业板指 / 中证红利',
    sampleLabel: '长样本 · 2010年至今 · MA20',
    ratioKey: 'chinext_csi_dividend_ratio',
    maKey: 'chinext_csi_dividend_ratio_ma20',
    upperKey: 'chinext_csi_dividend_ratio_upper_1pct',
    lowerKey: 'chinext_csi_dividend_ratio_lower_1pct',
    bollUpperKey: 'chinext_csi_dividend_ratio_boll_upper',
    bollLowerKey: 'chinext_csi_dividend_ratio_boll_lower',
  },
  {
    key: 'star50',
    label: '科创50 / 中证红利',
    sampleLabel: '短样本 · 2019年至今 · MA20',
    ratioKey: 'star50_csi_dividend_ratio',
    maKey: 'star50_csi_dividend_ratio_ma20',
    upperKey: 'star50_csi_dividend_ratio_upper_1pct',
    lowerKey: 'star50_csi_dividend_ratio_lower_1pct',
    bollUpperKey: 'star50_csi_dividend_ratio_boll_upper',
    bollLowerKey: 'star50_csi_dividend_ratio_boll_lower',
  },
]

const stylePairs = Object.fromEntries(stylePairList.map((item) => [item.key, item])) as Record<StylePairKey, StylePairDefinition>

function numericValue(point: MacroPoint | null | undefined, key: keyof MacroPoint) {
  const value = point?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function buildBollSnapshot(definition: BollDefinition): BollSnapshot {
  const points = dashboard.value?.points ?? []
  const latestPoint = [...points].reverse().find((point) => numericValue(point, definition.valueKey) != null)
  const value = numericValue(latestPoint, definition.valueKey)
  const middle = numericValue(latestPoint, definition.middleKey)
  const upper = numericValue(latestPoint, definition.upperKey)
  const lower = numericValue(latestPoint, definition.lowerKey)
  let position: BollPosition = 'unavailable'
  if (value != null && upper != null && lower != null) {
    if (value > upper) position = 'above'
    else if (value < lower) position = 'below'
    else position = 'inside'
  }
  const positionLabels: Record<BollPosition, string> = {
    above: '突破上轨',
    below: '跌破下轨',
    inside: '轨道内',
    unavailable: '暂无数据',
  }
  return { value, middle, upper, lower, position, positionLabel: positionLabels[position] }
}

function bollOverlaySeries(definition: BollDefinition, middleColor = '#2563eb', bandColor = '#e11d48') {
  return [
    {
      key: definition.middleKey,
      label: 'BOLL中轨',
      color: middleColor,
      lineWidth: 2 as const,
      lastValueVisible: false,
    },
    {
      key: definition.upperKey,
      label: 'BOLL上轨',
      color: bandColor,
      lineWidth: 1 as const,
      lineStyle: LineStyle.Dotted,
      lastValueVisible: false,
    },
    {
      key: definition.lowerKey,
      label: 'BOLL下轨',
      color: bandColor,
      lineWidth: 1 as const,
      lineStyle: LineStyle.Dotted,
      lastValueVisible: false,
    },
  ]
}

function signalForPoint(point: MacroPoint, pair: StylePairDefinition): Exclude<StyleSignal, 'unavailable'> {
  const ratio = numericValue(point, pair.ratioKey)
  const upper = numericValue(point, pair.upperKey)
  const lower = numericValue(point, pair.lowerKey)
  if (ratio == null || upper == null || lower == null) return 'neutral'
  if (ratio > upper) return 'growth'
  if (ratio < lower) return 'dividend'
  return 'neutral'
}

function buildStyleSnapshot(pair: StylePairDefinition): StyleSnapshot {
  const points = dashboard.value?.points ?? []
  const latestPoint = [...points].reverse().find((point) => numericValue(point, pair.ratioKey) != null)
  if (!latestPoint) {
    return {
      ratio: null,
      movingAverage: null,
      bollUpper: null,
      bollLower: null,
      bollPositionLabel: '暂无数据',
      distancePct: null,
      signal: 'unavailable',
      signalLabel: '暂无数据',
      tradeDate: '-',
      confirmation: '-',
    }
  }

  const ratio = numericValue(latestPoint, pair.ratioKey)
  const movingAverage = numericValue(latestPoint, pair.maKey)
  const bollUpper = numericValue(latestPoint, pair.bollUpperKey)
  const bollLower = numericValue(latestPoint, pair.bollLowerKey)
  const signal = signalForPoint(latestPoint, pair)
  let previousSignal: Exclude<StyleSignal, 'unavailable'> = 'neutral'
  let confirmation = '-'
  for (const point of points) {
    const currentSignal = signalForPoint(point, pair)
    if (currentSignal !== 'neutral' && currentSignal !== previousSignal) {
      confirmation = `${point.trade_date.slice(5)} ${currentSignal === 'growth' ? '上穿上轨' : '跌破下轨'}`
    }
    previousSignal = currentSignal
  }

  const signalLabels: Record<Exclude<StyleSignal, 'unavailable'>, string> = {
    growth: '成长占优',
    dividend: '红利占优',
    neutral: '震荡观察',
  }
  let bollPositionLabel = '暂无数据'
  if (ratio != null && bollUpper != null && bollLower != null) {
    if (ratio > bollUpper) bollPositionLabel = '突破上轨'
    else if (ratio < bollLower) bollPositionLabel = '跌破下轨'
    else bollPositionLabel = '轨道内'
  }
  return {
    ratio,
    movingAverage,
    bollUpper,
    bollLower,
    bollPositionLabel,
    distancePct: ratio != null && movingAverage ? (ratio / movingAverage - 1) * 100 : null,
    signal,
    signalLabel: signalLabels[signal],
    tradeDate: latestPoint.trade_date,
    confirmation,
  }
}

const styleSnapshots = computed<Record<StylePairKey, StyleSnapshot>>(() => ({
  chinext: buildStyleSnapshot(stylePairs.chinext),
  star50: buildStyleSnapshot(stylePairs.star50),
}))

const activeStyleDefinition = computed(() => stylePairs[activeStylePair.value])
const activeStyleSnapshot = computed(() => styleSnapshots.value[activeStylePair.value])
const spreadBollSnapshots = computed<Record<SpreadSeriesKey, BollSnapshot>>(() => ({
  hs300: buildBollSnapshot(spreadSeries.hs300),
  csi1000: buildBollSnapshot(spreadSeries.csi1000),
}))
const activeMacroBollDefinition = computed<BollDefinition | null>(() => {
  if (activeMetric.value === 'spread') return spreadSeries[activeSpreadSeries.value]
  if (activeMetric.value === 'buffett') return buffettBollDefinition
  if (activeMetric.value === 'deposit') return depositBollDefinition
  return null
})
const activeMacroBollSnapshot = computed(() => (
  activeMacroBollDefinition.value
    ? buildBollSnapshot(activeMacroBollDefinition.value)
    : buildBollSnapshot(buffettBollDefinition)
))

const chartConfig = computed(() => {
  if (activeMetric.value === 'spread') {
    const definition = spreadSeries[activeSpreadSeries.value]
    return {
      title: definition.label,
      unit: '个百分点',
      precision: 2,
      series: [
        { key: definition.valueKey, label: definition.seriesLabel, color: definition.color, lineWidth: 3 as const },
        ...bollOverlaySeries(definition, '#0f766e', '#c2410c'),
      ],
    }
  }
  if (activeMetric.value === 'buffett') {
    return {
      title: buffettBollDefinition.label,
      unit: '%',
      precision: 2,
      series: [
        { key: buffettBollDefinition.valueKey, label: buffettBollDefinition.seriesLabel, color: buffettBollDefinition.color, lineWidth: 3 as const },
        ...bollOverlaySeries(buffettBollDefinition),
      ],
    }
  }
  if (activeMetric.value === 'deposit') {
    return {
      title: depositBollDefinition.label,
      unit: '%',
      precision: 2,
      series: [
        { key: depositBollDefinition.valueKey, label: depositBollDefinition.seriesLabel, color: depositBollDefinition.color, lineWidth: 3 as const },
        ...bollOverlaySeries(depositBollDefinition),
      ],
    }
  }
  const pair = activeStyleDefinition.value
  return {
    title: pair.label,
    unit: '',
    precision: 3,
    series: [
      { key: pair.ratioKey, label: '风格比值', color: '#c2410c', lineWidth: 3 as const },
      { key: pair.maKey, label: 'MA20', color: '#2563eb', lineWidth: 2 as const, lastValueVisible: false },
      {
        key: pair.upperKey,
        label: '缓冲上轨 +1%',
        color: '#0f766e',
        lineWidth: 1 as const,
        lineStyle: LineStyle.Dashed,
        lastValueVisible: false,
      },
      {
        key: pair.lowerKey,
        label: '缓冲下轨 -1%',
        color: '#0f766e',
        lineWidth: 1 as const,
        lineStyle: LineStyle.Dashed,
        lastValueVisible: false,
      },
      {
        key: pair.bollUpperKey,
        label: 'BOLL上轨',
        color: '#e11d48',
        lineWidth: 1 as const,
        lineStyle: LineStyle.Dotted,
        lastValueVisible: false,
      },
      {
        key: pair.bollLowerKey,
        label: 'BOLL下轨',
        color: '#e11d48',
        lineWidth: 1 as const,
        lineStyle: LineStyle.Dotted,
        lastValueVisible: false,
      },
    ],
  }
})

const visiblePointCount = computed(() => {
  const primaryKey = chartConfig.value.series[0]?.key
  if (!primaryKey) return 0
  const visibleStartDate = activeRange.value === 'all' ? '' : startDateForRange(activeRange.value)
  return dashboard.value?.points.filter((point) => (
    (!visibleStartDate || point.trade_date >= visibleStartDate)
    && numericValue(point, primaryKey) != null
  )).length ?? 0
})

function formatValue(value: number | null | undefined, suffix = '') {
  return value == null || !Number.isFinite(value) ? '-' : `${value.toFixed(2)}${suffix}`
}

function formatRatio(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : value.toFixed(3)
}

function formatMacroBollValue(value: number | null | undefined) {
  const suffix = activeMetric.value === 'spread' ? 'pp' : '%'
  return formatValue(value, suffix)
}

function formatDistance(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '-'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatTrillion(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value / 1_000_000_000_000).toFixed(2)}万亿元`
}

function formatMarketCapSource(source: string | null | undefined) {
  if (source === 'exchange_official') return '沪深北交易所官网'
  if (source === 'legulegu_adjusted_to_exchange_official') return '长期序列桥接官网口径'
  if (source === 'legulegu_interpolated_adjusted_to_exchange_official') return '插值序列桥接官网口径'
  return '-'
}

function startDateForRange(range: RangeKey) {
  if (range === 'all') return '2005-04-08'
  const years = range === '1y' ? 1 : 3
  const target = new Date()
  target.setFullYear(target.getFullYear() - years)
  return target.toISOString().slice(0, 10)
}

async function loadDashboard() {
  loading.value = true
  error.value = ''
  try {
    dashboard.value = await fetchMacroDashboard('2005-04-08')
  } catch (rawError) {
    error.value =
      (rawError as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
      (rawError instanceof Error ? rawError.message : '宏观指标加载失败')
  } finally {
    loading.value = false
  }
}

function selectRange(range: RangeKey) {
  if (activeRange.value === range) return
  activeRange.value = range
}

onMounted(loadDashboard)
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="macro" />
    <main class="dashboard-main macro-main">
      <header class="macro-header">
        <div>
          <h2>A股宏观指标</h2>
          <p>估值、利率、居民资金与成长 / 红利风格的同一观察面板</p>
        </div>
        <div v-if="dashboard?.latest" class="macro-asof">数据日期 {{ dashboard.latest.trade_date }}</div>
      </header>

      <p v-if="error" class="banner-error">{{ error }}</p>
      <p v-if="loading && !dashboard" class="macro-loading">宏观数据加载中...</p>

      <template v-if="dashboard?.latest">
        <section class="macro-kpi-grid">
          <article class="macro-kpi">
            <span>沪深300股债利差</span>
            <strong>{{ formatValue(dashboard.latest.hs300_equity_bond_spread_pp, 'pp') }}</strong>
            <small>PE {{ formatValue(dashboard.latest.hs300_pe_ttm) }} · 10Y {{ formatValue(dashboard.latest.cn_gov_bond_10y_yield_pct, '%') }}</small>
          </article>
          <article class="macro-kpi">
            <span>中证1000股债利差</span>
            <strong>{{ formatValue(dashboard.latest.csi1000_equity_bond_spread_pp, 'pp') }}</strong>
            <small>PE {{ formatValue(dashboard.latest.csi1000_pe_ttm) }} · 10Y {{ formatValue(dashboard.latest.cn_gov_bond_10y_yield_pct, '%') }}</small>
          </article>
          <article class="macro-kpi">
            <span>巴菲特指标</span>
            <strong>{{ formatValue(dashboard.latest.buffett_indicator_pct, '%') }}</strong>
            <small>GDP期 {{ dashboard.latest.gdp_period_end || '-' }}</small>
          </article>
          <article class="macro-kpi">
            <span>居民存款 / 股市市值</span>
            <strong>{{ formatValue(dashboard.latest.household_deposit_market_cap_ratio_pct, '%') }}</strong>
            <small>存款期 {{ dashboard.latest.deposit_period_end || '-' }}</small>
          </article>
          <article class="macro-kpi macro-kpi-style">
            <span>创业板指 / 中证红利</span>
            <strong>{{ formatRatio(styleSnapshots.chinext.ratio) }}</strong>
            <small>
              <b :class="`signal-${styleSnapshots.chinext.signal}`">{{ styleSnapshots.chinext.signalLabel }}</b>
              · MA20 {{ formatRatio(styleSnapshots.chinext.movingAverage) }}
            </small>
          </article>
          <article class="macro-kpi macro-kpi-style">
            <span>科创50 / 中证红利</span>
            <strong>{{ formatRatio(styleSnapshots.star50.ratio) }}</strong>
            <small>
              <b :class="`signal-${styleSnapshots.star50.signal}`">{{ styleSnapshots.star50.signalLabel }}</b>
              · MA20 {{ formatRatio(styleSnapshots.star50.movingAverage) }}
            </small>
          </article>
        </section>

        <section class="card macro-chart-panel">
          <div class="macro-toolbar">
            <div class="macro-tabs" role="tablist">
              <button v-for="item in tabs" :key="item.key" type="button" :class="{ active: activeMetric === item.key }" @click="activeMetric = item.key">
                {{ item.label }}
              </button>
            </div>
            <div class="macro-range">
              <button type="button" :class="{ active: activeRange === '1y' }" @click="selectRange('1y')">1年</button>
              <button type="button" :class="{ active: activeRange === '3y' }" @click="selectRange('3y')">3年</button>
              <button type="button" :class="{ active: activeRange === 'all' }" @click="selectRange('all')">全部</button>
            </div>
          </div>

          <div v-if="activeMetric === 'spread'" class="macro-style-pairs" aria-label="股债利差指数">
            <button
              v-for="definition in spreadSeriesList"
              :key="definition.key"
              type="button"
              :class="['macro-style-pair', `pair-${definition.key}`, { active: activeSpreadSeries === definition.key }]"
              @click="activeSpreadSeries = definition.key"
            >
              <span>
                <strong>{{ definition.label }}</strong>
                <small>BOLL(20,2) · 单图查看</small>
              </span>
              <span class="macro-style-pair-value">
                <strong>{{ formatValue(spreadBollSnapshots[definition.key].value, 'pp') }}</strong>
                <small :class="`boll-${spreadBollSnapshots[definition.key].position}`">{{ spreadBollSnapshots[definition.key].positionLabel }}</small>
              </span>
            </button>
          </div>

          <div v-if="activeMetric === 'style'" class="macro-style-pairs" aria-label="成长红利组合">
            <button
              v-for="pair in stylePairList"
              :key="pair.key"
              type="button"
              :class="['macro-style-pair', `pair-${pair.key}`, { active: activeStylePair === pair.key }]"
              @click="activeStylePair = pair.key"
            >
              <span>
                <strong>{{ pair.label }}</strong>
                <small>{{ pair.sampleLabel }}</small>
              </span>
              <span class="macro-style-pair-value">
                <strong>{{ formatRatio(styleSnapshots[pair.key].ratio) }}</strong>
                <small :class="`signal-${styleSnapshots[pair.key].signal}`">{{ styleSnapshots[pair.key].signalLabel }}</small>
              </span>
            </button>
          </div>

          <div class="macro-chart-title">
            <div>
              <h3>{{ chartConfig.title }}</h3>
              <p v-if="activeMetric === 'style'">比值上行代表成长相对走强，下行代表红利相对走强</p>
              <p v-else>BOLL(20,2)：20日中轨与上下2倍标准差</p>
            </div>
            <span>{{ visiblePointCount }} 个有效交易日</span>
          </div>
          <MacroLineChart
            :points="dashboard.points"
            :series="chartConfig.series"
            :unit="chartConfig.unit"
            :precision="chartConfig.precision"
            :visible-start-date="activeRange === 'all' ? undefined : startDateForRange(activeRange)"
          />
        </section>

        <section v-if="activeMetric === 'style'" class="macro-style-signal-band">
          <div :class="['macro-style-primary', `signal-${activeStyleSnapshot.signal}`]">
            <span>当前风格信号</span>
            <strong>{{ activeStyleSnapshot.signalLabel }}</strong>
          </div>
          <div>
            <span>MA20</span>
            <strong>{{ formatRatio(activeStyleSnapshot.movingAverage) }}</strong>
          </div>
          <div>
            <span>偏离均线</span>
            <strong>{{ formatDistance(activeStyleSnapshot.distancePct) }}</strong>
          </div>
          <div>
            <span>BOLL(20,2)</span>
            <strong>{{ activeStyleSnapshot.bollPositionLabel }}</strong>
            <small>{{ formatRatio(activeStyleSnapshot.bollLower) }} – {{ formatRatio(activeStyleSnapshot.bollUpper) }}</small>
          </div>
          <div>
            <span>最近确认</span>
            <strong>{{ activeStyleSnapshot.confirmation }}</strong>
          </div>
        </section>

        <section v-else class="macro-detail-band">
          <div>
            <span>A股总市值</span>
            <strong>{{ formatTrillion(dashboard.latest.a_share_total_market_cap_cny) }}</strong>
            <small>{{ formatMarketCapSource(dashboard.latest.market_cap_source) }}</small>
          </div>
          <div>
            <span>最近四季名义GDP</span>
            <strong>{{ formatTrillion(dashboard.latest.trailing_4q_nominal_gdp_cny) }}</strong>
          </div>
          <div>
            <span>人民币住户存款</span>
            <strong>{{ formatTrillion(dashboard.latest.household_deposit_cny) }}</strong>
          </div>
          <div :class="['macro-boll-summary', `boll-${activeMacroBollSnapshot.position}`]">
            <span>{{ activeMacroBollDefinition?.label }} BOLL(20,2)</span>
            <strong>{{ activeMacroBollSnapshot.positionLabel }}</strong>
            <small>
              中轨 {{ formatMacroBollValue(activeMacroBollSnapshot.middle) }} ·
              {{ formatMacroBollValue(activeMacroBollSnapshot.lower) }} – {{ formatMacroBollValue(activeMacroBollSnapshot.upper) }}
            </small>
          </div>
        </section>

        <section class="macro-methods">
          <article><h3>股债利差</h3><p>{{ dashboard.methodology.equity_bond_spread }}</p></article>
          <article><h3>巴菲特指标</h3><p>{{ dashboard.methodology.buffett_indicator }}</p></article>
          <article><h3>居民资金</h3><p>{{ dashboard.methodology.deposit_market_cap_ratio }}</p></article>
          <article><h3>成长 / 红利</h3><p>{{ dashboard.methodology.growth_dividend_ratio }}</p></article>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.macro-main { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.macro-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 4px 2px; }
.macro-header h2 { margin: 0 0 4px; font-size: 28px; color: #172033; letter-spacing: 0; }
.macro-header p { margin: 0; color: #64748b; }
.macro-asof { font-size: 13px; font-weight: 700; color: #475569; }
.macro-loading { padding: 40px; text-align: center; color: #64748b; }
.macro-kpi-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.macro-kpi { min-width: 0; border: 1px solid #dce3eb; border-top: 3px solid #2563eb; border-radius: 6px; background: #fff; padding: 16px; }
.macro-kpi:nth-child(2) { border-top-color: #e11d48; }
.macro-kpi:nth-child(3) { border-top-color: #0f766e; }
.macro-kpi:nth-child(4) { border-top-color: #c2410c; }
.macro-kpi:nth-child(5) { border-top-color: #2563eb; }
.macro-kpi:nth-child(6) { border-top-color: #e11d48; }
.macro-kpi span, .macro-kpi small { display: block; color: #64748b; }
.macro-kpi strong { display: block; margin: 9px 0 8px; color: #172033; font-size: 25px; font-variant-numeric: tabular-nums; }
.macro-kpi small { min-height: 18px; font-size: 12px; white-space: normal; }
.macro-kpi small b { font-weight: 700; }
.signal-growth { color: #2563eb !important; }
.signal-dividend { color: #e11d48 !important; }
.signal-neutral { color: #b45309 !important; }
.signal-unavailable { color: #64748b !important; }
.boll-above { color: #2563eb !important; }
.boll-below { color: #e11d48 !important; }
.boll-inside { color: #0f766e !important; }
.boll-unavailable { color: #64748b !important; }
.macro-chart-panel { padding: 18px; min-width: 0; }
.macro-toolbar { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.macro-tabs, .macro-range { display: flex; gap: 4px; padding: 3px; border: 1px solid #dce3eb; border-radius: 6px; background: #f8fafc; }
.macro-tabs button, .macro-range button { border: 0; border-radius: 4px; background: transparent; color: #526077; font-weight: 700; padding: 8px 12px; cursor: pointer; white-space: nowrap; }
.macro-tabs button.active, .macro-range button.active { background: #fff; color: #172033; box-shadow: 0 1px 3px rgba(15, 23, 42, .12); }
.macro-style-pairs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.macro-style-pair { display: flex; align-items: center; justify-content: space-between; gap: 14px; min-width: 0; padding: 13px 14px; border: 1px solid #dce3eb; border-left: 4px solid #2563eb; border-radius: 10px; background: rgba(248, 250, 252, .72); color: #172033; cursor: pointer; text-align: left; }
.macro-style-pair.pair-star50, .macro-style-pair.pair-csi1000 { border-left-color: #e11d48; }
.macro-style-pair.active { border-color: rgba(37, 99, 235, .36); border-left-color: #2563eb; background: #fff; box-shadow: 0 10px 24px rgba(37, 99, 235, .10); }
.macro-style-pair.pair-star50.active, .macro-style-pair.pair-csi1000.active { border-color: rgba(225, 29, 72, .32); border-left-color: #e11d48; box-shadow: 0 10px 24px rgba(225, 29, 72, .08); }
.macro-style-pair > span, .macro-style-pair strong, .macro-style-pair small { display: block; min-width: 0; }
.macro-style-pair > span:first-child { overflow: hidden; }
.macro-style-pair > span:first-child strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.macro-style-pair small { margin-top: 4px; color: #64748b; font-size: 11px; }
.macro-style-pair-value { flex: 0 0 auto; text-align: right; }
.macro-style-pair-value strong { font-size: 17px; font-variant-numeric: tabular-nums; }
.macro-chart-title { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin: 20px 4px 8px; }
.macro-chart-title h3 { margin: 0; color: #172033; font-size: 17px; }
.macro-chart-title p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
.macro-chart-title > span { flex: 0 0 auto; color: #64748b; font-size: 12px; }
.macro-detail-band, .macro-style-signal-band { display: grid; border: 1px solid #dce3eb; background: #fff; }
.macro-detail-band { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.macro-style-signal-band { grid-template-columns: 1.2fr repeat(4, minmax(0, 1fr)); }
.macro-detail-band > div, .macro-style-signal-band > div { padding: 15px 18px; border-right: 1px solid #dce3eb; }
.macro-detail-band > div:last-child, .macro-style-signal-band > div:last-child { border-right: 0; }
.macro-detail-band span, .macro-style-signal-band span { display: block; color: #64748b; font-size: 12px; }
.macro-detail-band strong, .macro-style-signal-band strong { display: block; margin-top: 5px; color: #172033; font-size: 17px; font-variant-numeric: tabular-nums; }
.macro-style-signal-band small { display: block; margin-top: 4px; color: #64748b; font-size: 11px; font-variant-numeric: tabular-nums; }
.macro-detail-band small { display: block; margin-top: 4px; color: #64748b; font-size: 11px; }
.macro-boll-summary { border-top: 3px solid #94a3b8; }
.macro-boll-summary.boll-above { border-top-color: #2563eb; }
.macro-boll-summary.boll-below { border-top-color: #e11d48; }
.macro-boll-summary.boll-inside { border-top-color: #0f766e; }
.macro-boll-summary.boll-above strong { color: #2563eb; }
.macro-boll-summary.boll-below strong { color: #e11d48; }
.macro-boll-summary.boll-inside strong { color: #0f766e; }
.macro-style-primary { border-top: 3px solid #b45309; }
.macro-style-primary.signal-growth { border-top-color: #2563eb; }
.macro-style-primary.signal-dividend { border-top-color: #e11d48; }
.macro-style-primary.signal-unavailable { border-top-color: #94a3b8; }
.macro-style-primary.signal-growth strong { color: #2563eb; }
.macro-style-primary.signal-dividend strong { color: #e11d48; }
.macro-style-primary.signal-neutral strong { color: #b45309; }
.macro-methods { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; padding-bottom: 14px; }
.macro-methods article { padding: 4px 2px; }
.macro-methods h3 { margin: 0 0 6px; color: #334155; font-size: 14px; }
.macro-methods p { margin: 0; color: #64748b; font-size: 13px; line-height: 1.7; }
@media (max-width: 1200px) {
  .macro-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .macro-methods { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .macro-header, .macro-toolbar, .macro-chart-title { align-items: stretch; flex-direction: column; }
  .macro-kpi-grid, .macro-style-pairs, .macro-detail-band, .macro-style-signal-band, .macro-methods { grid-template-columns: 1fr; }
  .macro-detail-band > div, .macro-style-signal-band > div { border-right: 0; border-bottom: 1px solid #dce3eb; }
  .macro-detail-band > div:last-child, .macro-style-signal-band > div:last-child { border-bottom: 0; }
  .macro-tabs { overflow-x: auto; }
}
</style>
