from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FIT API"
    app_env: str = "dev"
    app_debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = "mysql+pymysql://root:root@127.0.0.1:3306/fit"
    redis_url: str = "redis://127.0.0.1:6379/0"

    collector_base_url: str = "http://127.0.0.1:9000"
    collector_timeout_seconds: int = 30
    collector_task_soft_time_limit_seconds: int = 45
    collector_task_time_limit_seconds: int = 60
    collector_task_max_retries: int = 3
    collector_task_retry_backoff_seconds: int = 5

    task_idempotency_ttl_seconds: int = 3600
    collector_dedupe_lock_ttl_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
