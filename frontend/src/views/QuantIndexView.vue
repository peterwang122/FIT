<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { createQuantStrategy, fetchIndexDashboard, fetchIndexOptions } from '../api/stocks'
import QuantIndexChart from '../components/QuantIndexChart.vue'
import QuantRuleGroupBuilder from '../components/QuantRuleGroupBuilder.vue'
import type {
  QuantFilterGroupSet,
  QuantHighlightBand,
  QuantIndicatorParams,
  QuantRuleGroupDraft,
} from '../types/quant'
import type { FuturesBasisPoint, IndexBreadthPoint, IndexEmotionPoint, KlineCandle, MarketOption } from '../types/stock'
import { INDEX_QUANT_FILTER_FIELD_KEYS, buildIndexQuantFilterDataset } from '../utils/quantIndicators'
import {
  createEmptyRuleConditionDraft,
  createEmptyRuleGroupDraft,
  matchRuleGroups,
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
  bollPeriod: string
  bollMultiplier: string
}

type QuantFormErrors = Partial<Record<keyof QuantFormState, string>>
type QuantFilterColor = 'blue' | 'red'

const DEFAULT_INDEX_NAME = '上证指数'
const CORE_INDEX_NAMES = ['上证50', '沪深300', '中证500', '中证1000'] as const
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
const loading = ref(false)
const fullLoading = ref(false)
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
let activeDashboardToken = 0

const appliedParams = ref<QuantIndicatorParams>(cloneParams(DEFAULT_PARAMS))
const appliedBlueFilterGroups = ref<QuantFilterGroupSet>([])
const appliedRedFilterGroups = ref<QuantFilterGroupSet>([])

const formState = reactive<QuantFormState>(buildFormState(DEFAULT_PARAMS))
const blueRuleDrafts = ref<QuantRuleGroupDraft[]>([])
const redRuleDrafts = ref<QuantRuleGroupDraft[]>([])

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
const numericFieldOptions = computed(() =>
  quantFilterDataset.value.fields
    .filter((field) => INDEX_QUANT_FILTER_FIELD_KEYS.includes(field.key))
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
      rsi: { period: appliedParams.value.rsi.period },
      boll: { period: bollPeriod.value as number, multiplier: bollMultiplier.value as number },
    } satisfies QuantIndicatorParams,
  }
})

const blueRuleValidation = computed(() => normalizeRuleGroups(blueRuleDrafts.value, INDEX_QUANT_FILTER_FIELD_KEYS))
const redRuleValidation = computed(() => normalizeRuleGroups(redRuleDrafts.value, INDEX_QUANT_FILTER_FIELD_KEYS))

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
    const isBlue = matchRuleGroups(snapshot, appliedBlueFilterGroups.value)
    const isRed = matchRuleGroups(snapshot, appliedRedFilterGroups.value)
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

function applyDashboardPayload(payload: Awaited<ReturnType<typeof fetchIndexDashboard>>) {
  const basisIndexNames = payload.index.name === DEFAULT_INDEX_NAME ? [...CORE_INDEX_NAMES] : [payload.index.name]
  indexCandles.value = payload.candles
  emotionPoints.value = payload.emotion_points.flatMap((item) =>
    basisIndexNames.map((indexName) => ({
      emotion_date: item.trade_date,
      index_name: indexName,
      emotion_value: item.value,
    })),
  )
  futuresBasisPoints.value = payload.basis_points.flatMap((item) =>
    basisIndexNames.map((indexName) => ({
      trade_date: item.trade_date,
      index_name: indexName,
      main_basis: item.main_basis,
      month_basis: item.month_basis,
    })),
  )
  breadthPoints.value = payload.breadth_points
}

async function loadFullDashboardForIndex(targetCode: string, token: number) {
  fullLoading.value = true
  try {
    const payload = await fetchIndexDashboard(targetCode, 'full')
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return
    applyDashboardPayload(payload)
  } catch (loadError) {
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return
    console.error(loadError)
  } finally {
    if (token === activeDashboardToken && targetCode === indexCode.value) {
      fullLoading.value = false
    }
  }
}

async function loadDashboardForIndex(targetCode: string) {
  if (!targetCode) return
  const token = ++activeDashboardToken
  loading.value = true
  fullLoading.value = false
  error.value = ''
  emotionError.value = ''
  futuresBasisError.value = ''
  breadthError.value = ''
  emotionLoading.value = false
  futuresBasisLoading.value = false
  breadthLoading.value = false
  indexCandles.value = []
  emotionPoints.value = []
  futuresBasisPoints.value = []
  breadthPoints.value = []
  try {
    const payload = await fetchIndexDashboard(targetCode, 'recent')
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return
    applyDashboardPayload(payload)
    void loadFullDashboardForIndex(targetCode, token)
  } catch (loadError) {
    if (token !== activeDashboardToken || targetCode !== indexCode.value) return
    error.value = getErrorMessage(loadError)
  } finally {
    if (token === activeDashboardToken && targetCode === indexCode.value) {
      loading.value = false
    }
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
  if (!indexCode.value || !selectedIndexName.value) {
    saveError.value = '当前没有可保存的指数标的'
    return
  }
  saveLoading.value = true
  try {
    const result = await createQuantStrategy({
      name: saveName.value.trim(),
      notes: '',
      strategy_type: 'index',
      target_code: indexCode.value,
      target_name: selectedIndexName.value,
      indicator_params: appliedParams.value,
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
    const options = await fetchIndexOptions()
    indexOptions.value = options
    indexCode.value = (options.find((item) => item.name === DEFAULT_INDEX_NAME) ?? options[0])?.code ?? ''
    if (!indexCode.value) {
      error.value = '暂无可用的指数选项'
      return
    }
    await loadDashboardForIndex(indexCode.value)
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
  <div v-if="showParamsModal" class="quant-modal-backdrop" @click="closeParamsModal"></div>
  <div class="quant-body">
    <div class="quant-content-column">
      <section v-if="showParamsModal" class="card quant-params-card quant-modal quant-param-modal">
        <div class="quant-page-head">
          <div>
            <h3>指数参数</h3>
            <p class="muted">主图支持均线 / BOLL 切换，副图同步展示情绪、期现差与上涨家数百分比。</p>
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
          :loading="loading || booting || fullLoading"
          :default-visible-days="90"
          @select-index="handleChartIndexSelect"
          @open-settings="openParamsModal"
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
        <p class="quant-filter-hint muted">规则组内全部满足，满足任一规则组即命中该颜色；同日蓝红同时命中会显示为紫色。</p>

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
