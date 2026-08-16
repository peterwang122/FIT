"""采集白名单（lan-test 环境隔离）。

``COLLECTION_EXECUTION_MODE=allowlist`` 时，只有 ``COLLECTION_ALLOWED_KEYS``
中的采集键可以执行；白名单为空表示全部拒绝。默认 ``enabled`` 模式保持原有行为。
"""

from app.core.config import settings


def collection_allowed(collector_key: str) -> bool:
    if settings.collection_execution_mode.strip().lower() != "allowlist":
        return True
    key = str(collector_key or "").strip().lower()
    if not key:
        return False
    return key in settings.collection_allowed_key_set


def ensure_collection_allowed(collector_key: str) -> None:
    if not collection_allowed(collector_key):
        raise PermissionError(
            f"collection allowlist rejected this task: collector_key={collector_key}"
        )
