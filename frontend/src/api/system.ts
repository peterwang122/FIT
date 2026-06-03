import { http } from './client'
import type { PhddnsWatchdogStatus, PhddnsWatchdogTogglePayload } from '../types/system'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchPhddnsWatchdogStatus() {
  const { data } = await http.get<ApiResponse<PhddnsWatchdogStatus>>('/system/phddns-watchdog')
  return data.data
}

export async function updatePhddnsWatchdogStatus(payload: PhddnsWatchdogTogglePayload) {
  const { data } = await http.put<ApiResponse<PhddnsWatchdogStatus>>('/system/phddns-watchdog', payload)
  return data.data
}
