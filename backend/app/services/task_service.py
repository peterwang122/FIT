import re
import smtplib
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
from app.models.user import User
from app.services.market_calendar_service import DEFAULT_MARKET_SCOPE, MarketCalendarService
from app.services.notification_service import NotificationService
from app.services.quant_service import QuantService
from app.services.stock_service import StockService
from app.tasks.collector import run_daily_collection_request, run_index_daily_collection_request, run_stock_hfq_collection_request

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
SCHEDULE_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
HK_INDEX_ALL_CODE = "ALL_HK_INDEX"
US_INDEX_ALL_CODE = "ALL_US_INDEX"
HK_INDEX_ALL_NAME = "港股指数全市场"
US_INDEX_ALL_NAME = "美股指数全市场"

COLLECTION_TASK_DEFINITIONS: dict[str, dict[str, str | bool | None]] = {
    "stock_hfq_single": {
        "label": "A股股票单只 HFQ 采集",
        "market_scope": "cn_stock",
        "target_type": "stock",
        "requires_target": True,
        "endpoint": "/collect",
    },
    "stock_daily": {
        "label": "股票日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-stock-daily",
    },
    "index_cn_daily": {
        "label": "A股指数日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-cn-daily",
    },
    "index_bj50_daily": {
        "label": "北证50日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-bj50-daily",
    },
    "cffex_daily": {
        "label": "中金所会员持仓日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-cffex-daily",
    },
    "forex_daily": {
        "label": "汇率日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-forex-daily",
    },
    "usd_index_daily": {
        "label": "美元指数日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-usd-index-daily",
    },
    "futures_daily": {
        "label": "中金所期货日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-futures-daily",
    },
    "etf_daily": {
        "label": "ETF 日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-etf-daily",
    },
    "option_daily": {
        "label": "中金所期权日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-option-daily",
    },
    "quant_index_daily": {
        "label": "量化指数看板日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-quant-index-daily",
    },
    "index_hk_daily": {
        "label": "港股指数日更",
        "market_scope": "hk_index",
        "target_type": "index",
        "requires_target": False,
        "endpoint": "/collect-index-hk-daily",
    },
    "index_us_daily": {
        "label": "美股指数日更",
        "market_scope": "us_index",
        "target_type": "index",
        "requires_target": False,
        "endpoint": "/collect-index-us-daily",
    },
    "hk_index_futures_daily": {
        "label": "港股股指期货日更",
        "market_scope": "hk_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-hk-index-futures-daily",
    },
    "us_index_futures_daily": {
        "label": "美股股指期货日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-us-index-futures-daily",
    },
    "index_qvix_daily": {
        "label": "QVIX 日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-qvix-daily",
    },
    "index_news_sentiment_daily": {
        "label": "新闻情绪日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-news-sentiment-daily",
    },
    "index_us_vix_daily": {
        "label": "美股 VIX 日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-vix-daily",
    },
    "index_us_fear_greed_daily": {
        "label": "美股恐贪指数日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-fear-greed-daily",
    },
    "index_us_hedge_proxy_daily": {
        "label": "美股对冲基金代理日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-hedge-proxy-daily",
    },
}

COLLECTION_TASK_LABEL_OVERRIDES = {
    "stock_hfq_single": "A股股票单只 HFQ 采集",
    "stock_daily": "股票日更",
    "index_cn_daily": "A股指数日更",
    "index_bj50_daily": "北证50日更",
    "cffex_daily": "中金所会员持仓日更",
    "forex_daily": "汇率日更",
    "usd_index_daily": "美元指数日更",
    "futures_daily": "中金所期货日更",
    "etf_daily": "ETF 日更",
    "option_daily": "中金所期权日更",
    "quant_index_daily": "量化指数看板日更",
    "index_hk_daily": "港股指数日更",
    "index_us_daily": "美股指数日更",
    "hk_index_futures_daily": "港股股指期货日更",
    "us_index_futures_daily": "美股股指期货日更",
    "index_qvix_daily": "QVIX 日更",
    "index_news_sentiment_daily": "新闻情绪日更",
    "index_us_vix_daily": "美股 VIX 日更",
    "index_us_fear_greed_daily": "美股恐贪指数日更",
    "index_us_hedge_proxy_daily": "美股对冲基金代理日更",
}
for _collector_key, _label in COLLECTION_TASK_LABEL_OVERRIDES.items():
    if _collector_key in COLLECTION_TASK_DEFINITIONS:
        COLLECTION_TASK_DEFINITIONS[_collector_key]["label"] = _label


class TaskService:
    def __init__(self, db: Session):
        self.db = db
        self.quant_service = QuantService(db)
        self.stock_service = StockService(db)
        self.market_calendar = MarketCalendarService()
        self.notification_service = NotificationService(db)

    def _get_collection_definition(self, collector_key: str | None) -> dict[str, str | bool | None]:
        normalized_key = str(collector_key or "").strip().lower()
        definition = COLLECTION_TASK_DEFINITIONS.get(normalized_key)
        if definition is None:
            raise ValueError("unsupported collection collector_key")
        return definition

    def _normalize_collector_key(
        self,
        collector_key: str | None,
        market_scope: str | None,
        target_type: str | None = None,
        target_code: str | None = None,
        target_name: str | None = None,
        task_name: str | None = None,
    ) -> str:
        normalized_key = str(collector_key or "").strip().lower()
        if normalized_key in COLLECTION_TASK_DEFINITIONS:
            return normalized_key

        normalized_scope = self._normalize_market_scope(market_scope)
        normalized_type = str(target_type or "").strip().lower()
        normalized_code = str(target_code or "").strip()
        legacy_inferred = self._infer_legacy_collector_key(
            market_scope=normalized_scope,
            target_type=normalized_type,
            target_code=normalized_code,
            target_name=target_name,
            task_name=task_name,
        )
        if legacy_inferred:
            return legacy_inferred
        if normalized_scope == "cn_stock" and (normalized_type == "stock" or normalized_code):
            return "stock_hfq_single"
        raise ValueError("collector_key is required for collection tasks")

    def _infer_legacy_collector_key(
        self,
        *,
        market_scope: str,
        target_type: str,
        target_code: str,
        target_name: str | None = None,
        task_name: str | None = None,
    ) -> str | None:
        normalized_name = " ".join(
            part.strip()
            for part in [task_name or "", target_name or "", target_code or ""]
            if str(part or "").strip()
        )
        lowered_name = normalized_name.lower()
        is_futures_task = "期货" in normalized_name or "futures" in lowered_name

        if "港股" in normalized_name:
            if is_futures_task:
                return "hk_index_futures_daily"
            return "index_hk_daily"

        if "美股" in normalized_name or "us " in lowered_name or "u.s." in lowered_name:
            if is_futures_task:
                return "us_index_futures_daily"
            if "hedge" in lowered_name or "对冲" in normalized_name:
                return "index_us_hedge_proxy_daily"
            if "fear" in lowered_name or "greed" in lowered_name or "恐贪" in normalized_name:
                return "index_us_fear_greed_daily"
            if "vix" in lowered_name:
                return "index_us_vix_daily"
            if "指数" in normalized_name:
                return "index_us_daily"

        if market_scope == "hk_index":
            if is_futures_task:
                return "hk_index_futures_daily"
            return "index_hk_daily"

        if market_scope == "us_index":
            if is_futures_task:
                return "us_index_futures_daily"
            if "hedge" in lowered_name or "对冲" in normalized_name:
                return "index_us_hedge_proxy_daily"
            if "fear" in lowered_name or "greed" in lowered_name or "恐贪" in normalized_name:
                return "index_us_fear_greed_daily"
            if "vix" in lowered_name:
                return "index_us_vix_daily"
            return "index_us_daily"

        if market_scope == "cn_stock":
            if "\u5317\u8bc1" in normalized_name or "899050" in lowered_name:
                return "index_bj50_daily"
            if "qvix" in lowered_name:
                return "index_qvix_daily"
            if "新闻" in normalized_name or "情绪" in normalized_name:
                return "index_news_sentiment_daily"
            if "量化" in normalized_name and "看板" in normalized_name:
                return "quant_index_daily"
            if "期权" in normalized_name:
                return "option_daily"
            if "会员持仓" in normalized_name:
                return "cffex_daily"
            if "期货" in normalized_name:
                return "futures_daily"
            if "美元指数" in normalized_name or ("美元" in normalized_name and "指数" in normalized_name):
                return "usd_index_daily"
            if "汇率" in normalized_name or "forex" in lowered_name:
                return "forex_daily"
            if "etf" in lowered_name:
                return "etf_daily"
            if "股票日更" in normalized_name:
                return "stock_daily"
            if "指数日更" in normalized_name or "a股指数" in lowered_name:
                return "index_cn_daily"
            if target_type == "stock" or target_code:
                return "stock_hfq_single"
        return None

    def _collection_market_scope(self, collector_key: str) -> str:
        definition = self._get_collection_definition(collector_key)
        return self._normalize_market_scope(str(definition["market_scope"]))

    def _is_single_stock_collection(self, task: ScheduledTask | None = None, config: dict | None = None) -> bool:
        target_config = config if config is not None else (task.config_json if task is not None else {}) or {}
        market_scope = task.market_scope if task is not None else None
        collector_key = self._normalize_collector_key(
            target_config.get("collector_key"),
            market_scope,
            target_config.get("target_type"),
            target_config.get("target_code") or target_config.get("stock_code"),
            target_config.get("target_name"),
            task.name if task is not None else None,
        )
        return collector_key == "stock_hfq_single"

    def _now(self) -> datetime:
        return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)

    def _format_schedule_time(self, raw_value: str) -> str:
        value = raw_value.strip()
        if not SCHEDULE_TIME_PATTERN.match(value):
            raise ValueError("schedule_time must be in HH:MM format")
        return value

    def _parse_schedule_parts(self, raw_value: str) -> tuple[int, int]:
        normalized = self._format_schedule_time(raw_value)
        hours_text, minutes_text = normalized.split(":")
        return int(hours_text), int(minutes_text)

    def _scheduled_for_today(self, schedule_time: str, now: datetime) -> datetime:
        hour, minute = self._parse_schedule_parts(schedule_time)
        return datetime.combine(now.date(), time(hour=hour, minute=minute))

    def _due_scheduled_for(self, task: ScheduledTask, now: datetime) -> datetime | None:
        if not task.enabled:
            return None

        scheduled_for = self._scheduled_for_today(task.schedule_time, now)
        if scheduled_for > now:
            return None

        return scheduled_for

    def _normalize_market_scope(self, raw_value: str | None) -> str:
        return self.market_calendar.normalize_market_scope(raw_value)

    def _effective_task_market_scope(self, task: ScheduledTask, config: dict | None = None) -> str:
        if task.task_type != "collection":
            return self._normalize_market_scope(task.market_scope)

        target_config = config if config is not None else (task.config_json or {})
        try:
            collector_key = self._normalize_collector_key(
                target_config.get("collector_key"),
                task.market_scope,
                target_config.get("target_type"),
                target_config.get("target_code") or target_config.get("stock_code"),
                target_config.get("target_name"),
                task.name,
            )
            return self._collection_market_scope(collector_key)
        except ValueError:
            return self._normalize_market_scope(task.market_scope)

    def _resolve_index_name(self, target_code: str | None, market_scope: str | None) -> str | None:
        normalized = str(target_code or "").strip()
        if not normalized:
            normalized_scope = self._normalize_market_scope(market_scope)
            if normalized_scope == "hk_index":
                return HK_INDEX_ALL_NAME
            if normalized_scope == "us_index":
                return US_INDEX_ALL_NAME
            return None
        normalized_scope = self._normalize_market_scope(market_scope)
        if normalized_scope == "hk_index" and normalized == HK_INDEX_ALL_CODE:
            return HK_INDEX_ALL_NAME
        if normalized_scope == "us_index" and normalized == US_INDEX_ALL_CODE:
            return US_INDEX_ALL_NAME
        market = "hk" if normalized_scope == "hk_index" else "us"
        for item in self.stock_service.list_index_options(market=market):
            if str(item.get("code", "")).strip() == normalized:
                return str(item.get("name", "")).strip() or None
        return None

    def _resolve_collection_target_name(
        self,
        target_type: str | None,
        target_code: str | None,
        market_scope: str | None,
    ) -> str | None:
        normalized_type = str(target_type or "").strip().lower()
        if normalized_type == "stock":
            return self._resolve_stock_name(target_code)
        if normalized_type == "index":
            return self._resolve_index_name(target_code, market_scope)
        return None

    def _resolve_stock_name(self, stock_code: str | None) -> str | None:
        normalized = str(stock_code or "").strip()
        if not normalized:
            return None
        candidates = self.stock_service.search_symbols(keyword=normalized, limit=20)
        for item in candidates:
            if str(item.get("ts_code", "")).strip() == normalized:
                return str(item.get("stock_name", "")).strip() or None
        return None

    def _serialize_run(self, item: ScheduledTaskRun) -> dict:
        return {
            "id": item.id,
            "scheduled_task_id": item.scheduled_task_id,
            "trigger_type": item.trigger_type,
            "status": item.status,
            "celery_task_id": item.celery_task_id,
            "scheduled_for": item.scheduled_for,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "summary": item.summary or "",
            "error_message": item.error_message or "",
            "created_at": item.created_at,
        }

    def _resolve_strategy_names(self, strategy_ids: list[int], owner_user_id: int) -> list[str]:
        if not strategy_ids:
            return []
        items = (
            self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == owner_user_id,
                QuantStrategyConfig.id.in_(strategy_ids),
            )
            .order_by(QuantStrategyConfig.updated_at.desc())
            .all()
        )
        name_map = {item.id: item.name for item in items}
        return [name_map[strategy_id] for strategy_id in strategy_ids if strategy_id in name_map]

    def _compute_next_run_at_for_scope(self, market_scope: str, schedule_time: str) -> datetime:
        hour, minute = self._parse_schedule_parts(schedule_time)
        now = self._now()
        today = now.date()
        today_candidate = datetime.combine(today, time(hour=hour, minute=minute))
        if self.market_calendar.is_trading_day(market_scope, today) and today_candidate > now:
            return today_candidate

        next_trade_date = self.market_calendar.next_trading_day(market_scope, today + timedelta(days=1))
        return datetime.combine(next_trade_date, time(hour=hour, minute=minute))

    def _notification_basis_trade_date(self, market_scope: str, run_at: datetime) -> date:
        market_open = self.market_calendar.market_open_time(market_scope, run_at.date())
        if run_at.time() < market_open:
            return self.market_calendar.previous_trading_day(market_scope, run_at.date())
        return run_at.date()

    def _compute_next_run_at(self, item: ScheduledTask) -> datetime | None:
        if not item.enabled:
            return None
        market_scope = self._effective_task_market_scope(item)
        return self._compute_next_run_at_for_scope(market_scope, item.schedule_time)

    def _serialize_task(self, item: ScheduledTask) -> dict:
        config = item.config_json or {}
        collector_key = None
        collection_label = None
        if item.task_type == "collection":
            collector_key = self._normalize_collector_key(
                config.get("collector_key"),
                item.market_scope,
                config.get("target_type"),
                config.get("target_code") or config.get("stock_code"),
                config.get("target_name"),
                item.name,
            )
            collection_label = str(self._get_collection_definition(collector_key).get("label") or "").strip() or None
        target_type = str(config.get("target_type", "")).strip() or None
        target_code = str(config.get("target_code", "")).strip() or None
        target_name = str(config.get("target_name", "")).strip() or None
        stock_code = str(config.get("stock_code", "")).strip() or None
        if stock_code and not target_code:
            target_code = stock_code
        if stock_code and not target_type:
            target_type = "stock"
        if target_type == "stock" and target_code and not stock_code:
            stock_code = target_code
        resolved_target_name = target_name or self._resolve_collection_target_name(target_type, target_code, item.market_scope)
        strategy_ids = [
            int(raw_id)
            for raw_id in config.get("strategy_ids", [])
            if isinstance(raw_id, int) or str(raw_id).isdigit()
        ]
        owner = self.db.get(User, item.owner_user_id) if item.task_type == "notification" else None
        return {
            "id": item.id,
            "owner_user_id": item.owner_user_id,
            "task_type": item.task_type,
            "market_scope": self._effective_task_market_scope(item, config),
            "collector_key": collector_key,
            "collection_label": collection_label,
            "name": item.name,
            "enabled": bool(item.enabled),
            "schedule_time": item.schedule_time,
            "target_type": target_type,
            "target_code": target_code,
            "target_name": resolved_target_name,
            "stock_code": stock_code,
            "stock_name": resolved_target_name if target_type == "stock" else None,
            "strategy_ids": strategy_ids,
            "strategy_names": self._resolve_strategy_names(strategy_ids, item.owner_user_id),
            "target_email": str((owner.email if owner else None) or config.get("target_email", "")).strip() or None,
            "next_run_at": self._compute_next_run_at(item),
            "last_run_at": item.last_run_at,
            "last_run_status": item.last_run_status or "",
            "last_run_summary": item.last_run_summary or "",
            "last_error_message": item.last_error_message or "",
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def list_root_visible_strategies(
        self,
        *,
        keyword: str = "",
        user_id: int | None = None,
        username: str | None = None,
        strategy_type: str = "stock",
    ) -> list[dict]:
        query = (
            self.db.query(QuantStrategyConfig, User)
            .join(User, QuantStrategyConfig.owner_user_id == User.id)
            .filter(User.role == "user")
        )

        normalized_user_id = int(user_id) if user_id else None
        normalized_username = str(username or "").strip()
        normalized_keyword = str(keyword or "").strip()
        normalized_strategy_type = str(strategy_type or "").strip().lower()

        if normalized_user_id:
            query = query.filter(User.id == normalized_user_id)

        if normalized_username:
            like_value = f"%{normalized_username}%"
            query = query.filter(
                or_(
                    User.username.like(like_value),
                    User.nickname.like(like_value),
                    User.phone.like(like_value),
                )
            )

        if normalized_strategy_type and normalized_strategy_type != "all":
            query = query.filter(QuantStrategyConfig.strategy_type == normalized_strategy_type)

        if normalized_keyword:
            like_value = f"%{normalized_keyword}%"
            query = query.filter(
                or_(
                    QuantStrategyConfig.name.like(like_value),
                    QuantStrategyConfig.target_code.like(like_value),
                    QuantStrategyConfig.target_name.like(like_value),
                    User.username.like(like_value),
                    User.nickname.like(like_value),
                    User.phone.like(like_value),
                )
            )

        rows = query.order_by(QuantStrategyConfig.updated_at.desc(), QuantStrategyConfig.id.desc()).all()
        return [
            {
                "id": strategy.id,
                "name": strategy.name,
                "notes": strategy.notes or "",
                "strategy_type": strategy.strategy_type,
                "target_code": strategy.target_code,
                "target_name": strategy.target_name,
                "start_date": strategy.start_date,
                "updated_at": strategy.updated_at,
                "owner_user_id": owner.id,
                "owner_username": owner.username,
                "owner_nickname": owner.nickname or "",
                "owner_role": owner.role,
            }
            for strategy, owner in rows
        ]

    def _get_owned_task(self, task_id: int, owner_user_id: int) -> ScheduledTask:
        item = (
            self.db.query(ScheduledTask)
            .filter(ScheduledTask.id == task_id, ScheduledTask.owner_user_id == owner_user_id)
            .first()
        )
        if item is None:
            raise LookupError("task not found")
        return item

    def _assert_create_permission(self, task_type: str, current_user: User) -> None:
        if task_type == "collection":
            if current_user.role != "root":
                raise PermissionError("only root can create collection tasks")
            return
        if task_type == "notification":
            if current_user.role == "guest":
                raise PermissionError("guest users cannot create notification tasks")
            return
        raise ValueError("unsupported task type")

    def _normalize_notification_strategy_ids(self, strategy_ids: list[int], owner_user_id: int) -> list[int]:
        normalized_ids: list[int] = []
        for raw_id in strategy_ids:
            parsed = int(raw_id)
            if parsed not in normalized_ids:
                normalized_ids.append(parsed)
        if not normalized_ids:
            raise ValueError("notification tasks require at least one strategy")
        matched_ids = {
            item.id
            for item in self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == owner_user_id,
                QuantStrategyConfig.id.in_(normalized_ids),
            )
            .all()
        }
        if len(matched_ids) != len(normalized_ids):
            raise ValueError("notification tasks can only target your own strategies")
        return normalized_ids

    def _build_config(self, payload: dict, current_user: User) -> tuple[str, dict]:
        task_type = str(payload.get("task_type", "")).strip()
        self._assert_create_permission(task_type, current_user)

        if task_type == "collection":
            target_code = str(payload.get("target_code") or payload.get("stock_code") or "").strip()
            target_type = str(payload.get("target_type", "")).strip().lower()
            target_name = str(payload.get("target_name", "")).strip()
            collector_key = self._normalize_collector_key(
                payload.get("collector_key"),
                payload.get("market_scope"),
                target_type,
                target_code,
                target_name,
                payload.get("name"),
            )
            definition = self._get_collection_definition(collector_key)
            market_scope = self._collection_market_scope(collector_key)
            requires_target = bool(definition.get("requires_target"))
            normalized_target_type = str(definition.get("target_type") or "").strip().lower() or None

            if requires_target:
                if not target_code:
                    raise ValueError("target_code is required for collection tasks")
                if not normalized_target_type:
                    normalized_target_type = target_type or "stock"
                if normalized_target_type != "stock":
                    raise ValueError("cn_stock collection tasks must target stocks")
            else:
                if collector_key == "index_hk_daily":
                    target_code = HK_INDEX_ALL_CODE
                    target_name = HK_INDEX_ALL_NAME
                    normalized_target_type = "index"
                elif collector_key == "index_us_daily":
                    target_code = US_INDEX_ALL_CODE
                    target_name = US_INDEX_ALL_NAME
                    normalized_target_type = "index"
                else:
                    target_code = ""
                    target_name = ""
                    normalized_target_type = None

            resolved_name = target_name or self._resolve_collection_target_name(normalized_target_type, target_code, market_scope)
            return market_scope, {
                "collector_key": collector_key,
                "target_type": normalized_target_type,
                "target_code": target_code or None,
                "target_name": resolved_name,
                "stock_code": target_code if normalized_target_type == "stock" else None,
            }

        target_email = str(current_user.email or "").strip()
        if not target_email:
            raise ValueError("please set your email in account center before enabling notification tasks")
        strategy_ids = self._normalize_notification_strategy_ids(payload.get("strategy_ids") or [], current_user.id)
        return self._normalize_market_scope(payload.get("market_scope")), {
            "strategy_ids": strategy_ids,
            "target_email": target_email,
        }

    def list_tasks(self, owner_user_id: int) -> list[dict]:
        items = (
            self.db.query(ScheduledTask)
            .filter(ScheduledTask.owner_user_id == owner_user_id)
            .order_by(ScheduledTask.updated_at.desc(), ScheduledTask.id.desc())
            .all()
        )
        return [self._serialize_task(item) for item in items]

    def get_task(self, task_id: int, owner_user_id: int) -> dict:
        item = self._get_owned_task(task_id, owner_user_id)
        return self._serialize_task(item)

    def create_task(self, payload: dict, current_user: User) -> dict:
        market_scope, config_json = self._build_config(
            {**payload, "market_scope": payload.get("market_scope", DEFAULT_MARKET_SCOPE)},
            current_user,
        )
        item = ScheduledTask(
            owner_user_id=current_user.id,
            task_type=str(payload.get("task_type", "")).strip(),
            market_scope=market_scope,
            name=str(payload.get("name", "")).strip(),
            enabled=bool(payload.get("enabled", True)),
            schedule_time=self._format_schedule_time(str(payload.get("schedule_time", "")).strip()),
            config_json=config_json,
            last_run_status="",
            last_run_summary="",
            last_error_message="",
        )
        if not item.name:
            raise ValueError("task name is required")
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        if item.task_type == "notification":
            self.notification_service.sync_notification_task_requirements(item)
        elif item.task_type == "collection":
            stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
            if item.market_scope == "cn_stock" and self._is_single_stock_collection(item) and stock_code:
                self.notification_service.sync_collection_task_state(item.market_scope, stock_code)
        return self._serialize_task(item)

    def update_task(self, task_id: int, payload: dict, current_user: User) -> dict:
        item = self._get_owned_task(task_id, current_user.id)
        previous_task_type = item.task_type
        previous_market_scope = item.market_scope
        previous_stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
        next_task_type = str(payload.get("task_type", item.task_type)).strip()
        self._assert_create_permission(next_task_type, current_user)
        item.task_type = next_task_type
        item.market_scope = self._normalize_market_scope(str(payload.get("market_scope", item.market_scope)).strip())
        item.name = str(payload.get("name", item.name)).strip()
        item.enabled = bool(payload.get("enabled", item.enabled))
        item.schedule_time = self._format_schedule_time(str(payload.get("schedule_time", item.schedule_time)).strip())
        if not item.name:
            raise ValueError("task name is required")
        market_scope, config_json = self._build_config(
            {
                "task_type": item.task_type,
                "market_scope": item.market_scope,
                "collector_key": payload.get("collector_key"),
                "target_type": payload.get("target_type"),
                "target_code": payload.get("target_code"),
                "target_name": payload.get("target_name"),
                "stock_code": payload.get("stock_code"),
                "strategy_ids": payload.get("strategy_ids"),
            },
            current_user,
        )
        item.market_scope = market_scope
        item.config_json = config_json
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        if previous_task_type == "notification" and item.task_type != "notification":
            self.notification_service.remove_notification_task_requirements(item.id)
        if item.task_type == "notification":
            self.notification_service.sync_notification_task_requirements(item)

        current_stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
        if previous_task_type == "collection" and previous_stock_code and (
            item.task_type != "collection"
            or previous_stock_code != current_stock_code
            or previous_market_scope != item.market_scope
        ):
            if previous_market_scope == "cn_stock":
                self.notification_service.sync_collection_task_state(previous_market_scope, previous_stock_code)
        if item.task_type == "collection" and item.market_scope == "cn_stock" and self._is_single_stock_collection(item) and current_stock_code:
            self.notification_service.sync_collection_task_state(item.market_scope, current_stock_code)
        return self._serialize_task(item)

    def delete_task(self, task_id: int, owner_user_id: int) -> None:
        item = self._get_owned_task(task_id, owner_user_id)
        previous_task_type = item.task_type
        previous_market_scope = item.market_scope
        previous_stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
        if previous_task_type == "notification":
            self.notification_service.remove_notification_task_requirements(item.id)
        self.db.query(ScheduledTaskRun).filter(ScheduledTaskRun.scheduled_task_id == item.id).delete(
            synchronize_session=False
        )
        self.db.delete(item)
        self.db.commit()
        if previous_task_type == "collection" and previous_market_scope == "cn_stock" and previous_stock_code:
            self.notification_service.sync_collection_task_state(previous_market_scope, previous_stock_code)

    def toggle_task(self, task_id: int, enabled: bool, current_user: User) -> dict:
        item = self._get_owned_task(task_id, current_user.id)
        if item.task_type == "notification":
            target_email = str(current_user.email or (item.config_json or {}).get("target_email") or "").strip()
            if enabled and not target_email:
                raise ValueError("please set your email in account center before enabling notification tasks")
            if target_email:
                item.config_json = {**(item.config_json or {}), "target_email": target_email}
        item.enabled = enabled
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        if item.task_type == "notification":
            self.notification_service.sync_notification_task_requirements(item)
        elif item.task_type == "collection":
            stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
            if item.market_scope == "cn_stock" and self._is_single_stock_collection(item) and stock_code:
                self.notification_service.sync_collection_task_state(item.market_scope, stock_code)
        return self._serialize_task(item)

    def list_runs(self, task_id: int, owner_user_id: int, limit: int = 20) -> list[dict]:
        task = self._get_owned_task(task_id, owner_user_id)
        items = (
            self.db.query(ScheduledTaskRun)
            .filter(ScheduledTaskRun.scheduled_task_id == task.id)
            .order_by(ScheduledTaskRun.created_at.desc(), ScheduledTaskRun.id.desc())
            .limit(max(limit, 1))
            .all()
        )
        return [self._serialize_run(item) for item in items]

    def _create_run(self, task: ScheduledTask, trigger_type: str, scheduled_for: datetime) -> ScheduledTaskRun:
        item = ScheduledTaskRun(
            scheduled_task_id=task.id,
            trigger_type=trigger_type,
            status="queued",
            scheduled_for=scheduled_for,
            summary="",
            error_message="",
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_manual_run(self, task_id: int, owner_user_id: int) -> dict:
        task = self._get_owned_task(task_id, owner_user_id)
        run = self._create_run(task, trigger_type="manual", scheduled_for=self._now())
        return self._serialize_run(run)

    def _scheduled_run_exists(self, task_id: int, scheduled_for: datetime) -> bool:
        return (
            self.db.query(ScheduledTaskRun)
            .filter(
                ScheduledTaskRun.scheduled_task_id == task_id,
                ScheduledTaskRun.trigger_type == "schedule",
                ScheduledTaskRun.scheduled_for == scheduled_for,
            )
            .first()
            is not None
        )

    def enqueue_due_task_runs(self) -> list[int]:
        now = self._now()
        candidate_tasks = (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.enabled.is_(True),
            )
            .all()
        )
        created_run_ids: list[int] = []
        for task in candidate_tasks:
            scheduled_for = self._due_scheduled_for(task, now)
            if scheduled_for is None:
                continue
            if self._scheduled_run_exists(task.id, scheduled_for):
                continue

            market_scope = self._effective_task_market_scope(task)
            market_reference_date = self.market_calendar.current_market_date(market_scope, now)
            if not self.market_calendar.is_trading_day(market_scope, market_reference_date):
                run = self._create_run(task, trigger_type="schedule", scheduled_for=scheduled_for)
                self._mark_run_state(
                    run,
                    task,
                    status="skipped",
                    summary="当前市场休市，已跳过自动调度。",
                    error_message="",
                    finished_at=now,
                )
                run.summary = "当前市场休市，已跳过自动调度。"
                task.last_run_summary = run.summary
                task.last_scheduled_date = market_reference_date
                self.db.add(task)
                self.db.add(run)
                self.db.commit()
                continue

            run = self._create_run(task, trigger_type="schedule", scheduled_for=scheduled_for)
            task.last_scheduled_date = market_reference_date
            self.db.add(task)
            self.db.commit()
            created_run_ids.append(run.id)
        return created_run_ids

    def bind_run_celery_task_id(self, run_id: int, celery_task_id: str) -> dict:
        item = self.db.get(ScheduledTaskRun, run_id)
        if item is None:
            raise LookupError("task run not found")
        item.celery_task_id = celery_task_id
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._serialize_run(item)

    def _mark_run_state(
        self,
        run: ScheduledTaskRun,
        task: ScheduledTask,
        *,
        status: str,
        summary: str = "",
        error_message: str = "",
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        run.status = status
        if started_at is not None:
            run.started_at = started_at
        if finished_at is not None:
            run.finished_at = finished_at
        run.summary = summary
        run.error_message = error_message

        task.last_run_at = finished_at or started_at or self._now()
        task.last_run_status = status
        task.last_run_summary = summary
        task.last_error_message = error_message

        self.db.add(run)
        self.db.add(task)
        self.db.commit()

    def _send_email(self, recipient: str, subject: str, body: str) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise RuntimeError("SMTP is not configured")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = (
            f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            if settings.smtp_from_name
            else settings.smtp_from_email
        )
        message["To"] = recipient
        message.set_content(body)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)

    def _build_notification_email(self, task: ScheduledTask, owner: User, basis_trade_date: date) -> tuple[str, str]:
        config = task.config_json or {}
        strategy_ids = [
            int(raw_id)
            for raw_id in config.get("strategy_ids", [])
            if isinstance(raw_id, int) or str(raw_id).isdigit()
        ]
        if not strategy_ids:
            raise ValueError("notification task is missing strategy_ids")

        summaries = self.quant_service.list_strategy_notification_summaries(
            strategy_ids,
            owner.id,
            basis_trade_date=basis_trade_date,
        )
        if not summaries:
            raise ValueError("notification task has no available strategies")

        display_name = (owner.nickname or "").strip() or owner.username
        today_text = self._now().strftime("%Y-%m-%d")
        basis_date_text = basis_trade_date.isoformat()
        subject = f"[FIT] 每日策略通知 {today_text} - {task.name}"
        lines = [
            f"你好，{display_name}：",
            "",
            f"以下是任务“{task.name}”在 {today_text} 发送的策略摘要。",
            f"通知基准交易日：{basis_date_text}",
            "",
        ]

        actionable_count = 0
        for item in summaries:
            signal_text = str(item.get("signal_text", "无操作")).strip() or "无操作"
            if signal_text in {"蓝", "红", "紫"}:
                actionable_count += 1
            lines.extend(
                [
                    f"- 策略：{item.get('strategy_name', '-')}",
                    f"  标的：{item.get('target_name', '-')}",
                    f"  最新交易日：{item.get('latest_trade_date', '-')}",
                    f"  当日信号：{signal_text}",
                    f"  说明：{item.get('note', '无操作')}",
                    "",
                ]
            )

        lines.append(f"本次汇总共 {len(summaries)} 条策略，其中 {actionable_count} 条存在操作信号。")
        return subject, "\n".join(lines).strip()

    def _execute_notification_task(self, task: ScheduledTask) -> str:
        owner = self.db.get(User, task.owner_user_id)
        if owner is None:
            raise ValueError("task owner not found")
        if owner.role == "guest":
            raise PermissionError("guest users cannot execute notification tasks")

        recipient = str(owner.email or (task.config_json or {}).get("target_email") or "").strip()
        if not recipient:
            raise ValueError("notification task target email is missing")

        market_scope = self._normalize_market_scope(task.market_scope)
        basis_trade_date = self._notification_basis_trade_date(market_scope, self._now())
        subject, body = self._build_notification_email(task, owner, basis_trade_date)
        self._send_email(recipient, subject, body)

        strategy_count = len((task.config_json or {}).get("strategy_ids") or [])
        return (
            f"Sent notification email to {recipient} for {strategy_count} strategies "
            f"based on trade date {basis_trade_date.isoformat()}."
        )

    def _execute_collection_task(self, task: ScheduledTask) -> str:
        config = task.config_json or {}
        collector_key = self._normalize_collector_key(
            config.get("collector_key"),
            task.market_scope,
            config.get("target_type"),
            config.get("target_code") or config.get("stock_code"),
            config.get("target_name"),
            task.name,
        )
        definition = self._get_collection_definition(collector_key)
        label = str(definition.get("label") or collector_key)
        target_code = str(config.get("target_code") or config.get("stock_code") or "").strip()
        target_name = str(config.get("target_name", "")).strip() or target_code

        if collector_key == "stock_hfq_single":
            if not target_code:
                raise ValueError("collection task is missing target_code")
            result = run_stock_hfq_collection_request(stock_code=target_code)
            upstream_status = str(result.get("upstream_status", result.get("status", "ok"))).upper()
            if upstream_status == "SUCCESS":
                return f"{target_name}（{target_code}）采集完成，已刷新数据。"
            if upstream_status == "UNCHANGED":
                return f"{target_name}（{target_code}）采集完成，但没有新数据。"
            return f"{target_name}（{target_code}）采集完成，状态：{upstream_status}。"

        if collector_key == "index_hk_daily":
            result = run_index_daily_collection_request("hk")
        elif collector_key == "index_us_daily":
            result = run_index_daily_collection_request("us")
        else:
            endpoint = str(definition.get("endpoint") or "").strip()
            result = run_daily_collection_request(collector_key=collector_key, endpoint=endpoint)

        upstream_status = str(result.get("upstream_status", result.get("status", "ok"))).upper()
        upstream_payload = result.get("upstream_response") if isinstance(result, dict) else None
        result_value = upstream_payload.get("result") if isinstance(upstream_payload, dict) else None
        if result_value not in (None, ""):
            return f"{label}执行完成，结果：{result_value}。"
        return f"{label}执行完成，状态：{upstream_status}。"

    def execute_run(self, run_id: int) -> dict:
        run = self.db.get(ScheduledTaskRun, run_id)
        if run is None:
            raise LookupError("task run not found")
        task = self.db.get(ScheduledTask, run.scheduled_task_id)
        if task is None:
            raise LookupError("scheduled task not found")

        started_at = self._now()
        self._mark_run_state(run, task, status="running", started_at=started_at)

        try:
            if task.task_type == "collection":
                summary = self._execute_collection_task(task)
            elif task.task_type == "notification":
                summary = self._execute_notification_task(task)
            else:
                raise ValueError("unsupported task type")
        except Exception as exc:
            finished_at = self._now()
            self._mark_run_state(
                run,
                task,
                status="failed",
                summary="",
                error_message=str(exc),
                finished_at=finished_at,
            )
            raise

        finished_at = self._now()
        self._mark_run_state(
            run,
            task,
            status="success",
            summary=summary,
            error_message="",
            finished_at=finished_at,
        )
        self.db.refresh(run)
        return self._serialize_run(run)
