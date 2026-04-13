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
import type {
  QuantEquityCurveResponse,
  QuantScanEventPage,
  QuantScanTargetHits,
  QuantSequenceGroupSet,
  QuantSequenceScanBacktestResponse,
  QuantSequenceScanPreviewResponse,
  QuantScanBacktestSelection,
  QuantScanTradeConfig,
  QuantStrategyConfig,
  QuantStrategyPayload,
  QuantStrategyType,
  QuantTargetOption,
} from '../types/quant'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const SCAN_REQUEST_TIMEOUT_MS = 300000

interface RequestOptions {
  signal?: AbortSignal
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

export async function fetchHfqKline(tsCode: string) {
  const { data } = await http.get<ApiResponse<KlineCandle[]>>(`/stocks/${tsCode}/hfq-kline`)
  return data.data
}

export async function fetchEtfKline(etfCode: string) {
  const { data } = await http.get<ApiResponse<KlineCandle[]>>(`/stocks/etfs/${etfCode}/kline`)
  return data.data
}

export async function fetchQuantTargets(targetType: 'index' | 'stock' | 'etf', keyword = '', limit = 50) {
  const { data } = await http.get<ApiResponse<QuantTargetOption[]>>('/stocks/quant/targets', {
    params: {
      target_type: targetType,
      keyword,
      limit,
    },
  })
  return data.data
}

export async function fetchIndexOptions() {
  const { data } = await http.get<ApiResponse<MarketOption[]>>('/stocks/indexes/options')
  return data.data
}

export async function fetchIndexEmotions(startDate?: string) {
  const { data } = await http.get<ApiResponse<IndexEmotionPoint[]>>('/stocks/index-emotions', {
    params: {
      start_date: startDate,
    },
  })
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

export async function fetchIndexDashboard(
  indexCode: string,
  options: {
    mode?: 'recent' | 'full'
    startDate?: string
    endDate?: string
  } = {},
) {
  const { data } = await http.get<ApiResponse<IndexDashboardResponse>>('/stocks/quant/index-dashboard', {
    params: {
      index_code: indexCode,
      mode: options.mode ?? 'recent',
      start_date: options.startDate,
      end_date: options.endDate,
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

export async function fetchCffexNetPositionSeries(startDate?: string) {
  const { data } = await http.get<ApiResponse<NetPositionSeries>>('/stocks/cffex/net-position-series', {
    params: {
      start_date: startDate,
    },
  })
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

export async function submitHfqCollectTask(tsCode: string, idempotencyKey: string) {
  const { data } = await http.post<ApiResponse<TaskSubmitResult>>(
    '/stocks/hfq-collect',
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

export async function fetchHfqTaskStatus(taskId: string) {
  const { data } = await http.get<ApiResponse<TaskStatusResult>>(`/stocks/hfq-collect/${taskId}`)
  return data.data
}

export async function fetchQuantStrategies() {
  const { data } = await http.get<ApiResponse<QuantStrategyConfig[]>>('/stocks/quant/strategies')
  return data.data
}

export async function fetchQuantStrategy(strategyId: number) {
  const { data } = await http.get<ApiResponse<QuantStrategyConfig>>(`/stocks/quant/strategies/${strategyId}`)
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

export async function sendQuantStrategy(strategyId: number, targetUsername: string) {
  const { data } = await http.post<ApiResponse<QuantStrategyConfig>>(`/stocks/quant/strategies/${strategyId}/send`, {
    target_username: targetUsername,
  })
  return data.data
}

export async function fetchQuantStrategyEquityCurve(strategyId: number) {
  const { data } = await http.get<ApiResponse<QuantEquityCurveResponse>>(
    `/stocks/quant/strategies/${strategyId}/equity-curve`,
  )
  return data.data
}

export async function previewQuantSequenceScan(payload: {
  strategy_type: QuantStrategyType
  buy_sequence_groups: QuantSequenceGroupSet
  scan_trade_config: QuantScanTradeConfig
  scan_start_date: string
  scan_end_date: string
}, options: RequestOptions = {}) {
  const { data } = await http.post<ApiResponse<QuantSequenceScanPreviewResponse>>(
    '/stocks/quant/sequence/scan-preview',
    payload,
    {
      timeout: SCAN_REQUEST_TIMEOUT_MS,
      signal: options.signal,
    },
  )
  return data.data
}

export async function fetchQuantSequenceScanEvents(
  scanResultId: string,
  page = 1,
  pageSize = 100,
  options: RequestOptions = {},
) {
  const { data } = await http.get<ApiResponse<QuantScanEventPage>>(
    `/stocks/quant/sequence/scan-results/${scanResultId}/events`,
    {
      params: {
        page,
        page_size: pageSize,
      },
      timeout: SCAN_REQUEST_TIMEOUT_MS,
      signal: options.signal,
    },
  )
  return data.data
}

export async function fetchQuantSequenceScanTargetHits(
  scanResultId: string,
  targetCode: string,
  options: RequestOptions = {},
) {
  const { data } = await http.get<ApiResponse<QuantScanTargetHits>>(
    `/stocks/quant/sequence/scan-results/${scanResultId}/targets/${targetCode}`,
    {
      timeout: SCAN_REQUEST_TIMEOUT_MS,
      signal: options.signal,
    },
  )
  return data.data
}

export async function backtestQuantSequenceScan(payload: {
  scan_result_id: string
  scan_trade_config: QuantScanTradeConfig
  selection: QuantScanBacktestSelection
  page?: number
  page_size?: number
}, options: RequestOptions = {}) {
  const { data } = await http.post<ApiResponse<QuantSequenceScanBacktestResponse>>(
    '/stocks/quant/sequence/scan-backtest',
    {
      scan_result_id: payload.scan_result_id,
      scan_trade_config: payload.scan_trade_config,
      use_all_events: payload.selection.use_all_events,
      excluded_event_ids: payload.selection.excluded_event_ids,
      page: payload.page,
      page_size: payload.page_size,
    },
    {
      timeout: SCAN_REQUEST_TIMEOUT_MS,
      signal: options.signal,
    },
  )
  return data.data
}
