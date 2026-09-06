import { http } from './client'
import type { MarketRegimeDashboard, RegimeIndex } from '../types/marketRegime'

export async function fetchMarketRegime(indexCode: RegimeIndex, signal?: AbortSignal) {
  const { data } = await http.get<{ data: MarketRegimeDashboard }>('/macro/market-regime', {
    params: { index_code: indexCode }, signal,
  })
  return data.data
}
