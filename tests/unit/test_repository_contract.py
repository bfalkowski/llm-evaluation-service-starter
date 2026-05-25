from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.errors import InvalidStateTransitionError, NotFoundError
from app.domain.models import EvaluationJob, EvaluationRequest, EvaluationResult, JobStatus
from app.storage.base import JobRepository
from app.storage.in_memory import InMemoryJobRepository


def make_job(
    *,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    created_at: datetime | None = None,
) -> EvaluationJob:
    timestamp = created_at or datetime.now(UTC)
    return EvaluationJob(
        job_id=uuid4(),
        tenant_id=tenant_id,
        project_id=project_id,
        status=JobStatus.QUEUED,
        request=EvaluationRequest(
            tenant_id=tenant_id,
            project_id=project_id,
            question="What does the service evaluate?",
            answer="It evaluates answer quality with deterministic mock scoring.",
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.fixture
def repository() -> JobRepository:
    return InMemoryJobRepository()


@pytest.mark.asyncio
async def test_repository_creates_and_reads_jobs(repository: JobRepository) -> None:
    job = make_job()

    created = await repository.create(job)
    fetched = await repository.get(job.job_id)

    assert created == job
    assert fetched == job


@pytest.mark.asyncio
async def test_repository_hides_cross_tenant_reads(repository: JobRepository) -> None:
    job = await repository.create(make_job(tenant_id="tenant-a"))

    with pytest.raises(NotFoundError):
        await repository.get_for_tenant(job.job_id, "tenant-b")


@pytest.mark.asyncio
async def test_repository_lists_recent_jobs_by_tenant_and_project(
    repository: JobRepository,
) -> None:
    now = datetime.now(UTC)
    older = await repository.create(
        make_job(
            tenant_id="tenant-a",
            project_id="project-a",
            created_at=now - timedelta(minutes=2),
        )
    )
    newer = await repository.create(
        make_job(
            tenant_id="tenant-a",
            project_id="project-a",
            created_at=now - timedelta(minutes=1),
        )
    )
    await repository.create(make_job(tenant_id="tenant-a", project_id="project-b", created_at=now))
    await repository.create(make_job(tenant_id="tenant-b", project_id="project-a", created_at=now))

    jobs = await repository.list_recent(tenant_id="tenant-a", project_id="project-a", limit=10)

    assert [job.job_id for job in jobs] == [newer.job_id, older.job_id]


@pytest.mark.asyncio
async def test_repository_applies_successful_transition(repository: JobRepository) -> None:
    job = await repository.create(make_job())
    result = EvaluationResult(score=88, justification="Good answer.", rubric_used=False)

    await repository.set_running(job.job_id)
    running = await repository.get(job.job_id)
    assert running.status == JobStatus.RUNNING

    succeeded = await repository.set_succeeded(job.job_id, result)
    assert succeeded.status == JobStatus.SUCCEEDED
    assert succeeded.result == result


@pytest.mark.asyncio
async def test_repository_rejects_invalid_transition(repository: JobRepository) -> None:
    job = await repository.create(make_job())

    await repository.set_running(job.job_id)

    with pytest.raises(InvalidStateTransitionError):
        await repository.set_running(job.job_id)


@pytest.mark.asyncio
async def test_repository_records_failure(repository: JobRepository) -> None:
    job = await repository.create(make_job())

    failed = await repository.set_failed(job.job_id, "provider timeout")

    assert failed.status == JobStatus.FAILED
    assert failed.error_message == "provider timeout"
