import type { QuantStrategyType } from './quant'

export type ScheduledTaskType = 'collection' | 'notification'
export type ScheduledTaskRunStatus = 'queued' | 'running' | 'success' | 'failed' | 'skipped'
export type ScheduledTaskTriggerType = 'schedule' | 'manual'
export type TaskMarketScope = 'cn_stock' | 'hk_index' | 'us_index'
export type CollectionCollectorKey =
  | 'stock_hfq_single'
  | 'stock_daily'
  | 'index_cn_daily'
  | 'index_bj50_daily'
  | 'cffex_daily'
  | 'forex_daily'
  | 'usd_index_daily'
  | 'futures_daily'
  | 'etf_daily'
  | 'option_daily'
  | 'quant_index_daily'
  | 'index_hk_daily'
  | 'index_us_daily'
  | 'hk_index_futures_daily'
  | 'us_index_futures_daily'
  | 'us_index_futures_official_daily'
  | 'index_qvix_daily'
  | 'index_news_sentiment_daily'
  | 'index_us_vix_daily'
  | 'index_us_fear_greed_daily'
  | 'index_us_hedge_proxy_daily'
  | 'index_us_put_call_ratio_daily'
  | 'index_us_treasury_yield_daily'
  | 'index_us_credit_spread_daily'
export type RootVisibleStrategyTypeFilter = QuantStrategyType | 'all'

export interface ScheduledTask {
  id: number
  owner_user_id: number
  task_type: ScheduledTaskType
  market_scope: TaskMarketScope
  collector_key: CollectionCollectorKey | null
  collection_label: string | null
  name: string
  enabled: boolean
  schedule_time: string
  target_type: 'stock' | 'index' | null
  target_code: string | null
  target_name: string | null
  stock_code: string | null
  stock_name: string | null
  strategy_ids: number[]
  strategy_names: string[]
  target_email: string | null
  next_run_at: string | null
  last_run_at: string | null
  last_run_status: string
  last_run_summary: string
  last_error_message: string
  created_at: string | null
  updated_at: string | null
}

export interface ScheduledTaskRun {
  id: number
  scheduled_task_id: number
  trigger_type: ScheduledTaskTriggerType
  status: ScheduledTaskRunStatus
  celery_task_id: string | null
  scheduled_for: string
  started_at: string | null
  finished_at: string | null
  summary: string
  error_message: string
  created_at: string | null
}

export interface TaskPayload {
  name: string
  task_type: ScheduledTaskType
  market_scope?: TaskMarketScope
  schedule_time: string
  enabled: boolean
  collector_key?: CollectionCollectorKey | null
  target_type?: 'stock' | 'index' | null
  target_code?: string | null
  target_name?: string | null
  stock_code?: string | null
  strategy_ids?: number[]
}

export interface TaskTogglePayload {
  enabled: boolean
}

export interface RootVisibleStrategy {
  id: number
  name: string
  notes: string
  strategy_type: QuantStrategyType
  target_code: string
  target_name: string
  start_date: string | null
  updated_at: string | null
  owner_user_id: number
  owner_username: string
  owner_nickname: string
  owner_role: 'user'
}

export interface RootVisibleStrategyQuery {
  keyword?: string
  user_id?: number | null
  username?: string
  strategy_type?: RootVisibleStrategyTypeFilter
}
