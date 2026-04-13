from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CollectionTaskRequest(Base):
    __tablename__ = "collection_task_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_scope: Mapped[str] = mapped_column(String(32), index=True, default="cn_stock")
    stock_code: Mapped[str] = mapped_column(String(32), index=True)
    stock_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    root_notification_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    resolved_task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    resolved_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
