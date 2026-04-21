export interface ProgressTodoItem {
  id: string
  text: string
}

export interface ProgressUpdateLog {
  id: string
  title: string
  description: string
}

export interface ProgressRepoLog {
  id: string
  repo_label: 'FIT' | 'AkShare Project' | string
  repo_full_name: string
  updates: ProgressUpdateLog[]
}

export interface ProgressGenerationRepo {
  repo_label: 'FIT' | 'AkShare Project' | string
  repo_full_name: string
  base_ref: string | null
  head_ref: string
  commit_count: number
}

export interface ProgressGenerationMeta {
  generator: 'codex' | string
  scope: 'committed' | string
  grouping: 'repo_updates' | string
  granularity: 'summarized_from_pr_and_commit' | string
  generated_at: string | null
  repos: ProgressGenerationRepo[]
}

export interface ProgressDay {
  id: string
  date: string
  title: string
  repos: ProgressRepoLog[]
}

export interface ProgressBoardResponse {
  todo_items: ProgressTodoItem[]
  published_progress_days: ProgressDay[]
  published_generation_meta: ProgressGenerationMeta | null
  draft_progress_days?: ProgressDay[] | null
  draft_generation_meta?: ProgressGenerationMeta | null
  updated_at: string | null
  updated_by_user_id: number | null
  updated_by_name: string | null
  last_synced_at: string | null
  last_synced_by_user_id: number | null
  last_synced_by_name: string | null
  last_sync_status: 'never' | 'success' | 'failed' | string
  last_sync_error: string | null
  last_published_at: string | null
  last_published_by_user_id: number | null
  last_published_by_name: string | null
}

export interface ProgressBoardPayload {
  todo_items: ProgressTodoItem[]
  published_progress_days: ProgressDay[]
}

export interface ProgressTodoPayload {
  todo_items: ProgressTodoItem[]
}

export interface ProgressDraftPayload {
  draft_progress_days: ProgressDay[]
  generation_meta?: ProgressGenerationMeta | null
}
