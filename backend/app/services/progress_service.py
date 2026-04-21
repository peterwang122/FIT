from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.progress_board import ProgressBoard
from app.models.user import User

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
REPO_ORDER = ["FIT", "AkShare Project"]
REPO_FULL_NAMES = {
    "FIT": "peterwang122/FIT",
    "AkShare Project": "peterwang122/akshareProkect",
}


def _default_progress_board() -> dict[str, Any]:
    return {
        "todo_items": [
            {"id": "todo-progress-1", "text": "继续完善双仓库开发日志生成规则，确保每条更新都能准确映射到实际改动。"},
            {"id": "todo-progress-2", "text": "补齐开发进度模块的接口与页面测试，覆盖重置、发布和权限校验。"},
            {"id": "todo-progress-3", "text": "继续优化开发日志的中文表达，让复杂改动也能被整理成面向用户的清晰说明。"},
        ],
        "published_progress_days": [],
        "draft_progress_days": [],
        "published_generation_meta": None,
        "draft_generation_meta": None,
    }


def _read_attr(raw_item: object, field: str, default: Any = None) -> Any:
    if isinstance(raw_item, dict):
        return raw_item.get(field, default)
    return getattr(raw_item, field, default)


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_optional_string(value: Any) -> str | None:
    normalized = _normalize_string(value)
    return normalized or None


def _sort_repo_key(repo_label: str) -> tuple[int, str]:
    order = REPO_ORDER.index(repo_label) if repo_label in REPO_ORDER else len(REPO_ORDER)
    return (order, repo_label)


def _normalize_todo_items(todo_items: list[object]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for raw_item in todo_items:
        item_id = _normalize_string(_read_attr(raw_item, "id"))
        text = _normalize_string(_read_attr(raw_item, "text"))
        if not text:
            continue
        normalized.append({"id": item_id or f"todo-{len(normalized) + 1}", "text": text})
    return normalized


def _normalize_update_logs(updates: list[object]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for raw_update in updates:
        update_id = _normalize_string(_read_attr(raw_update, "id"))
        title = _normalize_string(_read_attr(raw_update, "title"))
        description = _normalize_string(_read_attr(raw_update, "description"))
        legacy_text = _normalize_string(_read_attr(raw_update, "text"))
        if not description and legacy_text:
            description = legacy_text
        if not title:
            title = "更新内容"
        if not description:
            continue
        normalized.append(
            {
                "id": update_id or f"update-{len(normalized) + 1}",
                "title": title,
                "description": description,
            }
        )
    return normalized


def _normalize_repo_logs(repos: list[object]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_repo in repos:
        repo_id = _normalize_string(_read_attr(raw_repo, "id"))
        repo_label = _normalize_string(_read_attr(raw_repo, "repo_label"))
        repo_full_name = _normalize_string(_read_attr(raw_repo, "repo_full_name"))
        updates = _normalize_update_logs(list(_read_attr(raw_repo, "updates", []) or []))
        if not repo_label or not repo_full_name or not updates:
            continue
        normalized.append(
            {
                "id": repo_id or f"repo-{repo_label.lower().replace(' ', '-')}",
                "repo_label": repo_label,
                "repo_full_name": repo_full_name,
                "updates": updates,
            }
        )
    return sorted(normalized, key=lambda repo: _sort_repo_key(repo["repo_label"]))


def _legacy_sections_to_repos(sections: list[object]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw_section in sections:
        section_title = _normalize_string(_read_attr(raw_section, "title")) or "更新内容"
        raw_items = list(_read_attr(raw_section, "items", []) or [])
        for raw_item in raw_items:
            description = _normalize_string(_read_attr(raw_item, "text"))
            if not description:
                continue
            repo_label = _normalize_string(_read_attr(raw_item, "source_repo")) or "FIT"
            repo_full_name = REPO_FULL_NAMES.get(repo_label, repo_label)
            entry = grouped.setdefault(
                repo_label,
                {
                    "id": f"repo-{repo_label.lower().replace(' ', '-')}",
                    "repo_label": repo_label,
                    "repo_full_name": repo_full_name,
                    "updates": [],
                },
            )
            entry["updates"].append(
                {
                    "id": _normalize_string(_read_attr(raw_item, "id")) or f"update-{len(entry['updates']) + 1}",
                    "title": section_title,
                    "description": description,
                }
            )
    return sorted(grouped.values(), key=lambda repo: _sort_repo_key(repo["repo_label"]))


def _legacy_items_to_repos(items: list[object]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw_item in items:
        description = _normalize_string(_read_attr(raw_item, "text"))
        if not description:
            continue
        repo_label = _normalize_string(_read_attr(raw_item, "source_repo")) or "FIT"
        repo_full_name = REPO_FULL_NAMES.get(repo_label, repo_label)
        entry = grouped.setdefault(
            repo_label,
            {
                "id": f"repo-{repo_label.lower().replace(' ', '-')}",
                "repo_label": repo_label,
                "repo_full_name": repo_full_name,
                "updates": [],
            },
        )
        entry["updates"].append(
            {
                "id": _normalize_string(_read_attr(raw_item, "id")) or f"update-{len(entry['updates']) + 1}",
                "title": _normalize_string(_read_attr(raw_item, "title")) or "更新内容",
                "description": description,
            }
        )
    return sorted(grouped.values(), key=lambda repo: _sort_repo_key(repo["repo_label"]))


def _normalize_progress_days(progress_days: list[object]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_day in progress_days:
        day_id = _normalize_string(_read_attr(raw_day, "id"))
        date_text = _normalize_string(_read_attr(raw_day, "date"))
        title = _normalize_string(_read_attr(raw_day, "title"))
        repos = _normalize_repo_logs(list(_read_attr(raw_day, "repos", []) or []))
        if not repos:
            repos = _legacy_sections_to_repos(list(_read_attr(raw_day, "sections", []) or []))
        if not repos:
            repos = _legacy_items_to_repos(list(_read_attr(raw_day, "items", []) or []))
        if not date_text or not repos:
            continue
        normalized.append(
            {
                "id": day_id or f"day-{date_text}",
                "date": date_text,
                "title": title or f"{date_text} 更新",
                "repos": repos,
            }
        )
    return sorted(normalized, key=lambda item: (item["date"], item["title"]), reverse=True)


def _normalize_generated_at(raw_value: Any) -> str:
    if isinstance(raw_value, datetime):
        return raw_value.isoformat()
    normalized = _normalize_string(raw_value)
    if normalized:
        return normalized
    return datetime.now(SHANGHAI_TZ).isoformat()


def _normalize_generation_repos(raw_repos: list[object]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_repo in raw_repos:
        repo_label = _normalize_string(_read_attr(raw_repo, "repo_label"))
        repo_full_name = _normalize_string(_read_attr(raw_repo, "repo_full_name"))
        head_ref = _normalize_string(_read_attr(raw_repo, "head_ref"))
        if not repo_label or not repo_full_name or not head_ref:
            continue
        commit_count_raw = _read_attr(raw_repo, "commit_count", 0)
        try:
            commit_count = max(int(commit_count_raw), 0)
        except (TypeError, ValueError):
            commit_count = 0
        normalized.append(
            {
                "repo_label": repo_label,
                "repo_full_name": repo_full_name,
                "base_ref": _normalize_optional_string(_read_attr(raw_repo, "base_ref")),
                "head_ref": head_ref,
                "commit_count": commit_count,
            }
        )
    return sorted(normalized, key=lambda repo: _sort_repo_key(repo["repo_label"]))


def _normalize_generation_meta(raw_meta: object | None) -> dict[str, Any] | None:
    if raw_meta is None:
        return None
    repos = _normalize_generation_repos(list(_read_attr(raw_meta, "repos", []) or []))
    if not repos:
        return None
    return {
        "generator": _normalize_string(_read_attr(raw_meta, "generator")) or "codex",
        "scope": _normalize_string(_read_attr(raw_meta, "scope")) or "committed",
        "grouping": _normalize_string(_read_attr(raw_meta, "grouping")) or "repo_updates",
        "granularity": _normalize_string(_read_attr(raw_meta, "granularity")) or "summarized_from_pr_and_commit",
        "generated_at": _normalize_generated_at(_read_attr(raw_meta, "generated_at")),
        "repos": repos,
    }


class ProgressService:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_display_name(self, user: User | None) -> str | None:
        if user is None:
            return None
        return (user.nickname or "").strip() or user.username

    def _ensure_board_shape(self, item: ProgressBoard) -> bool:
        changed = False

        normalized_todo = _normalize_todo_items(item.todo_items or [])
        if item.todo_items != normalized_todo:
            item.todo_items = normalized_todo
            changed = True

        published_days = _normalize_progress_days(item.published_progress_days or [])
        draft_days = _normalize_progress_days(item.draft_progress_days or [])
        legacy_days = _normalize_progress_days(item.progress_days or [])

        if not published_days and legacy_days:
            published_days = legacy_days
            changed = True

        if item.published_progress_days != published_days:
            item.published_progress_days = published_days
            changed = True
        if item.draft_progress_days != draft_days:
            item.draft_progress_days = draft_days
            changed = True

        published_meta = _normalize_generation_meta(item.published_generation_meta)
        draft_meta = _normalize_generation_meta(item.draft_generation_meta)
        if item.published_generation_meta != published_meta:
            item.published_generation_meta = published_meta
            changed = True
        if item.draft_generation_meta != draft_meta:
            item.draft_generation_meta = draft_meta
            changed = True

        return changed

    def _get_board_row(self) -> ProgressBoard:
        item = self.db.query(ProgressBoard).order_by(ProgressBoard.id.asc()).first()
        if item is None:
            defaults = _default_progress_board()
            item = ProgressBoard(
                todo_items=defaults["todo_items"],
                progress_days=[],
                published_progress_days=defaults["published_progress_days"],
                draft_progress_days=defaults["draft_progress_days"],
                published_generation_meta=defaults["published_generation_meta"],
                draft_generation_meta=defaults["draft_generation_meta"],
                updated_by_user_id=None,
                last_sync_status="never",
            )
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
            return item

        if self._ensure_board_shape(item):
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
        return item

    def serialize_board(self, item: ProgressBoard, viewer: User | None = None) -> dict[str, Any]:
        updated_by = self.db.get(User, item.updated_by_user_id) if item.updated_by_user_id else None
        last_synced_by = self.db.get(User, item.last_synced_by_user_id) if item.last_synced_by_user_id else None
        last_published_by = self.db.get(User, item.last_published_by_user_id) if item.last_published_by_user_id else None
        return {
            "todo_items": item.todo_items or [],
            "published_progress_days": item.published_progress_days or [],
            "published_generation_meta": item.published_generation_meta,
            "updated_at": item.updated_at,
            "updated_by_user_id": item.updated_by_user_id,
            "updated_by_name": self._resolve_display_name(updated_by),
            "last_synced_at": item.last_synced_at,
            "last_synced_by_user_id": item.last_synced_by_user_id,
            "last_synced_by_name": self._resolve_display_name(last_synced_by),
            "last_sync_status": item.last_sync_status or "never",
            "last_sync_error": item.last_sync_error,
            "last_published_at": item.last_published_at,
            "last_published_by_user_id": item.last_published_by_user_id,
            "last_published_by_name": self._resolve_display_name(last_published_by),
            "draft_progress_days": item.draft_progress_days or [] if viewer and viewer.role == "root" else None,
            "draft_generation_meta": item.draft_generation_meta if viewer and viewer.role == "root" else None,
        }

    def get_board(self, viewer: User | None = None) -> dict[str, Any]:
        return self.serialize_board(self._get_board_row(), viewer)

    def update_todo_items(self, todo_items: list[object], current_user: User) -> dict[str, Any]:
        item = self._get_board_row()
        item.todo_items = _normalize_todo_items(todo_items)
        item.updated_by_user_id = current_user.id
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self.serialize_board(item, current_user)

    def update_draft_progress(
        self,
        draft_progress_days: list[object],
        generation_meta: object | None,
        current_user: User,
    ) -> dict[str, Any]:
        item = self._get_board_row()
        item.draft_progress_days = _normalize_progress_days(draft_progress_days)
        item.draft_generation_meta = _normalize_generation_meta(generation_meta)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self.serialize_board(item, current_user)

    def publish_draft(self, current_user: User) -> dict[str, Any]:
        item = self._get_board_row()
        item.published_progress_days = deepcopy(_normalize_progress_days(item.draft_progress_days or []))
        item.published_generation_meta = deepcopy(_normalize_generation_meta(item.draft_generation_meta))
        item.last_published_at = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
        item.last_published_by_user_id = current_user.id
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self.serialize_board(item, current_user)

    def reset_board(self, current_user: User) -> dict[str, Any]:
        item = self._get_board_row()
        item.progress_days = []
        item.published_progress_days = []
        item.draft_progress_days = []
        item.published_generation_meta = None
        item.draft_generation_meta = None
        item.last_published_at = None
        item.last_published_by_user_id = None
        item.last_synced_at = None
        item.last_synced_by_user_id = None
        item.last_sync_status = "never"
        item.last_sync_error = None
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self.serialize_board(item, current_user)
