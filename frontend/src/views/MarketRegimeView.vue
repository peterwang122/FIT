<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchMarketRegime } from '../api/marketRegime'
import AppSidebar from '../components/AppSidebar.vue'
import MarketRegimeChart from '../components/MarketRegimeChart.vue'
import {
  regimeColors, regimeLabels, regimePermissions,
  type MarketRegimeDashboard, type RegimeIndex, type RegimePoint,
} from '../types/marketRegime'

const indexCode = ref<RegimeIndex>('sh000852')
const dashboard = shallowRef<MarketRegimeDashboard | null>(null)
const loading = ref(false)
const error = ref('')
const committedDate = ref('')
const previewDate = ref<string | null>(null)
const focusDate = ref('')
const focusRevision = ref(0)
const eventPage = ref(0)
let request: AbortController | null = null
let sequence = 0
const points = computed(() => dashboard.value?.points ?? [])
const pointMap = computed(() => new Map(points.value.map(point => [point.date, point])))
const lockedPoint = computed(() => pointMap.value.get(committedDate.value) ?? null)
const displayPoint = computed(() => pointMap.value.get(previewDate.value ?? '') ?? lockedPoint.value)
const events = computed(() => [...(dashboard.value?.events ?? [])].reverse())
const pageEvents = computed(() => events.value.slice(eventPage.value * 6, eventPage.value * 6 + 6))
const eventPages = computed(() => Math.ceil(events.value.length / 6))
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
  if (dashboard.value && point.date > dashboard.value.breadth_as_of) return '后复权历史未覆盖该日，未与未复权序列拼接。'
  if (point.breadth_long == null) return '历史广度缺失或均线样本不足，未填补数据。'
  return `MA60以上 ${number(point.breadth_medium, 1, '%')}；MA120以上 ${number(point.breadth_long, 1, '%')}。可评估 ${number(point.eligible, 0)} 只。${point.state === 'unavailable' ? '覆盖不足，不输出许可。' : ''}`
}

watch(indexCode, load, { immediate: true })
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
        <div><h2>市场环境</h2><p class="regime-note">环境判断与低吸许可分离</p></div>
        <select v-model="indexCode" class="regime-control" aria-label="观察指数">
          <option value="sh000852">中证1000 · 策略适用环境</option>
          <option value="sh000985">中证全指 · 市场参照</option>
        </select>
      </div>
      <div v-if="loading" class="regime-empty" role="status">正在加载研究快照…</div>
      <div v-else-if="error" class="regime-error" role="alert">{{ error }} <button class="btn btn-secondary btn-compact" @click="load">重试</button></div>
      <template v-else-if="dashboard">
        <div class="regime-warning">研究候选 · 尚未通过模型验收，不控制买卖。后复权广度截至{{ dashboard.breadth_as_of }}；静态快照生成于{{ snapshotTime }}（北京时间）。</div>
        <div v-if="!points.length" class="regime-empty" role="status">所选指数暂无研究数据</div>
        <template v-else>
          <div class="regime-stats">
            <div class="regime-stat"><label>环境状态 <span data-testid="regime-preview-date">{{ displayPoint?.date }}</span></label>
              <strong :style="{ color: displayPoint?.state === 'unavailable' ? '#64748b' : regimeColors[displayPoint?.state ?? 'unavailable'] }">{{ regimeLabels[displayPoint?.state ?? 'unavailable'] }}</strong>
              <small>{{ displayPoint?.state === 'unavailable' ? '数据不足，不能当作平稳' : '基准候选 · 尚未批准接入' }}</small>
            </div>
            <div class="regime-stat"><label>低吸许可 · 候选</label><strong>{{ regimePermissions[displayPoint?.state ?? 'unavailable'] }}</strong><small>只限制新买入，不代替持仓退出</small></div>
            <div class="regime-stat"><label data-testid="regime-index-name">{{ dashboard.index_name }}</label><strong>{{ number(displayPoint?.close) }}</strong><small>日线收盘</small></div>
          </div>
          <div class="regime-chart-row">
            <MarketRegimeChart :key="indexCode" :points="points" :committed-date="committedDate" :focus-date="focusDate" :focus-revision="focusRevision" @preview="previewDate = $event" @confirm="confirmDate($event)" />
            <aside class="regime-review">
              <h3>日期复盘 <span class="regime-badge" data-testid="regime-review-date">{{ displayPoint?.date }}</span></h3>
              <div class="regime-evidence-line"><b>市场趋势</b><span>收盘 / MA60：{{ number(relativeMA(displayPoint), 2, '%') }}；MA120的20日变化：{{ number(displayPoint?.long_slope == null ? null : displayPoint.long_slope * 100, 2, '%') }}</span></div>
              <div class="regime-evidence-line"><b>市场广度{{ displayPoint?.state === 'unavailable' ? ' · 数据不足' : '' }}</b><span>{{ breadthNote(displayPoint) }}</span></div>
              <div class="regime-evidence-line"><b>资金与盈利</b><span>银行流动性已采集；信用和盈利广度待核验，当前未进入许可规则。</span></div>
            </aside>
          </div>
          <section class="regime-section">
            <div class="regime-section-head"><h3>底层证据 <span class="regime-badge" data-testid="regime-locked-date">{{ committedDate }} · 已锁定</span></h3>
              <input class="regime-control" type="date" :value="committedDate" :min="dashboard.history_start ?? undefined" :max="dashboard.history_end ?? undefined" aria-label="确认复盘日期" @change="changeDate" />
            </div>
            <div class="regime-table-wrap"><table class="regime-table"><thead><tr><th>证据</th><th>当日值</th><th>判断依据</th><th>数据口径</th></tr></thead><tbody>
              <tr><td>中期趋势</td><td>{{ number(relativeMA(lockedPoint), 2, '%') }}</td><td>收盘相对MA60</td><td>指数日线</td></tr>
              <tr><td>长期趋势</td><td>{{ number(lockedPoint?.long_slope == null ? null : lockedPoint.long_slope * 100, 2, '%') }}</td><td>MA120相对20日前</td><td>指数日线</td></tr>
              <tr><td>中期 / 长期广度</td><td>{{ number(lockedPoint?.breadth_medium, 1, '%') }} / {{ number(lockedPoint?.breadth_long, 1, '%') }}</td><td>暂停阈值40%；失效阈值30%</td><td>旧表后复权 · 覆盖待审计</td></tr>
              <tr><td>可评估股票 / 当日交易</td><td>{{ number(lockedPoint?.eligible, 0) }} / {{ number(lockedPoint?.traded, 0) }}</td><td>至少500只交易股票；120日窗口有效覆盖至少60%</td><td>历史观察范围，不回填停牌价格</td></tr>
              <tr><td>资金与盈利</td><td>尚未参与</td><td>不抵消趋势与广度破坏</td><td>独立解释层，待验证</td></tr>
            </tbody></table></div>
          </section>
          <section class="regime-section">
            <div class="regime-section-head"><h3>历史暂停与修复</h3><span class="regime-note">前瞻变化以触发日收盘为基准 · 研究候选</span></div>
            <div v-if="!events.length" class="regime-empty">暂无完整事件</div>
            <div v-else class="regime-table-wrap"><table class="regime-table"><thead><tr><th>暂停开始</th><th>最后暂停日</th><th>交易日</th><th>后20日最低价变化</th><th>后20日最高价变化</th></tr></thead><tbody>
              <tr v-for="event in pageEvents" :key="event.start" :data-event-date="event.start" :class="{ selected: committedDate === event.start }" @click="confirmDate(event.start, true)">
                <td><button class="regime-date-link" :aria-label="`复盘${event.start}事件`" @click.stop="confirmDate(event.start, true)">{{ event.start }}</button></td>
                <td>{{ event.end }}<small v-if="!event.closed">{{ event.end_reason === 'unavailable' ? '数据断点' : '尚未结束' }}</small></td><td>{{ event.days }}</td>
                <td>{{ event.drawdown_20d_pct == null ? '待验证' : number(event.drawdown_20d_pct, 2, '%') }}</td><td>{{ event.upside_20d_pct == null ? '待验证' : number(event.upside_20d_pct, 2, '%') }}</td>
              </tr>
            </tbody></table></div>
            <nav v-if="eventPages > 1" class="regime-pagination" aria-label="历史事件分页">
              <button class="regime-control" :disabled="eventPage === 0" aria-label="上一页事件" title="上一页事件" @click="eventPage--">←</button>
              <span>{{ eventPage + 1 }} / {{ eventPages }}</span>
              <button class="regime-control" :disabled="eventPage + 1 >= eventPages" aria-label="下一页事件" title="下一页事件" @click="eventPage++">→</button>
            </nav>
          </section>
          <details class="regime-method"><summary>研究口径与数据限制</summary><p v-for="note in dashboard.notes" :key="note">{{ note }}</p><p>价格覆盖：{{ dashboard.history_start }}至{{ dashboard.history_end }}；候选规则：MA60/MA120，暂停连续3日，失效连续10日，修复连续5日。</p></details>
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
.regime-method { border-top: 1px solid #dce3eb; padding: 12px 0; font-size: 12px; color: #64748b; line-height: 1.7; }.regime-method summary { cursor: pointer; }.regime-method p { margin-top: 7px; }
@media (max-width: 1280px) { .regime-chart-row { grid-template-columns: minmax(0,1fr) 225px; } h2 { font-size: 21px; }.regime-stat strong { font-size: 21px; }.regime-stats { gap: 10px; } }
@media (max-width: 1050px) { .regime-chart-row { grid-template-columns: minmax(0,1fr); }.regime-review { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }.regime-review h3 { grid-column: 1/-1; }.regime-evidence-line { padding: 5px 0; }.regime-stats { grid-template-columns: repeat(2,minmax(0,1fr)); }.regime-stat:last-child { grid-column: 1/-1; }.regime-table { min-width: 560px; } }
@media (max-width: 600px) { .regime-review, .regime-stats { grid-template-columns: minmax(0,1fr); }.regime-review h3 { grid-column: auto; } }
</style>
