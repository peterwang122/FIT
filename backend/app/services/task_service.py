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
from app.tasks.collector import run_stock_hfq_collection_request

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
SCHEDULE_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class TaskService:
    def __init__(self, db: Session):
        self.db = db
        self.quant_service = QuantService(db)
        self.stock_service = StockService(db)
        self.market_calendar = MarketCalendarService()
        self.notification_service = NotificationService(db)

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

    def _normalize_market_scope(self, raw_value: str | None) -> str:
        return self.market_calendar.normalize_market_scope(raw_value)

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
        market_open = self.market_calendar.market_open_time(market_scope)
        if run_at.time() < market_open:
            return self.market_calendar.previous_trading_day(market_scope, run_at.date())
        return run_at.date()

    def _compute_next_run_at(self, item: ScheduledTask) -> datetime | None:
        if not item.enabled:
            return None
        market_scope = self._normalize_market_scope(item.market_scope)
        return self._compute_next_run_at_for_scope(market_scope, item.schedule_time)

    def _serialize_task(self, item: ScheduledTask) -> dict:
        config = item.config_json or {}
        stock_code = str(config.get("stock_code", "")).strip() or None
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
            "market_scope": self._normalize_market_scope(item.market_scope),
            "name": item.name,
            "enabled": bool(item.enabled),
            "schedule_time": item.schedule_time,
            "stock_code": stock_code,
            "stock_name": self._resolve_stock_name(stock_code),
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

    def _build_config(self, payload: dict, current_user: User) -> dict:
        task_type = str(payload.get("task_type", "")).strip()
        self._assert_create_permission(task_type, current_user)

        if task_type == "collection":
            stock_code = str(payload.get("stock_code", "")).strip()
            if not stock_code:
                raise ValueError("stock_code is required for collection tasks")
            return {"stock_code": stock_code}

        target_email = str(current_user.email or "").strip()
        if not target_email:
            raise ValueError("please set your email in account center before enabling notification tasks")
        strategy_ids = self._normalize_notification_strategy_ids(payload.get("strategy_ids") or [], current_user.id)
        return {
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
        item = ScheduledTask(
            owner_user_id=current_user.id,
            task_type=str(payload.get("task_type", "")).strip(),
            market_scope=self._normalize_market_scope(str(payload.get("market_scope", DEFAULT_MARKET_SCOPE)).strip()),
            name=str(payload.get("name", "")).strip(),
            enabled=bool(payload.get("enabled", True)),
            schedule_time=self._format_schedule_time(str(payload.get("schedule_time", "")).strip()),
            config_json=self._build_config(payload, current_user),
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
            if stock_code:
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
        item.config_json = self._build_config(
            {
                "task_type": item.task_type,
                "stock_code": payload.get("stock_code"),
                "strategy_ids": payload.get("strategy_ids"),
            },
            current_user,
        )
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
            self.notification_service.sync_collection_task_state(previous_market_scope, previous_stock_code)
        if item.task_type == "collection" and current_stock_code:
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
        if previous_task_type == "collection" and previous_stock_code:
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
            if stock_code:
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

    def enqueue_due_task_runs(self) -> list[int]:
        now = self._now()
        current_time_text = now.strftime("%H:%M")
        due_tasks = (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.enabled.is_(True),
                ScheduledTask.schedule_time == current_time_text,
            )
            .all()
        )
        created_run_ids: list[int] = []
        for task in due_tasks:
            if task.last_scheduled_date == now.date():
                continue

            market_scope = self._normalize_market_scope(task.market_scope)
            if not self.market_calendar.is_trading_day(market_scope, now.date()):
                run = self._create_run(task, trigger_type="schedule", scheduled_for=now)
                self._mark_run_state(
                    run,
                    task,
                    status="skipped",
                    summary="Skipped because the scheduled market is closed today.",
                    error_message="",
                    finished_at=now,
                )
                task.last_scheduled_date = now.date()
                self.db.add(task)
                self.db.commit()
                continue

            run = self._create_run(task, trigger_type="schedule", scheduled_for=now)
            task.last_scheduled_date = now.date()
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

    def _execute_collection_task(self, task: ScheduledTask) -> str:
        stock_code = str((task.config_json or {}).get("stock_code", "")).strip()
        if not stock_code:
            raise ValueError("collection task is missing stock_code")

        result = run_stock_hfq_collection_request(stock_code=stock_code)
        upstream_status = str(result.get("upstream_status", result.get("status", "ok"))).upper()
        if upstream_status == "SUCCESS":
            return f"{stock_code} collection completed with refreshed data."
        if upstream_status == "UNCHANGED":
            return f"{stock_code} collection completed with no new data."
        return f"{stock_code} collection completed with status {upstream_status}."

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
