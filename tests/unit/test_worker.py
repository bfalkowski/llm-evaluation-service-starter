import asyncio

import pytest

from app.core.audit import AuditRecorder
from app.domain.models import EvaluationRequest, JobStatus
from app.services.evaluator import Evaluator
from app.services.job_service import EvaluationJobService
from app.services.queue import InMemoryJobQueue
from app.services.worker import EvaluationWorker
from app.storage.in_memory import InMemoryJobRepository


@pytest.mark.asyncio
async def test_worker_claims_and_processes_queued_jobs() -> None:
    repo = InMemoryJobRepository()
    service = EvaluationJobService(repo, InMemoryJobQueue(), Evaluator(), AuditRecorder())
    worker = EvaluationWorker(service, poll_seconds=0.01, stale_job_seconds=300)
    job = await service.submit(
        EvaluationRequest(
            tenant_id="tenant-a",
            project_id="project-a",
            question="Q",
            answer="A useful answer mentions latency and failures.",
        )
    )

    worker.start()
    try:
        for _ in range(100):
            updated = await service.get(job.job_id)
            if updated.status == JobStatus.SUCCEEDED:
                break
            await asyncio.sleep(0.01)
    finally:
        await worker.stop()

    updated = await service.get(job.job_id)
    assert updated.status == JobStatus.SUCCEEDED
    assert updated.result is not None
