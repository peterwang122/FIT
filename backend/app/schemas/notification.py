from datetime import datetime

from pydantic import BaseModel, Field


class UserNotificationResponse(BaseModel):
    id: int
    recipient_user_id: int
    category: str
    title: str
    body: str = ""
    action_url: str | None = None
    action_label: str | None = None
    is_read: bool
    dedupe_key: str | None = None
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    read_at: datetime | None = None


class NotificationListResponse(BaseModel):
    unread_count: int = 0
    items: list[UserNotificationResponse] = Field(default_factory=list)


class CodexResetWatchdogHistoryItemResponse(BaseModel):
    item_id: str
    text: str
    url: str | None = None
    author: str | None = None
    published_at: str | None = None
    translation_zh: str | None = None
    reset_status: str | None = None
    reset_evidence: str | None = None
    archived_at: str | None = None


class CodexResetWatchdogHistoryResponse(BaseModel):
    source_handle: str
    max_items: int = 30
    archived_count: int = 0
    last_success_at: str | None = None
    items: list[CodexResetWatchdogHistoryItemResponse] = Field(default_factory=list)
