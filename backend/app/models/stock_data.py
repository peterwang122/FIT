from sqlalchemy import BigInteger, Date, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockData(Base):
    """日级后复权行情数据（来自外部采集服务）"""

    __tablename__ = "stock_data"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts_code: Mapped[str] = mapped_column(String(20), index=True)
    trade_date: Mapped[Date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Numeric(18, 4))
    high: Mapped[float] = mapped_column(Numeric(18, 4))
    low: Mapped[float] = mapped_column(Numeric(18, 4))
    close: Mapped[float] = mapped_column(Numeric(18, 4))
    pre_close: Mapped[float] = mapped_column(Numeric(18, 4))
    change: Mapped[float] = mapped_column(Numeric(18, 4))
    pct_chg: Mapped[float] = mapped_column(Numeric(18, 4))
    vol: Mapped[float] = mapped_column(Numeric(20, 4))
    amount: Mapped[float] = mapped_column(Numeric(20, 4))

    __table_args__ = (
        Index("idx_stock_data_code_date", "ts_code", "trade_date", unique=True),
    )
