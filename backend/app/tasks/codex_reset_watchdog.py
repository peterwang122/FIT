from uuid import uuid4

from app.core.config import settings
from app.core.redis_client import redis_client
from app.db.session import SessionLocal
from app.services.codex_reset_watchdog_service import (
    CodexResetWatchdogService,
    WatchdogNotification,
)
from app.services.notification_service import NotificationService
from app.workers.celery_app import celery_app


LOCK_KEY = "system:lock:codex-reset-watchdog"


@celery_app.task(name="tasks.check_codex_reset_watchdog")
def check_codex_reset_watchdog():
    if not settings.codex_reset_watchdog_enabled:
        return {"status": "disabled"}

    owner_token = str(uuid4())
    lock_acquired = redis_client.set(
        LOCK_KEY,
        owner_token,
        nx=True,
        ex=max(int(settings.codex_reset_watchdog_lock_ttl_seconds), 60),
    )
    if not lock_acquired:
        return {"status": "deduplicated"}

    try:
        with SessionLocal() as db:
            notification_service = NotificationService(db)

            def notify(notification: WatchdogNotification) -> bool:
                return notification_service.create_root_notification_once(
                    category="codex_reset_watchdog",
                    title=notification.title,
                    body=notification.body,
                    action_url=notification.action_url,
                    action_label=notification.action_label,
                    dedupe_key=notification.dedupe_key,
                    payload_json=notification.payload,
                )

            return CodexResetWatchdogService(notifier=notify).check()
    finally:
        if redis_client.get(LOCK_KEY) == owner_token:
            redis_client.delete(LOCK_KEY)
