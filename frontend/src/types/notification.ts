export type NotificationCategory =
  | 'strategy_received'
  | 'collection_required'
  | 'collection_ready'
  | 'codex_reset_watchdog'

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

export type CodexResetStatus = 'scheduled' | 'completed' | 'possible'

export interface CodexResetWatchdogHistoryItem {
  item_id: string
  text: string
  url: string | null
  author: string | null
  published_at: string | null
  translation_zh: string | null
  reset_status: CodexResetStatus | null
  reset_evidence: string | null
  archived_at: string | null
}

export interface CodexResetWatchdogHistory {
  source_handle: string
  max_items: number
  archived_count: number
  last_success_at: string | null
  items: CodexResetWatchdogHistoryItem[]
}
