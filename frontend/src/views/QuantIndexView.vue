<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { createQuantStrategy, fetchIndexDashboard, fetchIndexOptions, fetchQuantStrategy, updateQuantStrategy } from '../api/stocks'
import QuantIndexChart from '../components/QuantIndexChart.vue'
import QuantRuleGroupBuilder from '../components/QuantRuleGroupBuilder.vue'
import type {
  QuantFilterGroupSet,
  QuantHighlightBand,
  QuantIndicatorParams,
  QuantRuleGroupDraft,
  QuantStrategyConfig,
  QuantTargetMarket,
} from '../types/quant'
import type {
  FuturesBasisPoint,
  IndexBreadthPoint,
  IndexDashboardBasisPoint,
  IndexDashboardEmotionPoint,
  IndexDashboardResponse,
  IndexEmotionPoint,
  IndexUsFearGreedPoint,
  IndexUsHedgeProxyPoint,
  IndexUsVixPoint,
  IndexVixPoint,
  KlineCandle,
  MarketOption,
} from '../types/stock'
import {
  INDEX_QUANT_FILTER_FIELD_KEYS,
  STOCK_QUANT_FILTER_FIELD_KEYS,
  US_INDEX_QUANT_FILTER_FIELD_KEYS,
  buildIndexQuantFilterDataset,
  buildStockQuantFilterDataset,
} from '../utils/quantIndicators'
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
type IndexDashboardChunkState = {
  market: QuantTargetMarket
  supportsAuxiliaryPanels: boolean
  candles: KlineCandle[]
  emotionPoints: IndexDashboardEmotionPoint[]
  basisPoints: IndexDashboardBasisPoint[]
  breadthPoints: IndexBreadthPoint[]
  vixPoints: IndexVixPoint[]
  usVixPoints: IndexUsVixPoint[]
  usFearGreedPoints: IndexUsFearGreedPoint[]
  usHedgeProxyPoints: IndexUsHedgeProxyPoint[]
  earliestLoadedDate: string | null
  hasMoreHistory: boolean
  pendingWindowKey: string | null
}

const DEFAULT_INDEX_NAME = '上证指数'
const BEIJING50_INDEX_NAME = '北证50'
const CORE_INDEX_NAMES = ['上证50', '沪深300', '中证500', '中证1000'] as const
const SHARED_AUXILIARY_INDEX_NAMES = [DEFAULT_INDEX_NAME, BEIJING50_INDEX_NAME] as const
const VIX_SUPPORTED_INDEX_NAMES = ['上证50', '沪深300', '中证500'] as const
const VIX_SUPPORTED_INDEX_CODES = [
  '000016',
  'sh000016',
  '000300',
  'sh000300',
  '399300',
  'sz399300',
  '000905',
  'sh000905',
  '399905',
  'sz399905',
] as const
const DEFAULT_INDEX_BY_MARKET: Record<QuantTargetMarket, { code?: string; name: string }> = {
  cn: { name: DEFAULT_INDEX_NAME },
  hk: { code: 'HSI', name: '恒生指数' },
  us: { code: '.INX', name: '标普500指数' },
}
const FILTER_COLORS: QuantFilterColor[] = ['blue', 'red']
const INDEX_DASHBOARD_CHUNK_MONTHS = 12
const MARKET_OPTIONS: Array<{ value: QuantTargetMarket; label: string }> = [
  { value: 'cn', label: 'A股' },
  { value: 'hk', label: '港股' },
  { value: 'us', label: '美股' },
]
const DEFAULT_PARAMS: QuantIndicatorParams = {
  ma: { periods: [5, 10, 20, 60] },
  macd: { fast: 12, slow: 26, signal: 9 },
  kdj: { period: 9, kSmoothing: 3, dSmoothing: 3 },
  wr: { period: 14 },
  rsi: { period: 14 },
  boll: { period: 20, multiplier: 2 },
}

function formatDateOnly(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function monthsAgo(months: number): string {
  const value = new Date()
  value.setMonth(value.getMonth() - months)
  return formatDateOnly(value)
}

function shiftMonths(value: string, months: number): string {
  const date = new Date(`${value}T00:00:00`)
  date.setMonth(date.getMonth() + months)
  return formatDateOnly(date)
}

function shiftDays(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00`)
  date.setDate(date.getDate() + days)
  return formatDateOnly(date)
}

function mergeByTradeDate<T extends { trade_date: string }>(existing: T[], incoming: T[]) {
  const byDate = new Map<string, T>()
  for (const item of [...existing, ...incoming]) {
    byDate.set(item.trade_date, item)
  }
  return [...byDate.values()].sort((left, right) => left.trade_date.localeCompare(right.trade_date))
}

function mergeByKey<T>(existing: T[], incoming: T[], keySelector: (item: T) => string) {
  const byKey = new Map<string, T>()
  for (const item of [...existing, ...incoming]) {
    const key = keySelector(item)
    if (key) {
      byKey.set(key, item)
    }
  }
  return [...byKey.values()].sort((left, right) => keySelector(left).localeCompare(keySelector(right)))
}

function indexSupportsVix(name: string, code: string) {
  const normalizedName = String(name || '').trim()
  const normalizedCode = String(code || '').trim().toLowerCase()
  return (
    VIX_SUPPORTED_INDEX_NAMES.includes(normalizedName as (typeof VIX_SUPPORTED_INDEX_NAMES)[number]) ||
    VIX_SUPPORTED_INDEX_CODES.includes(normalizedCode as (typeof VIX_SUPPORTED_INDEX_CODES)[number])
  )
}

function resolveUsHedgeProxyScope(name: string, code: string) {
  const normalizedCode = String(code || '').trim().toUpperCase()
  if (normalizedCode === '.INX') return 'ES'
  if (normalizedCode === '.NDX') return 'NQ'
  const normalizedName = String(name || '').trim()
  if (normalizedName === '标普500指数') return 'ES'
  if (normalizedName === '纳斯达克100指数') return 'NQ'
  return ''
}

function buildDashboardChunkState(
  payload: Pick<
    IndexDashboardResponse,
    | 'market'
    | 'supports_auxiliary_panels'
    | 'candles'
    | 'emotion_points'
    | 'basis_points'
    | 'breadth_points'
    | 'vix_points'
    | 'us_vix_points'
    | 'us_fear_greed_points'
    | 'us_hedge_proxy_points'
  >,
  hasMoreHistory = true,
  pendingWindowKey: string | null = null,
): IndexDashboardChunkState {
  return {
    market: payload.market,
    supportsAuxiliaryPanels: payload.supports_auxiliary_panels,
    candles: payload.candles,
    emotionPoints: payload.emotion_points,
    basisPoints: payload.basis_points,
    breadthPoints: payload.breadth_points,
    vixPoints: payload.vix_points,
    usVixPoints: payload.us_vix_points,
    usFearGreedPoints: payload.us_fear_greed_points,
    usHedgeProxyPoints: payload.us_hedge_proxy_points,
    earliestLoadedDate: payload.candles[0]?.trade_date ?? null,
    hasMoreHistory: payload.candles.length > 0 ? hasMoreHistory : false,
    pendingWindowKey,
  }
}

function buildDashboardStateKey(market: QuantTargetMarket, code: string) {
  return `${market}:${code}`
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
    hint: 'Relative Strength',
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

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '加载失败'
}

const indexOptions = ref<MarketOption[]>([])
const indexCode = ref('')
const indexCandles = ref<KlineCandle[]>([])
const emotionPoints = ref<IndexEmotionPoint[]>([])
const futuresBasisPoints = ref<FuturesBasisPoint[]>([])
const breadthPoints = ref<IndexBreadthPoint[]>([])
const vixPoints = ref<IndexVixPoint[]>([])
const usVixPoints = ref<IndexUsVixPoint[]>([])
const usFearGreedPoints = ref<IndexUsFearGreedPoint[]>([])
const usHedgeProxyPoints = ref<IndexUsHedgeProxyPoint[]>([])
const loading = ref(false)
const loadingMoreHistory = ref(false)
const hasMoreHistory = ref(false)
const targetMarket = ref<QuantTargetMarket>('cn')
const supportsAuxiliaryPanels = ref(true)
const booting = ref(true)
const error = ref('')
const emotionLoading = ref(false)
const emotionError = ref('')
const futuresBasisLoading = ref(false)
const futuresBasisError = ref('')
const breadthLoading = ref(false)
const breadthError = ref('')
const saveName = ref('')
const saveLoading = ref(false)
const saveMessage = ref('')
const saveError = ref('')
const showParamsModal = ref(false)
const loadedStrategyId = ref<number | null>(null)
let activeDashboardToken = 0
const dashboardStatesByKey = ref<Record<string, IndexDashboardChunkState>>({})
const strategyLoadMessage = ref('')
const route = useRoute()

const appliedParams = ref<QuantIndicatorParams>(cloneParams(DEFAULT_PARAMS))
const appliedBlueFilterGroups = ref<QuantFilterGroupSet>([])
const appliedRedFilterGroups = ref<QuantFilterGroupSet>([])

const formState = reactive<QuantFormState>(buildFormState(DEFAULT_PARAMS))
const blueRuleDrafts = ref<QuantRuleGroupDraft[]>([])
const redRuleDrafts = ref<QuantRuleGroupDraft[]>([])

const selectedIndexName = computed(() => indexOptions.value.find((item) => item.code === indexCode.value)?.name ?? '')
const isCnMarket = computed(() => targetMarket.value === 'cn')
const isUsMarket = computed(() => targetMarket.value === 'us')
const supportsVixPanel = computed(() => isCnMarket.value && indexSupportsVix(selectedIndexName.value, indexCode.value))
const usHedgeProxyScope = computed(() => resolveUsHedgeProxyScope(selectedIndexName.value, indexCode.value))
const supportsUsVixPanel = computed(() => isUsMarket.value)
const supportsUsFearGreedPanel = computed(() => isUsMarket.value)
const supportsUsHedgeProxyPanel = computed(() => isUsMarket.value && Boolean(usHedgeProxyScope.value))
const quantFilterDataset = computed(() => {
  if (isCnMarket.value && supportsAuxiliaryPanels.value) {
    return buildIndexQuantFilterDataset(
      indexCandles.value,
      appliedParams.value,
      selectedIndexName.value,
      emotionPoints.value,
      futuresBasisPoints.value,
      breadthPoints.value,
      vixPoints.value,
      supportsVixPanel.value,
    )
  }
  if (isUsMarket.value) {
    return buildIndexQuantFilterDataset(
      indexCandles.value,
      appliedParams.value,
      selectedIndexName.value,
      [],
      [],
      [],
      [],
      false,
      {
        includeCnAuxiliary: false,
        includeCnVix: false,
        includeUsVix: true,
        includeUsFearGreed: true,
        includeUsHedge: supportsUsHedgeProxyPanel.value,
        usVixPoints: usVixPoints.value,
        usFearGreedPoints: usFearGreedPoints.value,
        usHedgeProxyPoints: usHedgeProxyPoints.value,
      },
    )
  }
  return buildStockQuantFilterDataset(indexCandles.value, appliedParams.value)
})
const allowedNumericFieldKeys = computed(() => numericFieldOptions.value.map((item) => item.value))
const numericFieldOptions = computed(() =>
  quantFilterDataset.value.fields
    .filter((field) =>
      (
        isCnMarket.value
          ? INDEX_QUANT_FILTER_FIELD_KEYS
          : isUsMarket.value
            ? US_INDEX_QUANT_FILTER_FIELD_KEYS
            : STOCK_QUANT_FILTER_FIELD_KEYS
      ).includes(field.key),
    )
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

const blueRuleValidation = computed(() => normalizeRuleGroups(blueRuleDrafts.value, allowedNumericFieldKeys.value))
const redRuleValidation = computed(() => normalizeRuleGroups(redRuleDrafts.value, allowedNumericFieldKeys.value))

function hasNumericFieldRules(groups: QuantFilterGroupSet, targetFields: string[]) {
  const fieldSet = new Set(targetFields)
  return groups.some((group) =>
    group.conditions.some((condition) => condition.type === 'numeric' && fieldSet.has(condition.field)),
  )
}

const unsupportedAuxiliaryRuleMessage = computed(() => {
  const blueGroups = appliedBlueFilterGroups.value
  const redGroups = appliedRedFilterGroups.value

  if (hasNumericFieldRules(blueGroups, ['vix-open', 'vix-high', 'vix-low', 'vix-close']) || hasNumericFieldRules(redGroups, ['vix-open', 'vix-high', 'vix-low', 'vix-close'])) {
    if (!isCnMarket.value) {
      return '当前市场不支持 A股 VIX 条件，请先移除相关规则后再保存。'
    }
    if (!supportsVixPanel.value) {
      return '当前指数不支持 VIX 条件，请先移除相关规则后再保存。'
    }
  }

  if (
    hasNumericFieldRules(blueGroups, ['us-vix-open', 'us-vix-high', 'us-vix-low', 'us-vix-close', 'us-fear-greed']) ||
    hasNumericFieldRules(redGroups, ['us-vix-open', 'us-vix-high', 'us-vix-low', 'us-vix-close', 'us-fear-greed'])
  ) {
    if (!isUsMarket.value) {
      return '当前市场不支持美股辅助指标条件，请先移除相关规则后再保存。'
    }
  }

  if (
    hasNumericFieldRules(blueGroups, ['us-hedge-long', 'us-hedge-short', 'us-hedge-ratio']) ||
    hasNumericFieldRules(redGroups, ['us-hedge-long', 'us-hedge-short', 'us-hedge-ratio'])
  ) {
    if (!isUsMarket.value) {
      return '当前市场不支持对冲基金代理条件，请先移除相关规则后再保存。'
    }
    if (!supportsUsHedgeProxyPanel.value) {
      return '当前指数不支持对冲基金代理条件，请先移除相关规则后再保存。'
    }
  }

  return ''
})

const canApplyParams = computed(() => Boolean(validation.value.params) && !loading.value && Boolean(indexCode.value))
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
  const groups = getRuleDraftsByColor(color)
  const targetGroup = groups.find((item) => item.id === groupId)
  if (!targetGroup) return
  targetGroup.conditions.push(createEmptyRuleConditionDraft())
}

function deleteRuleCondition(color: QuantFilterColor, groupId: string, conditionId: string) {
  const groups = getRuleDraftsByColor(color)
  const targetGroup = groups.find((item) => item.id === groupId)
  if (!targetGroup) return
  targetGroup.conditions = targetGroup.conditions.filter((item) => item.id !== conditionId)
  if (!targetGroup.conditions.length) {
    deleteRuleGroup(color, groupId)
  }
}

async function handleChartIndexSelect(nextCode: string) {
  if (!nextCode || nextCode === indexCode.value) return
  indexCode.value = nextCode
  await loadDashboardForIndex(nextCode)
}

function applyDashboardState(targetCode: string, targetName: string, state: IndexDashboardChunkState | null) {
  const nextSupportsVix = targetMarket.value === 'cn' && indexSupportsVix(targetName, targetCode)
  const nextUsHedgeScope = targetMarket.value === 'us' ? resolveUsHedgeProxyScope(targetName, targetCode) : ''
  const basisIndexNames =
    state?.supportsAuxiliaryPanels &&
    SHARED_AUXILIARY_INDEX_NAMES.includes(targetName as (typeof SHARED_AUXILIARY_INDEX_NAMES)[number])
      ? [...CORE_INDEX_NAMES]
      : [targetName]
  indexCandles.value = state?.candles ?? []
  supportsAuxiliaryPanels.value = state?.supportsAuxiliaryPanels ?? isCnMarket.value
  emotionPoints.value = supportsAuxiliaryPanels.value
    ? state?.emotionPoints.flatMap((item) =>
        basisIndexNames.map((indexName) => ({
          emotion_date: item.trade_date,
          index_name: indexName,
          emotion_value: item.value,
        })),
      ) ?? []
    : []
  futuresBasisPoints.value = supportsAuxiliaryPanels.value
    ? state?.basisPoints.flatMap((item) =>
        basisIndexNames.map((indexName) => ({
          trade_date: item.trade_date,
          index_name: indexName,
          main_basis: item.main_basis,
          month_basis: item.month_basis,
        })),
      ) ?? []
    : []
  breadthPoints.value = supportsAuxiliaryPanels.value ? state?.breadthPoints ?? [] : []
  vixPoints.value = nextSupportsVix ? state?.vixPoints ?? [] : []
  usVixPoints.value = targetMarket.value === 'us' ? state?.usVixPoints ?? [] : []
  usFearGreedPoints.value = targetMarket.value === 'us' ? state?.usFearGreedPoints ?? [] : []
  usHedgeProxyPoints.value =
    targetMarket.value === 'us' && nextUsHedgeScope ? state?.usHedgeProxyPoints ?? [] : []
  hasMoreHistory.value = state?.hasMoreHistory ?? false
  loadingMoreHistory.value = Boolean(state?.pendingWindowKey)
  if (state) {
    dashboardStatesByKey.value[buildDashboardStateKey(state.market, targetCode)] = state
  }
}

function mergeDashboardState(
  currentState: IndexDashboardChunkState,
  payload: IndexDashboardResponse,
): IndexDashboardChunkState {
  const mergedCandles = mergeByTradeDate(currentState.candles, payload.candles)
  const hasOlderHistory =
    payload.candles.length > 0 &&
    Boolean(mergedCandles[0]?.trade_date) &&
    mergedCandles[0].trade_date < (currentState.earliestLoadedDate ?? '')

  return {
    market: payload.market,
    supportsAuxiliaryPanels: payload.supports_auxiliary_panels,
    candles: mergedCandles,
    emotionPoints: mergeByTradeDate(currentState.emotionPoints, payload.emotion_points),
    basisPoints: mergeByTradeDate(currentState.basisPoints, payload.basis_points),
    breadthPoints: mergeByTradeDate(currentState.breadthPoints, payload.breadth_points),
    vixPoints: mergeByTradeDate(currentState.vixPoints, payload.vix_points),
    usVixPoints: mergeByTradeDate(currentState.usVixPoints, payload.us_vix_points),
    usFearGreedPoints: mergeByTradeDate(currentState.usFearGreedPoints, payload.us_fear_greed_points),
    usHedgeProxyPoints: mergeByKey(
      currentState.usHedgeProxyPoints,
      payload.us_hedge_proxy_points,
      (item) => String(item.release_date || ''),
    ),
    earliestLoadedDate: mergedCandles[0]?.trade_date ?? null,
    hasMoreHistory: hasOlderHistory,
    pendingWindowKey: null,
  }
}

async function loadDashboardForIndex(targetCode: string) {
  if (!targetCode) return false
  const token = ++activeDashboardToken
  const stateKey = buildDashboardStateKey(targetMarket.value, targetCode)
  const cached = dashboardStatesByKey.value[stateKey]
  if (cached) {
    applyDashboardState(targetCode, selectedIndexName.value, cached)
    return true
  }
  loading.value = true
  loadingMoreHistory.value = false
  hasMoreHistory.value = false
  error.value = ''
  emotionError.value = ''
  futuresBasisError.value = ''
  breadthError.value = ''
  emotionLoading.value = false
  futuresBasisLoading.value = false
  breadthLoading.value = false
  applyDashboardState(targetCode, selectedIndexName.value, null)
  try {
    const payload = await fetchIndexDashboard(targetCode, {
      startDate: monthsAgo(INDEX_DASHBOARD_CHUNK_MONTHS),
      mode: 'recent',
      market: targetMarket.value,
    })
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return false
    applyDashboardState(targetCode, payload.index.name, buildDashboardChunkState(payload, payload.candles.length > 0))
    if (!payload.candles.length) {
      error.value = `${payload.index.name}暂无指数行情数据`
    }
    return true
  } catch (loadError) {
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return false
    error.value = getErrorMessage(loadError)
    return false
  } finally {
    if (token === activeDashboardToken && targetCode === indexCode.value) {
      loading.value = false
    }
  }
}

async function loadMoreDashboardHistory() {
  const targetCode = indexCode.value
  if (!targetCode) return
  const currentState = dashboardStatesByKey.value[buildDashboardStateKey(targetMarket.value, targetCode)]
  if (!currentState?.earliestLoadedDate || !currentState.hasMoreHistory || currentState.pendingWindowKey) {
    return
  }

  const token = activeDashboardToken
  const endDate = shiftDays(currentState.earliestLoadedDate, -1)
  const startDate = shiftMonths(endDate, -INDEX_DASHBOARD_CHUNK_MONTHS)
  const windowKey = `${startDate}:${endDate}`
  applyDashboardState(targetCode, selectedIndexName.value, {
    ...currentState,
    pendingWindowKey: windowKey,
  })

  try {
    const payload = await fetchIndexDashboard(targetCode, {
      startDate,
      endDate,
      mode: 'recent',
      market: targetMarket.value,
    })
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return
    applyDashboardState(targetCode, payload.index.name, mergeDashboardState(currentState, payload))
  } catch (loadError) {
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return
    console.error(loadError)
    applyDashboardState(targetCode, selectedIndexName.value, {
      ...currentState,
      pendingWindowKey: null,
    })
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

function buildStrategyPayload() {
  return {
    name: saveName.value.trim(),
    notes: '',
    strategy_engine: 'snapshot' as const,
    sequence_mode: 'single_target' as const,
    strategy_type: 'index' as const,
    target_market: targetMarket.value,
    target_code: indexCode.value,
    target_name: selectedIndexName.value,
    indicator_params: appliedParams.value,
    buy_sequence_groups: [],
    sell_sequence_groups: [],
    scan_trade_config: {
      initial_capital: 1_000_000,
      buy_amount_per_event: 10_000,
      buy_offset_trading_days: 1,
      sell_offset_trading_days: 2,
      buy_price_basis: 'open' as const,
      sell_price_basis: 'open' as const,
    },
    blue_filter_groups: appliedBlueFilterGroups.value,
    red_filter_groups: appliedRedFilterGroups.value,
    blue_filters: {},
    red_filters: {},
    blue_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
    red_boll_filter: { gt: null, lt: null, intraday_gt: null, intraday_lt: null },
    signal_buy_color: 'blue' as const,
    signal_sell_color: 'red' as const,
    purple_conflict_mode: 'sell_first' as const,
    start_date: null,
    scan_start_date: null,
    scan_end_date: null,
    buy_position_pct: 1,
    sell_position_pct: 1,
    execution_price_mode: 'next_open' as const,
  }
}

async function saveStrategy(asNew = false) {
  saveError.value = ''
  saveMessage.value = ''
  if (unsupportedAuxiliaryRuleMessage.value) {
    saveError.value = unsupportedAuxiliaryRuleMessage.value
    return
  }
  if (!saveName.value.trim()) {
    saveError.value = '请先填写策略名称'
    return
  }
  if (!indexCode.value || !selectedIndexName.value) {
    saveError.value = '当前没有可保存的指数标的'
    return
  }
  saveLoading.value = true
  try {
    const result = await createQuantStrategy(buildStrategyPayload())
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
    await saveStrategy(true)
    return
  }
  saveError.value = ''
  saveMessage.value = ''
  if (unsupportedAuxiliaryRuleMessage.value) {
    saveError.value = unsupportedAuxiliaryRuleMessage.value
    return
  }
  if (!saveName.value.trim()) {
    saveError.value = '请先填写策略名称'
    return
  }
  if (!indexCode.value || !selectedIndexName.value) {
    saveError.value = '当前没有可保存的指数标的'
    return
  }
  saveLoading.value = true
  try {
    const result = await updateQuantStrategy(loadedStrategyId.value, buildStrategyPayload())
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
  await saveStrategy(true)
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

async function loadIndexOptionsForMarket(
  market: QuantTargetMarket,
  preferredCode?: string | null,
  fallbackToDefault = true,
) {
  const options = await fetchIndexOptions(market)
  indexOptions.value = options
  const normalizedPreferredCode = String(preferredCode || '').trim()
  if (normalizedPreferredCode && options.some((item) => item.code === normalizedPreferredCode)) {
    indexCode.value = normalizedPreferredCode
    return
  }
  if (!fallbackToDefault) {
    indexCode.value = ''
    return
  }
  const preferred = DEFAULT_INDEX_BY_MARKET[market]
  const defaultOption = options.find((item) => preferred.code ? item.code === preferred.code : item.name === preferred.name)
    ?? options.find((item) => item.name === preferred.name)
    ?? options[0]
  indexCode.value = defaultOption?.code ?? ''
}

async function switchTargetMarket(nextMarket: QuantTargetMarket, preferredCode?: string | null) {
  targetMarket.value = nextMarket
  await loadIndexOptionsForMarket(nextMarket, preferredCode)
  if (!indexCode.value) {
    indexCandles.value = []
    emotionPoints.value = []
    futuresBasisPoints.value = []
    breadthPoints.value = []
    vixPoints.value = []
    usVixPoints.value = []
    usFearGreedPoints.value = []
    usHedgeProxyPoints.value = []
    supportsAuxiliaryPanels.value = nextMarket === 'cn'
    error.value = '当前市场暂无可用指数'
    return
  }
  await loadDashboardForIndex(indexCode.value)
}

async function hydrateStrategyFromRoute() {
  const strategyId = getStrategyIdFromRoute()
  if (!strategyId) return

  strategyLoadMessage.value = ''
  error.value = ''
  saveError.value = ''

  try {
    const strategy = await fetchQuantStrategy(strategyId)
    if (strategy.strategy_engine !== 'snapshot' || strategy.strategy_type !== 'index') {
      error.value = '当前策略不是指数策略，无法加载到指数分析页面'
      return
    }

    const strategyMarket = (strategy.target_market ?? 'cn') as QuantTargetMarket
    targetMarket.value = strategyMarket
    await loadIndexOptionsForMarket(strategyMarket, strategy.target_code, false)
    if (!indexOptions.value.some((item) => item.code === strategy.target_code)) {
      error.value = '当前市场暂无可用指数'
      return
    }

    indexCode.value = strategy.target_code
    const loaded = await loadDashboardForIndex(strategy.target_code)
    if (!loaded) {
      error.value = error.value || '策略对应指数数据加载失败'
      return
    }

    applyStrategyConfig(strategy)
    strategyLoadMessage.value = `已加载策略：${strategy.name}`
  } catch (loadError) {
    error.value = getErrorMessage(loadError)
  }
}

async function initializePage() {
  booting.value = true
  error.value = ''
  try {
    await loadIndexOptionsForMarket(targetMarket.value)
    if (!indexCode.value) {
      error.value = '当前市场暂无可用指数'
      return
    }
    await loadDashboardForIndex(indexCode.value)
  } catch (loadError) {
    error.value = getErrorMessage(loadError)
  } finally {
    booting.value = false
  }
}

onMounted(async () => {
  await initializePage()
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
</script>

<template>
  <p v-if="error" class="banner-error">{{ error }}</p>
  <p v-else-if="strategyLoadMessage" class="muted">{{ strategyLoadMessage }}</p>
  <div v-if="showParamsModal" class="quant-modal-backdrop" @click="closeParamsModal"></div>
  <div class="quant-body">
    <div class="quant-content-column">
      <section v-if="showParamsModal" class="card quant-params-card quant-modal quant-param-modal">
        <div class="quant-page-head">
          <div>
            <h3>指数参数</h3>
            <p class="muted">主图支持均线 / BOLL 切换，副图会联动更新对应指标和筛选结果。</p>
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
        <p v-if="Object.keys(validation.errors).length" class="quant-form-hint error">参数存在未通过校验的项目，修正后才能应用。</p>
        <p v-else class="quant-form-hint muted">参数会同时影响图表展示和右侧筛选逻辑。</p>
      </section>
      <section class="card quant-market-switch-card">
        <div class="progress-section-head">
          <div class="progress-section-copy">
            <h3>市场切换</h3>
            <p class="muted">
              {{ targetMarket === 'cn' ? 'A股指数保留完整量化辅助指标。' : '港股 / 美股指数只展示基于自身 K 线的量化指标。' }}
            </p>
          </div>
          <div class="quant-subnav">
            <button
              v-for="item in MARKET_OPTIONS"
              :key="item.value"
              type="button"
              class="quant-subnav-link"
              :class="{ active: targetMarket === item.value }"
              @click="switchTargetMarket(item.value)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
      </section>

      <section class="card quant-chart-card">
        <QuantIndexChart
          :candles="indexCandles"
          :emotion-points="emotionPoints"
          :emotion-loading="emotionLoading"
          :emotion-error-message="emotionError"
          :futures-basis-points="futuresBasisPoints"
          :futures-basis-loading="futuresBasisLoading"
          :futures-basis-error-message="futuresBasisError"
          :breadth-points="breadthPoints"
          :breadth-loading="breadthLoading"
          :breadth-error-message="breadthError"
          :vix-points="vixPoints"
          :supports-vix-panel="supportsVixPanel"
          :us-vix-points="usVixPoints"
          :us-fear-greed-points="usFearGreedPoints"
          :us-hedge-proxy-points="usHedgeProxyPoints"
          :supports-us-vix-panel="supportsUsVixPanel"
          :supports-us-fear-greed-panel="supportsUsFearGreedPanel"
          :supports-us-hedge-proxy-panel="supportsUsHedgeProxyPanel"
          :highlight-bands="highlightBands"
          :has-more-history="hasMoreHistory"
          :loading-more-history="loadingMoreHistory"
          :market-options="indexOptions"
          :symbol-name="selectedIndexName"
          :symbol-code="indexCode"
          :params="appliedParams"
          :supports-auxiliary-panels="supportsAuxiliaryPanels"
          :loading="loading || booting"
          :default-visible-days="90"
          @select-index="handleChartIndexSelect"
          @open-settings="openParamsModal"
          @request-more-history="loadMoreDashboardHistory"
        />
      </section>
    </div>

    <aside class="quant-filter-sidebar">
      <section class="card quant-filter-card">
        <div class="quant-filter-head">
          <div>
            <h3>指标筛选</h3>
            <p class="muted">当前指数：{{ selectedIndexName || '未选择' }}</p>
          </div>
          <div class="quant-filter-counts">
            <span class="quant-filter-count quant-filter-count-blue">蓝 {{ highlightSummary.blue }}</span>
            <span class="quant-filter-count quant-filter-count-red">红 {{ highlightSummary.red }}</span>
            <span class="quant-filter-count quant-filter-count-purple">紫 {{ highlightSummary.purple }}</span>
          </div>
        </div>
        <p class="quant-filter-hint muted">规则组内全部满足，命中任一规则组即触发对应颜色；同日蓝红同时命中会显示为紫色。</p>

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
            <span class="quant-field-label">保存当前指数策略</span>
            <input v-model="saveName" class="input" placeholder="输入策略名称" />
          </label>
          <p v-if="unsupportedAuxiliaryRuleMessage" class="error">{{ unsupportedAuxiliaryRuleMessage }}</p>
          <p v-else-if="saveError" class="error">{{ saveError }}</p>
          <p v-else-if="saveMessage" class="muted">{{ saveMessage }}</p>
        </section>

        <div class="quant-filter-footer">
          <button class="btn primary" :disabled="!canApplyFilters" @click="applyFilters">确定</button>
          <button class="btn" @click="clearFilters">清空筛选</button>
          <button class="btn" :disabled="saveLoading || !indexCode || Boolean(unsupportedAuxiliaryRuleMessage)" @click="saveCurrentStrategy">
            {{ saveLoading ? '保存中...' : loadedStrategyId ? '更新当前策略' : '保存筛选' }}
          </button>
          <button class="btn" :disabled="saveLoading || !indexCode || Boolean(unsupportedAuxiliaryRuleMessage)" @click="saveAsNewStrategy">
            {{ saveLoading ? '保存中...' : '另存为新策略' }}
          </button>
        </div>
      </section>
    </aside>
  </div>
</template>

