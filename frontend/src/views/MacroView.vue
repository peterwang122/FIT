<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchMacroDashboard } from '../api/macro'
import AppSidebar from '../components/AppSidebar.vue'
import MacroLineChart from '../components/MacroLineChart.vue'
import type { MacroDashboard } from '../types/macro'

type MetricTab = 'spread' | 'buffett' | 'deposit'
type RangeKey = '1y' | '3y' | 'all'

const dashboard = ref<MacroDashboard | null>(null)
const loading = ref(false)
const error = ref('')
const activeMetric = ref<MetricTab>('spread')
const activeRange = ref<RangeKey>('3y')

const tabs = [
  { key: 'spread' as const, label: '股债利差' },
  { key: 'buffett' as const, label: '巴菲特指标' },
  { key: 'deposit' as const, label: '居民存款 / 股市市值' },
]

const chartConfig = computed(() => {
  if (activeMetric.value === 'spread') {
    return {
      title: '股债利差',
      unit: '个百分点',
      series: [
        { key: 'hs300_equity_bond_spread_pp' as const, label: '沪深300', color: '#2563eb' },
        { key: 'csi1000_equity_bond_spread_pp' as const, label: '中证1000', color: '#e11d48' },
      ],
    }
  }
  if (activeMetric.value === 'buffett') {
    return {
      title: '巴菲特指标',
      unit: '%',
      series: [{ key: 'buffett_indicator_pct' as const, label: 'A股总市值 / 名义GDP', color: '#0f766e' }],
    }
  }
  return {
    title: '居民存款与股市市值比',
    unit: '%',
    series: [{ key: 'household_deposit_market_cap_ratio_pct' as const, label: '住户存款 / A股总市值', color: '#c2410c' }],
  }
})

function formatValue(value: number | null | undefined, suffix = '') {
  return value == null || !Number.isFinite(value) ? '-' : `${value.toFixed(2)}${suffix}`
}

function formatTrillion(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value / 1_000_000_000_000).toFixed(2)}万亿元`
}

function formatMarketCapSource(source: string | null | undefined) {
  if (source === 'exchange_official') return '沪深北交易所官网'
  if (source === 'legulegu_adjusted_to_exchange_official') return '长期序列桥接官网口径'
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
          <p>估值、利率、经济总量与居民资金的同一观察面板</p>
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
          <div class="macro-chart-title">
            <h3>{{ chartConfig.title }}</h3>
            <span>{{ dashboard.points.length }} 个交易日</span>
          </div>
          <MacroLineChart
            :points="dashboard.points"
            :series="chartConfig.series"
            :unit="chartConfig.unit"
            :visible-start-date="activeRange === 'all' ? undefined : startDateForRange(activeRange)"
          />
        </section>

        <section class="macro-detail-band">
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
        </section>

        <section class="macro-methods">
          <article><h3>股债利差</h3><p>{{ dashboard.methodology.equity_bond_spread }}</p></article>
          <article><h3>巴菲特指标</h3><p>{{ dashboard.methodology.buffett_indicator }}</p></article>
          <article><h3>居民资金</h3><p>{{ dashboard.methodology.deposit_market_cap_ratio }}</p></article>
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
.macro-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.macro-kpi { min-width: 0; border: 1px solid #dce3eb; border-top: 3px solid #2563eb; border-radius: 6px; background: #fff; padding: 16px; }
.macro-kpi:nth-child(2) { border-top-color: #e11d48; }
.macro-kpi:nth-child(3) { border-top-color: #0f766e; }
.macro-kpi:nth-child(4) { border-top-color: #c2410c; }
.macro-kpi span, .macro-kpi small { display: block; color: #64748b; }
.macro-kpi strong { display: block; margin: 9px 0 8px; color: #172033; font-size: 25px; font-variant-numeric: tabular-nums; }
.macro-kpi small { min-height: 18px; font-size: 12px; white-space: normal; }
.macro-chart-panel { padding: 18px; min-width: 0; }
.macro-toolbar { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.macro-tabs, .macro-range { display: flex; gap: 4px; padding: 3px; border: 1px solid #dce3eb; border-radius: 6px; background: #f8fafc; }
.macro-tabs button, .macro-range button { border: 0; border-radius: 4px; background: transparent; color: #526077; font-weight: 700; padding: 8px 12px; cursor: pointer; }
.macro-tabs button.active, .macro-range button.active { background: #fff; color: #172033; box-shadow: 0 1px 3px rgba(15, 23, 42, .12); }
.macro-chart-title { display: flex; align-items: baseline; justify-content: space-between; margin: 20px 4px 8px; }
.macro-chart-title h3 { margin: 0; color: #172033; font-size: 17px; }
.macro-chart-title span { color: #64748b; font-size: 12px; }
.macro-detail-band { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid #dce3eb; background: #fff; }
.macro-detail-band > div { padding: 15px 18px; border-right: 1px solid #dce3eb; }
.macro-detail-band > div:last-child { border-right: 0; }
.macro-detail-band span { display: block; color: #64748b; font-size: 12px; }
.macro-detail-band strong { display: block; margin-top: 5px; color: #172033; font-size: 17px; }
.macro-detail-band small { display: block; margin-top: 4px; color: #64748b; font-size: 11px; }
.macro-methods { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; padding-bottom: 14px; }
.macro-methods article { padding: 4px 2px; }
.macro-methods h3 { margin: 0 0 6px; color: #334155; font-size: 14px; }
.macro-methods p { margin: 0; color: #64748b; font-size: 13px; line-height: 1.7; }
@media (max-width: 1100px) { .macro-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) {
  .macro-header, .macro-toolbar { align-items: stretch; flex-direction: column; }
  .macro-kpi-grid, .macro-detail-band, .macro-methods { grid-template-columns: 1fr; }
  .macro-detail-band > div { border-right: 0; border-bottom: 1px solid #dce3eb; }
  .macro-detail-band > div:last-child { border-bottom: 0; }
  .macro-tabs { overflow-x: auto; }
}
</style>
