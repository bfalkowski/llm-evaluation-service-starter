from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.core.errors import InvalidStateTransitionError, NotFoundError
from app.domain.models import EvaluationJob, EvaluationResult, JobStatus


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, EvaluationJob] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: EvaluationJob) -> EvaluationJob:
        async with self._lock:
            self._jobs[job.job_id] = job
            return job

    async def get(self, job_id: UUID) -> EvaluationJob:
        async with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise NotFoundError() from exc

    async def list_recent(
        self,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[EvaluationJob]:
        async with self._lock:
            jobs = list(self._jobs.values())

        if tenant_id is not None:
            jobs = [job for job in jobs if job.tenant_id == tenant_id]
        if project_id is not None:
            jobs = [job for job in jobs if job.project_id == project_id]

        return sorted(jobs, key=lambda job: job.created_at, reverse=True)[:limit]

    async def set_running(self, job_id: UUID) -> EvaluationJob:
        return await self._transition(job_id, {JobStatus.QUEUED}, JobStatus.RUNNING)

    async def set_succeeded(self, job_id: UUID, result: EvaluationResult) -> EvaluationJob:
        job = await self._transition(job_id, {JobStatus.RUNNING}, JobStatus.SUCCEEDED)
        async with self._lock:
            job.result = result
            job.updated_at = datetime.now(UTC)
            self._jobs[job_id] = job
            return job

    async def set_failed(self, job_id: UUID, message: str) -> EvaluationJob:
        job = await self._transition(
            job_id,
            {JobStatus.QUEUED, JobStatus.RUNNING},
            JobStatus.FAILED,
        )
        async with self._lock:
            job.error_message = message
            job.updated_at = datetime.now(UTC)
            self._jobs[job_id] = job
            return job

    async def _transition(
        self,
        job_id: UUID,
        allowed_from: set[JobStatus],
        target: JobStatus,
    ) -> EvaluationJob:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotFoundError()
            current = JobStatus(job.status)
            if current not in allowed_from:
                raise InvalidStateTransitionError()
            job.status = target
            job.updated_at = datetime.now(UTC)
            self._jobs[job_id] = job
            return job

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None
