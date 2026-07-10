import { http } from './client'
import type { VixOptionAnalysisReport } from '../types/research'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchVixOptionAnalysis() {
  const { data } = await http.get<ApiResponse<VixOptionAnalysisReport>>('/research/vix-option-analysis')
  return data.data
}
