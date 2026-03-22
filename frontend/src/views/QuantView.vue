<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { fetchIndexEmotions, fetchIndexFuturesBasis, fetchIndexKline, fetchIndexOptions } from '../api/stocks'
import AppSidebar from '../components/AppSidebar.vue'
import QuantIndexChart from '../components/QuantIndexChart.vue'
import type {
  QuantFilterApplied,
  QuantFilterDraft,
  QuantFilterFieldKey,
  QuantFilterGroupKey,
  QuantHighlightBand,
  QuantIndicatorParams,
} from '../types/quant'
import type { FuturesBasisPoint, IndexEmotionPoint, KlineCandle, MarketOption } from '../types/stock'
import {
  QUANT_FILTER_FIELD_KEYS,
  buildQuantFilterDataset,
  createEmptyQuantFilterDraft,
} from '../utils/quantIndicators'

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
type QuantBollFilterAppliedOption = Exclude<QuantBollFilterOption, ''>
type QuantBollFilterInput = { gt: QuantBollFilterOption; lt: QuantBollFilterOption }
type QuantBollFilterApplied = { gt: QuantBollFilterAppliedOption | null; lt: QuantBollFilterAppliedOption | null }
type QuantSpecialFilterErrors = { boll: string }
type QuantSpecialFilterValidation = {
  errors: QuantSpecialFilterErrors
  boll: QuantBollFilterApplied
}
const FILTER_COLORS: QuantFilterColor[] = ['blue', 'red']
const BOLL_FILTER_OPTIONS: Array<{ value: QuantBollFilterAppliedOption; label: string }> = [
  { value: 'boll-upper', label: 'BOLL上轨' },
  { value: 'boll-middle', label: 'BOLL中轨' },
  { value: 'boll-lower', label: 'BOLL下轨' },
]

const DEFAULT_INDEX_NAME = '上证指数'
const DEFAULT_PARAMS: QuantIndicatorParams = {
  ma: {
    periods: [5, 10, 20, 60],
  },
  macd: {
    fast: 12,
    slow: 26,
    signal: 9,
  },
  kdj: {
    period: 9,
    kSmoothing: 3,
    dSmoothing: 3,
  },
  wr: {
    period: 14,
  },
  boll: {
    period: 20,
    multiplier: 2,
  },
}

const FILTER_GROUP_ORDER: QuantFilterGroupKey[] = ['emotion', 'basis', 'wr', 'macd', 'kdj']
const FILTER_GROUP_TITLE: Record<QuantFilterGroupKey, string> = {
  emotion: '情绪指标',
  basis: '期现差',
  wr: 'WR',
  macd: 'MACD',
  kdj: 'KDJ',
  ma: 'MA',
  boll: 'BOLL',
}

function cloneParams(params: QuantIndicatorParams): QuantIndicatorParams {
  return {
    ma: {
      periods: [...params.ma.periods] as [number, number, number, number],
    },
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

function createEmptyBollFilterInput(): QuantBollFilterInput {
  return {
    gt: '',
    lt: '',
  }
}

function createEmptyBollFilterApplied(): QuantBollFilterApplied {
  return {
    gt: null,
    lt: null,
  }
}

function parsePositiveInteger(label: string, rawValue: string) {
  const value = rawValue.trim()
  if (!value) {
    return { value: null, error: `${label}不能为空` }
  }

  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed <= 0) {
    return { value: null, error: `${label}需为正整数` }
  }

  return { value: parsed, error: '' }
}

function parsePositiveNumber(label: string, rawValue: string) {
  const value = rawValue.trim()
  if (!value) {
    return { value: null, error: `${label}不能为空` }
  }

  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return { value: null, error: `${label}需为大于 0 的数值` }
  }

  return { value: parsed, error: '' }
}

function parseOptionalNumber(label: string, rawValue: string) {
  const value = rawValue.trim()
  if (!value) {
    return { value: null, error: '' }
  }

  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return { value: null, error: `${label}必须是有效数字` }
  }

  return { value: parsed, error: '' }
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : '加载数据失败'
}

const indexOptions = ref<MarketOption[]>([])
const indexCode = ref('')
const indexCandles = ref<KlineCandle[]>([])
const emotionPoints = ref<IndexEmotionPoint[]>([])
const futuresBasisPoints = ref<FuturesBasisPoint[]>([])
const loading = ref(false)
const booting = ref(true)
const error = ref('')
const emotionLoading = ref(false)
const emotionError = ref('')
const futuresBasisLoading = ref(false)
const futuresBasisError = ref('')
const appliedParams = ref<QuantIndicatorParams>(cloneParams(DEFAULT_PARAMS))
const appliedBlueFilters = ref<QuantFilterApplied>({})
const appliedRedFilters = ref<QuantFilterApplied>({})
const formState = reactive<QuantFormState>(buildFormState(DEFAULT_PARAMS))
const blueFilterDraft = reactive<QuantFilterDraft>(createEmptyQuantFilterDraft())
const redFilterDraft = reactive<QuantFilterDraft>(createEmptyQuantFilterDraft())
const blueBollFilterDraft = reactive<QuantBollFilterInput>(createEmptyBollFilterInput())
const redBollFilterDraft = reactive<QuantBollFilterInput>(createEmptyBollFilterInput())
const appliedBlueBollFilter = ref<QuantBollFilterApplied>(createEmptyBollFilterApplied())
const appliedRedBollFilter = ref<QuantBollFilterApplied>(createEmptyBollFilterApplied())

const selectedIndexName = computed(
  () => indexOptions.value.find((item) => item.code === indexCode.value)?.name ?? '',
)

const quantFilterDataset = computed(() =>
  buildQuantFilterDataset(
    indexCandles.value,
    appliedParams.value,
    selectedIndexName.value,
    emotionPoints.value,
    futuresBasisPoints.value,
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

  if (ma1.error) errors.ma1 = ma1.error
  if (ma2.error) errors.ma2 = ma2.error
  if (ma3.error) errors.ma3 = ma3.error
  if (ma4.error) errors.ma4 = ma4.error
  if (macdFast.error) errors.macdFast = macdFast.error
  if (macdSlow.error) errors.macdSlow = macdSlow.error
  if (macdSignal.error) errors.macdSignal = macdSignal.error
  if (kdjPeriod.error) errors.kdjPeriod = kdjPeriod.error
  if (kdjKSmoothing.error) errors.kdjKSmoothing = kdjKSmoothing.error
  if (kdjDSmoothing.error) errors.kdjDSmoothing = kdjDSmoothing.error
  if (wrPeriod.error) errors.wrPeriod = wrPeriod.error
  if (bollPeriod.error) errors.bollPeriod = bollPeriod.error
  if (bollMultiplier.error) errors.bollMultiplier = bollMultiplier.error

  if (macdFast.value !== null && macdSlow.value !== null && macdFast.value >= macdSlow.value) {
    const relationError = '需满足 Fast < Slow'
    errors.macdFast = relationError
    errors.macdSlow = relationError
  }

  const hasErrors = Object.keys(errors).length > 0
  return {
    errors,
    params: hasErrors
      ? null
      : ({
          ma: {
            periods: [ma1.value, ma2.value, ma3.value, ma4.value] as [number, number, number, number],
          },
          macd: {
            fast: macdFast.value as number,
            slow: macdSlow.value as number,
            signal: macdSignal.value as number,
          },
          kdj: {
            period: kdjPeriod.value as number,
            kSmoothing: kdjKSmoothing.value as number,
            dSmoothing: kdjDSmoothing.value as number,
          },
          wr: {
            period: wrPeriod.value as number,
          },
          boll: {
            period: bollPeriod.value as number,
            multiplier: bollMultiplier.value as number,
          },
        } satisfies QuantIndicatorParams),
  }
})

function validateFilterDraft(draft: QuantFilterDraft) {
  const errors: QuantFilterErrors = {}
  const parsed: QuantFilterApplied = {}
  const labelByKey = new Map(quantFilterDataset.value.fields.map((field) => [field.key, field.label]))

  for (const key of QUANT_FILTER_FIELD_KEYS) {
    const label = labelByKey.get(key) ?? key
    const gtResult = parseOptionalNumber(`${label} 大于`, draft[key].gt)
    const ltResult = parseOptionalNumber(`${label} 小于`, draft[key].lt)
    const messages = [gtResult.error, ltResult.error].filter(Boolean)

    if (messages.length) {
      errors[key] = messages.join('；')
      continue
    }

    if (gtResult.value !== null || ltResult.value !== null) {
      parsed[key] = {
        gt: gtResult.value,
        lt: ltResult.value,
      }
    }
  }

  return {
    errors,
    applied: parsed,
  }
}

function validateSpecialFilterDraft(
  bollDraft: QuantBollFilterInput,
): QuantSpecialFilterValidation {
  const errors: QuantSpecialFilterErrors = {
    boll: '',
  }

  const validBollValues = new Set(BOLL_FILTER_OPTIONS.map((item) => item.value))
  const nextBollGt = bollDraft.gt && validBollValues.has(bollDraft.gt) ? bollDraft.gt : null
  const nextBollLt = bollDraft.lt && validBollValues.has(bollDraft.lt) ? bollDraft.lt : null

  if (bollDraft.gt && !nextBollGt) {
    errors.boll = 'BOLL 大于条件无效'
  }
  if (bollDraft.lt && !nextBollLt) {
    errors.boll = errors.boll ? `${errors.boll}；BOLL 小于条件无效` : 'BOLL 小于条件无效'
  }

  return {
    errors,
    boll: {
      gt: nextBollGt,
      lt: nextBollLt,
    },
  }
}

const blueFilterValidation = computed(() => validateFilterDraft(blueFilterDraft))
const redFilterValidation = computed(() => validateFilterDraft(redFilterDraft))
const blueSpecialFilterValidation = computed(() => validateSpecialFilterDraft(blueBollFilterDraft))
const redSpecialFilterValidation = computed(() => validateSpecialFilterDraft(redBollFilterDraft))

const hasValidationErrors = computed(() => Object.keys(validation.value.errors).length > 0)
const canApplyParams = computed(() => Boolean(validation.value.params) && !loading.value && Boolean(indexCode.value))
const canApplyFilters = computed(
  () =>
    !loading.value &&
    !booting.value &&
    !Object.keys(blueFilterValidation.value.errors).length &&
    !Object.keys(redFilterValidation.value.errors).length &&
    !blueSpecialFilterValidation.value.errors.boll &&
    !redSpecialFilterValidation.value.errors.boll,
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
  const blueEntries = Object.entries(appliedBlueFilters.value)
  const redEntries = Object.entries(appliedRedFilters.value)
  const blueBoll = appliedBlueBollFilter.value
  const redBoll = appliedRedBollFilter.value

  const blueDates = new Set<string>()
  const redDates = new Set<string>()

  function matchesNumericFilters(
    snapshot: (typeof snapshots)[number],
    entries: Array<[string, (typeof appliedBlueFilters.value)[QuantFilterFieldKey]]>,
  ) {
    return entries.every(([key, threshold]) => {
      const value = snapshot.values[key as QuantFilterFieldKey]
      if (value === null || value === undefined) {
        return false
      }

      if (threshold?.gt !== null && threshold?.gt !== undefined && !(value > threshold.gt)) {
        return false
      }

      if (threshold?.lt !== null && threshold?.lt !== undefined && !(value < threshold.lt)) {
        return false
      }

      return true
    })
  }

  function matchesBollFilter(snapshot: (typeof snapshots)[number], filter: QuantBollFilterApplied) {
    if (filter.gt === null && filter.lt === null) {
      return true
    }

    if (snapshot.close === null || snapshot.close === undefined) {
      return false
    }

    if (filter.gt) {
      const value = snapshot.values[filter.gt]
      if (value === null || value === undefined || !(snapshot.close > value)) {
        return false
      }
    }

    if (filter.lt) {
      const value = snapshot.values[filter.lt]
      if (value === null || value === undefined || !(snapshot.close < value)) {
        return false
      }
    }

    return true
  }

  const hasBlueFilters = blueEntries.length || blueBoll.gt !== null || blueBoll.lt !== null
  const hasRedFilters = redEntries.length || redBoll.gt !== null || redBoll.lt !== null

  if (hasBlueFilters) {
    snapshots.forEach((snapshot) => {
      const matches = matchesNumericFilters(snapshot, blueEntries) && matchesBollFilter(snapshot, blueBoll)

      if (matches) {
        blueDates.add(snapshot.tradeDate)
      }
    })
  }

  if (hasRedFilters) {
    snapshots.forEach((snapshot) => {
      const matches = matchesNumericFilters(snapshot, redEntries) && matchesBollFilter(snapshot, redBoll)

      if (matches) {
        redDates.add(snapshot.tradeDate)
      }
    })
  }

  return snapshots.reduce<QuantHighlightBand[]>((bands, snapshot) => {
    const isBlue = blueDates.has(snapshot.tradeDate)
    const isRed = redDates.has(snapshot.tradeDate)

    if (isBlue && isRed) {
      bands.push({ tradeDate: snapshot.tradeDate, color: 'purple' })
    } else if (isBlue) {
      bands.push({ tradeDate: snapshot.tradeDate, color: 'blue' })
    } else if (isRed) {
      bands.push({ tradeDate: snapshot.tradeDate, color: 'red' })
    }

    return bands
  }, [])
})

const highlightSummary = computed(() => {
  let blue = 0
  let red = 0
  let purple = 0

  highlightBands.value.forEach((item) => {
    if (item.color === 'blue') blue += 1
    if (item.color === 'red') red += 1
    if (item.color === 'purple') purple += 1
  })

  return { blue, red, purple }
})

function getDraftByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueFilterDraft : redFilterDraft
}

function getValidationByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueFilterValidation.value : redFilterValidation.value
}

function getBollDraftByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueBollFilterDraft : redBollFilterDraft
}

function getSpecialValidationByColor(color: QuantFilterColor) {
  return color === 'blue' ? blueSpecialFilterValidation.value : redSpecialFilterValidation.value
}

async function handleChartIndexSelect(nextCode: string) {
  if (!nextCode || nextCode === indexCode.value) {
    return
  }

  indexCode.value = nextCode
  await loadSelectedIndexKline()
}

async function loadSelectedIndexKline() {
  if (!indexCode.value) {
    indexCandles.value = []
    return
  }

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

  try {
    emotionPoints.value = await fetchIndexEmotions()
  } catch (loadError) {
    emotionPoints.value = []
    emotionError.value = getErrorMessage(loadError)
  } finally {
    emotionLoading.value = false
  }
}

async function loadFuturesBasisPoints() {
  futuresBasisLoading.value = true
  futuresBasisError.value = ''

  try {
    futuresBasisPoints.value = await fetchIndexFuturesBasis()
  } catch (loadError) {
    futuresBasisPoints.value = []
    futuresBasisError.value = getErrorMessage(loadError)
  } finally {
    futuresBasisLoading.value = false
  }
}

function applyParams() {
  if (!validation.value.params) {
    return
  }

  appliedParams.value = cloneParams(validation.value.params)
}

function resetParams() {
  const nextDefaults = cloneParams(DEFAULT_PARAMS)
  Object.assign(formState, buildFormState(nextDefaults))
  appliedParams.value = nextDefaults
}

function applyFilters() {
  if (
    Object.keys(blueFilterValidation.value.errors).length ||
    Object.keys(redFilterValidation.value.errors).length ||
    blueSpecialFilterValidation.value.errors.boll ||
    redSpecialFilterValidation.value.errors.boll
  ) {
    return
  }

  appliedBlueFilters.value = blueFilterValidation.value.applied
  appliedRedFilters.value = redFilterValidation.value.applied
  appliedBlueBollFilter.value = { ...blueSpecialFilterValidation.value.boll }
  appliedRedBollFilter.value = { ...redSpecialFilterValidation.value.boll }
}

function clearFilters() {
  ;(['blue', 'red'] as QuantFilterColor[]).forEach((color) => {
    const draft = getDraftByColor(color)
    const bollDraft = getBollDraftByColor(color)
    QUANT_FILTER_FIELD_KEYS.forEach((key) => {
      draft[key].gt = ''
      draft[key].lt = ''
    })
    bollDraft.gt = ''
    bollDraft.lt = ''
  })
  appliedBlueFilters.value = {}
  appliedRedFilters.value = {}
  appliedBlueBollFilter.value = createEmptyBollFilterApplied()
  appliedRedBollFilter.value = createEmptyBollFilterApplied()
}

async function initializePage() {
  booting.value = true
  error.value = ''

  try {
    const [options] = await Promise.all([fetchIndexOptions(), loadEmotionPoints(), loadFuturesBasisPoints()])
    indexOptions.value = options

    const preferredOption = options.find((item) => item.name === DEFAULT_INDEX_NAME) ?? options[0]
    indexCode.value = preferredOption?.code ?? ''

    if (!indexCode.value) {
      error.value = '暂无可用的指数选项'
      indexCandles.value = []
      return
    }

    await loadSelectedIndexKline()
  } catch (loadError) {
    error.value = getErrorMessage(loadError)
    indexOptions.value = []
    indexCandles.value = []
  } finally {
    booting.value = false
  }
}

onMounted(async () => {
  await initializePage()
})
</script>

<template>
  <div class="dashboard-shell">
    <AppSidebar active="quant" />

    <main class="dashboard-main quant-main">
      <p v-if="error" class="banner-error">{{ error }}</p>

      <section class="card quant-toolbar-card">
        <div class="quant-page-head">
          <div>
            <h2>量化展示</h2>
            <p class="muted">指数技术分析展示</p>
          </div>
        </div>
      </section>

      <div class="quant-body">
        <div class="quant-content-column">
          <section class="card quant-params-card">
            <div class="quant-form-grid">
              <article class="quant-param-group">
                <div class="quant-param-group-head">
                  <h3>均线</h3>
                  <span class="muted">SMA</span>
                </div>
                <div class="quant-field-grid">
                  <label class="quant-field">
                    <span class="quant-field-label">MA1</span>
                    <input v-model="formState.ma1" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.ma1" class="quant-field-error">{{ validation.errors.ma1 }}</span>
                  </label>
                  <label class="quant-field">
                    <span class="quant-field-label">MA2</span>
                    <input v-model="formState.ma2" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.ma2" class="quant-field-error">{{ validation.errors.ma2 }}</span>
                  </label>
                  <label class="quant-field">
                    <span class="quant-field-label">MA3</span>
                    <input v-model="formState.ma3" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.ma3" class="quant-field-error">{{ validation.errors.ma3 }}</span>
                  </label>
                  <label class="quant-field">
                    <span class="quant-field-label">MA4</span>
                    <input v-model="formState.ma4" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.ma4" class="quant-field-error">{{ validation.errors.ma4 }}</span>
                  </label>
                </div>
              </article>

              <article class="quant-param-group">
                <div class="quant-param-group-head">
                  <h3>MACD</h3>
                  <span class="muted">EMA</span>
                </div>
                <div class="quant-field-grid">
                  <label class="quant-field">
                    <span class="quant-field-label">Fast</span>
                    <input v-model="formState.macdFast" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.macdFast" class="quant-field-error">{{ validation.errors.macdFast }}</span>
                  </label>
                  <label class="quant-field">
                    <span class="quant-field-label">Slow</span>
                    <input v-model="formState.macdSlow" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.macdSlow" class="quant-field-error">{{ validation.errors.macdSlow }}</span>
                  </label>
                  <label class="quant-field quant-field-full">
                    <span class="quant-field-label">Signal</span>
                    <input v-model="formState.macdSignal" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.macdSignal" class="quant-field-error">
                      {{ validation.errors.macdSignal }}
                    </span>
                  </label>
                </div>
              </article>

              <article class="quant-param-group">
                <div class="quant-param-group-head">
                  <h3>KDJ</h3>
                  <span class="muted">RSV</span>
                </div>
                <div class="quant-field-grid">
                  <label class="quant-field">
                    <span class="quant-field-label">周期</span>
                    <input v-model="formState.kdjPeriod" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.kdjPeriod" class="quant-field-error">{{ validation.errors.kdjPeriod }}</span>
                  </label>
                  <label class="quant-field">
                    <span class="quant-field-label">K 平滑</span>
                    <input v-model="formState.kdjKSmoothing" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.kdjKSmoothing" class="quant-field-error">
                      {{ validation.errors.kdjKSmoothing }}
                    </span>
                  </label>
                  <label class="quant-field quant-field-full">
                    <span class="quant-field-label">D 平滑</span>
                    <input v-model="formState.kdjDSmoothing" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.kdjDSmoothing" class="quant-field-error">
                      {{ validation.errors.kdjDSmoothing }}
                    </span>
                  </label>
                </div>
              </article>

              <article class="quant-param-group">
                <div class="quant-param-group-head">
                  <h3>WR</h3>
                  <span class="muted">0-100</span>
                </div>
                <div class="quant-field-grid">
                  <label class="quant-field quant-field-full">
                    <span class="quant-field-label">周期</span>
                    <input v-model="formState.wrPeriod" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.wrPeriod" class="quant-field-error">{{ validation.errors.wrPeriod }}</span>
                  </label>
                </div>
              </article>

              <article class="quant-param-group quant-param-group-boll">
                <div class="quant-param-group-head">
                  <h3>BOLL</h3>
                  <span class="muted">SMA + STD</span>
                </div>
                <div class="quant-field-grid">
                  <label class="quant-field">
                    <span class="quant-field-label">周期</span>
                    <input v-model="formState.bollPeriod" class="input" inputmode="numeric" />
                    <span v-if="validation.errors.bollPeriod" class="quant-field-error">
                      {{ validation.errors.bollPeriod }}
                    </span>
                  </label>
                  <label class="quant-field">
                    <span class="quant-field-label">倍数</span>
                    <input v-model="formState.bollMultiplier" class="input" inputmode="decimal" />
                    <span v-if="validation.errors.bollMultiplier" class="quant-field-error">
                      {{ validation.errors.bollMultiplier }}
                    </span>
                  </label>
                </div>
                <div class="quant-param-group-footer">
                  <button class="btn primary" :disabled="!canApplyParams" @click="applyParams">应用参数</button>
                  <button class="btn" :disabled="loading" @click="resetParams">恢复默认</button>
                </div>
              </article>
            </div>

            <p v-if="hasValidationErrors" class="quant-form-hint error">
              参数存在未通过校验的项目，修正后才能应用。
            </p>
            <p v-else class="quant-form-hint muted">修改参数后点击“应用参数”，图表会按当前指数重新计算技术指标。</p>
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

            <p class="quant-filter-hint muted">
              蓝色和红色现在是两套独立筛选，分别单独求交集；同一天同时命中两套条件时显示紫色。点击“确定”后生效。
            </p>

            <div class="quant-filter-sections">
              <section
                v-for="color in FILTER_COLORS"
                :key="color"
                class="quant-filter-section"
                :class="`quant-filter-section-${color}`"
              >
                <div class="quant-filter-section-head">
                  <h4>{{ color === 'blue' ? '蓝色筛选' : '红色筛选' }}</h4>
                  <span class="quant-filter-section-badge">
                    {{ color === 'blue' ? '命中刷蓝色' : '命中刷红色' }}
                  </span>
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
                        <input
                          v-model="getDraftByColor(color)[field.key].gt"
                          class="input quant-filter-input"
                          inputmode="decimal"
                          placeholder="大于"
                        />
                        <input
                          v-model="getDraftByColor(color)[field.key].lt"
                          class="input quant-filter-input"
                          inputmode="decimal"
                          placeholder="小于"
                        />
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
                          <option
                            v-for="option in BOLL_FILTER_OPTIONS"
                            :key="`${color}-boll-gt-${option.value}`"
                            :value="option.value"
                          >
                            {{ option.label }}
                          </option>
                        </select>
                        <select v-model="getBollDraftByColor(color).lt" class="input quant-filter-input">
                          <option value="">不设置</option>
                          <option
                            v-for="option in BOLL_FILTER_OPTIONS"
                            :key="`${color}-boll-lt-${option.value}`"
                            :value="option.value"
                          >
                            {{ option.label }}
                          </option>
                        </select>
                      </div>
                      <p v-if="getSpecialValidationByColor(color).errors.boll" class="quant-filter-row-error">
                        {{ getSpecialValidationByColor(color).errors.boll }}
                      </p>
                    </div>
                  </section>
                </div>
              </section>
            </div>

            <div class="quant-filter-footer">
              <button class="btn primary" :disabled="!canApplyFilters" @click="applyFilters">确定</button>
              <button class="btn" @click="clearFilters">清空筛选</button>
            </div>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>
