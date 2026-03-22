import { http } from './client'
import type {
  DbStatus,
  FuturesBasisPoint,
  IndexEmotionPoint,
  KlineCandle,
  MarketOption,
  NetPositionSeries,
  NetPositionTables,
  StockMeta,
  StockSymbol,
} from '../types/stock'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchDbStatus() {
  const { data } = await http.get<ApiResponse<DbStatus>>('/stocks/db-status')
  return data.data
}

export async function fetchSymbols(limit = 5000, keyword = '') {
  const { data } = await http.get<ApiResponse<StockSymbol[]>>('/stocks/symbols', { params: { limit, keyword } })
  return data.data
}

export async function fetchMeta() {
  const { data } = await http.get<ApiResponse<StockMeta>>('/stocks/meta')
  return data.data
}

export async function fetchKline(tsCode: string) {
  const { data } = await http.get<ApiResponse<KlineCandle[]>>(`/stocks/${tsCode}/kline`)
  return data.data
}

export async function fetchIndexOptions() {
  const { data } = await http.get<ApiResponse<MarketOption[]>>('/stocks/indexes/options')
  return data.data
}

export async function fetchIndexEmotions() {
  const { data } = await http.get<ApiResponse<IndexEmotionPoint[]>>('/stocks/index-emotions')
  return data.data
}

export async function fetchIndexFuturesBasis() {
  const { data } = await http.get<ApiResponse<FuturesBasisPoint[]>>('/stocks/index-futures-basis')
  return data.data
}

export async function fetchCffexNetPositions(tradeDate?: string) {
  const { data } = await http.get<ApiResponse<NetPositionTables>>('/stocks/cffex/net-positions', {
    params: tradeDate ? { trade_date: tradeDate } : undefined,
  })
  return data.data
}

export async function fetchCffexNetPositionSeries() {
  const { data } = await http.get<ApiResponse<NetPositionSeries>>('/stocks/cffex/net-position-series')
  return data.data
}

export async function fetchIndexKline(indexCode: string, startDate?: string, endDate?: string) {
  const { data } = await http.get<ApiResponse<KlineCandle[]>>(`/stocks/indexes/${indexCode}/kline`, {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
  })
  return data.data
}

export async function fetchForexOptions() {
  const { data } = await http.get<ApiResponse<MarketOption[]>>('/stocks/forex/options')
  return data.data
}

export async function fetchForexKline(symbolCode: string, startDate?: string, endDate?: string) {
  const { data } = await http.get<ApiResponse<KlineCandle[]>>(`/stocks/forex/${symbolCode}/kline`, {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
  })
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
