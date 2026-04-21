from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.api.deps.auth import get_current_user
from app.main import app
from app.models.user import User


class DummyTask:
    def __init__(self, task_id: str):
        self.id = task_id


class DummyAsyncResult:
    def __init__(self, state: str):
        self.state = state


def _make_user() -> User:
    return User(id=1, username="root", role="root", nickname="root")


@contextmanager
def _test_client():
    original_startup = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_current_user] = _make_user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.router.on_startup[:] = original_startup
        app.dependency_overrides.clear()


def test_collect_endpoint_uses_existing_task_when_idempotency_key(monkeypatch):
    from app.api import routes_stock

    monkeypatch.setattr(routes_stock.TaskIdempotencyService, "get_existing_task_id", lambda self, key: "existing-task")
    monkeypatch.setattr(routes_stock, "AsyncResult", lambda task_id, app=None: DummyAsyncResult("STARTED"))

    with _test_client() as client:
        response = client.post(
            "/api/v1/stocks/collect",
            json={"ts_code": "000001.SZ"},
            headers={"Idempotency-Key": "same-key"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "existing-task"
    assert payload["status"] == "deduplicated"


def test_hfq_collect_endpoint_resubmits_when_existing_task_finished(monkeypatch):
    from app.api import routes_stock

    monkeypatch.setattr(routes_stock.TaskIdempotencyService, "get_existing_task_id", lambda self, key: "old-task")
    monkeypatch.setattr(routes_stock, "AsyncResult", lambda task_id, app=None: DummyAsyncResult("FAILURE"))

    cleared = {}
    captured = {}

    def _clear_task_id(self, idempotency_key):
        cleared["idempotency_key"] = idempotency_key

    def _bind_task_id(self, idempotency_key, task_id):
        captured["idempotency_key"] = idempotency_key
        captured["task_id"] = task_id

    monkeypatch.setattr(routes_stock.TaskIdempotencyService, "clear_task_id", _clear_task_id)
    monkeypatch.setattr(routes_stock.TaskIdempotencyService, "bind_task_id", _bind_task_id)
    monkeypatch.setattr(routes_stock.collect_stock_hfq_data, "delay", lambda **kwargs: DummyTask("new-hfq-task"))

    with _test_client() as client:
        response = client.post(
            "/api/v1/stocks/hfq-collect",
            json={"ts_code": "002594"},
            headers={"Idempotency-Key": "same-day-key"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "new-hfq-task"
    assert payload["status"] == "submitted"
    assert cleared == {"idempotency_key": "same-day-key"}
    assert captured == {"idempotency_key": "same-day-key", "task_id": "new-hfq-task"}


def test_collect_endpoint_submits_new_task(monkeypatch):
    from app.api import routes_stock

    monkeypatch.setattr(routes_stock.TaskIdempotencyService, "get_existing_task_id", lambda self, key: None)

    captured = {}

    def _bind_task_id(self, idempotency_key, task_id):
        captured["idempotency_key"] = idempotency_key
        captured["task_id"] = task_id

    monkeypatch.setattr(routes_stock.TaskIdempotencyService, "bind_task_id", _bind_task_id)
    monkeypatch.setattr(routes_stock.collect_stock_data, "delay", lambda **kwargs: DummyTask("new-task"))

    with _test_client() as client:
        response = client.post(
            "/api/v1/stocks/collect",
            json={"ts_code": "000001.SZ"},
            headers={"Idempotency-Key": "new-key"},
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["task_id"] == "new-task"
    assert payload["status"] == "submitted"
    assert captured == {"idempotency_key": "new-key", "task_id": "new-task"}
