from __future__ import annotations

from app.core.config import Settings
from app.storage.base import JobRepository
from app.storage.in_memory import InMemoryJobRepository


async def build_repository(settings: Settings) -> JobRepository:
    if settings.storage_backend == "memory":
        return InMemoryJobRepository()
    if settings.storage_backend == "postgres":
        from app.storage.postgres import PostgresJobRepository

        repository = PostgresJobRepository(settings.database_url)
        if settings.auto_create_schema:
            await repository.init_schema()
        return repository
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
