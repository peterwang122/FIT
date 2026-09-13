import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.services.task_service import TaskRunPollingPending, TaskService
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


def _should_sync_wechat_notification(result: dict, task: ScheduledTask, owner: User | None) -> bool:
    return bool(
        result.get("status") == "success"
        and result.get("trigger_type") in {"schedule", "manual"}
        and task.task_type == "notification"
        and task.name == settings.wechat_miniapp_notification_task_name
        and owner is not None
        and owner.role == "root"
    )


@celery_app.task(name="tasks.dispatch_due_scheduled_tasks")
def dispatch_due_scheduled_tasks():
    with SessionLocal() as db:
        service = TaskService(db)
        run_ids = service.enqueue_due_task_runs()

    queued_ids: list[int] = []
    for run_id in run_ids:
        async_result = execute_scheduled_task_run.delay(run_id)
        with SessionLocal() as db:
            service = TaskService(db)
            service.bind_run_celery_task_id(run_id, async_result.id)
        queued_ids.append(run_id)

    return {
        "queued_count": len(queued_ids),
        "run_ids": queued_ids,
    }


@celery_app.task(bind=True, name="tasks.execute_scheduled_task_run")
def execute_scheduled_task_run(self, run_id: int):
    should_sync_notification = False
    with SessionLocal() as db:
        service = TaskService(db)
        service.bind_run_celery_task_id(run_id, self.request.id)
        try:
            result = service.execute_run(run_id)
            task = db.get(ScheduledTask, result["scheduled_task_id"])
            owner = db.get(User, task.owner_user_id) if task is not None else None
            should_sync_notification = bool(
                task is not None and _should_sync_wechat_notification(result, task, owner)
            )
        except TaskRunPollingPending as exc:
            raise self.retry(
                exc=exc,
                countdown=exc.countdown_seconds,
                max_retries=130,
            )
    if should_sync_notification:
        try:
            from app.tasks.wechat_miniapp import sync_wechat_miniapp_notification

            # Keep the post-email sync on the dedicated mini-program queue.
            # If another data sync owns the shared lock, this task retries
            # instead of silently dropping the daily-notice update.
            sync_wechat_miniapp_notification.apply_async(queue="wechat-miniapp")
        except Exception:
            logger.exception("failed to enqueue mini-program notification sync")
    return result
