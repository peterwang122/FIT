<script setup lang="ts">
import type { QuantSequenceConditionDraft, QuantSequenceGroupDraft, QuantSequenceOperator, QuantSequenceSeriesKey } from '../types/quant'

defineProps<{
  side: 'buy' | 'sell'
  groups: QuantSequenceGroupDraft[]
  groupErrors: Record<string, string>
  conditionErrors: Record<string, string>
}>()

const emit = defineEmits<{
  (event: 'add-group'): void
  (event: 'delete-group', groupId: string): void
  (event: 'add-condition', groupId: string): void
  (event: 'delete-condition', payload: { groupId: string; conditionId: string }): void
}>()

const seriesOptions: Array<{ value: QuantSequenceSeriesKey; label: string }> = [
  { value: 'market-breadth-up-pct', label: '涨跌家数百分比' },
  { value: 'target-up-pct', label: '目标上涨幅度' },
  { value: 'target-down-pct', label: '目标下跌幅度' },
]

const operatorOptions: Array<{ value: QuantSequenceOperator; label: string }> = [
  { value: 'lt', label: '小于' },
  { value: 'gt', label: '大于' },
]

const seriesLabelMap: Record<QuantSequenceSeriesKey, string> = {
  'market-breadth-up-pct': '涨跌家数百分比',
  'target-up-pct': '目标上涨幅度',
  'target-down-pct': '目标下跌幅度',
}

const operatorLabelMap: Record<QuantSequenceOperator, string> = {
  gt: '大于',
  lt: '小于',
}

function getSeriesHint(seriesKey: QuantSequenceConditionDraft['series_key']) {
  if (seriesKey === 'target-up-pct' || seriesKey === 'target-down-pct') {
    return '阈值填正数，单位为 %。例如 9 表示 9%。'
  }
  if (seriesKey === 'market-breadth-up-pct') {
    return '阈值表示上涨家数占比，单位为 %。例如 20 表示 20%。'
  }
  return '先选择序列，再设置阈值和连续交易日数。'
}

function buildConditionPreview(condition: QuantSequenceConditionDraft) {
  if (!condition.series_key) return '请先选择序列。'
  const seriesLabel = seriesLabelMap[condition.series_key]
  const operatorLabel = operatorLabelMap[condition.operator]
  const threshold = condition.threshold.trim() || '阈值'
  const days = condition.consecutive_days.trim() || 'N'
  return `连续 ${days} 个交易日${seriesLabel}${operatorLabel} ${threshold}%`
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
              <div class="quant-sequence-condition-grid">
                <div class="quant-sequence-condition-field">
                  <span class="quant-sequence-condition-label">序列</span>
                  <select v-model="condition.series_key" class="input">
                    <option value="">选择序列</option>
                    <option v-for="option in seriesOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </div>

                <div class="quant-sequence-condition-field">
                  <span class="quant-sequence-condition-label">运算符</span>
                  <select v-model="condition.operator" class="input">
                    <option v-for="option in operatorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </div>

                <div class="quant-sequence-condition-field">
                  <span class="quant-sequence-condition-label">阈值（%）</span>
                  <input v-model="condition.threshold" class="input" inputmode="decimal" placeholder="例如 9" />
                </div>

                <div class="quant-sequence-condition-field">
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
