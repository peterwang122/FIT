from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo


SUPPORTED_MARKET_SCOPES = {"cn_stock", "hk_stock", "us_stock", "hk_index", "us_index"}
DEFAULT_MARKET_SCOPE = "cn_stock"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class MarketCalendarRule:
    calendar_name: str
    open_time: time
    timezone: ZoneInfo


MARKET_CALENDAR_RULES: dict[str, MarketCalendarRule] = {
    "cn_stock": MarketCalendarRule(
        calendar_name="XSHG",
        open_time=time(hour=9, minute=30),
        timezone=SHANGHAI_TZ,
    ),
    "hk_stock": MarketCalendarRule(
        calendar_name="XHKG",
        open_time=time(hour=9, minute=30),
        timezone=ZoneInfo("Asia/Hong_Kong"),
    ),
    "us_stock": MarketCalendarRule(
        calendar_name="XNYS",
        open_time=time(hour=21, minute=30),
        timezone=ZoneInfo("America/New_York"),
    ),
    "hk_index": MarketCalendarRule(
        calendar_name="XHKG",
        open_time=time(hour=9, minute=30),
        timezone=ZoneInfo("Asia/Hong_Kong"),
    ),
    "us_index": MarketCalendarRule(
        calendar_name="XNYS",
        open_time=time(hour=21, minute=30),
        timezone=ZoneInfo("America/New_York"),
    ),
}


class MarketCalendarService:
    def normalize_market_scope(self, market_scope: str | None) -> str:
        normalized = str(market_scope or "").strip().lower()
        if normalized == "hk_stock_index":
            normalized = "hk_index"
        if normalized == "us_stock_index":
            normalized = "us_index"
        if normalized in SUPPORTED_MARKET_SCOPES:
            return normalized
        return DEFAULT_MARKET_SCOPE

    def current_market_date(self, market_scope: str | None, reference_dt: datetime | None = None) -> date:
        scope = self.normalize_market_scope(market_scope)
        shanghai_now = self._ensure_shanghai_datetime(reference_dt)
        return shanghai_now.astimezone(MARKET_CALENDAR_RULES[scope].timezone).date()

    def market_open_time(self, market_scope: str | None, target_date: date | None = None) -> time:
        scope = self.normalize_market_scope(market_scope)
        fallback = MARKET_CALENDAR_RULES[scope].open_time
        if target_date is None:
            return fallback

        calendar_name = MARKET_CALENDAR_RULES[scope].calendar_name
        calendar = self._load_calendar(calendar_name)
        if calendar is None:
            return fallback

        try:
            schedule = calendar.schedule(start_date=target_date.isoformat(), end_date=target_date.isoformat())
        except Exception:
            return fallback
        if schedule.empty:
            return fallback

        market_open = schedule.iloc[0].get("market_open")
        if market_open is None:
            return fallback

        try:
            localized = market_open.tz_convert(SHANGHAI_TZ)
        except Exception:
            try:
                localized = market_open.tz_localize("UTC").tz_convert(SHANGHAI_TZ)
            except Exception:
                return fallback
        return localized.time().replace(tzinfo=None)

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

    @staticmethod
    def _ensure_shanghai_datetime(reference_dt: datetime | None) -> datetime:
        if reference_dt is None:
            return datetime.now(SHANGHAI_TZ)
        if reference_dt.tzinfo is None:
            return reference_dt.replace(tzinfo=SHANGHAI_TZ)
        return reference_dt.astimezone(SHANGHAI_TZ)
