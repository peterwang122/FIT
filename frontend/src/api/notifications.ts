import { http } from './client'
import type { NotificationListResponse, UserNotification } from '../types/notification'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function fetchNotifications() {
  const { data } = await http.get<ApiResponse<NotificationListResponse>>('/notifications')
  return data.data
}

export async function markNotificationRead(notificationId: number) {
  const { data } = await http.post<ApiResponse<UserNotification>>(`/notifications/${notificationId}/read`)
  return data.data
}

export async function markAllNotificationsRead() {
  const { data } = await http.post<ApiResponse<NotificationListResponse>>('/notifications/read-all')
  return data.data
}
