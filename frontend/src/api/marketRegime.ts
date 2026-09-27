import { http } from './client'
import type { MarketRegimeDashboard, RegimeIndex, MacroEvidenceResponse } from '../types/marketRegime'

export async function fetchMarketRegime(indexCode: RegimeIndex, signal?: AbortSignal) {
  const { data } = await http.get<{ data: MarketRegimeDashboard }>('/macro/market-regime', {
    params: { index_code: indexCode }, signal,
  })
  return data.data
}

export async function fetchMarketRegimeMacroEvidence(date: string, signal?: AbortSignal) {
  const { data } = await http.get<{ data: MacroEvidenceResponse }>('/macro/market-regime/macro-evidence', {
    params: { as_of_at: `${date}T22:45:00+08:00` }, signal,
  })
  return data.data
}
