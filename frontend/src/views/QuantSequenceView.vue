<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  createQuantStrategy,
  fetchEtfKline,
  fetchIndexBreadth,
  fetchIndexKline,
  fetchKline,
  fetchQuantSequenceScanEvents,
  fetchQuantSequenceScanTargetHits,
  fetchQuantStrategy,
  fetchQuantTargets,
  previewQuantSequenceScan,
  updateQuantStrategy,
} from '../api/stocks'
import KlineChart from '../components/KlineChart.vue'
import QuantSequenceRuleBuilder from '../components/QuantSequenceRuleBuilder.vue'
import type {
  QuantHighlightBand,
  QuantIndicatorParams,
  QuantScanEvent,
  QuantScanTradeConfig,
  QuantSequenceGroupDraft,
  QuantSequenceMode,
  QuantStrategyConfig,
  QuantStrategyPayload,
  QuantStrategyType,
  QuantTargetOption,
} from '../types/quant'
import type { IndexBreadthPoint, KlineCandle } from '../types/stock'
import {
  buildSequenceHighlightBands,
  buildSequenceSnapshots,
  createEmptySequenceGroupDraft,
  deserializeSequenceGroups,
  normalizeSequenceGroups,
} from '../utils/quantSequence'

const DEFAULT_INDICATOR_PARAMS: QuantIndicatorParams = {
  ma: { periods: [5, 10, 20, 60] },
  macd: { fast: 12, slow: 26, signal: 9 },
  kdj: { period: 9, kSmoothing: 3, dSmoothing: 3 },
  wr: { period: 14 },
  rsi: { period: 14 },
  boll: { period: 20, multiplier: 2 },
}

const DEFAULT_SCAN_TRADE_CONFIG: QuantScanTradeConfig = {
  initial_capital: 1_000_000,
  buy_amount_per_event: 10_000,
  buy_offset_trading_days: 1,
  sell_offset_trading_days: 2,
  buy_price_basis: 'open',
  sell_price_basis: 'open',
}

const route = useRoute()

const sequenceMode = ref<QuantSequenceMode>('single_target')
const targetType = ref<QuantStrategyType>('index')
const targetKeyword = ref('')
const targetOptions = ref<QuantTargetOption[]>([])
const showSuggestions = ref(false)
const suggestionLoading = ref(false)
const selectedCode = ref('')
const selectedName = ref('')
const candles = ref<KlineCandle[]>([])
const breadthPoints = ref<IndexBreadthPoint[]>([])
const loading = ref(false)
const chartRequested = ref(false)
const error = ref('')
const saveName = ref('')
const saveLoading = ref(false)
const saveMessage = ref('')
const saveError = ref('')
const loadedStrategyId = ref<number | null>(null)
const loadedStrategyBase = ref<QuantStrategyConfig | null>(null)
const strategyLoadMessage = ref('')
const buyRuleDrafts = ref<QuantSequenceGroupDraft[]>([])
const sellRuleDrafts = ref<QuantSequenceGroupDraft[]>([])
const strategyStartDate = ref('')
const scanStartDate = ref('')
const scanEndDate = ref('')
const scanTradeConfig = ref<QuantScanTradeConfig>({ ...DEFAULT_SCAN_TRADE_CONFIG })
const scanPreviewEvents = ref<QuantScanEvent[]>([])
const scanLoading = ref(false)
const scanStatusMessage = ref('')
const scanResultId = ref('')
const scanPage = ref(1)
const scanPageSize = ref(100)
const scanTotalEventCount = ref(0)
const scanMatchedEventCount = ref(0)
const scanTradableEventCount = ref(0)
const selectedScanEventId = ref<string | null>(null)
const scanSymbolCode = ref('')
const scanSymbolName = ref('')
const scanCandles = ref<KlineCandle[]>([])
const scanHitDates = ref<string[]>([])
const suppressTargetReset = ref(false)
const scanPreviewController = ref<AbortController | null>(null)
const scanPageController = ref<AbortController | null>(null)
const scanTargetHitsController = ref<AbortController | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null
let latestSearchRequestId = 0

const modeOptions = [
  { value: 'single_target', label: '单标的' },
  { value: 'market_scan', label: '全市场扫描' },
] as const

const singleTargetTypeOptions = [
  { value: 'index', label: '指数' },
  { value: 'stock', label: '个股' },
  { value: 'etf', label: 'ETF' },
] as const

const scanTargetTypeOptions = [
  { value: 'stock', label: '全市场个股' },
  { value: 'etf', label: '全市场 ETF' },
] as const

const cloneJson = <T,>(value: T) => JSON.parse(JSON.stringify(value)) as T
const getErrorMessage = (cause: unknown) => (cause instanceof Error ? cause.message : '加载失败')
const cloneIndicatorParams = (params?: QuantIndicatorParams | null) =>
  params ? cloneJson(params) : cloneJson(DEFAULT_INDICATOR_PARAMS)
const cloneScanTradeConfig = (config?: Partial<QuantScanTradeConfig> | null): QuantScanTradeConfig => ({
  ...DEFAULT_SCAN_TRADE_CONFIG,
  ...(config ?? {}),
})

const getStrategyIdFromRoute = () => {
  const raw = Array.isArray(route.query.strategyId) ? route.query.strategyId[0] : route.query.strategyId
  const parsed = raw ? Number(raw) : Number.NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

async function ensureBreadthLoaded() {
  if (!breadthPoints.value.length) breadthPoints.value = await fetchIndexBreadth()
}

async function loadTargetOptions(keyword: string) {
  const requestId = ++latestSearchRequestId
  suggestionLoading.value = true
  try {
    const items = await fetchQuantTargets(targetType.value, keyword, 30)
    if (requestId === latestSearchRequestId) targetOptions.value = items
  } catch (cause) {
    if (requestId === latestSearchRequestId) {
      error.value = getErrorMessage(cause)
      targetOptions.value = []
    }
  } finally {
    if (requestId === latestSearchRequestId) suggestionLoading.value = false
  }
}

function scheduleTargetSearch(keyword: string) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void loadTargetOptions(keyword.trim()), 280)
}

function handleSearchFocus() {
  if (sequenceMode.value !== 'single_target') return
  showSuggestions.value = true
  scheduleTargetSearch(targetKeyword.value)
}

function handleSearchInput() {
  if (sequenceMode.value !== 'single_target') return
  showSuggestions.value = true
  scheduleTargetSearch(targetKeyword.value)
}

function pickTarget(option: QuantTargetOption) {
  selectedCode.value = option.code
  selectedName.value = option.name
  targetKeyword.value = `${option.code} ${option.name}`
  showSuggestions.value = false
  candles.value = []
  chartRequested.value = false
}

async function loadSingleTargetKline() {
  if (!selectedCode.value) {
    error.value = '请先选择目标'
    return false
  }
  loading.value = true
  error.value = ''
  chartRequested.value = true
  try {
    await ensureBreadthLoaded()
    candles.value =
      targetType.value === 'index'
        ? await fetchIndexKline(selectedCode.value)
        : targetType.value === 'stock'
          ? await fetchKline(selectedCode.value)
          : await fetchEtfKline(selectedCode.value)
    if (!candles.value.length) {
      error.value = '当前目标暂无可用于条件策略的行情数据'
      return false
    }
    return true
  } catch (cause) {
    candles.value = []
    error.value = getErrorMessage(cause)
    return false
  } finally {
    loading.value = false
  }
}

function resetScanPreviewState() {
  scanResultId.value = ''
  scanPage.value = 1
  scanTotalEventCount.value = 0
  scanMatchedEventCount.value = 0
  scanTradableEventCount.value = 0
  scanPreviewEvents.value = []
  selectedScanEventId.value = null
  scanHitDates.value = []
  scanCandles.value = []
  scanSymbolCode.value = ''
  scanSymbolName.value = ''
}

function applyScanEventPage(payload: {
  scan_result_id: string
  matched_events: QuantScanEvent[]
  matched_event_count: number
  tradable_event_count: number
  total_event_count: number
  page: number
  page_size: number
}) {
  scanResultId.value = payload.scan_result_id
  scanPreviewEvents.value = payload.matched_events
  scanMatchedEventCount.value = payload.matched_event_count
  scanTradableEventCount.value = payload.tradable_event_count
  scanTotalEventCount.value = payload.total_event_count
  scanPage.value = payload.page
  scanPageSize.value = payload.page_size
}

async function loadScanEventChart(event: QuantScanEvent | null) {
  if (!event) {
    scanCandles.value = []
    scanSymbolCode.value = ''
    scanSymbolName.value = ''
    return
  }
  try {
    scanCandles.value =
      event.target_type === 'stock' ? await fetchKline(event.target_code) : await fetchEtfKline(event.target_code)
    scanSymbolCode.value = event.target_code
    scanSymbolName.value = event.target_name
  } catch (cause) {
    scanCandles.value = []
    error.value = getErrorMessage(cause)
  }
}

async function loadScanTargetHits(event: QuantScanEvent | null) {
  if (!event || !scanResultId.value) {
    scanHitDates.value = []
    return
  }
  scanTargetHitsController.value?.abort()
  const controller = new AbortController()
  scanTargetHitsController.value = controller
  try {
    const result = await fetchQuantSequenceScanTargetHits(scanResultId.value, event.target_code, { signal: controller.signal })
    scanHitDates.value = result.hit_dates
  } catch (cause) {
    if ((cause as { name?: string }).name !== 'CanceledError') {
      error.value = getErrorMessage(cause)
      scanHitDates.value = []
    }
  } finally {
    if (scanTargetHitsController.value === controller) scanTargetHitsController.value = null
  }
}

async function selectScanEvent(event: QuantScanEvent) {
  selectedScanEventId.value = event.event_id
  await loadScanTargetHits(event)
  await loadScanEventChart(event)
}

async function loadScanEventsPage(page: number) {
  if (!scanResultId.value) return
  scanPageController.value?.abort()
  const controller = new AbortController()
  scanPageController.value = controller
  scanLoading.value = true
  scanStatusMessage.value = `正在加载第 ${page} 页事件...`
  try {
    const result = await fetchQuantSequenceScanEvents(scanResultId.value, page, scanPageSize.value, { signal: controller.signal })
    applyScanEventPage(result)
    const next =
      result.matched_events.find((item) => item.event_id === selectedScanEventId.value) ?? result.matched_events[0] ?? null
    selectedScanEventId.value = next?.event_id ?? null
    await loadScanTargetHits(next)
    await loadScanEventChart(next)
  } catch (cause) {
    if ((cause as { name?: string }).name !== 'CanceledError') error.value = getErrorMessage(cause)
  } finally {
    if (scanPageController.value === controller) {
      scanPageController.value = null
      scanLoading.value = false
      scanStatusMessage.value = ''
    }
  }
}

const buyValidation = computed(() => normalizeSequenceGroups(buyRuleDrafts.value))
const sellValidation = computed(() => normalizeSequenceGroups(sellRuleDrafts.value))
const singleTargetSnapshots = computed(() => buildSequenceSnapshots(candles.value, breadthPoints.value))
const singleTargetHighlightBands = computed<QuantHighlightBand[]>(() =>
  buildSequenceHighlightBands(singleTargetSnapshots.value, buyValidation.value.groups, sellValidation.value.groups),
)
const selectedScanEvent = computed(() => scanPreviewEvents.value.find((item) => item.event_id === selectedScanEventId.value) ?? null)
const scanHighlightBands = computed<QuantHighlightBand[]>(() =>
  scanHitDates.value.map((tradeDate) => ({
    tradeDate,
    color: 'red',
    variant: selectedScanEvent.value?.signal_date === tradeDate ? 'striped' : 'solid',
  })),
)
const activeCandles = computed(() => (sequenceMode.value === 'market_scan' ? scanCandles.value : candles.value))
const activeHighlightBands = computed(() => (sequenceMode.value === 'market_scan' ? scanHighlightBands.value : singleTargetHighlightBands.value))
const activeSymbolCode = computed(() => (sequenceMode.value === 'market_scan' ? scanSymbolCode.value : selectedCode.value))
const activeSymbolName = computed(() =>
  sequenceMode.value === 'market_scan' ? scanSymbolName.value || '全市场扫描预览' : selectedName.value || '条件策略',
)
const highlightSummary = computed(() =>
  sequenceMode.value === 'market_scan'
    ? {
        matched: scanMatchedEventCount.value,
        tradable: scanTradableEventCount.value,
        targets: new Set(scanPreviewEvents.value.map((item) => item.target_code)).size,
      }
    : { matched: singleTargetHighlightBands.value.length, tradable: singleTargetHighlightBands.value.length, targets: 1 },
)
const scanTotalPages = computed(() =>
  !scanTotalEventCount.value || scanPageSize.value <= 0 ? 1 : Math.max(1, Math.ceil(scanTotalEventCount.value / scanPageSize.value)),
)
const sequencePageDescription = computed(() =>
  sequenceMode.value === 'market_scan'
    ? '定义全市场命中条件，执行扫描后查看事件；组合回测请到策略回测页。'
    : '选一个目标，配置买卖规则并预览高亮。',
)
const scanRangeWarning = computed(() => {
  if (sequenceMode.value !== 'market_scan' || !scanStartDate.value || !scanEndDate.value) return ''
  const start = new Date(`${scanStartDate.value}T00:00:00`)
  const end = new Date(`${scanEndDate.value}T00:00:00`)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return ''
  return Math.floor((end.getTime() - start.getTime()) / 86400000) > 365
    ? '当前扫描跨度超过 12 个月，可能会明显更慢，但系统仍会继续执行。'
    : ''
})
const canSave = computed(() => {
  const base =
    !loading.value &&
    !saveLoading.value &&
    Boolean(saveName.value.trim()) &&
    buyValidation.value.groups.length > 0 &&
    !Object.keys(buyValidation.value.groupErrors).length &&
    !Object.keys(buyValidation.value.conditionErrors).length
  if (!base) return false
  return sequenceMode.value === 'market_scan'
    ? (targetType.value === 'stock' || targetType.value === 'etf') && Boolean(scanStartDate.value) && Boolean(scanEndDate.value)
    : Boolean(selectedCode.value) &&
        Boolean(selectedName.value) &&
        sellValidation.value.groups.length > 0 &&
        !Object.keys(sellValidation.value.groupErrors).length &&
        !Object.keys(sellValidation.value.conditionErrors).length
})

function addRuleGroup(side: 'buy' | 'sell') {
  const group = createEmptySequenceGroupDraft()
  if (side === 'buy') buyRuleDrafts.value = [...buyRuleDrafts.value, group]
  else sellRuleDrafts.value = [...sellRuleDrafts.value, group]
}

function deleteRuleGroup(side: 'buy' | 'sell', groupId: string) {
  if (side === 'buy') buyRuleDrafts.value = buyRuleDrafts.value.filter((group) => group.id !== groupId)
  else sellRuleDrafts.value = sellRuleDrafts.value.filter((group) => group.id !== groupId)
}

function addRuleCondition(side: 'buy' | 'sell', groupId: string) {
  const groups = side === 'buy' ? buyRuleDrafts.value : sellRuleDrafts.value
  const group = groups.find((item) => item.id === groupId)
  if (!group) return
  group.conditions.push({
    id: `${groupId}-${Date.now()}-${group.conditions.length}`,
    series_key: '',
    operator: 'lt',
    threshold: '',
    consecutive_days: '3',
  })
}

function deleteRuleCondition(side: 'buy' | 'sell', groupId: string, conditionId: string) {
  const groups = side === 'buy' ? buyRuleDrafts.value : sellRuleDrafts.value
  const group = groups.find((item) => item.id === groupId)
  if (!group) return
  group.conditions = group.conditions.filter((condition) => condition.id !== conditionId)
  if (!group.conditions.length) deleteRuleGroup(side, groupId)
}

function buildPayload(name: string): QuantStrategyPayload {
  const base = loadedStrategyBase.value
  const common = {
    name,
    notes: base?.notes ?? '',
    strategy_engine: 'sequence' as const,
    strategy_type: targetType.value,
    indicator_params: cloneIndicatorParams(base?.indicator_params),
    buy_sequence_groups: buyValidation.value.groups,
    blue_filter_groups: [],
    red_filter_groups: [],
    blue_filters: {},
    red_filters: {},
    blue_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
    red_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
    signal_buy_color: base?.signal_buy_color ?? 'blue',
    signal_sell_color: base?.signal_sell_color ?? 'red',
    purple_conflict_mode: base?.purple_conflict_mode ?? 'sell_first',
    buy_position_pct: base?.buy_position_pct ?? 1,
    sell_position_pct: base?.sell_position_pct ?? 1,
    execution_price_mode: base?.execution_price_mode ?? 'next_open',
    scan_trade_config: cloneScanTradeConfig(scanTradeConfig.value),
  }

  if (sequenceMode.value === 'market_scan') {
    return {
      ...common,
      sequence_mode: 'market_scan',
      target_code: targetType.value === 'stock' ? 'ALL_STOCK' : 'ALL_ETF',
      target_name: targetType.value === 'stock' ? '全市场股票' : '全市场 ETF',
      sell_sequence_groups: [],
      start_date: null,
      scan_start_date: scanStartDate.value || null,
      scan_end_date: scanEndDate.value || null,
    }
  }

  return {
    ...common,
    sequence_mode: 'single_target',
    target_code: selectedCode.value,
    target_name: selectedName.value,
    sell_sequence_groups: sellValidation.value.groups,
    start_date: strategyStartDate.value || null,
    scan_start_date: null,
    scan_end_date: null,
  }
}

async function saveStrategy(createNew: boolean) {
  saveError.value = ''
  saveMessage.value = ''
  if (!saveName.value.trim()) {
    saveError.value = '请先填写策略名称'
    return
  }
  if (sequenceMode.value === 'single_target' && (!selectedCode.value || !selectedName.value)) {
    saveError.value = '请先选择目标'
    return
  }
  if (!buyValidation.value.groups.length) {
    saveError.value = '请至少配置一组入场规则'
    return
  }
  if (sequenceMode.value === 'single_target' && !sellValidation.value.groups.length) {
    saveError.value = '单标的模式至少需要一组卖出规则'
    return
  }
  if (sequenceMode.value === 'market_scan' && (!scanStartDate.value || !scanEndDate.value)) {
    saveError.value = '请先选择全市场扫描的开始日期和结束日期'
    return
  }

  saveLoading.value = true
  try {
    const isCreate = createNew || !loadedStrategyId.value
    const payload = buildPayload(saveName.value.trim())
    const result = !createNew && loadedStrategyId.value
      ? await updateQuantStrategy(loadedStrategyId.value, payload)
      : await createQuantStrategy(payload)
    loadedStrategyId.value = result.id
    loadedStrategyBase.value = result
    saveName.value = result.name
    strategyStartDate.value = result.start_date ?? ''
    scanStartDate.value = result.scan_start_date ?? ''
    scanEndDate.value = result.scan_end_date ?? ''
    scanTradeConfig.value = cloneScanTradeConfig(result.scan_trade_config)
    saveMessage.value = `${isCreate ? '已保存策略' : '已更新策略'}：${result.name}`
  } catch (cause) {
    saveError.value = getErrorMessage(cause)
  } finally {
    saveLoading.value = false
  }
}

async function executeMarketScan() {
  saveError.value = ''
  saveMessage.value = ''
  error.value = ''
  if (sequenceMode.value !== 'market_scan') return
  if (!buyValidation.value.groups.length) {
    saveError.value = '请至少配置一组入场规则'
    return
  }
  if (!scanStartDate.value || !scanEndDate.value) {
    saveError.value = '请先选择扫描开始日期和结束日期'
    return
  }
  if (scanEndDate.value < scanStartDate.value) {
    saveError.value = '扫描结束日期不能早于开始日期'
    return
  }

  scanPreviewController.value?.abort()
  scanPageController.value?.abort()
  scanTargetHitsController.value?.abort()

  const controller = new AbortController()
  scanPreviewController.value = controller
  resetScanPreviewState()
  scanLoading.value = true
  scanStatusMessage.value = '正在扫描全市场...'
  try {
    const result = await previewQuantSequenceScan(
      {
        strategy_type: targetType.value,
        buy_sequence_groups: buyValidation.value.groups,
        scan_trade_config: scanTradeConfig.value,
        scan_start_date: scanStartDate.value,
        scan_end_date: scanEndDate.value,
      },
      { signal: controller.signal },
    )
    applyScanEventPage(result)
    const first = result.matched_events[0] ?? null
    selectedScanEventId.value = first?.event_id ?? null
    if (first) {
      scanStatusMessage.value = '扫描完成，正在加载命中详情...'
      await loadScanTargetHits(first)
      await loadScanEventChart(first)
    } else {
      scanHitDates.value = []
      await loadScanEventChart(null)
    }
  } catch (cause) {
    if ((cause as { name?: string }).name !== 'CanceledError') {
      resetScanPreviewState()
      await loadScanEventChart(null)
      error.value = getErrorMessage(cause)
    }
  } finally {
    if (scanPreviewController.value === controller) {
      scanPreviewController.value = null
      scanLoading.value = false
      scanStatusMessage.value = ''
    }
  }
}

function applyLoadedStrategy(strategy: QuantStrategyConfig) {
  suppressTargetReset.value = true
  loadedStrategyId.value = strategy.id
  loadedStrategyBase.value = strategy
  saveName.value = strategy.name
  strategyStartDate.value = strategy.start_date ?? ''
  scanStartDate.value = strategy.scan_start_date ?? ''
  scanEndDate.value = strategy.scan_end_date ?? ''
  scanTradeConfig.value = cloneScanTradeConfig(strategy.scan_trade_config)
  sequenceMode.value = strategy.sequence_mode ?? 'single_target'
  targetType.value = strategy.strategy_type
  buyRuleDrafts.value = deserializeSequenceGroups(strategy.buy_sequence_groups)
  sellRuleDrafts.value = deserializeSequenceGroups(strategy.sell_sequence_groups)
  if (sequenceMode.value === 'single_target') {
    selectedCode.value = strategy.target_code
    selectedName.value = strategy.target_name
    targetKeyword.value = `${strategy.target_code} ${strategy.target_name}`
  } else {
    selectedCode.value = ''
    selectedName.value = ''
    targetKeyword.value = ''
  }
  suppressTargetReset.value = false
}

async function hydrateStrategyFromRoute() {
  const strategyId = getStrategyIdFromRoute()
  if (!strategyId) return
  strategyLoadMessage.value = ''
  error.value = ''
  saveError.value = ''
  try {
    const strategy = await fetchQuantStrategy(strategyId)
    if (strategy.strategy_engine !== 'sequence') {
      error.value = '当前策略不是条件策略，无法加载到条件策略页面'
      return
    }
    applyLoadedStrategy(strategy)
    if (sequenceMode.value === 'market_scan') await executeMarketScan()
    else {
      const ok = await loadSingleTargetKline()
      if (!ok) return
    }
    strategyLoadMessage.value = `已加载条件策略：${strategy.name}`
  } catch (cause) {
    error.value = getErrorMessage(cause)
  }
}

watch(sequenceMode, () => {
  if (suppressTargetReset.value) return
  error.value = ''
  saveError.value = ''
  saveMessage.value = ''
  resetScanPreviewState()
  if (sequenceMode.value === 'market_scan') {
    if (targetType.value === 'index') targetType.value = 'stock'
    selectedCode.value = ''
    selectedName.value = ''
    targetKeyword.value = ''
    candles.value = []
    chartRequested.value = false
  }
})

watch(targetType, () => {
  if (suppressTargetReset.value) return
  targetOptions.value = []
  showSuggestions.value = false
  resetScanPreviewState()
  if (sequenceMode.value === 'single_target') {
    selectedCode.value = ''
    selectedName.value = ''
    targetKeyword.value = ''
    candles.value = []
    chartRequested.value = false
  }
})

watch(
  () => route.query.strategyId,
  (value, previousValue) => {
    if (value !== previousValue) void hydrateStrategyFromRoute()
  },
)

onMounted(async () => {
  await ensureBreadthLoaded()
  await hydrateStrategyFromRoute()
})

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
  scanPreviewController.value?.abort()
  scanPageController.value?.abort()
  scanTargetHitsController.value?.abort()
})
</script>

<template>
  <p v-if="error" class="banner-error">{{ error }}</p>
  <p v-else-if="strategyLoadMessage" class="muted">{{ strategyLoadMessage }}</p>

  <div class="quant-body">
    <div class="quant-content-column">
      <section class="card quant-toolbar-card">
        <div class="quant-page-head">
          <div class="quant-page-head-copy">
            <h3>条件策略</h3>
            <p class="muted">{{ sequencePageDescription }}</p>
          </div>

          <div class="quant-mode-switch" aria-label="条件策略模式切换">
            <button
              v-for="option in modeOptions"
              :key="option.value"
              type="button"
              class="quant-mode-button"
              :class="{ active: sequenceMode === option.value }"
              @click="sequenceMode = option.value"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <div class="quant-sequence-controls">
          <label class="quant-field">
            <span class="quant-field-label">目标类型</span>
            <select v-model="targetType" class="input">
              <option
                v-for="option in sequenceMode === 'market_scan' ? scanTargetTypeOptions : singleTargetTypeOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </label>

          <div v-if="sequenceMode === 'single_target'" class="search-wrap quant-sequence-target-search">
            <label class="quant-field">
              <span class="quant-field-label">目标搜索</span>
              <input
                v-model="targetKeyword"
                class="input"
                placeholder="输入代码或名称"
                @focus="handleSearchFocus"
                @input="handleSearchInput"
              />
            </label>

            <ul v-if="showSuggestions" class="suggest-list">
              <li v-if="suggestionLoading"><span>搜索中...</span></li>
              <li v-else-if="!targetOptions.length"><span>没有匹配结果</span></li>
              <template v-else>
                <li v-for="option in targetOptions" :key="option.code" @mousedown.prevent="pickTarget(option)">
                  <span>{{ option.code }}</span>
                  <strong>{{ option.name }}</strong>
                </li>
              </template>
            </ul>
          </div>

          <div v-else class="quant-sequence-scan-hint">
            <div class="label">扫描范围</div>
            <div class="value small">{{ targetType === 'stock' ? '全市场股票' : '全市场 ETF' }}</div>
          </div>

          <div class="btn-group">
            <button
              v-if="sequenceMode === 'single_target'"
              class="btn primary"
              :disabled="loading || !selectedCode"
              @click="loadSingleTargetKline"
            >
              加载目标 K 线
            </button>
            <button
              v-else
              class="btn primary"
              :disabled="scanLoading || !buyValidation.groups.length || !scanStartDate || !scanEndDate"
              @click="executeMarketScan"
            >
              {{ scanLoading ? '扫描中...' : '执行扫描' }}
            </button>
          </div>
        </div>

        <p v-if="scanStatusMessage" class="muted">{{ scanStatusMessage }}</p>

        <div class="summary quant-sequence-summary">
          <div>
            <div class="label">{{ sequenceMode === 'market_scan' ? '扫描范围' : '当前目标' }}</div>
            <div class="value small">
              {{
                sequenceMode === 'market_scan'
                  ? targetType === 'stock'
                    ? '全市场股票'
                    : '全市场 ETF'
                  : `${selectedName || '-'}（${selectedCode || '-'}）`
              }}
            </div>
          </div>
          <div>
            <div class="label">{{ sequenceMode === 'market_scan' ? '命中事件' : '命中区间' }}</div>
            <div class="value">{{ highlightSummary.matched }}</div>
          </div>
          <div>
            <div class="label">{{ sequenceMode === 'market_scan' ? '可回测事件' : '可预览目标数' }}</div>
            <div class="value">{{ highlightSummary.tradable }}</div>
          </div>
          <div>
            <div class="label">{{ sequenceMode === 'market_scan' ? '命中标的数' : '当前模式' }}</div>
            <div class="value small">{{ sequenceMode === 'market_scan' ? highlightSummary.targets : '单标的预览' }}</div>
          </div>
        </div>
      </section>

      <section
        v-if="sequenceMode === 'single_target' ? activeCandles.length : activeCandles.length || scanPreviewEvents.length"
        class="card quant-chart-card"
      >
        <KlineChart
          v-if="activeCandles.length"
          :candles="activeCandles"
          :highlight-bands="activeHighlightBands"
          :symbol-name="activeSymbolName"
          :symbol-code="activeSymbolCode"
          :default-visible-days="120"
        />
        <div v-else class="quant-stock-empty">
          <h3>扫描结果预览</h3>
          <p class="muted">点击下方事件后，这里会显示该标的在当前扫描结果中的全部命中日期。</p>
        </div>
      </section>

      <section v-else-if="!chartRequested && !loading && sequenceMode === 'single_target'" class="card quant-stock-empty">
        <h3>条件策略预览</h3>
        <p class="muted">先选定目标，再加载 K 线，就能看到信号区间。</p>
      </section>

      <section v-if="sequenceMode === 'market_scan'" class="card progress-card">
        <div class="progress-section-head">
          <div class="progress-section-copy">
            <h3>命中事件</h3>
            <p class="muted">点击事件后，下方图表会切到对应标的，并把该标的的全部命中日期标出来。</p>
          </div>
        </div>

        <div v-if="scanPreviewEvents.length" class="quant-scan-events">
          <button
            v-for="event in scanPreviewEvents"
            :key="event.event_id"
            type="button"
            class="quant-scan-event-item"
            :class="{ active: selectedScanEventId === event.event_id, disabled: !event.tradable }"
            @click="selectScanEvent(event)"
          >
            <div class="quant-scan-event-main">
              <strong>{{ event.target_name }}（{{ event.target_code }}）</strong>
              <span>{{ event.signal_date }} 命中</span>
            </div>
            <div class="quant-scan-event-meta">
              <span>买入：{{ event.buy_date ?? '-' }}</span>
              <span>卖出：{{ event.sell_date ?? '-' }}</span>
              <span>{{ event.tradable ? '可回测' : event.disabled_reason || '不可回测' }}</span>
            </div>
          </button>
        </div>

        <p v-else class="muted">当前还没有扫描到命中事件。</p>

        <div v-if="scanTotalEventCount > scanPageSize" class="progress-hero-actions">
          <button class="btn" :disabled="scanLoading || scanPage <= 1" @click="loadScanEventsPage(scanPage - 1)">上一页</button>
          <span class="muted">第 {{ scanPage }} / {{ scanTotalPages }} 页，共 {{ scanTotalEventCount }} 条事件</span>
          <button class="btn" :disabled="scanLoading || scanPage >= scanTotalPages" @click="loadScanEventsPage(scanPage + 1)">下一页</button>
        </div>
      </section>
    </div>

    <aside class="quant-filter-sidebar">
      <section class="card quant-filter-card">
        <div class="quant-filter-head">
          <div>
            <h3>{{ sequenceMode === 'market_scan' ? '扫描条件' : '连续交易日规则' }}</h3>
            <p class="muted">
              {{
                sequenceMode === 'market_scan'
                  ? '这里只定义哪些日期算命中，不在这里配置回测买卖执行参数。'
                  : '单标的模式支持买卖两套规则，组内 AND，组间 OR。'
              }}
            </p>
          </div>
        </div>

        <div class="quant-filter-sections">
          <QuantSequenceRuleBuilder
            side="buy"
            :groups="buyRuleDrafts"
            :group-errors="buyValidation.groupErrors"
            :condition-errors="buyValidation.conditionErrors"
            @add-group="addRuleGroup('buy')"
            @delete-group="deleteRuleGroup('buy', $event)"
            @add-condition="addRuleCondition('buy', $event)"
            @delete-condition="deleteRuleCondition('buy', $event.groupId, $event.conditionId)"
          />

          <QuantSequenceRuleBuilder
            v-if="sequenceMode === 'single_target'"
            side="sell"
            :groups="sellRuleDrafts"
            :group-errors="sellValidation.groupErrors"
            :condition-errors="sellValidation.conditionErrors"
            @add-group="addRuleGroup('sell')"
            @delete-group="deleteRuleGroup('sell', $event)"
            @add-condition="addRuleCondition('sell', $event)"
            @delete-condition="deleteRuleCondition('sell', $event.groupId, $event.conditionId)"
          />
        </div>

        <section class="quant-save-box">
          <label class="quant-field">
            <span class="quant-field-label">策略名称</span>
            <input v-model="saveName" class="input" placeholder="输入策略名称" />
          </label>

          <label v-if="sequenceMode === 'single_target'" class="quant-field">
            <span class="quant-field-label">策略开始日期</span>
            <input v-model="strategyStartDate" class="input" type="date" />
          </label>

          <template v-if="sequenceMode === 'market_scan'">
            <div class="quant-scan-config-grid">
              <label class="quant-field">
                <span class="quant-field-label">扫描开始日期</span>
                <input v-model="scanStartDate" class="input" type="date" />
              </label>
              <label class="quant-field">
                <span class="quant-field-label">扫描结束日期</span>
                <input v-model="scanEndDate" class="input" type="date" />
              </label>
            </div>
            <p class="muted quant-save-hint">这里仅保存扫描范围和策略名称；组合回测参数请到策略回测页中调整。</p>
            <p v-if="scanRangeWarning" class="muted">{{ scanRangeWarning }}</p>
          </template>

          <p v-if="saveError" class="error">{{ saveError }}</p>
          <p v-else-if="saveMessage" class="muted">{{ saveMessage }}</p>
        </section>

        <div class="quant-filter-footer">
          <button class="btn primary" :disabled="!canSave" @click="saveStrategy(false)">
            {{ saveLoading ? '保存中...' : loadedStrategyId ? '更新当前策略' : '保存策略' }}
          </button>
          <button class="btn" :disabled="!canSave" @click="saveStrategy(true)">
            {{ saveLoading ? '保存中...' : '另存为新策略' }}
          </button>
        </div>
      </section>
    </aside>
  </div>
</template>
