from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.models import EvaluationJob, EvaluationResult


class JobRepository(Protocol):
    async def create(self, job: EvaluationJob) -> EvaluationJob: ...

    async def get(self, job_id: UUID) -> EvaluationJob: ...

    async def get_for_tenant(self, job_id: UUID, tenant_id: str) -> EvaluationJob: ...

    async def list_recent(
        self,
        *,
        tenant_id: str,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[EvaluationJob]: ...

    async def claim_next_queued(self) -> EvaluationJob | None: ...

    async def set_running(self, job_id: UUID) -> EvaluationJob: ...

    async def set_succeeded(self, job_id: UUID, result: EvaluationResult) -> EvaluationJob: ...

    async def set_failed(self, job_id: UUID, message: str) -> EvaluationJob: ...

    async def health_check(self) -> bool: ...

    async def close(self) -> None: ...
