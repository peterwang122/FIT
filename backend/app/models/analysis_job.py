from sqlalchemy import BigInteger, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisJob(Base):
    """数据分析/深度学习任务模块预留"""

    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    payload: Mapped[dict] = mapped_column(JSON)
    result_uri: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
