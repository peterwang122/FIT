from datetime import date, datetime, time, timedelta

from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
import app.services.task_service as task_service_module
from app.services.task_service import TaskService


class _FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        if self.model is ScheduledTask:
            return list(self.session.tasks)
        if self.model is ScheduledTaskRun:
            return list(self.session.runs)
        return []

    def first(self):
        items = self.all()
        return items[0] if items else None


class _FakeSession:
    def __init__(self, tasks=None, runs=None):
        self.tasks = list(tasks or [])
        self.runs = list(runs or [])

    def query(self, model):
        return _FakeQuery(self, model)

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

    def add(self, instance):
        if isinstance(instance, ScheduledTask):
            for index, item in enumerate(self.tasks):
                if item.id == instance.id:
                    self.tasks[index] = instance
                    return
            self.tasks.append(instance)
            return

        if isinstance(instance, ScheduledTaskRun):
            if getattr(instance, "id", None) is None:
                instance.id = len(self.runs) + 1
            for index, item in enumerate(self.runs):
                if item.id == instance.id:
                    self.runs[index] = instance
                    return
            self.runs.append(instance)

    def commit(self):
        return None

    def refresh(self, instance):
        if isinstance(instance, ScheduledTaskRun) and getattr(instance, "id", None) is None:
            instance.id = len(self.runs) + 1


class _ClosedMarketCalendar:
    def normalize_market_scope(self, market_scope):
        return str(market_scope or "cn_stock")

    def current_market_date(self, _market_scope, reference_dt):
        return reference_dt.date()

    def is_trading_day(self, _market_scope, _target_date):
        return False

    def next_trading_day(self, _market_scope, target_date):
        return target_date + timedelta(days=1)

    def previous_trading_day(self, _market_scope, target_date):
        return target_date - timedelta(days=1)

    def market_open_time(self, _market_scope, _target_date=None):
        return time(hour=21, minute=30)


class _OpenMarketCalendar(_ClosedMarketCalendar):
    def is_trading_day(self, _market_scope, _target_date):
        return True


class _RecordingMarketCalendar:
    def __init__(self):
        self.open_time_calls = []

    def normalize_market_scope(self, market_scope):
        return str(market_scope or "cn_stock")

    def current_market_date(self, _market_scope, reference_dt):
        return reference_dt.date()

    def market_open_time(self, market_scope, target_date=None):
        self.open_time_calls.append((market_scope, target_date))
        return time(hour=20, minute=30)

    def previous_trading_day(self, _market_scope, _target_date):
        return date(2026, 6, 12)


def _make_task(task_id: int, market_scope: str) -> ScheduledTask:
    return ScheduledTask(
        id=task_id,
        owner_user_id=1,
        task_type="collection",
        market_scope=market_scope,
        name=f"{market_scope}-task",
        enabled=True,
        schedule_time="09:00",
        config_json={"target_type": "index", "target_code": "ALL_US_INDEX", "target_name": "美股指数全市场"},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )


def test_enqueue_due_task_runs_skips_closed_market_scope():
    task = _make_task(1, "us_index")
    db = _FakeSession(tasks=[task])
    service = TaskService(db)
    service.market_calendar = _ClosedMarketCalendar()
    service._now = lambda: datetime(2026, 4, 19, 9, 0)

    run_ids = service.enqueue_due_task_runs()

    assert run_ids == []
    assert len(db.runs) == 1
    assert db.runs[0].status == "skipped"
    assert db.runs[0].summary == "当前市场休市，已跳过自动调度。"
    assert task.last_scheduled_date == date(2026, 4, 19)


def test_enqueue_due_task_runs_catches_up_missed_schedule_minute():
    task = _make_task(1, "cn_stock")
    task.schedule_time = "17:01"
    db = _FakeSession(tasks=[task])
    service = TaskService(db)
    service.market_calendar = _OpenMarketCalendar()
    service._now = lambda: datetime(2026, 4, 20, 17, 12)

    run_ids = service.enqueue_due_task_runs()

    assert run_ids == [1]
    assert len(db.runs) == 1
    assert db.runs[0].status == "queued"
    assert db.runs[0].scheduled_for == datetime(2026, 4, 20, 17, 1)
    assert task.last_scheduled_date == date(2026, 4, 20)


def test_enqueue_due_task_runs_ignores_future_schedule_time():
    task = _make_task(1, "cn_stock")
    task.schedule_time = "17:30"
    db = _FakeSession(tasks=[task])
    service = TaskService(db)
    service.market_calendar = _OpenMarketCalendar()
    service._now = lambda: datetime(2026, 4, 20, 17, 12)

    run_ids = service.enqueue_due_task_runs()

    assert run_ids == []
    assert db.runs == []
    assert task.last_scheduled_date is None


def test_create_manual_run_keeps_forced_execution_even_when_market_is_closed():
    task = _make_task(1, "us_index")
    db = _FakeSession(tasks=[task])
    service = TaskService(db)
    service.market_calendar = _ClosedMarketCalendar()

    run = service.create_manual_run(task.id, task.owner_user_id)

    assert run["trigger_type"] == "manual"
    assert run["status"] == "queued"
    assert len(db.runs) == 1
    assert db.runs[0].status == "queued"


def test_notification_basis_trade_date_uses_market_open_time_for_current_trade_day():
    db = _FakeSession()
    service = TaskService(db)
    recording_calendar = _RecordingMarketCalendar()
    service.market_calendar = recording_calendar

    basis_trade_date = service._notification_basis_trade_date("us_index", datetime(2026, 6, 15, 20, 0))

    assert basis_trade_date == date(2026, 6, 12)
    assert recording_calendar.open_time_calls == [("us_index", date(2026, 6, 15))]


class _UsSundayCalendar(_ClosedMarketCalendar):
    def current_market_date(self, _market_scope, _reference_dt):
        return date(2026, 4, 19)


class _UsMondayCalendar(_OpenMarketCalendar):
    def current_market_date(self, _market_scope, _reference_dt):
        return date(2026, 4, 20)


def test_enqueue_due_task_runs_uses_market_local_date_for_us_scope():
    task = _make_task(1, "us_index")
    db = _FakeSession(tasks=[task])
    service = TaskService(db)
    service.market_calendar = _UsSundayCalendar()
    service._now = lambda: datetime(2026, 4, 20, 9, 0)

    run_ids = service.enqueue_due_task_runs()

    assert run_ids == []
    assert len(db.runs) == 1
    assert db.runs[0].status == "skipped"
    assert task.last_scheduled_date == date(2026, 4, 19)


def test_enqueue_due_task_runs_uses_scheduled_for_to_recover_from_stale_market_date_marker():
    task = _make_task(1, "us_index")
    task.last_scheduled_date = date(2026, 4, 20)
    db = _FakeSession(tasks=[task])
    service = TaskService(db)
    service.market_calendar = _UsMondayCalendar()
    service._now = lambda: datetime(2026, 4, 21, 10, 0)

    run_ids = service.enqueue_due_task_runs()

    assert run_ids == [1]
    assert len(db.runs) == 1
    assert db.runs[0].status == "queued"
    assert db.runs[0].scheduled_for == datetime(2026, 4, 21, 9, 0)
    assert task.last_scheduled_date == date(2026, 4, 20)


def test_normalize_collector_key_infers_legacy_daily_tasks_from_name():
    service = TaskService(_FakeSession())

    assert (
        service._normalize_collector_key(
            None,
            "us_index",
            target_type=None,
            target_code=None,
            target_name=None,
            task_name="美股 VIX 日更",
        )
        == "index_us_vix_daily"
    )
    assert (
        service._normalize_collector_key(
            None,
            "us_index",
            target_type=None,
            target_code=None,
            target_name=None,
            task_name="美股恐贪指数日更",
        )
        == "index_us_fear_greed_daily"
    )
    assert (
        service._normalize_collector_key(
            None,
            "us_index",
            target_type=None,
            target_code=None,
            target_name=None,
            task_name="美股对冲基金代理日更",
        )
        == "index_us_hedge_proxy_daily"
    )
    assert (
        service._normalize_collector_key(
            None,
            "cn_stock",
            target_type=None,
            target_code=None,
            target_name=None,
            task_name="北证50日更",
        )
        == "index_bj50_daily"
    )
    assert (
        service._normalize_collector_key(
            None,
            "cn_stock",
            target_type=None,
            target_code=None,
            target_name=None,
            task_name="QVIX 日更",
        )
        == "index_qvix_daily"
    )
    assert (
        service._normalize_collector_key(
            None,
            "hk_index",
            target_type=None,
            target_code=None,
            target_name=None,
            task_name="港股股指期货日更",
        )
        == "hk_index_futures_daily"
    )
    assert (
        service._normalize_collector_key(
            None,
            "us_index",
            target_type=None,
            target_code=None,
            target_name=None,
            task_name="美股股指期货日更",
        )
        == "us_index_futures_daily"
    )


def test_effective_task_market_scope_prefers_inferred_collector_key_scope():
    task = ScheduledTask(
        id=99,
        owner_user_id=1,
        task_type="collection",
        market_scope="cn_stock",
        name="美股 VIX 日更",
        enabled=True,
        schedule_time="09:00",
        config_json={},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )
    service = TaskService(_FakeSession(tasks=[task]))

    assert service._effective_task_market_scope(task) == "us_index"


def test_execute_collection_task_routes_legacy_us_vix_to_daily_endpoint():
    task = ScheduledTask(
        id=100,
        owner_user_id=1,
        task_type="collection",
        market_scope="cn_stock",
        name="美股 VIX 日更",
        enabled=True,
        schedule_time="09:00",
        config_json={},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )
    service = TaskService(_FakeSession(tasks=[task]))
    calls = []

    original_daily = task_service_module.run_daily_collection_request
    original_stock = task_service_module.run_stock_hfq_collection_request

    def fake_daily(**kwargs):
        calls.append(("daily", kwargs))
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {"result": "ok"},
        }

    def fake_stock(**kwargs):
        calls.append(("stock", kwargs))
        raise AssertionError("daily collection task must not use single-stock collect endpoint")

    try:
        task_service_module.run_daily_collection_request = fake_daily
        task_service_module.run_stock_hfq_collection_request = fake_stock

        summary = service._execute_collection_task(task)
    finally:
        task_service_module.run_daily_collection_request = original_daily
        task_service_module.run_stock_hfq_collection_request = original_stock

    assert summary == "美股 VIX 日更执行完成，结果：ok。"
    assert calls == [
        (
            "daily",
            {
                "collector_key": "index_us_vix_daily",
                "endpoint": "/collect-index-us-vix-daily",
            },
        )
    ]


def test_execute_collection_task_routes_bj50_daily_to_dedicated_endpoint():
    task = ScheduledTask(
        id=101,
        owner_user_id=1,
        task_type="collection",
        market_scope="cn_stock",
        name="北证50日更",
        enabled=True,
        schedule_time="17:00",
        config_json={},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )
    service = TaskService(_FakeSession(tasks=[task]))
    calls = []

    original_daily = task_service_module.run_daily_collection_request
    original_stock = task_service_module.run_stock_hfq_collection_request

    def fake_daily(**kwargs):
        calls.append(("daily", kwargs))
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {"result": "ok"},
        }

    def fake_stock(**kwargs):
        calls.append(("stock", kwargs))
        raise AssertionError("daily collection task must not use single-stock collect endpoint")

    try:
        task_service_module.run_daily_collection_request = fake_daily
        task_service_module.run_stock_hfq_collection_request = fake_stock

        summary = service._execute_collection_task(task)
    finally:
        task_service_module.run_daily_collection_request = original_daily
        task_service_module.run_stock_hfq_collection_request = original_stock

    assert "ok" in summary
    assert calls == [
        (
            "daily",
            {
                "collector_key": "index_bj50_daily",
                "endpoint": "/collect-index-bj50-daily",
            },
        )
    ]


def test_execute_collection_task_routes_index_futures_daily_to_dedicated_endpoint():
    task = ScheduledTask(
        id=102,
        owner_user_id=1,
        task_type="collection",
        market_scope="us_index",
        name="美股股指期货日更",
        enabled=True,
        schedule_time="09:00",
        config_json={"collector_key": "us_index_futures_daily"},
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )
    service = TaskService(_FakeSession(tasks=[task]))
    calls = []

    original_daily = task_service_module.run_daily_collection_request
    original_index = task_service_module.run_index_daily_collection_request

    def fake_daily(**kwargs):
        calls.append(("daily", kwargs))
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {"result": "ok"},
        }

    def fake_index(*_args, **_kwargs):
        calls.append(("index", {}))
        raise AssertionError("index futures daily task must use its dedicated daily endpoint")

    try:
        task_service_module.run_daily_collection_request = fake_daily
        task_service_module.run_index_daily_collection_request = fake_index

        summary = service._execute_collection_task(task)
    finally:
        task_service_module.run_daily_collection_request = original_daily
        task_service_module.run_index_daily_collection_request = original_index

    assert "ok" in summary
    assert calls == [
        (
            "daily",
            {
                "collector_key": "us_index_futures_daily",
                "endpoint": "/collect-us-index-futures-daily",
            },
        )
    ]
