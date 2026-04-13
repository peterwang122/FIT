from datetime import datetime

from pydantic import BaseModel, Field


class SendSmsCodePayload(BaseModel):
    phone: str


class SmsLoginPayload(BaseModel):
    phone: str
    code: str = Field(min_length=4, max_length=8)


class AccountLoginPayload(BaseModel):
    account: str
    password: str = Field(min_length=6, max_length=128)


class SetPasswordPayload(BaseModel):
    password: str = Field(min_length=6, max_length=128)
    current_password: str | None = Field(default=None, min_length=6, max_length=128)


class UpdateProfilePayload(BaseModel):
    nickname: str = Field(default="", max_length=64)
    email: str | None = Field(default=None, max_length=128)
    company: str = Field(default="", max_length=128)
    bio: str = Field(default="", max_length=2000)


class UpdatePreferencesPayload(BaseModel):
    theme: str = Field(default="system", max_length=32)
    language: str = Field(default="zh-CN", max_length=32)
    notifications_enabled: bool = True
    default_homepage: str = Field(default="/", max_length=128)


class AuthPreferencesResponse(BaseModel):
    theme: str
    language: str
    notifications_enabled: bool
    default_homepage: str


class AuthUserResponse(BaseModel):
    id: int
    username: str
    phone: str | None = None
    role: str
    has_password: bool
    nickname: str = ""
    email: str | None = None
    company: str = ""
    bio: str = ""
    created_at: datetime | None = None
    last_login_at: datetime | None = None
    preferences: AuthPreferencesResponse


class AuthSessionResponse(BaseModel):
    user: AuthUserResponse


class AuthStatusResponse(BaseModel):
    status: str


class AuthSessionRecordResponse(BaseModel):
    id: int
    user_agent: str = ""
    ip_address: str = ""
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    is_current: bool = False
    is_active: bool = False


class UserSearchResultResponse(BaseModel):
    id: int
    username: str
    phone: str | None = None
    nickname: str = ""
    role: str
