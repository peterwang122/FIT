<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchMarketRegime } from '../api/marketRegime'
import AppSidebar from '../components/AppSidebar.vue'
import MarketRegimeChart from '../components/MarketRegimeChart.vue'
import MarketRegimeMacroEvidence from '../components/MarketRegimeMacroEvidence.vue'
import {
  regimeColors, regimeLabels, regimePermissions, regimeMissingLabels,
  type MarketRegimeDashboard, type RegimeIndex, type RegimePoint, type RegimeEvent, type RegimeWindow,
} from '../types/marketRegime'

const indexCode = ref<RegimeIndex>('sh000985')
const dashboard = shallowRef<MarketRegimeDashboard | null>(null)
const loading = ref(false)
const error = ref('')
const committedDate = ref('')
const previewDate = ref<string | null>(null)
const focusDate = ref('')
const focusRevision = ref(0)
const eventPage = ref(0)
const historyTab = ref<'events' | 'gaps'>('events')
const eventWindow = ref<RegimeWindow>(20)
const historyPeriod = ref<'all' | 'recent'>('recent')
const comparisonKey = ref('sh000985')
const comparison = computed(() => dashboard.value?.strategy_comparison)
const selectedComparison = computed(() => comparison.value?.results.find(row => row.key === comparisonKey.value))
const affectedEntries = computed(() => selectedComparison.value?.restricted_entries.filter(row => row.baseline_bought) ?? [])
const windows: RegimeWindow[] = [5, 10, 20, 60]
let request: AbortController | null = null
let sequence = 0
const points = computed(() => dashboard.value?.points ?? [])
const pointMap = computed(() => new Map(points.value.map(point => [point.date, point])))
const lockedPoint = computed(() => pointMap.value.get(committedDate.value) ?? null)
const displayPoint = computed(() => pointMap.value.get(previewDate.value ?? '') ?? lockedPoint.value)
const macroAt = (date: string) => [...(dashboard.value?.lightweight_research?.macro_regime_timeline ?? [])].reverse().find(row => row.date <= date)
const displayMacro = computed(() => macroAt(displayPoint.value?.date ?? ''))
const lockedMacro = computed(() => macroAt(committedDate.value))
const macroDirection = (value: number | null) => value == null ? '未核验' : value > 0 ? '改善 / 支持' : value < 0 ? '走弱' : '分化'
const events = computed(() => [...(dashboard.value?.events ?? [])]
  .filter(event => historyPeriod.value === 'all' || event.start >= '2024-01-01').reverse())
const gaps = computed(() => [...(dashboard.value?.coverage_gaps ?? [])]
  .filter(gap => historyPeriod.value === 'all' || gap.end >= '2024-01-01').reverse())
const pageEvents = computed(() => events.value.slice(eventPage.value * 6, eventPage.value * 6 + 6))
const pageGaps = computed(() => gaps.value.slice(eventPage.value * 6, eventPage.value * 6 + 6))
const eventPages = computed(() => Math.ceil((historyTab.value === 'events' ? events.value.length : gaps.value.length) / 6))
const eventStats = computed(() => {
  const complete = events.value.filter(event => eventChange(event, 'drawdown') != null && eventChange(event, 'upside') != null)
  return {
    complete: complete.length, pending: events.value.length - complete.length,
    decline: complete.filter(event => eventChange(event, 'drawdown')! <= -5).length,
    missedRise: complete.filter(event => eventChange(event, 'drawdown')! > -3 && eventChange(event, 'upside')! >= 5).length,
  }
})
const ruleNames: Record<string, string> = { warning: '转弱观察', bear: '结构转熊', shock: '深度破坏', repair: '熊市修复', bull: '牛市确认' }
const triggerNames: Record<string, string> = { ...ruleNames, initial: '初始观察', pullback: '牛市内调整' }
const ruleRows = computed(() => (lockedPoint.value?.rules ?? []).map(rule => ({ ...rule, label: ruleNames[rule.key] ?? rule.key, threshold: dashboard.value?.model_rules?.[rule.key] ?? '' })))
const snapshotTime = computed(() => dashboard.value
  ? new Date(dashboard.value.generated_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '')

async function load() {
  request?.abort()
  const current = ++sequence
  request = new AbortController()
  loading.value = true
  error.value = ''
  dashboard.value = null
  previewDate.value = null
  committedDate.value = ''
  focusDate.value = ''
  eventPage.value = 0
  try {
    const response = await fetchMarketRegime(indexCode.value, request.signal)
    if (current !== sequence) return
    dashboard.value = response
    committedDate.value = response.latest?.date ?? ''
  } catch (cause) {
    if (current !== sequence || request?.signal.aborted) return
    const detail = (cause as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    error.value = typeof detail === 'string' ? detail : '市场环境加载失败，请稍后重试'
  } finally {
    if (current === sequence) loading.value = false
  }
}

function confirmDate(date: string, center = false) {
  const point = [...points.value].reverse().find(item => item.date <= date)
  if (!point) return
  committedDate.value = point.date
  previewDate.value = null
  if (center) {
    focusDate.value = point.date
    focusRevision.value++
  }
}

function changeDate(event: Event) {
  confirmDate((event.target as HTMLInputElement).value, true)
  ;(event.target as HTMLInputElement).value = committedDate.value
}

function number(value: number | null | undefined, precision = 2, suffix = '') {
  return value == null || !Number.isFinite(value) ? '缺失' : `${value.toFixed(precision)}${suffix}`
}
function relativeMA(point: RegimePoint | null) {
  return point?.medium_ma ? (point.close / point.medium_ma - 1) * 100 : null
}
function breadthNote(point: RegimePoint | null) {
  if (!point) return '暂无数据'
  if (point.evidence_mode === 'index_proxy') {
    return `三宽基指数MA60参与度 ${number(point.breadth_medium, 1, '%')}；MA120参与度 ${number(point.breadth_long, 1, '%')}。${point.state === 'unavailable' ? '指数缺值或窗口不足。' : '沪深300、中证500、中证1000均完整。'}`
  }
  if (point.breadth_long == null) return '历史广度缺失或均线样本不足，未填补数据。'
  return `MA60以上 ${number(point.breadth_medium, 1, '%')}；MA120以上 ${number(point.breadth_long, 1, '%')}。MA120可评估 ${number(point.eligible, 0)} 只，覆盖 ${number(coverage(point), 2, '%')}。`
}

function coverage(point: RegimePoint | null) {
  if (point?.coverage_pct != null) return point.coverage_pct
  return point?.traded && point.eligible != null ? point.eligible / point.traded * 100 : null
}
function missingNote(point: RegimePoint | null) {
  return point?.missing_reasons?.map(reason => regimeMissingLabels[reason]).join('；') || '历史样本或来源覆盖待核验'
}
function sourceNote(point: RegimePoint | null) {
  if (point?.evidence_mode === 'index_proxy') return '三宽基指数代理 · 每日轻量更新'
  const source = dashboard.value?.breadth_sources?.find(item => point && item.start <= point.date && item.end >= point.date)
  return source?.table === 'stock_hfq_daily_data' ? '回补后复权 · 独立均线窗口' : '历史后复权 · 覆盖待审计'
}
function eventChange(event: RegimeEvent, kind: 'drawdown' | 'upside') {
  return event[`${kind}_${eventWindow.value}d_pct`] ?? null
}
function selectGap(date: string) {
  confirmDate(date, true)
}

watch(indexCode, load, { immediate: true })
watch([historyTab, historyPeriod], () => { eventPage.value = 0 })
onBeforeUnmount(() => { sequence++; request?.abort() })
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="macro" />
    <main class="dashboard-main regime-main">
      <nav class="macro-subnav" aria-label="宏观页面导航">
        <RouterLink to="/macro">综合指标</RouterLink>
        <RouterLink to="/macro/bank-liquidity">银行流动性</RouterLink>
        <RouterLink to="/macro/market-regime" class="active" aria-current="page">市场环境</RouterLink>
      </nav>
      <div class="regime-head">
        <div><h2>市场环境</h2><p class="regime-note">全A主环境 · 指数适配 · 宏观证据</p></div>
        <select v-model="indexCode" class="regime-control" aria-label="观察指数">
          <option value="sh000985">中证全指 · 全A主环境</option>
          <option value="sh000300">沪深300 · 策略适用环境</option>
          <option value="sh000852">中证1000 · 策略适用环境</option>
        </select>
      </div>
      <div v-if="loading" class="regime-empty" role="status">正在加载研究快照…</div>
      <div v-else-if="error" class="regime-error" role="alert">{{ error }} <button class="btn btn-secondary btn-compact" @click="load">重试</button></div>
      <template v-else-if="dashboard">
        <div class="regime-warning">指数日更至{{ dashboard.daily_as_of ?? dashboard.history_end }} · {{ dashboard.rule_name }}。牛市内调整不再直接停买；宏观确认结构转弱或修复。宏观版本未核验的历史仅为指数基线，候选模型不控制实际买卖。快照：{{ snapshotTime }}（北京时间）。</div>
        <div v-if="!points.length" class="regime-empty" role="status">所选指数暂无研究数据</div>
        <template v-else>
          <div class="regime-stats">
            <div class="regime-stat"><label>环境状态 <span data-testid="regime-preview-date">{{ displayPoint?.date }}</span></label>
              <strong :style="{ color: displayPoint?.state === 'unavailable' ? '#64748b' : regimeColors[displayPoint?.state ?? 'unavailable'] }">{{ regimeLabels[displayPoint?.state ?? 'unavailable'] }}</strong>
              <small>{{ displayPoint?.state === 'unavailable' ? '指数数据不足' : displayPoint?.macro_complete ? '指数 + 宏观 · 研究候选' : '指数基线 · 宏观未核验' }}</small>
            </div>
            <div class="regime-stat"><label>策略适配 · 研究</label><strong>{{ regimePermissions[displayPoint?.state ?? 'unavailable'] }}</strong><small>未接入实际交易或自动停买</small></div>
            <div class="regime-stat"><label data-testid="regime-index-name">{{ dashboard.index_name }}</label><strong>{{ number(displayPoint?.close) }}</strong><small>日线收盘</small></div>
          </div>
          <div class="regime-chart-row">
            <MarketRegimeChart :key="indexCode" :points="points" :committed-date="committedDate" :focus-date="focusDate" :focus-revision="focusRevision" @preview="previewDate = $event" @confirm="confirmDate($event)" />
            <aside class="regime-review">
              <h3>日期复盘 <span class="regime-badge" data-testid="regime-review-date">{{ displayPoint?.date }}</span></h3>
              <div v-if="displayPoint?.state_since" class="regime-evidence-line"><b>状态来源</b><span>{{ displayPoint.state_since }} · {{ triggerNames[displayPoint.trigger_rule ?? ''] }}；未满足切换条件时延续，不以单日反弹解除。</span></div>
              <div class="regime-evidence-line"><b>市场趋势</b><span>收盘 / MA60：{{ number(relativeMA(displayPoint), 2, '%') }}；MA120的20日变化：{{ number(displayPoint?.long_slope == null ? null : displayPoint.long_slope * 100, 2, '%') }}</span></div>
              <div class="regime-evidence-line"><b>指数参与度{{ displayPoint?.state === 'unavailable' ? ' · 数据不足' : '' }}</b><span>{{ breadthNote(displayPoint) }}</span></div>
              <div class="regime-evidence-line"><b>宏观确认</b><span v-if="displayPoint?.macro_complete">{{ displayMacro?.support_count }}组支持，{{ displayMacro?.adverse_count }}组走弱；{{ displayPoint?.macro_applied ? '本日提前确认切换' : '本日未因宏观提前切换' }}</span><span v-else>当时版本不完整，仅指数基线；不倒填最新宏观值。</span></div>
              <div class="regime-evidence-line"><b>{{ displayPoint?.state === 'unavailable' ? '数据核验' : '候选买入额度' }}</b><span>{{ displayPoint?.state === 'unavailable' ? missingNote(displayPoint) : `原策略买入额度的${number((displayPoint?.buy_multiplier ?? 0) * 100, 0, '%')}；持仓卖出仍按原策略。` }}</span></div>
            </aside>
          </div>
          <section class="regime-section">
            <div class="regime-section-head"><h3>底层证据 <span class="regime-badge" data-testid="regime-locked-date">{{ committedDate }} · 已锁定</span></h3>
              <input class="regime-control" type="date" :value="committedDate" :min="dashboard.history_start ?? undefined" :max="dashboard.history_end ?? undefined" aria-label="确认复盘日期" @change="changeDate" />
            </div>
            <div class="regime-table-wrap"><table class="regime-table"><thead><tr><th>证据</th><th>当日值</th><th>判断依据</th><th>数据口径</th></tr></thead><tbody>
              <tr><td>中期趋势</td><td>{{ number(relativeMA(lockedPoint), 2, '%') }}</td><td>收盘相对MA60</td><td>指数日线</td></tr>
              <tr><td>长期趋势</td><td>{{ number(lockedPoint?.long_slope == null ? null : lockedPoint.long_slope * 100, 2, '%') }}</td><td>MA120相对20日前</td><td>指数日线</td></tr>
              <tr><td>长期结构</td><td>MA250 {{ number(lockedPoint?.annual_ma) }}；20日变化 {{ number(lockedPoint?.annual_slope_pct, 2, '%') }}</td><td>长期结构破坏后才确认转熊</td><td>指数日线</td></tr>
              <tr><td>MA60 / MA120 / MA250参与度</td><td>{{ number(lockedPoint?.breadth_medium, 1, '%') }} / {{ number(lockedPoint?.breadth_long, 1, '%') }} / {{ number(lockedPoint?.breadth_annual, 1, '%') }}</td><td>改善至少2/3；转弱至多1/3</td><td>{{ sourceNote(lockedPoint) }}</td></tr>
              <tr><td>250日高点回撤</td><td>{{ number(lockedPoint?.drawdown_250d_pct, 2, '%') }}</td><td>20%深度破坏须同时满足趋势及参与度条件</td><td>历史收盘高点，无未来极值</td></tr>
              <tr><td>{{ lockedPoint?.evidence_mode === 'index_proxy' ? '完整代理指数 / 应有指数' : 'MA120可评估 / 当日交易' }}</td><td>{{ number(lockedPoint?.eligible, 0) }} / {{ number(lockedPoint?.traded, 0) }}<small data-testid="regime-coverage">有效覆盖 {{ number(coverage(lockedPoint), 2, '%') }}</small></td><td>{{ lockedPoint?.evidence_mode === 'index_proxy' ? '沪深300、中证500、中证1000三条指数均需完整' : '至少500只交易股票；完整120日窗口覆盖至少60%' }}</td><td>{{ lockedPoint?.evidence_mode === 'index_proxy' ? '每日只采集4条指数，不逐股采集' : '停牌、新股及原始缺口待区分' }}</td></tr>
            </tbody></table></div>
            <p v-if="lockedPoint?.state === 'unavailable'" class="regime-data-warning" data-testid="regime-missing-reason">{{ missingNote(lockedPoint) }}。该日不给出低吸许可，不计入有效停买事件。</p>
            <div class="regime-table-wrap regime-rules"><table class="regime-table"><thead><tr><th>规则确认</th><th>当日条件</th><th>连续 / 所需交易日</th><th>全部条件</th></tr></thead><tbody>
              <tr v-for="rule in ruleRows" :key="rule.key" :data-rule="rule.key"><td>{{ rule.label }}</td><td>{{ rule.met == null ? '数据不足' : rule.met ? '满足' : '未满足' }}</td><td>{{ rule.met == null ? '—' : number(rule.streak, 0) }} / {{ rule.days }}</td><td>{{ rule.threshold }}</td></tr>
            </tbody></table></div>
            <p class="regime-note">收盘后确认，下一交易日观察。指数缺失打断连续计数，不解除此前熊市状态。牛市内调整保留100%研究额度，转弱及修复为50%，熊市为0%；不改变已保存策略。</p>
            <div class="regime-table-wrap"><table class="regime-table"><thead><tr><th>宏观确认组</th><th>当前方向</th><th>判定依据</th></tr></thead><tbody>
              <tr v-for="group in lockedMacro?.groups ?? []" :key="group.key"><td>{{ group.label }}</td><td>{{ macroDirection(group.direction) }}</td><td>{{ group.key === 'money_credit' ? 'M1-M2增速差与社融存量同比的3个月变化同向' : group.key === 'activity' ? 'PMI、新订单的3个月均值与3个月变化共同确认' : '利润与营业收入官方累计同比同向，不推算单月利润' }}</td></tr>
            </tbody></table></div>
            <p class="regime-note">至少两组走弱，价格转弱/转熊确认由10日缩短至5日；至少两组改善，价格修复确认由5日缩短至3日。宏观不能单独把牛市改成熊市，也不能凭空确认牛市。</p>
          </section>
          <MarketRegimeMacroEvidence :date="committedDate" :research="dashboard.lightweight_research ?? null" />
          <section v-if="comparison" class="regime-section" data-testid="regime-strategy-comparison">
            <div class="regime-section-head"><h3>情绪强化测试 · 买入限制对照</h3><span class="regime-note">{{ comparison.start_date }} 至 {{ comparison.end_date }}</span></div>
            <p class="regime-note">同一套当前信号与{{ comparison.execution_asset }}成交价格，只改变新买入许可。红买蓝卖，每次总资产50%，次日开盘；含期末持仓浮盈亏，无手续费和滑点。原策略未修改。</p>
            <p v-if="comparison.signal_data_quality && !comparison.signal_data_quality.strict_replay_complete" class="regime-data-warning">{{ comparison.signal_data_quality.note }}</p>
            <p v-if="comparison.end_date !== dashboard.daily_as_of" class="regime-data-warning">研究报告截至{{ comparison.end_date }}，不代表之后交易日；日更环境已更新至{{ dashboard.daily_as_of }}。</p>
            <div class="regime-table-wrap"><table class="regime-table"><thead><tr><th>限制口径</th><th>累计收益</th><th>最大回撤</th><th>比原策略少赚</th><th>原有买入被阻止 / 减半</th></tr></thead><tbody>
              <tr v-for="row in comparison.results" :key="row.key"><td>{{ row.label }}</td><td>{{ number(row.return_pct, 2, '%') }}</td><td>{{ number(row.mdd_pct, 2, '%') }}</td><td>{{ number(row.missed_return_pp, 2, '个百分点') }}</td><td>{{ row.blocked_baseline_buys }} / {{ row.reduced_baseline_buys }}<small v-if="row.missing_gate_days.length">{{ row.missing_gate_days.length }}日数据缺失</small></td></tr>
            </tbody></table></div>
            <details class="regime-method"><summary>查看受影响买入与研究口径</summary>
              <select v-model="comparisonKey" class="regime-control" aria-label="受限买入对照口径"><option v-for="row in comparison.results.filter(row => row.key !== 'ungated')" :key="row.key" :value="row.key">{{ row.label }}</option></select>
              <div class="regime-table-wrap"><table class="regime-table"><thead><tr><th>信号日</th><th>次日成交日</th><th>限制状态</th><th>后20日收盘收益</th><th>后20日最高 / 最低价变化</th></tr></thead><tbody>
                <tr v-for="row in affectedEntries" :key="row.signal_date"><td><button class="regime-date-link" @click="confirmDate(row.signal_date, true)">{{ row.signal_date }}</button></td><td>{{ row.execution_date }}</td><td>{{ regimeLabels[row.state] }} · {{ row.multiplier === 0 ? '不买入' : '半额' }}</td><td>{{ row.return_20d_pct == null ? '待验证' : number(row.return_20d_pct, 2, '%') }}</td><td>{{ number(row.upside_20d_pct, 2, '%') }} / {{ number(row.drawdown_20d_pct, 2, '%') }}</td></tr>
                <tr v-if="!affectedEntries.length"><td colspan="5">无原策略实际买入受到限制</td></tr>
              </tbody></table></div>
              <p v-for="note in comparison.notes" :key="note">{{ note }}</p>
              <p v-if="comparison.signal_data_quality?.missing_emotion_dates.length">原始情绪缺失日：{{ comparison.signal_data_quality.missing_emotion_dates.join('、') }}</p>
              <p>保存策略起点{{ comparison.saved_start_date }}；本次仅研究回放延伸到2024-09-24。策略配置更新时间{{ comparison.strategy_updated_at }}。</p>
            </details>
          </section>
          <section class="regime-section">
            <div class="regime-section-head"><div class="regime-history-tabs" role="tablist" aria-label="历史记录类型"><button role="tab" :aria-selected="historyTab === 'events'" @click="historyTab = 'events'">转弱 / 熊市事件</button><button role="tab" :aria-selected="historyTab === 'gaps'" @click="historyTab = 'gaps'">数据缺口</button></div>
              <div class="regime-history-controls"><select v-model="historyPeriod" class="regime-control" aria-label="历史评估区间"><option value="recent">2024年至今</option><option value="all">全部历史</option></select><select v-if="historyTab === 'events'" v-model="eventWindow" class="regime-control" aria-label="事件前瞻窗口"><option v-for="window in windows" :key="window" :value="window">后{{ window }}个交易日</option></select></div>
            </div>
            <template v-if="historyTab === 'events'">
            <p class="regime-event-summary" data-testid="regime-event-summary">{{ events.length }}段转弱 / 熊市 · {{ eventStats.complete }}段窗口完整 · 其中{{ eventStats.decline }}段下探≥5% · {{ eventStats.missedRise }}段回撤&lt;3%且上涨≥5% · {{ eventStats.pending }}段待验证</p>
            <p class="regime-note">以首次触发日收盘为基准；未完成窗口或缺少区间高低价不参与统计，数据缺口不算停买命中。</p>
            <div v-if="!events.length" class="regime-empty">暂无转弱 / 熊市事件</div>
            <div v-else class="regime-table-wrap"><table class="regime-table"><thead><tr><th>开始日期</th><th>最后风险日 / 恢复日</th><th>交易日</th><th>后{{ eventWindow }}日最低价变化</th><th>后{{ eventWindow }}日最高价变化</th></tr></thead><tbody>
              <tr v-for="event in pageEvents" :key="event.start" :data-event-date="event.start" :class="{ selected: committedDate === event.start }" @click="confirmDate(event.start, true)">
                <td><button class="regime-date-link" :aria-label="`复盘${event.start}事件`" @click.stop="confirmDate(event.start, true)">{{ event.start }}</button></td>
                <td>{{ event.end }}<small v-if="!event.closed">{{ event.end_reason === 'unavailable' ? '数据断点' : '尚未结束' }}</small><small v-else-if="event.resumed_date">{{ event.resumed_date }} {{ regimeLabels[event.end_reason as 'repair' | 'valid'] ?? '恢复' }}</small></td><td>{{ event.days }}</td>
                <td>{{ eventChange(event, 'drawdown') == null ? '待验证' : number(eventChange(event, 'drawdown'), 2, '%') }}</td><td>{{ eventChange(event, 'upside') == null ? '待验证' : number(eventChange(event, 'upside'), 2, '%') }}</td>
              </tr>
            </tbody></table></div>
            </template>
            <template v-else>
              <p class="regime-note">低覆盖率不能证明停牌原因；恢复完整数据后重新判断，不将缺口视作风险解除。</p>
              <div v-if="!gaps.length" class="regime-empty">所选区间无数据缺口</div>
              <div v-else class="regime-table-wrap"><table class="regime-table"><thead><tr><th>起始日</th><th>结束日</th><th>交易日</th><th>有效覆盖范围</th><th>缺失原因</th></tr></thead><tbody>
                <tr v-for="gap in pageGaps" :key="gap.start"><td><button class="regime-date-link" :aria-label="`查看${gap.start}数据缺口`" @click="selectGap(gap.start)">{{ gap.start }}</button></td><td>{{ gap.end }}</td><td>{{ gap.days }}</td><td>{{ number(gap.min_coverage_pct, 2, '%') }} – {{ number(gap.max_coverage_pct, 2, '%') }}</td><td>{{ gap.reasons.map(reason => regimeMissingLabels[reason]).join('；') || '历史来源待核验' }}</td></tr>
              </tbody></table></div>
            </template>
            <nav v-if="eventPages > 1" class="regime-pagination" aria-label="历史事件分页">
              <button class="regime-control" :disabled="eventPage === 0" aria-label="上一页事件" title="上一页事件" @click="eventPage--">←</button>
              <span>{{ eventPage + 1 }} / {{ eventPages }}</span>
              <button class="regime-control" :disabled="eventPage + 1 >= eventPages" aria-label="下一页事件" title="下一页事件" @click="eventPage++">→</button>
            </nav>
          </section>
          <details class="regime-method"><summary>研究口径与数据限制</summary><p v-for="note in dashboard.notes" :key="note">{{ note }}</p><p v-for="source in dashboard.breadth_sources" :key="source.table">{{ source.start }}至{{ source.end }}：{{ source.note }}</p><p>价格覆盖：{{ dashboard.history_start }}至{{ dashboard.history_end }}；策略对照截至{{ dashboard.strategy_evaluation_end ?? '未记录' }}。模型：{{ dashboard.rule_name }}。阈值本次固定后重算，不因收益结果自动调参。</p></details>
        </template>
      </template>
    </main>
  </div>
</template>

<style scoped>
.regime-main { gap: 16px; min-width: 0; letter-spacing: 0; }
.macro-subnav { display: flex; gap: 24px; flex-wrap: wrap; border-bottom: 1px solid #dce3eb; padding: 0 0 10px; }
.macro-subnav a { font-size: 14px; color: #64748b; text-decoration: none; }
.macro-subnav a.active { color: #0f4c75; font-weight: 700; border-bottom: 2px solid #0f4c75; padding-bottom: 10px; margin-bottom: -11px; }
h2 { font-size: 23px; margin: 0; } h3 { font-size: 16px; margin: 0; } p { margin: 0; }
.regime-head, .regime-section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.regime-note { font-size: 12px; color: #64748b; line-height: 1.6; }
.regime-warning { font-size: 13px; color: #805b19; background: #fff7e4; border-left: 3px solid #d4a444; padding: 9px 12px; line-height: 1.6; }
.regime-stats { display: grid; grid-template-columns: 1.2fr 1.2fr 1fr; gap: 16px; }
.regime-stat { padding: 12px 16px; border-left: 3px solid #cbd5e1; background: #fff; min-width: 0; }
.regime-stat label { display: block; font-size: 12px; color: #64748b; }
.regime-stat strong { display: block; font-size: 24px; margin: 5px 0; line-height: 1.4; }
.regime-stat small { font-size: 12px; color: #64748b; }
.regime-chart-row { display: grid; grid-template-columns: minmax(0,1fr) 255px; gap: 18px; }
.regime-review { padding: 6px 0; min-width: 0; }.regime-review h3 { padding-bottom: 12px; border-bottom: 1px solid #dce3eb; }
.regime-evidence-line { padding: 13px 0; border-bottom: 1px solid #e2e8f0; display: grid; gap: 5px; font-size: 13px; }
.regime-evidence-line b { font-weight: 600; }.regime-evidence-line span { color: #64748b; font-size: 12px; line-height: 1.55; }
.regime-table-wrap { overflow-x: auto; width: 100%; min-width: 0; }
.regime-table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
.regime-table th, .regime-table td { text-align: left; padding: 10px; border-bottom: 1px solid #e2e8f0; line-height: 1.5; overflow-wrap: anywhere; }
.regime-table th { font-weight: 500; color: #64748b; background: #f3f6fa; }.regime-table td:first-child { font-weight: 600; }
.regime-table tr[data-event-date] { cursor: pointer; }.regime-table tr[data-event-date]:hover, .regime-table tr.selected { background: #edf3fa; }
.regime-table small { display: block; color: #64748b; }
.regime-section { border-top: 1px solid #dce3eb; padding-top: 14px; min-width: 0; }.regime-section-head { margin-bottom: 8px; }
.regime-control { background: white; border: 1px solid #cbd5e1; color: #14213d; border-radius: 6px; font-size: 13px; padding: 7px 9px; max-width: 100%; }
.regime-control:disabled { opacity: .45; cursor: not-allowed; }.regime-badge { font-size: 12px; color: #0f4c75; }
.regime-date-link { border: 0; padding: 0; background: transparent; color: #0f4c75; font: inherit; cursor: pointer; text-decoration: underline; text-underline-offset: 3px; }
.regime-empty, .regime-error { padding: 18px 0; color: #64748b; font-size: 14px; }.regime-error { color: #a33b3b; }
.regime-pagination { display: flex; justify-content: flex-end; align-items: center; gap: 12px; margin-top: 12px; font-size: 13px; }
.regime-history-tabs, .regime-history-controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.regime-history-tabs button { font: inherit; font-size: 15px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: #64748b; padding: 8px 0; cursor: pointer; }
.regime-history-tabs button[aria-selected="true"] { color: #0f4c75; border-bottom-color: #0f4c75; font-weight: 600; }
.regime-event-summary { font-size: 13px; line-height: 1.7; padding: 5px 0; color: #334155; }
.regime-rules { margin: 12px 0 8px; }
.regime-data-warning { margin-top: 9px; font-size: 13px; line-height: 1.6; color: #805b19; }
.regime-method { border-top: 1px solid #dce3eb; padding: 12px 0; font-size: 12px; color: #64748b; line-height: 1.7; }.regime-method summary { cursor: pointer; }.regime-method p { margin-top: 7px; }
@media (max-width: 1280px) { .regime-chart-row { grid-template-columns: minmax(0,1fr) 225px; } h2 { font-size: 21px; }.regime-stat strong { font-size: 21px; }.regime-stats { gap: 10px; } }
@media (max-width: 1050px) { .regime-chart-row { grid-template-columns: minmax(0,1fr); }.regime-review { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }.regime-review h3 { grid-column: 1/-1; }.regime-evidence-line { padding: 5px 0; }.regime-stats { grid-template-columns: repeat(2,minmax(0,1fr)); }.regime-stat:last-child { grid-column: 1/-1; }.regime-table { min-width: 560px; } }
@media (max-width: 600px) { .regime-review, .regime-stats { grid-template-columns: minmax(0,1fr); }.regime-review h3 { grid-column: auto; } }
</style>
