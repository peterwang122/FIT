<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  backtestQuantSequenceScan,
  deleteQuantStrategy,
  fetchQuantStrategies,
  fetchQuantStrategyEquityCurve,
  previewQuantSequenceScan,
  sendQuantStrategy,
  updateQuantStrategy,
} from '../api/stocks'
import StrategyEquityCurveChart from '../components/StrategyEquityCurveChart.vue'
import { useAuthStore } from '../stores/auth'
import type {
  QuantConflictMode,
  QuantEquityCurveResponse,
  QuantExecutionPriceMode,
  QuantPositionPair,
  QuantScanEvent,
  QuantScanBacktestSelection,
  QuantSequenceScanBacktestResponse,
  QuantSignalColor,
  QuantStrategyConfig,
  QuantStrategyPayload,
} from '../types/quant'
import type { UserSearchResult } from '../types/auth'

const strategies = ref<QuantStrategyConfig[]>([])
const selectedStrategyId = ref<number | null>(null)
const editingStrategy = ref<QuantStrategyConfig | null>(null)
const equityCurve = ref<QuantEquityCurveResponse | null>(null)
const sequenceScanBacktest = ref<QuantSequenceScanBacktestResponse | null>(null)
const sequenceScanResultId = ref('')
const sequenceScanSelection = ref<QuantScanBacktestSelection>({
  use_all_events: true,
  excluded_event_ids: [],
})
const sequenceScanPage = ref(1)
const sequenceScanPageSize = ref(100)

const loading = ref(false)
const curveLoading = ref(false)
const curveRequested = ref(false)
const error = ref('')
const saveMessage = ref('')

const router = useRouter()
const authStore = useAuthStore()

const sendDialogOpen = ref(false)
const recipientKeyword = ref('')
const recipientLoading = ref(false)
const recipientOptions = ref<UserSearchResult[]>([])
const selectedRecipient = ref<UserSearchResult | null>(null)
const sendLoading = ref(false)
const showRecipientSuggestions = ref(false)
let recipientSearchTimer: number | null = null

const isRoot = computed(() => authStore.isRoot)

const signalColorOptions: Array<{ value: QuantSignalColor; label: string }> = [
  { value: 'blue', label: '蓝色' },
  { value: 'red', label: '红色' },
]

const conflictModeOptions: Array<{ value: QuantConflictMode; label: string }> = [
  { value: 'sell_first', label: '紫色冲突优先卖出' },
  { value: 'buy_first', label: '紫色冲突优先买入' },
  { value: 'skip', label: '紫色冲突跳过' },
]

const executionModeOptions: Array<{ value: QuantExecutionPriceMode; label: string }> = [
  { value: 'next_open', label: '次日开盘价' },
  { value: 'next_close', label: '次日收盘价' },
  { value: 'next_best', label: '次日最优价' },
]

const priceBasisOptions: Array<{ value: 'open' | 'close'; label: string }> = [
  { value: 'open', label: '开盘价' },
  { value: 'close', label: '收盘价' },
]

const DEFAULT_SCAN_TRADE_CONFIG = {
  initial_capital: 1_000_000,
  buy_amount_per_event: 10_000,
  buy_offset_trading_days: 1,
  sell_offset_trading_days: 2,
  buy_price_basis: 'open' as const,
  sell_price_basis: 'open' as const,
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function isMarketScanStrategy(strategy: QuantStrategyConfig | null | undefined) {
  return strategy?.strategy_engine === 'sequence' && strategy.sequence_mode === 'market_scan'
}

function strategyTypeLabel(strategyType: QuantStrategyConfig['strategy_type']) {
  if (strategyType === 'index') return '指数策略'
  if (strategyType === 'etf') return 'ETF 策略'
  return '股票策略'
}

function strategyEngineLabel(strategy: QuantStrategyConfig) {
  if (strategy.strategy_engine !== 'sequence') return '单日策略'
  return strategy.sequence_mode === 'market_scan' ? '条件策略 / 扫描模式' : '条件策略 / 单标的'
}

function analysisPathForStrategy(strategy: QuantStrategyConfig) {
  if (strategy.strategy_engine === 'sequence') return '/quant/sequence'
  return strategy.strategy_type === 'index' ? '/quant/index' : '/quant/stock'
}

function analysisButtonLabel(strategy: QuantStrategyConfig) {
  if (strategy.strategy_engine === 'sequence') return '加载到条件策略'
  return strategy.strategy_type === 'index' ? '加载到指数分析' : '加载到股票分析'
}

function formatPositionPct(value: number) {
  return `${(value * 100).toFixed(0)}%`
}

function formatPositionPair(pair: QuantPositionPair) {
  return `买入 ${formatPositionPct(pair.buy_position_pct)} / 卖出 ${formatPositionPct(pair.sell_position_pct)}`
}

function formatPositionPairWithReturn(pair: QuantPositionPair) {
  const base = formatPositionPair(pair)
  if (pair.cumulative_return_pct === null || pair.cumulative_return_pct === undefined || Number.isNaN(pair.cumulative_return_pct)) {
    return base
  }
  return `${base} / 总收益 ${pair.cumulative_return_pct.toFixed(2)}%`
}

function formatRecipientDisplay(option: UserSearchResult) {
  return `${option.nickname || option.username} / ${option.phone || option.username}`
}

function cloneStrategy(strategy: QuantStrategyConfig): QuantStrategyConfig {
  return {
    ...strategy,
    notes: strategy.notes ?? '',
    indicator_params: cloneJson(strategy.indicator_params),
    buy_sequence_groups: cloneJson(strategy.buy_sequence_groups ?? []),
    sell_sequence_groups: cloneJson(strategy.sell_sequence_groups ?? []),
    scan_trade_config: {
      ...DEFAULT_SCAN_TRADE_CONFIG,
      ...cloneJson(strategy.scan_trade_config ?? {}),
    },
    blue_filter_groups: cloneJson(strategy.blue_filter_groups ?? []),
    red_filter_groups: cloneJson(strategy.red_filter_groups ?? []),
    blue_filters: cloneJson(strategy.blue_filters),
    red_filters: cloneJson(strategy.red_filters),
    blue_boll_filter: cloneJson(strategy.blue_boll_filter),
    red_boll_filter: cloneJson(strategy.red_boll_filter),
  }
}

function toPayload(strategy: QuantStrategyConfig): QuantStrategyPayload {
  return {
    name: strategy.name,
    notes: strategy.notes ?? '',
    strategy_engine: strategy.strategy_engine,
    sequence_mode: strategy.sequence_mode,
    strategy_type: strategy.strategy_type,
    target_code: strategy.target_code,
    target_name: strategy.target_name,
    indicator_params: strategy.indicator_params,
    buy_sequence_groups: strategy.buy_sequence_groups,
    sell_sequence_groups: strategy.sell_sequence_groups,
    scan_trade_config: strategy.scan_trade_config,
    blue_filter_groups: strategy.blue_filter_groups,
    red_filter_groups: strategy.red_filter_groups,
    blue_filters: strategy.blue_filters,
    red_filters: strategy.red_filters,
    blue_boll_filter: strategy.blue_boll_filter,
    red_boll_filter: strategy.red_boll_filter,
    signal_buy_color: strategy.signal_buy_color,
    signal_sell_color: strategy.signal_sell_color,
    purple_conflict_mode: strategy.purple_conflict_mode,
    start_date: strategy.start_date || null,
    scan_start_date: strategy.scan_start_date || null,
    scan_end_date: strategy.scan_end_date || null,
    buy_position_pct: strategy.buy_position_pct,
    sell_position_pct: strategy.sell_position_pct,
    execution_price_mode: strategy.execution_price_mode,
  }
}

function buildScanPreviewPayload(strategy: QuantStrategyConfig) {
  return {
    strategy_type: strategy.strategy_type,
    buy_sequence_groups: strategy.buy_sequence_groups,
    scan_trade_config: {
      ...DEFAULT_SCAN_TRADE_CONFIG,
      ...(strategy.scan_trade_config ?? {}),
    },
    scan_start_date: strategy.scan_start_date || '',
    scan_end_date: strategy.scan_end_date || '',
  }
}

function resetSequenceScanState() {
  sequenceScanResultId.value = ''
  sequenceScanSelection.value = { use_all_events: true, excluded_event_ids: [] }
  sequenceScanPage.value = 1
  sequenceScanBacktest.value = null
}

async function loadStrategies(preferredId?: number | null) {
  loading.value = true
  error.value = ''
  try {
    strategies.value = await fetchQuantStrategies()
    const nextId = preferredId ?? selectedStrategyId.value ?? strategies.value[0]?.id ?? null
    if (nextId && strategies.value.some((item) => item.id === nextId)) {
      selectStrategy(nextId)
    } else {
      selectedStrategyId.value = null
      editingStrategy.value = null
      equityCurve.value = null
      resetSequenceScanState()
      curveRequested.value = false
    }
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : '策略加载失败'
  } finally {
    loading.value = false
  }
}

async function loadEquityCurve(strategyId: number) {
  curveLoading.value = true
  error.value = ''
  try {
    equityCurve.value = await fetchQuantStrategyEquityCurve(strategyId)
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : '收益曲线加载失败'
    equityCurve.value = null
  } finally {
    curveLoading.value = false
  }
}

async function loadSequenceScanBacktest(strategy: QuantStrategyConfig, page = sequenceScanPage.value, resetScanResult = false) {
  curveLoading.value = true
  error.value = ''
  try {
    if (resetScanResult || !sequenceScanResultId.value) {
      const preview = await previewQuantSequenceScan(buildScanPreviewPayload(strategy))
      sequenceScanResultId.value = preview.scan_result_id
      sequenceScanPage.value = preview.page
      sequenceScanPageSize.value = preview.page_size
    }
    const response = await backtestQuantSequenceScan({
      scan_result_id: sequenceScanResultId.value,
      scan_trade_config: {
        ...DEFAULT_SCAN_TRADE_CONFIG,
        ...(strategy.scan_trade_config ?? {}),
      },
      selection: sequenceScanSelection.value,
      page,
      page_size: sequenceScanPageSize.value,
    })
    sequenceScanBacktest.value = response
    sequenceScanPage.value = response.page
    sequenceScanPageSize.value = response.page_size
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : '扫描回测加载失败'
    sequenceScanBacktest.value = null
  } finally {
    curveLoading.value = false
  }
}

function selectStrategy(strategyId: number) {
  const target = strategies.value.find((item) => item.id === strategyId)
  if (!target) return
  selectedStrategyId.value = strategyId
  editingStrategy.value = cloneStrategy(target)
  equityCurve.value = null
  resetSequenceScanState()
  curveRequested.value = false
  curveLoading.value = false
  saveMessage.value = ''
  error.value = ''
}

async function persistStrategy(showSavedMessage = true) {
  if (!editingStrategy.value) return null
  error.value = ''
  if (showSavedMessage) saveMessage.value = ''
  try {
    const updated = await updateQuantStrategy(editingStrategy.value.id, toPayload(editingStrategy.value))
    await loadStrategies(updated.id)
    if (showSavedMessage) {
      saveMessage.value = `已更新策略：${updated.name}`
    }
    return updated
  } catch (saveError) {
    error.value = saveError instanceof Error ? saveError.message : '策略保存失败'
    return null
  }
}

async function saveStrategy() {
  await persistStrategy(true)
}

async function confirmAndLoadCurve() {
  if (!editingStrategy.value) return
  saveMessage.value = ''
  const updated = await persistStrategy(false)
  if (!updated) return
  curveRequested.value = true
  equityCurve.value = null
  resetSequenceScanState()
  if (isMarketScanStrategy(updated)) {
    if (!updated.scan_start_date || !updated.scan_end_date) {
      error.value = '全市场扫描策略必须先设置扫描开始日期和结束日期'
      curveRequested.value = false
      return
    }
    await loadSequenceScanBacktest(updated, 1, true)
    return
  }
  await loadEquityCurve(updated.id)
}

async function toggleSequenceScanEvent(eventId: string, checked: boolean) {
  if (!editingStrategy.value || !sequenceScanBacktest.value || !isMarketScanStrategy(editingStrategy.value)) return
  const excluded = new Set(sequenceScanSelection.value.excluded_event_ids)
  if (checked) excluded.delete(eventId)
  else excluded.add(eventId)
  sequenceScanSelection.value = {
    use_all_events: true,
    excluded_event_ids: [...excluded],
  }
  await loadSequenceScanBacktest(editingStrategy.value, sequenceScanPage.value, false)
}

async function changeSequenceScanPage(page: number) {
  if (!editingStrategy.value || !isMarketScanStrategy(editingStrategy.value)) return
  if (page < 1 || page > sequenceScanTotalPages.value) return
  await loadSequenceScanBacktest(editingStrategy.value, page, false)
}

async function removeStrategy() {
  if (!editingStrategy.value) return
  error.value = ''
  saveMessage.value = ''
  try {
    const deletingId = editingStrategy.value.id
    await deleteQuantStrategy(deletingId)
    const nextId = strategies.value.find((item) => item.id !== deletingId)?.id ?? null
    await loadStrategies(nextId)
    curveRequested.value = false
    saveMessage.value = '策略已删除'
  } catch (deleteError) {
    error.value = deleteError instanceof Error ? deleteError.message : '策略删除失败'
  }
}

function loadStrategyToAnalysis() {
  if (!editingStrategy.value) return
  void router.push({
    path: analysisPathForStrategy(editingStrategy.value),
    query: { strategyId: String(editingStrategy.value.id) },
  })
}

function resetSendDialog() {
  if (recipientSearchTimer !== null) {
    window.clearTimeout(recipientSearchTimer)
    recipientSearchTimer = null
  }
  sendDialogOpen.value = false
  recipientKeyword.value = ''
  recipientOptions.value = []
  selectedRecipient.value = null
  recipientLoading.value = false
  sendLoading.value = false
  showRecipientSuggestions.value = false
}

function openSendDialog() {
  if (!editingStrategy.value) return
  resetSendDialog()
  sendDialogOpen.value = true
}

async function loadRecipients(keyword: string) {
  if (!isRoot.value) return
  const trimmedKeyword = keyword.trim()
  if (!trimmedKeyword) {
    recipientOptions.value = []
    recipientLoading.value = false
    showRecipientSuggestions.value = false
    return
  }
  recipientLoading.value = true
  try {
    recipientOptions.value = await authStore.searchUsers(trimmedKeyword)
    showRecipientSuggestions.value = recipientOptions.value.length > 0
  } catch (searchError) {
    error.value = searchError instanceof Error ? searchError.message : '用户搜索失败'
    recipientOptions.value = []
    showRecipientSuggestions.value = false
  } finally {
    recipientLoading.value = false
  }
}

function scheduleRecipientSearch(keyword: string) {
  if (recipientSearchTimer !== null) {
    window.clearTimeout(recipientSearchTimer)
  }
  recipientSearchTimer = window.setTimeout(() => {
    recipientSearchTimer = null
    void loadRecipients(keyword)
  }, 280)
}

function handleRecipientInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  recipientKeyword.value = value
  selectedRecipient.value = null
  showRecipientSuggestions.value = value.trim().length > 0
  if (!value.trim()) {
    if (recipientSearchTimer !== null) {
      window.clearTimeout(recipientSearchTimer)
      recipientSearchTimer = null
    }
    recipientOptions.value = []
    recipientLoading.value = false
    return
  }
  scheduleRecipientSearch(value)
}

async function handleRecipientSearch() {
  selectedRecipient.value = null
  showRecipientSuggestions.value = recipientKeyword.value.trim().length > 0
  await loadRecipients(recipientKeyword.value)
}

function handleRecipientBlur() {
  window.setTimeout(() => {
    showRecipientSuggestions.value = false
  }, 120)
}

function pickRecipientOption(option: UserSearchResult) {
  selectedRecipient.value = option
  recipientKeyword.value = formatRecipientDisplay(option)
  recipientOptions.value = []
  recipientLoading.value = false
  showRecipientSuggestions.value = false
}

async function confirmSendStrategy() {
  if (!editingStrategy.value || !selectedRecipient.value) return
  sendLoading.value = true
  error.value = ''
  saveMessage.value = ''
  try {
    await sendQuantStrategy(editingStrategy.value.id, selectedRecipient.value.username)
    saveMessage.value = `策略已发送给 ${selectedRecipient.value.nickname || selectedRecipient.value.username}`
    resetSendDialog()
  } catch (sendError) {
    error.value = sendError instanceof Error ? sendError.message : '策略发送失败'
  } finally {
    sendLoading.value = false
  }
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `¥${value.toFixed(2)}`
}

function formatQuantity(value: number | null | undefined, targetType?: QuantScanEvent['target_type']) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `${value}${targetType === 'etf' ? '份' : '股'}`
}

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return value.toFixed(2)
}

function formatBoardLabel(event: QuantScanEvent) {
  if (event.target_type === 'etf') return 'ETF'
  return event.board || '-'
}

function formatLotRuleLabel(event: QuantScanEvent) {
  if (event.target_type === 'etf') return '最少 100 份，按 100 份递增'
  const board = String(event.board || '')
  if (board.includes('科创板')) return '最少 200 股，200 股以上按 1 股递增'
  if (board.includes('北交所') || board.includes('北证')) return '最少 100 股，100 股以上按 1 股递增'
  if (board.includes('主板')) return '最少 100 股，按 100 股递增'
  if (board.includes('创业板')) return '最少 100 股，按 100 股递增'
  return event.lot_rule || '-'
}

function formatDisabledReason(event: QuantScanEvent) {
  if (event.tradable) return '-'
  if (!event.buy_date) return '买入执行日超出行情范围'
  if (!event.sell_date) return '卖出执行日超出行情范围'
  if (event.target_type === 'stock' && !event.board) return '无法根据 board 判断最小交易单位'
  if ((event.buy_price ?? 0) <= 0 || (event.sell_price ?? 0) <= 0) return '买卖执行价格无效'
  if (!event.planned_quantity || !event.planned_buy_amount) return '无法生成合法下单数量'
  return event.disabled_reason || '不可回测'
}

function formatSkipReason(reason: string | null | undefined) {
  if (!reason) return '-'
  if (reason === 'insufficient_cash') return '资金不足，未开仓'
  if (reason === 'invalid_trade_plan') return '交易计划无效'
  return reason
}

function scanEventStatus(event: QuantScanEvent) {
  if (!event.tradable) return { label: '不可回测', tone: 'muted', detail: formatDisabledReason(event) }
  if (!event.selected) return { label: '未选中', tone: 'muted', detail: '本次回测未纳入该事件' }
  if (event.executed) {
    return {
      label: '已执行',
      tone: 'success',
      detail: `单笔收益 ${event.return_pct?.toFixed(2) ?? '0.00'}% / 盈亏 ${formatMoney(event.pnl_amount)}`,
    }
  }
  if (event.skip_reason) return { label: '已跳过', tone: 'warning', detail: formatSkipReason(event.skip_reason) }
  return { label: '待执行', tone: 'info', detail: '等待本次回测撮合' }
}

const curvePoints = computed(() => {
  if (sequenceScanBacktest.value) return sequenceScanBacktest.value.points
  return equityCurve.value?.points ?? []
})

const scanEvents = computed<QuantScanEvent[]>(() => sequenceScanBacktest.value?.matched_events ?? [])
const sequenceScanTotalPages = computed(() => {
  const total = sequenceScanBacktest.value?.total_event_count ?? 0
  const size = sequenceScanBacktest.value?.page_size ?? sequenceScanPageSize.value
  if (!total || !size) return 1
  return Math.max(1, Math.ceil(total / size))
})

onMounted(async () => {
  await authStore.ensureInitialized()
  await loadStrategies()
})

onUnmounted(() => {
  if (recipientSearchTimer !== null) {
    window.clearTimeout(recipientSearchTimer)
    recipientSearchTimer = null
  }
})
</script>

<template>
  <p v-if="error" class="banner-error">{{ error }}</p>

  <div class="progress-grid quant-strategy-grid">
    <section class="card progress-card">
      <div class="progress-section-head">
        <div class="progress-section-copy">
          <h3>已保存策略</h3>
          <p class="muted">这里会按当前账号加载自己的策略，扫描模式会在策略回测页里重新执行全市场扫描。</p>
        </div>
      </div>

      <p v-if="loading" class="muted">策略列表加载中...</p>
      <div v-else-if="strategies.length" class="timeline quant-strategy-list">
        <button
          v-for="item in strategies"
          :key="item.id"
          type="button"
          class="sidebar-link quant-strategy-item"
          :class="{ active: selectedStrategyId === item.id }"
          @click="selectStrategy(item.id)"
        >
          <strong>{{ item.name }}</strong>
          <span>{{ strategyEngineLabel(item) }} / {{ strategyTypeLabel(item.strategy_type) }}</span>
          <span>{{ item.target_name }}</span>
        </button>
      </div>
      <p v-else class="muted">当前还没有已保存策略，请先去指数、股票或条件策略页面保存一条策略。</p>
    </section>

    <section class="card progress-card progress-card-wide">
      <template v-if="editingStrategy">
        <div class="progress-section-head">
          <div class="progress-section-copy">
            <h3>{{ editingStrategy.name }}</h3>
            <p class="muted">{{ strategyEngineLabel(editingStrategy) }} / {{ strategyTypeLabel(editingStrategy.strategy_type) }} / {{ editingStrategy.target_name }}</p>
          </div>
        </div>

        <div class="quant-strategy-form">
          <label class="quant-field">
            <span class="quant-field-label">策略名称</span>
            <input v-model="editingStrategy.name" class="input" />
          </label>
          <label class="quant-field quant-field-full">
            <span class="quant-field-label">策略备注</span>
            <textarea v-model="editingStrategy.notes" class="input progress-textarea progress-textarea-compact" />
          </label>
          <label class="quant-field">
            <span class="quant-field-label">买入信号颜色</span>
            <select v-model="editingStrategy.signal_buy_color" class="input">
              <option v-for="option in signalColorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="quant-field">
            <span class="quant-field-label">卖出信号颜色</span>
            <select v-model="editingStrategy.signal_sell_color" class="input">
              <option v-for="option in signalColorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="quant-field">
            <span class="quant-field-label">紫色冲突处理</span>
            <select v-model="editingStrategy.purple_conflict_mode" class="input">
              <option v-for="option in conflictModeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <template v-if="isMarketScanStrategy(editingStrategy)">
            <div class="quant-scan-backtest-note quant-field-full">
              <strong>扫描模式组合回测参数</strong>
              <p class="muted">以下参数只影响扫描模式策略的组合回测，不影响扫描命中事件本身。</p>
            </div>
            <label class="quant-field">
              <span class="quant-field-label">扫描开始日期</span>
              <input v-model="editingStrategy.scan_start_date" class="input" type="date" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">扫描结束日期</span>
              <input v-model="editingStrategy.scan_end_date" class="input" type="date" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">初始资金</span>
              <input v-model.number="editingStrategy.scan_trade_config.initial_capital" class="input" type="number" min="1000" step="1000" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">单事件目标买入金额</span>
              <input v-model.number="editingStrategy.scan_trade_config.buy_amount_per_event" class="input" type="number" min="1000" step="1000" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">买入偏移交易日</span>
              <input v-model.number="editingStrategy.scan_trade_config.buy_offset_trading_days" class="input" type="number" min="1" step="1" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">卖出偏移交易日</span>
              <input v-model.number="editingStrategy.scan_trade_config.sell_offset_trading_days" class="input" type="number" min="1" step="1" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">买入价格</span>
              <select v-model="editingStrategy.scan_trade_config.buy_price_basis" class="input">
                <option v-for="option in priceBasisOptions" :key="`buy-${option.value}`" :value="option.value">{{ option.label }}</option>
              </select>
            </label>
            <label class="quant-field">
              <span class="quant-field-label">卖出价格</span>
              <select v-model="editingStrategy.scan_trade_config.sell_price_basis" class="input">
                <option v-for="option in priceBasisOptions" :key="`sell-${option.value}`" :value="option.value">{{ option.label }}</option>
              </select>
            </label>
          </template>
          <template v-else>
            <label class="quant-field">
              <span class="quant-field-label">策略开始日期</span>
              <input v-model="editingStrategy.start_date" class="input" type="date" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">每次买入仓位</span>
              <input v-model.number="editingStrategy.buy_position_pct" class="input" type="number" min="0" step="0.01" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">每次卖出仓位</span>
              <input v-model.number="editingStrategy.sell_position_pct" class="input" type="number" min="0" step="0.01" />
            </label>
            <label class="quant-field">
              <span class="quant-field-label">成交价格模式</span>
              <select v-model="editingStrategy.execution_price_mode" class="input">
                <option v-for="option in executionModeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </label>
          </template>
        </div>

        <div class="progress-hero-actions">
          <button class="btn" @click="loadStrategyToAnalysis">{{ analysisButtonLabel(editingStrategy) }}</button>
          <button v-if="isRoot" class="btn" @click="openSendDialog">发送给用户</button>
          <button class="btn" @click="saveStrategy">保存策略</button>
          <button class="btn primary" :disabled="curveLoading" @click="confirmAndLoadCurve">确定并加载收益曲线</button>
          <button class="btn" @click="removeStrategy">删除策略</button>
        </div>

        <p v-if="saveMessage" class="muted">{{ saveMessage }}</p>

        <div v-if="curveRequested && (equityCurve || sequenceScanBacktest)" class="summary quant-strategy-summary">
          <div>
            <div class="label">累计收益</div>
            <div class="value">{{ (sequenceScanBacktest?.cumulative_return_pct ?? equityCurve?.cumulative_return_pct ?? 0).toFixed(2) }}%</div>
          </div>
          <div>
            <div class="label">年化收益</div>
            <div class="value">{{ (sequenceScanBacktest?.annualized_return_pct ?? equityCurve?.annualized_return_pct ?? 0).toFixed(2) }}%</div>
          </div>
          <div>
            <div class="label">最大回撤</div>
            <div class="value">{{ (sequenceScanBacktest?.max_drawdown_pct ?? equityCurve?.max_drawdown_pct ?? 0).toFixed(2) }}%</div>
          </div>
          <div>
            <div class="label">回测交易日数</div>
            <div class="value">{{ curvePoints.length }}</div>
          </div>

          <template v-if="isMarketScanStrategy(editingStrategy) && sequenceScanBacktest">
            <div>
              <div class="label">命中事件</div>
              <div class="value">{{ sequenceScanBacktest.summary.matched_event_count }}</div>
            </div>
            <div>
              <div class="label">已执行事件</div>
              <div class="value">{{ sequenceScanBacktest.summary.executed_event_count }}</div>
            </div>
            <div>
              <div class="label">资金不足跳过</div>
              <div class="value">{{ sequenceScanBacktest.summary.skipped_event_count }}</div>
            </div>
          </template>

          <template v-else-if="equityCurve">
            <div>
              <div class="label">当前执行价模式</div>
              <div class="value small">{{ editingStrategy.execution_price_mode }}</div>
            </div>
            <div class="quant-strategy-optimization-card">
              <div class="label">最小回撤组合</div>
              <div class="value">{{ equityCurve.position_optimization.min_drawdown.value_pct.toFixed(2) }}%</div>
              <div v-if="equityCurve.position_optimization.min_drawdown.combinations.length" class="quant-strategy-optimization-list">
                <div
                  v-for="(pair, index) in equityCurve.position_optimization.min_drawdown.combinations"
                  :key="`drawdown-${index}-${pair.buy_position_pct}-${pair.sell_position_pct}`"
                  class="quant-strategy-optimization-item"
                >
                  {{ formatPositionPairWithReturn(pair) }}
                </div>
              </div>
              <div v-else class="muted quant-strategy-optimization-empty">暂无可计算结果</div>
            </div>
            <div class="quant-strategy-optimization-card">
              <div class="label">最大总收益组合</div>
              <div class="value">{{ equityCurve.position_optimization.max_total_return.value_pct.toFixed(2) }}%</div>
              <div v-if="equityCurve.position_optimization.max_total_return.combinations.length" class="quant-strategy-optimization-list">
                <div
                  v-for="(pair, index) in equityCurve.position_optimization.max_total_return.combinations"
                  :key="`return-${index}-${pair.buy_position_pct}-${pair.sell_position_pct}`"
                  class="quant-strategy-optimization-item"
                >
                  {{ formatPositionPair(pair) }}
                </div>
              </div>
              <div v-else class="muted quant-strategy-optimization-empty">暂无可计算结果</div>
            </div>
          </template>
        </div>

        <section v-if="isMarketScanStrategy(editingStrategy) && sequenceScanBacktest" class="card progress-card quant-scan-backtest-card">
          <div class="progress-section-head">
            <div class="progress-section-copy">
              <h3>扫描事件回测</h3>
              <p class="muted">默认全选全部可回测事件。取消勾选后，会重新按当前事件集合生成组合收益曲线。</p>
            </div>
          </div>

          <div class="quant-scan-event-table-wrap">
            <table class="quant-scan-event-table">
              <thead>
                <tr>
                  <th>选择</th>
                  <th>信号日</th>
                  <th>标的</th>
                  <th>板块 / 交易单位</th>
                  <th>买入计划</th>
                  <th>卖出计划</th>
                  <th>计划下单</th>
                  <th>实际成交</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="event in scanEvents"
                  :key="`table-${event.event_id}`"
                  :class="{ disabled: !event.tradable, inactive: !event.selected }"
                >
                  <td>
                    <input
                      type="checkbox"
                      :checked="Boolean(event.selected)"
                      :disabled="curveLoading || !event.tradable"
                      @change="toggleSequenceScanEvent(event.event_id, ($event.target as HTMLInputElement).checked)"
                    />
                  </td>
                  <td>
                    <div class="quant-scan-cell-main">{{ event.signal_date }}</div>
                    <div class="quant-scan-cell-sub">命中组 {{ event.hit_buy_groups.join('、') || '-' }}</div>
                  </td>
                  <td>
                    <div class="quant-scan-cell-main">{{ event.target_name }}</div>
                    <div class="quant-scan-cell-sub">{{ event.target_code }}</div>
                  </td>
                  <td>
                    <div class="quant-scan-cell-main">{{ formatBoardLabel(event) }}</div>
                    <div class="quant-scan-cell-sub">{{ formatLotRuleLabel(event) }}</div>
                  </td>
                  <td>
                    <div class="quant-scan-cell-main">{{ event.buy_date ?? '-' }}</div>
                    <div class="quant-scan-cell-sub">{{ formatPrice(event.buy_price) }} / {{ editingStrategy.scan_trade_config.buy_price_basis === 'open' ? '开盘价' : '收盘价' }}</div>
                  </td>
                  <td>
                    <div class="quant-scan-cell-main">{{ event.sell_date ?? '-' }}</div>
                    <div class="quant-scan-cell-sub">{{ formatPrice(event.sell_price) }} / {{ editingStrategy.scan_trade_config.sell_price_basis === 'open' ? '开盘价' : '收盘价' }}</div>
                  </td>
                  <td>
                    <div class="quant-scan-cell-main">{{ formatQuantity(event.planned_quantity, event.target_type) }}</div>
                    <div class="quant-scan-cell-sub">{{ formatMoney(event.planned_buy_amount) }}</div>
                  </td>
                  <td>
                    <div class="quant-scan-cell-main">{{ formatQuantity(event.actual_quantity, event.target_type) }}</div>
                    <div class="quant-scan-cell-sub">买 {{ formatMoney(event.actual_buy_amount) }} / 卖 {{ formatMoney(event.actual_sell_amount) }}</div>
                  </td>
                  <td>
                    <div class="quant-scan-status" :class="`tone-${scanEventStatus(event).tone}`">
                      {{ scanEventStatus(event).label }}
                    </div>
                    <div class="quant-scan-cell-sub">
                      {{ event.tradable ? scanEventStatus(event).detail : formatDisabledReason(event) }}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="sequenceScanBacktest.total_event_count > sequenceScanBacktest.page_size" class="progress-hero-actions">
            <button class="btn" :disabled="curveLoading || sequenceScanBacktest.page <= 1" @click="changeSequenceScanPage(sequenceScanBacktest.page - 1)">上一页</button>
            <span class="muted">第 {{ sequenceScanBacktest.page }} / {{ sequenceScanTotalPages }} 页，共 {{ sequenceScanBacktest.total_event_count }} 条事件</span>
            <button class="btn" :disabled="curveLoading || sequenceScanBacktest.page >= sequenceScanTotalPages" @click="changeSequenceScanPage(sequenceScanBacktest.page + 1)">下一页</button>
          </div>

          <div v-if="false" class="quant-scan-events">
            <label
              v-for="event in scanEvents"
              :key="event.event_id"
              class="quant-scan-event-item"
              :class="{ disabled: !event.tradable }"
            >
              <input
                type="checkbox"
                :checked="Boolean(event.selected)"
                :disabled="curveLoading || !event.tradable"
                @change="toggleSequenceScanEvent(event.event_id, ($event.target as HTMLInputElement).checked)"
              />
              <div class="quant-scan-event-main">
                <strong>{{ event.target_name }}（{{ event.target_code }}）</strong>
                <span>{{ event.signal_date }} 命中</span>
              </div>
              <div class="quant-scan-event-meta">
                <span>买：{{ event.buy_date ?? '-' }}</span>
                <span>卖：{{ event.sell_date ?? '-' }}</span>
                <span v-if="event.executed">已执行 / 收益 {{ (event.return_pct ?? 0).toFixed(2) }}%</span>
                <span v-else-if="event.skip_reason">跳过：{{ event.skip_reason }}</span>
                <span v-else>{{ event.tradable ? '待执行' : event.disabled_reason || '不可回测' }}</span>
              </div>
            </label>
          </div>
        </section>

        <p v-if="!curveRequested && !curveLoading" class="muted">
          当前只加载了策略配置。调整好选项后，点击“确定并加载收益曲线”再开始回测。
        </p>
        <StrategyEquityCurveChart v-else :points="curvePoints" :loading="curveLoading" />
      </template>

      <template v-else>
        <div class="quant-stock-empty">
          <h3>策略回测</h3>
          <p class="muted">从左侧选择一条已保存策略后，这里会显示交易规则和收益曲线。</p>
        </div>
      </template>
    </section>
  </div>

  <div v-if="sendDialogOpen" class="modal-overlay" @click.self="resetSendDialog">
    <section class="card auth-dialog account-send-dialog">
      <div class="auth-dialog-head">
        <h3>发送给用户</h3>
        <button type="button" class="btn btn-secondary btn-compact" @click="resetSendDialog">关闭</button>
      </div>

      <p class="muted">会复制一份独立策略给目标正式用户，之后双方修改互不影响。</p>

      <div class="search-wrap">
        <div class="login-code-row">
          <label class="quant-field">
            <span class="quant-field-label">搜索用户</span>
            <input
              :value="recipientKeyword"
              class="input"
              placeholder="按手机号或账号搜索正式用户"
              @focus="showRecipientSuggestions = Boolean(recipientKeyword.trim()) && recipientOptions.length > 0"
              @input="handleRecipientInput"
              @blur="handleRecipientBlur"
            />
          </label>
          <button type="button" class="btn btn-secondary" :disabled="recipientLoading" @click="handleRecipientSearch">
            {{ recipientLoading ? '搜索中...' : '搜索' }}
          </button>
        </div>

        <ul v-if="showRecipientSuggestions && recipientOptions.length" class="suggest-list account-send-suggest-list">
          <li v-for="option in recipientOptions" :key="option.id" @mousedown.prevent="pickRecipientOption(option)">
            <span>{{ option.nickname || option.username }}</span>
            <span>{{ option.phone || option.username }}</span>
          </li>
        </ul>
      </div>

      <p class="muted">
        当前选择：
        <strong>{{ selectedRecipient ? `${selectedRecipient.nickname || selectedRecipient.username} / ${selectedRecipient.phone || selectedRecipient.username}` : '未选择用户' }}</strong>
      </p>

      <div class="quant-modal-actions">
        <button class="btn btn-secondary" @click="resetSendDialog">取消</button>
        <button class="btn btn-primary" :disabled="sendLoading || !selectedRecipient" @click="confirmSendStrategy">
          {{ sendLoading ? '发送中...' : '确认发送' }}
        </button>
      </div>
    </section>
  </div>
</template>
