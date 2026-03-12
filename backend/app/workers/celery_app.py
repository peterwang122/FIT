from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "fit-worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
)

celery_app.autodiscover_tasks(["app.tasks"])
