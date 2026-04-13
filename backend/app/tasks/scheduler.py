from app.db.session import SessionLocal
from app.services.task_service import TaskService
from app.workers.celery_app import celery_app


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
    with SessionLocal() as db:
        service = TaskService(db)
        service.bind_run_celery_task_id(run_id, self.request.id)
        return service.execute_run(run_id)
