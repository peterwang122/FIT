from sqlalchemy.orm import Session

from app.models.progress_board import ProgressBoard
from app.models.user import User


def _default_progress_board() -> dict:
    return {
        "todo_items": [
            {"id": "todo-1", "text": "补充自动化测试与前端构建校验，形成稳定发布流程。"},
            {"id": "todo-2", "text": "继续优化首页细节交互，包括图表密度、导航体验与移动端适配。"},
            {"id": "todo-3", "text": "补齐更多市场数据模块的异常提示与空数据处理。"},
        ],
        "progress_days": [
            {
                "id": "progress-1",
                "date": "2026-03-12",
                "title": "基础展示框架搭建",
                "items": [
                    {"id": "progress-1-1", "text": "完成前端 UI 重构，接入 Flower 任务监控入口。"},
                    {"id": "progress-1-2", "text": "支持读取现有数据库字段映射，兼容已存在的表结构。"},
                ],
            },
            {
                "id": "progress-2",
                "date": "2026-03-15",
                "title": "首页与量化分析扩展",
                "items": [
                    {"id": "progress-2-1", "text": "首页加入指数、汇率、情绪和中金所相关视图。"},
                    {"id": "progress-2-2", "text": "量化分析补充更多指标、副图和策略回测能力。"},
                ],
            },
        ],
    }


class ProgressService:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_display_name(self, user: User | None) -> str | None:
        if user is None:
            return None
        return (user.nickname or "").strip() or user.username

    def _get_board_row(self) -> ProgressBoard:
        item = self.db.query(ProgressBoard).order_by(ProgressBoard.id.asc()).first()
        if item is not None:
            return item

        defaults = _default_progress_board()
        item = ProgressBoard(todo_items=defaults["todo_items"], progress_days=defaults["progress_days"], updated_by_user_id=None)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def serialize_board(self, item: ProgressBoard) -> dict:
        updated_by = self.db.get(User, item.updated_by_user_id) if item.updated_by_user_id else None
        return {
            "todo_items": item.todo_items or [],
            "progress_days": item.progress_days or [],
            "updated_at": item.updated_at,
            "updated_by_user_id": item.updated_by_user_id,
            "updated_by_name": self._resolve_display_name(updated_by),
        }

    def get_board(self) -> dict:
        item = self._get_board_row()
        return self.serialize_board(item)

    def update_board(self, payload: dict, current_user: User) -> dict:
        item = self._get_board_row()
        item.todo_items = payload.get("todo_items") or []
        item.progress_days = payload.get("progress_days") or []
        item.updated_by_user_id = current_user.id
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self.serialize_board(item)
