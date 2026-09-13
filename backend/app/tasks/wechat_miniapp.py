from uuid import uuid4

from app.core.redis_client import redis_client
from app.db.session import SessionLocal
from app.services.wechat_miniapp_sync_service import WechatMiniappSyncService
from app.workers.celery_app import celery_app


LOCK_KEY = "system:lock:wechat-miniapp-sync"
LOCK_TTL_SECONDS = 9 * 60


def _run_with_lock(operation):
    owner_token = str(uuid4())
    lock_acquired = redis_client.set(
        LOCK_KEY,
        owner_token,
        nx=True,
        ex=LOCK_TTL_SECONDS,
    )
    if not lock_acquired:
        return {"status": "deduplicated"}

    try:
        with SessionLocal() as db:
            return operation(WechatMiniappSyncService(db))
    finally:
        if redis_client.get(LOCK_KEY) == owner_token:
            redis_client.delete(LOCK_KEY)


@celery_app.task(name="tasks.sync_wechat_miniapp")
def sync_wechat_miniapp():
    # Scheduled/manual dashboard refreshes must never upload a notification
    # event. Only the post-email task below is allowed to do that.
    return _run_with_lock(lambda service: service.sync(full=False, include_notification=False))


@celery_app.task(name="tasks.sync_wechat_miniapp_data")
def sync_wechat_miniapp_data():
    return _run_with_lock(lambda service: service.sync(full=False, include_notification=False))


@celery_app.task(bind=True, name="tasks.sync_wechat_miniapp_notification")
def sync_wechat_miniapp_notification(self):
    try:
        result = _run_with_lock(lambda service: service.sync_notification())
        if result.get("status") == "deduplicated":
            raise RuntimeError("wechat mini-program sync is busy")
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30, max_retries=5)
