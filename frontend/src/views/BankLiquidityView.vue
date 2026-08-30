<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { fetchBankLiquidityDashboard } from '../api/macro'
import AppSidebar from '../components/AppSidebar.vue'
import BankLiquidityChart, { type BankLiquiditySeriesDefinition } from '../components/BankLiquidityChart.vue'
import type { BankLiquidityDailyPoint, BankLiquidityDashboard } from '../types/macro'

type ViewKey = 'score' | 'rates' | 'operations' | 'funding'
type RangeKey = '1y' | '3y' | 'all'

const dashboard = ref<BankLiquidityDashboard | null>(null)
const loading = ref(false)
const error = ref('')
const activeView = ref<ViewKey>('score')
const activeRange = ref<RangeKey>('3y')

const views = [
  { key: 'score' as const, label: '紧张度' },
  { key: 'rates' as const, label: '资金价格' },
  { key: 'operations' as const, label: '央行投放' },
  { key: 'funding' as const, label: '银行负债' },
]

const scoreSeries: BankLiquiditySeriesDefinition[] = [
  { key: 'liquidity_tightness_score', label: '紧张度', color: '#2563eb', unit: '分', precision: 1 },
  { key: 'pct_fdr007_policy_spread', label: 'FDR007政策偏离', color: '#0f766e', unit: '分', precision: 1, sourceDateKey: 'frr_source_date', availableAtKey: 'frr_available_at', sourceUrlKey: 'source_url_frr', sourceLabel: '中国货币网定盘利率' },
  { key: 'pct_overnight_pressure', label: '隔夜挤压', color: '#b45309', unit: '分', precision: 1 },
  { key: 'pct_nonbank_layering', label: '机构分层', color: '#7c3aed', unit: '分', precision: 1 },
  { key: 'pct_bank_funding_spread', label: '银行负债压力', color: '#dc2626', unit: '分', precision: 1, sourceDateKey: 'chinabond_source_date', availableAtKey: 'chinabond_available_at', sourceUrlKey: 'source_url_chinabond', sourceLabel: '中债收益率曲线' },
]

const rateSeries: BankLiquiditySeriesDefinition[] = [
  { key: 'fdr001_pct', label: 'FDR001', color: '#2563eb', unit: '%', precision: 3, sourceDateKey: 'frr_source_date', availableAtKey: 'frr_available_at', sourceUrlKey: 'source_url_frr', sourceLabel: '中国货币网定盘利率' },
  { key: 'fdr007_pct', label: 'FDR007', color: '#0f766e', unit: '%', precision: 3 },
  { key: 'fr007_pct', label: 'FR007', color: '#7c3aed', unit: '%', precision: 3 },
  { key: 'reverse_repo_7d_policy_rate_pct', label: '7天逆回购政策利率', color: '#b45309', unit: '%', precision: 3, sourceDateKey: 'pbc_source_date', availableAtKey: 'pbc_available_at', sourceUrlKey: 'source_url_pbc', sourceLabel: '人民银行公开市场公告' },
  { key: 'dr001_weighted_pct', label: 'DR001日终', color: '#0284c7', unit: '%', precision: 3, sourceDateKey: 'closing_repo_source_date', availableAtKey: 'closing_repo_available_at', sourceUrlKey: 'source_url_closing_repo', sourceLabel: '中国货币网全日回购' },
  { key: 'dr007_weighted_pct', label: 'DR007日终', color: '#16a34a', unit: '%', precision: 3 },
  { key: 'r001_weighted_pct', label: 'R001日终', color: '#e11d48', unit: '%', precision: 3 },
  { key: 'r007_weighted_pct', label: 'R007日终', color: '#ea580c', unit: '%', precision: 3 },
]

const operationSeries: BankLiquiditySeriesDefinition[] = [
  { key: 'reverse_repo_net_cny', label: '当日净投放', color: '#0f766e', type: 'histogram', unit: '亿元', precision: 0, sourceDateKey: 'pbc_source_date', availableAtKey: 'pbc_available_at', sourceUrlKey: 'source_url_pbc', sourceLabel: '人民银行公开市场公告' },
  { key: 'reverse_repo_injection_cny', label: '投放', color: '#2563eb', unit: '亿元', precision: 0 },
  { key: 'reverse_repo_maturity_cny', label: '到期', color: '#dc2626', unit: '亿元', precision: 0 },
  { key: 'reverse_repo_net_5d_cny', label: '5日累计', color: '#7c3aed', unit: '亿元', precision: 0 },
  { key: 'reverse_repo_net_20d_cny', label: '20日累计', color: '#b45309', unit: '亿元', precision: 0 },
]

const fundingSeries: BankLiquiditySeriesDefinition[] = [
  { key: 'bank_bond_aaa_1y_yield_pct', label: '1Y AAA银行普通债', color: '#2563eb', unit: '%', precision: 3, sourceDateKey: 'chinabond_source_date', availableAtKey: 'chinabond_available_at', sourceUrlKey: 'source_url_chinabond', sourceLabel: '中债收益率曲线' },
  { key: 'cgb_1y_yield_pct', label: '1Y国债', color: '#0f766e', unit: '%', precision: 3 },
  { key: 'factor_bank_funding_spread_bp', label: '银行负债利差', color: '#dc2626', unit: 'bp', precision: 1, priceScaleId: 'left' },
]

const scorePoint = computed(() => (
  [...(dashboard.value?.daily_points ?? [])]
    .reverse()
    .find((point) => point.liquidity_tightness_score != null) ?? null
))

const latestPoint = computed(() => dashboard.value?.latest ?? null)

const visibleStartDate = computed(() => {
  if (activeRange.value === 'all') return undefined
  const latestDate = dashboard.value?.coverage.latest_date
  if (!latestDate) return undefined
  const target = new Date(`${latestDate}T00:00:00`)
  target.setFullYear(target.getFullYear() - (activeRange.value === '1y' ? 1 : 3))
  return target.toISOString().slice(0, 10)
})

const chartPoints = computed<BankLiquidityDailyPoint[]>(() => {
  if (activeView.value !== 'operations') return dashboard.value?.daily_points ?? []
  const amountFields = [
    'reverse_repo_injection_cny',
    'reverse_repo_maturity_cny',
    'reverse_repo_net_cny',
    'reverse_repo_net_5d_cny',
    'reverse_repo_net_20d_cny',
  ] as const
  return (dashboard.value?.daily_points ?? []).map((point) => {
    const normalized = { ...point }
    for (const field of amountFields) {
      normalized[field] = point[field] == null ? null : point[field]! / 100_000_000
    }
    return normalized
  })
})

const chartConfig = computed(() => {
  if (activeView.value === 'rates') {
    return { title: '银行间资金价格', subtitle: '11:30定盘利率与22:00日终加权利率', series: rateSeries }
  }
  if (activeView.value === 'operations') {
    return { title: '公开市场逆回购投放', subtitle: '投放、到期、净投放及交易日累计，单位亿元', series: operationSeries }
  }
  if (activeView.value === 'funding') {
    return { title: '银行中期负债融资压力', subtitle: '1年AAA银行普通债与1年国债，利差使用左轴', series: fundingSeries }
  }
  return { title: '银行流动性紧张度', subtitle: '0代表宽松，100代表紧张', series: scoreSeries }
})

const contextCards = computed(() => {
  const point = latestPoint.value
  if (!point) return []
  if (activeView.value === 'rates') {
    return [
      { label: 'FDR001', value: formatRate(point.fdr001_pct), note: '11:30定盘' },
      { label: 'FDR007', value: formatRate(point.fdr007_pct), note: '11:30定盘' },
      { label: 'FR007', value: formatRate(point.fr007_pct), note: '非银资金' },
      { label: 'DR007', value: formatRate(point.dr007_weighted_pct), note: '22:00日终确认' },
    ]
  }
  if (activeView.value === 'operations') {
    return [
      { label: '当日投放', value: formatYi(point.reverse_repo_injection_cny), note: '官方公告' },
      { label: '当日到期', value: formatYi(point.reverse_repo_maturity_cny), note: '按逐笔到期日' },
      { label: '5日净投放', value: formatYi(point.reverse_repo_net_5d_cny), note: '交易日累计' },
      { label: '20日净投放', value: formatYi(point.reverse_repo_net_20d_cny), note: '交易日累计' },
    ]
  }
  if (activeView.value === 'funding') {
    return [
      { label: 'AAA银行普通债1Y', value: formatRate(point.bank_bond_aaa_1y_yield_pct), note: '中债17:30' },
      { label: '国债1Y', value: formatRate(point.cgb_1y_yield_pct), note: '中债17:30' },
      { label: '银行负债利差', value: formatBp(point.factor_bank_funding_spread_bp), note: '银行债－国债' },
      { label: '利差百分位', value: formatScore(point.pct_bank_funding_spread), note: '排除当日' },
    ]
  }
  return [
    { label: '政策偏离百分位', value: formatScore(point.pct_fdr007_policy_spread), note: '权重40%' },
    { label: '隔夜挤压百分位', value: formatScore(point.pct_overnight_pressure), note: '权重20%' },
    { label: '机构分层百分位', value: formatScore(point.pct_nonbank_layering), note: '权重20%' },
    { label: '银行负债百分位', value: formatScore(point.pct_bank_funding_spread), note: '权重20%' },
  ]
})

const recentMonthlyTools = computed(() => (
  [...(dashboard.value?.monthly_tool_points ?? [])]
    .reverse()
    .slice(0, 24)
))

function formatScore(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : `${value.toFixed(1)}分`
}

function formatRate(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : `${value.toFixed(3)}%`
}

function formatBp(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : `${value.toFixed(1)}bp`
}

function formatYi(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value / 100_000_000).toFixed(0)}亿元`
}

function formatSignedYi(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '-'
  const yi = value / 100_000_000
  return `${yi > 0 ? '+' : ''}${yi.toFixed(0)}亿元`
}

function statusClass(state: string | null | undefined) {
  if (state === '紧张') return 'status-tight'
  if (state === '偏紧') return 'status-pressured'
  if (state === '宽松') return 'status-easy'
  return 'status-balanced'
}

async function loadDashboard() {
  loading.value = true
  error.value = ''
  try {
    dashboard.value = await fetchBankLiquidityDashboard('2017-05-31')
  } catch (rawError) {
    error.value =
      (rawError as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
      (rawError instanceof Error ? rawError.message : '银行流动性数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="macro" />
    <main class="dashboard-main liquidity-main">
      <nav class="macro-subnav" aria-label="宏观页面导航">
        <RouterLink to="/macro">综合指标</RouterLink>
        <RouterLink to="/macro/bank-liquidity" class="active">银行流动性</RouterLink>
      </nav>

      <header class="liquidity-header">
        <div>
          <h2>银行流动性</h2>
          <p>银行间资金价格、央行投放与银行负债压力</p>
        </div>
        <div v-if="dashboard?.coverage.latest_date" class="liquidity-asof">
          数据日期 {{ dashboard.coverage.latest_date }}
        </div>
      </header>

      <p v-if="error" class="banner-error">{{ error }}</p>
      <p v-if="loading && !dashboard" class="liquidity-loading">银行流动性数据加载中...</p>

      <template v-if="dashboard">
        <section class="liquidity-summary">
          <article class="summary-score">
            <span>流动性紧张度</span>
            <strong>{{ formatScore(scorePoint?.liquidity_tightness_score) }}</strong>
            <small>数据日 {{ scorePoint?.trade_date || '-' }}</small>
          </article>
          <article :class="['summary-state', statusClass(scorePoint?.liquidity_state)]">
            <span>当前状态</span>
            <strong>{{ scorePoint?.liquidity_state || '数据不完整' }}</strong>
            <small>0宽松 · 100紧张</small>
          </article>
          <article class="summary-trend">
            <span>5日趋势</span>
            <strong>{{ scorePoint?.liquidity_trend || '-' }}</strong>
            <small>{{ scorePoint?.score_change_5d == null ? '样本不足' : `${scorePoint.score_change_5d >= 0 ? '+' : ''}${scorePoint.score_change_5d.toFixed(1)}分` }}</small>
          </article>
        </section>

        <section class="context-grid">
          <article v-for="card in contextCards" :key="card.label">
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
            <small>{{ card.note }}</small>
          </article>
        </section>

        <section class="card liquidity-chart-panel">
          <div class="liquidity-toolbar">
            <div class="liquidity-tabs" role="tablist">
              <button
                v-for="item in views"
                :key="item.key"
                type="button"
                :class="{ active: activeView === item.key }"
                @click="activeView = item.key"
              >
                {{ item.label }}
              </button>
            </div>
            <div class="liquidity-range">
              <button type="button" :class="{ active: activeRange === '1y' }" @click="activeRange = '1y'">1年</button>
              <button type="button" :class="{ active: activeRange === '3y' }" @click="activeRange = '3y'">3年</button>
              <button type="button" :class="{ active: activeRange === 'all' }" @click="activeRange = 'all'">全部</button>
            </div>
          </div>
          <div class="liquidity-chart-title">
            <div>
              <h3>{{ chartConfig.title }}</h3>
              <p>{{ chartConfig.subtitle }}</p>
            </div>
            <span>{{ dashboard.daily_points.length }} 个官方数据日</span>
          </div>
          <BankLiquidityChart
            :points="chartPoints"
            :series="chartConfig.series"
            :visible-start-date="visibleStartDate"
          />
        </section>

        <section v-if="activeView === 'operations'" class="monthly-tools">
          <div class="section-title">
            <div>
              <h3>月度货币政策工具</h3>
              <p>{{ dashboard.coverage.monthly_tools_note }}</p>
            </div>
            <span>起始 {{ dashboard.coverage.monthly_tools_start || '-' }}</span>
          </div>
          <div class="monthly-table-wrap">
            <table>
              <thead>
                <tr><th>月份</th><th>类别</th><th>工具</th><th>投放</th><th>回笼</th><th>净投放</th><th>发布时间</th></tr>
              </thead>
              <tbody>
                <tr v-for="item in recentMonthlyTools" :key="`${item.period_end}-${item.tool_type}-${item.tool_name}`">
                  <td>{{ item.period_end.slice(0, 7) }}</td>
                  <td>{{ item.category || '-' }}</td>
                  <td><a :href="item.source_url" target="_blank" rel="noreferrer">{{ item.tool_name }}</a></td>
                  <td>{{ formatYi(item.injection_cny) }}</td>
                  <td>{{ formatYi(item.withdrawal_cny) }}</td>
                  <td :class="{ positive: (item.net_injection_cny ?? 0) > 0, negative: (item.net_injection_cny ?? 0) < 0 }">{{ formatSignedYi(item.net_injection_cny) }}</td>
                  <td>{{ item.published_at }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="coverage-band">
          <div><span>官方历史</span><strong>{{ dashboard.coverage.official_history_start || '-' }}</strong></div>
          <div><span>紧张度起始</span><strong>{{ dashboard.coverage.score_start || '样本不足' }}</strong></div>
          <div><span>日终DR/R起始</span><strong>{{ dashboard.coverage.closing_repo_start || '尚未积累' }}</strong></div>
          <div><span>最近完整日</span><strong>{{ dashboard.coverage.latest_complete_date || '-' }}</strong></div>
        </section>

        <section class="liquidity-notes">
          <article><h3>紧张度</h3><p>{{ dashboard.methodology.score }}</p></article>
          <article><h3>状态</h3><p>{{ dashboard.methodology.states }}</p></article>
          <article><h3>日终确认</h3><p>{{ dashboard.coverage.closing_repo_note }}</p></article>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.liquidity-main { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.macro-subnav { display: inline-flex; align-self: flex-start; gap: 3px; padding: 3px; border: 1px solid #dce3eb; border-radius: 6px; background: #f8fafc; }
.macro-subnav a { padding: 7px 12px; border-radius: 4px; color: #64748b; font-size: 13px; font-weight: 700; text-decoration: none; }
.macro-subnav a.active { background: #fff; color: #172033; box-shadow: 0 1px 3px rgba(15, 23, 42, .12); }
.liquidity-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 2px; }
.liquidity-header h2 { margin: 0 0 4px; color: #172033; font-size: 28px; letter-spacing: 0; }
.liquidity-header p { margin: 0; color: #64748b; }
.liquidity-asof { color: #475569; font-size: 13px; font-weight: 700; }
.liquidity-loading { padding: 40px; color: #64748b; text-align: center; }
.liquidity-summary { display: grid; grid-template-columns: 1.4fr 1fr 1fr; border: 1px solid #dce3eb; background: #fff; }
.liquidity-summary article { min-width: 0; padding: 15px 18px; border-right: 1px solid #dce3eb; border-top: 3px solid #2563eb; }
.liquidity-summary article:last-child { border-right: 0; }
.liquidity-summary span, .liquidity-summary small { display: block; color: #64748b; font-size: 12px; }
.liquidity-summary strong { display: block; margin: 5px 0 3px; color: #172033; font-size: 23px; font-variant-numeric: tabular-nums; }
.summary-state.status-easy { border-top-color: #0f766e; }
.summary-state.status-balanced { border-top-color: #2563eb; }
.summary-state.status-pressured { border-top-color: #d97706; }
.summary-state.status-tight { border-top-color: #dc2626; }
.context-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.context-grid article { min-width: 0; padding: 13px 15px; border: 1px solid #dce3eb; border-radius: 6px; background: #fff; }
.context-grid span, .context-grid small { display: block; color: #64748b; font-size: 11px; }
.context-grid strong { display: block; margin: 6px 0 4px; color: #172033; font-size: 18px; font-variant-numeric: tabular-nums; }
.liquidity-chart-panel { min-width: 0; padding: 17px; }
.liquidity-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.liquidity-tabs, .liquidity-range { display: flex; gap: 3px; padding: 3px; border: 1px solid #dce3eb; border-radius: 6px; background: #f8fafc; }
.liquidity-tabs button, .liquidity-range button { border: 0; border-radius: 4px; background: transparent; color: #526077; cursor: pointer; font-weight: 700; padding: 8px 11px; white-space: nowrap; }
.liquidity-tabs button.active, .liquidity-range button.active { background: #fff; color: #172033; box-shadow: 0 1px 3px rgba(15, 23, 42, .12); }
.liquidity-chart-title { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin: 18px 4px 9px; }
.liquidity-chart-title h3, .section-title h3 { margin: 0; color: #172033; font-size: 17px; }
.liquidity-chart-title p, .section-title p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
.liquidity-chart-title > span, .section-title > span { color: #64748b; font-size: 12px; white-space: nowrap; }
.monthly-tools { border: 1px solid #dce3eb; background: #fff; }
.section-title { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; padding: 16px 18px; border-bottom: 1px solid #dce3eb; }
.monthly-table-wrap { max-width: 100%; overflow-x: auto; }
.monthly-tools table { width: 100%; min-width: 860px; border-collapse: collapse; }
.monthly-tools th, .monthly-tools td { padding: 10px 12px; border-bottom: 1px solid #eef2f6; color: #475569; font-size: 12px; text-align: right; white-space: nowrap; }
.monthly-tools th:nth-child(-n+3), .monthly-tools td:nth-child(-n+3) { text-align: left; }
.monthly-tools th { background: #f8fafc; color: #64748b; font-weight: 700; }
.monthly-tools a { color: #2563eb; text-decoration: none; }
.positive { color: #0f766e !important; font-weight: 700; }
.negative { color: #dc2626 !important; font-weight: 700; }
.coverage-band { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #dce3eb; background: #fff; }
.coverage-band > div { padding: 13px 16px; border-right: 1px solid #dce3eb; }
.coverage-band > div:last-child { border-right: 0; }
.coverage-band span { display: block; color: #64748b; font-size: 11px; }
.coverage-band strong { display: block; margin-top: 5px; color: #172033; font-size: 15px; }
.liquidity-notes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; padding-bottom: 12px; }
.liquidity-notes article { padding: 3px 2px; }
.liquidity-notes h3 { margin: 0 0 5px; color: #334155; font-size: 14px; }
.liquidity-notes p { margin: 0; color: #64748b; font-size: 12px; line-height: 1.7; }
@media (max-width: 1180px) {
  .context-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .liquidity-notes { grid-template-columns: 1fr; }
}
@media (max-width: 820px) {
  .liquidity-header, .liquidity-toolbar, .liquidity-chart-title, .section-title { align-items: stretch; flex-direction: column; }
  .liquidity-summary, .context-grid, .coverage-band { grid-template-columns: 1fr; }
  .liquidity-summary article, .coverage-band > div { border-right: 0; border-bottom: 1px solid #dce3eb; }
  .liquidity-summary article:last-child, .coverage-band > div:last-child { border-bottom: 0; }
  .liquidity-tabs, .liquidity-range { max-width: 100%; overflow-x: auto; }
}
</style>
