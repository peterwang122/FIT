<script setup lang="ts">
import { computed } from 'vue'

import type {
  QuantSequenceConditionDraft,
  QuantSequenceGroupDraft,
  QuantSequenceOperator,
  QuantSequenceSeriesKey,
  QuantStrategyType,
} from '../types/quant'
import { isMaBiasSequenceSeries, isNewHighSequenceSeries } from '../utils/quantSequence'

const props = withDefaults(defineProps<{
  side: 'buy' | 'sell'
  mode?: 'single_target' | 'market_scan'
  targetType?: QuantStrategyType
  maPeriods?: readonly number[]
  groups: QuantSequenceGroupDraft[]
  groupErrors: Record<string, string>
  conditionErrors: Record<string, string>
}>(), {
  mode: 'single_target',
  targetType: 'stock',
  maPeriods: () => [5, 10, 20, 60],
})

const emit = defineEmits<{
  (event: 'add-group'): void
  (event: 'delete-group', groupId: string): void
  (event: 'add-condition', groupId: string): void
  (event: 'delete-condition', payload: { groupId: string; conditionId: string }): void
}>()

type SeriesOption = { value: QuantSequenceSeriesKey; label: string; marketOnly?: boolean; stockEtfOnly?: boolean }

const baseSeriesOptions: SeriesOption[] = [
  { value: 'market-breadth-up-pct', label: '涨跌家数百分比' },
  { value: 'market-emotion', label: '市场情绪指标', marketOnly: true },
  { value: 'market-qvix', label: '市场QVIX均值', marketOnly: true },
  { value: 'market-basis-main', label: '主连期现差均值', marketOnly: true },
  { value: 'target-up-pct', label: '目标上涨幅度' },
  { value: 'target-down-pct', label: '目标下跌幅度' },
  { value: 'target-high-new-high', label: '最高价创历史新高' },
  { value: 'target-close-new-high', label: '收盘价创历史新高' },
]
const maBiasSeriesKeys: QuantSequenceSeriesKey[] = [
  'target-ma-bias-1',
  'target-ma-bias-2',
  'target-ma-bias-3',
  'target-ma-bias-4',
]

const operatorOptions: Array<{ value: QuantSequenceOperator; label: string }> = [
  { value: 'gt', label: '大于' },
  { value: 'gte', label: '大于等于' },
  { value: 'lt', label: '小于' },
  { value: 'lte', label: '小于等于' },
]

const operatorLabelMap: Record<QuantSequenceOperator, string> = {
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
}

const normalizedMaPeriods = computed(() =>
  [5, 10, 20, 60].map((fallback, index) => {
    const value = Number(props.maPeriods?.[index])
    return Number.isInteger(value) && value > 0 ? value : fallback
  }),
)

const maBiasSeriesOptions = computed<SeriesOption[]>(() =>
  maBiasSeriesKeys.map((value, index) => ({
    value,
    label: `收盘价相对 MA${normalizedMaPeriods.value[index]} 乖离`,
    stockEtfOnly: true,
  })),
)

const seriesOptions = computed<SeriesOption[]>(() => [...baseSeriesOptions, ...maBiasSeriesOptions.value])
const seriesLabelMap = computed<Record<QuantSequenceSeriesKey, string>>(
  () =>
    seriesOptions.value.reduce(
      (result, option) => ({ ...result, [option.value]: option.label }),
      {} as Record<QuantSequenceSeriesKey, string>,
    ),
)

function visibleSeriesOptions() {
  return seriesOptions.value.filter((option) => {
    if (option.marketOnly && props.mode !== 'market_scan') return false
    if (option.stockEtfOnly && props.targetType === 'index') return false
    return true
  })
}

function getSeriesHint(seriesKey: QuantSequenceConditionDraft['series_key']) {
  if (seriesKey === 'target-high-new-high') {
    return '当日最高价严格高于此前所有交易日最高价时命中。'
  }
  if (seriesKey === 'target-close-new-high') {
    return '当日收盘价严格高于此前所有交易日收盘价时命中。'
  }
  if (seriesKey === 'target-up-pct' || seriesKey === 'target-down-pct') {
    return '阈值填正数，单位为 %。例如 9 表示 9%。'
  }
  if (isMaBiasSequenceSeries(seriesKey)) {
    return '按 (收盘价 - MA) / MA * 100 计算。若要站上均线且不过热，可同时配置大于等于 0 和小于等于 15。'
  }
  if (seriesKey === 'market-breadth-up-pct') {
    return '阈值表示上涨家数占比，单位为 %。例如 20 表示 20%。'
  }
  if (seriesKey === 'market-emotion') {
    return 'A股核心指数情绪均值，阈值可填 60 表示只在偏强情绪里扫描。'
  }
  if (seriesKey === 'market-qvix') {
    return 'A股 QVIX 有效收盘均值，已忽略 0 和负数异常值。'
  }
  if (seriesKey === 'market-basis-main') {
    return 'A股核心股指期货主连期现差均值，可用于过滤贴水或升水环境。'
  }
  return '先选择序列，再设置阈值和连续交易日数。'
}

function buildConditionPreview(condition: QuantSequenceConditionDraft) {
  if (!condition.series_key) return '请先选择序列。'
  if (condition.series_key === 'target-high-new-high') return '当日最高价创历史新高'
  if (condition.series_key === 'target-close-new-high') return '当日收盘价创历史新高'
  const seriesLabel = seriesLabelMap.value[condition.series_key] ?? condition.series_key
  const operatorLabel = operatorLabelMap[condition.operator]
  const threshold = condition.threshold.trim() || '阈值'
  const days = condition.consecutive_days.trim() || 'N'
  const isPercentSeries =
    ['market-breadth-up-pct', 'target-up-pct', 'target-down-pct'].includes(condition.series_key) ||
    isMaBiasSequenceSeries(condition.series_key)
  const unitLabel = isPercentSeries ? '%' : condition.series_key === 'market-basis-main' ? '点' : ''
  return `连续 ${days} 个交易日${seriesLabel}${operatorLabel} ${threshold}${unitLabel}`
}

function handleSeriesChange(condition: QuantSequenceConditionDraft) {
  if (!isNewHighSequenceSeries(condition.series_key)) return
  condition.operator = 'gt'
  condition.threshold = '0'
  condition.consecutive_days = '1'
}
</script>

<template>
  <section class="quant-filter-section" :class="side === 'buy' ? 'quant-filter-section-blue' : 'quant-filter-section-red'">
    <div class="quant-filter-section-head">
      <h4>{{ side === 'buy' ? '买入规则组' : '卖出规则组' }}</h4>
      <span class="quant-filter-section-badge">{{ side === 'buy' ? '命中刷蓝色' : '命中刷红色' }}</span>
    </div>

    <div class="quant-rule-group-stack">
      <div v-if="!groups.length" class="quant-rule-empty muted">暂无规则组，可新增后配置连续交易日条件。</div>

      <template v-for="(group, groupIndex) in groups" :key="group.id">
        <div v-if="groupIndex > 0" class="quant-rule-or-divider">满足任一规则组</div>

        <section class="quant-filter-group quant-rule-group-card">
          <div class="quant-rule-group-head">
            <div>
              <h4>规则组 {{ groupIndex + 1 }}</h4>
              <p class="muted">组内全部满足</p>
            </div>
            <div class="quant-rule-group-actions">
              <button type="button" class="btn" @click="emit('add-condition', group.id)">新增条件</button>
              <button type="button" class="btn" @click="emit('delete-group', group.id)">删除规则组</button>
            </div>
          </div>

          <div class="quant-rule-condition-list">
            <div v-for="condition in group.conditions" :key="condition.id" class="quant-rule-condition">
              <div
                class="quant-sequence-condition-grid"
                :class="{ 'quant-sequence-condition-grid-boolean': isNewHighSequenceSeries(condition.series_key) }"
              >
                <div class="quant-sequence-condition-field">
                  <span class="quant-sequence-condition-label">序列</span>
                  <select v-model="condition.series_key" class="input" @change="handleSeriesChange(condition)">
                    <option value="">选择序列</option>
                    <option v-for="option in visibleSeriesOptions()" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </div>

                <div v-if="!isNewHighSequenceSeries(condition.series_key)" class="quant-sequence-condition-field">
                  <span class="quant-sequence-condition-label">运算符</span>
                  <select v-model="condition.operator" class="input">
                    <option v-for="option in operatorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </div>

                <div v-if="!isNewHighSequenceSeries(condition.series_key)" class="quant-sequence-condition-field">
                  <span class="quant-sequence-condition-label">阈值（%）</span>
                  <input v-model="condition.threshold" class="input" inputmode="decimal" placeholder="例如 9" />
                </div>

                <div v-if="!isNewHighSequenceSeries(condition.series_key)" class="quant-sequence-condition-field">
                  <span class="quant-sequence-condition-label">连续交易日数</span>
                  <input v-model="condition.consecutive_days" class="input" inputmode="numeric" placeholder="例如 3" />
                </div>

                <button
                  type="button"
                  class="btn quant-rule-delete-btn"
                  @click="emit('delete-condition', { groupId: group.id, conditionId: condition.id })"
                >
                  删除
                </button>
              </div>

              <p class="muted quant-sequence-condition-hint">{{ getSeriesHint(condition.series_key) }}</p>
              <p class="quant-sequence-condition-preview">{{ buildConditionPreview(condition) }}</p>
              <p v-if="conditionErrors[condition.id]" class="quant-filter-row-error">{{ conditionErrors[condition.id] }}</p>
            </div>
          </div>

          <p v-if="groupErrors[group.id]" class="quant-filter-row-error">{{ groupErrors[group.id] }}</p>
        </section>
      </template>
    </div>

    <button type="button" class="btn quant-rule-add-group" @click="emit('add-group')">新增规则组</button>
  </section>
</template>
