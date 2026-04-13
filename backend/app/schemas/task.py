from datetime import date, datetime

from pydantic import BaseModel, Field


class TaskCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    task_type: str = Field(min_length=1, max_length=32)
    market_scope: str = Field(default="cn_stock", min_length=1, max_length=32)
    schedule_time: str = Field(min_length=5, max_length=5)
    enabled: bool = True
    stock_code: str | None = Field(default=None, max_length=32)
    strategy_ids: list[int] = Field(default_factory=list)


class TaskUpdatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    task_type: str = Field(min_length=1, max_length=32)
    market_scope: str = Field(default="cn_stock", min_length=1, max_length=32)
    schedule_time: str = Field(min_length=5, max_length=5)
    enabled: bool = True
    stock_code: str | None = Field(default=None, max_length=32)
    strategy_ids: list[int] = Field(default_factory=list)


class TaskTogglePayload(BaseModel):
    enabled: bool


class ScheduledTaskRunResponse(BaseModel):
    id: int
    scheduled_task_id: int
    trigger_type: str
    status: str
    celery_task_id: str | None = None
    scheduled_for: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: str = ""
    error_message: str = ""
    created_at: datetime | None = None


class ScheduledTaskResponse(BaseModel):
    id: int
    owner_user_id: int
    task_type: str
    market_scope: str
    name: str
    enabled: bool
    schedule_time: str
    stock_code: str | None = None
    stock_name: str | None = None
    strategy_ids: list[int] = Field(default_factory=list)
    strategy_names: list[str] = Field(default_factory=list)
    target_email: str | None = None
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: str = ""
    last_run_summary: str = ""
    last_error_message: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RootVisibleStrategyResponse(BaseModel):
    id: int
    name: str
    notes: str = ""
    strategy_type: str
    target_code: str
    target_name: str
    start_date: date | None = None
    updated_at: datetime | None = None
    owner_user_id: int
    owner_username: str
    owner_nickname: str = ""
    owner_role: str
