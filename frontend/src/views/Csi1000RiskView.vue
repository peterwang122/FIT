<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import RiskMonitorChart from '../components/RiskMonitorChart.vue'
import { fetchQuantRiskDashboard, fetchQuantRiskEvidence } from '../api/stocks'
import type {
  QuantRiskDashboardPoint,
  QuantRiskDashboardResponse,
  QuantRiskEvidenceCell,
  QuantRiskEvidenceResponse,
  QuantRiskEvidenceRow,
  QuantRiskEvent,
  QuantRiskDisplayState,
} from '../types/risk'

type RiskModuleStatus =
  | 'matched'
  | 'unmatched'
  | 'incomplete'
  | 'raw-leading'
  | 'leading'
  | 'confirmed'
  | 'leading-confirmed'
  | 'stable'
  | 'yellow'
  | 'red'

const props = withDefaults(defineProps<{ indexCode?: string }>(), {
  indexCode: 'sh000852',
})

const dashboard = ref<QuantRiskDashboardResponse | null>(null)
const evidence = ref<QuantRiskEvidenceResponse | null>(null)
const loading = ref(false)
const evidenceLoading = ref(false)
const historyLoading = ref(false)
const historyExhausted = ref(false)
const error = ref('')
const evidenceError = ref('')
const historyError = ref('')
const committedDate = ref<string | null>(null)
const previewDate = ref<string | null>(null)
const selectedEventId = ref<string | null>(null)
const expandedEventIds = ref<string[]>([])
let dashboardController: AbortController | null = null
let evidenceController: AbortController | null = null
let historyController: AbortController | null = null

const pointMap = computed(
  () => new Map((dashboard.value?.points ?? []).map((item) => [item.trade_date, item])),
)
const isFlatScoring = computed(() => dashboard.value?.scoring_mode === 'flat')
const targetName = computed(() => dashboard.value?.target_name ?? (props.indexCode === 'sh000300' ? '沪深300' : '中证1000'))
const candleDates = computed(() => (dashboard.value?.candles ?? []).map((item) => item.trade_date))
const displayDate = computed(() => previewDate.value ?? committedDate.value)
const selectedPoint = computed(() => displayDate.value ? pointMap.value.get(displayDate.value) ?? null : null)
const previewPending = computed(() => previewDate.value != null && previewDate.value !== committedDate.value)
const selectedDisplayState = computed(() => scoreDisplayState(selectedPoint.value))
const selectedBaseState = computed(() => {
  if (selectedPoint.value?.overall_score == null) return null
  if (selectedPoint.value.overall_score > 50) return 'red'
  if (selectedPoint.value.overall_score >= 40) return 'yellow'
  return 'stable'
})
const selectedRiskLabel = computed(() => displayStateLabel(selectedDisplayState.value))
const sortedEvents = computed(() =>
  [...(dashboard.value?.events ?? [])].sort((left, right) => right.start_date.localeCompare(left.start_date)),
)
const globalRiskStatus = computed<RiskModuleStatus>(() => {
  const point = selectedPoint.value
  if (!point) return 'incomplete'
  if (isFlatScoring.value) {
    if (point.global_shock === true) return 'confirmed'
    if (point.global_shock === false) return 'unmatched'
    return 'incomplete'
  }
  if (point.global_leading === true && point.global_shock === true) return 'leading-confirmed'
  if (point.global_shock === true) return 'confirmed'
  if (point.global_leading === true) return 'leading'
  if (point.global_raw_leading === true) return 'raw-leading'
  if (
    point.global_raw_leading === false
    && point.global_leading === false
    && point.global_shock === false
  ) return 'unmatched'
  return 'incomplete'
})
const flatLeadingStatus = computed<RiskModuleStatus>(() => {
  const point = selectedPoint.value
  if (!point) return 'incomplete'
  if (point.global_leading === true) return 'leading'
  if (point.global_raw_leading === true && point.global_leading === false) return 'raw-leading'
  if (point.global_raw_leading === false && point.global_leading === false) return 'unmatched'
  return 'incomplete'
})
const inspectorModules = computed(() => {
  if (isFlatScoring.value) {
    const baseStatus: RiskModuleStatus = selectedPoint.value?.overall_score == null
      ? 'incomplete'
      : selectedPoint.value.overall_score > 50
        ? 'red'
        : selectedPoint.value.overall_score >= 40
          ? 'yellow'
          : 'stable'
    return [
      {
        key: 'overall-score',
        label: '唯一总分状态',
        tone: baseStatus,
        status: baseStatus,
      },
      {
        key: 'global-leading-observation',
        label: '全球前兆（观察）',
        tone: 'global',
        status: flatLeadingStatus.value,
      },
      {
        key: 'global-confirmation',
        label: '全球冲击确认（计分）',
        tone: 'global',
        status: globalRiskStatus.value,
      },
    ]
  }
  return [
    {
      key: 'domestic-vulnerability',
      label: '国内脆弱积累',
      tone: 'yellow',
      status: riskModuleStatus(selectedPoint.value?.yellow_vulnerability),
    },
    {
      key: 'domestic-deterioration',
      label: '国内风险恶化',
      tone: 'red',
      status: riskModuleStatus(selectedPoint.value?.red_escalation),
    },
    {
      key: 'global-shock',
      label: '全球风险',
      tone: 'global',
      status: globalRiskStatus.value,
    },
  ]
})
const evidenceSections = computed(() => {
  const sections: Array<{
    key: string
    strategyKey: string
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
const selectedAdvice = computed(() => buildAdvice(selectedPoint.value, selectedDisplayState.value))

function isCanceledRequest(cause: unknown) {
  const payload = cause as { name?: string; code?: string } | null
  return payload?.name === 'CanceledError' || payload?.name === 'AbortError' || payload?.code === 'ERR_CANCELED'
}

async function loadDashboard() {
  dashboardController?.abort()
  historyController?.abort()
  const controller = new AbortController()
  dashboardController = controller
  loading.value = true
  error.value = ''
  try {
    const response = await fetchQuantRiskDashboard({
      indexCode: props.indexCode,
      mode: 'default',
      signal: controller.signal,
    })
    if (dashboardController !== controller) return
    dashboard.value = response
    const dates = response.points.map((item) => item.trade_date)
    committedDate.value = committedDate.value && dates.includes(committedDate.value)
      ? committedDate.value
      : dates[dates.length - 1] ?? null
    previewDate.value = null
    selectedEventId.value = null
    historyExhausted.value = false
    historyError.value = ''
    await loadEvidenceForDate(committedDate.value)
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

function shiftDateBackOneYear(value: string) {
  const [year, month, day] = value.split('-').map(Number)
  return `${year - 1}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

async function loadEarlierHistory(earliestTradeDate: string) {
  const current = dashboard.value
  if (
    !current
    || historyLoading.value
    || historyExhausted.value
    || earliestTradeDate !== current.candles[0]?.trade_date
  ) {
    return
  }
  historyController?.abort()
  const controller = new AbortController()
  historyController = controller
  historyLoading.value = true
  historyError.value = ''
  try {
    const response = await fetchQuantRiskDashboard({
      indexCode: props.indexCode,
      mode: 'custom',
      startDate: shiftDateBackOneYear(current.start_date),
      endDate: current.end_date,
      signal: controller.signal,
    })
    if (historyController !== controller) return
    historyExhausted.value = response.start_date >= current.start_date
    dashboard.value = response
    if (
      selectedEventId.value
      && !response.events.some((item) => item.event_id === selectedEventId.value)
    ) {
      selectedEventId.value = null
    }
  } catch (cause) {
    if (!isCanceledRequest(cause) && historyController === controller) {
      historyError.value = cause instanceof Error ? cause.message : '更早历史加载失败'
    }
  } finally {
    if (historyController === controller) {
      historyController = null
      historyLoading.value = false
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
    const response = await fetchQuantRiskEvidence(
      startDate,
      endDate,
      props.indexCode,
      controller.signal,
    )
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

function commitChartDate(tradeDate: string) {
  previewDate.value = null
  if (committedDate.value === tradeDate && evidence.value?.dates.includes(tradeDate)) return
  committedDate.value = tradeDate
  selectedEventId.value = null
  void loadEvidenceForDate(tradeDate)
}

function selectEvent(event: QuantRiskEvent) {
  selectedEventId.value = event.event_id
  previewDate.value = null
  committedDate.value = event.first_trigger_date
  const window = eventEvidenceWindow(event)
  void loadEvidence(window.start, window.end)
}

function toggleEventDetails(event: QuantRiskEvent) {
  selectEvent(event)
  expandedEventIds.value = expandedEventIds.value.includes(event.event_id)
    ? expandedEventIds.value.filter((item) => item !== event.event_id)
    : [...expandedEventIds.value, event.event_id]
}

function previewChartDate(tradeDate: string) {
  previewDate.value = tradeDate
}

function clearChartPreview() {
  previewDate.value = null
}

function formatScore(value: number | null) {
  return value == null ? '--' : value.toFixed(2)
}

function formatSignalState(
  value: boolean | null | undefined,
  activeLabel: string,
  inactiveLabel: string,
) {
  if (value == null) return '缺失'
  return value ? activeLabel : inactiveLabel
}

function scoreDisplayState(point: QuantRiskDashboardPoint | null): QuantRiskDisplayState {
  if (point?.overall_score == null) return 'incomplete'
  const baseState = point.overall_score > 50
    ? 'red'
    : point.overall_score >= 40
      ? 'yellow'
      : 'stable'
  const globalOverlay = point.global_shock === true
    || (!isFlatScoring.value && point.global_leading === true)
  if (!globalOverlay) return baseState
  if (baseState === 'red') return 'red_global'
  if (baseState === 'yellow') return 'yellow_global'
  return 'global'
}

function displayStateLabel(state: QuantRiskDisplayState) {
  return {
    stable: '平稳',
    global: '全球风险',
    yellow: '黄色',
    yellow_global: '黄色+全球',
    red: '红色',
    red_global: '红色+全球',
    incomplete: '数据不完整',
  }[state]
}

function buildAdvice(point: QuantRiskDashboardPoint | null, displayState: QuantRiskDisplayState) {
  if (!point) return '暂无可用风险建议'
  if (!point.data_complete || displayState === 'incomplete') {
    return '数据不完整，暂不把缺失当作风险解除'
  }
  const leadingOnly = point.global_leading === true && point.global_shock !== true
  if (displayState === 'red_global' && leadingOnly) return '全球风险前兆已出现，按大级别调整提前管理风险'
  if (displayState === 'red_global') return '按大级别调整管理风险，并优先控制总风险敞口'
  if (displayState === 'red') return '按大级别调整管理风险，不按普通回踩处理'
  if (displayState === 'yellow_global' && leadingOnly) return '全球风险前兆已出现，降低高弹性仓位、停止追涨'
  if (displayState === 'yellow_global') return '降低高弹性仓位、停止追涨，同时控制外部风险敞口'
  if (displayState === 'yellow') return '降低高弹性仓位、停止追涨'
  if (displayState === 'global' && leadingOnly) return '全球风险前兆已出现，提前控制外部风险敞口'
  if (displayState === 'global') return '全球冲击已成立，优先控制总风险敞口'
  return '统一风险评分处于平稳区间'
}

function riskModuleStatus(value: boolean | null | undefined): RiskModuleStatus {
  if (value == null) return 'incomplete'
  return value ? 'matched' : 'unmatched'
}

function riskModuleStatusLabel(value: RiskModuleStatus, flatScoring = false) {
  if (value === 'leading-confirmed') return '前兆+确认'
  if (value === 'raw-leading') return '原始前兆'
  if (value === 'leading') return flatScoring ? '沪深300生效' : 'A股前兆'
  if (value === 'confirmed') return '确认'
  if (value === 'matched') return '满足'
  if (value === 'unmatched') return '未满足'
  if (value === 'stable') return '平稳'
  if (value === 'yellow') return '黄色'
  if (value === 'red') return '红色'
  return '数据不完整'
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
    ...(cell.level_value == null ? [] : [`当前收益率：${cell.level_value.toFixed(2)}%`]),
    `百分位：${cell.percentile == null ? '--' : `${cell.percentile.toFixed(2)}%`}`,
    `阈值：${thresholdText(cell) || '--'}`,
    `状态：${evidenceStateLabel(cell)}`,
    ...(cell.score == null ? [] : [`因子分：${cell.score.toFixed(2)}`]),
    ...(cell.weight == null ? [] : [`权重：${(cell.weight * 100).toFixed(0)}%`]),
    ...(cell.contribution == null ? [] : [`总分贡献：${cell.contribution.toFixed(2)}`]),
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
    yellow: row.strategy_key === 'domestic_vulnerability',
    red: row.strategy_key === 'domestic_deterioration',
    global: row.strategy_key === 'global_shock',
    flat: row.strategy_key === 'flat_score',
    selected: cell.trade_date === committedDate.value,
  }
}

function formatShortDate(value: string | null) {
  return value ? value.slice(5) : '--'
}

function eventRange(event: QuantRiskEvent) {
  return `${event.start_date} — ${event.is_open ? '进行中' : formatShortDate(event.end_date)}`
}

function displayStateClass(state: QuantRiskDisplayState | null) {
  return state ?? 'incomplete'
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

watch(
  () => props.indexCode,
  () => {
    dashboard.value = null
    evidence.value = null
    committedDate.value = null
    previewDate.value = null
    selectedEventId.value = null
    expandedEventIds.value = []
    historyExhausted.value = false
    void loadDashboard()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  dashboardController?.abort()
  evidenceController?.abort()
  historyController?.abort()
})
</script>

<template>
  <section class="risk-page">
    <section class="card risk-title-card">
      <div>
        <h2>{{ targetName }}风险监控</h2>
        <p v-if="isFlatScoring" class="muted">七项唯一因子直接形成总分；全球原始前兆与沪深300有效前兆只观察，全球确认只计分一次。</p>
        <p v-else class="muted">国内脆弱、国内恶化与全球冲击统一评分，只表示风险状态，不产生买卖交易。</p>
      </div>
    </section>

    <div v-if="error" class="card risk-state error-state">{{ error }}</div>
    <div v-else-if="loading && !dashboard" class="card risk-state">正在加载风险历史...</div>

    <template v-if="dashboard">
      <section class="card risk-summary" :class="{ flat: isFlatScoring }">
        <div class="summary-item composite">
          <span>{{ previewPending ? '光标日' : '已确认日' }}统一风险总分</span>
          <strong :class="selectedBaseState ?? ''">
            {{ formatScore(selectedPoint?.overall_score ?? null) }}
            <small v-if="selectedPoint?.overall_score != null">/ 100 · {{ selectedRiskLabel }}</small>
            <small v-else>数据不完整</small>
          </strong>
        </div>
        <div v-if="!isFlatScoring" class="summary-item yellow">
          <span>国内脆弱积累 · 35%</span>
          <strong><i></i>{{ formatScore(selectedPoint?.domestic_vulnerability_score ?? null) }} <small>贡献 {{ formatScore(selectedPoint?.domestic_vulnerability_contribution ?? null) }}</small></strong>
        </div>
        <div v-if="!isFlatScoring" class="summary-item red">
          <span>国内风险恶化 · 35%</span>
          <strong><i></i>{{ formatScore(selectedPoint?.domestic_deterioration_score ?? null) }} <small>贡献 {{ formatScore(selectedPoint?.domestic_deterioration_contribution ?? null) }}</small></strong>
        </div>
        <div class="summary-item global">
          <span>{{ isFlatScoring ? '全球冲击确认 · 30%' : '全球风险 · 30%' }}</span>
          <strong><i></i>{{ formatScore(selectedPoint?.global_score ?? null) }} <small>贡献 {{ formatScore(selectedPoint?.global_contribution ?? null) }}</small></strong>
          <small v-if="!isFlatScoring" class="global-score-detail">
            原始 {{ formatScore(selectedPoint?.global_raw_leading_score ?? null) }}
            {{ formatSignalState(selectedPoint?.global_raw_leading, '触发', '未触发') }} ·
            A股 {{ formatSignalState(selectedPoint?.global_leading, '生效', '未生效') }} ·
            确认 {{ formatScore(selectedPoint?.global_confirmation_score ?? null) }}
          </small>
        </div>
        <div v-if="isFlatScoring" class="summary-item global observation">
          <span>全球前兆 · 仅观察</span>
          <strong>
            <i></i>原始 {{ formatScore(selectedPoint?.global_raw_leading_score ?? null) }}
            <small>{{ formatSignalState(selectedPoint?.global_raw_leading, '触发', '未触发') }}</small>
          </strong>
          <small class="global-score-detail">
            沪深300 {{ formatSignalState(selectedPoint?.global_leading, '生效', '未生效') }} ·
            国内门槛 {{ formatScore(selectedPoint?.global_leading_gate_score ?? null) }}
            （{{ formatScore(selectedPoint?.global_leading_trigger_threshold ?? null) }}/{{ formatScore(selectedPoint?.global_leading_release_threshold ?? null) }}）
          </small>
          <small class="global-score-detail">
            有效至 {{ selectedPoint?.global_leading_valid_through ?? '--' }} · 不进入总分和颜色
          </small>
        </div>
        <div class="summary-item advice">
          <span>最终状态 · {{ displayDate ?? '--' }}</span>
          <strong :class="displayStateClass(selectedDisplayState)">{{ selectedRiskLabel }}</strong>
          <small>{{ selectedAdvice }}</small>
        </div>
      </section>

      <div class="risk-workbench">
        <section class="card chart-panel">
          <div class="panel-head">
            <div>
              <strong>{{ targetName }} · K线与风险状态</strong>
              <span>
                悬停查看 · 单击锁定 · 滚轮缩放
                <template v-if="historyLoading"> · 正在加载更早历史</template>
                <template v-else-if="historyError"> · {{ historyError }}</template>
              </span>
            </div>
            <div class="state-legend" aria-label="最终风险状态图例">
              <span class="yellow">黄色</span><span class="global">全球</span>
              <span class="yellow_global">黄色+全球</span><span class="red">红色</span>
              <span class="red_global">红色+全球</span>
            </div>
          </div>
          <RiskMonitorChart
            :candles="dashboard.candles"
            :points="dashboard.points"
            :committed-date="committedDate"
            :has-more-history="!historyExhausted"
            :loading-more-history="historyLoading"
            @preview-date="previewChartDate"
            @preview-clear="clearChartPreview"
            @commit-date="commitChartDate"
            @request-more-history="loadEarlierHistory"
          />
        </section>

        <aside class="card inspector-panel">
          <div class="panel-head inspector-head">
            <div>
              <strong>{{ displayDate ?? '--' }} · 日期复盘</strong>
              <span>{{ previewPending ? '随光标查看；单击后更新证据矩阵' : '已锁定日期' }}</span>
            </div>
          </div>
          <div class="inspector-body">
            <span class="inspector-label">综合风险完成度 · 黄色40–50 / 红色&gt;50</span>
            <div class="inspector-score" :class="selectedBaseState ?? ''">
              {{ formatScore(selectedPoint?.overall_score ?? null) }}
              <small>{{ selectedRiskLabel }}</small>
            </div>
            <div class="score-bar"><span :style="{ width: `${selectedPoint?.overall_score ?? 0}%` }"></span></div>

            <div class="module-status-list">
              <div
                v-for="module in inspectorModules"
                :key="module.key"
                class="module-status-row"
                :class="module.tone"
              >
                <span>{{ module.label }}</span>
                <b :class="module.status">{{ riskModuleStatusLabel(module.status, isFlatScoring) }}</b>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <section class="card evidence-panel">
        <div class="panel-head matrix-head">
          <div>
            <strong>底层证据矩阵</strong>
            <span>
              锁定 {{ committedDate ?? '--' }} ·
              {{ selectedEventId ? '选中事件及前后5个交易日' : '已确认日期前后10个交易日' }}
            </span>
          </div>
          <div class="matrix-legend">
            <template v-if="isFlatScoring">
              <span><i class="flat"></i>计分因子满足</span>
            </template>
            <template v-else>
              <span><i class="yellow"></i>国内脆弱</span>
              <span><i class="red"></i>国内恶化</span>
              <span><i class="global"></i>全球</span>
            </template>
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
                  :class="{ selected: tradeDate === committedDate }"
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
                  :class="{ 'selected-column': cell.trade_date === committedDate }"
                >
                  <button
                    type="button"
                    class="evidence-cell"
                    :class="evidenceCellClass(row, cell)"
                    :title="evidenceTooltip(row, cell)"
                    :aria-label="`${cell.trade_date} ${row.label} ${evidenceStateLabel(cell)}`"
                    @click="commitChartDate(cell.trade_date)"
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
                      v-for="span in event.state_spans"
                      :key="`${span.display_state}:${span.start_date}`"
                      class="event-chip"
                      :class="span.display_state"
                    >{{ span.state_label }}</span>
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
                      <article v-for="span in event.state_spans" :key="`${span.display_state}-${span.start_date}`">
                        <strong :class="span.display_state">{{ span.state_label }}</strong>
                        <span>{{ span.start_date }} — {{ span.end_date }} · {{ span.active_days }}日</span>
                        <small>{{ span.key_evidence.join('、') || '统一评分达到该状态区间' }}</small>
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

.detail-button {
  border: 0;
  background: transparent;
  color: #607086;
  cursor: pointer;
  font: inherit;
}

.risk-state { padding: 24px; color: #64748b; text-align: center; }
.error-state { color: #b91c1c; background: #fff7f7; }

.risk-summary {
  display: grid;
  grid-template-columns: 1.18fr .88fr .88fr .95fr 1.65fr;
  overflow: hidden;
}
.risk-summary.flat { grid-template-columns: 1.18fr .95fr .95fr 1.65fr; }

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
.global-score-detail { display: block; margin-top: 2px; color: #7d709f; font-size: 9px; }
.summary-item.advice strong { font-size: 12px; font-weight: 700; }
.summary-item.advice > small { display: block; margin-top: 3px; color: #748196; font-size: 9px; line-height: 1.4; }
.summary-item strong.stable { color: #25806a; }
.summary-item strong.yellow { color: #b7791f; }
.summary-item strong.global { color: #6e50b8; }
.summary-item strong.yellow_global { color: #c35d28; }
.summary-item strong.red { color: #c94444; }
.summary-item strong.red_global { color: #762d58; }
.summary-item strong.incomplete { color: #7d8999; }

.risk-workbench { display: grid; grid-template-columns: minmax(0, 1fr) 286px; gap: 12px; min-width: 0; }
.chart-panel,
.inspector-panel,
.evidence-panel,
.events-panel { min-width: 0; overflow: hidden; }
.panel-head { min-height: 48px; padding: 10px 13px; border-bottom: 1px solid #e7ebf1; }
.panel-head > div:first-child { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.panel-head strong { color: #27364a; font-size: 13px; }
.panel-head span { color: #768397; font-size: 10px; }

.state-legend { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 4px; }
.state-legend span { padding: 3px 6px; border-radius: 3px; color: #fff; font-size: 8px; font-weight: 700; }
.state-legend .yellow { background: #d89a18; }
.state-legend .global { background: #7657c8; }
.state-legend .yellow_global { background: #d56b2f; }
.state-legend .red { background: #dc4f4f; }
.state-legend .red_global { background: #762d58; }

.inspector-body { padding: 13px 14px; }
.inspector-label { color: #718096; font-size: 10px; }
.inspector-score { margin: 4px 0 8px; color: #315fa8; font-size: 24px; font-weight: 800; }
.inspector-score small { margin-left: 4px; font-size: 11px; }
.inspector-score.yellow { color: #b7791f; }
.inspector-score.red { color: #c94444; }
.score-bar { height: 6px; overflow: hidden; border-radius: 999px; background: #edf1f5; }
.score-bar span { display: block; height: 100%; background: #c94444; transition: width .2s ease; }
.module-status-list { display: grid; gap: 7px; margin-top: 13px; }
.module-status-row { display: flex; align-items: center; justify-content: space-between; min-height: 34px; padding: 7px 9px; border-left: 3px solid #94a3b8; background: #f7f9fc; }
.module-status-row.yellow { border-left-color: #d89a18; }
.module-status-row.red { border-left-color: #dc4f4f; }
.module-status-row.global { border-left-color: #7657c8; }
.module-status-row.stable { border-left-color: #25806a; }
.module-status-row span { color: #334155; font-size: 11px; font-weight: 700; }
.module-status-row b { color: #64748b; font-size: 10px; }
.module-status-row b.matched { color: #b42333; }
.module-status-row b.stable { color: #25806a; }
.module-status-row b.yellow { color: #b7791f; }
.module-status-row b.red { color: #c94444; }
.module-status-row b.leading,
.module-status-row b.raw-leading,
.module-status-row b.confirmed,
.module-status-row b.leading-confirmed { color: #6544aa; }
.module-status-row b.incomplete { color: #a06b10; }

.matrix-head { flex-wrap: wrap; }
.matrix-legend { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.matrix-legend span { display: inline-flex; align-items: center; gap: 4px; }
.matrix-legend i { width: 9px; height: 9px; border-radius: 2px; }
.matrix-legend i.yellow { background: #d89a18; }
.matrix-legend i.red { background: #dc4f4f; }
.matrix-legend i.global { background: #7657c8; }
.matrix-legend i.flat { background: #315fa8; }
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
.section-row th.domestic_vulnerability { color: #a86e14; }
.section-row th.domestic_deterioration { color: #bd3d3d; }
.section-row th.global_shock { color: #6544aa; }
.section-row th.flat_score { color: #315fa8; }
.evidence-table td { min-width: 31px; padding: 0; }
.evidence-table td.selected-column { background: #edf5ff; }
.evidence-cell { display: block; width: 100%; height: 18px; border: 1px solid rgba(51, 65, 85, .05); border-radius: 3px; background: #e9edf2; cursor: pointer; }
.evidence-cell.matched.yellow { background: rgba(216, 154, 24, .82); }
.evidence-cell.matched.red { background: rgba(220, 79, 79, .82); }
.evidence-cell.matched.global { background: rgba(118, 87, 200, .82); }
.evidence-cell.matched.flat { background: rgba(49, 95, 168, .82); }
.evidence-cell.partial.yellow { background: rgba(216, 154, 24, .34); }
.evidence-cell.partial.red { background: rgba(220, 79, 79, .34); }
.evidence-cell.partial.global { background: rgba(118, 87, 200, .34); }
.evidence-cell.partial.flat { background: rgba(49, 95, 168, .34); }
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
.event-chip.yellow { color: #8b5a0f; background: #fff2c8; }
.event-chip.global { color: #59349a; background: #eee8ff; }
.event-chip.yellow_global { color: #914019; background: #ffe5d5; }
.event-chip.red { color: #9f2929; background: #ffe0e0; }
.event-chip.red_global { color: #642044; background: #f1dce8; }
.events-table .drawdown { color: #c94444; font-weight: 700; }
.detail-button { padding: 4px 6px; border: 1px solid #d9e1eb; border-radius: 3px; background: #fff; color: #315fa8; font-size: 9px; }
.event-detail-row td { padding: 10px 12px; background: #f9fbfd; }
.event-spans { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.event-spans article { padding: 8px; border: 1px solid #e2e8f0; border-radius: 4px; background: #fff; }
.event-spans strong,
.event-spans span,
.event-spans small { display: block; }
.event-spans strong { margin-bottom: 4px; font-size: 10px; }
.event-spans strong.yellow { color: #a86e14; }
.event-spans strong.global { color: #6544aa; }
.event-spans strong.yellow_global { color: #bd5b2c; }
.event-spans strong.red { color: #bd3d3d; }
.event-spans strong.red_global { color: #762d58; }
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
  .module-status-list { grid-column: 1 / -1; }
  .event-spans { grid-template-columns: 1fr; }
}

@media (max-width: 760px) {
  .risk-title-card { align-items: flex-start; }
  .risk-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .summary-item { border-bottom: 1px solid #e7ebf1; }
  .summary-item:nth-child(2n) { border-right: 0; }
  .summary-item.advice { grid-column: 1 / -1; }
  .inspector-panel { display: block; }
  .inspector-head { border-right: 0; border-bottom: 1px solid #e7ebf1; }
  .inspector-body { display: block; }
}
</style>
