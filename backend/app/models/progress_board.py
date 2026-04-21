from sqlalchemy import BigInteger, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProgressBoard(Base):
    __tablename__ = "progress_boards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    todo_items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    progress_days: Mapped[list[dict]] = mapped_column(JSON, default=list)
    published_progress_days: Mapped[list[dict]] = mapped_column(JSON, default=list)
    draft_progress_days: Mapped[list[dict]] = mapped_column(JSON, default=list)
    published_generation_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    draft_generation_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_synced_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    last_synced_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_sync_status: Mapped[str] = mapped_column(String(32), default="never")
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_published_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    last_published_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
