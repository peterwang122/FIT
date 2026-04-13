from sqlalchemy import BigInteger, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CollectionTaskRequestLink(Base):
    __tablename__ = "collection_task_request_links"
    __table_args__ = (
        UniqueConstraint(
            "notification_task_id",
            "strategy_id",
            name="uq_collection_task_request_links_task_strategy",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(BigInteger, index=True)
    requester_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    notification_task_id: Mapped[int] = mapped_column(BigInteger, index=True)
    strategy_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
