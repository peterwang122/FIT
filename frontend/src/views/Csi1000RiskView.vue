<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import RiskMonitorChart from '../components/RiskMonitorChart.vue'
import { fetchQuantRiskDashboard, fetchQuantRiskEvidence } from '../api/stocks'
import type {
  QuantRiskDashboardPoint,
  QuantRiskDashboardResponse,
  QuantRiskEvidenceCell,
  QuantRiskEvidenceResponse,
  QuantRiskEvidenceRow,
  QuantRiskEvent,
  QuantRiskStrategyKey,
} from '../types/risk'

type RangeMode = '1y' | 'since2024' | '3y' | 'full' | 'custom'
type TrackVisibility = Record<QuantRiskStrategyKey, boolean>

const RANGE_STORAGE_KEY = 'fit:risk:csi1000:range:v1'
const TRACK_STORAGE_KEY = 'fit:risk:csi1000:tracks:v1'
const EVIDENCE_HOVER_DEBOUNCE_MS = 240
const DEFAULT_TRACKS: TrackVisibility = {
  yellow_vulnerability: true,
  red_escalation: true,
  global_shock: true,
}
const RANGE_OPTIONS: Array<{ key: RangeMode; label: string }> = [
  { key: '1y', label: '1年' },
  { key: 'since2024', label: '2024-09至今' },
  { key: '3y', label: '3年' },
  { key: 'full', label: '全部' },
  { key: 'custom', label: '自定义' },
]
const TRACK_OPTIONS: Array<{ key: QuantRiskStrategyKey; label: string; color: string }> = [
  { key: 'yellow_vulnerability', label: '黄色', color: '#d89a18' },
  { key: 'red_escalation', label: '红色', color: '#dc4f4f' },
  { key: 'global_shock', label: '全球冲击', color: '#7657c8' },
]

const dashboard = ref<QuantRiskDashboardResponse | null>(null)
const evidence = ref<QuantRiskEvidenceResponse | null>(null)
const loading = ref(false)
const evidenceLoading = ref(false)
const error = ref('')
const evidenceError = ref('')
const rangeMode = ref<RangeMode>('since2024')
const customStartDate = ref('2024-09-01')
const customEndDate = ref('')
const selectedDate = ref<string | null>(null)
const selectedEventId = ref<string | null>(null)
const expandedEventIds = ref<string[]>([])
const visibleTracks = ref<TrackVisibility>({ ...DEFAULT_TRACKS })
let dashboardController: AbortController | null = null
let evidenceController: AbortController | null = null
let evidenceLoadTimer: number | null = null

const pointMap = computed(
  () => new Map((dashboard.value?.points ?? []).map((item) => [item.trade_date, item])),
)
const candleDates = computed(() => (dashboard.value?.candles ?? []).map((item) => item.trade_date))
const selectedPoint = computed(() =>
  selectedDate.value ? pointMap.value.get(selectedDate.value) ?? null : null,
)
const selectedEvent = computed(() => {
  const events = dashboard.value?.events ?? []
  if (selectedEventId.value) {
    return events.find((item) => item.event_id === selectedEventId.value) ?? null
  }
  if (!selectedDate.value) return null
  return events.find(
    (item) => item.start_date <= selectedDate.value! && item.end_date >= selectedDate.value!,
  ) ?? null
})
const sortedEvents = computed(() =>
  [...(dashboard.value?.events ?? [])].sort((left, right) => right.start_date.localeCompare(left.start_date)),
)
const selectedEvidenceRows = computed(() => {
  if (!selectedDate.value || !evidence.value) return []
  return evidence.value.rows
    .map((row) => ({ row, cell: row.cells.find((item) => item.trade_date === selectedDate.value) ?? null }))
    .filter((item): item is { row: QuantRiskEvidenceRow; cell: QuantRiskEvidenceCell } => item.cell != null)
})
const inspectorEvidenceRows = computed(() =>
  [...selectedEvidenceRows.value]
    .sort((left, right) => evidencePriority(left.cell) - evidencePriority(right.cell))
    .slice(0, 5),
)
const evidenceSections = computed(() => {
  const sections: Array<{
    key: string
    strategyKey: QuantRiskStrategyKey
    strategyLabel: string
    sectionLabel: string
    rows: QuantRiskEvidenceRow[]
  }> = []
  for (const row of evidence.value?.rows ?? []) {
    const key = `${row.strategy_key}:${row.section_key}`
    let section = sections.find((item) => item.key === key)
    if (!section) {
      section = {
        key,
        strategyKey: row.strategy_key,
        strategyLabel: row.strategy_label,
        sectionLabel: row.section_label,
        rows: [],
      }
      sections.push(section)
    }
    section.rows.push(row)
  }
  return sections
})
const freshnessNotice = computed(() => {
  if (!selectedDate.value) return ''
  const lagged = selectedEvidenceRows.value
    .filter((item) => item.cell.data_date && item.cell.data_date < selectedDate.value!)
    .map((item) => ({
      lag: calendarDayDiff(item.cell.data_date!, selectedDate.value!),
      source: item.cell.data_source,
    }))
    .sort((left, right) => right.lag - left.lag)
  if (!lagged.length) return '底层证据均使用选中日已经可见的数据。'
  const sources = [...new Set(lagged.map((item) => item.source).filter(Boolean))].slice(0, 3)
  return `部分外盘或FRED数据较选中日滞后最多${lagged[0].lag}个自然日；按当时实际可用日期参与判断${sources.length ? `（${sources.join('、')}）` : ''}。`
})
const selectedAdvice = computed(() => buildAdvice(selectedPoint.value))
const selectedDrawdown = computed(() =>
  selectedEvent.value?.drawdowns.find((item) => item.trading_days === 20) ?? null,
)

function loadPreferences() {
  try {
    const savedRange = JSON.parse(localStorage.getItem(RANGE_STORAGE_KEY) || '{}') as {
      mode?: RangeMode
      startDate?: string
      endDate?: string
    }
    if (RANGE_OPTIONS.some((item) => item.key === savedRange.mode)) {
      rangeMode.value = savedRange.mode!
    }
    if (savedRange.startDate) customStartDate.value = savedRange.startDate
    if (savedRange.endDate) customEndDate.value = savedRange.endDate
  } catch {
    rangeMode.value = 'since2024'
  }
  try {
    const savedTracks = JSON.parse(localStorage.getItem(TRACK_STORAGE_KEY) || '{}') as Partial<TrackVisibility>
    visibleTracks.value = {
      yellow_vulnerability: savedTracks.yellow_vulnerability ?? true,
      red_escalation: savedTracks.red_escalation ?? true,
      global_shock: savedTracks.global_shock ?? true,
    }
  } catch {
    visibleTracks.value = { ...DEFAULT_TRACKS }
  }
}

function saveRangePreference() {
  localStorage.setItem(
    RANGE_STORAGE_KEY,
    JSON.stringify({
      mode: rangeMode.value,
      startDate: customStartDate.value,
      endDate: customEndDate.value,
    }),
  )
}

function saveTrackPreference() {
  localStorage.setItem(TRACK_STORAGE_KEY, JSON.stringify(visibleTracks.value))
}

function isCanceledRequest(cause: unknown) {
  const payload = cause as { name?: string; code?: string } | null
  return payload?.name === 'CanceledError' || payload?.name === 'AbortError' || payload?.code === 'ERR_CANCELED'
}

function dateYearsBefore(referenceDate: string, years: number) {
  const [year, month, day] = referenceDate.split('-').map(Number)
  return `${year - years}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function currentReferenceDate() {
  return dashboard.value?.as_of_date ?? new Date().toISOString().slice(0, 10)
}

function dashboardRequest() {
  const referenceDate = currentReferenceDate()
  if (rangeMode.value === 'full') return { mode: 'full' as const }
  if (rangeMode.value === '1y') {
    return { mode: 'custom' as const, startDate: dateYearsBefore(referenceDate, 1), endDate: referenceDate }
  }
  if (rangeMode.value === '3y') {
    return { mode: 'custom' as const, startDate: dateYearsBefore(referenceDate, 3), endDate: referenceDate }
  }
  if (rangeMode.value === 'custom') {
    return {
      mode: 'custom' as const,
      startDate: customStartDate.value || '2024-09-01',
      endDate: customEndDate.value || undefined,
    }
  }
  return { mode: 'default' as const }
}

async function loadDashboard() {
  cancelScheduledEvidenceLoad()
  dashboardController?.abort()
  const controller = new AbortController()
  dashboardController = controller
  loading.value = true
  error.value = ''
  try {
    const response = await fetchQuantRiskDashboard({ ...dashboardRequest(), signal: controller.signal })
    if (dashboardController !== controller) return
    dashboard.value = response
    const dates = response.points.map((item) => item.trade_date)
    selectedDate.value = selectedDate.value && dates.includes(selectedDate.value)
      ? selectedDate.value
      : dates[dates.length - 1] ?? null
    selectedEventId.value = null
    saveRangePreference()
    await loadEvidenceForDate(selectedDate.value)
  } catch (cause) {
    if (!isCanceledRequest(cause) && dashboardController === controller) {
      dashboard.value = null
      evidence.value = null
      error.value = cause instanceof Error ? cause.message : '风险监控数据加载失败'
    }
  } finally {
    if (dashboardController === controller) {
      dashboardController = null
      loading.value = false
    }
  }
}

function evidenceWindow(centerDate: string, before: number, after: number) {
  const dates = candleDates.value
  const index = dates.indexOf(centerDate)
  if (index < 0) return { start: centerDate, end: centerDate }
  return {
    start: dates[Math.max(0, index - before)],
    end: dates[Math.min(dates.length - 1, index + after)],
  }
}

function eventEvidenceWindow(event: QuantRiskEvent) {
  const dates = candleDates.value
  const startIndex = Math.max(0, dates.indexOf(event.start_date))
  const endIndex = Math.max(startIndex, dates.indexOf(event.end_date))
  return {
    start: dates[Math.max(0, startIndex - 5)] ?? event.start_date,
    end: dates[Math.min(dates.length - 1, endIndex + 5)] ?? event.end_date,
  }
}

async function loadEvidence(startDate: string, endDate: string) {
  evidenceController?.abort()
  const controller = new AbortController()
  evidenceController = controller
  evidenceLoading.value = true
  evidenceError.value = ''
  try {
    const response = await fetchQuantRiskEvidence(startDate, endDate, controller.signal)
    if (evidenceController === controller) evidence.value = response
  } catch (cause) {
    if (!isCanceledRequest(cause) && evidenceController === controller) {
      evidence.value = null
      evidenceError.value = cause instanceof Error ? cause.message : '证据矩阵加载失败'
    }
  } finally {
    if (evidenceController === controller) {
      evidenceController = null
      evidenceLoading.value = false
    }
  }
}

async function loadEvidenceForDate(tradeDate: string | null) {
  if (!tradeDate) return
  const window = evidenceWindow(tradeDate, 10, 10)
  await loadEvidence(window.start, window.end)
}

function cancelScheduledEvidenceLoad() {
  if (evidenceLoadTimer == null) return
  window.clearTimeout(evidenceLoadTimer)
  evidenceLoadTimer = null
}

function scheduleEvidenceForDate(tradeDate: string) {
  cancelScheduledEvidenceLoad()
  evidenceLoadTimer = window.setTimeout(() => {
    evidenceLoadTimer = null
    if (selectedDate.value !== tradeDate || evidenceContainsDate(tradeDate)) return
    void loadEvidenceForDate(tradeDate)
  }, EVIDENCE_HOVER_DEBOUNCE_MS)
}

function evidenceContainsDate(tradeDate: string) {
  return evidence.value?.dates.includes(tradeDate) ?? false
}

function selectChartDate(tradeDate: string) {
  if (selectedDate.value === tradeDate && evidenceContainsDate(tradeDate)) return
  selectedDate.value = tradeDate
  selectedEventId.value = null
  if (!evidenceContainsDate(tradeDate)) scheduleEvidenceForDate(tradeDate)
  else cancelScheduledEvidenceLoad()
}

function selectEvent(event: QuantRiskEvent) {
  cancelScheduledEvidenceLoad()
  selectedEventId.value = event.event_id
  selectedDate.value = event.first_trigger_date
  const window = eventEvidenceWindow(event)
  void loadEvidence(window.start, window.end)
}

function toggleEventDetails(event: QuantRiskEvent) {
  selectEvent(event)
  expandedEventIds.value = expandedEventIds.value.includes(event.event_id)
    ? expandedEventIds.value.filter((item) => item !== event.event_id)
    : [...expandedEventIds.value, event.event_id]
}

function setRange(mode: RangeMode) {
  rangeMode.value = mode
  saveRangePreference()
  if (mode !== 'custom') void loadDashboard()
}

function toggleTrack(key: QuantRiskStrategyKey) {
  visibleTracks.value = { ...visibleTracks.value, [key]: !visibleTracks.value[key] }
  saveTrackPreference()
}

function formatScore(value: number | null) {
  return value == null ? '--' : value.toFixed(1)
}

function statusLabel(point: QuantRiskDashboardPoint | null, key: QuantRiskStrategyKey) {
  if (!point) return '无数据'
  const state = point[key]
  if (state === true) return '命中'
  if (state === false) return '未命中'
  const missingLabels = selectedEvidenceRows.value
    .filter((item) => item.row.strategy_key === key && item.cell.matched === null)
    .map((item) => item.row.label)
  if (!missingLabels.length) return '数据不完整'
  return missingLabels.length === 1
    ? `缺${missingLabels[0]}`
    : `缺${missingLabels[0]}等${missingLabels.length}项`
}

function scoreFor(point: QuantRiskDashboardPoint | null, key: QuantRiskStrategyKey) {
  if (!point) return null
  if (key === 'yellow_vulnerability') return point.yellow_score
  if (key === 'red_escalation') return point.red_score
  return point.global_score
}

function globalModeLabel(mode: string | null) {
  const labels: Record<string, string> = {
    broad_risk_off: '全面避险',
    tech_deleveraging: '科技去杠杆',
    usd_rate_shock: '美元利率冲击',
  }
  if (!mode) return ''
  return mode
    .split('+')
    .map((part) => labels[part.trim()] ?? part.trim())
    .join(' + ')
}

function buildAdvice(point: QuantRiskDashboardPoint | null) {
  if (!point) return '暂无可用风险建议'
  const advice: string[] = []
  if (point.red_escalation) advice.push('按大级别调整管理风险，不按普通回踩处理')
  if (point.global_shock) {
    const modes = new Set(
      (point.global_mode ?? '')
        .split('+')
        .map((mode) => mode.trim())
        .filter(Boolean),
    )
    if (modes.has('broad_risk_off')) advice.push('优先控制总风险敞口')
    if (modes.has('tech_deleveraging')) advice.push('控制科技成长暴露')
    if (modes.has('usd_rate_shock')) {
      advice.push('实际贴现率快速上升且全球科技承压，控制高估值成长暴露')
    }
  }
  if (point.yellow_vulnerability) advice.push('降低高弹性仓位、停止追涨')
  if (advice.length) return advice.join('；')
  if (!point.data_complete) return '数据不完整，暂不把缺失当作风险解除'
  return '当日三项风险状态均未命中'
}

function evidencePriority(cell: QuantRiskEvidenceCell) {
  if (cell.matched === null) return 0
  if (cell.matched === true) return 1
  if (cell.partial) return 2
  return 3
}

function evidenceStateLabel(cell: QuantRiskEvidenceCell) {
  if (cell.matched === null) return '缺失'
  if (cell.matched) return '满足'
  if (cell.partial) return '接近'
  return '未满足'
}

function formatEvidenceValue(cell: QuantRiskEvidenceCell) {
  if (cell.value == null) return '--'
  if (cell.unit === '元') return `${(cell.value / 100_000_000).toFixed(1)}亿`
  if (cell.unit === '手') return `${Math.round(cell.value).toLocaleString('zh-CN')}手`
  if (cell.unit === '%' || cell.unit === '百分点') return `${cell.value.toFixed(2)}%`
  if (cell.unit === 'bp') return `${cell.value.toFixed(1)}bp`
  if (cell.unit === '倍') return `${cell.value.toFixed(3)}倍`
  return `${cell.value.toFixed(2)}${cell.unit ?? ''}`
}

function thresholdText(cell: QuantRiskEvidenceCell) {
  const operator = cell.direction === 'low' ? '≤' : '≥'
  const parts: string[] = []
  if (cell.absolute_threshold != null) {
    parts.push(`${operator}${formatEvidenceValue({ ...cell, value: cell.absolute_threshold })}`)
  }
  if (cell.percentile_threshold != null) parts.push(`分位${operator}${cell.percentile_threshold.toFixed(0)}%`)
  return parts.join(' 且 ')
}

function evidenceTooltip(row: QuantRiskEvidenceRow, cell: QuantRiskEvidenceCell) {
  if (cell.matched === null) {
    return `${row.label}\n${cell.missing_reason ?? '数据缺失'}\n数据日：${cell.data_date ?? '--'}\n可用时间：${cell.available_at ?? '--'}\n来源：${cell.data_source ?? '--'}`
  }
  return [
    row.label,
    `原值：${formatEvidenceValue(cell)}`,
    `百分位：${cell.percentile == null ? '--' : `${cell.percentile.toFixed(2)}%`}`,
    `阈值：${thresholdText(cell) || '--'}`,
    `状态：${evidenceStateLabel(cell)}`,
    `数据日：${cell.data_date ?? '--'}`,
    `可用时间：${cell.available_at ?? '--'}`,
    `来源：${cell.data_source ?? '--'}`,
  ].join('\n')
}

function evidenceCellClass(row: QuantRiskEvidenceRow, cell: QuantRiskEvidenceCell) {
  return {
    missing: cell.matched === null,
    matched: cell.matched === true,
    partial: cell.partial,
    yellow: row.strategy_key === 'yellow_vulnerability',
    red: row.strategy_key === 'red_escalation',
    global: row.strategy_key === 'global_shock',
    selected: cell.trade_date === selectedDate.value,
  }
}

function calendarDayDiff(fromDate: string, toDate: string) {
  const from = new Date(`${fromDate}T00:00:00+08:00`).getTime()
  const to = new Date(`${toDate}T00:00:00+08:00`).getTime()
  return Math.max(0, Math.round((to - from) / 86_400_000))
}

function formatShortDate(value: string | null) {
  return value ? value.slice(5) : '--'
}

function eventRange(event: QuantRiskEvent) {
  return `${event.start_date} — ${event.is_open ? '进行中' : formatShortDate(event.end_date)}`
}

function strategyShortLabel(key: QuantRiskStrategyKey, mode?: string | null) {
  if (key === 'yellow_vulnerability') return '黄色'
  if (key === 'red_escalation') return '红色'
  return globalModeLabel(mode ?? null) || '全球冲击'
}

function eventModes(event: QuantRiskEvent) {
  const seen = new Set<string>()
  return event.strategy_spans
    .map((span) => ({
      key: `${span.strategy_key}:${span.mode ?? ''}`,
      strategyKey: span.strategy_key,
      label: strategyShortLabel(span.strategy_key, span.mode),
    }))
    .filter((item) => {
      if (seen.has(item.key)) return false
      seen.add(item.key)
      return true
    })
}

function drawdownFor(event: QuantRiskEvent, horizon: number) {
  return event.drawdowns.find((item) => item.trading_days === horizon) ?? null
}

function formatDrawdown(event: QuantRiskEvent, horizon: number) {
  const item = drawdownFor(event, horizon)
  return item?.status === 'complete' && item.value_pct != null ? `${item.value_pct.toFixed(2)}%` : '待验证'
}

function eventTrough(event: QuantRiskEvent) {
  const complete = event.drawdowns.filter((item) => item.status === 'complete' && item.value_pct != null)
  if (!complete.length) return '待验证'
  const worst = [...complete].sort((left, right) => left.value_pct! - right.value_pct!)[0]
  return `${formatShortDate(worst.trough_date)} · ${worst.days_to_trough}日`
}

onMounted(() => {
  loadPreferences()
  void loadDashboard()
})

watch(customStartDate, saveRangePreference)
watch(customEndDate, saveRangePreference)

onBeforeUnmount(() => {
  cancelScheduledEvidenceLoad()
  dashboardController?.abort()
  evidenceController?.abort()
})
</script>

<template>
  <section class="risk-page">
    <section class="card risk-title-card">
      <div>
        <h2>中证1000风险监控</h2>
        <p class="muted">三套策略只表示风险状态，不产生买卖交易。</p>
      </div>
      <div class="range-controls" aria-label="日期范围">
        <button
          v-for="option in RANGE_OPTIONS"
          :key="option.key"
          type="button"
          :class="{ active: rangeMode === option.key }"
          @click="setRange(option.key)"
        >
          {{ option.label }}
        </button>
      </div>
      <div v-if="rangeMode === 'custom'" class="custom-range">
        <label>开始<input v-model="customStartDate" type="date" /></label>
        <label>结束<input v-model="customEndDate" type="date" /></label>
        <button type="button" class="primary-action" @click="loadDashboard">应用</button>
      </div>
    </section>

    <div v-if="error" class="card risk-state error-state">{{ error }}</div>
    <div v-else-if="loading && !dashboard" class="card risk-state">正在加载风险历史...</div>

    <template v-if="dashboard">
      <section class="card risk-summary">
        <div class="summary-item composite">
          <span>选中日综合风险完成度</span>
          <strong :class="selectedPoint?.risk_level ?? ''">
            {{ formatScore(selectedPoint?.composite_score ?? null) }}
            <small v-if="selectedPoint?.composite_score != null">/ 100 · {{ selectedPoint.risk_level_label }}</small>
            <small v-else>数据不完整</small>
          </strong>
        </div>
        <div class="summary-item yellow">
          <span>黄色脆弱期</span>
          <strong><i></i>{{ statusLabel(selectedPoint, 'yellow_vulnerability') }} <small>{{ formatScore(scoreFor(selectedPoint, 'yellow_vulnerability')) }}%</small></strong>
        </div>
        <div class="summary-item red">
          <span>红色风险升级</span>
          <strong><i></i>{{ statusLabel(selectedPoint, 'red_escalation') }} <small>{{ formatScore(scoreFor(selectedPoint, 'red_escalation')) }}%</small></strong>
        </div>
        <div class="summary-item global">
          <span>全球冲击</span>
          <strong><i></i>{{ statusLabel(selectedPoint, 'global_shock') }} <small>{{ globalModeLabel(selectedPoint?.global_mode ?? null) || `${formatScore(scoreFor(selectedPoint, 'global_shock'))}%` }}</small></strong>
        </div>
        <div class="summary-item advice">
          <span>固定风险建议</span>
          <strong>{{ selectedAdvice }}</strong>
        </div>
      </section>

      <div class="risk-workbench">
        <section class="card chart-panel">
          <div class="panel-head">
            <div>
              <strong>中证1000 · K线与风险状态</strong>
              <span>十字光标联动 · {{ selectedDate ?? '--' }}</span>
            </div>
            <div class="track-controls" aria-label="风险轨道显示">
              <button
                v-for="track in TRACK_OPTIONS"
                :key="track.key"
                type="button"
                :class="{ active: visibleTracks[track.key] }"
                @click="toggleTrack(track.key)"
              >
                <i :style="{ backgroundColor: track.color }"></i>{{ track.label }}
              </button>
            </div>
          </div>
          <RiskMonitorChart
            :candles="dashboard.candles"
            :points="dashboard.points"
            :selected-date="selectedDate"
            :visible-tracks="visibleTracks"
            @select-date="selectChartDate"
          />
        </section>

        <aside class="card inspector-panel">
          <div class="panel-head inspector-head">
            <div>
              <strong>{{ selectedDate ?? '--' }} · 日期复盘</strong>
              <span>数据截至当日</span>
            </div>
          </div>
          <div class="inspector-body">
            <span class="inspector-label">综合风险完成度</span>
            <div class="inspector-score" :class="selectedPoint?.risk_level ?? ''">
              {{ formatScore(selectedPoint?.composite_score ?? null) }}
              <small>{{ selectedPoint?.risk_level_label ?? '数据不完整' }}</small>
            </div>
            <div class="score-bar"><span :style="{ width: `${selectedPoint?.composite_score ?? 0}%` }"></span></div>

            <div v-if="evidenceLoading && !evidence" class="inspector-loading">加载证据...</div>
            <div v-for="item in inspectorEvidenceRows" :key="item.row.key" class="factor-row">
              <div>
                <span>{{ item.row.label }}</span>
                <b :class="[item.row.strategy_key, { muted: item.cell.matched === false && !item.cell.partial }]">
                  {{ evidenceStateLabel(item.cell) }}
                </b>
              </div>
              <small>
                {{ formatEvidenceValue(item.cell) }} · 分位 {{ item.cell.percentile == null ? '--' : `${item.cell.percentile.toFixed(1)}%` }}
                · 数据日 {{ formatShortDate(item.cell.data_date) }}
                · 可用时间 {{ item.cell.available_at ?? '--' }}
              </small>
            </div>
            <div v-if="selectedDrawdown" class="factor-row drawdown-row">
              <div><span>后续20日最大跌幅</span><b class="red_escalation">{{ selectedDrawdown.status === 'complete' ? `${selectedDrawdown.value_pct?.toFixed(2)}%` : '待验证' }}</b></div>
              <small v-if="selectedDrawdown.status === 'complete'">最低点 {{ selectedDrawdown.trough_date }} · 第{{ selectedDrawdown.days_to_trough }}个交易日</small>
              <small v-else>未来交易日数量尚不足</small>
            </div>
            <div class="freshness-note">{{ freshnessNotice }}</div>
          </div>
        </aside>
      </div>

      <section class="card evidence-panel">
        <div class="panel-head matrix-head">
          <div>
            <strong>底层证据矩阵</strong>
            <span>{{ selectedEventId ? '选中事件及前后5个交易日' : '选中日期前后10个交易日' }}</span>
          </div>
          <div class="matrix-legend">
            <span><i class="yellow"></i>黄色</span>
            <span><i class="red"></i>红色</span>
            <span><i class="global"></i>全球</span>
            <span><i class="partial"></i>接近</span>
            <span><i class="missing"></i>缺失</span>
          </div>
        </div>
        <div v-if="evidenceError" class="risk-state error-state">{{ evidenceError }}</div>
        <div v-else-if="evidenceLoading && !evidence" class="risk-state">正在加载证据矩阵...</div>
        <div v-else-if="evidence" class="matrix-scroll">
          <table class="evidence-table">
            <thead>
              <tr>
                <th class="sticky-label">风险证据</th>
                <th
                  v-for="tradeDate in evidence.dates"
                  :key="tradeDate"
                  :class="{ selected: tradeDate === selectedDate }"
                >
                  {{ formatShortDate(tradeDate) }}
                </th>
              </tr>
            </thead>
            <tbody v-for="section in evidenceSections" :key="section.key">
              <tr class="section-row">
                <th class="sticky-label" :class="section.strategyKey">
                  {{ section.strategyLabel }} · {{ section.sectionLabel }}
                </th>
                <td :colspan="evidence.dates.length"></td>
              </tr>
              <tr v-for="row in section.rows" :key="row.key">
                <th class="sticky-label factor-label">{{ row.label }}</th>
                <td
                  v-for="cell in row.cells"
                  :key="cell.trade_date"
                  :class="{ 'selected-column': cell.trade_date === selectedDate }"
                >
                  <button
                    type="button"
                    class="evidence-cell"
                    :class="evidenceCellClass(row, cell)"
                    :title="evidenceTooltip(row, cell)"
                    :aria-label="`${cell.trade_date} ${row.label} ${evidenceStateLabel(cell)}`"
                    @click="selectChartDate(cell.trade_date)"
                  ></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card events-panel">
        <div class="panel-head">
          <div>
            <strong>综合风险事件</strong>
            <span>点击事件定位K线与证据；数据缺口不误判为风险解除</span>
          </div>
          <span class="event-count">{{ sortedEvents.length }} 段</span>
        </div>
        <div class="events-scroll">
          <table class="events-table">
            <thead>
              <tr>
                <th>事件区间</th>
                <th>策略接力</th>
                <th>持续</th>
                <th>5日最大跌幅</th>
                <th>10日最大跌幅</th>
                <th>20日最大跌幅</th>
                <th>最低点</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="event in sortedEvents" :key="event.event_id">
                <tr
                  class="event-row"
                  :class="{ selected: selectedEventId === event.event_id }"
                  @click="selectEvent(event)"
                >
                  <td>
                    <strong>{{ eventRange(event) }}</strong>
                    <small v-if="event.end_reason === 'data_gap'">数据缺口结束</small>
                    <small v-else-if="event.is_open">尚未结束</small>
                    <small v-else>明确解除 {{ event.release_date }}</small>
                  </td>
                  <td>
                    <span
                      v-for="mode in eventModes(event)"
                      :key="mode.key"
                      class="event-chip"
                      :class="mode.strategyKey"
                    >{{ mode.label }}</span>
                  </td>
                  <td>{{ event.duration_trade_days }}日</td>
                  <td class="drawdown">{{ formatDrawdown(event, 5) }}</td>
                  <td class="drawdown">{{ formatDrawdown(event, 10) }}</td>
                  <td class="drawdown">{{ formatDrawdown(event, 20) }}</td>
                  <td>{{ eventTrough(event) }}</td>
                  <td>
                    <button type="button" class="detail-button" title="展开事件详情" @click.stop="toggleEventDetails(event)">
                      {{ expandedEventIds.includes(event.event_id) ? '收起' : '详情' }}
                    </button>
                  </td>
                </tr>
                <tr v-if="expandedEventIds.includes(event.event_id)" class="event-detail-row">
                  <td colspan="8">
                    <div class="event-spans">
                      <article v-for="span in event.strategy_spans" :key="`${span.strategy_key}-${span.start_date}`">
                        <strong :class="span.strategy_key">{{ span.strategy_label }}{{ span.mode ? ` · ${globalModeLabel(span.mode)}` : '' }}</strong>
                        <span>{{ span.start_date }} — {{ span.end_date }} · {{ span.active_days }}日</span>
                        <small>{{ span.key_evidence.join('、') || '当日组件已满足策略条件' }}</small>
                      </article>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.risk-page {
  display: grid;
  min-width: 0;
  gap: 12px;
}

.risk-title-card,
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.risk-title-card { flex-wrap: wrap; padding: 15px 17px; }
.risk-title-card h2 { margin: 0; color: #172033; font-size: 20px; }
.risk-title-card p { margin: 4px 0 0; font-size: 12px; }

.range-controls,
.track-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border: 1px solid #dce3ec;
  border-radius: 6px;
  background: #f7f9fc;
}

.range-controls button,
.track-controls button,
.detail-button {
  border: 0;
  background: transparent;
  color: #607086;
  cursor: pointer;
  font: inherit;
}

.range-controls button { padding: 6px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.range-controls button.active { background: #fff; color: #1f4d8c; box-shadow: 0 1px 3px rgba(15, 23, 42, .12); }

.custom-range { display: flex; align-items: center; gap: 8px; width: 100%; justify-content: flex-end; }
.custom-range label { display: flex; align-items: center; gap: 5px; color: #64748b; font-size: 11px; }
.custom-range input { height: 30px; border: 1px solid #d8e0ea; border-radius: 4px; padding: 0 7px; color: #334155; }
.primary-action { height: 30px; border: 1px solid #315fa8; border-radius: 4px; padding: 0 12px; background: #315fa8; color: #fff; cursor: pointer; }

.risk-state { padding: 24px; color: #64748b; text-align: center; }
.error-state { color: #b91c1c; background: #fff7f7; }

.risk-summary {
  display: grid;
  grid-template-columns: 1.18fr .88fr .88fr .95fr 1.65fr;
  overflow: hidden;
}

.summary-item { min-width: 0; padding: 12px 14px; border-right: 1px solid #e7ebf1; }
.summary-item:last-child { border-right: 0; }
.summary-item > span { display: block; color: #6b7789; font-size: 10px; }
.summary-item strong { display: block; margin-top: 5px; color: #27364a; font-size: 17px; line-height: 1.35; }
.summary-item strong small { color: #748196; font-size: 10px; font-weight: 600; }
.summary-item strong i { display: inline-block; width: 8px; height: 8px; margin-right: 6px; border-radius: 50%; }
.summary-item.yellow strong { color: #b7791f; }
.summary-item.yellow i { background: #d89a18; }
.summary-item.red strong { color: #c94444; }
.summary-item.red i { background: #dc4f4f; }
.summary-item.global strong { color: #6e50b8; }
.summary-item.global i { background: #7657c8; }
.summary-item.advice strong { font-size: 12px; font-weight: 700; }
.summary-item strong.stable { color: #25806a; }
.summary-item strong.vulnerable { color: #b7791f; }
.summary-item strong.high { color: #d56b2f; }
.summary-item strong.severe { color: #c94444; }

.risk-workbench { display: grid; grid-template-columns: minmax(0, 1fr) 286px; gap: 12px; min-width: 0; }
.chart-panel,
.inspector-panel,
.evidence-panel,
.events-panel { min-width: 0; overflow: hidden; }
.panel-head { min-height: 48px; padding: 10px 13px; border-bottom: 1px solid #e7ebf1; }
.panel-head > div:first-child { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.panel-head strong { color: #27364a; font-size: 13px; }
.panel-head span { color: #768397; font-size: 10px; }

.track-controls { flex-wrap: wrap; justify-content: flex-end; }
.track-controls button { display: inline-flex; align-items: center; gap: 5px; min-height: 25px; padding: 4px 7px; border-radius: 3px; font-size: 10px; }
.track-controls button.active { background: #fff; color: #27364a; box-shadow: 0 1px 2px rgba(15, 23, 42, .12); }
.track-controls button:not(.active) { opacity: .48; }
.track-controls i { width: 7px; height: 7px; border-radius: 50%; }

.inspector-body { padding: 13px 14px; }
.inspector-label { color: #718096; font-size: 10px; }
.inspector-score { margin: 4px 0 8px; color: #315fa8; font-size: 24px; font-weight: 800; }
.inspector-score small { margin-left: 4px; font-size: 11px; }
.inspector-score.vulnerable { color: #b7791f; }
.inspector-score.high { color: #d56b2f; }
.inspector-score.severe { color: #c94444; }
.score-bar { height: 6px; overflow: hidden; border-radius: 999px; background: #edf1f5; }
.score-bar span { display: block; height: 100%; background: #c94444; transition: width .2s ease; }
.inspector-loading { padding: 12px 0; color: #64748b; font-size: 11px; }
.factor-row { padding: 9px 0; border-bottom: 1px solid #edf1f5; }
.factor-row > div { display: flex; justify-content: space-between; gap: 8px; color: #334155; font-size: 11px; font-weight: 700; }
.factor-row b { white-space: nowrap; }
.factor-row small { display: block; margin-top: 3px; color: #758195; font-size: 9px; line-height: 1.45; }
.factor-row b.yellow_vulnerability { color: #b7791f; }
.factor-row b.red_escalation { color: #c94444; }
.factor-row b.global_shock { color: #6e50b8; }
.factor-row b.muted { color: #7d8999; }
.freshness-note { margin-top: 10px; padding: 8px 9px; border-left: 3px solid #d89a18; background: #fff9e9; color: #855d16; font-size: 9px; line-height: 1.5; }

.matrix-head { flex-wrap: wrap; }
.matrix-legend { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.matrix-legend span { display: inline-flex; align-items: center; gap: 4px; }
.matrix-legend i { width: 9px; height: 9px; border-radius: 2px; }
.matrix-legend i.yellow { background: #d89a18; }
.matrix-legend i.red { background: #dc4f4f; }
.matrix-legend i.global { background: #7657c8; }
.matrix-legend i.partial { background: rgba(49, 95, 168, .28); }
.matrix-legend i.missing { background: repeating-linear-gradient(135deg, #f8fafc, #f8fafc 3px, #cfd7e2 3px, #cfd7e2 5px); }

.matrix-scroll,
.events-scroll { width: 100%; overflow-x: auto; overscroll-behavior-inline: contain; }
.evidence-table { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 3px; padding: 8px 10px 12px; }
.evidence-table th { color: #6b7789; font-size: 8px; font-weight: 600; text-align: center; }
.evidence-table thead th { min-width: 31px; padding: 2px; }
.evidence-table thead th.selected { color: #1f4d8c; font-weight: 800; }
.evidence-table .sticky-label { position: sticky; left: 0; z-index: 2; width: 178px; min-width: 178px; max-width: 178px; padding: 3px 7px; background: #fff; text-align: left; }
.evidence-table .factor-label { overflow: hidden; color: #425169; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.section-row th { padding-top: 8px !important; border-top: 1px solid #e7ebf1; font-size: 9px !important; font-weight: 800 !important; }
.section-row th.yellow_vulnerability { color: #a86e14; }
.section-row th.red_escalation { color: #bd3d3d; }
.section-row th.global_shock { color: #6544aa; }
.evidence-table td { min-width: 31px; padding: 0; }
.evidence-table td.selected-column { background: #edf5ff; }
.evidence-cell { display: block; width: 100%; height: 18px; border: 1px solid rgba(51, 65, 85, .05); border-radius: 3px; background: #e9edf2; cursor: pointer; }
.evidence-cell.matched.yellow { background: rgba(216, 154, 24, .82); }
.evidence-cell.matched.red { background: rgba(220, 79, 79, .82); }
.evidence-cell.matched.global { background: rgba(118, 87, 200, .82); }
.evidence-cell.partial.yellow { background: rgba(216, 154, 24, .34); }
.evidence-cell.partial.red { background: rgba(220, 79, 79, .34); }
.evidence-cell.partial.global { background: rgba(118, 87, 200, .34); }
.evidence-cell.missing { background: repeating-linear-gradient(135deg, #f8fafc, #f8fafc 3px, #d8dee7 3px, #d8dee7 5px); }
.evidence-cell.selected { outline: 2px solid #315fa8; outline-offset: 1px; }

.event-count { white-space: nowrap; }
.events-table { width: 100%; min-width: 930px; border-collapse: collapse; font-size: 10px; }
.events-table th { padding: 8px 11px; background: #f7f9fc; color: #6d798b; text-align: left; font-weight: 700; }
.events-table td { padding: 9px 11px; border-top: 1px solid #e9edf2; color: #405069; }
.event-row { cursor: pointer; }
.event-row:hover td { background: #f8fbff; }
.event-row.selected td { background: #edf5ff; }
.event-row td:first-child strong,
.event-row td:first-child small { display: block; }
.event-row td:first-child small { margin-top: 2px; color: #7a8798; font-size: 8px; }
.event-chip { display: inline-block; margin: 1px 3px 1px 0; padding: 3px 6px; border-radius: 999px; font-size: 8px; font-weight: 700; }
.event-chip.yellow_vulnerability { color: #8b5a0f; background: #fff2c8; }
.event-chip.red_escalation { color: #9f2929; background: #ffe0e0; }
.event-chip.global_shock { color: #59349a; background: #eee8ff; }
.events-table .drawdown { color: #c94444; font-weight: 700; }
.detail-button { padding: 4px 6px; border: 1px solid #d9e1eb; border-radius: 3px; background: #fff; color: #315fa8; font-size: 9px; }
.event-detail-row td { padding: 10px 12px; background: #f9fbfd; }
.event-spans { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.event-spans article { padding: 8px; border: 1px solid #e2e8f0; border-radius: 4px; background: #fff; }
.event-spans strong,
.event-spans span,
.event-spans small { display: block; }
.event-spans strong { margin-bottom: 4px; font-size: 10px; }
.event-spans strong.yellow_vulnerability { color: #a86e14; }
.event-spans strong.red_escalation { color: #bd3d3d; }
.event-spans strong.global_shock { color: #6544aa; }
.event-spans span { color: #526174; font-size: 9px; }
.event-spans small { margin-top: 4px; color: #7a8798; font-size: 8px; line-height: 1.45; }

@media (max-width: 1280px) {
  .risk-summary { grid-template-columns: 1.15fr repeat(3, 1fr); }
  .summary-item:nth-child(4) { border-right: 0; }
  .summary-item.advice { grid-column: 1 / -1; border-top: 1px solid #e7ebf1; border-right: 0; }
  .risk-workbench { grid-template-columns: minmax(0, 1fr) 258px; }
  .summary-item { padding: 10px 11px; }
  .panel-head { padding: 9px 11px; }
}

@media (max-width: 1050px) {
  .risk-workbench { grid-template-columns: 1fr; }
  .inspector-panel { display: grid; grid-template-columns: 180px minmax(0, 1fr); }
  .inspector-head { align-items: flex-start; border-right: 1px solid #e7ebf1; border-bottom: 0; }
  .inspector-body { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
  .inspector-label,
  .inspector-score,
  .score-bar,
  .freshness-note { grid-column: 1 / -1; }
  .event-spans { grid-template-columns: 1fr; }
}

@media (max-width: 760px) {
  .risk-title-card { align-items: flex-start; }
  .range-controls { width: 100%; overflow-x: auto; }
  .range-controls button { flex: 0 0 auto; }
  .risk-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .summary-item { border-bottom: 1px solid #e7ebf1; }
  .summary-item:nth-child(2n) { border-right: 0; }
  .summary-item.advice { grid-column: 1 / -1; }
  .inspector-panel { display: block; }
  .inspector-head { border-right: 0; border-bottom: 1px solid #e7ebf1; }
  .inspector-body { display: block; }
  .custom-range { justify-content: flex-start; flex-wrap: wrap; }
}
</style>
