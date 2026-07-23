import { http } from './client'
import type { MacroDashboard } from '../types/macro'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchMacroDashboard(startDate?: string, endDate?: string) {
  const { data } = await http.get<ApiResponse<MacroDashboard>>('/macro/dashboard', {
    params: {
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    },
  })
  return data.data
}
