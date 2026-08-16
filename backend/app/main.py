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
    if "research_option_template" not in existing_strategy_columns:
        strategy_alter_statements.append(
            f"ALTER TABLE `{QuantStrategyConfig.__tablename__}` ADD COLUMN `research_option_template` JSON NULL"
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
    if (
        inspector.has_table(settings.stock_table_name)
        and "idx_stock_daily_source_code_date" not in existing_stock_indexes
    ):
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{settings.stock_table_name}` "
                    f"ADD INDEX `idx_stock_daily_source_code_date` "
                    f"(`{settings.stock_data_source_column}`, "
                    f"`{settings.stock_code_column}`, "
                    f"`{settings.stock_date_column}`)"
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
        risk_strategies = _ensure_default_risk_strategies(db, root_user)
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="stock_exchange_official_daily",
            name="沪深官网股票日更",
            schedule_time="18:30",
            market_scope="cn_stock",
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="index_csi_dividend_daily",
            name="中证红利指数日更",
            schedule_time="17:10",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="forex_daily",
            name="汇率日更",
            schedule_time="09:10",
            market_scope="us_index",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="usd_index_daily",
            name="美元指数日更",
            schedule_time="09:15",
            market_scope="us_index",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="forex_intraday",
            name="汇率18时盘中更新",
            schedule_time="18:00",
            market_scope="us_index",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="usd_index_intraday",
            name="美元指数18时盘中更新",
            schedule_time="18:00",
            market_scope="us_index",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="douyin_coze_emotion_daily",
            name="抖音四大指数情绪日更",
            schedule_time="19:00",
            market_scope="cn_stock",
            enforce_schedule_time=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="exchange_option_daily",
            name="沪深交易所期权行情日更",
            schedule_time="17:00",
            market_scope="cn_stock",
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="exchange_option_stats_daily",
            name="沪深交易所期权官方统计补齐",
            schedule_time="21:10",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="option_minute_daily",
            name="期权分钟行情采集",
            schedule_time="09:25",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="cn_risk_free_rate_daily",
            name="人民币无风险利率日更",
            schedule_time="16:40",
            market_scope="cn_stock",
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="cn_macro_daily",
            name="A股宏观指标日更",
            schedule_time="21:30",
            market_scope="cn_stock",
            enforce_schedule_time=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="margin_trading_daily",
            name="A股融资融券日更",
            schedule_time="09:20",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="fund_purchase_limit_daily",
            name="A股公募基金限购日更",
            schedule_time="22:15",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="index_cn_market_fear_greed_daily",
            name="A股大盘恐贪指数日更",
            schedule_time="21:50",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="index_cn_baifenwei_fear_greed_daily",
            name="百分位A股恐贪指数日更",
            schedule_time="23:10",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="quant_index_daily",
            name="看板数据计算",
            schedule_time="22:30",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="global_risk_daily",
            name="全球冲击因子日更",
            schedule_time="16:10",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
        )
        _ensure_default_collection_task(
            db,
            root_user,
            collector_key="a_share_turnover_concentration_daily",
            name="A股成交集中度日更",
            schedule_time="22:05",
            market_scope="cn_stock",
            enforce_schedule_time=True,
            enforce_name=True,
            legacy_collector_keys=("csi_tech_concentration_daily",),
        )
        _ensure_default_risk_notification_task(db, root_user, risk_strategies)
        for collector_key, name, schedule_time, legacy_names in (
            ("index_hk_daily", "港股指数日更", "18:00", ("港股指数采集",)),
            (
                "hk_index_futures_daily",
                "港股股指期货日更",
                "22:45",
                ("港股期货数据采集",),
            ),
        ):
            _ensure_default_collection_task(
                db,
                root_user,
                collector_key=collector_key,
                name=name,
                schedule_time=schedule_time,
                market_scope="hk_index",
                enforce_schedule_time=True,
                enforce_name=True,
                legacy_names=legacy_names,
            )
        for collector_key, name, schedule_time, legacy_names in (
            ("index_us_credit_spread_daily", "美股高收益债利差日更", "00:45", ("美债收益债利差采集",)),
            ("index_us_treasury_yield_daily", "美债收益率日更", "05:30", ("美债收益率采集",)),
            ("index_us_daily", "美股指数日更", "09:30", ("美股指数采集",)),
            ("index_us_vix_daily", "美股 VIX 日更", "09:40", ("美股VIX采集",)),
            ("index_us_fear_greed_daily", "美股恐贪指数日更", "06:20", ("美股恐贪指数采集",)),
            ("index_us_put_call_ratio_daily", "美股 Put/Call Ratio 日更", "09:50", ()),
            ("us_index_futures_daily", "美股股指期货日更", "10:00", ("美股期货数据采集",)),
            ("index_us_hedge_proxy_daily", "OFR 美股持仓代理月更", "09:30", ("美股持仓采集",)),
            (
                "us_index_futures_official_daily",
                "CME 美股股指期货官方结算日更",
                "14:30",
                ("美股期货合约采集",),
            ),
        ):
            _ensure_default_collection_task(
                db,
                root_user,
                collector_key=collector_key,
                name=name,
                schedule_time=schedule_time,
                market_scope="us_index",
                enforce_schedule_time=True,
                enforce_name=True,
                legacy_names=legacy_names,
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


def _ensure_default_risk_strategies(db, owner: User) -> list[QuantStrategyConfig]:
    definitions = (
        (
            "中证1000-黄色脆弱期",
            "yellow_vulnerability",
            "融资堆积、MO价格P/C偏高且IM中期期现差转弱时提示降低高弹性仓位、停止追涨。",
        ),
        (
            "中证1000-红色风险升级",
            "red_escalation",
            "IM期现差恶化、中信净空增加且融资短期流出时按大级别调整管理风险。",
        ),
        (
            "中证1000-全球冲击",
            "global_shock",
            "识别全球全面避险或海外科技去杠杆输入，仅表示风险状态。",
        ),
    )
    result: list[QuantStrategyConfig] = []
    for name, risk_key, notes in definitions:
        item = (
            db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == owner.id,
                QuantStrategyConfig.name == name,
            )
            .first()
        )
        if item is None:
            item = QuantStrategyConfig(owner_user_id=owner.id, name=name)
        item.notes = notes
        item.strategy_engine = "risk"
        item.sequence_mode = "single_target"
        item.strategy_type = "index"
        item.target_market = "cn"
        item.target_code = "sh000852"
        item.target_name = "中证1000"
        item.indicator_params = {"risk_strategy": {"key": risk_key}}
        item.buy_sequence_groups = []
        item.sell_sequence_groups = []
        item.scan_trade_config = {}
        item.research_option_template = None
        item.blue_filter_groups = []
        item.red_filter_groups = []
        item.blue_filters = {}
        item.red_filters = {}
        item.blue_boll_filter = {}
        item.red_boll_filter = {}
        item.signal_buy_color = "blue"
        item.signal_sell_color = "red"
        item.purple_conflict_mode = "sell_first"
        item.start_date = None
        item.scan_start_date = None
        item.scan_end_date = None
        item.buy_position_pct = 0
        item.sell_position_pct = 0
        item.execution_price_mode = "next_open"
        db.add(item)
        result.append(item)
    db.commit()
    for item in result:
        db.refresh(item)
    return result


def _ensure_default_risk_notification_task(
    db,
    owner: User,
    strategies: list[QuantStrategyConfig],
) -> ScheduledTask:
    name = "中证1000风险状态每日通知"
    item = (
        db.query(ScheduledTask)
        .filter(
            ScheduledTask.owner_user_id == owner.id,
            ScheduledTask.task_type == "notification",
            ScheduledTask.name == name,
        )
        .first()
    )
    strategy_ids = [strategy.id for strategy in strategies]
    config = {
        "target_type": "index",
        "target_code": "sh000852",
        "target_name": "中证1000",
        "strategy_ids": strategy_ids,
        "target_email": str(owner.email or "").strip() or None,
    }
    if item is None:
        item = ScheduledTask(
            owner_user_id=owner.id,
            task_type="notification",
            market_scope="cn_stock",
            name=name,
            enabled=True,
            schedule_time="22:40",
            config_json=config,
            last_run_status="",
            last_run_summary="",
            last_error_message="",
        )
    else:
        item.market_scope = "cn_stock"
        item.schedule_time = "22:40"
        item.config_json = config
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _ensure_default_collection_task(
    db,
    owner: User,
    *,
    collector_key: str,
    name: str,
    schedule_time: str,
    market_scope: str = "cn_stock",
    enforce_schedule_time: bool = False,
    enforce_name: bool = False,
    legacy_names: tuple[str, ...] = (),
    legacy_collector_keys: tuple[str, ...] = (),
) -> ScheduledTask:
    existing_items = (
        db.query(ScheduledTask)
        .filter(
            ScheduledTask.owner_user_id == owner.id,
            ScheduledTask.task_type == "collection",
            ScheduledTask.market_scope == market_scope,
        )
        .all()
    )
    for item in existing_items:
        item_config = dict(item.config_json or {})
        item_collector_key = str(item_config.get("collector_key") or "").strip().lower()
        matches_legacy_name = not item_collector_key and item.name in legacy_names
        matches_legacy_collector = item_collector_key in {
            str(key).strip().lower() for key in legacy_collector_keys
        }
        if item_collector_key == collector_key or matches_legacy_name or matches_legacy_collector:
            if matches_legacy_name or matches_legacy_collector:
                item_config["collector_key"] = collector_key
                item.config_json = item_config
                db.add(item)
            if enforce_schedule_time and item.schedule_time != schedule_time:
                item.schedule_time = schedule_time
                db.add(item)
            if enforce_name and item.name != name:
                item.name = name
                db.add(item)
            return item

    item = ScheduledTask(
        owner_user_id=owner.id,
        task_type="collection",
        market_scope=market_scope,
        name=name,
        enabled=True,
        schedule_time=schedule_time,
        config_json={
            "collector_key": collector_key,
            "target_type": None,
            "target_code": "",
            "target_name": "",
        },
        last_run_status="",
        last_run_summary="",
        last_error_message="",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
