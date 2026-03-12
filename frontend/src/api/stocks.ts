import { http } from './client'
import type { DbStatus, StockCandle, StockMeta, StockSymbol } from '../types/stock'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchDbStatus() {
  const { data } = await http.get<ApiResponse<DbStatus>>('/stocks/db-status')
  return data.data
}

export async function fetchSymbols(limit = 200) {
  const { data } = await http.get<ApiResponse<StockSymbol[]>>('/stocks/symbols', { params: { limit } })
  return data.data
}

export async function fetchMeta() {
  const { data } = await http.get<ApiResponse<StockMeta>>('/stocks/meta')
  return data.data
}

export async function fetchKline(tsCode: string) {
  const { data } = await http.get<ApiResponse<StockCandle[]>>(`/stocks/${tsCode}/kline`)
  return data.data
}

export async function submitCollectTask(tsCode: string, idempotencyKey: string) {
  const { data } = await http.post<ApiResponse<{ task_id: string; status: string }>>(
    '/stocks/collect',
    {
      ts_code: tsCode,
    },
    {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    },
  )
  return data.data
}

export async function fetchTaskStatus(taskId: string) {
  const { data } = await http.get<ApiResponse<Record<string, unknown>>>(`/stocks/collect/${taskId}`)
  return data.data
}
