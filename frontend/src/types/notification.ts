export type NotificationCategory = 'strategy_received' | 'collection_required' | 'collection_ready'

export interface UserNotification {
  id: number
  recipient_user_id: number
  category: NotificationCategory
  title: string
  body: string
  action_url: string | null
  action_label: string | null
  is_read: boolean
  dedupe_key: string | null
  payload_json: Record<string, unknown>
  created_at: string | null
  read_at: string | null
}

export interface NotificationListResponse {
  unread_count: number
  items: UserNotification[]
}
