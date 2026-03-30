<script setup lang="ts">
import { computed } from 'vue'

import type { QuantFilterFieldKey, QuantRuleGroupDraft } from '../types/quant'
import { isNumericTarget } from '../utils/quantRuleGroups'

const props = defineProps<{
  color: 'blue' | 'red'
  groups: QuantRuleGroupDraft[]
  numericFieldOptions: Array<{ value: QuantFilterFieldKey; label: string }>
  groupErrors: Record<string, string>
  conditionErrors: Record<string, string>
}>()

const emit = defineEmits<{
  (event: 'add-group'): void
  (event: 'delete-group', groupId: string): void
  (event: 'add-condition', groupId: string): void
  (event: 'delete-condition', payload: { groupId: string; conditionId: string }): void
}>()

const targetOptions = computed(() => [
  ...props.numericFieldOptions.map((item) => ({
    value: `field:${item.value}` as const,
    label: item.label,
  })),
  { value: 'boll:close' as const, label: '收盘价相对 BOLL' },
  { value: 'boll:intraday' as const, label: '当日是否有高于/低于 BOLL' },
])

const operatorOptions = [
  { value: 'gt', label: '大于' },
  { value: 'lt', label: '小于' },
]

const bollTrackOptions = [
  { value: 'boll-upper', label: 'BOLL上轨' },
  { value: 'boll-middle', label: 'BOLL中轨' },
  { value: 'boll-lower', label: 'BOLL下轨' },
]
</script>

<template>
  <section class="quant-filter-section" :class="`quant-filter-section-${color}`">
    <div class="quant-filter-section-head">
      <h4>{{ color === 'blue' ? '蓝色筛选' : '红色筛选' }}</h4>
      <span class="quant-filter-section-badge">{{ color === 'blue' ? '命中刷蓝色' : '命中刷红色' }}</span>
    </div>

    <div class="quant-rule-group-stack">
      <div v-if="!groups.length" class="quant-rule-empty muted">暂无规则组，可新增后配置条件。</div>

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
              <div class="quant-rule-condition-grid">
                <select v-model="condition.target" class="input quant-rule-condition-target">
                  <option value="">选择条件</option>
                  <option v-for="option in targetOptions" :key="`${group.id}-${condition.id}-${option.value}`" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>

                <select v-model="condition.operator" class="input quant-rule-condition-operator">
                  <option v-for="option in operatorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>

                <input
                  v-if="isNumericTarget(condition.target)"
                  v-model="condition.value"
                  class="input quant-rule-condition-value"
                  inputmode="decimal"
                  placeholder="输入数值"
                />
                <select v-else v-model="condition.track" class="input quant-rule-condition-value">
                  <option value="">选择轨道</option>
                  <option v-for="option in bollTrackOptions" :key="`${condition.id}-${option.value}`" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>

                <button
                  type="button"
                  class="btn quant-rule-delete-btn"
                  @click="emit('delete-condition', { groupId: group.id, conditionId: condition.id })"
                >
                  删除
                </button>
              </div>

              <p v-if="conditionErrors[condition.id]" class="quant-filter-row-error">
                {{ conditionErrors[condition.id] }}
              </p>
            </div>
          </div>

          <p v-if="groupErrors[group.id]" class="quant-filter-row-error">{{ groupErrors[group.id] }}</p>
        </section>
      </template>
    </div>

    <button type="button" class="btn quant-rule-add-group" @click="emit('add-group')">新增规则组</button>
  </section>
</template>
