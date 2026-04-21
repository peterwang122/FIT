import { http } from './client'
import type {
  ProgressBoardPayload,
  ProgressBoardResponse,
  ProgressDraftPayload,
  ProgressTodoPayload,
} from '../types/progress'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchProgressBoard() {
  const { data } = await http.get<ApiResponse<ProgressBoardResponse>>('/progress')
  return data.data
}

export async function updateProgressTodo(payload: ProgressTodoPayload) {
  const { data } = await http.put<ApiResponse<ProgressBoardResponse>>('/progress/todo', payload)
  return data.data
}

export async function updateProgressDraft(payload: ProgressDraftPayload) {
  const { data } = await http.put<ApiResponse<ProgressBoardResponse>>('/progress/draft', payload)
  return data.data
}

export async function publishProgressBoard() {
  const { data } = await http.post<ApiResponse<ProgressBoardResponse>>('/progress/publish')
  return data.data
}

export async function resetProgressBoard() {
  const { data } = await http.post<ApiResponse<ProgressBoardResponse>>('/progress/reset')
  return data.data
}

// Legacy alias kept for older call sites.
export async function updateProgressBoard(payload: ProgressBoardPayload) {
  return updateProgressTodo({ todo_items: payload.todo_items })
}
