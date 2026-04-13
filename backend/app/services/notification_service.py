from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.models.collection_task_request import CollectionTaskRequest
from app.models.collection_task_request_link import CollectionTaskRequestLink
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.models.user_notification import UserNotification


def _utcnow() -> datetime:
    return datetime.utcnow()


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def _serialize_notification(self, item: UserNotification) -> dict:
        return {
            "id": item.id,
            "recipient_user_id": item.recipient_user_id,
            "category": item.category,
            "title": item.title,
            "body": item.body or "",
            "action_url": item.action_url,
            "action_label": item.action_label,
            "is_read": bool(item.is_read),
            "dedupe_key": item.dedupe_key,
            "payload_json": item.payload_json or {},
            "created_at": item.created_at,
            "read_at": item.read_at,
        }

    def list_notifications(self, recipient_user_id: int, limit: int = 12) -> dict:
        unread_count = (
            self.db.query(UserNotification)
            .filter(
                UserNotification.recipient_user_id == recipient_user_id,
                UserNotification.is_read.is_(False),
            )
            .count()
        )
        items = (
            self.db.query(UserNotification)
            .filter(UserNotification.recipient_user_id == recipient_user_id)
            .order_by(UserNotification.created_at.desc(), UserNotification.id.desc())
            .limit(max(limit, 1))
            .all()
        )
        return {
            "unread_count": unread_count,
            "items": [self._serialize_notification(item) for item in items],
        }

    def mark_read(self, notification_id: int, recipient_user_id: int) -> dict:
        item = (
            self.db.query(UserNotification)
            .filter(
                UserNotification.id == notification_id,
                UserNotification.recipient_user_id == recipient_user_id,
            )
            .first()
        )
        if item is None:
            raise ValueError("notification not found")
        if not item.is_read:
            item.is_read = True
            item.read_at = _utcnow()
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
        return self._serialize_notification(item)

    def mark_all_read(self, recipient_user_id: int) -> dict:
        now = _utcnow()
        (
            self.db.query(UserNotification)
            .filter(
                UserNotification.recipient_user_id == recipient_user_id,
                UserNotification.is_read.is_(False),
            )
            .update(
                {
                    UserNotification.is_read: True,
                    UserNotification.read_at: now,
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return self.list_notifications(recipient_user_id)

    def _upsert_notification(
        self,
        *,
        recipient_user_id: int,
        category: str,
        title: str,
        body: str,
        action_url: str | None = None,
        action_label: str | None = None,
        dedupe_key: str | None = None,
        payload_json: dict | None = None,
    ) -> UserNotification:
        item: UserNotification | None = None
        if dedupe_key:
            item = (
                self.db.query(UserNotification)
                .filter(
                    UserNotification.recipient_user_id == recipient_user_id,
                    UserNotification.dedupe_key == dedupe_key,
                )
                .first()
            )
        if item is None:
            item = UserNotification(
                recipient_user_id=recipient_user_id,
                category=category,
                title=title,
                body=body,
                action_url=action_url,
                action_label=action_label,
                dedupe_key=dedupe_key,
                payload_json=payload_json or {},
                is_read=False,
                read_at=None,
            )
            self.db.add(item)
        else:
            item.category = category
            item.title = title
            item.body = body
            item.action_url = action_url
            item.action_label = action_label
            item.payload_json = payload_json or {}
            item.is_read = False
            item.read_at = None
            self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _create_notification(
        self,
        *,
        recipient_user_id: int,
        category: str,
        title: str,
        body: str,
        action_url: str | None = None,
        action_label: str | None = None,
        payload_json: dict | None = None,
    ) -> UserNotification:
        item = UserNotification(
            recipient_user_id=recipient_user_id,
            category=category,
            title=title,
            body=body,
            action_url=action_url,
            action_label=action_label,
            payload_json=payload_json or {},
            is_read=False,
            read_at=None,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _delete_notification(self, notification_id: int | None) -> None:
        if not notification_id:
            return
        item = self.db.get(UserNotification, notification_id)
        if item is None:
            return
        self.db.delete(item)
        self.db.commit()

    def create_strategy_received_notification(
        self,
        *,
        recipient_user_id: int,
        sender_user: User,
        strategy: QuantStrategyConfig,
    ) -> None:
        sender_name = (sender_user.nickname or "").strip() or sender_user.username
        target_name = strategy.target_name or strategy.target_code
        self._create_notification(
            recipient_user_id=recipient_user_id,
            category="strategy_received",
            title="你收到一条来自 root 的策略",
            body=f"{sender_name} 已将策略《{strategy.name}》发送给你，标的为 {target_name}。",
            action_url="/quant/strategies",
            action_label="查看策略",
            payload_json={
                "strategy_id": strategy.id,
                "strategy_name": strategy.name,
                "target_code": strategy.target_code,
                "target_name": strategy.target_name,
                "sender_user_id": sender_user.id,
                "sender_username": sender_user.username,
            },
        )

    def _get_root_user(self) -> User | None:
        return self.db.query(User).filter(User.role == "root").order_by(User.id.asc()).first()

    def _get_or_create_request(self, market_scope: str, stock_code: str, stock_name: str) -> CollectionTaskRequest:
        item = (
            self.db.query(CollectionTaskRequest)
            .filter(
                CollectionTaskRequest.market_scope == market_scope,
                CollectionTaskRequest.stock_code == stock_code,
            )
            .order_by(CollectionTaskRequest.id.desc())
            .first()
        )
        if item is None:
            item = CollectionTaskRequest(
                market_scope=market_scope,
                stock_code=stock_code,
                stock_name=stock_name or "",
                status="closed",
                root_notification_id=None,
                resolved_task_id=None,
                resolved_at=None,
            )
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
            return item
        if stock_name and item.stock_name != stock_name:
            item.stock_name = stock_name
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
        return item

    def _find_enabled_root_collection_task(self, market_scope: str, stock_code: str) -> ScheduledTask | None:
        root_user = self._get_root_user()
        if root_user is None:
            return None
        candidates = (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.owner_user_id == root_user.id,
                ScheduledTask.task_type == "collection",
                ScheduledTask.market_scope == market_scope,
                ScheduledTask.enabled.is_(True),
            )
            .order_by(ScheduledTask.updated_at.desc(), ScheduledTask.id.desc())
            .all()
        )
        for item in candidates:
            config = item.config_json or {}
            if str(config.get("stock_code", "")).strip() == stock_code:
                return item
        return None

    def _build_root_collection_action_url(self, market_scope: str, stock_code: str, stock_name: str) -> str:
        query = urlencode(
            {
                "task_type": "collection",
                "market_scope": market_scope,
                "stock_code": stock_code,
                "stock_name": stock_name or "",
            }
        )
        return f"/tasks/manage?{query}"

    def _upsert_root_collection_required_notification(
        self,
        request: CollectionTaskRequest,
        links: list[CollectionTaskRequestLink],
    ) -> UserNotification | None:
        root_user = self._get_root_user()
        if root_user is None:
            return None

        user_ids = sorted({item.requester_user_id for item in links})
        task_ids = sorted({item.notification_task_id for item in links})
        strategy_ids = sorted({item.strategy_id for item in links})
        users = self.db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
        display_names = [
            ((item.nickname or "").strip() or item.username)
            for item in users
        ]
        display_text = "、".join(display_names[:3])
        if len(display_names) > 3:
            display_text = f"{display_text} 等 {len(display_names)} 人"
        elif not display_text:
            display_text = "相关用户"

        title = f"待配置采集：{request.stock_name or request.stock_code}"
        body = (
            f"股票 {request.stock_code}"
            f"{f'（{request.stock_name}）' if request.stock_name else ''}"
            f" 当前有 {len(user_ids)} 位用户、{len(task_ids)} 条通知任务、{len(strategy_ids)} 条策略等待采集支持。"
            f" 涉及用户：{display_text}。"
        )
        notification = self._upsert_notification(
            recipient_user_id=root_user.id,
            category="collection_required",
            title=title,
            body=body,
            action_url=self._build_root_collection_action_url(
                request.market_scope,
                request.stock_code,
                request.stock_name,
            ),
            action_label="去配置采集",
            dedupe_key=f"collection_required:{request.market_scope}:{request.stock_code}",
            payload_json={
                "request_id": request.id,
                "market_scope": request.market_scope,
                "stock_code": request.stock_code,
                "stock_name": request.stock_name,
                "user_ids": user_ids,
                "task_ids": task_ids,
                "strategy_ids": strategy_ids,
            },
        )
        return notification

    def _notify_requesters_collection_ready(
        self,
        request: CollectionTaskRequest,
        links: list[CollectionTaskRequestLink],
    ) -> None:
        if not links:
            return
        links_by_user: dict[int, list[CollectionTaskRequestLink]] = defaultdict(list)
        for item in links:
            links_by_user[item.requester_user_id].append(item)

        for user_id, user_links in links_by_user.items():
            strategy_ids = [item.strategy_id for item in user_links]
            strategies = (
                self.db.query(QuantStrategyConfig)
                .filter(QuantStrategyConfig.id.in_(strategy_ids))
                .order_by(QuantStrategyConfig.updated_at.desc(), QuantStrategyConfig.id.desc())
                .all()
            )
            strategy_names = [item.name for item in strategies]
            summary = "、".join(strategy_names[:3])
            if len(strategy_names) > 3:
                summary = f"{summary} 等 {len(strategy_names)} 条策略"
            elif not summary:
                summary = "相关策略"
            self._create_notification(
                recipient_user_id=user_id,
                category="collection_ready",
                title=f"已配置采集：{request.stock_name or request.stock_code}",
                body=(
                    f"root 已为股票 {request.stock_code}"
                    f"{f'（{request.stock_name}）' if request.stock_name else ''}"
                    f" 配置采集任务。涉及策略：{summary}。"
                ),
                action_url="/quant/strategies",
                action_label="查看策略",
                payload_json={
                    "request_id": request.id,
                    "market_scope": request.market_scope,
                    "stock_code": request.stock_code,
                    "stock_name": request.stock_name,
                    "strategy_ids": strategy_ids,
                },
            )

    def _close_request_without_links(self, request: CollectionTaskRequest) -> None:
        if request.root_notification_id:
            self._delete_notification(request.root_notification_id)
        request.root_notification_id = None
        request.status = "closed"
        request.resolved_task_id = None
        request.resolved_at = None
        self.db.add(request)
        self.db.commit()

    def _reconcile_request(self, request_id: int) -> None:
        request = self.db.get(CollectionTaskRequest, request_id)
        if request is None:
            return

        links = (
            self.db.query(CollectionTaskRequestLink)
            .filter(CollectionTaskRequestLink.request_id == request.id)
            .order_by(CollectionTaskRequestLink.id.asc())
            .all()
        )
        if not links:
            self._close_request_without_links(request)
            return

        enabled_collection_task = self._find_enabled_root_collection_task(request.market_scope, request.stock_code)
        previous_status = request.status

        if enabled_collection_task is not None:
            if request.root_notification_id:
                self._delete_notification(request.root_notification_id)
                request.root_notification_id = None
            request.status = "resolved"
            request.resolved_task_id = enabled_collection_task.id
            if previous_status == "pending":
                request.resolved_at = _utcnow()
                self.db.add(request)
                self.db.commit()
                self._notify_requesters_collection_ready(request, links)
                return
            self.db.add(request)
            self.db.commit()
            return

        request.status = "pending"
        request.resolved_task_id = None
        request.resolved_at = None
        notification = self._upsert_root_collection_required_notification(request, links)
        request.root_notification_id = notification.id if notification else None
        self.db.add(request)
        self.db.commit()

    def sync_notification_task_requirements(self, task: ScheduledTask) -> None:
        if task.task_type != "notification":
            return

        owner = self.db.get(User, task.owner_user_id)
        existing_links = (
            self.db.query(CollectionTaskRequestLink)
            .filter(CollectionTaskRequestLink.notification_task_id == task.id)
            .all()
        )
        existing_by_strategy = {item.strategy_id: item for item in existing_links}
        affected_request_ids = {item.request_id for item in existing_links}

        desired_stock_strategies: list[QuantStrategyConfig] = []
        if owner is not None and owner.role == "user" and task.enabled:
            strategy_ids = [
                int(raw_id)
                for raw_id in (task.config_json or {}).get("strategy_ids", [])
                if isinstance(raw_id, int) or str(raw_id).isdigit()
            ]
            if strategy_ids:
                desired_stock_strategies = (
                    self.db.query(QuantStrategyConfig)
                    .filter(
                        QuantStrategyConfig.owner_user_id == owner.id,
                        QuantStrategyConfig.id.in_(strategy_ids),
                        QuantStrategyConfig.strategy_type == "stock",
                    )
                    .all()
                )
                desired_stock_strategies = [
                    item
                    for item in desired_stock_strategies
                    if not (
                        str(item.strategy_engine or "").strip().lower() == "sequence"
                        and str(item.sequence_mode or "").strip().lower() == "market_scan"
                    )
                ]

        desired_strategy_ids = {item.id for item in desired_stock_strategies}
        for strategy_id, link in existing_by_strategy.items():
            if strategy_id not in desired_strategy_ids:
                self.db.delete(link)

        for strategy in desired_stock_strategies:
            request = self._get_or_create_request(
                task.market_scope,
                strategy.target_code,
                strategy.target_name,
            )
            existing_link = existing_by_strategy.get(strategy.id)
            if existing_link is None:
                self.db.add(
                    CollectionTaskRequestLink(
                        request_id=request.id,
                        requester_user_id=task.owner_user_id,
                        notification_task_id=task.id,
                        strategy_id=strategy.id,
                    )
                )
            elif existing_link.request_id != request.id:
                existing_link.request_id = request.id
                self.db.add(existing_link)
            affected_request_ids.add(request.id)

        self.db.commit()

        for request_id in sorted(affected_request_ids):
            self._reconcile_request(request_id)

    def remove_notification_task_requirements(self, notification_task_id: int) -> None:
        links = (
            self.db.query(CollectionTaskRequestLink)
            .filter(CollectionTaskRequestLink.notification_task_id == notification_task_id)
            .all()
        )
        if not links:
            return
        request_ids = sorted({item.request_id for item in links})
        for item in links:
            self.db.delete(item)
        self.db.commit()
        for request_id in request_ids:
            self._reconcile_request(request_id)

    def sync_collection_task_state(self, market_scope: str, stock_code: str) -> None:
        requests = (
            self.db.query(CollectionTaskRequest)
            .filter(
                CollectionTaskRequest.market_scope == market_scope,
                CollectionTaskRequest.stock_code == stock_code,
            )
            .order_by(CollectionTaskRequest.id.desc())
            .all()
        )
        for request in requests:
            self._reconcile_request(request.id)
