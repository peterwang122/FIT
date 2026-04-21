from datetime import datetime

from pydantic import BaseModel, Field


class ProgressTodoItem(BaseModel):
    id: str
    text: str


class ProgressUpdateLog(BaseModel):
    id: str
    title: str
    description: str


class ProgressRepoLog(BaseModel):
    id: str
    repo_label: str
    repo_full_name: str
    updates: list[ProgressUpdateLog] = Field(default_factory=list)


class ProgressGenerationRepo(BaseModel):
    repo_label: str
    repo_full_name: str
    base_ref: str | None = None
    head_ref: str
    commit_count: int = 0


class ProgressGenerationMeta(BaseModel):
    generator: str = "codex"
    scope: str = "committed"
    grouping: str = "repo_updates"
    granularity: str = "summarized_from_pr_and_commit"
    generated_at: datetime | None = None
    repos: list[ProgressGenerationRepo] = Field(default_factory=list)


class ProgressDay(BaseModel):
    id: str
    date: str
    title: str
    repos: list[ProgressRepoLog] = Field(default_factory=list)


class ProgressBoardPayload(BaseModel):
    todo_items: list[ProgressTodoItem] = Field(default_factory=list)
    published_progress_days: list[ProgressDay] = Field(default_factory=list)


class ProgressDraftPayload(BaseModel):
    draft_progress_days: list[ProgressDay] = Field(default_factory=list)
    generation_meta: ProgressGenerationMeta | None = None


class ProgressTodoPayload(BaseModel):
    todo_items: list[ProgressTodoItem] = Field(default_factory=list)


class ProgressBoardResponse(ProgressBoardPayload):
    draft_progress_days: list[ProgressDay] | None = None
    draft_generation_meta: ProgressGenerationMeta | None = None
    published_generation_meta: ProgressGenerationMeta | None = None
    updated_at: datetime | None = None
    updated_by_user_id: int | None = None
    updated_by_name: str | None = None
    last_synced_at: datetime | None = None
    last_synced_by_user_id: int | None = None
    last_synced_by_name: str | None = None
    last_sync_status: str = "never"
    last_sync_error: str | None = None
    last_published_at: datetime | None = None
    last_published_by_user_id: int | None = None
    last_published_by_name: str | None = None
