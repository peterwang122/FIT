from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FIT API"
    app_env: str = "dev"
    app_debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = 'mysql+pymysql://root:root@127.0.0.1:3306/fit'
    redis_url: str = 'redis://127.0.0.1:6379/0'

    collector_base_url: str = 'http://127.0.0.1:9000'
    collector_timeout_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
