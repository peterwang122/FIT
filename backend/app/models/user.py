from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="user", index=True)
    nickname: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company: Mapped[str] = mapped_column(String(128), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    theme_preference: Mapped[str] = mapped_column(String(32), default="system")
    language_preference: Mapped[str] = mapped_column(String(32), default="zh-CN")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    default_homepage: Mapped[str] = mapped_column(String(128), default="/")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    last_login_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
