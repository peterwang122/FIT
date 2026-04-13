<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  createQuantStrategy,
  fetchQuantStrategy,
  fetchHfqKline,
  fetchHfqTaskStatus,
  fetchSymbols,
  submitHfqCollectTask,
  updateQuantStrategy,
} from '../api/stocks'
import QuantRuleGroupBuilder from '../components/QuantRuleGroupBuilder.vue'
import QuantStockChart from '../components/QuantStockChart.vue'
import type {
  QuantFilterGroupSet,
  QuantHighlightBand,
  QuantIndicatorParams,
  QuantRuleGroupDraft,
  QuantStrategyConfig,
} from '../types/quant'
import type { KlineCandle, StockSymbol } from '../types/stock'
import { STOCK_QUANT_FILTER_FIELD_KEYS, buildStockQuantFilterDataset } from '../utils/quantIndicators'
import {
  createEmptyRuleConditionDraft,
  createEmptyRuleGroupDraft,
  deserializeRuleGroups,
  matchRuleGroupIndexes,
  normalizeRuleGroups,
} from '../utils/quantRuleGroups'

type QuantFormState = {
  ma1: string
  ma2: string
  ma3: string
  ma4: string
  macdFast: string
  macdSlow: string
  macdSignal: string
  kdjPeriod: string
  kdjKSmoothing: string
  kdjDSmoothing: string
  wrPeriod: string
  rsiPeriod: string
  bollPeriod: string
  bollMultiplier: string
}

type QuantFormErrors = Partial<Record<keyof QuantFormState, string>>
type QuantFilterColor = 'blue' | 'red'

const FILTER_COLORS: QuantFilterColor[] = ['blue', 'red']
const DEFAULT_PARAMS: QuantIndicatorParams = {
  ma: { periods: [5, 10, 20, 60] },
  macd: { fast: 12, slow: 26, signal: 9 },
  kdj: { period: 9, kSmoothing: 3, dSmoothing: 3 },
  wr: { period: 14 },
  rsi: { period: 14 },
  boll: { period: 20, multiplier: 2 },
}
const PARAM_GROUPS: Array<{
  key: 'ma' | 'macd' | 'kdj' | 'wr' | 'rsi' | 'boll'
  title: string
  hint: string
  fields: Array<{ key: keyof QuantFormState; label: string; mode: 'numeric' | 'decimal'; full?: boolean }>
}> = [
  {
    key: 'ma',
    title: '均线',
    hint: 'SMA',
    fields: [
      { key: 'ma1', label: 'MA1', mode: 'numeric' },
      { key: 'ma2', label: 'MA2', mode: 'numeric' },
      { key: 'ma3', label: 'MA3', mode: 'numeric' },
      { key: 'ma4', label: 'MA4', mode: 'numeric' },
    ],
  },
  {
    key: 'macd',
    title: 'MACD',
    hint: 'EMA',
    fields: [
      { key: 'macdFast', label: 'Fast', mode: 'numeric' },
      { key: 'macdSlow', label: 'Slow', mode: 'numeric' },
      { key: 'macdSignal', label: 'Signal', mode: 'numeric', full: true },
    ],
  },
  {
    key: 'kdj',
    title: 'KDJ',
    hint: 'RSV',
    fields: [
      { key: 'kdjPeriod', label: '周期', mode: 'numeric' },
      { key: 'kdjKSmoothing', label: 'K 平滑', mode: 'numeric' },
      { key: 'kdjDSmoothing', label: 'D 平滑', mode: 'numeric', full: true },
    ],
  },
  {
    key: 'wr',
    title: 'WR',
    hint: '0-100',
    fields: [{ key: 'wrPeriod', label: '周期', mode: 'numeric', full: true }],
  },
  {
    key: 'rsi',
    title: 'RSI',
    hint: '0-100',
    fields: [{ key: 'rsiPeriod', label: '周期', mode: 'numeric', full: true }],
  },
  {
    key: 'boll',
    title: 'BOLL',
    hint: 'SMA + STD',
    fields: [
      { key: 'bollPeriod', label: '周期', mode: 'numeric' },
      { key: 'bollMultiplier', label: '倍数', mode: 'decimal' },
    ],
  },
]

function cloneParams(params: QuantIndicatorParams): QuantIndicatorParams {
  return {
    ma: { periods: [...params.ma.periods] as [number, number, number, number] },
    macd: { ...params.macd },
    kdj: { ...params.kdj },
    wr: { ...params.wr },
    rsi: { ...params.rsi },
    boll: { ...params.boll },
  }
}

function buildFormState(params: QuantIndicatorParams): QuantFormState {
  return {
    ma1: String(params.ma.periods[0]),
    ma2: String(params.ma.periods[1]),
    ma3: String(params.ma.periods[2]),
    ma4: String(params.ma.periods[3]),
    macdFast: String(params.macd.fast),
    macdSlow: String(params.macd.slow),
    macdSignal: String(params.macd.signal),
    kdjPeriod: String(params.kdj.period),
    kdjKSmoothing: String(params.kdj.kSmoothing),
    kdjDSmoothing: String(params.kdj.dSmoothing),
    wrPeriod: String(params.wr.period),
    rsiPeriod: String(params.rsi.period),
    bollPeriod: String(params.boll.period),
    bollMultiplier: String(params.boll.multiplier),
  }
}

function cloneFilterGroups(groups: QuantFilterGroupSet): QuantFilterGroupSet {
  return JSON.parse(JSON.stringify(groups ?? [])) as QuantFilterGroupSet
}

function normalizeIndicatorParams(raw: Partial<QuantIndicatorParams> | null | undefined): QuantIndicatorParams {
  const periods = raw?.ma?.periods
  const maPeriods: [number, number, number, number] =
    Array.isArray(periods) && periods.length >= 4
      ? [
          Number(periods[0]) || DEFAULT_PARAMS.ma.periods[0],
          Number(periods[1]) || DEFAULT_PARAMS.ma.periods[1],
          Number(periods[2]) || DEFAULT_PARAMS.ma.periods[2],
          Number(periods[3]) || DEFAULT_PARAMS.ma.periods[3],
        ]
      : [...DEFAULT_PARAMS.ma.periods]

  return {
    ma: { periods: maPeriods },
    macd: {
      fast: Number(raw?.macd?.fast) || DEFAULT_PARAMS.macd.fast,
      slow: Number(raw?.macd?.slow) || DEFAULT_PARAMS.macd.slow,
      signal: Number(raw?.macd?.signal) || DEFAULT_PARAMS.macd.signal,
    },
    kdj: {
      period: Number(raw?.kdj?.period) || DEFAULT_PARAMS.kdj.period,
      kSmoothing: Number(raw?.kdj?.kSmoothing) || DEFAULT_PARAMS.kdj.kSmoothing,
      dSmoothing: Number(raw?.kdj?.dSmoothing) || DEFAULT_PARAMS.kdj.dSmoothing,
    },
    wr: {
      period: Number(raw?.wr?.period) || DEFAULT_PARAMS.wr.period,
    },
    rsi: {
      period: Number(raw?.rsi?.period) || DEFAULT_PARAMS.rsi.period,
    },
    boll: {
      period: Number(raw?.boll?.period) || DEFAULT_PARAMS.boll.period,
      multiplier: Number(raw?.boll?.multiplier) || DEFAULT_PARAMS.boll.multiplier,
    },
  }
}

function buildIdempotencyKey(tsCode: string): string {
  return `hfq-collect:${tsCode}:${new Date().toISOString().slice(0, 10)}`
}

function parsePositiveInteger(label: string, rawValue: string) {
  const parsed = Number(rawValue.trim())
  if (!rawValue.trim()) return { value: null, error: `${label}不能为空` }
  if (!Number.isInteger(parsed) || parsed <= 0) return { value: null, error: `${label}必须为正整数` }
  return { value: parsed, error: '' }
}

function parsePositiveNumber(label: string, rawValue: string) {
  const parsed = Number(rawValue.trim())
  if (!rawValue.trim()) return { value: null, error: `${label}不能为空` }
  if (!Number.isFinite(parsed) || parsed <= 0) return { value: null, error: `${label}必须大于 0` }
  return { value: parsed, error: '' }
}

function formatTurnoverRatePercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '-'
  return (Number(value) * 100).toFixed(4).replace(/\.?0+$/, '')
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '加载失败'
}

const symbols = ref<StockSymbol[]>([])
const searchKeyword = ref('')
const showSuggestions = ref(false)
const suggestionLoading = ref(false)
const selectedCode = ref('')
const selectedName = ref('')
const candles = ref<KlineCandle[]>([])
const loading = ref(false)
const booting = ref(true)
const error = ref('')
const chartRequested = ref(false)
const collectLoading = ref(false)
const collectTaskId = ref('')
const collectState = ref('')
const collectMessage = ref('')
const saveName = ref('')
const saveLoading = ref(false)
const saveMessage = ref('')
const saveError = ref('')
const showParamsModal = ref(false)
const loadedStrategyId = ref<number | null>(null)
const strategyLoadMessage = ref('')
const route = useRoute()

const appliedParams = ref<QuantIndicatorParams>(cloneParams(DEFAULT_PARAMS))
const appliedBlueFilterGroups = ref<QuantFilterGroupSet>([])
const appliedRedFilterGroups = ref<QuantFilterGroupSet>([])

const formState = reactive<QuantFormState>(buildFormState(DEFAULT_PARAMS))
const blueRuleDrafts = ref<QuantRuleGroupDraft[]>([])
const redRuleDrafts = ref<QuantRuleGroupDraft[]>([])

const latestStockSnapshot = computed(() => (candles.value.length ? candles.value[candles.value.length - 1] : undefined))
const filteredSymbols = computed(() => symbols.value)

let searchTimer: ReturnType<typeof setTimeout> | null = null
let latestSearchRequestId = 0

async function loadSuggestions(keyword: string) {
  const requestId = ++latestSearchRequestId
  suggestionLoading.value = true
  try {
    const items = await fetchSymbols(30, keyword)
    if (requestId !== latestSearchRequestId) return
    symbols.value = items
  } catch (loadError) {
    if (requestId === latestSearchRequestId) {
      error.value = getErrorMessage(loadError)
    }
  } finally {
    if (requestId === latestSearchRequestId) {
      suggestionLoading.value = false
    }
  }
}

function scheduleSuggestionSearch(keyword: string) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    void loadSuggestions(keyword)
  }, 280)
}

const quantFilterDataset = computed(() => buildStockQuantFilterDataset(candles.value, appliedParams.value))
const numericFieldOptions = computed(() =>
  quantFilterDataset.value.fields
    .filter((field) => STOCK_QUANT_FILTER_FIELD_KEYS.includes(field.key))
    .map((field) => ({ value: field.key, label: field.label })),
)

const validation = computed(() => {
  const errors: QuantFormErrors = {}
  const ma1 = parsePositiveInteger('MA1', formState.ma1)
  const ma2 = parsePositiveInteger('MA2', formState.ma2)
  const ma3 = parsePositiveInteger('MA3', formState.ma3)
  const ma4 = parsePositiveInteger('MA4', formState.ma4)
  const macdFast = parsePositiveInteger('MACD Fast', formState.macdFast)
  const macdSlow = parsePositiveInteger('MACD Slow', formState.macdSlow)
  const macdSignal = parsePositiveInteger('MACD Signal', formState.macdSignal)
  const kdjPeriod = parsePositiveInteger('KDJ 周期', formState.kdjPeriod)
  const kdjKSmoothing = parsePositiveInteger('KDJ K 平滑', formState.kdjKSmoothing)
  const kdjDSmoothing = parsePositiveInteger('KDJ D 平滑', formState.kdjDSmoothing)
  const wrPeriod = parsePositiveInteger('WR 周期', formState.wrPeriod)
  const rsiPeriod = parsePositiveInteger('RSI 周期', formState.rsiPeriod)
  const bollPeriod = parsePositiveInteger('BOLL 周期', formState.bollPeriod)
  const bollMultiplier = parsePositiveNumber('BOLL 倍数', formState.bollMultiplier)
  ;[
    ['ma1', ma1.error],
    ['ma2', ma2.error],
    ['ma3', ma3.error],
    ['ma4', ma4.error],
    ['macdFast', macdFast.error],
    ['macdSlow', macdSlow.error],
    ['macdSignal', macdSignal.error],
    ['kdjPeriod', kdjPeriod.error],
    ['kdjKSmoothing', kdjKSmoothing.error],
    ['kdjDSmoothing', kdjDSmoothing.error],
    ['wrPeriod', wrPeriod.error],
    ['rsiPeriod', rsiPeriod.error],
    ['bollPeriod', bollPeriod.error],
    ['bollMultiplier', bollMultiplier.error],
  ].forEach(([key, message]) => {
    if (message) errors[key as keyof QuantFormState] = message
  })
  if (macdFast.value !== null && macdSlow.value !== null && macdFast.value >= macdSlow.value) {
    errors.macdFast = '必须满足 Fast < Slow'
    errors.macdSlow = '必须满足 Fast < Slow'
  }
  if (Object.keys(errors).length) return { errors, params: null }
  return {
    errors,
    params: {
      ma: { periods: [ma1.value, ma2.value, ma3.value, ma4.value] as [number, number, number, number] },
      macd: { fast: macdFast.value as number, slow: macdSlow.value as number, signal: macdSignal.value as number },
      kdj: {
        period: kdjPeriod.value as number,
        kSmoothing: kdjKSmoothing.value as number,
        dSmoothing: kdjDSmoothing.value as number,
      },
      wr: { period: wrPeriod.value as number },
      rsi: { period: rsiPeriod.value as number },
      boll: { period: bollPeriod.value as number, multiplier: bollMultiplier.value as number },
    } satisfies QuantIndicatorParams,
  }
})

const blueRuleValidation = computed(() => normalizeRuleGroups(blueRuleDrafts.value, STOCK_QUANT_FILTER_FIELD_KEYS))
const redRuleValidation = computed(() => normalizeRuleGroups(redRuleDrafts.value, STOCK_QUANT_FILTER_FIELD_KEYS))
const canApplyParams = computed(() => Boolean(validation.value.params) && !loading.value)

const highlightBands = computed<QuantHighlightBand[]>(() => {
  return quantFilterDataset.value.snapshots.reduce<QuantHighlightBand[]>((bands, snapshot) => {
    const blueHitGroups = matchRuleGroupIndexes(snapshot, appliedBlueFilterGroups.value)
    const redHitGroups = matchRuleGroupIndexes(snapshot, appliedRedFilterGroups.value)
    const isBlue = blueHitGroups.length > 0
    const isRed = redHitGroups.length > 0
    const variant = blueHitGroups.length > 1 || redHitGroups.length > 1 ? 'striped' : 'solid'

    if (isBlue && isRed) {
      bands.push({ tradeDate: snapshot.tradeDate, color: 'purple', variant, blueHitGroups, redHitGroups })
    } else if (isBlue) {
      bands.push({ tradeDate: snapshot.tradeDate, color: 'blue', variant, blueHitGroups, redHitGroups: [] })
    } else if (isRed) {
      bands.push({ tradeDate: snapshot.tradeDate, color: 'red', variant, blueHitGroups: [], redHitGroups })
    }
    return bands
  }, [])
})

const highlightSummary = computed(() => ({
  blue: highlightBands.value.filter((item) => item.color === 'blue').length,
  red: highlightBands.value.filter((item) => item.color === 'red').length,
  purple: highlightBands.value.filter((item) => item.color === 'purple').length,
}))

const canApplyFilters = computed(() => {
  const blueValid = blueRuleValidation.value
  const redValid = redRuleValidation.value
  return (
    !loading.value &&
    !booting.value &&
    !Object.keys(blueValid.groupErrors).length &&
    !Object.keys(blueValid.conditionErrors).length &&
    !Object.keys(redValid.groupErrors).length &&
    !Object.keys(redValid.conditionErrors).length
  )
})

function getRuleDraftsByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueRuleDrafts.value : redRuleDrafts.value
}

function getRuleValidationByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueRuleValidation.value : redRuleValidation.value
}

function addRuleGroup(color: QuantFilterColor) {
  const nextGroup = createEmptyRuleGroupDraft()
  if (color === 'blue') blueRuleDrafts.value = [...blueRuleDrafts.value, nextGroup]
  else redRuleDrafts.value = [...redRuleDrafts.value, nextGroup]
}

function deleteRuleGroup(color: QuantFilterColor, groupId: string) {
  if (color === 'blue') blueRuleDrafts.value = blueRuleDrafts.value.filter((group) => group.id !== groupId)
  else redRuleDrafts.value = redRuleDrafts.value.filter((group) => group.id !== groupId)
}

function addRuleCondition(color: QuantFilterColor, groupId: string) {
  const targetGroup = getRuleDraftsByColor(color).find((item) => item.id === groupId)
  if (!targetGroup) return
  targetGroup.conditions.push(createEmptyRuleConditionDraft())
}

function deleteRuleCondition(color: QuantFilterColor, groupId: string, conditionId: string) {
  const targetGroup = getRuleDraftsByColor(color).find((item) => item.id === groupId)
  if (!targetGroup) return
  targetGroup.conditions = targetGroup.conditions.filter((item) => item.id !== conditionId)
  if (!targetGroup.conditions.length) {
    deleteRuleGroup(color, groupId)
  }
}

function pickSymbol(code: string, name: string) {
  selectedCode.value = code
  selectedName.value = name
  searchKeyword.value = `${code} ${name}`
  showSuggestions.value = false
  candles.value = []
  chartRequested.value = false
}

function handleSearchFocus() {
  showSuggestions.value = true
  scheduleSuggestionSearch(searchKeyword.value.trim())
}

function handleSearchInput() {
  showSuggestions.value = true
  scheduleSuggestionSearch(searchKeyword.value.trim())
}

async function loadHfqKline() {
  if (!selectedCode.value) {
    error.value = '请先选择股票'
    return false
  }
  loading.value = true
  error.value = ''
  chartRequested.value = true
  try {
    candles.value = await fetchHfqKline(selectedCode.value)
    if (!candles.value.length) {
      error.value = '当前暂无后复权数据，请先触发临时采集或等待采集端初始化。'
      return false
    }
    return true
  } catch (loadError) {
    candles.value = []
    error.value = getErrorMessage(loadError)
    return false
  } finally {
    loading.value = false
  }
}

async function triggerCollect() {
  if (!selectedCode.value) {
    error.value = '请先选择股票'
    return
  }
  collectLoading.value = true
  collectMessage.value = ''
  try {
    const result = await submitHfqCollectTask(selectedCode.value, buildIdempotencyKey(selectedCode.value))
    collectTaskId.value = result.task_id
    collectState.value = result.status
    collectMessage.value = '采集任务已提交，完成后请手动刷新股票 K 线。'
  } catch (collectError) {
    error.value = getErrorMessage(collectError)
  } finally {
    collectLoading.value = false
  }
}

async function refreshTaskStatus() {
  if (!collectTaskId.value) return
  try {
    const result = await fetchHfqTaskStatus(collectTaskId.value)
    collectState.value = result.state
  } catch (taskError) {
    error.value = getErrorMessage(taskError)
  }
}

function applyParams() {
  if (validation.value.params) {
    appliedParams.value = cloneParams(validation.value.params)
    showParamsModal.value = false
  }
}

function resetParams() {
  Object.assign(formState, buildFormState(DEFAULT_PARAMS))
}

function openParamsModal() {
  Object.assign(formState, buildFormState(appliedParams.value))
  showParamsModal.value = true
}

function closeParamsModal() {
  showParamsModal.value = false
  Object.assign(formState, buildFormState(appliedParams.value))
}

function applyFilters() {
  if (!canApplyFilters.value) return
  appliedBlueFilterGroups.value = blueRuleValidation.value.groups
  appliedRedFilterGroups.value = redRuleValidation.value.groups
}

function clearFilters() {
  blueRuleDrafts.value = []
  redRuleDrafts.value = []
  appliedBlueFilterGroups.value = []
  appliedRedFilterGroups.value = []
}

async function saveStrategy() {
  saveError.value = ''
  saveMessage.value = ''
  if (!saveName.value.trim()) {
    saveError.value = '请先填写策略名称'
    return
  }
  if (!selectedCode.value || !selectedName.value) {
    saveError.value = '当前没有可保存的股票标的'
    return
  }
  saveLoading.value = true
  try {
    const result = await createQuantStrategy({
      name: saveName.value.trim(),
      notes: '',
      strategy_engine: 'snapshot',
      sequence_mode: 'single_target',
      strategy_type: 'stock',
      target_code: selectedCode.value,
      target_name: selectedName.value,
      indicator_params: appliedParams.value,
      buy_sequence_groups: [],
      sell_sequence_groups: [],
      scan_trade_config: {
        initial_capital: 1_000_000,
        buy_amount_per_event: 10_000,
        buy_offset_trading_days: 1,
        sell_offset_trading_days: 2,
        buy_price_basis: 'open',
        sell_price_basis: 'open',
      },
      blue_filter_groups: appliedBlueFilterGroups.value,
      red_filter_groups: appliedRedFilterGroups.value,
      blue_filters: {},
      red_filters: {},
      blue_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
      red_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
      signal_buy_color: 'blue',
      signal_sell_color: 'red',
      purple_conflict_mode: 'sell_first',
      start_date: null,
      scan_start_date: null,
      scan_end_date: null,
      buy_position_pct: 1,
      sell_position_pct: 1,
      execution_price_mode: 'next_open',
    })
    loadedStrategyId.value = result.id
    saveName.value = result.name
    saveMessage.value = `已保存策略：${result.name}`
  } catch (saveErr) {
    saveError.value = getErrorMessage(saveErr)
  } finally {
    saveLoading.value = false
  }
}

async function saveCurrentStrategy() {
  if (!loadedStrategyId.value) {
    await saveStrategy()
    return
  }
  saveError.value = ''
  saveMessage.value = ''
  if (!saveName.value.trim()) {
    saveError.value = '璇峰厛濉啓绛栫暐鍚嶇О'
    return
  }
  if (!selectedCode.value || !selectedName.value) {
    saveError.value = '褰撳墠娌℃湁鍙繚瀛樼殑鑲＄エ鏍囩殑'
    return
  }
  saveLoading.value = true
  try {
    const result = await updateQuantStrategy(loadedStrategyId.value, {
      name: saveName.value.trim(),
      notes: '',
      strategy_engine: 'snapshot',
      sequence_mode: 'single_target',
      strategy_type: 'stock',
      target_code: selectedCode.value,
      target_name: selectedName.value,
      indicator_params: appliedParams.value,
      buy_sequence_groups: [],
      sell_sequence_groups: [],
      scan_trade_config: {
        initial_capital: 1_000_000,
        buy_amount_per_event: 10_000,
        buy_offset_trading_days: 1,
        sell_offset_trading_days: 2,
        buy_price_basis: 'open',
        sell_price_basis: 'open',
      },
      blue_filter_groups: appliedBlueFilterGroups.value,
      red_filter_groups: appliedRedFilterGroups.value,
      blue_filters: {},
      red_filters: {},
      blue_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
      red_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
      signal_buy_color: 'blue',
      signal_sell_color: 'red',
      purple_conflict_mode: 'sell_first',
      start_date: null,
      scan_start_date: null,
      scan_end_date: null,
      buy_position_pct: 1,
      sell_position_pct: 1,
      execution_price_mode: 'next_open',
    })
    loadedStrategyId.value = result.id
    saveName.value = result.name
    saveMessage.value = `已更新策略：${result.name}`
  } catch (saveErr) {
    saveError.value = getErrorMessage(saveErr)
  } finally {
    saveLoading.value = false
  }
}

async function saveAsNewStrategy() {
  await saveStrategy()
}

function getStrategyIdFromRoute() {
  const raw = route.query.strategyId
  const normalized = Array.isArray(raw) ? raw[0] : raw
  const parsed = normalized ? Number(normalized) : Number.NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function applyStrategyConfig(strategy: QuantStrategyConfig) {
  const nextParams = normalizeIndicatorParams(strategy.indicator_params)
  const blueGroups = cloneFilterGroups(strategy.blue_filter_groups)
  const redGroups = cloneFilterGroups(strategy.red_filter_groups)

  appliedParams.value = nextParams
  Object.assign(formState, buildFormState(nextParams))
  blueRuleDrafts.value = deserializeRuleGroups(blueGroups)
  redRuleDrafts.value = deserializeRuleGroups(redGroups)
  appliedBlueFilterGroups.value = blueGroups
  appliedRedFilterGroups.value = redGroups
  saveName.value = strategy.name
  loadedStrategyId.value = strategy.id
  showParamsModal.value = false
}

async function hydrateStrategyFromRoute() {
  const strategyId = getStrategyIdFromRoute()
  if (!strategyId) return

  strategyLoadMessage.value = ''
  error.value = ''
  saveError.value = ''

  try {
    const strategy = await fetchQuantStrategy(strategyId)
    if (strategy.strategy_engine !== 'snapshot' || strategy.strategy_type !== 'stock') {
      error.value = '当前策略不是股票策略，无法加载到股票分析页'
      return
    }

    pickSymbol(strategy.target_code, strategy.target_name)
    const loaded = await loadHfqKline()
    if (!loaded) {
      error.value = error.value || '策略对应股票数据加载失败'
      return
    }

    applyStrategyConfig(strategy)
    strategyLoadMessage.value = `已加载策略：${strategy.name}`
  } catch (loadError) {
    error.value = getErrorMessage(loadError)
  }
}

onMounted(async () => {
  booting.value = false
  await hydrateStrategyFromRoute()
})

watch(
  () => route.query.strategyId,
  (value, previousValue) => {
    if (booting.value) return
    if (value === previousValue) return
    void hydrateStrategyFromRoute()
  },
)

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <p v-if="error" class="banner-error">{{ error }}</p>
  <p v-else-if="strategyLoadMessage" class="muted">{{ strategyLoadMessage }}</p>
  <div v-if="showParamsModal" class="quant-modal-backdrop" @click="closeParamsModal"></div>
  <div class="quant-body">
    <div class="quant-content-column">
      <section class="card quant-toolbar-card">
        <div class="quant-page-head">
          <div>
            <h3>股票参数</h3>
            <p class="muted">默认不自动展示数据，选股后可手动刷新后复权 K 线或触发临时采集。</p>
          </div>
        </div>

        <div class="stock-stage-grid quant-stock-top">
          <aside class="card stock-control-panel quant-stock-control">
            <div class="stock-control-block">
              <h3>股票搜索</h3>
              <div class="search-wrap">
                <input
                  v-model="searchKeyword"
                  class="input"
                  placeholder="输入股票代码或股票名称"
                  @focus="handleSearchFocus"
                  @input="handleSearchInput"
                />
                <ul v-if="showSuggestions" class="suggest-list">
                  <li v-if="suggestionLoading">
                    <span>搜索中...</span>
                  </li>
                  <li v-else-if="!filteredSymbols.length">
                    <span>没有匹配结果</span>
                  </li>
                  <template v-else>
                    <li v-for="item in filteredSymbols" :key="item.ts_code" @mousedown.prevent="pickSymbol(item.ts_code, item.stock_name)">
                      <span>{{ item.ts_code }}</span>
                      <strong>{{ item.stock_name }}</strong>
                    </li>
                  </template>
                </ul>
              </div>
            </div>

            <div class="btn-group">
              <button class="btn primary" :disabled="loading || !selectedCode" @click="loadHfqKline">刷新股票 K 线</button>
              <button class="btn" :disabled="collectLoading || !selectedCode" @click="triggerCollect">
                {{ collectLoading ? '提交中...' : '触发采集' }}
              </button>
              <button class="btn" :disabled="!collectTaskId" @click="refreshTaskStatus">刷新任务状态</button>
            </div>

            <div class="stock-status-list">
              <div class="stock-status-item">
                <span>当前股票</span>
                <strong>{{ selectedName || '-' }}（{{ selectedCode || '-' }}）</strong>
              </div>
              <div class="stock-status-item">
                <span>任务 ID</span>
                <strong>{{ collectTaskId || '-' }}</strong>
              </div>
              <div class="stock-status-item">
                <span>任务状态</span>
                <strong>{{ collectState || '-' }}</strong>
              </div>
            </div>

            <p v-if="collectMessage" class="muted">{{ collectMessage }}</p>
          </aside>

          <div class="quant-stock-summary-wrap">
            <section v-if="latestStockSnapshot" class="card summary stock-summary">
              <div class="symbol-head">{{ selectedName }}（{{ selectedCode }}）</div>
              <div>
                <div class="label">交易日期</div>
                <div class="value">{{ latestStockSnapshot.trade_date }}</div>
              </div>
              <div>
                <div class="label">收盘价</div>
                <div class="value">{{ latestStockSnapshot.close }}</div>
              </div>
              <div>
                <div class="label">涨跌幅</div>
                <div class="value">{{ latestStockSnapshot.pct_chg }}%</div>
              </div>
              <div>
                <div class="label">成交量</div>
                <div class="value">{{ latestStockSnapshot.vol }}</div>
              </div>
              <div>
                <div class="label">换手率</div>
                <div class="value">{{ formatTurnoverRatePercent(latestStockSnapshot.turnover_rate) }}%</div>
              </div>
            </section>

            <section v-else-if="!chartRequested && !loading" class="card quant-stock-empty">
              <h3>股票量化图表</h3>
              <p class="muted">先选择股票，再点击“刷新股票 K 线”加载后复权数据。</p>
            </section>
          </div>
        </div>
      </section>

      <section v-if="showParamsModal" class="card quant-modal quant-param-modal">
          <div class="quant-page-head">
            <div>
              <h3>股票参数</h3>
              <p class="muted">默认不自动展示数据，选股后可手动刷新后复权 K 线或触发临时采集。</p>
            </div>
            <button type="button" class="btn" @click="closeParamsModal">关闭</button>
          </div>
          <div class="quant-form-grid">
            <article v-for="group in PARAM_GROUPS" :key="group.key" class="quant-param-group" :class="{ 'quant-param-group-boll': group.key === 'boll' }">
            <div class="quant-param-group-head">
              <h3>{{ group.title }}</h3>
              <span class="muted">{{ group.hint }}</span>
            </div>
            <div class="quant-field-grid">
              <label v-for="field in group.fields" :key="field.key" class="quant-field" :class="{ 'quant-field-full': field.full }">
                <span class="quant-field-label">{{ field.label }}</span>
                <input v-model="formState[field.key]" class="input" :inputmode="field.mode" />
                <span v-if="validation.errors[field.key]" class="quant-field-error">{{ validation.errors[field.key] }}</span>
              </label>
            </div>
            <div v-if="group.key === 'boll'" class="quant-param-group-footer">
              <button class="btn primary" :disabled="!canApplyParams" @click="applyParams">应用参数</button>
              <button class="btn" :disabled="loading" @click="resetParams">恢复默认</button>
            </div>
            </article>
          </div>
        </section>

      <section v-if="candles.length" class="card quant-chart-card">
        <QuantStockChart
          :candles="candles"
          :highlight-bands="highlightBands"
          :symbol-name="selectedName"
          :symbol-code="selectedCode"
          :params="appliedParams"
          :loading="loading || booting"
          :default-visible-days="90"
          @open-settings="openParamsModal"
        />
      </section>
    </div>

    <aside class="quant-filter-sidebar">
      <section class="card quant-filter-card">
        <div class="quant-filter-head">
          <div>
            <h3>指标筛选</h3>
            <p class="muted">当前股票：{{ selectedName || '未选择' }}</p>
          </div>
          <div class="quant-filter-counts">
            <span class="quant-filter-count quant-filter-count-blue">蓝 {{ highlightSummary.blue }}</span>
            <span class="quant-filter-count quant-filter-count-red">红 {{ highlightSummary.red }}</span>
            <span class="quant-filter-count quant-filter-count-purple">紫 {{ highlightSummary.purple }}</span>
          </div>
        </div>

        <p class="quant-filter-hint muted">股票筛选支持 MA、换手率、RSI、BOLL、MACD、KDJ、WR；规则组内全部满足，满足任一规则组即命中颜色。</p>

        <div class="quant-filter-sections">
          <QuantRuleGroupBuilder
            v-for="color in FILTER_COLORS"
            :key="color"
            :color="color"
            :groups="getRuleDraftsByColor(color)"
            :numeric-field-options="numericFieldOptions"
            :group-errors="getRuleValidationByColor(color).groupErrors"
            :condition-errors="getRuleValidationByColor(color).conditionErrors"
            @add-group="addRuleGroup(color)"
            @delete-group="deleteRuleGroup(color, $event)"
            @add-condition="addRuleCondition(color, $event)"
            @delete-condition="deleteRuleCondition(color, $event.groupId, $event.conditionId)"
          />
        </div>

        <section class="quant-save-box">
          <label class="quant-field">
            <span class="quant-field-label">保存当前股票策略</span>
            <input v-model="saveName" class="input" placeholder="输入策略名称" />
          </label>
          <p v-if="saveError" class="error">{{ saveError }}</p>
          <p v-else-if="saveMessage" class="muted">{{ saveMessage }}</p>
        </section>

        <div class="quant-filter-footer">
          <button class="btn primary" :disabled="!canApplyFilters" @click="applyFilters">确定</button>
          <button class="btn" @click="clearFilters">清空筛选</button>
          <button class="btn" :disabled="saveLoading || !selectedCode" @click="saveCurrentStrategy">
            {{ saveLoading ? '保存中...' : loadedStrategyId ? '更新当前策略' : '保存筛选' }}
          </button>
          <button class="btn" :disabled="saveLoading || !selectedCode" @click="saveAsNewStrategy">
            {{ saveLoading ? '保存中...' : '另存为新策略' }}
          </button>
        </div>
      </section>
    </aside>
  </div>
</template>
