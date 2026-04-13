from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from functools import lru_cache


SUPPORTED_MARKET_SCOPES = {"cn_stock", "hk_stock", "us_stock"}
DEFAULT_MARKET_SCOPE = "cn_stock"


@dataclass(frozen=True)
class MarketCalendarRule:
    calendar_name: str
    open_time: time


MARKET_CALENDAR_RULES: dict[str, MarketCalendarRule] = {
    "cn_stock": MarketCalendarRule(calendar_name="XSHG", open_time=time(hour=9, minute=30)),
    "hk_stock": MarketCalendarRule(calendar_name="XHKG", open_time=time(hour=9, minute=30)),
    "us_stock": MarketCalendarRule(calendar_name="XNYS", open_time=time(hour=21, minute=30)),
}


class MarketCalendarService:
    def normalize_market_scope(self, market_scope: str | None) -> str:
        normalized = str(market_scope or "").strip().lower()
        if normalized in SUPPORTED_MARKET_SCOPES:
            return normalized
        return DEFAULT_MARKET_SCOPE

    def market_open_time(self, market_scope: str | None) -> time:
        scope = self.normalize_market_scope(market_scope)
        return MARKET_CALENDAR_RULES[scope].open_time

    def is_trading_day(self, market_scope: str | None, target_date: date) -> bool:
        scope = self.normalize_market_scope(market_scope)
        calendar_name = MARKET_CALENDAR_RULES[scope].calendar_name
        calendar = self._load_calendar(calendar_name)
        if calendar is None:
            return target_date.weekday() < 5
        schedule = calendar.schedule(start_date=target_date.isoformat(), end_date=target_date.isoformat())
        return not schedule.empty

    def next_trading_day(self, market_scope: str | None, target_date: date) -> date:
        current = target_date
        for _ in range(370):
            if self.is_trading_day(market_scope, current):
                return current
            current += timedelta(days=1)
        raise RuntimeError("unable to find next trading day")

    def previous_trading_day(self, market_scope: str | None, target_date: date) -> date:
        current = target_date - timedelta(days=1)
        for _ in range(370):
            if self.is_trading_day(market_scope, current):
                return current
            current -= timedelta(days=1)
        raise RuntimeError("unable to find previous trading day")

    @staticmethod
    @lru_cache(maxsize=8)
    def _load_calendar(calendar_name: str):
        try:
            import pandas_market_calendars as market_calendars
        except ImportError:
            return None
        try:
            return market_calendars.get_calendar(calendar_name)
        except Exception:
            return None
