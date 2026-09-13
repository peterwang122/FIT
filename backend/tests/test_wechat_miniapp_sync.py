import hashlib
import hmac
import json
from datetime import date, datetime
from types import SimpleNamespace

from app.services import wechat_miniapp_sync_service as module
from app.services.wechat_miniapp_sync_service import WechatMiniappSyncService
from app.tasks.scheduler import _should_sync_wechat_notification
from app.workers.celery_app import celery_app


class _MappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _ExecuteDb:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return _MappingsResult(self.rows)


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value


class _NotificationDb:
    def __init__(self, values):
        self.values = iter(values)

    def query(self, _model):
        return _Query(next(self.values))


def test_table_sample_exposes_only_neutral_labels():
    source = {
        "total_net_position": 42,
        "total_net_position_text": "净多42",
        "rows": [
            {
                "index_name": "沪深300",
                "short_position": 100,
                "long_position": 142,
                "net_position": 42,
                "net_position_text": "净多42",
                "action": "增多",
            }
        ],
    }

    result = WechatMiniappSyncService._table_sample(source, "ZX样本")

    assert result["label"] == "ZX样本"
    assert result["rows"][0]["group"] == "300"
    assert "沪深300" not in json.dumps(result, ensure_ascii=False)


def test_table_records_are_built_from_one_grouped_result(monkeypatch):
    service = WechatMiniappSyncService(SimpleNamespace())
    source_rows = [
        {
            "item_date": date(2026, 9, 8),
            "product_code": code,
            "zx_short": 100 + index,
            "zx_long": 90 + index,
            "aggregate_short": 300 + index,
            "aggregate_long": 320 + index,
        }
        for index, code in enumerate(["IH", "IF", "IC", "IM"])
    ]
    monkeypatch.setattr(service, "_table_position_rows", lambda _start_date: source_rows)

    records = service.build_table_records()

    assert len(records) == 1
    assert [row["group"] for row in records[0]["samples"]["sample_zx"]["rows"]] == [
        "50",
        "300",
        "500",
        "1000",
    ]
    serialized = json.dumps(records[0], ensure_ascii=False)
    assert "IH" not in serialized
    assert "IF" not in serialized


def test_score_records_use_1000_global_value_and_flag_mismatch():
    db = _ExecuteDb(
        [
            {
                "item_date": date(2026, 9, 8),
                "item_code": "sh000300",
                "risk_overall_score": 31.5,
                "risk_global_shock_score": 7.0,
            },
            {
                "item_date": date(2026, 9, 8),
                "item_code": "sh000852",
                "risk_overall_score": 48.5,
                "risk_global_shock_score": 8.0,
            },
        ]
    )

    records = WechatMiniappSyncService(db).build_score_records()

    assert records[0]["values"] == {
        "score_300": 31.5,
        "score_1000": 48.5,
        "score_global": 8.0,
    }
    assert records[0]["quality"]["global_consistent"] is False


def test_notification_uses_future_event_time_stable_aliases_and_actual_basis_date(monkeypatch):
    root = SimpleNamespace(id=1)
    task = SimpleNamespace(id=11, enabled=True, config_json={"strategy_ids": [8, 3, 5]})
    run = SimpleNamespace(
        id=27,
        scheduled_for=datetime(2026, 9, 9, 21, 0),
        finished_at=datetime(2026, 9, 9, 21, 0, 12),
        summary="Sent notification email based on trade date 2026-09-08.",
    )

    class _QuantService:
        def __init__(self, _db):
            pass

        def list_strategy_notification_summaries(self, strategy_ids, owner_id, basis_trade_date):
            assert strategy_ids == [8, 3, 5]
            assert owner_id == 1
            assert basis_trade_date == date(2026, 9, 8)
            return [
                {"strategy_id": 8, "signal_text": "蓝", "strategy_name": "沪深300期现强化", "target_name": "沪深300"},
                {"strategy_id": 3, "signal_text": "无操作", "strategy_name": "北自科技测试", "target_name": "北自科技"},
                {"strategy_id": 5, "signal_text": "紫", "strategy_name": "比亚迪买入计划", "target_name": "比亚迪"},
            ]

    monkeypatch.setattr(module, "QuantService", _QuantService)
    strategy_rows = [
        SimpleNamespace(id=8, name="沪深300期现强化", strategy_type="index", target_code="sh000300", target_name="沪深300"),
        SimpleNamespace(id=3, name="北自科技测试", strategy_type="stock", target_code="603082", target_name="北自科技"),
        SimpleNamespace(id=5, name="比亚迪买入计划", strategy_type="stock", target_code="002594", target_name="比亚迪"),
    ]
    event = WechatMiniappSyncService(
        _NotificationDb([root, task, run, strategy_rows])
    ).build_notification_event()

    assert event["event_id"] == "event_11_27"
    assert event["basis_date"] == "2026-09-08"
    assert event["completed_at"] == "2026-09-09T21:00:12"
    assert event["total_count"] == 3
    assert event["effective_count"] == 2
    assert "effective_aliases" not in event
    assert [item["target"] for item in event["mail"]["items"]] == ["300", "BZKJ", "BYD"]
    assert event["mail"]["summary"] == "本次汇总共 3 个项目，其中 2 个出现有效结果。"
    serialized = json.dumps(event, ensure_ascii=False)
    assert [item["name"] for item in event["mail"]["items"]] == [
        "300联动强化",
        "BZKJ测试",
        "BYD阶段计划",
    ]
    assert "沪深300" not in serialized
    assert "北自科技" not in serialized
    assert "比亚迪" not in serialized


def test_signed_headers_match_body(monkeypatch):
    monkeypatch.setattr(module.settings, "wechat_miniapp_ingest_secret", "test-secret")
    body = '{"dataset":"series","items":[]}'

    headers = WechatMiniappSyncService(SimpleNamespace())._signed_headers(body)

    digest = hashlib.sha256(body.encode()).hexdigest()
    canonical = f"{headers['X-FIT-Timestamp']}\n{headers['X-FIT-Nonce']}\n{digest}"
    expected = hmac.new(b"test-secret", canonical.encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(headers["X-FIT-Signature"], expected)


def test_push_accepts_http_gateway_wrapped_body(monkeypatch):
    class _Response:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"body": '{"ok":true,"data":{"written":1}}'}

    class _Http:
        @staticmethod
        def post(*_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(module.settings, "wechat_miniapp_ingest_url", "https://example.test/fit-ingest")
    monkeypatch.setattr(module.settings, "wechat_miniapp_ingest_secret", "secret")
    service = WechatMiniappSyncService(SimpleNamespace(), http_session=_Http())

    result = service.push("series", [{"_id": "series_20260909", "date": "2026-09-09"}])

    assert result == {"dataset": "series", "written": 1, "batches": 1}


def test_sync_schedule_runs_only_after_source_updates():
    half_past_schedule = celery_app.conf.beat_schedule[
        "sync-wechat-miniapp-after-source-updates"
    ]["schedule"]
    evening_schedule = celery_app.conf.beat_schedule[
        "sync-wechat-miniapp-at-21-independent-of-notification"
    ]["schedule"]

    assert half_past_schedule.minute == {30}
    assert half_past_schedule.hour == {9, 10, 17, 23}
    assert celery_app.conf.beat_schedule[
        "sync-wechat-miniapp-after-source-updates"
    ]["task"] == "tasks.sync_wechat_miniapp_data"
    assert celery_app.conf.beat_schedule[
        "sync-wechat-miniapp-after-source-updates"
    ]["options"]["queue"] == "wechat-miniapp"
    assert evening_schedule.minute == {0}
    assert evening_schedule.hour == {21}
    assert celery_app.conf.beat_schedule[
        "sync-wechat-miniapp-at-21-independent-of-notification"
    ]["task"] == "tasks.sync_wechat_miniapp_data"
    assert celery_app.conf.beat_schedule[
        "sync-wechat-miniapp-at-21-independent-of-notification"
    ]["options"]["queue"] == "wechat-miniapp"


def test_daily_notification_sync_runs_only_after_successful_root_email(monkeypatch):
    monkeypatch.setattr(module.settings, "wechat_miniapp_notification_task_name", "每日通知")
    result = {"status": "success", "trigger_type": "schedule"}
    task = SimpleNamespace(task_type="notification", name="每日通知")
    root = SimpleNamespace(role="root")

    assert _should_sync_wechat_notification(result, task, root) is True
    assert _should_sync_wechat_notification({**result, "status": "failed"}, task, root) is False
    assert _should_sync_wechat_notification({**result, "trigger_type": "manual"}, task, root) is True
    assert _should_sync_wechat_notification({**result, "trigger_type": "retry"}, task, root) is False
    assert _should_sync_wechat_notification(result, task, SimpleNamespace(role="admin")) is False
    assert _should_sync_wechat_notification(
        result,
        SimpleNamespace(task_type="notification", name="其他通知"),
        root,
    ) is False
