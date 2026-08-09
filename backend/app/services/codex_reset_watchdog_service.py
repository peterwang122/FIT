import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings


REPO_ROOT = Path(__file__).resolve().parents[3]
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
WATCHDOG_HISTORY_LIMIT = 30
WATCHDOG_SOURCE_HANDLE = "thsottiaux"
SLASH_COMMAND_PATTERN = re.compile(
    r"(?<!/)/[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)*"
)
TRANSLATED_SLASH_COMMAND_PATTERN = re.compile(
    r"(?<!/)/[^\s,，。.!！？;；:：)）\]】}]+"
)


@dataclass(frozen=True)
class WatchdogItem:
    item_id: str
    text: str
    url: str | None
    author: str | None
    published_at: str | None


@dataclass(frozen=True)
class ResetFinding:
    status: str
    evidence: str


@dataclass(frozen=True)
class WatchdogNotification:
    title: str
    body: str
    action_url: str | None
    action_label: str | None
    dedupe_key: str
    payload: dict


class JsonWatchdogStateStore:
    def __init__(self, file_path: str | Path):
        candidate = Path(file_path).expanduser()
        self.path = candidate if candidate.is_absolute() else REPO_ROOT / candidate

    @staticmethod
    def _empty_state() -> dict:
        return {
            "version": 3,
            "initialized_at": None,
            "last_success_at": None,
            "seen_item_ids": {},
            "items": {},
            "consecutive_failures": 0,
            "last_failure": None,
        }

    def load(self) -> dict:
        if not self.path.exists():
            return self._empty_state()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Codex reset watchdog state must be a JSON object")
        state = self._empty_state()
        state.update(raw)
        state["version"] = 3
        if not isinstance(state.get("seen_item_ids"), dict):
            state["seen_item_ids"] = {}
        if not isinstance(state.get("items"), dict):
            state["items"] = {}
        return state

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(f".{self.path.name}.{time.time_ns()}.tmp")
        try:
            temp_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        finally:
            temp_path.unlink(missing_ok=True)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _matches_any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


QUOTA_PATTERNS = (
    r"\brate[ -]?limits?\b",
    r"\busage[ -]?(?:limits?|caps?|quota)\b",
    r"\bweekly[ -]?(?:limits?|caps?|quota|allowance)\b",
    r"\b(?:limits?|quota|allowance|credits?)\b",
    r"\b(?:5|five)[ -]?hour(?:ly)?\b",
    r"\bcapacity\b",
)
RESET_PATTERNS = (
    r"\breset(?:s|ting|ted)?\b",
    r"\brefill(?:s|ing|ed)?\b",
    r"\breplenish(?:es|ing|ed)?\b",
    r"\brestore(?:s|d|ing)?\b",
    r"\btop(?:ped|ping)?[ -]?up\b",
    r"\b(?:give|giving|gave|get|getting|got).{0,35}\b(?:allowance|quota|credits?|usage)\b.{0,20}\bback\b",
    r"\b(?:allowance|quota|credits?|usage).{0,20}\bback\b",
)
NEGATION_PATTERNS = (
    r"\bno[ ,:-]+(?:reset|refill|restore|replenish)",
    r"\bnot (?:going to )?(?:reset|refill|restore|replenish)",
    r"\b(?:won't|will not|can't|cannot|isn't|aren't) (?:be )?(?:reset|refill|restore|replenish)",
    r"\b(?:reset|refill|restore|replenish).{0,20}\bnot planned\b",
)
NON_QUOTA_PATTERNS = (
    r"\b(?:git|branch|workspace|cache|password|database|session|settings?|config)\b",
    r"\b(?:context window|token limit|reset button)\b",
)
FUTURE_PATTERNS = (
    r"\bwill (?:be )?(?:reset|refill|restore|replenish)",
    r"\bgoing to (?:reset|refill|restore|replenish)",
    r"\b(?:resetting|refilling|restoring|replenishing)\b.{0,30}\b(?:tomorrow|later|soon|tonight|this week)\b",
    r"\b(?:tomorrow|later today|tonight|soon|this week|next week|in \d+ (?:minutes?|hours?|days?))\b",
    r"\bshould be (?:back|restored|refilled|reset)\b",
)
COMPLETED_PATTERNS = (
    r"\b(?:have|has|had|just|we've|i've) (?:now )?(?:reset|refilled|restored|replenished)",
    r"\b(?:reset|refilled|restored|replenished) (?:now|today|everyone|all|the)\b",
    r"\b(?:limits?|quota|allowance|credits?|usage) (?:is|are) (?:back|restored|refilled|reset)\b",
    r"\b(?:done|completed)\b",
)


def classify_reset_finding(text: str) -> ResetFinding | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    if _matches_any(NEGATION_PATTERNS, normalized):
        return None
    if not _matches_any(QUOTA_PATTERNS, normalized):
        return None
    if not _matches_any(RESET_PATTERNS, normalized):
        return None
    if _matches_any(NON_QUOTA_PATTERNS, normalized) and not re.search(
        r"\b(?:usage|rate|weekly)[ -]?(?:limits?|quota|caps?)\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        return None
    if _matches_any(FUTURE_PATTERNS, normalized):
        return ResetFinding(status="scheduled", evidence="原文包含未来重置或恢复额度的明确表述")
    if _matches_any(COMPLETED_PATTERNS, normalized):
        return ResetFinding(status="completed", evidence="原文表明额度已经重置或恢复")
    return ResetFinding(status="possible", evidence="原文同时包含额度与重置含义，建议核对原文")


def normalize_source_item(raw: dict) -> WatchdogItem | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("external_id") or raw.get("id") or "").strip()
    text = _normalize_text(str(raw.get("content") or raw.get("title") or ""))
    if not item_id or not text:
        return None
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return WatchdogItem(
        item_id=item_id,
        text=text,
        url=str(raw.get("url") or "").strip() or None,
        author=str(metadata.get("author_user_name") or raw.get("author") or "").strip() or None,
        published_at=str(raw.get("published_at") or "").strip() or None,
    )


def extract_source_items(payload: dict) -> list[WatchdogItem]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raw_items = (payload.get("data") or {}).get("items") if isinstance(payload.get("data"), dict) else []
    return [item for raw in raw_items if (item := normalize_source_item(raw)) is not None]


def extract_translation(payload: object) -> str | None:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        return None
    chunks = [
        segment[0]
        for segment in payload[0]
        if isinstance(segment, list) and segment and isinstance(segment[0], str)
    ]
    translated = _normalize_text("".join(chunks))
    return translated or None


def extract_mymemory_translation(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    response_data = payload.get("responseData")
    if not isinstance(response_data, dict):
        return None
    translated_text = response_data.get("translatedText")
    if not isinstance(translated_text, str):
        return None
    translated = _normalize_text(html.unescape(translated_text))
    if not translated or translated.upper().startswith("MYMEMORY WARNING"):
        return None
    return translated


def restore_slash_commands(source_text: str, translated_text: str) -> str:
    """Keep Codex commands executable when a translation provider localizes them."""
    source_commands = SLASH_COMMAND_PATTERN.findall(source_text)
    if not source_commands:
        return translated_text

    command_index = 0

    def replace_command(match: re.Match[str]) -> str:
        nonlocal command_index
        if command_index >= len(source_commands):
            return match.group(0)
        restored = source_commands[command_index]
        command_index += 1
        return restored

    restored_text = TRANSLATED_SLASH_COMMAND_PATTERN.sub(replace_command, translated_text)
    return _normalize_text(restored_text)


def _parse_source_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _item_sort_key(item: WatchdogItem) -> tuple[datetime, str]:
    return (_parse_source_time(item.published_at) or datetime.min.replace(tzinfo=timezone.utc), item.item_id)


def _history_item_sort_key(item: dict) -> tuple[datetime, str]:
    published_at = item.get("published_at") if isinstance(item.get("published_at"), str) else None
    item_id = str(item.get("item_id") or "")
    return (_parse_source_time(published_at) or datetime.min.replace(tzinfo=timezone.utc), item_id)


def _format_source_time(value: str | None) -> str:
    parsed = _parse_source_time(value)
    if parsed is None:
        return "时间未知"
    return parsed.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")


def _excerpt(text: str, length: int = 220) -> str:
    return text if len(text) <= length else f"{text[:length].rstrip()}..."


class CodexResetWatchdogService:
    def __init__(
        self,
        *,
        state_store: JsonWatchdogStateStore | None = None,
        fetcher: Callable[[], list[WatchdogItem]] | None = None,
        notifier: Callable[[WatchdogNotification], bool] | None = None,
        translator: Callable[[str], str | None] | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.state_store = state_store or JsonWatchdogStateStore(settings.codex_reset_watchdog_state_file)
        self.fetcher = fetcher or self._fetch_source_items
        self.notifier = notifier or (lambda _notification: False)
        self.translator = translator
        if self.translator is None and settings.codex_reset_watchdog_translation_enabled:
            self.translator = self._translate_to_chinese
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _archive_items(self, state: dict, items: list[WatchdogItem], archived_at: str) -> None:
        archived_items = state.get("items") if isinstance(state.get("items"), dict) else {}
        for item in items:
            existing = archived_items.get(item.item_id)
            existing_archived_at = existing.get("archived_at") if isinstance(existing, dict) else None
            same_source_text = isinstance(existing, dict) and existing.get("text") == item.text
            translation_zh = existing.get("translation_zh") if same_source_text else None
            translated_at = existing.get("translated_at") if same_source_text else None
            translation_error = None
            if not translation_zh and self.translator is not None:
                try:
                    translation_zh = self.translator(item.text)
                    if translation_zh:
                        translated_at = archived_at
                    else:
                        translation_error = "翻译服务未返回有效译文"
                except Exception as exc:
                    translation_error = _excerpt(str(exc), 300)
            finding = classify_reset_finding(item.text)
            archived_items[item.item_id] = {
                "item_id": item.item_id,
                "text": item.text,
                "url": item.url,
                "author": item.author,
                "published_at": item.published_at,
                "translation_zh": translation_zh,
                "translated_at": translated_at,
                "translation_error": translation_error,
                "reset_status": finding.status if finding else None,
                "reset_evidence": finding.evidence if finding else None,
                "archived_at": existing_archived_at or archived_at,
            }

        newest_items = sorted(archived_items.values(), key=_history_item_sort_key)[-WATCHDOG_HISTORY_LIMIT:]
        state["items"] = {str(item["item_id"]): item for item in newest_items}

    def _translate_with_google(self, text: str) -> str:
        attempts = max(int(settings.codex_reset_watchdog_translation_retry_attempts), 1)
        timeout = max(int(settings.codex_reset_watchdog_translation_timeout_seconds), 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                    response = client.get(
                        settings.codex_reset_watchdog_translation_url,
                        params={
                            "client": "gtx",
                            "sl": "auto",
                            "tl": "zh-CN",
                            "dt": "t",
                            "q": text,
                        },
                    )
                    response.raise_for_status()
                    translated = extract_translation(response.json())
                if not translated:
                    raise ValueError("translation response has no usable text")
                return translated
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(min(attempt, 2))
        raise RuntimeError(f"Google translation failed after {attempts} attempts: {last_error}")

    def _translate_with_mymemory(self, text: str) -> str:
        attempts = max(int(settings.codex_reset_watchdog_translation_retry_attempts), 1)
        timeout = max(int(settings.codex_reset_watchdog_translation_timeout_seconds), 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                    response = client.get(
                        settings.codex_reset_watchdog_translation_fallback_url,
                        params={
                            "q": text,
                            "langpair": "en|zh-CN",
                        },
                    )
                    response.raise_for_status()
                    translated = extract_mymemory_translation(response.json())
                if not translated:
                    raise ValueError("MyMemory response has no usable translation")
                return translated
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(min(attempt, 2))
        raise RuntimeError(f"MyMemory translation failed after {attempts} attempts: {last_error}")

    def _translate_to_chinese(self, text: str) -> str | None:
        provider_errors: list[str] = []
        for provider_name, translator in (
            ("Google", self._translate_with_google),
            ("MyMemory", self._translate_with_mymemory),
        ):
            try:
                translated = translator(text)
                return restore_slash_commands(text, translated)
            except Exception as exc:  # noqa: BLE001
                provider_errors.append(f"{provider_name}: {exc}")
        raise RuntimeError("all translation providers failed; " + "; ".join(provider_errors))

    def list_history(self, limit: int = WATCHDOG_HISTORY_LIMIT) -> dict:
        state = self.state_store.load()
        archived_items = state.get("items") if isinstance(state.get("items"), dict) else {}
        requested_limit = min(max(int(limit), 1), WATCHDOG_HISTORY_LIMIT)
        items = sorted(archived_items.values(), key=_history_item_sort_key, reverse=True)
        return {
            "source_handle": WATCHDOG_SOURCE_HANDLE,
            "max_items": WATCHDOG_HISTORY_LIMIT,
            "archived_count": len(archived_items),
            "last_success_at": state.get("last_success_at"),
            "items": items[:requested_limit],
        }

    def _fetch_source_items(self) -> list[WatchdogItem]:
        attempts = max(int(settings.codex_reset_watchdog_retry_attempts), 1)
        timeout = max(int(settings.codex_reset_watchdog_request_timeout_seconds), 1)
        backoff = max(int(settings.codex_reset_watchdog_retry_backoff_seconds), 0)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
                    response = client.get(settings.codex_reset_watchdog_source_url)
                    response.raise_for_status()
                    payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Dayclaw response is not a JSON object")
                items = extract_source_items(payload)
                if not items:
                    raise ValueError("Dayclaw returned no usable source items")
                return items
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < attempts and backoff:
                    time.sleep(min(backoff * (2 ** (attempt - 1)), 30))

        raise RuntimeError(f"Dayclaw source request failed after {attempts} attempts: {last_error}")

    def _build_signal_notification(
        self,
        item: WatchdogItem,
        finding: ResetFinding,
    ) -> WatchdogNotification:
        title_by_status = {
            "scheduled": "Codex 额度重置预告",
            "completed": "Codex 额度已重置",
            "possible": "Codex 额度重置信号待核对",
        }
        source_time = _format_source_time(item.published_at)
        return WatchdogNotification(
            title=title_by_status[finding.status],
            body=f"Tibo 于 {source_time} 发布：\u201c{_excerpt(item.text)}\u201d",
            action_url=item.url,
            action_label="查看原文",
            dedupe_key=f"codex-reset-watchdog:item:{item.item_id}",
            payload={
                "item_id": item.item_id,
                "author": item.author,
                "published_at": item.published_at,
                "finding_status": finding.status,
                "evidence": finding.evidence,
                "source_text": item.text,
                "source_url": item.url,
            },
        )

    def _build_failure_notification(self, failure_count: int, detail: str) -> WatchdogNotification:
        return WatchdogNotification(
            title="Codex 额度监控连续失败",
            body=f"已连续 {failure_count} 次无法读取 Tibo 的公开动态。监控会自动继续重试；原因：{_excerpt(detail, 160)}",
            action_url="https://github.com/thinkingjimmy/codex-reset-watchdog",
            action_label="查看监控说明",
            dedupe_key=f"codex-reset-watchdog:error:{failure_count}",
            payload={
                "consecutive_failures": failure_count,
                "error": detail,
                "source_url": settings.codex_reset_watchdog_source_url,
            },
        )

    def _should_notify_failure(self, failure_count: int) -> bool:
        threshold = max(int(settings.codex_reset_watchdog_failure_notification_threshold), 1)
        interval = max(int(settings.codex_reset_watchdog_failure_notification_interval), 1)
        if failure_count < threshold:
            return False
        return failure_count == threshold or (failure_count - threshold) % interval == 0

    def _record_failure(self, error: Exception) -> dict:
        state = self.state_store.load()
        failure_count = int(state.get("consecutive_failures") or 0) + 1
        detail = _excerpt(str(error), 500)
        state["consecutive_failures"] = failure_count
        state["last_failure"] = {
            "at": self.now().isoformat(),
            "detail": detail,
        }
        self.state_store.save(state)
        notified = False
        if self._should_notify_failure(failure_count):
            notified = self.notifier(self._build_failure_notification(failure_count, detail))
        return {
            "status": "source_error",
            "consecutive_failures": failure_count,
            "notification_created": bool(notified),
            "error": detail,
        }

    def check(self) -> dict:
        try:
            items = sorted(self.fetcher(), key=_item_sort_key)
        except Exception as exc:
            return self._record_failure(exc)

        state = self.state_store.load()
        now_iso = self.now().isoformat()
        seen_item_ids = state.get("seen_item_ids") or {}
        self._archive_items(state, items, now_iso)
        if not state.get("initialized_at"):
            state["initialized_at"] = now_iso
            state["last_success_at"] = now_iso
            state["consecutive_failures"] = 0
            state["last_failure"] = None
            state["seen_item_ids"] = {item.item_id: now_iso for item in items}
            self.state_store.save(state)
            return {
                "status": "primed",
                "fetched": len(items),
                "new_items": 0,
                "findings": 0,
                "notifications_created": 0,
            }

        new_items = [item for item in items if item.item_id not in seen_item_ids]
        findings = 0
        notifications_created = 0
        for item in new_items:
            finding = classify_reset_finding(item.text)
            if finding is None:
                continue
            findings += 1
            if self.notifier(self._build_signal_notification(item, finding)):
                notifications_created += 1

        for item in items:
            seen_item_ids.setdefault(item.item_id, now_iso)
        if len(seen_item_ids) > 500:
            seen_item_ids = dict(sorted(seen_item_ids.items(), key=lambda pair: pair[1])[-500:])
        state["seen_item_ids"] = seen_item_ids
        state["last_success_at"] = now_iso
        state["consecutive_failures"] = 0
        state["last_failure"] = None
        self.state_store.save(state)
        return {
            "status": "ok",
            "fetched": len(items),
            "new_items": len(new_items),
            "findings": findings,
            "notifications_created": notifications_created,
        }
