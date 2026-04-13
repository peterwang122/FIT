export interface ProgressTodoItem {
  id: string
  text: string
}

export interface ProgressEntry {
  id: string
  text: string
}

export interface ProgressDay {
  id: string
  date: string
  title: string
  items: ProgressEntry[]
}

export interface ProgressBoardResponse {
  todo_items: ProgressTodoItem[]
  progress_days: ProgressDay[]
  updated_at: string | null
  updated_by_user_id: number | null
  updated_by_name: string | null
}

export interface ProgressBoardPayload {
  todo_items: ProgressTodoItem[]
  progress_days: ProgressDay[]
}
