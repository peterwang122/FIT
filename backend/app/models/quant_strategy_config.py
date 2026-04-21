from datetime import date

from sqlalchemy import BigInteger, Date, DateTime, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuantStrategyConfig(Base):
    __tablename__ = "quant_strategy_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    notes: Mapped[str] = mapped_column(String(1000), default="")
    strategy_engine: Mapped[str] = mapped_column(String(32), index=True, default="snapshot")
    sequence_mode: Mapped[str] = mapped_column(String(32), index=True, default="single_target")
    strategy_type: Mapped[str] = mapped_column(String(32), index=True)
    target_market: Mapped[str] = mapped_column(String(16), index=True, default="cn")
    target_code: Mapped[str] = mapped_column(String(32), index=True)
    target_name: Mapped[str] = mapped_column(String(128))
    indicator_params: Mapped[dict] = mapped_column(JSON, default=dict)
    buy_sequence_groups: Mapped[list[dict]] = mapped_column(JSON, default=list)
    sell_sequence_groups: Mapped[list[dict]] = mapped_column(JSON, default=list)
    scan_trade_config: Mapped[dict] = mapped_column(JSON, default=dict)
    blue_filter_groups: Mapped[list[dict]] = mapped_column(JSON, default=list)
    red_filter_groups: Mapped[list[dict]] = mapped_column(JSON, default=list)
    blue_filters: Mapped[dict] = mapped_column(JSON, default=dict)
    red_filters: Mapped[dict] = mapped_column(JSON, default=dict)
    blue_boll_filter: Mapped[dict] = mapped_column(JSON, default=dict)
    red_boll_filter: Mapped[dict] = mapped_column(JSON, default=dict)
    signal_buy_color: Mapped[str] = mapped_column(String(16), default="blue")
    signal_sell_color: Mapped[str] = mapped_column(String(16), default="red")
    purple_conflict_mode: Mapped[str] = mapped_column(String(32), default="sell_first")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scan_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scan_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    buy_position_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=1)
    sell_position_pct: Mapped[float] = mapped_column(Numeric(10, 4), default=1)
    execution_price_mode: Mapped[str] = mapped_column(String(32), default="next_open")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
