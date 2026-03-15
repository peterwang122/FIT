from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FIT API"
    app_env: str = "dev"
    app_debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = "mysql+pymysql://root:865418267@127.0.0.1:3306/stock_info"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # read-only existing table mapping (defaults aligned with current DB)
    stock_table_name: str = "stock_data"
    stock_code_column: str = "stock_code"
    stock_date_column: str = "date"
    stock_open_column: str = "open_price"
    stock_high_column: str = "high_price"
    stock_low_column: str = "low_price"
    stock_close_column: str = "close_price"
    stock_pre_close_column: str = "0"
    stock_change_column: str = "price_change_amount"
    stock_pct_chg_column: str = "price_change_rate"
    stock_vol_column: str = "volume"
    stock_amount_column: str = "turnover"
    stock_pe_ttm_column: str = "pe_ttm"
    stock_pb_column: str = "pb"
    stock_total_market_value_column: str = "total_market_value"
    stock_circulating_market_value_column: str = "circulating_market_value"

    stock_basic_info_table_name: str = "stock_basic_info"
    stock_basic_info_code_column: str = "stock_code"
    stock_basic_info_name_column: str = "stock_name"
    stock_basic_cache_key: str = "fit:stock_basic_info:all"
    stock_basic_cache_ttl_seconds: int = 86400

    collector_base_url: str = "http://127.0.0.1:9000"
    collector_timeout_seconds: int = 30
    collector_task_soft_time_limit_seconds: int = 45
    collector_task_time_limit_seconds: int = 60
    collector_task_max_retries: int = 3
    collector_task_retry_backoff_seconds: int = 5

    task_idempotency_ttl_seconds: int = 3600
    collector_dedupe_lock_ttl_seconds: int = 120

    flower_url: str = "http://127.0.0.1:5555"
    cors_allow_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
