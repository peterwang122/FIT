<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  createQuantStrategy,
  fetchIndexBreadth,
  fetchIndexEmotions,
  fetchIndexFuturesBasis,
  fetchIndexKline,
  fetchIndexOptions,
} from '../api/stocks'
import QuantIndexChart from '../components/QuantIndexChart.vue'
import type {
  QuantFilterApplied,
  QuantFilterDraft,
  QuantFilterFieldKey,
  QuantFilterGroupKey,
  QuantHighlightBand,
  QuantIndicatorParams,
  QuantSavedBollFilter,
} from '../types/quant'
import type { FuturesBasisPoint, IndexBreadthPoint, IndexEmotionPoint, KlineCandle, MarketOption } from '../types/stock'
import { INDEX_QUANT_FILTER_FIELD_KEYS, buildIndexQuantFilterDataset, createEmptyQuantFilterDraft } from '../utils/quantIndicators'

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
  bollPeriod: string
  bollMultiplier: string
}

type QuantFormErrors = Partial<Record<keyof QuantFormState, string>>
type QuantFilterErrors = Partial<Record<QuantFilterFieldKey, string>>
type QuantFilterColor = 'blue' | 'red'
type QuantBollFilterOption = '' | 'boll-upper' | 'boll-middle' | 'boll-lower'

const DEFAULT_INDEX_NAME = '上证指数'
const FILTER_COLORS: QuantFilterColor[] = ['blue', 'red']
const FILTER_GROUP_ORDER: QuantFilterGroupKey[] = ['emotion', 'basis', 'breadth', 'wr', 'macd', 'kdj']
const FILTER_GROUP_TITLE: Record<QuantFilterGroupKey, string> = {
  emotion: '情绪指标',
  basis: '期现差',
  breadth: '涨跌家数',
  wr: 'WR',
  macd: 'MACD',
  kdj: 'KDJ',
  ma: 'MA',
  boll: 'BOLL',
}
const BOLL_FILTER_OPTIONS: Array<{ value: Exclude<QuantBollFilterOption, ''>; label: string }> = [
  { value: 'boll-upper', label: 'BOLL上轨' },
  { value: 'boll-middle', label: 'BOLL中轨' },
  { value: 'boll-lower', label: 'BOLL下轨' },
]
const DEFAULT_PARAMS: QuantIndicatorParams = {
  ma: { periods: [5, 10, 20, 60] },
  macd: { fast: 12, slow: 26, signal: 9 },
  kdj: { period: 9, kSmoothing: 3, dSmoothing: 3 },
  wr: { period: 14 },
  boll: { period: 20, multiplier: 2 },
}
const PARAM_GROUPS: Array<{
  key: 'ma' | 'macd' | 'kdj' | 'wr' | 'boll'
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
    bollPeriod: String(params.boll.period),
    bollMultiplier: String(params.boll.multiplier),
  }
}

function createEmptySavedBollFilter(): QuantSavedBollFilter {
  return { gt: null, lt: null }
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

function parseOptionalNumber(label: string, rawValue: string) {
  if (!rawValue.trim()) return { value: null, error: '' }
  const parsed = Number(rawValue.trim())
  if (!Number.isFinite(parsed)) return { value: null, error: `${label}必须是有效数字` }
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
const loading = ref(false)
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

const appliedParams = ref<QuantIndicatorParams>(cloneParams(DEFAULT_PARAMS))
const appliedBlueFilters = ref<QuantFilterApplied>({})
const appliedRedFilters = ref<QuantFilterApplied>({})
const appliedBlueBollFilter = ref<QuantSavedBollFilter>(createEmptySavedBollFilter())
const appliedRedBollFilter = ref<QuantSavedBollFilter>(createEmptySavedBollFilter())

const formState = reactive<QuantFormState>(buildFormState(DEFAULT_PARAMS))
const blueFilterDraft = reactive<QuantFilterDraft>(createEmptyQuantFilterDraft(INDEX_QUANT_FILTER_FIELD_KEYS))
const redFilterDraft = reactive<QuantFilterDraft>(createEmptyQuantFilterDraft(INDEX_QUANT_FILTER_FIELD_KEYS))
const blueBollFilterDraft = reactive({ gt: '' as QuantBollFilterOption, lt: '' as QuantBollFilterOption })
const redBollFilterDraft = reactive({ gt: '' as QuantBollFilterOption, lt: '' as QuantBollFilterOption })

const selectedIndexName = computed(() => indexOptions.value.find((item) => item.code === indexCode.value)?.name ?? '')
const quantFilterDataset = computed(() =>
  buildIndexQuantFilterDataset(
    indexCandles.value,
    appliedParams.value,
    selectedIndexName.value,
    emotionPoints.value,
    futuresBasisPoints.value,
    breadthPoints.value,
  ),
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
  const bollPeriod = parsePositiveInteger('BOLL 周期', formState.bollPeriod)
  const bollMultiplier = parsePositiveNumber('BOLL 倍数', formState.bollMultiplier)
  ;[
    ['ma1', ma1.error], ['ma2', ma2.error], ['ma3', ma3.error], ['ma4', ma4.error],
    ['macdFast', macdFast.error], ['macdSlow', macdSlow.error], ['macdSignal', macdSignal.error],
    ['kdjPeriod', kdjPeriod.error], ['kdjKSmoothing', kdjKSmoothing.error], ['kdjDSmoothing', kdjDSmoothing.error],
    ['wrPeriod', wrPeriod.error], ['bollPeriod', bollPeriod.error], ['bollMultiplier', bollMultiplier.error],
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
      boll: { period: bollPeriod.value as number, multiplier: bollMultiplier.value as number },
    } satisfies QuantIndicatorParams,
  }
})

function validateFilterDraft(draft: QuantFilterDraft) {
  const errors: QuantFilterErrors = {}
  const parsed: QuantFilterApplied = {}
  const labelByKey = new Map(quantFilterDataset.value.fields.map((field) => [field.key, field.label]))
  INDEX_QUANT_FILTER_FIELD_KEYS.forEach((key) => {
    const label = labelByKey.get(key) ?? key
    const gt = parseOptionalNumber(`${label}大于`, draft[key].gt)
    const lt = parseOptionalNumber(`${label}小于`, draft[key].lt)
    const messages = [gt.error, lt.error].filter(Boolean)
    if (messages.length) {
      errors[key] = messages.join('，')
      return
    }
    if (gt.value !== null || lt.value !== null) {
      parsed[key] = { gt: gt.value, lt: lt.value }
    }
  })
  return { errors, applied: parsed }
}

function validateBollDraft(draft: { gt: QuantBollFilterOption; lt: QuantBollFilterOption }) {
  const validValues = new Set(BOLL_FILTER_OPTIONS.map((item) => item.value))
  return {
    error:
      (draft.gt && !validValues.has(draft.gt as Exclude<QuantBollFilterOption, ''>)) ||
      (draft.lt && !validValues.has(draft.lt as Exclude<QuantBollFilterOption, ''>))
        ? 'BOLL 条件无效'
        : '',
    applied: {
      gt: draft.gt || null,
      lt: draft.lt || null,
    } satisfies QuantSavedBollFilter,
  }
}

const blueValidation = computed(() => validateFilterDraft(blueFilterDraft))
const redValidation = computed(() => validateFilterDraft(redFilterDraft))
const blueBollValidation = computed(() => validateBollDraft(blueBollFilterDraft))
const redBollValidation = computed(() => validateBollDraft(redBollFilterDraft))
const canApplyParams = computed(() => Boolean(validation.value.params) && !loading.value && Boolean(indexCode.value))
const canApplyFilters = computed(
  () => !loading.value && !booting.value && !Object.keys(blueValidation.value.errors).length && !Object.keys(redValidation.value.errors).length && !blueBollValidation.value.error && !redBollValidation.value.error,
)
const filterGroups = computed(() =>
  FILTER_GROUP_ORDER.map((groupKey) => ({
    key: groupKey,
    title: FILTER_GROUP_TITLE[groupKey],
    fields: quantFilterDataset.value.fields.filter((field) => field.group === groupKey),
  })).filter((group) => group.fields.length),
)
const highlightBands = computed<QuantHighlightBand[]>(() => {
  const snapshots = quantFilterDataset.value.snapshots
  const blueDates = new Set<string>()
  const redDates = new Set<string>()
  const matchNumeric = (snapshot: (typeof snapshots)[number], entries: Array<[string, (typeof appliedBlueFilters.value)[QuantFilterFieldKey]]>) =>
    entries.every(([key, threshold]) => {
      const value = snapshot.values[key as QuantFilterFieldKey]
      if (value === null || value === undefined) return false
      if (threshold?.gt !== null && threshold?.gt !== undefined && !(value > threshold.gt)) return false
      if (threshold?.lt !== null && threshold?.lt !== undefined && !(value < threshold.lt)) return false
      return true
    })
  const matchBoll = (snapshot: (typeof snapshots)[number], filter: QuantSavedBollFilter) => {
    if (!filter.gt && !filter.lt) return true
    if (snapshot.close === null || snapshot.close === undefined) return false
    if (filter.gt) {
      const value = snapshot.values[filter.gt]
      if (value === null || value === undefined || !(snapshot.close > value)) return false
    }
    if (filter.lt) {
      const value = snapshot.values[filter.lt]
      if (value === null || value === undefined || !(snapshot.close < value)) return false
    }
    return true
  }
  if (Object.keys(appliedBlueFilters.value).length || appliedBlueBollFilter.value.gt || appliedBlueBollFilter.value.lt) {
    snapshots.forEach((snapshot) => {
      if (matchNumeric(snapshot, Object.entries(appliedBlueFilters.value)) && matchBoll(snapshot, appliedBlueBollFilter.value)) {
        blueDates.add(snapshot.tradeDate)
      }
    })
  }
  if (Object.keys(appliedRedFilters.value).length || appliedRedBollFilter.value.gt || appliedRedBollFilter.value.lt) {
    snapshots.forEach((snapshot) => {
      if (matchNumeric(snapshot, Object.entries(appliedRedFilters.value)) && matchBoll(snapshot, appliedRedBollFilter.value)) {
        redDates.add(snapshot.tradeDate)
      }
    })
  }
  return snapshots.reduce<QuantHighlightBand[]>((bands, snapshot) => {
    const isBlue = blueDates.has(snapshot.tradeDate)
    const isRed = redDates.has(snapshot.tradeDate)
    if (isBlue && isRed) bands.push({ tradeDate: snapshot.tradeDate, color: 'purple' })
    else if (isBlue) bands.push({ tradeDate: snapshot.tradeDate, color: 'blue' })
    else if (isRed) bands.push({ tradeDate: snapshot.tradeDate, color: 'red' })
    return bands
  }, [])
})
const highlightSummary = computed(() => ({
  blue: highlightBands.value.filter((item) => item.color === 'blue').length,
  red: highlightBands.value.filter((item) => item.color === 'red').length,
  purple: highlightBands.value.filter((item) => item.color === 'purple').length,
}))

function getDraftByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueFilterDraft : redFilterDraft
}
function getValidationByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueValidation.value : redValidation.value
}
function getBollDraftByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueBollFilterDraft : redBollFilterDraft
}
function getBollValidationByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueBollValidation.value : redBollValidation.value
}
async function handleChartIndexSelect(nextCode: string) {
  if (!nextCode || nextCode === indexCode.value) return
  indexCode.value = nextCode
  await loadSelectedIndexKline()
}
async function loadSelectedIndexKline() {
  if (!indexCode.value) return
  loading.value = true
  error.value = ''
  try {
    indexCandles.value = await fetchIndexKline(indexCode.value)
  } catch (loadError) {
    indexCandles.value = []
    error.value = getErrorMessage(loadError)
  } finally {
    loading.value = false
  }
}
async function loadEmotionPoints() {
  emotionLoading.value = true
  emotionError.value = ''
  try { emotionPoints.value = await fetchIndexEmotions() } catch (loadError) { emotionPoints.value = []; emotionError.value = getErrorMessage(loadError) } finally { emotionLoading.value = false }
}
async function loadFuturesBasisPoints() {
  futuresBasisLoading.value = true
  futuresBasisError.value = ''
  try { futuresBasisPoints.value = await fetchIndexFuturesBasis() } catch (loadError) { futuresBasisPoints.value = []; futuresBasisError.value = getErrorMessage(loadError) } finally { futuresBasisLoading.value = false }
}
async function loadBreadthPoints() {
  breadthLoading.value = true
  breadthError.value = ''
  try { breadthPoints.value = await fetchIndexBreadth() } catch (loadError) { breadthPoints.value = []; breadthError.value = getErrorMessage(loadError) } finally { breadthLoading.value = false }
}
function applyParams() {
  if (validation.value.params) appliedParams.value = cloneParams(validation.value.params)
}
function resetParams() {
  Object.assign(formState, buildFormState(DEFAULT_PARAMS))
  appliedParams.value = cloneParams(DEFAULT_PARAMS)
}
function applyFilters() {
  if (!canApplyFilters.value) return
  appliedBlueFilters.value = blueValidation.value.applied
  appliedRedFilters.value = redValidation.value.applied
  appliedBlueBollFilter.value = { ...blueBollValidation.value.applied }
  appliedRedBollFilter.value = { ...redBollValidation.value.applied }
}
function clearFilters() {
  FILTER_COLORS.forEach((color) => {
    const draft = getDraftByColor(color)
    const bollDraft = getBollDraftByColor(color)
    INDEX_QUANT_FILTER_FIELD_KEYS.forEach((key) => {
      draft[key].gt = ''
      draft[key].lt = ''
    })
    bollDraft.gt = ''
    bollDraft.lt = ''
  })
  appliedBlueFilters.value = {}
  appliedRedFilters.value = {}
  appliedBlueBollFilter.value = createEmptySavedBollFilter()
  appliedRedBollFilter.value = createEmptySavedBollFilter()
}
async function saveStrategy() {
  saveError.value = ''
  saveMessage.value = ''
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
    const result = await createQuantStrategy({
      name: saveName.value.trim(),
      strategy_type: 'index',
      target_code: indexCode.value,
      target_name: selectedIndexName.value,
      indicator_params: appliedParams.value,
      blue_filters: appliedBlueFilters.value,
      red_filters: appliedRedFilters.value,
      blue_boll_filter: appliedBlueBollFilter.value,
      red_boll_filter: appliedRedBollFilter.value,
      signal_buy_color: 'blue',
      signal_sell_color: 'red',
      purple_conflict_mode: 'sell_first',
      start_date: null,
      buy_position_pct: 1,
      sell_position_pct: 1,
      execution_price_mode: 'next_open',
    })
    saveMessage.value = `已保存策略：${result.name}`
  } catch (saveErr) {
    saveError.value = getErrorMessage(saveErr)
  } finally {
    saveLoading.value = false
  }
}
async function initializePage() {
  booting.value = true
  error.value = ''
  try {
    const [options] = await Promise.all([fetchIndexOptions(), loadEmotionPoints(), loadFuturesBasisPoints(), loadBreadthPoints()])
    indexOptions.value = options
    indexCode.value = (options.find((item) => item.name === DEFAULT_INDEX_NAME) ?? options[0])?.code ?? ''
    if (!indexCode.value) {
      error.value = '暂无可用的指数选项'
      return
    }
    await loadSelectedIndexKline()
  } catch (loadError) {
    error.value = getErrorMessage(loadError)
  } finally {
    booting.value = false
  }
}
onMounted(initializePage)
</script>

<template>
  <p v-if="error" class="banner-error">{{ error }}</p>
  <div class="quant-body">
    <div class="quant-content-column">
      <section class="card quant-params-card">
        <div class="quant-page-head">
          <div>
            <h3>指数参数</h3>
            <p class="muted">主图支持均线 / BOLL 切换，副图同步展示情绪、期现差与上涨家数百分比。</p>
          </div>
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
          :highlight-bands="highlightBands"
          :market-options="indexOptions"
          :symbol-name="selectedIndexName"
          :symbol-code="indexCode"
          :params="appliedParams"
          :loading="loading || booting"
          :default-visible-days="90"
          @select-index="handleChartIndexSelect"
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
        <p class="quant-filter-hint muted">蓝色和红色各自独立求交集；同一天同时命中两套条件时会显示为紫色。</p>

        <div class="quant-filter-sections">
          <section v-for="color in FILTER_COLORS" :key="color" class="quant-filter-section" :class="`quant-filter-section-${color}`">
            <div class="quant-filter-section-head">
              <h4>{{ color === 'blue' ? '蓝色筛选' : '红色筛选' }}</h4>
              <span class="quant-filter-section-badge">{{ color === 'blue' ? '命中刷蓝色' : '命中刷红色' }}</span>
            </div>

            <div class="quant-filter-groups">
              <section v-for="group in filterGroups" :key="`${color}-${group.key}`" class="quant-filter-group">
                <div class="quant-filter-group-head">
                  <h4>{{ group.title }}</h4>
                  <div class="quant-filter-header-row">
                    <span>指标</span>
                    <span>大于</span>
                    <span>小于</span>
                  </div>
                </div>

                <div v-for="field in group.fields" :key="`${color}-${field.key}`" class="quant-filter-row">
                  <div class="quant-filter-row-grid">
                    <div class="quant-filter-row-label">{{ field.label }}</div>
                    <input v-model="getDraftByColor(color)[field.key].gt" class="input quant-filter-input" inputmode="decimal" placeholder="大于" />
                    <input v-model="getDraftByColor(color)[field.key].lt" class="input quant-filter-input" inputmode="decimal" placeholder="小于" />
                  </div>
                  <p v-if="getValidationByColor(color).errors[field.key]" class="quant-filter-row-error">
                    {{ getValidationByColor(color).errors[field.key] }}
                  </p>
                </div>
              </section>

              <section class="quant-filter-group">
                <div class="quant-filter-group-head">
                  <h4>BOLL</h4>
                  <div class="quant-filter-header-row">
                    <span>指标</span>
                    <span>大于</span>
                    <span>小于</span>
                  </div>
                </div>
                <div class="quant-filter-row">
                  <div class="quant-filter-row-grid">
                    <div class="quant-filter-row-label">收盘价相对 BOLL</div>
                    <select v-model="getBollDraftByColor(color).gt" class="input quant-filter-input">
                      <option value="">不设置</option>
                      <option v-for="option in BOLL_FILTER_OPTIONS" :key="`${color}-gt-${option.value}`" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                    <select v-model="getBollDraftByColor(color).lt" class="input quant-filter-input">
                      <option value="">不设置</option>
                      <option v-for="option in BOLL_FILTER_OPTIONS" :key="`${color}-lt-${option.value}`" :value="option.value">
                        {{ option.label }}
                      </option>
                    </select>
                  </div>
                  <p v-if="getBollValidationByColor(color).error" class="quant-filter-row-error">
                    {{ getBollValidationByColor(color).error }}
                  </p>
                </div>
              </section>
            </div>
          </section>
        </div>

        <section class="quant-save-box">
          <label class="quant-field">
            <span class="quant-field-label">保存当前指数策略</span>
            <input v-model="saveName" class="input" placeholder="输入策略名称" />
          </label>
          <p v-if="saveError" class="error">{{ saveError }}</p>
          <p v-else-if="saveMessage" class="muted">{{ saveMessage }}</p>
        </section>

        <div class="quant-filter-footer">
          <button class="btn primary" :disabled="!canApplyFilters" @click="applyFilters">确定</button>
          <button class="btn" @click="clearFilters">清空筛选</button>
          <button class="btn" :disabled="saveLoading || !indexCode" @click="saveStrategy">{{ saveLoading ? '保存中...' : '保存筛选' }}</button>
        </div>
      </section>
    </aside>
  </div>
</template>
