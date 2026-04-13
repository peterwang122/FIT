import { defineStore } from 'pinia'

import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from '../api/notifications'
import type { NotificationListResponse, UserNotification } from '../types/notification'

function extractErrorMessage(error: unknown, fallback: string) {
  if (typeof error === 'object' && error !== null) {
    const candidate = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return fallback
}

export const useNotificationStore = defineStore('notifications', {
  state: () => ({
    items: [] as UserNotification[],
    unreadCount: 0,
    loading: false,
    pollTimer: null as number | null,
    initialized: false,
  }),
  actions: {
    async refresh() {
      this.loading = true
      try {
        const data = await fetchNotifications()
        this.items = data.items
        this.unreadCount = data.unread_count
        this.initialized = true
        return data
      } catch (error) {
        throw new Error(extractErrorMessage(error, '消息加载失败'))
      } finally {
        this.loading = false
      }
    },
    async refreshQuietly() {
      try {
        await this.refresh()
      } catch {
        // Ignore polling errors to keep the header stable.
      }
    },
    async markRead(notificationId: number) {
      try {
        const item = await markNotificationRead(notificationId)
        this.items = this.items.map((entry) => (entry.id === item.id ? item : entry))
        this.unreadCount = Math.max(this.unreadCount - 1, 0)
        return item
      } catch (error) {
        throw new Error(extractErrorMessage(error, '消息状态更新失败'))
      }
    },
    async markAllRead() {
      try {
        const data: NotificationListResponse = await markAllNotificationsRead()
        this.items = data.items
        this.unreadCount = data.unread_count
        return data
      } catch (error) {
        throw new Error(extractErrorMessage(error, '全部已读操作失败'))
      }
    },
    startPolling(intervalMs = 60000) {
      this.stopPolling()
      this.pollTimer = window.setInterval(() => {
        void this.refreshQuietly()
      }, intervalMs)
    },
    stopPolling() {
      if (this.pollTimer !== null) {
        window.clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },
    clear() {
      this.stopPolling()
      this.items = []
      this.unreadCount = 0
      this.loading = false
      this.initialized = false
    },
  },
})
