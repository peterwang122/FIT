import { http } from './client'
import type { RootVisibleStrategy, RootVisibleStrategyQuery, ScheduledTask, ScheduledTaskRun, TaskPayload } from '../types/tasks'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchTasks() {
  const { data } = await http.get<ApiResponse<ScheduledTask[]>>('/tasks')
  return data.data
}

export async function fetchTask(taskId: number) {
  const { data } = await http.get<ApiResponse<ScheduledTask>>(`/tasks/${taskId}`)
  return data.data
}

export async function createTask(payload: TaskPayload) {
  const { data } = await http.post<ApiResponse<ScheduledTask>>('/tasks', payload)
  return data.data
}

export async function updateTask(taskId: number, payload: TaskPayload) {
  const { data } = await http.put<ApiResponse<ScheduledTask>>(`/tasks/${taskId}`, payload)
  return data.data
}

export async function deleteTask(taskId: number) {
  const { data } = await http.delete<ApiResponse<{ id: number; status: string }>>(`/tasks/${taskId}`)
  return data.data
}

export async function toggleTask(taskId: number, enabled: boolean) {
  const { data } = await http.post<ApiResponse<ScheduledTask>>(`/tasks/${taskId}/toggle`, { enabled })
  return data.data
}

export async function runTaskNow(taskId: number) {
  const { data } = await http.post<ApiResponse<ScheduledTaskRun>>(`/tasks/${taskId}/run`)
  return data.data
}

export async function fetchTaskRuns(taskId: number) {
  const { data } = await http.get<ApiResponse<ScheduledTaskRun[]>>(`/tasks/${taskId}/runs`)
  return data.data
}

export async function fetchRootVisibleStrategies(params: RootVisibleStrategyQuery = {}) {
  const { data } = await http.get<ApiResponse<RootVisibleStrategy[]>>('/tasks/strategies', {
    params,
  })
  return data.data
}
