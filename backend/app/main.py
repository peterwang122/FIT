from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.collection_task_request import CollectionTaskRequest
from app.models.collection_task_request_link import CollectionTaskRequestLink
from app.models.progress_board import ProgressBoard
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
from app.models.user import User
from app.models.user_notification import UserNotification
from app.models.user_session import UserSession

app = FastAPI(title=settings.app_name)

origins = ["*"] if settings.cors_allow_origins.strip() == "*" else [
    item.strip() for item in settings.cors_allow_origins.split(",") if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(api_router, prefix=settings.api_prefix)


def _ensure_columns(table_name: str, statements: list[str]) -> None:
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


@app.on_event("startup")
def ensure_runtime_tables() -> None:
    User.__table__.create(bind=engine, checkfirst=True)
    UserSession.__table__.create(bind=engine, checkfirst=True)
    ProgressBoard.__table__.create(bind=engine, checkfirst=True)
    QuantStrategyConfig.__table__.create(bind=engine, checkfirst=True)
    ScheduledTask.__table__.create(bind=engine, checkfirst=True)
    ScheduledTaskRun.__table__.create(bind=engine, checkfirst=True)
    UserNotification.__table__.create(bind=engine, checkfirst=True)
    CollectionTaskRequest.__table__.create(bind=engine, checkfirst=True)
    CollectionTaskRequestLink.__table__.create(bind=engine, checkfirst=True)

    inspector = inspect(engine)
    existing_user_columns = {column["name"] for column in inspector.get_columns(User.__tablename__)}
    existing_progress_columns = {column["name"] for column in inspector.get_columns(ProgressBoard.__tablename__)}
    existing_strategy_columns = {column["name"] for column in inspector.get_columns(QuantStrategyConfig.__tablename__)}
    existing_strategy_indexes = {index["name"] for index in inspector.get_indexes(QuantStrategyConfig.__tablename__)}
    existing_task_columns = {column["name"] for column in inspector.get_columns(ScheduledTask.__tablename__)}
    existing_task_indexes = {index["name"] for index in inspector.get_indexes(ScheduledTask.__tablename__)}
    existing_task_run_columns = {column["name"] for column in inspector.get_columns(ScheduledTaskRun.__tablename__)}
    existing_task_run_indexes = {index["name"] for index in inspector.get_indexes(ScheduledTaskRun.__tablename__)}
    existing_stock_indexes = (
        {index["name"] for index in inspector.get_indexes(settings.stock_table_name)}
        if inspector.has_table(settings.stock_table_name)
        else set()
    )

    user_alter_statements: list[str] = []
    if "phone" not in existing_user_columns:
        user_alter_statements.append(f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `phone` VARCHAR(32) NULL UNIQUE")
    if "role" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `role` VARCHAR(32) NOT NULL DEFAULT 'user'"
        )
    if "password_hash" in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` MODIFY COLUMN `password_hash` VARCHAR(255) NULL"
        )
    if "nickname" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `nickname` VARCHAR(64) NOT NULL DEFAULT ''"
        )
    if "email" not in existing_user_columns:
        user_alter_statements.append(f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `email` VARCHAR(128) NULL")
    if "company" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `company` VARCHAR(128) NOT NULL DEFAULT ''"
        )
    if "bio" not in existing_user_columns:
        user_alter_statements.append(f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `bio` TEXT NULL")
    if "theme_preference" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `theme_preference` VARCHAR(32) NOT NULL DEFAULT 'system'"
        )
    if "language_preference" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `language_preference` VARCHAR(32) NOT NULL DEFAULT 'zh-CN'"
        )
    if "notifications_enabled" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `notifications_enabled` BOOLEAN NOT NULL DEFAULT TRUE"
        )
    if "default_homepage" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `default_homepage` VARCHAR(128) NOT NULL DEFAULT '/'"
        )
    if "updated_at" not in existing_user_columns:
        user_alter_statements.append(
            f"ALTER TABLE `{User.__tablename__}` "
            f"ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )
    if "last_login_at" not in existing_user_columns:
        user_alter_statements.append(f"ALTER TABLE `{User.__tablename__}` ADD COLUMN `last_login_at` DATETIME NULL")
    _ensure_columns(User.__tablename__, user_alter_statements)

    progress_alter_statements: list[str] = []
    if "last_synced_at" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `last_synced_at` DATETIME NULL"
        )
    if "last_synced_by_user_id" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `last_synced_by_user_id` BIGINT NULL"
        )
    if "last_sync_status" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `last_sync_status` VARCHAR(32) NOT NULL DEFAULT 'never'"
        )
    if "last_sync_error" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `last_sync_error` TEXT NULL"
        )
    if "published_progress_days" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `published_progress_days` JSON NULL"
        )
    if "draft_progress_days" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `draft_progress_days` JSON NULL"
        )
    if "published_generation_meta" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `published_generation_meta` JSON NULL"
        )
    if "draft_generation_meta" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `draft_generation_meta` JSON NULL"
        )
    if "last_published_at" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `last_published_at` DATETIME NULL"
        )
    if "last_published_by_user_id" not in existing_progress_columns:
        progress_alter_statements.append(
            f"ALTER TABLE `{ProgressBoard.__tablename__}` ADD COLUMN `last_published_by_user_id` BIGINT NULL"
        )
    _ensure_columns(ProgressBoard.__tablename__, progress_alter_statements)

    strategy_alter_statements: list[str] = []
    if "owner_user_id" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `owner_user_id` BIGINT NULL"
        )
    if "notes" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `notes` VARCHAR(1000) NOT NULL DEFAULT ''"
        )
    if "strategy_engine" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` "
            f"ADD COLUMN `strategy_engine` VARCHAR(32) NOT NULL DEFAULT 'snapshot'"
        )
    if "sequence_mode" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` "
            f"ADD COLUMN `sequence_mode` VARCHAR(32) NOT NULL DEFAULT 'single_target'"
        )
    if "target_market" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` "
            f"ADD COLUMN `target_market` VARCHAR(16) NOT NULL DEFAULT 'cn'"
        )
    if "buy_sequence_groups" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `buy_sequence_groups` JSON NULL"
        )
    if "sell_sequence_groups" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `sell_sequence_groups` JSON NULL"
        )
    if "scan_trade_config" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `scan_trade_config` JSON NULL"
        )
    if "scan_start_date" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `scan_start_date` DATE NULL"
        )
    if "scan_end_date" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `scan_end_date` DATE NULL"
        )
    if "blue_filter_groups" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `blue_filter_groups` JSON NULL"
        )
    if "red_filter_groups" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `red_filter_groups` JSON NULL"
        )
    _ensure_columns(QuantStrategyConfig.__tablename__, strategy_alter_statements)

    if "ix_quant_strategy_configs_owner_user_id" not in existing_strategy_indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` "
                    f"ADD INDEX `ix_quant_strategy_configs_owner_user_id` (`owner_user_id`)"
                )
            )
    if "ix_quant_strategy_configs_target_market" not in existing_strategy_indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` "
                    f"ADD INDEX `ix_quant_strategy_configs_target_market` (`target_market`)"
                )
            )

    task_alter_statements: list[str] = []
    if "owner_user_id" not in existing_task_columns:
        task_alter_statements.append(f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `owner_user_id` BIGINT NOT NULL")
    if "task_type" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `task_type` VARCHAR(32) NOT NULL DEFAULT 'notification'"
        )
    if "market_scope" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `market_scope` VARCHAR(32) NOT NULL DEFAULT 'cn_stock'"
        )
    if "name" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `name` VARCHAR(128) NOT NULL DEFAULT ''"
        )
    if "enabled" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `enabled` BOOLEAN NOT NULL DEFAULT TRUE"
        )
    if "schedule_time" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `schedule_time` VARCHAR(5) NOT NULL DEFAULT '09:00'"
        )
    if "config_json" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `config_json` JSON NULL"
        )
    if "last_scheduled_date" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `last_scheduled_date` DATE NULL"
        )
    if "last_run_at" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `last_run_at` DATETIME NULL"
        )
    if "last_run_status" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `last_run_status` VARCHAR(32) NOT NULL DEFAULT ''"
        )
    if "last_run_summary" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `last_run_summary` TEXT NULL"
        )
    if "last_error_message" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `last_error_message` TEXT NULL"
        )
    if "created_at" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` ADD COLUMN `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )
    if "updated_at" not in existing_task_columns:
        task_alter_statements.append(
            f"ALTER TABLE `{ScheduledTask.__tablename__}` "
            f"ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )
    _ensure_columns(ScheduledTask.__tablename__, task_alter_statements)

    if "ix_scheduled_tasks_owner_user_id" not in existing_task_indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{ScheduledTask.__tablename__}` "
                    f"ADD INDEX `ix_scheduled_tasks_owner_user_id` (`owner_user_id`)"
                )
            )
    if "ix_scheduled_tasks_task_type" not in existing_task_indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{ScheduledTask.__tablename__}` "
                    f"ADD INDEX `ix_scheduled_tasks_task_type` (`task_type`)"
                )
            )
    if "ix_scheduled_tasks_market_scope" not in existing_task_indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{ScheduledTask.__tablename__}` "
                    f"ADD INDEX `ix_scheduled_tasks_market_scope` (`market_scope`)"
                )
            )

    task_run_alter_statements: list[str] = []
    if "scheduled_task_id" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `scheduled_task_id` BIGINT NOT NULL"
        )
    if "trigger_type" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `trigger_type` VARCHAR(32) NOT NULL DEFAULT 'manual'"
        )
    if "status" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `status` VARCHAR(32) NOT NULL DEFAULT 'queued'"
        )
    if "celery_task_id" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `celery_task_id` VARCHAR(128) NULL"
        )
    if "scheduled_for" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `scheduled_for` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )
    if "started_at" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `started_at` DATETIME NULL"
        )
    if "finished_at" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `finished_at` DATETIME NULL"
        )
    if "summary" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `summary` TEXT NULL"
        )
    if "error_message" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `error_message` TEXT NULL"
        )
    if "created_at" not in existing_task_run_columns:
        task_run_alter_statements.append(
            f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` ADD COLUMN `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )
    _ensure_columns(ScheduledTaskRun.__tablename__, task_run_alter_statements)

    if "ix_scheduled_task_runs_scheduled_task_id" not in existing_task_run_indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` "
                    f"ADD INDEX `ix_scheduled_task_runs_scheduled_task_id` (`scheduled_task_id`)"
                )
            )

    if (
        inspector.has_table(settings.stock_table_name)
        and "idx_stock_daily_source_date_code" not in existing_stock_indexes
    ):
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{settings.stock_table_name}` "
                    f"ADD INDEX `idx_stock_daily_source_date_code` "
                    f"(`{settings.stock_data_source_column}`, "
                    f"`{settings.stock_date_column}`, "
                    f"`{settings.stock_code_column}`)"
                )
            )
    if "ix_scheduled_task_runs_status" not in existing_task_run_indexes:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{ScheduledTaskRun.__tablename__}` "
                    f"ADD INDEX `ix_scheduled_task_runs_status` (`status`)"
                )
            )

    with SessionLocal() as db:
        root_user = _ensure_system_user(db, settings.root_username, settings.root_password, "root")
        _ensure_system_user(db, settings.guest_username, settings.guest_password, "guest")
        (
            db.query(QuantStrategyConfig)
            .filter(QuantStrategyConfig.owner_user_id.is_(None))
            .update({QuantStrategyConfig.owner_user_id: root_user.id}, synchronize_session=False)
        )
        db.commit()


def _ensure_system_user(db, username: str, password: str, role: str) -> User:
    item = db.query(User).filter(User.username == username).first()
    nickname = "Root" if role == "root" else "游客"
    if item is None:
        item = User(
            username=username,
            phone=None,
            password_hash=hash_password(password) if password else None,
            role=role,
            nickname=nickname,
            email=None,
            company="",
            bio="",
            theme_preference="system",
            language_preference="zh-CN",
            notifications_enabled=True,
            default_homepage="/",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    mutated = False
    if item.role != role:
        item.role = role
        mutated = True
    if not item.password_hash and password:
        item.password_hash = hash_password(password)
        mutated = True
    if not (item.nickname or "").strip():
        item.nickname = nickname
        mutated = True
    if not (item.theme_preference or "").strip():
        item.theme_preference = "system"
        mutated = True
    if not (item.language_preference or "").strip():
        item.language_preference = "zh-CN"
        mutated = True
    if not (item.default_homepage or "").strip():
        item.default_homepage = "/"
        mutated = True
    if mutated:
        db.add(item)
        db.commit()
        db.refresh(item)
    return item


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
