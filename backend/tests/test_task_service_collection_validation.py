from datetime import date, datetime, timedelta

import pytest

from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
import app.services.task_service as task_service_module
from app.services.task_service import TaskRunPollingPending, TaskService


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


def test_douyin_no_update_marks_run_skipped(monkeypatch):
    task = _make_collection_task("douyin_coze_emotion_daily")
    task.schedule_time = "19:00"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 6, 28, 21, 0)
    db = _FakeSession(tasks=[task], runs=[run])
    service = TaskService(db)
    service._now = lambda: datetime(2026, 6, 28, 21, 0)

    requests = []

    def fake_run_daily_collection_request(**kwargs):
        requests.append(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "douyin_coze_emotion_daily",
                "result": {
                    "status": "NO_UPDATE",
                    "target_date": "2026-06-28",
                    "latest_video_date": "2026-06-27",
                    "minimum_publish_time": "15:00",
                },
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        fake_run_daily_collection_request,
    )

    result = service.execute_run(run.id)

    assert result["status"] == "skipped"
    assert task.last_run_status == "skipped"
    assert "截至 21:00 仍未发现 15:00 后发布的新作品" in result["summary"]
    assert "今日轮询已结束" in result["summary"]
    assert requests[0]["payload"] == {
        "target_date": "2026-06-28",
        "keep_browser_open": False,
        "browser_close_at": "2026-06-28T21:00:00",
    }


def test_douyin_no_update_before_deadline_reports_next_check(monkeypatch):
    task = _make_collection_task("douyin_coze_emotion_daily")
    task.schedule_time = "19:00"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 6, 28, 20, 15)
    db = _FakeSession(tasks=[task], runs=[run])
    service = TaskService(db)
    service._now = lambda: datetime(2026, 6, 28, 20, 15, 20)

    requests = []

    def fake_run_daily_collection_request(**kwargs):
        requests.append(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "douyin_coze_emotion_daily",
                "result": {
                    "status": "NO_UPDATE",
                    "target_date": "2026-06-28",
                    "latest_video_date": "2026-06-27",
                    "minimum_publish_time": "15:00",
                },
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        fake_run_daily_collection_request,
    )

    with pytest.raises(TaskRunPollingPending, match="20:16"):
        service.execute_run(run.id)

    assert run.status == "running"
    assert "同一条运行记录" in run.summary
    assert requests[0]["payload"] == {
        "target_date": "2026-06-28",
        "keep_browser_open": True,
        "browser_close_at": "2026-06-28T21:00:00",
    }


def test_douyin_detected_content_processing_failure_stops_daily_polling(monkeypatch):
    task = _make_collection_task("douyin_coze_emotion_daily")
    task.schedule_time = "19:00"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 6, 28, 19, 8)
    db = _FakeSession(tasks=[task], runs=[run])
    service = TaskService(db)
    service._now = lambda: datetime(2026, 6, 28, 19, 8, 20)

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "douyin_coze_emotion_daily",
                "result": {
                    "status": "UPDATE_FOUND_FAILED",
                    "target_date": "2026-06-28",
                    "video_id": "123",
                    "error": "文案日期 2026-06-27 与作品发布日期 2026-06-28 不一致",
                },
            },
        },
    )

    result = service.execute_run(run.id)

    assert result["status"] == "failed"
    assert result["summary"].startswith("已发现当天新作品")
    assert "今日轮询已停止" in result["summary"]
    assert task.last_run_status == "failed"


def test_douyin_incomplete_extraction_continues_daily_polling(monkeypatch):
    task = _make_collection_task("douyin_coze_emotion_daily")
    task.schedule_time = "19:00"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 6, 28, 19, 8)
    db = _FakeSession(tasks=[task], runs=[run])
    service = TaskService(db)
    service._now = lambda: datetime(2026, 6, 28, 19, 18, 20)

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "douyin_coze_emotion_daily",
                "result": {
                    "status": "UPDATE_FOUND_FAILED",
                    "target_date": "2026-06-28",
                    "video_id": "123",
                    "error": "文案缺少上证50情绪指标",
                },
            },
        },
    )

    with pytest.raises(TaskRunPollingPending, match="同一条运行记录"):
        service.execute_run(run.id)

    assert run.status == "running"
    assert "文案缺少上证50情绪指标" in run.summary


def test_douyin_transient_processing_failure_continues_daily_polling(monkeypatch):
    task = _make_collection_task("douyin_coze_emotion_daily")
    task.schedule_time = "19:00"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 6, 28, 19, 8)
    db = _FakeSession(tasks=[task], runs=[run])
    service = TaskService(db)
    service._now = lambda: datetime(2026, 6, 28, 19, 18, 20)

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "douyin_coze_emotion_daily",
                "result": {
                    "status": "UPDATE_FOUND_RETRYABLE",
                    "target_date": "2026-06-28",
                    "video_id": "123",
                    "error": "等待 Coze 视频文案超时",
                },
            },
        },
    )

    with pytest.raises(TaskRunPollingPending, match="同一条运行记录"):
        service.execute_run(run.id)

    assert run.status == "running"
    assert "等待 Coze 视频文案超时" in run.summary


def test_douyin_success_requires_four_rows_and_clears_caches(monkeypatch):
    task = _make_collection_task("douyin_coze_emotion_daily")
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 6, 28, 20, 55)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[{"target_count": 4, "latest_date": date(2026, 6, 28)}],
    )
    service = TaskService(db)
    cleared = []
    monkeypatch.setattr(service.stock_service, "clear_index_emotions_cache", lambda: cleared.append("emotion"))
    monkeypatch.setattr(
        service.quant_service,
        "clear_index_dashboard_cache",
        lambda market: cleared.append(f"dashboard:{market}"),
    )
    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "douyin_coze_emotion_daily",
                "result": {
                    "status": "SUCCESS",
                    "target_date": "2026-06-28",
                    "video_id": "123",
                    "values": {
                        "sz50_emotion": 51,
                        "hs300_emotion": 52,
                        "zz500_emotion": 53,
                        "zz1000_emotion": 54,
                    },
                },
            },
        },
    )

    result = service.execute_run(run.id)

    assert result["status"] == "success"
    assert cleared == ["emotion", "dashboard:cn"]
    assert "上证50=51" in result["summary"]


def test_execute_run_succeeds_when_target_rows_exist(monkeypatch):
    task = _make_collection_task("index_qvix_daily")
    run = _make_run(task.id)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 5, "latest_date": date(2026, 4, 30)},
            {"missing_date_count": 0, "missing_summary": None},
        ],
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


def test_qvix_validation_fails_when_recent_backfill_has_gaps():
    service = TaskService(
        _FakeSession(
            execute_rows=[
                {"target_count": 5, "latest_date": date(2026, 7, 8)},
                {
                    "missing_date_count": 2,
                    "missing_summary": "2026-07-01:50ETF_QVIX,300ETF_QVIX；2026-07-02:50ETF_QVIX",
                },
            ]
        )
    )
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 8))

    with pytest.raises(RuntimeError) as exc_info:
        service._validate_collection_result(
            "index_qvix_daily",
            "QVIX 日更",
            {"upstream_response": {"result": {"latest_source_trade_date": "2026-07-08"}}},
            datetime(2026, 7, 8, 20, 30),
        )

    message = str(exc_info.value)
    assert "近30个A股交易日QVIX仍有缺口" in message
    assert "2026-07-01:50ETF_QVIX,300ETF_QVIX" in message


def test_exchange_option_daily_validates_both_exchanges_contract_rows(monkeypatch):
    task = _make_collection_task("exchange_option_daily")
    run = _make_run(task.id)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 600, "latest_date": date(2026, 4, 30)},
            {"target_count": 300, "latest_date": date(2026, 4, 30)},
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 4, 30))
    requests = []

    def fake_run_daily_collection_request(**kwargs):
        requests.append(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "exchange_option_daily",
                "result": {"status": "SUCCESS", "target_date": "2026-04-30"},
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        fake_run_daily_collection_request,
    )

    result = service.execute_run(run.id)

    assert result["status"] == "success"
    assert requests[0]["collector_key"] == "exchange_option_daily"
    assert requests[0]["endpoint"] == "/collect-exchange-option-daily"
    assert requests[0]["payload"] == {"target_date": "2026-04-30"}
    assert "上交所期权合约官方量额600行" in result["summary"]
    assert "深交所期权合约官方量额300行" in result["summary"]


def test_exchange_option_stats_daily_requires_all_nine_products(monkeypatch):
    task = _make_collection_task("exchange_option_stats_daily")
    run = _make_run(task.id)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 5, "latest_date": date(2026, 4, 30)},
            {"target_count": 4, "latest_date": date(2026, 4, 30)},
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 4, 30))
    requests = []

    def fake_run_daily_collection_request(**kwargs):
        requests.append(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "exchange_option_stats_daily",
                "result": {"status": "SUCCESS", "target_date": "2026-04-30"},
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        fake_run_daily_collection_request,
    )

    result = service.execute_run(run.id)

    assert result["status"] == "success"
    assert requests[0]["collector_key"] == "exchange_option_stats_daily"
    assert requests[0]["endpoint"] == "/collect-exchange-option-stats-daily"
    assert requests[0]["payload"] == {"target_date": "2026-04-30"}
    assert "上交所期权产品5行" in result["summary"]
    assert "深交所期权产品4行" in result["summary"]


def test_option_minute_daily_requires_all_ten_raw_and_vix_sources(monkeypatch):
    task = _make_collection_task("option_minute_daily")
    run = _make_run(task.id)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 242, "latest_date": date(2026, 7, 13)}
            for _ in range(20)
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 13))
    requests = []

    def fake_run_daily_collection_request(**kwargs):
        requests.append(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "option_minute_daily",
                "result": {"status": "SUCCESS", "target_date": "2026-07-13"},
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        fake_run_daily_collection_request,
    )

    result = service.execute_run(run.id)

    assert result["status"] == "success"
    assert requests[0]["endpoint"] == "/collect-option-minute-daily"
    assert requests[0]["payload"] == {"target_date": "2026-07-13"}
    assert "cffex:HO原始分钟242分钟" in result["summary"]
    assert "cffex:HO分钟VIX242行" in result["summary"]
    assert "szse:159922分钟VIX242行" in result["summary"]


def test_option_minute_daily_warns_for_partial_vix_when_raw_minutes_are_complete(monkeypatch):
    task = _make_collection_task("option_minute_daily")
    run = _make_run(task.id)
    vix_counts = [242, 242, 242, 242, 241, 241, 147, 224, 241, 126]
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            *[
                {"target_count": 242, "latest_date": date(2026, 7, 17)}
                for _ in range(10)
            ],
            *[
                {"target_count": count, "latest_date": date(2026, 7, 17)}
                for count in vix_counts
            ],
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 17))

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "option_minute_daily",
                "result": {"status": "SUCCESS", "target_date": "2026-07-17"},
            },
        },
    )

    result = service.execute_run(run.id)

    assert result["status"] == "success"
    assert "sse:588000分钟VIX147行（质量告警" in result["summary"]
    assert "szse:159922分钟VIX126行（质量告警" in result["summary"]


def test_us_futures_validation_accepts_immediately_previous_upstream_trade_date(monkeypatch):
    task = _make_collection_task("us_index_futures_daily", market_scope="us_index")
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 5, 2, 9, 0)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 0, "latest_date": date(2026, 4, 30)},
            {"target_count": 2, "latest_date": date(2026, 4, 30)},
        ],
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

    result = service.execute_run(run.id)

    assert db.executed[0][1]["target_trade_date"] == date(2026, 5, 1)
    assert db.executed[1][1]["target_trade_date"] == date(2026, 4, 30)
    assert result["status"] == "success"
    assert "实际更新并确认的是前一美股交易日 2026-04-30" in result["summary"]


def test_us_futures_validation_rejects_data_older_than_previous_trade_date(monkeypatch):
    task = _make_collection_task("us_index_futures_daily", market_scope="us_index")
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 5, 2, 9, 0)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 0, "latest_date": date(2026, 4, 29)},
            {"target_count": 0, "latest_date": date(2026, 4, 29)},
        ],
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
                "result": {"trade_date": "2026-04-29", "collection": 2},
            },
        },
    )

    with pytest.raises(RuntimeError) as exc_info:
        service.execute_run(run.id)

    assert "目标交易日 2026-05-01 数据未完整入库" in str(exc_info.value)
    assert "2026-04-29" in str(exc_info.value)


def test_cme_network_block_is_skipped_with_latest_official_date(monkeypatch):
    task = _make_collection_task("us_index_futures_official_daily", market_scope="us_index")
    run = _make_run(task.id)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[{"target_count": 0, "latest_date": date(2026, 7, 17)}],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 20), previous_date=date(2026, 7, 17))

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError(
                'upstream returned 500, body={"error":"CME settlements official API blocked the request (HTTP 403)"}'
            )
        ),
    )

    result = service.execute_run(run.id)

    assert result["status"] == "skipped"
    assert "CME 官方结算接口拒绝当前网络请求" in result["summary"]
    assert "2026-07-17" in result["summary"]


def test_duplicate_daily_collection_is_skipped_before_validation(monkeypatch):
    task = _make_collection_task("index_us_vix_daily", market_scope="us_index")
    run = _make_run(task.id)
    db = _FakeSession(tasks=[task], runs=[run])
    service = TaskService(db)

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "requested_at": "2026-07-29",
            "status": "deduplicated",
            "message": "same daily collection is already running",
        },
    )

    result = service.execute_run(run.id)

    assert result["status"] == "skipped"
    assert "已有同类型采集正在运行" in result["summary"]
    assert db.executed == []


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


@pytest.mark.parametrize(
    "collector_key,label,target_count",
    [
        ("index_us_treasury_yield_daily", "美债收益率日更", 1),
        ("index_us_credit_spread_daily", "美股高收益债利差日更", 1),
        ("us_index_futures_official_daily", "美股股指期货官方合约日更", 2),
    ],
)
def test_lagged_us_releases_validate_previous_us_trading_day(collector_key, label, target_count):
    db = _FakeSession(execute_rows=[{"target_count": target_count, "latest_date": date(2026, 7, 17)}])
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(
        date(2026, 7, 20),
        previous_date=date(2026, 7, 17),
    )

    summary = service._validate_collection_result(
        collector_key,
        label,
        {"upstream_response": {"result": 1}},
        datetime(2026, 7, 21, 5, 30),
    )

    assert db.executed[0][1]["target_trade_date"] == date(2026, 7, 17)
    assert "已确认 2026-07-17 数据入库" in summary


def test_monthly_us_hedge_proxy_validates_latest_release_instead_of_daily_target():
    db = _FakeSession(
        execute_rows=[
            {"target_count": 0, "latest_date": date(2026, 6, 19)},
            {"target_count": 2, "latest_date": date(2026, 6, 19)},
        ]
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 20))

    summary = service._validate_collection_result(
        "index_us_hedge_proxy_daily",
        "OFR 美股持仓代理月更",
        {"upstream_response": {"result": 0}},
        datetime(2026, 7, 21, 9, 30),
    )

    assert db.executed[1][1]["target_trade_date"] == date(2026, 6, 19)
    assert "最新月度发布2026-06-19共2行" in summary


def test_monthly_us_hedge_proxy_rejects_stale_release():
    db = _FakeSession(
        execute_rows=[
            {"target_count": 0, "latest_date": date(2026, 5, 1)},
            {"target_count": 2, "latest_date": date(2026, 5, 1)},
        ]
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 20))

    with pytest.raises(RuntimeError) as exc_info:
        service._validate_collection_result(
            "index_us_hedge_proxy_daily",
            "OFR 美股持仓代理月更",
            {"upstream_response": {"result": 0}},
            datetime(2026, 7, 21, 9, 30),
        )

    assert "已超过45天未更新" in str(exc_info.value)


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


def test_hk_index_futures_scheduled_run_passes_current_trade_date(monkeypatch):
    task = _make_collection_task("hk_index_futures_daily", market_scope="hk_index")
    task.schedule_time = "22:45"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 7, 23, 22, 45)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 36, "latest_date": date(2026, 7, 23)},
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 23), trading=True)
    captured_kwargs = {}

    def _fake_run_daily_collection_request(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "hk_index_futures_daily",
                "result": {
                    "status": "SUCCESS",
                    "target_date": "2026-07-23",
                    "collection": 36,
                },
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        _fake_run_daily_collection_request,
    )

    result = service.execute_run(run.id)

    assert captured_kwargs["payload"] == {"target_date": "2026-07-23"}
    assert db.executed[0][1]["target_trade_date"] == date(2026, 7, 23)
    assert result["status"] == "success"


def test_hk_index_futures_waits_in_same_run_when_report_is_not_ready(monkeypatch):
    task = _make_collection_task("hk_index_futures_daily", market_scope="hk_index")
    task.schedule_time = "22:45"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 7, 23, 22, 45)
    db = _FakeSession(tasks=[task], runs=[run])
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 23), trading=True)
    service._now = lambda: datetime(2026, 7, 23, 22, 50)

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        lambda **_kwargs: {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "hk_index_futures_daily",
                "result": {
                    "status": "SOURCE_NOT_READY",
                    "target_date": "2026-07-23",
                    "available_products": ["HSI"],
                    "expected_products": ["HSI", "HHI", "HTI"],
                },
            },
        },
    )

    with pytest.raises(TaskRunPollingPending) as exc_info:
        service.execute_run(run.id)

    assert exc_info.value.countdown_seconds == 300
    assert "同一条运行记录内继续检查" in str(exc_info.value)
    assert run.status == "running"


def test_quant_index_manual_run_uses_previous_trade_date_before_schedule(monkeypatch):
    task = _make_collection_task("quant_index_daily")
    task.schedule_time = "17:30"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 7, 6, 8, 30)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 9, "latest_date": date(2026, 7, 3)},
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(
        date(2026, 7, 6),
        trading=True,
        previous_date=date(2026, 7, 3),
    )
    captured_kwargs = {}

    def _fake_run_daily_collection_request(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "quant_index_daily",
                "result": 9,
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        _fake_run_daily_collection_request,
    )

    result = service.execute_run(run.id)

    assert captured_kwargs["payload"] is None
    assert db.executed[0][1]["target_trade_date"] == date(2026, 7, 3)
    assert result["status"] == "success"


def test_cn_macro_manual_run_passes_trade_date_and_requires_complete_indicator(monkeypatch):
    task = _make_collection_task("cn_macro_daily")
    task.schedule_time = "18:10"
    run = _make_run(task.id)
    run.scheduled_for = datetime(2026, 7, 10, 19, 0)
    db = _FakeSession(
        tasks=[task],
        runs=[run],
        execute_rows=[
            {"target_count": 1, "latest_date": date(2026, 7, 10)},
        ],
    )
    service = TaskService(db)
    service.market_calendar = _FixedMarketCalendar(date(2026, 7, 10), trading=True)
    captured_kwargs = {}

    def _fake_run_daily_collection_request(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "status": "ok",
            "upstream_status": "SUCCESS",
            "upstream_response": {
                "task_name": "cn_macro_daily",
                "result": {"indicator_rows": {"rows": 1}},
            },
        }

    monkeypatch.setattr(
        task_service_module,
        "run_daily_collection_request",
        _fake_run_daily_collection_request,
    )

    result = service.execute_run(run.id)

    assert captured_kwargs["endpoint"] == "/collect-cn-macro-daily"
    assert captured_kwargs["payload"] == {"target_date": "2026-07-10"}
    assert db.executed[0][1]["target_trade_date"] == date(2026, 7, 10)
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
