from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScheduledTaskRun(Base):
    __tablename__ = "scheduled_task_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scheduled_task_id: Mapped[int] = mapped_column(BigInteger, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="queued")
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scheduled_for: Mapped[DateTime] = mapped_column(DateTime)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
