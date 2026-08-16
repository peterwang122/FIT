from types import SimpleNamespace

import pytest

from app.services import auth_service as auth_service_module
from app.services.auth_service import AuthService, SESSION_RECORD_TOUCH_INTERVAL_SECONDS


class FakeRedis:
    def __init__(self, set_results):
        self.set_results = list(set_results)
        self.set_calls = []
        self.deleted_keys = []

    def set(self, key, value, **kwargs):
        self.set_calls.append((key, value, kwargs))
        return self.set_results.pop(0)

    def delete(self, key):
        self.deleted_keys.append(key)


def test_refresh_session_throttles_database_touch(monkeypatch):
    fake_redis = FakeRedis([True, None])
    monkeypatch.setattr(auth_service_module, "redis_client", fake_redis)

    service = AuthService(db=SimpleNamespace())
    user = SimpleNamespace(id=1)
    stored_sessions = []
    touched_sessions = []
    cookies = []
    monkeypatch.setattr(service, "_store_session", lambda session_id, _user: stored_sessions.append(session_id))
    monkeypatch.setattr(
        service,
        "_touch_session_record",
        lambda session_id, _user, _request: touched_sessions.append(session_id),
    )
    monkeypatch.setattr(service, "_set_session_cookie", lambda _response, session_id: cookies.append(session_id))

    service.refresh_session("session-1", object(), user)
    service.refresh_session("session-1", object(), user)

    assert stored_sessions == ["session-1", "session-1"]
    assert touched_sessions == ["session-1"]
    assert cookies == ["session-1", "session-1"]
    assert fake_redis.set_calls[0][2] == {
        "nx": True,
        "ex": SESSION_RECORD_TOUCH_INTERVAL_SECONDS,
    }
    assert "session-1" not in fake_redis.set_calls[0][0]


def test_refresh_session_releases_throttle_after_database_error(monkeypatch):
    fake_redis = FakeRedis([True])
    monkeypatch.setattr(auth_service_module, "redis_client", fake_redis)

    service = AuthService(db=SimpleNamespace())
    monkeypatch.setattr(service, "_store_session", lambda _session_id, _user: None)
    monkeypatch.setattr(service, "_set_session_cookie", lambda _response, _session_id: None)

    def fail_touch(_session_id, _user, _request):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(service, "_touch_session_record", fail_touch)

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.refresh_session("session-2", object(), SimpleNamespace(id=2))

    assert fake_redis.deleted_keys == [fake_redis.set_calls[0][0]]
