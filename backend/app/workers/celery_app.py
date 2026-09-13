import sys

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "fit-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.collector",
        "app.tasks.scheduler",
        "app.tasks.codex_reset_watchdog",
        "app.tasks.wechat_miniapp",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_routes={
        "tasks.sync_wechat_miniapp": {"queue": "wechat-miniapp"},
        "tasks.sync_wechat_miniapp_data": {"queue": "wechat-miniapp"},
        "tasks.sync_wechat_miniapp_notification": {"queue": "wechat-miniapp"},
    },
    imports=(
        "app.tasks.collector",
        "app.tasks.scheduler",
        "app.tasks.codex_reset_watchdog",
        "app.tasks.wechat_miniapp",
    ),
    beat_schedule={
        "dispatch-scheduled-tasks-every-minute": {
            "task": "tasks.dispatch_due_scheduled_tasks",
            "schedule": crontab(minute="*"),
        },
        "check-codex-reset-watchdog-hourly": {
            "task": "tasks.check_codex_reset_watchdog",
            "schedule": crontab(minute="8"),
        },
        "sync-wechat-miniapp-after-source-updates": {
            "task": "tasks.sync_wechat_miniapp_data",
            # Beijing time, after the actual source updates:
            # 09:30 initial risk/previous notice, 10:30 final risk,
            # 17:30 global score/position table, and 23:30 final dashboard
            # scores after the 22:30 calculation.
            "schedule": crontab(minute="30", hour="9,10,17,23"),
            "options": {"queue": "wechat-miniapp"},
        },
        "sync-wechat-miniapp-at-21-independent-of-notification": {
            "task": "tasks.sync_wechat_miniapp_data",
            # Fixed Beijing 21:00 sync. This does not depend on whether the
            # separate notification task succeeds or fails.
            "schedule": crontab(minute="0", hour="21"),
            "options": {"queue": "wechat-miniapp"},
        },
    },
)

if sys.platform.startswith("win"):
    celery_app.conf.update(
        worker_pool="solo",
        worker_concurrency=1,
    )

celery_app.autodiscover_tasks(["app"])
