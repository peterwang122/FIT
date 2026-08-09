from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.routes_notifications import get_codex_reset_watchdog_history
from app.services.codex_reset_watchdog_service import (
    CodexResetWatchdogService,
    JsonWatchdogStateStore,
    WatchdogItem,
    classify_reset_finding,
    extract_mymemory_translation,
    extract_source_items,
    extract_translation,
    restore_slash_commands,
)
from app.models.user import User
from app.models.user_notification import UserNotification
from app.services.notification_service import NotificationService


@pytest.fixture(autouse=True)
def disable_live_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.codex_reset_watchdog_service.settings.codex_reset_watchdog_translation_enabled",
        False,
    )


def _item(item_id: str, text: str, published_at: str) -> WatchdogItem:
    return WatchdogItem(
        item_id=item_id,
        text=text,
        url=f"https://x.com/thsottiaux/status/{item_id}",
        author="thsottiaux",
        published_at=published_at,
    )


class _NotificationQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def first(self):
        if self.model is User:
            return self.session.root_user
        if self.model is UserNotification:
            return self.session.notifications[0] if self.session.notifications else None
        return None


class _NotificationSession:
    def __init__(self, root_user: User | None):
        self.root_user = root_user
        self.notifications = []

    def query(self, model):
        return _NotificationQuery(self, model)

    def add(self, item):
        if isinstance(item, UserNotification) and item not in self.notifications:
            item.id = len(self.notifications) + 1
            self.notifications.append(item)

    def commit(self):
        return None

    def refresh(self, _item):
        return None


def test_classifies_scheduled_and_completed_quota_resets():
    scheduled = classify_reset_finding("We will reset Codex weekly usage limits tomorrow morning.")
    completed = classify_reset_finding("We have just reset the Codex usage limits for all paid users.")

    assert scheduled is not None
    assert scheduled.status == "scheduled"
    assert completed is not None
    assert completed.status == "completed"


def test_ignores_negated_and_non_quota_resets():
    assert classify_reset_finding("No reset is planned for Codex weekly usage limits.") is None
    assert classify_reset_finding("Reset your local Codex workspace and git branch.") is None
    assert classify_reset_finding("Codex is faster today.") is None


def test_extracts_dayclaw_public_items():
    items = extract_source_items(
        {
            "items": [
                {
                    "id": "internal-id",
                    "external_id": "123456",
                    "content": "  Codex limits will reset tomorrow.  ",
                    "url": "https://x.com/thsottiaux/status/123456",
                    "author": "thsottiaux",
                    "published_at": "2026-08-03T08:00:00",
                    "metadata": {"author_user_name": "thsottiaux"},
                }
            ]
        }
    )

    assert len(items) == 1
    assert items[0].item_id == "123456"
    assert items[0].text == "Codex limits will reset tomorrow."


def test_extracts_google_translation_segments():
    payload = [[
        ["我已重置 Codex 的使用限制。", "I reset Codex usage limits.", None, None],
        ["请尽情使用。", "Enjoy.", None, None],
    ]]

    assert extract_translation(payload) == "我已重置 Codex 的使用限制。请尽情使用。"


def test_extracts_mymemory_translation_and_decodes_entities():
    payload = {
        "responseStatus": 200,
        "responseData": {"translatedText": "Codex &amp; GPT 都已更新。"},
    }

    assert extract_mymemory_translation(payload) == "Codex & GPT 都已更新。"


def test_restores_codex_slash_commands_after_translation():
    source = "Explore /goal in Codex, then use /fast."
    translated = "在 Codex 中探索/目标，然后使用/快速。"

    assert restore_slash_commands(source, translated) == "在 Codex 中探索/goal，然后使用/fast。"


def test_translation_falls_back_when_google_is_rate_limited(tmp_path, monkeypatch):
    service = CodexResetWatchdogService(
        state_store=JsonWatchdogStateStore(tmp_path / "state.json"),
        fetcher=lambda: [],
    )

    def fail_google(_text: str) -> str:
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(service, "_translate_with_google", fail_google)
    monkeypatch.setattr(service, "_translate_with_mymemory", lambda _text: "请在 Codex 中使用/目标。")

    assert service._translate_to_chinese("Use /goal in Codex.") == "请在 Codex 中使用/goal。"


def test_archives_translation_once_and_reuses_it(tmp_path):
    state_store = JsonWatchdogStateStore(tmp_path / "state.json")
    source_item = _item("100", "Codex is faster today.", "2026-08-03T08:00:00")
    translated_texts = []

    def translate(text: str) -> str:
        translated_texts.append(text)
        return "Codex 今天更快了。"

    service = CodexResetWatchdogService(
        state_store=state_store,
        fetcher=lambda: [source_item],
        translator=translate,
        now=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    service.check()
    service.check()
    history = service.list_history()

    assert translated_texts == [source_item.text]
    assert history["items"][0]["translation_zh"] == "Codex 今天更快了。"


def test_first_run_primes_then_only_notifies_for_new_actionable_items(tmp_path):
    state_store = JsonWatchdogStateStore(tmp_path / "state.json")
    old_item = _item("100", "A normal Codex product update.", "2026-08-01T08:00:00")
    reset_item = _item(
        "101",
        "We will reset Codex weekly usage limits tomorrow morning.",
        "2026-08-02T08:00:00",
    )
    batches = iter([[old_item], [old_item, reset_item], [old_item, reset_item]])
    notifications = []
    service = CodexResetWatchdogService(
        state_store=state_store,
        fetcher=lambda: next(batches),
        notifier=lambda item: notifications.append(item) is None,
        now=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    first = service.check()
    second = service.check()
    third = service.check()

    assert first["status"] == "primed"
    assert second == {
        "status": "ok",
        "fetched": 2,
        "new_items": 1,
        "findings": 1,
        "notifications_created": 1,
    }
    assert third["new_items"] == 0
    assert len(notifications) == 1
    assert notifications[0].dedupe_key == "codex-reset-watchdog:item:101"
    history = service.list_history()
    assert history["archived_count"] == 2
    assert [item["item_id"] for item in history["items"]] == ["101", "100"]
    assert history["items"][0]["reset_status"] == "scheduled"


def test_history_keeps_latest_thirty_items(tmp_path):
    state_store = JsonWatchdogStateStore(tmp_path / "state.json")
    base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
    items = [
        _item(
            str(index),
            f"Codex public update {index}",
            (base_time + timedelta(hours=index)).isoformat(),
        )
        for index in range(35)
    ]
    service = CodexResetWatchdogService(
        state_store=state_store,
        fetcher=lambda: items,
        now=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
    )

    assert service.check()["status"] == "primed"
    history = service.list_history()

    assert history["max_items"] == 30
    assert history["archived_count"] == 30
    assert history["items"][0]["item_id"] == "34"
    assert history["items"][-1]["item_id"] == "5"


def test_codex_history_route_is_root_only(monkeypatch):
    history = {
        "source_handle": "thsottiaux",
        "max_items": 30,
        "archived_count": 1,
        "last_success_at": "2026-08-03T10:00:00+00:00",
        "items": [
            {
                "item_id": "123",
                "text": "Codex update",
                "url": "https://x.com/thsottiaux/status/123",
                "author": "thsottiaux",
                "published_at": "2026-08-03T09:00:00+00:00",
                "translation_zh": "Codex 动态",
                "reset_status": None,
                "reset_evidence": None,
                "archived_at": "2026-08-03T10:00:00+00:00",
            }
        ],
    }
    monkeypatch.setattr(
        "app.api.routes_notifications.CodexResetWatchdogService",
        lambda: type("HistoryService", (), {"list_history": lambda self: history})(),
    )
    root_user = User(id=7, username="root", role="root", nickname="root")
    regular_user = User(id=8, username="user", role="user", nickname="user")

    response = get_codex_reset_watchdog_history(current_user=root_user)
    assert response.data.archived_count == 1
    assert response.data.items[0].item_id == "123"
    with pytest.raises(HTTPException) as exc_info:
        get_codex_reset_watchdog_history(current_user=regular_user)
    assert exc_info.value.status_code == 403


def test_source_failure_notifies_only_at_configured_threshold(tmp_path, monkeypatch):
    state_store = JsonWatchdogStateStore(tmp_path / "state.json")
    notifications = []
    monkeypatch.setattr(
        "app.services.codex_reset_watchdog_service.settings.codex_reset_watchdog_failure_notification_threshold",
        3,
    )
    monkeypatch.setattr(
        "app.services.codex_reset_watchdog_service.settings.codex_reset_watchdog_failure_notification_interval",
        24,
    )
    service = CodexResetWatchdogService(
        state_store=state_store,
        fetcher=lambda: (_ for _ in ()).throw(RuntimeError("source timeout")),
        notifier=lambda item: notifications.append(item) is None,
    )

    assert service.check()["notification_created"] is False
    assert service.check()["notification_created"] is False
    third = service.check()

    assert third["consecutive_failures"] == 3
    assert third["notification_created"] is True
    assert len(notifications) == 1
    assert notifications[0].dedupe_key == "codex-reset-watchdog:error:3"


def test_root_notification_is_created_once_for_root_only():
    root_user = User(id=7, username="root", role="root", nickname="root")
    db = _NotificationSession(root_user)
    service = NotificationService(db)

    first = service.create_root_notification_once(
        category="codex_reset_watchdog",
        title="Codex 额度已重置",
        body="source text",
        action_url="https://x.com/thsottiaux/status/123",
        action_label="查看原文",
        dedupe_key="codex-reset-watchdog:item:123",
        payload_json={"item_id": "123"},
    )
    second = service.create_root_notification_once(
        category="codex_reset_watchdog",
        title="Codex 额度已重置",
        body="source text",
        action_url="https://x.com/thsottiaux/status/123",
        action_label="查看原文",
        dedupe_key="codex-reset-watchdog:item:123",
        payload_json={"item_id": "123"},
    )

    assert first is True
    assert second is False
    assert len(db.notifications) == 1
    assert db.notifications[0].recipient_user_id == 7
    assert db.notifications[0].dedupe_key == "codex-reset-watchdog:item:123"
