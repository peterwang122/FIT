import asyncio
from datetime import datetime

import pytest

import app.main as app_main
import app.tasks.scheduler as scheduler_module
from app.core.collection_allowlist import collection_allowed
from app.core.config import settings
from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
from app.services import auth_service
from app.services.task_service import TaskRunSkipped, TaskService


def _make_collection_task(collector_key, *, task_id=1, market_scope="cn_stock"):
    return ScheduledTask(
        id=task_id,
        owner_user_id=1,
        task_type="collection",
        market_scope=market_scope,
        name=f"{collector_key}-task",
        enabled=True,
        schedule_time="09:00",
        config_json={"collector_key": collector_key},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )


def _make_notification_task(*, task_id=2):
    return ScheduledTask(
        id=task_id,
        owner_user_id=1,
        task_type="notification",
        market_scope="cn_stock",
        name="每日通知",
        enabled=True,
        schedule_time="09:00",
        config_json={"strategy_ids": [1]},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )


def _make_run(task_id=1):
    return ScheduledTaskRun(
        id=1,
        scheduled_task_id=task_id,
        trigger_type="schedule",
        status="queued",
        scheduled_for=datetime(2026, 4, 30, 17, 0),
        summary="",
        error_message="",
    )


class _RaisingSession:
    def __init__(self, *args, **kwargs):
        raise AssertionError("database must not be touched")

    def query(self, *args, **kwargs):
        raise AssertionError("database must not be touched")

    def get(self, *args, **kwargs):
        raise AssertionError("database must not be touched")


class _UntouchableSession:
    def __init__(self, *args, **kwargs):
        return None

    def query(self, *args, **kwargs):
        raise AssertionError("database must not be touched")

    def get(self, *args, **kwargs):
        raise AssertionError("database must not be touched")


class _FakeQuery:
    def __init__(self, items):
        self._items = list(items or [])

    def filter(self, *_criteria):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class _ManualRunFakeSession:
    def __init__(self, task):
        self.task = task
        self.added = []

    def query(self, model):
        if model is ScheduledTask:
            return _FakeQuery([self.task] if self.task else [])
        return _FakeQuery([])

    def add(self, instance):
        self.added.append(instance)

    def commit(self):
        return None

    def refresh(self, _instance):
        return None


class _ExecuteFakeSession:
    def __init__(self, *, tasks=None, runs=None):
        self.tasks = list(tasks or [])
        self.runs = list(runs or [])

    def get(self, model, identity):
        if model is ScheduledTask:
            for item in self.tasks:
                if item.id == identity:
                    return item
        if model is ScheduledTaskRun:
            for item in self.runs:
                if item.id == identity:
                    return item
        return None


def _set_allowlist(monkeypatch, allowed_keys):
    monkeypatch.setattr(settings, "collection_execution_mode", "allowlist")
    monkeypatch.setattr(settings, "collection_allowed_keys", allowed_keys)


def test_settings_defaults_preserve_existing_behavior():
    assert settings.startup_schema_mode == "full"
    assert settings.bootstrap_default_tasks is True
    assert settings.scheduled_tasks_enabled is True
    assert settings.outbound_notifications_enabled is True
    assert settings.collection_execution_mode == "enabled"
    assert settings.collection_allowed_keys == ""


def test_allowed_keys_parsing(monkeypatch):
    monkeypatch.setattr(
        settings,
        "collection_allowed_keys",
        " stock_daily , quant_index_daily ",
    )
    assert settings.collection_allowed_key_set == {
        "stock_daily",
        "quant_index_daily",
    }


def test_collection_allowed_defaults_to_true_in_enabled_mode(monkeypatch):
    monkeypatch.setattr(settings, "collection_execution_mode", "enabled")
    assert collection_allowed("stock_daily") is True
    assert collection_allowed("") is True


def test_collection_allowed_respects_allowlist(monkeypatch):
    _set_allowlist(monkeypatch, "stock_daily")
    assert collection_allowed("stock_daily") is True
    assert collection_allowed("STOCK_DAILY") is True
    assert collection_allowed("etf_daily") is False
    assert collection_allowed("") is False


def test_health_includes_isolation_fields(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "lan-test")
    monkeypatch.setattr(settings, "scheduled_tasks_enabled", False)
    monkeypatch.setattr(settings, "outbound_notifications_enabled", False)
    monkeypatch.setattr(settings, "collection_execution_mode", "allowlist")
    monkeypatch.setattr(settings, "collection_allowed_keys", "stock_daily, quant_index_daily")

    payload = asyncio.run(app_main.health())
    assert payload["env"] == "lan-test"
    assert payload["scheduled_tasks_enabled"] is False
    assert payload["outbound_notifications_enabled"] is False
    assert payload["collection_execution_mode"] == "allowlist"
    assert payload["allowed_collectors"] == ["quant_index_daily", "stock_daily"]


def test_startup_guard_rejects_non_test_database_in_lan_test(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "lan-test")
    monkeypatch.setattr(
        settings,
        "database_url",
        "mysql+pymysql://fit:fitpass@127.0.0.1:3306/stock_info",
    )
    with pytest.raises(RuntimeError, match="stock_info_test"):
        app_main.ensure_runtime_tables()


def test_default_collection_task_noop_when_bootstrap_disabled(monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_default_tasks", False)
    result = app_main._ensure_default_collection_task(
        _RaisingSession,
        owner=None,
        collector_key="stock_daily",
        name="日更",
        schedule_time="09:00",
    )
    assert result is None


def test_default_risk_strategies_noop_when_bootstrap_disabled(monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_default_tasks", False)
    assert app_main._ensure_default_risk_strategies(_RaisingSession, owner=None) == []


def test_default_risk_notification_task_noop_when_bootstrap_disabled(monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_default_tasks", False)
    result = app_main._ensure_default_risk_notification_task(
        _RaisingSession,
        owner=None,
        strategies=[],
    )
    assert result is None


def test_dispatch_disabled_returns_empty_without_db(monkeypatch):
    monkeypatch.setattr(settings, "scheduled_tasks_enabled", False)
    monkeypatch.setattr(scheduler_module, "SessionLocal", _RaisingSession)
    result = scheduler_module.dispatch_due_scheduled_tasks()
    assert result == {"queued_count": 0, "run_ids": [], "disabled": True}


def test_create_manual_run_denied_before_creating_run(monkeypatch):
    _set_allowlist(monkeypatch, "")
    db = _ManualRunFakeSession(task=_make_collection_task("stock_daily"))
    service = TaskService(db)
    with pytest.raises(PermissionError, match="allowlist"):
        service.create_manual_run(1, 1)
    assert db.added == []


def test_create_manual_run_allowed_when_allowlisted(monkeypatch):
    _set_allowlist(monkeypatch, "stock_daily")
    db = _ManualRunFakeSession(task=_make_collection_task("stock_daily"))
    service = TaskService(db)
    service.create_manual_run(1, 1)
    assert len(db.added) == 1
    assert isinstance(db.added[0], ScheduledTaskRun)


def test_execute_run_denied_for_collection_when_not_allowlisted(monkeypatch):
    _set_allowlist(monkeypatch, "")
    task = _make_collection_task("stock_daily")
    run = _make_run(task.id)
    service = TaskService(_ExecuteFakeSession(tasks=[task], runs=[run]))
    with pytest.raises(TaskRunSkipped, match="allowlist"):
        service.execute_run(run.id)


def test_enqueue_due_task_runs_skips_denied_collection(monkeypatch):
    _set_allowlist(monkeypatch, "")
    task = _make_collection_task("stock_daily")

    class _EnqueueSession:
        def query(self, model):
            return _FakeQuery([task] if model is ScheduledTask else [])

        def get(self, *_args, **_kwargs):
            raise AssertionError("denied collection task must not touch the database")

        def add(self, *_args):
            raise AssertionError("denied collection task must not create run records")

        def commit(self):
            raise AssertionError("denied collection task must not commit")

    service = TaskService(_EnqueueSession())
    assert service.enqueue_due_task_runs() == []


def test_execute_notification_task_skipped_when_outbound_disabled(monkeypatch):
    monkeypatch.setattr(settings, "outbound_notifications_enabled", False)
    service = TaskService(_UntouchableSession())
    with pytest.raises(TaskRunSkipped, match="outbound notifications are disabled"):
        service._execute_notification_task(_make_notification_task())


def test_send_email_blocked_when_outbound_disabled(monkeypatch):
    monkeypatch.setattr(settings, "outbound_notifications_enabled", False)
    service = TaskService(_UntouchableSession())
    with pytest.raises(RuntimeError, match="outbound notifications are disabled"):
        service._send_email("a@example.com", "subject", "body")


def test_sms_debug_fallback_when_outbound_disabled(monkeypatch):
    monkeypatch.setattr(settings, "outbound_notifications_enabled", False)
    service = auth_service.AuthService.__new__(auth_service.AuthService)
    # 不应抛出异常，也不应真正调用阿里云
    service._send_with_aliyun("13800000000", "123456")
