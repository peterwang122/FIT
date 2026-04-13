from datetime import datetime

from pydantic import BaseModel, Field


class ProgressTodoItem(BaseModel):
    id: str
    text: str


class ProgressEntry(BaseModel):
    id: str
    text: str


class ProgressDay(BaseModel):
    id: str
    date: str
    title: str
    items: list[ProgressEntry] = Field(default_factory=list)


class ProgressBoardPayload(BaseModel):
    todo_items: list[ProgressTodoItem] = Field(default_factory=list)
    progress_days: list[ProgressDay] = Field(default_factory=list)


class ProgressBoardResponse(ProgressBoardPayload):
    updated_at: datetime | None = None
    updated_by_user_id: int | None = None
    updated_by_name: str | None = None
