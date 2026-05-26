from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    service_name: str = "llm-evaluation-service"
    process_role: Literal["combined", "api", "worker"] = "combined"
    environment: str = "local"
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    otel_enabled: bool = True
    otel_exporter: Literal["console", "otlp", "none"] = "console"
    otel_otlp_endpoint: str | None = None
    worker_poll_seconds: float = 0.05
    worker_stale_job_seconds: float = 300.0
    evaluator_timeout_seconds: float = 5.0
    storage_backend: str = "postgres"
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/llm_evaluations"
    auto_create_schema: bool = True
    rate_limit_enabled: bool = True
    rate_limit_submit_per_minute: int = 30
    rate_limit_read_per_minute: int = 120
    rate_limit_list_per_minute: int = 60


def get_settings() -> Settings:
    return Settings()
