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

    async def get_for_tenant(self, job_id: UUID, tenant_id: str) -> EvaluationJob:
        job = await self.get(job_id)
        if job.tenant_id != tenant_id:
            raise NotFoundError()
        return job

    async def list_recent(
        self,
        *,
        tenant_id: str,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[EvaluationJob]:
        async with self._lock:
            jobs = list(self._jobs.values())

        jobs = [job for job in jobs if job.tenant_id == tenant_id]
        if project_id is not None:
            jobs = [job for job in jobs if job.project_id == project_id]

        return sorted(jobs, key=lambda job: job.created_at, reverse=True)[:limit]

    async def claim_next_queued(self) -> EvaluationJob | None:
        async with self._lock:
            queued_jobs = [
                job
                for job in self._jobs.values()
                if JobStatus(job.status) == JobStatus.QUEUED
                and job.attempt_count < job.max_attempts
            ]
            if not queued_jobs:
                return None

            job = sorted(queued_jobs, key=lambda item: item.created_at)[0]
            job.status = JobStatus.RUNNING
            job.attempt_count += 1
            job.claimed_at = datetime.now(UTC)
            job.updated_at = datetime.now(UTC)
            self._jobs[job.job_id] = job
            return job

    async def recover_stale_running(self, *, cutoff: datetime) -> int:
        recovered = 0
        async with self._lock:
            for job in self._jobs.values():
                if JobStatus(job.status) != JobStatus.RUNNING:
                    continue
                if job.claimed_at is None or job.claimed_at >= cutoff:
                    continue

                if job.attempt_count >= job.max_attempts:
                    job.status = JobStatus.FAILED
                    job.error_message = "Evaluation worker timed out."
                else:
                    job.status = JobStatus.QUEUED
                    job.error_message = "Evaluation worker stopped before completing the job."
                job.claimed_at = None
                job.updated_at = datetime.now(UTC)
                self._jobs[job.job_id] = job
                recovered += 1
        return recovered

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
