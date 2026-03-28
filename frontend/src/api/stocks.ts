import { http } from './client'
import type {
  DbStatus,
  IndexDashboardResponse,
  FuturesBasisPoint,
  IndexBreadthPoint,
  IndexEmotionPoint,
  KlineCandle,
  MarketOption,
  NetPositionSeries,
  NetPositionTables,
  StockMeta,
  StockSymbol,
  TaskStatusResult,
  TaskSubmitResult,
} from '../types/stock'
import type { QuantEquityCurveResponse, QuantStrategyConfig, QuantStrategyPayload } from '../types/quant'

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

export async function fetchQfqKline(tsCode: string) {
  const { data } = await http.get<ApiResponse<KlineCandle[]>>(`/stocks/${tsCode}/qfq-kline`)
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

export async function fetchIndexBreadth() {
  const { data } = await http.get<ApiResponse<IndexBreadthPoint[]>>('/stocks/quant/index-breadth')
  return data.data
}

export async function fetchIndexDashboard(indexCode: string, mode: 'recent' | 'full' = 'recent') {
  const { data } = await http.get<ApiResponse<IndexDashboardResponse>>('/stocks/quant/index-dashboard', {
    params: {
      index_code: indexCode,
      mode,
    },
  })
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
  const { data } = await http.post<ApiResponse<TaskSubmitResult>>(
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
  const { data } = await http.get<ApiResponse<TaskStatusResult>>(`/stocks/collect/${taskId}`)
  return data.data
}

export async function submitQfqCollectTask(tsCode: string, idempotencyKey: string) {
  const { data } = await http.post<ApiResponse<TaskSubmitResult>>(
    '/stocks/qfq-collect',
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

export async function fetchQfqTaskStatus(taskId: string) {
  const { data } = await http.get<ApiResponse<TaskStatusResult>>(`/stocks/qfq-collect/${taskId}`)
  return data.data
}

export async function fetchQuantStrategies() {
  const { data } = await http.get<ApiResponse<QuantStrategyConfig[]>>('/stocks/quant/strategies')
  return data.data
}

export async function createQuantStrategy(payload: QuantStrategyPayload) {
  const { data } = await http.post<ApiResponse<QuantStrategyConfig>>('/stocks/quant/strategies', payload)
  return data.data
}

export async function updateQuantStrategy(strategyId: number, payload: QuantStrategyPayload) {
  const { data } = await http.put<ApiResponse<QuantStrategyConfig>>(`/stocks/quant/strategies/${strategyId}`, payload)
  return data.data
}

export async function deleteQuantStrategy(strategyId: number) {
  const { data } = await http.delete<ApiResponse<{ id: number; status: string }>>(
    `/stocks/quant/strategies/${strategyId}`,
  )
  return data.data
}

export async function fetchQuantStrategyEquityCurve(strategyId: number) {
  const { data } = await http.get<ApiResponse<QuantEquityCurveResponse>>(
    `/stocks/quant/strategies/${strategyId}/equity-curve`,
  )
  return data.data
}
