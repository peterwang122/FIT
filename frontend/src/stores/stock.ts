import { defineStore } from 'pinia'

import {
  fetchCffexNetPositions,
  fetchCffexNetPositionSeries,
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
  NetPositionSeries,
  NetPositionTables,
  StockSymbol,
} from '../types/stock'

function buildIdempotencyKey(tsCode: string): string {
  return `collect:${tsCode}:${new Date().toISOString().slice(0, 10)}`
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
    indexCode: '',
    indexOptions: [] as MarketOption[],
    indexCandles: [] as KlineCandle[],
    forexCode: '',
    forexOptions: [] as MarketOption[],
    forexCandles: [] as KlineCandle[],
    loading: false,
    indexEmotionLoading: false,
    netPositionLoading: false,
    netPositionSeriesLoading: false,
    indexLoading: false,
    forexLoading: false,
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
    async initialize() {
      this.error = ''
      try {
        const [symbols, indexOptions, forexOptions] = await Promise.all([
          fetchSymbols(),
          fetchIndexOptions(),
          fetchForexOptions(),
        ])
        this.symbols = symbols
        this.indexOptions = indexOptions
        this.forexOptions = forexOptions

        if (!this.symbols.find((item) => item.ts_code === this.tsCode) && this.symbols.length > 0) {
          this.tsCode = this.symbols[0].ts_code
        }
        if (!this.indexOptions.find((item) => item.code === this.indexCode) && this.indexOptions.length > 0) {
          this.indexCode = this.indexOptions[0].code
        }
        if (!this.forexOptions.find((item) => item.code === this.forexCode) && this.forexOptions.length > 0) {
          this.forexCode = this.forexOptions[0].code
        }

        await Promise.all([
          this.loadKline(),
          this.loadIndexEmotionPoints(),
          this.loadNetPositionTables(),
          this.loadNetPositionSeries(),
          this.loadIndexKline(),
          this.loadForexKline(),
        ])
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
        this.indexEmotionPoints = await fetchIndexEmotions()
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
        this.netPositionSeries = await fetchCffexNetPositionSeries()
      } catch (error) {
        this.error = `加载中金所净空单折线图失败：${String(error)}`
      } finally {
        this.netPositionSeriesLoading = false
      }
    },
    async loadIndexKline() {
      if (!this.indexCode) return
      this.indexLoading = true
      this.error = ''
      try {
        this.indexCandles = await fetchIndexKline(this.indexCode)
      } catch (error) {
        this.error = `加载指数 K 线失败：${String(error)}`
      } finally {
        this.indexLoading = false
      }
    },
    async loadForexKline() {
      if (!this.forexCode) return
      this.forexLoading = true
      this.error = ''
      try {
        this.forexCandles = await fetchForexKline(this.forexCode)
      } catch (error) {
        this.error = `加载汇率 K 线失败：${String(error)}`
      } finally {
        this.forexLoading = false
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
