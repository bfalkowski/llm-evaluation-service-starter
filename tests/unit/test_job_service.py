import pytest

from app.core.audit import AuditRecorder
from app.domain.models import EvaluationRequest, JobStatus
from app.services.evaluator import Evaluator
from app.services.job_service import EvaluationJobService
from app.services.queue import InMemoryJobQueue
from app.storage.in_memory import InMemoryJobRepository


@pytest.mark.asyncio
async def test_job_state_transitions_to_succeeded() -> None:
    repo = InMemoryJobRepository()
    queue = InMemoryJobQueue()
    service = EvaluationJobService(repo, queue, Evaluator(), AuditRecorder())
    request = EvaluationRequest(
        tenant_id="tenant-a",
        project_id="project-a",
        question="Why use typed errors?",
        answer="Typed errors make API behavior predictable.",
    )

    job = await service.submit(request)
    assert job.status == JobStatus.QUEUED

    queued_job_id = await queue._queue.get()  # Small white-box assertion for this in-memory adapter.
    await service.process(queued_job_id)
    updated = await service.get(job.job_id)

    assert updated.status == JobStatus.SUCCEEDED
    assert updated.result is not None
    assert updated.result.score > 0


@pytest.mark.asyncio
async def test_repository_rejects_invalid_transition() -> None:
    repo = InMemoryJobRepository()
    queue = InMemoryJobQueue()
    service = EvaluationJobService(repo, queue, Evaluator(), AuditRecorder())
    job = await service.submit(
        EvaluationRequest(
            tenant_id="tenant-a",
            project_id="project-a",
            question="Q",
            answer="A longer deterministic answer.",
        )
    )

    await repo.set_running(job.job_id)

    with pytest.raises(Exception):
        await repo.set_running(job.job_id)
