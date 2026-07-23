<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { fetchVixOptionAnalysis } from '../api/research'
import VixEventTopTradesTable from '../components/VixEventTopTradesTable.vue'
import type {
  VixBottomStatus,
  VixOptionEvent,
  VixIndexSummary,
  VixOptionAnalysisReport,
  VixOptionRecommendation,
  VixThresholdModel,
} from '../types/research'

type ResultTab = 'summary' | 'events' | 'combinations' | 'method'
type LayoutVersion = 'table' | 'timeline' | 'workbench'
type ThresholdMode = 'max_return' | 'balanced'
type EventTypeFilter = 'all' | 'first_cross' | 'range_peak'

const report = ref<VixOptionAnalysisReport | null>(null)
const loading = ref(true)
const error = ref('')
const selectedIndex = ref('')
const activeTab = ref<ResultTab>('summary')
const bottomFilter = ref<'all' | VixBottomStatus>('all')
const layoutVersion = ref<LayoutVersion>('table')
const thresholdMode = ref<ThresholdMode>('balanced')
const eventTypeFilter = ref<EventTypeFilter>('all')
const expandedEventKeys = ref<string[]>([])
const selectedEventKey = ref('')
const eventPage = ref(1)
const pageSize = 20

const selectedSummary = computed<VixIndexSummary | null>(
  () => report.value?.index_summaries.find((item) => item.index_name === selectedIndex.value) ?? null,
)
const selectedThresholdModel = computed(
  () => selectedSummary.value?.threshold_models?.find((item) => item.mode === thresholdMode.value) ?? null,
)
const activeRecommendation = computed(
  () => selectedThresholdModel.value?.recommendation ?? selectedSummary.value?.recommendation ?? null,
)
const filteredEvents = computed(() =>
  (report.value?.events ?? [])
    .filter(
      (item) =>
        item.index_name === selectedIndex.value &&
        item.threshold_mode === thresholdMode.value &&
        (eventTypeFilter.value === 'all' || item.event_type === eventTypeFilter.value) &&
        (bottomFilter.value === 'all' || item.bottom_status === bottomFilter.value),
    )
    .sort((left, right) => right.signal_date.localeCompare(left.signal_date)),
)
const eventPageCount = computed(() => Math.max(1, Math.ceil(filteredEvents.value.length / pageSize)))
const pagedEvents = computed(() =>
  filteredEvents.value.slice((eventPage.value - 1) * pageSize, eventPage.value * pageSize),
)
const combinations = computed(() =>
  (report.value?.top_combinations ?? []).filter((item) => item.index_name === selectedIndex.value),
)
const overallConclusion = computed(() => report.value?.overall_conclusion ?? null)
const selectedEvent = computed(
  () => filteredEvents.value.find((item) => eventKey(item) === selectedEventKey.value) ?? filteredEvents.value[0] ?? null,
)

watch([selectedIndex, bottomFilter, thresholdMode, eventTypeFilter], () => {
  eventPage.value = 1
  expandedEventKeys.value = []
  selectedEventKey.value = ''
})

watch(layoutVersion, () => {
  expandedEventKeys.value = []
  selectedEventKey.value = filteredEvents.value[0] ? eventKey(filteredEvents.value[0]) : ''
})

function percent(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value * 100).toFixed(digits)}%`
}

function number(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? '-' : value.toFixed(digits)
}

function thresholdModelText(model: VixThresholdModel | null | undefined) {
  if (!model) return '-'
  if (model.source_thresholds?.length) {
    return model.source_thresholds
      .map((item) => `${item.source_name} ≥ ${number(item.threshold, 1)}`)
      .join(' / ')
  }
  return `VIX最高价 ≥ ${number(model.threshold, 1)}`
}

function strategyLabel(value: string | null | undefined) {
  if (value === 'long_call') return '单买认购'
  if (value === 'long_put') return '单买认沽'
  return '-'
}

function exchangeLabel(value: string | null | undefined) {
  if (value === 'SSE') return '上交所'
  if (value === 'SZSE') return '深交所'
  if (value === 'CFFEX') return '中金所'
  return value || '-'
}

function productLabel(item: { exchange?: string | null; product_name?: string | null }) {
  const parts = [exchangeLabel(item.exchange), item.product_name || ''].filter((value) => value && value !== '-')
  return parts.join(' ') || '-'
}

function bottomLabel(value: VixBottomStatus) {
  if (value === 'true_bottom') return '相对底部'
  if (value === 'false_bottom') return '假底部'
  if (value === 'true_top') return '高位有效'
  if (value === 'false_top') return '高位无效'
  return '待验证'
}

function recommendationText(item: VixOptionRecommendation | null) {
  if (!item) return '-'
  return `${productLabel(item)} / ${strategyLabel(item.strategy_type)} / ${item.expiry_bucket_label || item.dte_bucket} / ${item.moneyness_label}`
}

function directionLabel(value: string | null | undefined) {
  return value === 'bearish' ? '涨多后买认沽' : value === 'bullish' ? '跌后或震荡买认购' : '-'
}

function strike(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : value.toFixed(value >= 100 ? 0 : 3)
}

function exactTradeText(item: {
  hindsight_product_code?: string | null
  hindsight_product_name?: string | null
  hindsight_exchange?: string | null
  hindsight_strategy_type?: string | null
  hindsight_dte_bucket?: string | null
  hindsight_contract_month_label?: string | null
  hindsight_moneyness?: string | null
  hindsight_holding_days?: number | null
  hindsight_long_contract?: string | null
  hindsight_long_strike?: number | null
  hindsight_long_strike_label?: string | null
}) {
  if (!item.hindsight_product_code) return '-'
  const strikeText = item.hindsight_long_strike_label
    ? `行权价${strike(item.hindsight_long_strike)}，${item.hindsight_long_strike_label}`
    : `行权价${strike(item.hindsight_long_strike)}`
  const product = productLabel({ exchange: item.hindsight_exchange, product_name: item.hindsight_product_name })
  return `${product}，${item.hindsight_contract_month_label || item.hindsight_dte_bucket || '-'}，${strategyLabel(item.hindsight_strategy_type)}，${item.hindsight_long_strike_label || item.hindsight_moneyness || '-'}（${strikeText}，合约代码${item.hindsight_long_contract || '-'}），持有${item.hindsight_holding_days || '-'}日`
}

function eventKey(item: VixOptionEvent) {
  return `${item.index_name}-${item.threshold_mode}-${item.episode_id}-${item.event_type}-${item.signal_date}`
}

function toggleEvent(item: VixOptionEvent) {
  const key = eventKey(item)
  expandedEventKeys.value = expandedEventKeys.value.includes(key)
    ? expandedEventKeys.value.filter((itemKey) => itemKey !== key)
    : [...expandedEventKeys.value, key]
}

function isEventExpanded(item: VixOptionEvent) {
  return expandedEventKeys.value.includes(eventKey(item))
}

function selectEvent(item: VixOptionEvent) {
  selectedEventKey.value = eventKey(item)
}

function eventTypeClass(value: string) {
  return value === 'range_peak' ? 'peak' : 'first'
}

async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    const payload = await fetchVixOptionAnalysis()
    report.value = payload
    selectedIndex.value = payload.index_summaries[0]?.index_name ?? ''
  } catch (rawError) {
    error.value =
      (rawError as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
      (rawError instanceof Error ? rawError.message : '研究报告加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadReport)
</script>

<template>
  <section class="research-panel card">
    <p v-if="loading" class="muted">研究结果加载中...</p>
    <div v-else-if="error" class="research-error">
      <strong>{{ error }}</strong>
      <button type="button" class="btn secondary" @click="loadReport">重新加载</button>
    </div>
    <template v-else-if="report && selectedSummary">
      <header class="research-head">
        <div>
          <h3>VIX异常高与底部期权策略</h3>
          <p class="muted">更新时间 {{ new Date(report.generated_at).toLocaleString('zh-CN') }}</p>
        </div>
        <select v-model="selectedIndex" class="input research-index-select">
          <option v-for="item in report.index_summaries" :key="item.index_name" :value="item.index_name">
            {{ item.index_name }}
          </option>
        </select>
      </header>

      <div class="research-tabs" role="tablist">
        <button type="button" :class="{ active: activeTab === 'summary' }" @click="activeTab = 'summary'">结论</button>
        <button type="button" :class="{ active: activeTab === 'events' }" @click="activeTab = 'events'">高VIX事件</button>
        <button type="button" :class="{ active: activeTab === 'combinations' }" @click="activeTab = 'combinations'">参数排行</button>
        <button type="button" :class="{ active: activeTab === 'method' }" @click="activeTab = 'method'">研究口径</button>
      </div>

      <template v-if="activeTab === 'summary'">
        <div class="research-kpis">
          <article><span>高VIX区间</span><strong>{{ selectedThresholdModel?.episode_count ?? selectedSummary.episode_count ?? '-' }}</strong></article>
          <article><span>当前绝对阈值</span><strong class="threshold-kpi-value">{{ thresholdModelText(selectedThresholdModel) }}</strong></article>
          <article><span>可验证事件</span><strong>{{ selectedSummary.complete_event_count }}</strong></article>
          <article><span>认购底部命中</span><strong>{{ percent(selectedSummary.bottom_hit_rate_3pct) }}</strong></article>
          <article><span>认沽高位有效</span><strong>{{ percent(selectedSummary.top_hit_rate_3pct) }}</strong></article>
        </div>

        <div class="threshold-models">
          <button
            v-for="model in selectedSummary.threshold_models"
            :key="model.mode"
            type="button"
            :class="['threshold-model', { active: thresholdMode === model.mode }]"
            @click="thresholdMode = model.mode"
          >
            <span>{{ model.label }}</span>
            <strong>{{ thresholdModelText(model) }}</strong>
            <small>{{ model.episode_count }}个区间 / {{ model.event_date_count }}个交易日</small>
            <small v-if="model.recommendation">{{ recommendationText(model.recommendation) }}，样本{{ model.recommendation.trade_count }}次</small>
          </button>
        </div>

        <p class="research-note">
          每个指数只用一个绝对阈值划分连续高VIX区间；“首次突破”是当时可观察信号，“区间最高”是事后回望节点。列表只展示该日收益最高的一张期权，点开后查看前十。
        </p>

        <article v-if="overallConclusion" class="overall-conclusion">
          <h4>最终结论</h4>
          <p>{{ overallConclusion.summary }}</p>
          <div class="research-table-wrap conclusion-rank-wrap">
            <table class="research-table conclusion-table">
              <thead><tr><th>排序</th><th>指数</th><th>主模板</th><th>样本</th><th>收益中位数</th><th>25%收益分位</th><th>胜率</th><th>MAE</th></tr></thead>
              <tbody>
                <tr v-for="(item, index) in overallConclusion.rankings" :key="item.index_name">
                  <td>{{ index + 1 }}</td>
                  <td>{{ item.index_name }}</td>
                  <td>{{ productLabel(item) }} / {{ strategyLabel(item.strategy_type) }} / {{ item.expiry_bucket_label || '-' }} / {{ item.moneyness_label || '-' }} / {{ item.holding_days || '-' }}日</td>
                  <td>{{ item.trade_count ?? '-' }}</td>
                  <td>{{ percent(item.net_return_median) }}</td>
                  <td>{{ percent(item.net_return_p25) }}</td>
                  <td>{{ percent(item.win_rate) }}</td>
                  <td>{{ percent(item.median_mae) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>

        <div class="recommendation-grid">
          <article class="recommendation-block">
            <h4>{{ selectedThresholdModel?.label || '综合最优' }}参数模板（回望）</h4>
            <strong>{{ recommendationText(activeRecommendation) }}</strong>
            <dl v-if="activeRecommendation">
              <div><dt>绝对阈值</dt><dd>{{ thresholdModelText(selectedThresholdModel) }}</dd></div>
              <div><dt>持仓周期</dt><dd>{{ activeRecommendation.holding_days }}个交易日</dd></div>
              <div><dt>收益中位数</dt><dd>{{ percent(activeRecommendation.net_return_median) }}</dd></div>
              <div><dt>胜率</dt><dd>{{ percent(activeRecommendation.win_rate) }}</dd></div>
              <div><dt>25%收益分位</dt><dd>{{ percent(activeRecommendation.net_return_p25) }}</dd></div>
              <div><dt>样本/MAE</dt><dd>{{ activeRecommendation.trade_count }}次 / {{ percent(activeRecommendation.median_mae) }}</dd></div>
            </dl>
          </article>
          <article class="recommendation-block">
            <h4>低回撤模板（回望）</h4>
            <strong>{{ recommendationText(selectedSummary.defensive_recommendation) }}</strong>
            <dl v-if="selectedSummary.defensive_recommendation">
              <div><dt>VIX规则</dt><dd>{{ selectedSummary.defensive_recommendation.rule_label }}</dd></div>
              <div><dt>持仓周期</dt><dd>{{ selectedSummary.defensive_recommendation.holding_days }}个交易日</dd></div>
              <div><dt>收益中位数</dt><dd>{{ percent(selectedSummary.defensive_recommendation.net_return_median) }}</dd></div>
              <div><dt>胜率</dt><dd>{{ percent(selectedSummary.defensive_recommendation.win_rate) }}</dd></div>
              <div><dt>最差单笔</dt><dd>{{ percent(selectedSummary.defensive_recommendation.worst_loss) }}</dd></div>
              <div><dt>单笔MAE中位数</dt><dd>{{ percent(selectedSummary.defensive_recommendation.median_mae) }}</dd></div>
            </dl>
          </article>
        </div>

        <div class="reference-checks">
          <h4>关键日期校验</h4>
          <div class="reference-grid">
            <article v-for="item in selectedSummary.reference_checks" :key="item.signal_date" :class="{ selected: item.selected }">
              <span>{{ item.signal_date.slice(0, 10) }}</span>
              <strong>{{ item.selected ? `入选，VIX最高 ${number(item.vix_high ?? item.vix_close)}` : '未入选' }}</strong>
              <small>{{ item.selected ? directionLabel(item.trade_direction) : '未达到本指数绝对VIX门槛' }}</small>
            </article>
          </div>
        </div>

        <div v-if="selectedSummary.walk_forward" class="walk-forward-band">
          <h4>扩展窗口复核</h4>
          <dl>
            <div><dt>独立测试</dt><dd>{{ selectedSummary.walk_forward.trade_count }}次</dd></div>
            <div><dt>收益中位数</dt><dd>{{ percent(selectedSummary.walk_forward.net_return_median) }}</dd></div>
            <div><dt>胜率</dt><dd>{{ percent(selectedSummary.walk_forward.win_rate) }}</dd></div>
            <div><dt>25%收益分位</dt><dd>{{ percent(selectedSummary.walk_forward.net_return_p25) }}</dd></div>
            <div><dt>MAE中位数</dt><dd>{{ percent(selectedSummary.walk_forward.median_mae) }}</dd></div>
            <div><dt>最差单笔</dt><dd>{{ percent(selectedSummary.walk_forward.worst_loss) }}</dd></div>
          </dl>
        </div>

        <div class="research-table-wrap">
          <table class="research-table">
            <thead><tr><th>VIX规则</th><th>事件</th><th>认购底部3%</th><th>认沽高位3%</th></tr></thead>
            <tbody>
              <tr v-for="item in selectedSummary.threshold_performance" :key="item.rule_id">
                <td>{{ item.rule_label }}</td>
                <td>{{ item.complete_count }}/{{ item.event_count }}</td>
                <td>{{ percent(item.bottom_hit_rate_3pct) }}</td>
                <td>{{ percent(item.top_hit_rate_3pct) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else-if="activeTab === 'events'">
        <div class="layout-version-bar">
          <span>界面方案</span>
          <div class="segmented-control" role="group" aria-label="界面方案">
            <button type="button" :class="{ active: layoutVersion === 'table' }" @click="layoutVersion = 'table'">方案一 表格总览</button>
            <button type="button" :class="{ active: layoutVersion === 'timeline' }" @click="layoutVersion = 'timeline'">方案二 事件时间线</button>
            <button type="button" :class="{ active: layoutVersion === 'workbench' }" @click="layoutVersion = 'workbench'">方案三 左右分析台</button>
          </div>
        </div>
        <div class="research-filter-row">
          <div class="filter-group">
            <span>阈值</span>
            <button v-for="model in selectedSummary.threshold_models" :key="model.mode" type="button" :class="{ active: thresholdMode === model.mode }" @click="thresholdMode = model.mode">
              {{ model.label }} {{ thresholdModelText(model) }}
            </button>
          </div>
          <div class="filter-group">
            <span>事件</span>
            <button v-for="item in [
              { key: 'all', label: '全部' },
              { key: 'first_cross', label: '首次突破' },
              { key: 'range_peak', label: '区间最高' },
            ]" :key="item.key" type="button" :class="{ active: eventTypeFilter === item.key }" @click="eventTypeFilter = item.key as EventTypeFilter">
              {{ item.label }}
            </button>
          </div>
          <div class="filter-group">
            <span>判断</span>
          <button v-for="item in [
            { key: 'all', label: '全部' },
            { key: 'true_bottom', label: '相对底部' },
            { key: 'false_bottom', label: '假底部' },
            { key: 'true_top', label: '高位有效' },
            { key: 'false_top', label: '高位无效' },
            { key: 'incomplete', label: '待验证' },
          ]" :key="item.key" type="button" :class="{ active: bottomFilter === item.key }" @click="bottomFilter = item.key as typeof bottomFilter">
            {{ item.label }}
          </button>
          </div>
        </div>

        <div v-if="layoutVersion === 'table'" class="research-table-wrap">
          <table class="research-table research-events-table">
            <thead><tr><th>日期/类型</th><th>VIX最高/收盘/阈值</th><th>方向</th><th>前20/40日</th><th>判断</th><th>后20日区间</th><th>回望收益最高合约</th><th>净收益</th><th>MAE</th><th></th></tr></thead>
            <tbody>
              <template v-for="item in pagedEvents" :key="eventKey(item)">
                <tr>
                  <td><strong>{{ item.signal_date.slice(0, 10) }}</strong><span :class="['event-type', eventTypeClass(item.event_type)]">{{ item.event_type_label }}</span><small v-if="item.vix_source_label" class="event-source">{{ item.vix_source_label }}VIX</small></td>
                  <td>{{ number(item.vix_high) }} / {{ number(item.vix_close) }} / {{ number(item.threshold_value) }}</td>
                  <td :title="item.direction_reason">{{ directionLabel(item.trade_direction) }}</td>
                  <td>{{ percent(item.prior_20d_return) }} / {{ percent(item.prior_40d_return) }}</td>
                  <td><span class="status-pill" :class="item.bottom_status">{{ bottomLabel(item.bottom_status) }}</span></td>
                  <td>{{ percent(item.future_20d_min_return) }} 至 {{ percent(item.future_20d_max_return) }}</td>
                  <td class="trade-cell">{{ exactTradeText(item) }}</td>
                  <td class="strong-return">{{ percent(item.hindsight_net_return) }}</td>
                  <td>{{ percent(item.hindsight_mae) }}</td>
                  <td><button type="button" class="detail-button" @click="toggleEvent(item)">{{ isEventExpanded(item) ? '收起' : '前十' }}</button></td>
                </tr>
                <tr v-if="isEventExpanded(item)" class="expanded-row">
                  <td colspan="10"><VixEventTopTradesTable :trades="item.top_trades || []" :signal-date="item.signal_date" /></td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <div v-else-if="layoutVersion === 'timeline'" class="event-timeline">
          <article v-for="item in pagedEvents" :key="eventKey(item)" class="timeline-event">
            <div class="timeline-marker" :class="eventTypeClass(item.event_type)"></div>
            <div class="timeline-content">
              <header>
                <div><strong>{{ item.signal_date.slice(0, 10) }}</strong><span :class="['event-type', eventTypeClass(item.event_type)]">{{ item.event_type_label }}</span><span v-if="item.vix_source_label" class="event-source">{{ item.vix_source_label }}VIX</span></div>
                <span class="status-pill" :class="item.bottom_status">{{ bottomLabel(item.bottom_status) }}</span>
              </header>
              <div class="timeline-metrics">
                <span>VIX最高 <strong>{{ number(item.vix_high) }}</strong></span>
                <span>绝对阈值 <strong>{{ number(item.threshold_value) }}</strong></span>
                <span>方向 <strong>{{ directionLabel(item.trade_direction) }}</strong></span>
                <span>后20日 <strong>{{ percent(item.future_20d_min_return) }} 至 {{ percent(item.future_20d_max_return) }}</strong></span>
              </div>
              <p>{{ exactTradeText(item) }}</p>
              <div class="timeline-result"><strong>回望净收益 {{ percent(item.hindsight_net_return) }}</strong><span>MAE {{ percent(item.hindsight_mae) }}</span><button type="button" class="detail-button" @click="toggleEvent(item)">{{ isEventExpanded(item) ? '收起前十' : '查看前十' }}</button></div>
              <VixEventTopTradesTable v-if="isEventExpanded(item)" :trades="item.top_trades || []" :signal-date="item.signal_date" />
            </div>
          </article>
        </div>

        <div v-else class="event-workbench">
          <div class="workbench-list">
            <button v-for="item in pagedEvents" :key="eventKey(item)" type="button" :class="{ active: selectedEvent && eventKey(selectedEvent) === eventKey(item) }" @click="selectEvent(item)">
              <span><strong>{{ item.signal_date.slice(0, 10) }}</strong><small :class="['event-type', eventTypeClass(item.event_type)]">{{ item.event_type_label }}</small><small v-if="item.vix_source_label" class="event-source">{{ item.vix_source_label }}VIX</small></span>
              <span>{{ number(item.vix_high) }}<small>{{ bottomLabel(item.bottom_status) }}</small></span>
            </button>
          </div>
          <div v-if="selectedEvent" class="workbench-detail">
            <header><div><span class="muted">{{ selectedEvent.vix_source_label ? `${selectedEvent.vix_source_label}VIX` : 'VIX' }} / {{ selectedEvent.threshold_mode_label }}阈值 {{ number(selectedEvent.threshold_value) }}</span><h4>{{ selectedEvent.signal_date.slice(0, 10) }} {{ selectedEvent.event_type_label }}</h4></div><span class="status-pill" :class="selectedEvent.bottom_status">{{ bottomLabel(selectedEvent.bottom_status) }}</span></header>
            <div class="workbench-metrics">
              <div><span>VIX最高</span><strong>{{ number(selectedEvent.vix_high) }}</strong></div>
              <div><span>VIX收盘</span><strong>{{ number(selectedEvent.vix_close) }}</strong></div>
              <div><span>后20日最低</span><strong>{{ percent(selectedEvent.future_20d_min_return) }}</strong></div>
              <div><span>后20日最高</span><strong>{{ percent(selectedEvent.future_20d_max_return) }}</strong></div>
            </div>
            <div class="workbench-best"><span>回望收益最高</span><strong>{{ exactTradeText(selectedEvent) }}</strong><p>净收益 {{ percent(selectedEvent.hindsight_net_return) }}，MAE {{ percent(selectedEvent.hindsight_mae) }}</p></div>
            <VixEventTopTradesTable :trades="selectedEvent.top_trades || []" :signal-date="selectedEvent.signal_date" />
          </div>
        </div>

        <div class="research-pagination">
          <button type="button" :disabled="eventPage <= 1" @click="eventPage -= 1">上一页</button>
          <span>第 {{ eventPage }} / {{ eventPageCount }} 页，共 {{ filteredEvents.length }} 条</span>
          <button type="button" :disabled="eventPage >= eventPageCount" @click="eventPage += 1">下一页</button>
        </div>
      </template>

      <template v-else-if="activeTab === 'combinations'">
        <div class="research-table-wrap">
          <table class="research-table">
            <thead><tr><th>排名</th><th>VIX规则</th><th>产品/策略</th><th>到期月份/行权档位</th><th>持仓</th><th>样本</th><th>收益中位数</th><th>胜率</th><th>MAE</th></tr></thead>
            <tbody>
              <tr v-for="(item, index) in combinations" :key="`${item.rule_id}-${item.product_code}-${item.strategy_type}-${item.dte_bucket}-${item.moneyness_label}-${item.holding_days}`">
                <td>{{ index + 1 }}</td>
                <td>{{ item.rule_label }}</td>
                <td>{{ productLabel(item) }} / {{ strategyLabel(item.strategy_type) }}</td>
                <td>{{ item.expiry_bucket_label || item.dte_bucket }} / {{ item.moneyness_label }}</td>
                <td>{{ item.holding_days }}日</td>
                <td>{{ item.trade_count }}</td>
                <td>{{ percent(item.net_return_median) }}</td>
                <td>{{ percent(item.win_rate) }}</td>
                <td>{{ percent(item.median_mae) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <template v-else>
        <dl class="method-list">
          <div><dt>信号</dt><dd>{{ report.methodology.signal }}</dd></div>
          <div><dt>方向</dt><dd>{{ report.methodology.direction }}</dd></div>
          <div><dt>成交</dt><dd>{{ report.methodology.entry }}，单边滑点 {{ percent(report.methodology.slippage) }}</dd></div>
          <div><dt>底部定义</dt><dd>{{ report.methodology.bottom_definition }}</dd></div>
          <div><dt>高位定义</dt><dd>{{ report.methodology.top_definition }}</dd></div>
          <div><dt>持仓周期</dt><dd>{{ report.methodology.holding_days.join(' / ') }} 个交易日</dd></div>
          <div><dt>到期月份</dt><dd>{{ report.methodology.dte_buckets.join(' / ') }}</dd></div>
          <div><dt>行权档位</dt><dd>{{ report.methodology.moneyness.join(' / ') }}</dd></div>
        </dl>
      </template>
    </template>
  </section>
</template>

<style scoped>
.research-panel { padding: 22px; }
.research-head, .research-filter-row, .research-pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.research-head h3 { margin: 0 0 4px; }
.research-index-select { width: 150px; }
.layout-version-bar { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin: 18px 0 0; padding: 10px 0; border-top: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }
.layout-version-bar > span { flex: 0 0 auto; color: #64748b; font-size: 13px; font-weight: 700; }
.segmented-control { display: flex; flex-wrap: wrap; gap: 0; }
.segmented-control button { min-height: 34px; padding: 0 14px; border: 1px solid #cbd5e1; border-right-width: 0; background: #fff; color: #475569; font-weight: 700; }
.segmented-control button:first-child { border-radius: 6px 0 0 6px; }
.segmented-control button:last-child { border-right-width: 1px; border-radius: 0 6px 6px 0; }
.segmented-control button.active { border-color: #2563eb; background: #1d4ed8; color: #fff; }
.research-tabs, .research-filter-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0; }
.research-tabs button, .research-filter-row button, .research-pagination button {
  min-height: 34px; padding: 0 13px; border: 1px solid #dbe3ec; border-radius: 6px; background: #fff; color: #475569; font-weight: 700;
}
.research-tabs button.active, .research-filter-row button.active { border-color: #2563eb; background: #eff6ff; color: #1d4ed8; }
.research-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.research-kpis article { padding: 14px; border: 1px solid #e2e8f0; border-radius: 6px; background: #f8fafc; }
.research-kpis span { display: block; color: #64748b; font-size: 13px; }
.research-kpis strong { display: block; margin-top: 5px; color: #0f172a; font-size: 22px; }
.research-kpis .threshold-kpi-value { min-height: 40px; font-size: 13px; line-height: 1.55; }
.threshold-models { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.threshold-model { display: grid; gap: 5px; padding: 14px; border: 1px solid #dbe3ec; border-radius: 6px; background: #fff; text-align: left; color: #334155; }
.threshold-model > span { color: #64748b; font-size: 12px; font-weight: 800; }
.threshold-model > strong { color: #1e293b; font-size: 17px; }
.threshold-model > small { line-height: 1.5; }
.threshold-model.active { border-color: #2563eb; box-shadow: inset 3px 0 #2563eb; background: #eff6ff; }
.research-note { margin: 14px 0 0; padding: 12px 14px; border: 1px solid #dbeafe; border-radius: 6px; background: #eff6ff; color: #1e3a8a; font-size: 13px; line-height: 1.6; }
.overall-conclusion { margin-top: 14px; padding: 16px; border: 1px solid #bbf7d0; border-radius: 6px; background: #f0fdf4; }
.overall-conclusion h4 { margin: 0 0 8px; color: #14532d; }
.overall-conclusion p { margin: 0; color: #166534; line-height: 1.7; }
.conclusion-rank-wrap { margin-top: 12px; background: #fff; }
.conclusion-table { min-width: 980px; }
.recommendation-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 16px 0; }
.recommendation-block { padding: 18px; border: 1px solid #dbe3ec; border-radius: 6px; }
.recommendation-block h4 { margin: 0 0 8px; }
.recommendation-block > strong { display: block; min-height: 44px; color: #1e3a5f; }
.recommendation-block dl, .method-list { margin: 14px 0 0; }
.recommendation-block dl div, .method-list div, .walk-forward-band dl div { display: grid; grid-template-columns: 130px 1fr; gap: 12px; padding: 9px 0; border-top: 1px solid #edf2f7; }
.walk-forward-band { margin: 16px 0; padding: 16px 0; border-top: 1px solid #dbe3ec; border-bottom: 1px solid #dbe3ec; }
.walk-forward-band h4 { margin: 0; }
.walk-forward-band dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 18px; margin: 10px 0 0; }
.reference-checks { margin: 16px 0; }
.reference-checks h4 { margin: 0 0 10px; }
.reference-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.reference-grid article { padding: 12px; border: 1px solid #e2e8f0; border-radius: 6px; background: #f8fafc; }
.reference-grid article.selected { border-color: #93c5fd; background: #eff6ff; }
.reference-grid span, .reference-grid small { display: block; color: #64748b; }
.reference-grid strong { display: block; margin: 5px 0; color: #0f172a; }
dt { color: #64748b; } dd { margin: 0; font-weight: 700; color: #1e293b; }
.research-table-wrap { overflow-x: auto; border: 1px solid #e2e8f0; border-radius: 6px; }
.research-table { width: 100%; border-collapse: collapse; min-width: 760px; }
.research-table th, .research-table td { padding: 10px 12px; border-bottom: 1px solid #edf2f7; text-align: left; font-size: 13px; white-space: nowrap; }
.research-table th { background: #f8fafc; color: #475569; }
.research-events-table { min-width: 1480px; }
.research-filter-row { align-items: flex-start; }
.filter-group { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; padding-right: 12px; border-right: 1px solid #e2e8f0; }
.filter-group:last-child { border-right: 0; }
.filter-group > span { color: #64748b; font-size: 12px; font-weight: 800; }
.event-type { display: inline-flex; margin-left: 7px; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 800; white-space: nowrap; }
.event-type.first { background: #dbeafe; color: #1d4ed8; }
.event-type.peak { background: #ffedd5; color: #9a3412; }
.event-source { display: block; margin-top: 5px; color: #64748b; font-size: 11px; font-weight: 700; }
.strong-return { color: #166534; font-weight: 800; }
.detail-button { min-height: 30px; padding: 0 10px; border: 1px solid #93c5fd; border-radius: 5px; background: #eff6ff; color: #1d4ed8; font-weight: 800; }
.expanded-row > td { padding: 0 18px 16px !important; background: #f8fafc; }
.event-timeline { position: relative; display: grid; gap: 14px; padding-left: 25px; }
.event-timeline::before { content: ''; position: absolute; top: 10px; bottom: 10px; left: 8px; width: 1px; background: #cbd5e1; }
.timeline-event { position: relative; padding: 15px 16px; border: 1px solid #dbe3ec; border-radius: 6px; background: #fff; }
.timeline-marker { position: absolute; top: 19px; left: -23px; width: 12px; height: 12px; border: 3px solid #fff; border-radius: 50%; box-shadow: 0 0 0 1px #94a3b8; }
.timeline-marker.first { background: #2563eb; }
.timeline-marker.peak { background: #ea580c; }
.timeline-content > header, .timeline-result { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.timeline-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 13px 0; }
.timeline-metrics span { color: #64748b; font-size: 12px; }
.timeline-metrics strong { display: block; margin-top: 4px; color: #1e293b; font-size: 13px; }
.timeline-content p { margin: 0 0 13px; color: #334155; line-height: 1.6; }
.timeline-result { justify-content: flex-start; padding-top: 11px; border-top: 1px solid #edf2f7; }
.timeline-result > strong { color: #166534; }
.timeline-result > span { color: #64748b; }
.timeline-result .detail-button { margin-left: auto; }
.event-workbench { display: grid; grid-template-columns: minmax(220px, 300px) minmax(0, 1fr); min-height: 560px; border: 1px solid #dbe3ec; border-radius: 6px; overflow: hidden; }
.workbench-list { overflow-y: auto; border-right: 1px solid #dbe3ec; background: #f8fafc; }
.workbench-list button { display: flex; width: 100%; min-height: 62px; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 0; border-bottom: 1px solid #e2e8f0; background: transparent; color: #334155; text-align: left; }
.workbench-list button.active { background: #eff6ff; box-shadow: inset 3px 0 #2563eb; }
.workbench-list button > span { display: grid; gap: 5px; }
.workbench-list button > span:last-child { justify-items: end; }
.workbench-list small { color: #64748b; font-size: 11px; }
.workbench-detail { min-width: 0; padding: 18px; }
.workbench-detail > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.workbench-detail h4 { margin: 5px 0 0; font-size: 19px; }
.workbench-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 18px 0; }
.workbench-metrics div { padding: 11px; border-left: 2px solid #cbd5e1; background: #f8fafc; }
.workbench-metrics span { display: block; color: #64748b; font-size: 12px; }
.workbench-metrics strong { display: block; margin-top: 5px; color: #1e293b; }
.workbench-best { padding: 14px 0; border-top: 1px solid #dbe3ec; border-bottom: 1px solid #dbe3ec; }
.workbench-best span, .workbench-best strong { display: block; }
.workbench-best span { color: #64748b; font-size: 12px; }
.workbench-best strong { margin-top: 6px; color: #1e293b; line-height: 1.6; }
.workbench-best p { margin: 7px 0 0; color: #166534; font-weight: 800; }
.cross-vix-section h4 { margin: 18px 0 10px; }
.cross-vix-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
.cross-vix-head h4 { margin: 0 0 6px; }
.cross-vix-head p { margin: 0; max-width: 840px; line-height: 1.6; }
.cross-vix-head > strong { flex: 0 0 auto; color: #1e3a5f; }
.cross-vix-subhead { margin-top: 26px !important; }
.cross-vix-table { min-width: 1180px; }
.trade-cell { min-width: 360px; white-space: normal !important; line-height: 1.5; }
.status-pill { display: inline-flex; padding: 3px 8px; border-radius: 999px; font-weight: 700; }
.status-pill.true_bottom { background: #dcfce7; color: #166534; }
.status-pill.false_bottom { background: #fee2e2; color: #991b1b; }
.status-pill.true_top { background: #ffedd5; color: #9a3412; }
.status-pill.false_top { background: #f1f5f9; color: #475569; }
.status-pill.incomplete { background: #f1f5f9; color: #475569; }
.research-pagination { margin-top: 14px; justify-content: flex-end; color: #64748b; }
.research-pagination button:disabled { opacity: .45; }
.research-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #b91c1c; }
@media (max-width: 900px) {
  .research-kpis, .recommendation-grid, .reference-grid, .threshold-models { grid-template-columns: 1fr 1fr; }
  .timeline-metrics, .workbench-metrics { grid-template-columns: 1fr 1fr; }
  .event-workbench { grid-template-columns: 220px minmax(0, 1fr); }
}
@media (max-width: 620px) {
  .research-panel { padding: 14px; }
  .research-head { align-items: stretch; flex-direction: column; }
  .cross-vix-head { flex-direction: column; }
  .research-index-select { width: 100%; }
  .layout-version-bar { align-items: stretch; flex-direction: column; }
  .segmented-control { display: grid; grid-template-columns: 1fr; }
  .segmented-control button, .segmented-control button:first-child, .segmented-control button:last-child { border: 1px solid #cbd5e1; border-radius: 5px; }
  .research-kpis, .recommendation-grid, .reference-grid, .threshold-models { grid-template-columns: 1fr; }
  .filter-group { width: 100%; border-right: 0; }
  .timeline-metrics, .workbench-metrics { grid-template-columns: 1fr 1fr; }
  .timeline-result { align-items: flex-start; flex-direction: column; }
  .timeline-result .detail-button { margin-left: 0; }
  .event-workbench { grid-template-columns: 1fr; }
  .workbench-list { max-height: 260px; border-right: 0; border-bottom: 1px solid #dbe3ec; }
}
</style>
