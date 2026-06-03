from datetime import date, datetime, timedelta

import pytest

from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
import app.services.task_service as task_service_module
from app.services.task_service import TaskService


class _FakeExecuteResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class _FakeSession:
    def __init__(self, *, tasks=None, runs=None, execute_rows=None):
        self.tasks = list(tasks or [])
        self.runs = list(runs or [])
        self.execute_rows = list(execute_rows or [])
        self.executed = []

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
            for index, item in enumerate(self.runs):
                if item.id == instance.id:
                    self.runs[index] = instance
                    return
            self.runs.append(instance)

    def commit(self):
        return None

    def refresh(self, _instance):
        return None

    def execute(self, statement, params=None):
        self.executed.append((str(statement), dict(params or {})))
        row = self.execute_rows.pop(0) if self.execute_rows else {"target_count": 0, "latest_date": None}
        return _FakeExecuteResult(row)


class _FixedMarketCalendar:
    def __init__(self, market_date, *, trading=True, previous_date=None):
        self.market_date = market_date
        self.trading = trading
        self.previous_date = previous_date or (market_date - timedelta(days=1))

    def normalize_market_scope(self, market_scope):
        return str(market_scope or "cn_stock")

    def current_market_date(self, _market_scope, _reference_dt):
        return self.market_date

    def is_trading_day(self, _market_scope, _target_date):
        return self.trading

    def previous_trading_day(self, _market_scope, _target_date):
        return self.previous_date


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


def test_collection_validation_fails_when_target_trade_date_is_missing():
    service = TaskService(
        _FakeSession(execute_rows=[{"target_count": 0, "latest_date": date(2026, 4, 29)}])
    )
    service.market_calendar = _FixedMarketCalendar(date(2026, 4, 30))

    with pytest.raises(RuntimeError) as exc_info:
        service._validate_collection_result(
            "index_qvix_daily",
            "QVIX 日更",
            {"upstream_response": {"result": 5}},
            datetime(2026, 4, 30, 17, 0),
        )

    message = str(exc_info.value)
    assert "目标交易日 2026-04-30 数据未完整入库" in message
    assert "当前最新2026-04-29" in message
    assert "上游返回：5" in message


def test_execute_run_marks_failed_when_upstream_success_has_no_target_rows(monkeypatch):
    task = _make_collection_task("index_qvix_daily")
    run = _make_run(task.id)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[{"target_count": 0, "latest_date": date(2026, 4, 29)}],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 4, 30))

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {"task_name": "index_qvix_daily", "result": 5},
        },
    )

    with pytest.raises(RuntimeError):
        service.execute_run(run.id)

    assert run.status == "failed"
    assert task.last_run_status == "failed"
    assert "目标交易日 2026-04-30 数据未完整入库" in run.error_message


def test_execute_run_succeeds_when_target_rows_exist(monkeypatch):
    task = _make_collection_task("index_qvix_daily")
    run = _make_run(task.id)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[{"target_count": 5, "latest_date": date(2026, 4, 30)}],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 4, 30))

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {"task_name": "index_qvix_daily", "result": 5},
        },
    )

    result = service.execute_run(run.id)

    assert result["status"] == "success"
    assert task.last_run_status == "success"
    assert "已确认 2026-04-30 数据入库：QVIX5行" in result["summary"]


def test_us_futures_validation_rejects_stale_upstream_trade_date(monkeypatch):
    task = _make_collection_task("us_index_futures_daily", market_scope="us_index")
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 5, 2, 9, 0)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[{"target_count": 0, "latest_date": date(2026, 4, 30)}],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 5, 1))

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "us_index_futures_daily",
                "result": {"trade_date": "2026-04-30", "collection": 2},
            },
        },
    )

    with pytest.raises(RuntimeError) as exc_info:
        service.execute_run(run.id)

    assert db.executed[0][1]["target_trade_date"] == date(2026, 5, 1)
    assert "目标交易日 2026-05-01 数据未完整入库" in str(exc_info.value)
    assert "2026-04-30" in str(exc_info.value)


def test_collection_validation_uses_previous_trade_date_when_reference_market_is_closed():
    db = _FakeSession(execute_rows=[{"target_count": 1, "latest_date": date(2026, 5, 1)}])
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(
        date(2026, 5, 2),
        trading=False,
        previous_date=date(2026, 5, 1),
    )

    summary = service._validate_collection_result(
        "index_us_vix_daily",
        "美股 VIX 日更",
        {"upstream_response": {"result": 1}},
        datetime(2026, 5, 2, 14, 0),
    )

    assert db.executed[0][1]["target_trade_date"] == date(2026, 5, 1)
    assert "已确认 2026-05-01 数据入库" in summary


def test_stock_exchange_official_validation_requires_both_sh_and_sz():
    db = _FakeSession(
        execute_rows=[
            {"target_count": 1200, "latest_date": date(2026, 4, 30)},
            {"target_count": 1600, "latest_date": date(2026, 4, 30)},
        ]
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 4, 30))

    summary = service._validate_collection_result(
        "stock_exchange_official_daily",
        "沪深官网股票日更",
        {"upserted": 2800},
        datetime(2026, 4, 30, 18, 30),
    )

    assert db.executed[0][1]["exchange"] == "SH"
    assert db.executed[1][1]["exchange"] == "SZ"
    assert "上交所官网股票日线1200行" in summary
    assert "深交所官网股票日线1600行" in summary


def test_stock_exchange_official_validation_fails_when_one_exchange_missing():
    db = _FakeSession(
        execute_rows=[
            {"target_count": 1200, "latest_date": date(2026, 4, 30)},
            {"target_count": 0, "latest_date": date(2026, 4, 29)},
        ]
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 4, 30))

    with pytest.raises(RuntimeError) as exc_info:
        service._validate_collection_result(
            "stock_exchange_official_daily",
            "沪深官网股票日更",
            {"upserted": 1200, "sz": {"row_count": 0}},
            datetime(2026, 4, 30, 18, 30),
        )

    message = str(exc_info.value)
    assert "深交所官网股票日线目标日2026-04-30仅0行" in message
    assert "上交所官网股票日线" not in message.split("；上游返回：", 1)[0]


def test_stock_exchange_official_manual_run_passes_previous_trade_date_before_schedule(monkeypatch):
    task = _make_collection_task("stock_exchange_official_daily")
    task.schedule_time = "18:30"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 5, 11, 0, 45)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 1200, "latest_date": date(2026, 5, 8)},
            {"target_count": 1600, "latest_date": date(2026, 5, 8)},
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(
        date(2026, 5, 11),
        trading=True,
        previous_date=date(2026, 5, 8),
    )
    captured_kwargs = {}

    def _fake_run_daily_collection_request(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {"task_name": "stock_exchange_official_daily", "result": {"upserted": 2800}},
        }

    monkeypatch.setattr(task_service_module, "run_daily_collection_request", _fake_run_daily_collection_request)

    result = service.execute_run(run.id)

    assert captured_kwargs["payload"] == {"target_date": "2026-05-08"}
    assert db.executed[0][1]["target_trade_date"] == date(2026, 5, 8)
    assert db.executed[1][1]["target_trade_date"] == date(2026, 5, 8)
    assert result["status"] == "success"


def test_cffex_validation_requires_each_product():
    db = _FakeSession(
        execute_rows=[
            {"target_count": 80, "latest_date": date(2026, 5, 8)},
            {"target_count": 60, "latest_date": date(2026, 5, 8)},
            {"target_count": 80, "latest_date": date(2026, 5, 8)},
            {"target_count": 80, "latest_date": date(2026, 5, 8)},
            {"target_count": 20, "latest_date": date(2026, 5, 8)},
            {"target_count": 40, "latest_date": date(2026, 5, 8)},
            {"target_count": 40, "latest_date": date(2026, 5, 8)},
            {"target_count": 40, "latest_date": date(2026, 5, 8)},
        ]
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 5, 8))

    summary = service._validate_collection_result(
        "cffex_daily",
        "中金所会员持仓日更",
        {"result": 440},
        datetime(2026, 5, 8, 18, 0),
    )

    assert [params["target_trade_date"] for _statement, params in db.executed] == [date(2026, 5, 8)] * 8
    assert db.executed[0][1]["cffex_product_if"] == "IF"
    assert db.executed[-1][1]["cffex_product_tl"] == "TL"
    assert "中金所会员持仓-IF80行" in summary
    assert "中金所会员持仓-TL40行" in summary


def test_cffex_validation_fails_when_if_is_missing():
    db = _FakeSession(
        execute_rows=[
            {"target_count": 0, "latest_date": date(2026, 5, 7)},
            {"target_count": 60, "latest_date": date(2026, 5, 8)},
            {"target_count": 80, "latest_date": date(2026, 5, 8)},
            {"target_count": 80, "latest_date": date(2026, 5, 8)},
            {"target_count": 20, "latest_date": date(2026, 5, 8)},
            {"target_count": 40, "latest_date": date(2026, 5, 8)},
            {"target_count": 40, "latest_date": date(2026, 5, 8)},
            {"target_count": 40, "latest_date": date(2026, 5, 8)},
        ]
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 5, 8))

    with pytest.raises(RuntimeError) as exc_info:
        service._validate_collection_result(
            "cffex_daily",
            "中金所会员持仓日更",
            {"result": 360},
            datetime(2026, 5, 8, 18, 0),
        )

    message = str(exc_info.value)
    assert "中金所会员持仓-IF目标日2026-05-08仅0行" in message
    assert "中金所会员持仓-IH" not in message.split("；上游返回：", 1)[0]
