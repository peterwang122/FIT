from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FIT API"
    app_env: str = "dev"
    app_debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = "mysql+pymysql://root:root@127.0.0.1:3306/fit"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # read-only existing table mapping
    stock_table_name: str = "stock_data"
    stock_code_column: str = "ts_code"
    stock_date_column: str = "trade_date"
    stock_open_column: str = "open"
    stock_high_column: str = "high"
    stock_low_column: str = "low"
    stock_close_column: str = "close"
    stock_pre_close_column: str = "pre_close"
    stock_change_column: str = "change"
    stock_pct_chg_column: str = "pct_chg"
    stock_vol_column: str = "vol"
    stock_amount_column: str = "amount"

    collector_base_url: str = "http://127.0.0.1:9000"
    collector_timeout_seconds: int = 30
    collector_task_soft_time_limit_seconds: int = 45
    collector_task_time_limit_seconds: int = 60
    collector_task_max_retries: int = 3
    collector_task_retry_backoff_seconds: int = 5

    task_idempotency_ttl_seconds: int = 3600
    collector_dedupe_lock_ttl_seconds: int = 120

    flower_url: str = "http://127.0.0.1:5555"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
