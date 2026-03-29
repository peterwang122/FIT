import sys

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "fit-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.collector"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    imports=("app.tasks.collector",),
)

if sys.platform.startswith("win"):
    celery_app.conf.update(
        worker_pool="solo",
        worker_concurrency=1,
    )

celery_app.autodiscover_tasks(["app"])
