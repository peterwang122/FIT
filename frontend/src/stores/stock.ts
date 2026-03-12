import { defineStore } from 'pinia'

import type { StockCandle } from '../types/stock'
import { fetchKline, fetchTaskStatus, submitCollectTask } from '../api/stocks'

export const useStockStore = defineStore('stock', {
  state: () => ({
    tsCode: '000001.SZ',
    candles: [] as StockCandle[],
    loading: false,
    collectTaskId: '' as string,
    collectState: '' as string,
  }),
  actions: {
    async loadKline() {
      this.loading = true
      try {
        this.candles = await fetchKline(this.tsCode)
      } finally {
        this.loading = false
      }
    },
    async triggerCollect() {
      const result = await submitCollectTask(this.tsCode)
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
