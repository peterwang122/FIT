from sqlalchemy import BigInteger, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BacktestJob(Base):
    """回测任务模块预留"""

    __tablename__ = "backtest_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(BigInteger, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    params: Mapped[dict] = mapped_column(JSON)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
