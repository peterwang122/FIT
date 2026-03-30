import type {
  QuantBollFilterKey,
  QuantDailyIndicatorSnapshot,
  QuantFilterFieldKey,
  QuantFilterGroupSet,
  QuantRuleCondition,
  QuantRuleConditionDraft,
  QuantRuleGroup,
  QuantRuleGroupDraft,
  QuantRuleOperator,
  QuantRuleTargetKey,
} from '../types/quant'

export type QuantRuleFieldOption = {
  value: QuantFilterFieldKey
  label: string
}

export type QuantRuleValidationResult = {
  groups: QuantFilterGroupSet
  groupErrors: Record<string, string>
  conditionErrors: Record<string, string>
}

let draftSequence = 0

function nextDraftId(prefix: string) {
  draftSequence += 1
  return `${prefix}-${draftSequence}`
}

export function createFieldTarget(field: QuantFilterFieldKey): QuantRuleTargetKey {
  return `field:${field}` as QuantRuleTargetKey
}

export function isNumericTarget(target: QuantRuleTargetKey | ''): target is `field:${QuantFilterFieldKey}` {
  return target.startsWith('field:')
}

export function isBollCloseTarget(target: QuantRuleTargetKey | ''): boolean {
  return target === 'boll:close'
}

export function isBollIntradayTarget(target: QuantRuleTargetKey | ''): boolean {
  return target === 'boll:intraday'
}

export function getFieldFromTarget(target: QuantRuleTargetKey | ''): QuantFilterFieldKey | null {
  if (!isNumericTarget(target)) return null
  return target.slice('field:'.length) as QuantFilterFieldKey
}

export function createEmptyRuleConditionDraft(): QuantRuleConditionDraft {
  return {
    id: nextDraftId('condition'),
    target: '',
    operator: 'gt',
    value: '',
    track: '',
  }
}

export function createEmptyRuleGroupDraft(): QuantRuleGroupDraft {
  return {
    id: nextDraftId('group'),
    conditions: [createEmptyRuleConditionDraft()],
  }
}

export function normalizeRuleGroups(
  drafts: QuantRuleGroupDraft[],
  allowedFields: QuantFilterFieldKey[],
): QuantRuleValidationResult {
  const allowedFieldSet = new Set(allowedFields)
  const groups: QuantRuleGroup[] = []
  const groupErrors: Record<string, string> = {}
  const conditionErrors: Record<string, string> = {}

  drafts.forEach((group) => {
    const conditions: QuantRuleCondition[] = []
    let hasConditionError = false

    group.conditions.forEach((condition) => {
      if (!condition.target) {
        return
      }

      if (isNumericTarget(condition.target)) {
        const field = getFieldFromTarget(condition.target)
        if (!field || !allowedFieldSet.has(field)) {
          conditionErrors[condition.id] = '指标无效'
          hasConditionError = true
          return
        }
        if (!condition.value.trim()) {
          conditionErrors[condition.id] = '请输入数值'
          hasConditionError = true
          return
        }
        const parsed = Number(condition.value.trim())
        if (!Number.isFinite(parsed)) {
          conditionErrors[condition.id] = '请输入有效数字'
          hasConditionError = true
          return
        }
        conditions.push({
          type: 'numeric',
          field,
          operator: condition.operator,
          value: parsed,
        })
        return
      }

      if (!condition.track) {
        conditionErrors[condition.id] = '请选择 BOLL 轨道'
        hasConditionError = true
        return
      }

      const mode = isBollIntradayTarget(condition.target) ? 'intraday' : 'close'
      conditions.push({
        type: 'boll',
        mode,
        operator: condition.operator,
        track: condition.track as QuantBollFilterKey,
      })
    })

    if (!conditions.length) {
      if (!hasConditionError) {
        groupErrors[group.id] = '请至少保留一个有效条件'
      }
      return
    }

    groups.push({ conditions })
  })

  return {
    groups,
    groupErrors,
    conditionErrors,
  }
}

export function matchRuleCondition(snapshot: QuantDailyIndicatorSnapshot, condition: QuantRuleCondition): boolean {
  if (condition.type === 'numeric') {
    const value = snapshot.values[condition.field]
    if (value === null || value === undefined) return false
    if (condition.operator === 'gt') return value > condition.value
    return value < condition.value
  }

  const reference = snapshot.values[condition.track]
  if (reference === null || reference === undefined) return false

  if (condition.mode === 'close') {
    if (snapshot.close === null || snapshot.close === undefined) return false
    return condition.operator === 'gt' ? snapshot.close > reference : snapshot.close < reference
  }

  if (condition.operator === 'gt') {
    if (snapshot.high === null || snapshot.high === undefined) return false
    return snapshot.high > reference
  }

  if (snapshot.low === null || snapshot.low === undefined) return false
  return snapshot.low < reference
}

export function matchRuleGroup(snapshot: QuantDailyIndicatorSnapshot, group: QuantRuleGroup): boolean {
  return group.conditions.every((condition) => matchRuleCondition(snapshot, condition))
}

export function matchRuleGroups(snapshot: QuantDailyIndicatorSnapshot, groups: QuantFilterGroupSet): boolean {
  if (!groups.length) return false
  return groups.some((group) => matchRuleGroup(snapshot, group))
}

export function hasRuleGroups(groups: QuantFilterGroupSet): boolean {
  return groups.length > 0
}
