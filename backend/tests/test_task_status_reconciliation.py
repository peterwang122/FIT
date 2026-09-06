from datetime import datetime

from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
from app.services.task_service import TaskService


class _RecordingSession:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


def _make_task(status: str = "running") -> ScheduledTask:
    return ScheduledTask(
        id=30,
        owner_user_id=1,
        task_type="collection",
        market_scope="cn_stock",
        name="抖音四大指数情绪日更",
        enabled=False,
        schedule_time="07:00",
        config_json={"collector_key": "douyin_coze_emotion_daily"},
        last_run_status=status,
        last_run_summary="旧摘要",
        last_error_message="",
    )


def _make_terminal_run() -> ScheduledTaskRun:
    return ScheduledTaskRun(
        id=4448,
        scheduled_task_id=30,
        trigger_type="manual",
        status="failed",
        scheduled_for=datetime(2026, 9, 2, 3, 25, 18),
        started_at=datetime(2026, 9, 2, 3, 25, 18),
        finished_at=datetime(2026, 9, 2, 3, 40, 40),
        summary="任务已终止",
        error_message="文案提取失败",
    )


def _make_service() -> TaskService:
    service = TaskService.__new__(TaskService)
    service.db = _RecordingSession()
    return service


def test_reconcile_stale_last_run_state_uses_latest_terminal_run(monkeypatch):
    service = _make_service()
    task = _make_task()
    run = _make_terminal_run()
    monkeypatch.setattr(service, "_has_active_task_run", lambda _task_id: False)
    monkeypatch.setattr(service, "_latest_task_run", lambda _task_id: run)

    changed = service._reconcile_stale_last_run_state(task)

    assert changed is True
    assert task.last_run_status == "failed"
    assert task.last_run_at == datetime(2026, 9, 2, 3, 40, 40)
    assert task.last_run_summary == "任务已终止"
    assert task.last_error_message == "文案提取失败"
    assert service.db.added == [task]


def test_reconcile_stale_last_run_state_preserves_real_active_run(monkeypatch):
    service = _make_service()
    task = _make_task()
    monkeypatch.setattr(service, "_has_active_task_run", lambda _task_id: True)
    monkeypatch.setattr(
        service,
        "_latest_task_run",
        lambda _task_id: (_ for _ in ()).throw(AssertionError("latest run should not be queried")),
    )

    changed = service._reconcile_stale_last_run_state(task)

    assert changed is False
    assert task.last_run_status == "running"
    assert service.db.added == []


def test_reconcile_stale_last_run_state_ignores_terminal_task_card(monkeypatch):
    service = _make_service()
    task = _make_task(status="failed")
    monkeypatch.setattr(
        service,
        "_has_active_task_run",
        lambda _task_id: (_ for _ in ()).throw(AssertionError("active run should not be queried")),
    )

    changed = service._reconcile_stale_last_run_state(task)

    assert changed is False
    assert service.db.added == []
