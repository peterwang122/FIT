from app.core.config import settings
from app.core.redis_client import redis_client


class TaskIdempotencyService:
    def _task_key(self, idempotency_key: str) -> str:
        return f"idempotency:collect:{idempotency_key}"

    def get_existing_task_id(self, idempotency_key: str) -> str | None:
        return redis_client.get(self._task_key(idempotency_key))

    def bind_task_id(self, idempotency_key: str, task_id: str) -> None:
        redis_client.set(self._task_key(idempotency_key), task_id, ex=settings.task_idempotency_ttl_seconds)

    def clear_task_id(self, idempotency_key: str) -> None:
        redis_client.delete(self._task_key(idempotency_key))
