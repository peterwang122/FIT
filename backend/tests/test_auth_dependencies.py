from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request, Response

from app.api.deps import auth as auth_dependencies


class FakeDb:
    def __init__(self):
        self.close_calls = 0
        self.refresh_calls = []
        self.expunge_calls = []

    def refresh(self, item):
        self.refresh_calls.append(item)

    def expunge(self, item):
        self.expunge_calls.append(item)

    def close(self):
        self.close_calls += 1


def make_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def test_current_user_releases_authentication_connection(monkeypatch):
    db = FakeDb()
    user = SimpleNamespace(id=1, role="root")
    service = SimpleNamespace(
        get_user_from_session=lambda _session_id: user,
        refresh_session=lambda *_args: None,
    )
    monkeypatch.setattr(auth_dependencies, "AuthService", lambda _db: service)

    result = auth_dependencies.get_current_user(make_request(), Response(), "session-1", db)

    assert result is user
    assert db.refresh_calls == [user]
    assert db.expunge_calls == [user]
    assert db.close_calls == 1


def test_optional_current_user_returns_detached_snapshot(monkeypatch):
    db = FakeDb()
    user = SimpleNamespace(id=2, role="user")
    service = SimpleNamespace(
        get_user_from_session=lambda _session_id: user,
        refresh_session=lambda *_args: None,
    )
    monkeypatch.setattr(auth_dependencies, "AuthService", lambda _db: service)

    result = auth_dependencies.get_current_user_optional(
        make_request(),
        Response(),
        "session-2",
        db,
    )

    assert result is user
    assert db.refresh_calls == [user]
    assert db.expunge_calls == [user]
    assert db.close_calls == 1


def test_current_user_releases_connection_when_session_is_missing():
    db = FakeDb()

    with pytest.raises(HTTPException, match="请先登录"):
        auth_dependencies.get_current_user(make_request(), Response(), None, db)

    assert db.close_calls == 1


def test_optional_current_user_releases_connection_without_session():
    db = FakeDb()

    assert auth_dependencies.get_current_user_optional(make_request(), Response(), None, db) is None
    assert db.close_calls == 1
