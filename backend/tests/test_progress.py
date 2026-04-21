from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.api.deps.auth import get_current_user, get_current_user_optional
from app.db.session import get_db
from app.main import app
from app.models.progress_board import ProgressBoard
from app.models.user import User
from app.services.progress_service import ProgressService


def _make_user(user_id: int, username: str, role: str) -> User:
    return User(id=user_id, username=username, role=role, nickname=username)


class _FakeQuery:
    def __init__(self, db):
        self.db = db

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.db.board


class _FakeSession:
    def __init__(self, board: ProgressBoard | None = None, users: list[User] | None = None):
        self.board = board
        self.users = {user.id: user for user in users or []}

    def query(self, model):
        assert model is ProgressBoard
        return _FakeQuery(self)

    def get(self, model, identity):
        if model is User:
            return self.users.get(identity)
        return None

    def add(self, instance):
        if isinstance(instance, ProgressBoard):
            if getattr(instance, "id", None) is None:
                instance.id = 1
            self.board = instance
        elif isinstance(instance, User):
            self.users[instance.id] = instance

    def commit(self):
        return None

    def refresh(self, instance):
        if isinstance(instance, ProgressBoard) and getattr(instance, "id", None) is None:
            instance.id = 1


@contextmanager
def _test_client_for(user: User):
    original_startup = list(app.router.on_startup)
    app.router.on_startup.clear()
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.router.on_startup[:] = original_startup
        app.dependency_overrides.clear()


def test_update_draft_progress_stores_generation_meta_and_repo_updates():
    root_user = _make_user(1, "root", "root")
    service = ProgressService(_FakeSession(users=[root_user]))

    board = service.update_draft_progress(
        draft_progress_days=[
            {
                "id": "day-1",
                "date": "2026-04-14",
                "title": "",
                "repos": [
                    {
                        "id": "repo-2",
                        "repo_label": "AkShare Project",
                        "repo_full_name": "peterwang122/akshareProkect",
                        "updates": [
                            {
                                "id": "update-2",
                                "title": "同步调度结果展示",
                                "description": "补上任务执行结果摘要，方便直接核对调度输出。",
                            }
                        ],
                    },
                    {
                        "id": "repo-1",
                        "repo_label": "FIT",
                        "repo_full_name": "peterwang122/FIT",
                        "updates": [
                            {
                                "id": "update-1",
                                "title": "重构开发进度页",
                                "description": "把开发日志页面改成按日期和仓库展示中文详细更新说明。",
                            }
                        ],
                    },
                ],
            }
        ],
        generation_meta={
            "generator": "codex",
            "scope": "committed",
            "grouping": "repo_updates",
            "granularity": "summarized_from_pr_and_commit",
            "generated_at": "2026-04-14T20:30:00+08:00",
            "repos": [
                {
                    "repo_label": "AkShare Project",
                    "repo_full_name": "peterwang122/akshareProkect",
                    "base_ref": None,
                    "head_ref": "abcdef1234567890",
                    "commit_count": 4,
                },
                {
                    "repo_label": "FIT",
                    "repo_full_name": "peterwang122/FIT",
                    "base_ref": "1234567890abcdef",
                    "head_ref": "fedcba0987654321",
                    "commit_count": 7,
                },
            ],
        },
        current_user=root_user,
    )

    assert [repo["repo_label"] for repo in board["draft_progress_days"][0]["repos"]] == ["FIT", "AkShare Project"]
    assert board["draft_progress_days"][0]["title"] == "2026-04-14 更新"
    assert board["draft_progress_days"][0]["repos"][0]["updates"][0]["title"] == "重构开发进度页"
    assert board["draft_generation_meta"]["repos"][0]["repo_label"] == "FIT"
    assert board["draft_generation_meta"]["repos"][1]["repo_label"] == "AkShare Project"


def test_publish_draft_copies_generation_meta_and_hides_draft_for_non_root():
    root_user = _make_user(1, "root", "root")
    normal_user = _make_user(2, "alice", "user")
    db = _FakeSession(
        board=ProgressBoard(
            id=1,
            todo_items=[],
            progress_days=[],
            draft_progress_days=[
                {
                    "id": "day-1",
                    "date": "2026-04-14",
                    "title": "2026-04-14 更新",
                    "repos": [
                        {
                            "id": "repo-1",
                            "repo_label": "FIT",
                            "repo_full_name": "peterwang122/FIT",
                            "updates": [
                                {
                                    "id": "update-1",
                                    "title": "补齐发布流程",
                                    "description": "发布时同步复制草稿内容和生成范围基线。",
                                }
                            ],
                        }
                    ],
                }
            ],
            published_progress_days=[],
            draft_generation_meta={
                "generator": "codex",
                "scope": "committed",
                "grouping": "repo_updates",
                "granularity": "summarized_from_pr_and_commit",
                "generated_at": "2026-04-14T20:30:00+08:00",
                "repos": [
                    {
                        "repo_label": "FIT",
                        "repo_full_name": "peterwang122/FIT",
                        "base_ref": None,
                        "head_ref": "fedcba0987654321",
                        "commit_count": 3,
                    }
                ],
            },
            published_generation_meta=None,
        ),
        users=[root_user, normal_user],
    )
    service = ProgressService(db)

    published = service.publish_draft(root_user)
    public_view = service.get_board(normal_user)

    assert published["published_progress_days"][0]["repos"][0]["updates"][0]["title"] == "补齐发布流程"
    assert published["published_generation_meta"]["repos"][0]["head_ref"] == "fedcba0987654321"
    assert public_view["published_generation_meta"]["repos"][0]["repo_label"] == "FIT"
    assert public_view["draft_progress_days"] is None
    assert public_view["draft_generation_meta"] is None


def test_reset_board_clears_published_and_draft():
    root_user = _make_user(1, "root", "root")
    db = _FakeSession(
        board=ProgressBoard(
            id=1,
            todo_items=[],
            progress_days=[{"id": "legacy-day", "date": "2026-04-10", "title": "旧数据", "repos": []}],
            draft_progress_days=[
                {
                    "id": "day-1",
                    "date": "2026-04-14",
                    "title": "2026-04-14 更新",
                    "repos": [
                        {
                            "id": "repo-1",
                            "repo_label": "FIT",
                            "repo_full_name": "peterwang122/FIT",
                            "updates": [{"id": "update-1", "title": "草稿", "description": "待发布"}],
                        }
                    ],
                }
            ],
            published_progress_days=[
                {
                    "id": "day-0",
                    "date": "2026-04-13",
                    "title": "2026-04-13 更新",
                    "repos": [
                        {
                            "id": "repo-1",
                            "repo_label": "FIT",
                            "repo_full_name": "peterwang122/FIT",
                            "updates": [{"id": "update-0", "title": "已发布", "description": "旧日志"}],
                        }
                    ],
                }
            ],
            draft_generation_meta={
                "generator": "codex",
                "scope": "committed",
                "grouping": "repo_updates",
                "granularity": "summarized_from_pr_and_commit",
                "generated_at": "2026-04-14T20:30:00+08:00",
                "repos": [
                    {
                        "repo_label": "FIT",
                        "repo_full_name": "peterwang122/FIT",
                        "base_ref": None,
                        "head_ref": "draft-head",
                        "commit_count": 2,
                    }
                ],
            },
            published_generation_meta={
                "generator": "codex",
                "scope": "committed",
                "grouping": "repo_updates",
                "granularity": "summarized_from_pr_and_commit",
                "generated_at": "2026-04-13T20:30:00+08:00",
                "repos": [
                    {
                        "repo_label": "FIT",
                        "repo_full_name": "peterwang122/FIT",
                        "base_ref": None,
                        "head_ref": "published-head",
                        "commit_count": 5,
                    }
                ],
            },
        ),
        users=[root_user],
    )
    service = ProgressService(db)

    board = service.reset_board(root_user)

    assert board["published_progress_days"] == []
    assert board["draft_progress_days"] == []
    assert board["published_generation_meta"] is None
    assert board["draft_generation_meta"] is None
    assert board["last_published_at"] is None
    assert board["last_published_by_user_id"] is None


def test_non_root_cannot_reset_progress_board():
    with _test_client_for(_make_user(2, "alice", "user")) as client:
        response = client.post("/api/v1/progress/reset")

    assert response.status_code == 403


def test_progress_reset_route_forwards_current_user(monkeypatch):
    captured = {}

    def _reset_board(self, current_user):
        captured["current_user"] = current_user.username
        return {
            "todo_items": [],
            "published_progress_days": [],
            "published_generation_meta": None,
            "draft_progress_days": [],
            "draft_generation_meta": None,
            "updated_at": None,
            "updated_by_user_id": None,
            "updated_by_name": None,
            "last_synced_at": None,
            "last_synced_by_user_id": None,
            "last_synced_by_name": None,
            "last_sync_status": "never",
            "last_sync_error": None,
            "last_published_at": None,
            "last_published_by_user_id": None,
            "last_published_by_name": None,
        }

    from app.api import routes_progress

    monkeypatch.setattr(routes_progress.ProgressService, "reset_board", _reset_board)

    with _test_client_for(_make_user(1, "root", "root")) as client:
        response = client.post("/api/v1/progress/reset")

    assert response.status_code == 200
    assert captured["current_user"] == "root"
