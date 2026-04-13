from sqlalchemy import BigInteger, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProgressBoard(Base):
    __tablename__ = "progress_boards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    todo_items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    progress_days: Mapped[list[dict]] = mapped_column(JSON, default=list)
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
