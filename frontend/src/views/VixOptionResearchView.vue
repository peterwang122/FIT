<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { fetchVixOptionAnalysis } from '../api/research'
import type {
  VixBottomStatus,
  VixIndexSummary,
  VixOptionAnalysisReport,
  VixOptionRecommendation,
} from '../types/research'

type ResultTab = 'summary' | 'events' | 'combinations' | 'method'

const report = ref<VixOptionAnalysisReport | null>(null)
const loading = ref(true)
const error = ref('')
const selectedIndex = ref('')
const activeTab = ref<ResultTab>('summary')
const bottomFilter = ref<'all' | VixBottomStatus>('all')
const eventPage = ref(1)
const pageSize = 20

const selectedSummary = computed<VixIndexSummary | null>(
  () => report.value?.index_summaries.find((item) => item.index_name === selectedIndex.value) ?? null,
)
const filteredEvents = computed(() =>
  (report.value?.events ?? []).filter(
    (item) =>
      item.index_name === selectedIndex.value &&
      (bottomFilter.value === 'all' || item.bottom_status === bottomFilter.value),
  ),
)
const eventPageCount = computed(() => Math.max(1, Math.ceil(filteredEvents.value.length / pageSize)))
const pagedEvents = computed(() =>
  filteredEvents.value.slice((eventPage.value - 1) * pageSize, eventPage.value * pageSize),
)
const combinations = computed(() =>
  (report.value?.top_combinations ?? []).filter((item) => item.index_name === selectedIndex.value),
)
const overallConclusion = computed(() => report.value?.overall_conclusion ?? null)

watch([selectedIndex, bottomFilter], () => {
  eventPage.value = 1
})

function percent(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? '-' : `${(value * 100).toFixed(digits)}%`
}

function number(value: number | null | undefined, digits = 2) {
  return value == null || !Number.isFinite(value) ? '-' : value.toFixed(digits)
}

function strategyLabel(value: string | null | undefined) {
  if (value === 'long_call') return '单买认购'
  if (value === 'long_put') return '单买认沽'
  return '-'
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
  return `${item.product_code} / ${strategyLabel(item.strategy_type)} / ${item.expiry_bucket_label || item.dte_bucket} / ${item.moneyness_label}`
}

function directionLabel(value: string | null | undefined) {
  return value === 'bearish' ? '涨多后买认沽' : value === 'bullish' ? '跌后或震荡买认购' : '-'
}

function strike(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? '-' : value.toFixed(value >= 100 ? 0 : 3)
}

function exactTradeText(item: {
  hindsight_product_code?: string | null
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
  return `${item.hindsight_product_code}，${item.hindsight_contract_month_label || item.hindsight_dte_bucket || '-'}，${strategyLabel(item.hindsight_strategy_type)}，买${item.hindsight_long_contract || '-'}（${strikeText}），持有${item.hindsight_holding_days || '-'}日`
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
          <article><span>独立事件</span><strong>{{ selectedSummary.event_count }}</strong></article>
          <article><span>绝对VIX地板</span><strong>{{ number(selectedSummary.absolute_vix_floor, 0) }}</strong></article>
          <article><span>可验证事件</span><strong>{{ selectedSummary.complete_event_count }}</strong></article>
          <article><span>认购底部命中</span><strong>{{ percent(selectedSummary.bottom_hit_rate_3pct) }}</strong></article>
          <article><span>认沽高位有效</span><strong>{{ percent(selectedSummary.top_hit_rate_3pct) }}</strong></article>
        </div>

        <p class="research-note">
          这里的“长期参数模板”按当月、下月、季月1、季月2描述到期月份，行权档位按相对标的是高行权价还是低行权价展示。本版只做单买期权，不做价差；真正复盘某一天时，请看“高VIX事件”表里的具体合约月份、合约代码和行权价。
        </p>

        <article v-if="overallConclusion" class="overall-conclusion">
          <h4>最终结论</h4>
          <p>{{ overallConclusion.summary }}</p>
          <div class="research-table-wrap conclusion-rank-wrap">
            <table class="research-table conclusion-table">
              <thead><tr><th>排序</th><th>指数</th><th>主模板</th><th>收益中位数</th><th>25%收益分位</th><th>胜率</th><th>MAE</th></tr></thead>
              <tbody>
                <tr v-for="(item, index) in overallConclusion.rankings" :key="item.index_name">
                  <td>{{ index + 1 }}</td>
                  <td>{{ item.index_name }}</td>
                  <td>{{ item.product_code || '-' }} / {{ strategyLabel(item.strategy_type) }} / {{ item.expiry_bucket_label || '-' }} / {{ item.moneyness_label || '-' }} / {{ item.holding_days || '-' }}日</td>
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
            <h4>长期参数模板（回望平衡）</h4>
            <strong>{{ recommendationText(selectedSummary.recommendation) }}</strong>
            <dl v-if="selectedSummary.recommendation">
              <div><dt>VIX规则</dt><dd>{{ selectedSummary.recommendation.rule_label }}</dd></div>
              <div><dt>持仓周期</dt><dd>{{ selectedSummary.recommendation.holding_days }}个交易日</dd></div>
              <div><dt>收益中位数</dt><dd>{{ percent(selectedSummary.recommendation.net_return_median) }}</dd></div>
              <div><dt>胜率</dt><dd>{{ percent(selectedSummary.recommendation.win_rate) }}</dd></div>
              <div><dt>25%收益分位</dt><dd>{{ percent(selectedSummary.recommendation.net_return_p25) }}</dd></div>
              <div><dt>单笔MAE中位数</dt><dd>{{ percent(selectedSummary.recommendation.median_mae) }}</dd></div>
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
              <strong>{{ item.selected ? `入选，VIX ${number(item.vix_close)}` : '未入选' }}</strong>
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
        <div class="research-filter-row">
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
        <div class="research-table-wrap">
          <table class="research-table research-events-table">
            <thead><tr><th>日期</th><th>VIX/门槛</th><th>方向</th><th>前20日</th><th>前40日</th><th>判断</th><th>后10日最低</th><th>后10日最高</th><th>后20日最低</th><th>后20日最高</th><th>回望最佳具体合约</th><th>净收益</th><th>MAE</th></tr></thead>
            <tbody>
              <tr v-for="item in pagedEvents" :key="`${item.index_name}-${item.signal_date}`">
                <td>{{ item.signal_date.slice(0, 10) }}</td>
                <td>{{ number(item.vix_close) }} / {{ number(item.threshold_value) }}</td>
                <td :title="item.direction_reason">{{ directionLabel(item.trade_direction) }}</td>
                <td>{{ percent(item.prior_20d_return) }}</td>
                <td>{{ percent(item.prior_40d_return) }}</td>
                <td><span class="status-pill" :class="item.bottom_status">{{ bottomLabel(item.bottom_status) }}</span></td>
                <td>{{ percent(item.future_10d_min_return) }}</td>
                <td>{{ percent(item.future_10d_max_return) }}</td>
                <td>{{ percent(item.future_20d_min_return) }}</td>
                <td>{{ percent(item.future_20d_max_return) }}</td>
                <td class="trade-cell">{{ exactTradeText(item) }}</td>
                <td>{{ percent(item.hindsight_net_return) }}</td>
                <td>{{ percent(item.hindsight_mae) }}</td>
              </tr>
            </tbody>
          </table>
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
                <td>{{ item.product_code }} / {{ strategyLabel(item.strategy_type) }}</td>
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
.research-tabs, .research-filter-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0; }
.research-tabs button, .research-filter-row button, .research-pagination button {
  min-height: 34px; padding: 0 13px; border: 1px solid #dbe3ec; border-radius: 6px; background: #fff; color: #475569; font-weight: 700;
}
.research-tabs button.active, .research-filter-row button.active { border-color: #2563eb; background: #eff6ff; color: #1d4ed8; }
.research-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.research-kpis article { padding: 14px; border: 1px solid #e2e8f0; border-radius: 6px; background: #f8fafc; }
.research-kpis span { display: block; color: #64748b; font-size: 13px; }
.research-kpis strong { display: block; margin-top: 5px; color: #0f172a; font-size: 22px; }
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
.research-events-table { min-width: 1660px; }
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
  .research-kpis, .recommendation-grid, .reference-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 620px) {
  .research-panel { padding: 14px; }
  .research-head { align-items: stretch; flex-direction: column; }
  .research-index-select { width: 100%; }
  .research-kpis, .recommendation-grid, .reference-grid { grid-template-columns: 1fr; }
}
</style>
