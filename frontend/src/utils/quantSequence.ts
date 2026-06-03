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
const sequenceSeriesKeys: QuantSequenceSeriesKey[] = [
  'market-breadth-up-pct',
  'market-emotion',
  'market-qvix',
  'market-basis-main',
  'target-up-pct',
  'target-down-pct',
  'target-high-new-high',
  'target-close-new-high',
  'target-ma-bias-1',
  'target-ma-bias-2',
  'target-ma-bias-3',
  'target-ma-bias-4',
]
const newHighSeriesKeys = new Set<QuantSequenceSeriesKey>(['target-high-new-high', 'target-close-new-high'])
const maBiasSeriesKeys = new Set<QuantSequenceSeriesKey>([
  'target-ma-bias-1',
  'target-ma-bias-2',
  'target-ma-bias-3',
  'target-ma-bias-4',
])
const sequenceOperators = new Set(['gt', 'gte', 'lt', 'lte'])

function nextDraftId(prefix: string) {
  draftSequence += 1
  return `${prefix}-${draftSequence}`
}

export function isNewHighSequenceSeries(seriesKey: QuantSequenceSeriesKey | '') {
  return Boolean(seriesKey && newHighSeriesKeys.has(seriesKey))
}

export function isMaBiasSequenceSeries(seriesKey: QuantSequenceSeriesKey | '') {
  return Boolean(seriesKey && maBiasSeriesKeys.has(seriesKey))
}

function normalizeMaPeriods(periods?: readonly number[]) {
  const defaults = [5, 10, 20, 60]
  return defaults.map((fallback, index) => {
    const value = Number(periods?.[index])
    return Number.isInteger(value) && value > 0 ? value : fallback
  })
}

function calculateSma(values: number[], period: number) {
  const result: Array<number | null> = Array(values.length).fill(null)
  let rollingSum = 0
  let validCount = 0
  values.forEach((value, index) => {
    if (Number.isFinite(value)) {
      rollingSum += value
      validCount += 1
    }
    if (index >= period) {
      const dropped = values[index - period]
      if (Number.isFinite(dropped)) {
        rollingSum -= dropped
        validCount -= 1
      }
    }
    if (index >= period - 1 && validCount === period) {
      result[index] = rollingSum / period
    }
  })
  return result
}

function calculateMaBias(close: number, maValue: number | null) {
  if (!Number.isFinite(close) || maValue === null || !Number.isFinite(maValue) || maValue <= 0) return null
  return ((close - maValue) / maValue) * 100
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
  const allowedSeries = new Set<QuantSequenceSeriesKey>(sequenceSeriesKeys)

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

      if (isNewHighSequenceSeries(condition.series_key)) {
        conditions.push({
          series_key: condition.series_key,
          operator: 'gt',
          threshold: 0,
          consecutive_days: 1,
        })
        return
      }

      const threshold = Number(condition.threshold.trim())
      if (!condition.threshold.trim() || !Number.isFinite(threshold)) {
        conditionErrors[condition.id] = '请输入有效阈值'
        hasError = true
        return
      }
      if (!sequenceOperators.has(condition.operator)) {
        conditionErrors[condition.id] = '运算符无效'
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

export function buildSequenceSnapshots(
  candles: KlineCandle[],
  breadthPoints: IndexBreadthPoint[],
  maPeriods?: readonly number[],
): QuantSequenceSnapshot[] {
  const breadthByDate = new Map(breadthPoints.map((item) => [item.trade_date, item.up_ratio_pct]))
  const sortedCandles = [...candles].sort((left, right) => left.trade_date.localeCompare(right.trade_date))
  const closes = sortedCandles.map((item) => Number(item.close))
  const maValues = normalizeMaPeriods(maPeriods).map((period) => calculateSma(closes, period))
  let priorMaxHigh: number | null = null
  let priorMaxClose: number | null = null
  return sortedCandles
    .map((item, index) => {
      const high = Number(item.high)
      const close = Number(item.close)
      const highIsNewHigh = Number.isFinite(high) && priorMaxHigh !== null && high > priorMaxHigh
      const closeIsNewHigh = Number.isFinite(close) && priorMaxClose !== null && close > priorMaxClose
      const snapshot: QuantSequenceSnapshot = {
        tradeDate: item.trade_date,
        values: {
          'target-up-pct': Number.isFinite(item.pct_chg) && Number(item.pct_chg) > 0 ? Number(item.pct_chg) : null,
          'target-down-pct':
            Number.isFinite(item.pct_chg) && Number(item.pct_chg) < 0 ? Math.abs(Number(item.pct_chg)) : null,
          'market-breadth-up-pct': breadthByDate.get(item.trade_date) ?? null,
          'market-emotion': null,
          'market-qvix': null,
          'market-basis-main': null,
          'target-high-new-high': highIsNewHigh ? 1 : 0,
          'target-close-new-high': closeIsNewHigh ? 1 : 0,
          'target-ma-bias-1': calculateMaBias(close, maValues[0]?.[index] ?? null),
          'target-ma-bias-2': calculateMaBias(close, maValues[1]?.[index] ?? null),
          'target-ma-bias-3': calculateMaBias(close, maValues[2]?.[index] ?? null),
          'target-ma-bias-4': calculateMaBias(close, maValues[3]?.[index] ?? null),
        },
      }
      if (Number.isFinite(high)) {
        priorMaxHigh = priorMaxHigh === null ? high : Math.max(priorMaxHigh, high)
      }
      if (Number.isFinite(close)) {
        priorMaxClose = priorMaxClose === null ? close : Math.max(priorMaxClose, close)
      }
      return snapshot
    })
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
    if (condition.operator === 'gte' && value < condition.threshold) {
      return false
    }
    if (condition.operator === 'lt' && value >= condition.threshold) {
      return false
    }
    if (condition.operator === 'lte' && value > condition.threshold) {
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
