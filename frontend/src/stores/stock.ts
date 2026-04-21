import { defineStore } from 'pinia'

import {
  collectForexSymbol,
  fetchCffexNetPositionSeries,
  fetchCffexNetPositions,
  fetchForexKline,
  fetchForexOptions,
  fetchIndexEmotions,
  fetchIndexKline,
  fetchIndexOptions,
  fetchKline,
  fetchSymbols,
  fetchTaskStatus,
  submitCollectTask,
} from '../api/stocks'
import type {
  IndexEmotionPoint,
  KlineCandle,
  MarketOption,
  NetPositionSeriesGroup,
  NetPositionSeries,
  NetPositionTables,
  StockSymbol,
} from '../types/stock'

const DEFAULT_FOREX_CODE = 'UDI'
const DEFAULT_FOREX_NAME = '美元指数'
const INDEX_RECENT_MONTHS = 4
const FOREX_RECENT_MONTHS = 3
const EMOTION_RECENT_MONTHS = 6
const NET_POSITION_SERIES_RECENT_MONTHS = 12

type ChunkedHistoryState = {
  candles: KlineCandle[]
  earliestLoadedDate: string | null
  hasMoreHistory: boolean
  pendingWindowKey: string | null
}

type ChunkedNetPositionSeriesState = {
  series: NetPositionSeries | null
  earliestLoadedDate: string | null
  hasMoreHistory: boolean
  pendingWindowKey: string | null
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

function buildIdempotencyKey(tsCode: string): string {
  return `collect:${tsCode}:${new Date().toISOString().slice(0, 10)}`
}

function mergeCandles(existing: KlineCandle[], incoming: KlineCandle[]) {
  const byDate = new Map<string, KlineCandle>()
  for (const item of [...existing, ...incoming]) {
    byDate.set(item.trade_date, item)
  }
  return [...byDate.values()].sort((left, right) => left.trade_date.localeCompare(right.trade_date))
}

function buildChunkState(
  candles: KlineCandle[],
  hasMoreHistory = true,
  pendingWindowKey: string | null = null,
): ChunkedHistoryState {
  return {
    candles,
    earliestLoadedDate: candles[0]?.trade_date ?? null,
    hasMoreHistory: candles.length > 0 ? hasMoreHistory : false,
    pendingWindowKey,
  }
}

function mergeNetPositionGroup(
  existing: NetPositionSeriesGroup | undefined,
  incoming: NetPositionSeriesGroup | undefined,
): NetPositionSeriesGroup {
  const memberLabel = incoming?.member_label ?? existing?.member_label ?? ''
  const keys = ['OVERALL', 'IF', 'IH', 'IC', 'IM'] as const
  const series = Object.fromEntries(
    keys.map((key) => {
      const byDate = new Map<string, { trade_date: string; net_position: number }>()
      for (const item of [...(existing?.series?.[key] ?? []), ...(incoming?.series?.[key] ?? [])]) {
        byDate.set(item.trade_date, item)
      }
      return [key, [...byDate.values()].sort((left, right) => left.trade_date.localeCompare(right.trade_date))]
    }),
  ) as NetPositionSeriesGroup['series']

  return {
    member_label: memberLabel,
    series,
  }
}

function mergeNetPositionSeries(
  existing: NetPositionSeries | null,
  incoming: NetPositionSeries | null,
): NetPositionSeries | null {
  if (!existing) return incoming
  if (!incoming) return existing
  return {
    citic_customer: mergeNetPositionGroup(existing.citic_customer, incoming.citic_customer),
    top20_institutions: mergeNetPositionGroup(existing.top20_institutions, incoming.top20_institutions),
  }
}

function extractEarliestNetPositionTradeDate(series: NetPositionSeries | null): string | null {
  if (!series) return null
  const tradeDates = [
    ...Object.values(series.citic_customer?.series ?? {}).flatMap((items) => items.map((item) => item.trade_date)),
    ...Object.values(series.top20_institutions?.series ?? {}).flatMap((items) => items.map((item) => item.trade_date)),
  ]
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right))

  return tradeDates[0] ?? null
}

function buildNetPositionSeriesState(
  series: NetPositionSeries | null,
  hasMoreHistory = true,
  pendingWindowKey: string | null = null,
): ChunkedNetPositionSeriesState {
  const earliestLoadedDate = extractEarliestNetPositionTradeDate(series)
  return {
    series,
    earliestLoadedDate,
    hasMoreHistory: Boolean(earliestLoadedDate) && hasMoreHistory,
    pendingWindowKey,
  }
}

export const useStockStore = defineStore('stock', {
  state: () => ({
    tsCode: '002594',
    searchKeyword: '',
    netPositionDate: '' as string,
    symbols: [] as StockSymbol[],
    candles: [] as KlineCandle[],
    indexEmotionPoints: [] as IndexEmotionPoint[],
    netPositionTables: null as NetPositionTables | null,
    netPositionSeries: null as NetPositionSeries | null,
    netPositionSeriesHasMoreHistory: false,
    netPositionSeriesLoadingMore: false,
    netPositionSeriesHistory: null as ChunkedNetPositionSeriesState | null,
    indexCode: '',
    indexOptions: [] as MarketOption[],
    indexCandles: [] as KlineCandle[],
    indexHasMoreHistory: false,
    indexHistoryLoadingMore: false,
    forexCode: '',
    forexOptions: [] as MarketOption[],
    forexCandles: [] as KlineCandle[],
    forexHasMoreHistory: false,
    forexHistoryLoadingMore: false,
    indexHistoryByCode: {} as Record<string, ChunkedHistoryState>,
    forexHistoryByCode: {} as Record<string, ChunkedHistoryState>,
    loading: false,
    indexEmotionLoading: false,
    netPositionLoading: false,
    netPositionSeriesLoading: false,
    indexLoading: false,
    forexLoading: false,
    forexCollecting: false,
    collectTaskId: '' as string,
    collectState: '' as string,
    error: '' as string,
  }),
  getters: {
    selectedSymbolName(state): string {
      return state.symbols.find((item) => item.ts_code === state.tsCode)?.stock_name ?? ''
    },
    selectedIndexName(state): string {
      return state.indexOptions.find((item) => item.code === state.indexCode)?.name ?? ''
    },
    selectedForexName(state): string {
      return state.forexOptions.find((item) => item.code === state.forexCode)?.name ?? ''
    },
  },
  actions: {
    ensureDefaultStockSelection() {
      if (!this.symbols.find((item) => item.ts_code === this.tsCode) && this.symbols.length > 0) {
        this.tsCode = this.symbols[0].ts_code
      }
    },
    ensureDefaultIndexSelection() {
      if (!this.indexOptions.find((item) => item.code === this.indexCode) && this.indexOptions.length > 0) {
        this.indexCode = this.indexOptions[0].code
      }
    },
    ensureDefaultForexSelection() {
      const preferredOption =
        this.forexOptions.find((item) => item.code.toUpperCase() === DEFAULT_FOREX_CODE) ??
        this.forexOptions.find((item) => item.name === DEFAULT_FOREX_NAME) ??
        this.forexOptions[0]

      if (!this.forexOptions.find((item) => item.code === this.forexCode) && preferredOption) {
        this.forexCode = preferredOption.code
      }
    },
    applyIndexHistoryState(indexCode: string, state: ChunkedHistoryState | null) {
      this.indexCandles = state?.candles ?? []
      this.indexHasMoreHistory = state?.hasMoreHistory ?? false
      this.indexHistoryLoadingMore = Boolean(state?.pendingWindowKey)
      if (state) {
        this.indexHistoryByCode[indexCode] = state
      }
    },
    applyForexHistoryState(forexCode: string, state: ChunkedHistoryState | null) {
      this.forexCandles = state?.candles ?? []
      this.forexHasMoreHistory = state?.hasMoreHistory ?? false
      this.forexHistoryLoadingMore = Boolean(state?.pendingWindowKey)
      if (state) {
        this.forexHistoryByCode[forexCode] = state
      }
    },
    applyNetPositionSeriesState(state: ChunkedNetPositionSeriesState | null) {
      this.netPositionSeries = state?.series ?? null
      this.netPositionSeriesHasMoreHistory = state?.hasMoreHistory ?? false
      this.netPositionSeriesLoadingMore = Boolean(state?.pendingWindowKey)
      this.netPositionSeriesHistory = state
    },
    async loadSymbols() {
      this.symbols = await fetchSymbols()
      this.ensureDefaultStockSelection()
    },
    async initializeOverview() {
      this.error = ''
      try {
        const [indexOptions, forexOptions] = await Promise.all([fetchIndexOptions(), fetchForexOptions()])
        this.indexOptions = indexOptions
        this.forexOptions = forexOptions

        this.ensureDefaultIndexSelection()
        this.ensureDefaultForexSelection()

        await Promise.allSettled([this.loadIndexKline(), this.loadForexKline(), this.loadNetPositionTables()])
        void this.loadIndexEmotionPoints()
        void this.loadNetPositionSeries()
      } catch (error) {
        this.error = `初始化失败：${String(error)}`
      }
    },
    async initializeStocksPage() {
      this.error = ''
      try {
        await this.loadKline()
      } catch (error) {
        this.error = `初始化失败：${String(error)}`
      }
    },
    async loadKline() {
      if (!this.tsCode) return
      this.loading = true
      this.error = ''
      try {
        this.candles = await fetchKline(this.tsCode)
      } catch (error) {
        this.error = `加载股票 K 线失败：${String(error)}`
      } finally {
        this.loading = false
      }
    },
    async loadIndexEmotionPoints() {
      this.indexEmotionLoading = true
      try {
        this.indexEmotionPoints = await fetchIndexEmotions(monthsAgo(EMOTION_RECENT_MONTHS))
      } catch (error) {
        this.error = `加载指数情绪图失败：${String(error)}`
      } finally {
        this.indexEmotionLoading = false
      }
    },
    async loadNetPositionTables(tradeDate?: string) {
      this.netPositionLoading = true
      try {
        this.netPositionTables = await fetchCffexNetPositions(tradeDate)
        this.netPositionDate = this.netPositionTables?.citic_customer?.trade_date ?? tradeDate ?? ''
        return { ok: true as const }
      } catch (error: any) {
        const status = error?.response?.status
        if (status === 404) {
          return {
            ok: false as const,
            message: error?.response?.data?.detail ?? `${tradeDate ?? '所选日期'} 暂无中金所净持仓数据`,
          }
        }
        this.error = `加载中金所净持仓表失败：${String(error)}`
        return {
          ok: false as const,
          message: '加载中金所净持仓表失败，请稍后重试。',
        }
      } finally {
        this.netPositionLoading = false
      }
    },
    async loadNetPositionSeries() {
      this.netPositionSeriesLoading = true
      try {
        const recentSeries = await fetchCffexNetPositionSeries(monthsAgo(NET_POSITION_SERIES_RECENT_MONTHS))
        const cached = this.netPositionSeriesHistory
        const mergedSeries = mergeNetPositionSeries(cached?.series ?? null, recentSeries)
        this.applyNetPositionSeriesState(
          buildNetPositionSeriesState(mergedSeries, cached?.hasMoreHistory ?? Boolean(mergedSeries)),
        )
      } catch (error) {
        this.error = `加载中金所净空单折线图失败：${String(error)}`
      } finally {
        this.netPositionSeriesLoading = false
      }
    },
    async loadMoreNetPositionSeries() {
      const currentState = this.netPositionSeriesHistory
      if (!currentState?.earliestLoadedDate || !currentState.hasMoreHistory || currentState.pendingWindowKey) {
        return
      }

      const endDate = shiftDays(currentState.earliestLoadedDate, -1)
      const startDate = shiftMonths(endDate, -NET_POSITION_SERIES_RECENT_MONTHS)
      const windowKey = `${startDate}:${endDate}`
      this.applyNetPositionSeriesState({
        ...currentState,
        pendingWindowKey: windowKey,
      })

      try {
        const series = await fetchCffexNetPositionSeries(startDate, endDate)
        const mergedSeries = mergeNetPositionSeries(currentState.series, series)
        const nextEarliestTradeDate = extractEarliestNetPositionTradeDate(mergedSeries)
        const hasOlderHistory = Boolean(
          nextEarliestTradeDate && nextEarliestTradeDate < currentState.earliestLoadedDate,
        )
        this.applyNetPositionSeriesState(buildNetPositionSeriesState(mergedSeries, hasOlderHistory))
      } catch (error) {
        this.error = `加载更早中金所净空单折线图失败：${String(error)}`
        this.applyNetPositionSeriesState({
          ...currentState,
          pendingWindowKey: null,
        })
      }
    },
    async loadIndexKline() {
      if (!this.indexCode) return
      const cached = this.indexHistoryByCode[this.indexCode]
      if (cached?.candles.length) {
        this.applyIndexHistoryState(this.indexCode, cached)
        return
      }
      this.indexLoading = true
      this.error = ''
      try {
        const candles = await fetchIndexKline(this.indexCode, monthsAgo(INDEX_RECENT_MONTHS))
        this.applyIndexHistoryState(this.indexCode, buildChunkState(candles, candles.length > 0))
      } catch (error) {
        this.error = `加载指数 K 线失败：${String(error)}`
      } finally {
        this.indexLoading = false
      }
    },
    async loadMoreIndexHistory() {
      if (!this.indexCode) return
      const currentState = this.indexHistoryByCode[this.indexCode]
      if (!currentState?.earliestLoadedDate || !currentState.hasMoreHistory || currentState.pendingWindowKey) {
        return
      }

      const endDate = shiftDays(currentState.earliestLoadedDate, -1)
      const startDate = shiftMonths(endDate, -INDEX_RECENT_MONTHS)
      const windowKey = `${startDate}:${endDate}`
      this.applyIndexHistoryState(this.indexCode, {
        ...currentState,
        pendingWindowKey: windowKey,
      })

      try {
        const candles = await fetchIndexKline(this.indexCode, startDate, endDate)
        const mergedCandles = mergeCandles(currentState.candles, candles)
        const hasOlderCandles =
          candles.length > 0 &&
          Boolean(mergedCandles[0]?.trade_date) &&
          mergedCandles[0].trade_date < currentState.earliestLoadedDate
        this.applyIndexHistoryState(this.indexCode, buildChunkState(mergedCandles, hasOlderCandles))
      } catch (error) {
        this.error = `加载更早指数 K 线失败：${String(error)}`
        this.applyIndexHistoryState(this.indexCode, {
          ...currentState,
          pendingWindowKey: null,
        })
      }
    },
    async loadForexKline() {
      if (!this.forexCode) return
      const cached = this.forexHistoryByCode[this.forexCode]
      if (cached?.candles.length) {
        this.applyForexHistoryState(this.forexCode, cached)
        return
      }
      this.forexLoading = true
      this.error = ''
      try {
        const candles = await fetchForexKline(this.forexCode, monthsAgo(FOREX_RECENT_MONTHS))
        this.applyForexHistoryState(this.forexCode, buildChunkState(candles, candles.length > 0))
      } catch (error) {
        this.error = `加载汇率 K 线失败：${String(error)}`
      } finally {
        this.forexLoading = false
      }
    },
    async loadMoreForexHistory() {
      if (!this.forexCode) return
      const currentState = this.forexHistoryByCode[this.forexCode]
      if (!currentState?.earliestLoadedDate || !currentState.hasMoreHistory || currentState.pendingWindowKey) {
        return
      }

      const endDate = shiftDays(currentState.earliestLoadedDate, -1)
      const startDate = shiftMonths(endDate, -FOREX_RECENT_MONTHS)
      const windowKey = `${startDate}:${endDate}`
      this.applyForexHistoryState(this.forexCode, {
        ...currentState,
        pendingWindowKey: windowKey,
      })

      try {
        const candles = await fetchForexKline(this.forexCode, startDate, endDate)
        const mergedCandles = mergeCandles(currentState.candles, candles)
        const hasOlderCandles =
          candles.length > 0 &&
          Boolean(mergedCandles[0]?.trade_date) &&
          mergedCandles[0].trade_date < currentState.earliestLoadedDate
        this.applyForexHistoryState(this.forexCode, buildChunkState(mergedCandles, hasOlderCandles))
      } catch (error) {
        this.error = `加载更早汇率 K 线失败：${String(error)}`
        this.applyForexHistoryState(this.forexCode, {
          ...currentState,
          pendingWindowKey: null,
        })
      }
    },
    async collectCurrentForex() {
      const requestedCode = this.forexCode
      if (!requestedCode || this.forexCollecting) return null

      this.forexCollecting = true
      this.error = ''
      try {
        const result = await collectForexSymbol(requestedCode)
        delete this.forexHistoryByCode[requestedCode]
        if (this.forexCode === requestedCode) {
          await this.loadForexKline()
        }
        return result
      } catch (error) {
        this.error = `采集汇率失败：${String(error)}`
        return null
      } finally {
        this.forexCollecting = false
      }
    },
    async triggerCollect() {
      if (!this.tsCode) return
      const result = await submitCollectTask(this.tsCode, buildIdempotencyKey(this.tsCode))
      this.collectTaskId = result.task_id
      this.collectState = result.status
    },
    async refreshTaskStatus() {
      if (!this.collectTaskId) return
      const result = await fetchTaskStatus(this.collectTaskId)
      this.collectState = String(result.state ?? '')
    },
  },
})

