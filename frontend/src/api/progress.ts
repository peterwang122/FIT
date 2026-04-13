import { http } from './client'
import type { ProgressBoardPayload, ProgressBoardResponse } from '../types/progress'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchProgressBoard() {
  const { data } = await http.get<ApiResponse<ProgressBoardResponse>>('/progress')
  return data.data
}

export async function updateProgressBoard(payload: ProgressBoardPayload) {
  const { data } = await http.put<ApiResponse<ProgressBoardResponse>>('/progress', payload)
  return data.data
}
