import { http } from './client'
import type {
  Csi1000FuturesReport,
  VixOptionAnalysisReport,
  VixOptionContractKline,
} from '../types/research'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchVixOptionAnalysis() {
  const { data } = await http.get<ApiResponse<VixOptionAnalysisReport>>('/research/vix-option-analysis')
  return data.data
}

export async function fetchVixOptionContractKline(exchange: string, contractCode: string) {
  const { data } = await http.get<ApiResponse<VixOptionContractKline>>(
    `/research/vix-option-analysis/contracts/${encodeURIComponent(contractCode)}/candles`,
    { params: { exchange } },
  )
  return data.data
}

export async function fetchCsi1000FuturesAnalysis() {
  const { data } = await http.get<ApiResponse<Csi1000FuturesReport>>(
    '/research/csi1000-futures-analysis',
  )
  return data.data
}
