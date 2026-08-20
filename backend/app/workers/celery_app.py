import sys

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.lan_test import ensure_lan_test_runtime_safe

celery_app = Celery(
    "fit-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.collector", "app.tasks.scheduler", "app.tasks.codex_reset_watchdog"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    imports=("app.tasks.collector", "app.tasks.scheduler", "app.tasks.codex_reset_watchdog"),
    beat_schedule={
        "dispatch-scheduled-tasks-every-minute": {
            "task": "tasks.dispatch_due_scheduled_tasks",
            "schedule": crontab(minute="*"),
        },
        "check-codex-reset-watchdog-hourly": {
            "task": "tasks.check_codex_reset_watchdog",
            "schedule": crontab(minute="8"),
        },
    },
)

if sys.platform.startswith("win"):
    celery_app.conf.update(
        worker_pool="solo",
        worker_concurrency=1,
    )

celery_app.autodiscover_tasks(["app"])

# lan-test 契约在 worker / beat 进程导入时 fail-closed：
# 任何安全开关不符合预期时，Celery 进程直接拒绝启动。
ensure_lan_test_runtime_safe()
