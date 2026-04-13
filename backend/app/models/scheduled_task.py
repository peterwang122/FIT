from sqlalchemy import BigInteger, Boolean, Date, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    market_scope: Mapped[str] = mapped_column(String(32), index=True, default="cn_stock")
    name: Mapped[str] = mapped_column(String(128), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_time: Mapped[str] = mapped_column(String(5))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_scheduled_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    last_run_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(32), default="")
    last_run_summary: Mapped[str] = mapped_column(Text, default="")
    last_error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
