import { defineStore } from 'pinia'

import { fetchDbStatus, fetchKline, fetchMeta, fetchSymbols, fetchTaskStatus, submitCollectTask } from '../api/stocks'
import type { DbStatus, StockCandle, StockMeta, StockSymbol } from '../types/stock'

function buildIdempotencyKey(tsCode: string): string {
  return `collect:${tsCode}:${new Date().toISOString().slice(0, 10)}`
}

export const useStockStore = defineStore('stock', {
  state: () => ({
    tsCode: '002594',
    searchKeyword: '',
    symbols: [] as StockSymbol[],
    candles: [] as StockCandle[],
    meta: null as StockMeta | null,
    dbStatus: null as DbStatus | null,
    loading: false,
    collectTaskId: '' as string,
    collectState: '' as string,
    error: '' as string,
  }),
  getters: {
    selectedSymbolName(state): string {
      return state.symbols.find((item) => item.ts_code === state.tsCode)?.stock_name ?? ''
    },
  },
  actions: {
    async initialize() {
      this.error = ''
      try {
        const [dbStatus, meta, symbols] = await Promise.all([fetchDbStatus(), fetchMeta(), fetchSymbols()])
        this.dbStatus = dbStatus
        this.meta = meta
        this.symbols = symbols
        if (!this.symbols.find((item) => item.ts_code === this.tsCode) && this.symbols.length > 0) {
          this.tsCode = this.symbols[0].ts_code
        }
        await this.loadKline()
      } catch (error) {
        this.error = `初始化失败：${String(error)}`
      }
    },
    async refreshDbStatus() {
      this.dbStatus = await fetchDbStatus()
    },
    async loadKline() {
      if (!this.tsCode) return
      this.loading = true
      this.error = ''
      try {
        this.candles = await fetchKline(this.tsCode)
      } catch (error) {
        this.error = `加载K线失败：${String(error)}`
      } finally {
        this.loading = false
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
