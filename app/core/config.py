from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    service_name: str = "llm-evaluation-service"
    environment: str = "local"
    log_level: str = "INFO"
    otel_enabled: bool = True
    worker_poll_seconds: float = 0.05
    evaluator_timeout_seconds: float = 5.0
    storage_backend: str = "postgres"
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/llm_evaluations"


def get_settings() -> Settings:
    return Settings()
