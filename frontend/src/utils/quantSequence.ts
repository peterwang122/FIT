import type { IndexBreadthPoint, KlineCandle } from '../types/stock'
import type {
  QuantHighlightBand,
  QuantSequenceCondition,
  QuantSequenceConditionDraft,
  QuantSequenceGroup,
  QuantSequenceGroupDraft,
  QuantSequenceGroupSet,
  QuantSequenceSeriesKey,
  QuantSequenceSnapshot,
} from '../types/quant'

let draftSequence = 0

function nextDraftId(prefix: string) {
  draftSequence += 1
  return `${prefix}-${draftSequence}`
}

export function createEmptySequenceConditionDraft(): QuantSequenceConditionDraft {
  return {
    id: nextDraftId('sequence-condition'),
    series_key: '',
    operator: 'lt',
    threshold: '',
    consecutive_days: '3',
  }
}

export function createEmptySequenceGroupDraft(): QuantSequenceGroupDraft {
  return {
    id: nextDraftId('sequence-group'),
    conditions: [createEmptySequenceConditionDraft()],
  }
}

export function deserializeSequenceGroups(groups: QuantSequenceGroupSet): QuantSequenceGroupDraft[] {
  return groups.map((group) => ({
    id: nextDraftId('sequence-group'),
    conditions: group.conditions.map((condition) => ({
      id: nextDraftId('sequence-condition'),
      series_key: condition.series_key,
      operator: condition.operator,
      threshold: String(condition.threshold),
      consecutive_days: String(condition.consecutive_days),
    })),
  }))
}

export function normalizeSequenceGroups(drafts: QuantSequenceGroupDraft[]) {
  const groups: QuantSequenceGroup[] = []
  const groupErrors: Record<string, string> = {}
  const conditionErrors: Record<string, string> = {}
  const allowedSeries = new Set<QuantSequenceSeriesKey>(['market-breadth-up-pct', 'target-up-pct', 'target-down-pct'])

  drafts.forEach((group) => {
    const conditions: QuantSequenceCondition[] = []
    let hasError = false

    group.conditions.forEach((condition) => {
      if (!condition.series_key) {
        return
      }
      if (!allowedSeries.has(condition.series_key)) {
        conditionErrors[condition.id] = '条件序列无效'
        hasError = true
        return
      }

      const threshold = Number(condition.threshold.trim())
      if (!condition.threshold.trim() || !Number.isFinite(threshold)) {
        conditionErrors[condition.id] = '请输入有效阈值'
        hasError = true
        return
      }

      const consecutiveDays = Number(condition.consecutive_days.trim())
      if (!condition.consecutive_days.trim() || !Number.isInteger(consecutiveDays) || consecutiveDays <= 0) {
        conditionErrors[condition.id] = '连续天数必须是正整数'
        hasError = true
        return
      }

      conditions.push({
        series_key: condition.series_key,
        operator: condition.operator,
        threshold,
        consecutive_days: consecutiveDays,
      })
    })

    if (!conditions.length) {
      if (!hasError) {
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

export function buildSequenceSnapshots(candles: KlineCandle[], breadthPoints: IndexBreadthPoint[]): QuantSequenceSnapshot[] {
  const breadthByDate = new Map(breadthPoints.map((item) => [item.trade_date, item.up_ratio_pct]))
  return [...candles]
    .sort((left, right) => left.trade_date.localeCompare(right.trade_date))
    .map((item) => ({
      tradeDate: item.trade_date,
      values: {
        'target-up-pct': Number.isFinite(item.pct_chg) && Number(item.pct_chg) > 0 ? Number(item.pct_chg) : null,
        'target-down-pct':
          Number.isFinite(item.pct_chg) && Number(item.pct_chg) < 0 ? Math.abs(Number(item.pct_chg)) : null,
        'market-breadth-up-pct': breadthByDate.get(item.trade_date) ?? null,
      },
    }))
}

function matchSequenceConditionAt(
  snapshots: QuantSequenceSnapshot[],
  index: number,
  condition: QuantSequenceCondition,
): boolean {
  const startIndex = index - condition.consecutive_days + 1
  if (startIndex < 0) {
    return false
  }

  for (let cursor = startIndex; cursor <= index; cursor += 1) {
    const value = snapshots[cursor].values[condition.series_key]
    if (value === null || value === undefined) {
      return false
    }
    if (condition.operator === 'gt' && value <= condition.threshold) {
      return false
    }
    if (condition.operator === 'lt' && value >= condition.threshold) {
      return false
    }
  }
  return true
}

function matchSequenceGroupAt(
  snapshots: QuantSequenceSnapshot[],
  index: number,
  group: QuantSequenceGroup,
) {
  return group.conditions.every((condition) => matchSequenceConditionAt(snapshots, index, condition))
}

export function matchSequenceGroupIndexes(
  snapshots: QuantSequenceSnapshot[],
  index: number,
  groups: QuantSequenceGroupSet,
): number[] {
  if (!groups.length) return []
  return groups.reduce<number[]>((matches, group, groupIndex) => {
    if (matchSequenceGroupAt(snapshots, index, group)) {
      matches.push(groupIndex + 1)
    }
    return matches
  }, [])
}

export function buildSequenceHighlightBands(
  snapshots: QuantSequenceSnapshot[],
  buyGroups: QuantSequenceGroupSet,
  sellGroups: QuantSequenceGroupSet,
): QuantHighlightBand[] {
  return snapshots.reduce<QuantHighlightBand[]>((bands, snapshot, index) => {
    const blueHitGroups = matchSequenceGroupIndexes(snapshots, index, buyGroups)
    const redHitGroups = matchSequenceGroupIndexes(snapshots, index, sellGroups)
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
}
