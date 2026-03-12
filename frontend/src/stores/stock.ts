import { defineStore } from 'pinia'

import { fetchKline, fetchMeta, fetchSymbols, fetchTaskStatus, submitCollectTask } from '../api/stocks'
import type { StockCandle, StockMeta, StockSymbol } from '../types/stock'

function buildIdempotencyKey(tsCode: string): string {
  return `collect:${tsCode}:${new Date().toISOString().slice(0, 10)}`
}

export const useStockStore = defineStore('stock', {
  state: () => ({
    tsCode: '',
    symbols: [] as StockSymbol[],
    candles: [] as StockCandle[],
    meta: null as StockMeta | null,
    loading: false,
    collectTaskId: '' as string,
    collectState: '' as string,
    error: '' as string,
  }),
  actions: {
    async initialize() {
      this.error = ''
      try {
        const [symbols, meta] = await Promise.all([fetchSymbols(), fetchMeta()])
        this.symbols = symbols
        this.meta = meta
        if (!this.tsCode && symbols.length > 0) {
          this.tsCode = symbols[0].ts_code
        }
        if (this.tsCode) {
          await this.loadKline()
        }
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
