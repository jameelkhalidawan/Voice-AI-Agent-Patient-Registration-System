"""Environment-backed application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables and an optional .env file."""

    app_name: str = "Care Cloud Patient Intake API"
    app_env: str = "development"
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "sqlite:///./care_cloud.db"
    api_key: str | None = None
    vapi_webhook_secret: str | None = None
    cors_origins: str = ""
    max_request_bytes: int = 65536
    max_webhook_request_bytes: int = 1048576
    rate_limit_per_minute: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
