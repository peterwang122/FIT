from datetime import date, datetime

import pytest
from pydantic import ValidationError

import app.services.task_service as task_service_module
from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
from app.schemas.task import ManualDouyinEmotionPayload
from app.services.task_service import TaskService


class _FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.items[0] if self.items else None


class _FakeSession:
    def __init__(self, task):
        self.task = task
        self.runs = []
        self.executed = []
        self.rollback_count = 0

    def query(self, model):
        return _FakeQuery([self.task] if model is ScheduledTask else [])

    def add(self, item):
        if isinstance(item, ScheduledTaskRun):
            if item.id is None:
                item.id = len(self.runs) + 1
            if item not in self.runs:
                self.runs.append(item)

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))

    def commit(self):
        return None

    def rollback(self):
        self.rollback_count += 1

    def refresh(self, _item):
        return None


def _make_task(collector_key="douyin_coze_emotion_daily"):
    return ScheduledTask(
        id=30,
        owner_user_id=1,
        task_type="collection",
        market_scope="cn_stock",
        name="抖音四大指数情绪日更",
        enabled=True,
        schedule_time="19:00",
        config_json={"collector_key": collector_key},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )


def test_manual_douyin_emotions_upserts_four_rows_and_recomputes(monkeypatch):
    db = _FakeSession(_make_task())
    service = TaskService(db)
    service._now = lambda: datetime(2026, 9, 2, 10, 0)
    service.stock_service.clear_index_emotions_cache = lambda: 4
    service.quant_service.clear_index_dashboard_cache = lambda _market: 8
    requests = []

    def fake_recompute(**kwargs):
        requests.append(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(task_service_module, "run_daily_collection_request", fake_recompute)

    result = service.save_manual_douyin_emotions(
        task_id=30,
        owner_user_id=1,
        emotion_date=date(2026, 9, 1),
        values={
            "sz50_emotion": 61,
            "hs300_emotion": 52.345,
            "zz500_emotion": 43,
            "zz1000_emotion": 34,
        },
    )

    assert len(db.executed) == 1
    rows = db.executed[0][1]
    assert [row["index_name"] for row in rows] == ["上证50", "沪深300", "中证500", "中证1000"]
    assert rows[1]["emotion_value"] == 52.34
    assert {row["data_source"] for row in rows} == {"manual_task_center"}
    assert requests == [
        {
            "collector_key": "quant_index_daily",
            "endpoint": "/collect-quant-index-daily",
            "payload": {"target_date": "2026-09-01"},
        }
    ]
    assert result["emotion_date"] == date(2026, 9, 1)
    assert result["run"]["status"] == "success"
    assert db.task.last_run_status == "success"


def test_manual_douyin_emotions_rejects_other_tasks():
    service = TaskService(_FakeSession(_make_task("index_qvix_daily")))

    with pytest.raises(ValueError, match="only available"):
        service.save_manual_douyin_emotions(
            task_id=30,
            owner_user_id=1,
            emotion_date=date(2026, 9, 1),
            values={
                "sz50_emotion": 1,
                "hs300_emotion": 2,
                "zz500_emotion": 3,
                "zz1000_emotion": 4,
            },
        )


def test_manual_douyin_emotion_payload_enforces_range():
    with pytest.raises(ValidationError):
        ManualDouyinEmotionPayload(
            emotion_date=date(2026, 9, 1),
            sz50_emotion=101,
            hs300_emotion=50,
            zz500_emotion=50,
            zz1000_emotion=50,
        )
