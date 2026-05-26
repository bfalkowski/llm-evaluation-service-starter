from __future__ import annotations

import logging
from uuid import UUID, uuid4

from app.core.audit import AuditRecorder
from app.core.tracing import traced_span
from app.domain.models import EvaluationJob, EvaluationRequest, JobStatus
from app.services.evaluator import Evaluator
from app.services.queue import InMemoryJobQueue
from app.storage.base import JobRepository

logger = logging.getLogger(__name__)


class EvaluationJobService:
    def __init__(
        self,
        repository: JobRepository,
        queue: InMemoryJobQueue,
        evaluator: Evaluator,
        audit: AuditRecorder,
    ) -> None:
        self.repository = repository
        self.queue = queue
        self.evaluator = evaluator
        self.audit = audit

    async def submit(self, request: EvaluationRequest) -> EvaluationJob:
        job = EvaluationJob(
            job_id=uuid4(),
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            status=JobStatus.QUEUED,
            request=request,
        )
        with traced_span(
            "job.create",
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            job_id=str(job.job_id),
        ):
            await self.repository.create(job)
            await self.queue.enqueue(job.job_id)
            self.audit.record(
                event_type="evaluation.job_queued",
                tenant_id=job.tenant_id,
                project_id=job.project_id,
                job_id=str(job.job_id),
            )
        return job

    async def get(self, job_id: UUID) -> EvaluationJob:
        return await self.repository.get(job_id)

    async def get_for_tenant(self, job_id: UUID, tenant_id: str) -> EvaluationJob:
        return await self.repository.get_for_tenant(job_id, tenant_id)

    async def list_recent(
        self,
        *,
        tenant_id: str,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[EvaluationJob]:
        return await self.repository.list_recent(
            tenant_id=tenant_id,
            project_id=project_id,
            limit=limit,
        )

    async def process(self, job_id: UUID) -> None:
        job = await self.repository.get(job_id)
        with traced_span(
            "job.process",
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            job_id=str(job_id),
        ):
            try:
                await self.repository.set_running(job_id)
                self.audit.record(
                    event_type="evaluation.job_running",
                    tenant_id=job.tenant_id,
                    project_id=job.project_id,
                    job_id=str(job_id),
                )
                result = await self.evaluator.score(job.request)
                updated = await self.repository.set_succeeded(job_id, result)
                self.audit.record(
                    event_type="evaluation.job_succeeded",
                    tenant_id=updated.tenant_id,
                    project_id=updated.project_id,
                    job_id=str(job_id),
                    score=result.score,
                )
                logger.info(
                    "evaluation job succeeded",
                    extra={
                        "tenant_id": updated.tenant_id,
                        "project_id": updated.project_id,
                        "job_id": str(job_id),
                    },
                )
            except Exception as exc:
                await self._record_failure(job, "Evaluation failed.", exc)
                logger.exception("evaluation job failed", extra={"job_id": str(job_id)})
                raise

    async def process_claimed(self, job: EvaluationJob) -> None:
        with traced_span(
            "job.process",
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            job_id=str(job.job_id),
        ):
            try:
                self.audit.record(
                    event_type="evaluation.job_running",
                    tenant_id=job.tenant_id,
                    project_id=job.project_id,
                    job_id=str(job.job_id),
                )
                result = await self.evaluator.score(job.request)
                updated = await self.repository.set_succeeded(job.job_id, result)
                self.audit.record(
                    event_type="evaluation.job_succeeded",
                    tenant_id=updated.tenant_id,
                    project_id=updated.project_id,
                    job_id=str(job.job_id),
                    score=result.score,
                )
                logger.info(
                    "evaluation job succeeded",
                    extra={
                        "tenant_id": updated.tenant_id,
                        "project_id": updated.project_id,
                        "job_id": str(job.job_id),
                    },
                )
            except Exception as exc:
                await self._record_failure(job, "Evaluation failed.", exc)
                logger.exception("evaluation job failed", extra={"job_id": str(job.job_id)})
                raise

    async def _record_failure(
        self,
        job: EvaluationJob,
        message: str,
        original_error: Exception,
    ) -> None:
        try:
            await self.repository.set_failed(job.job_id, message)
            self.audit.record(
                event_type="evaluation.job_failed",
                tenant_id=job.tenant_id,
                project_id=job.project_id,
                job_id=str(job.job_id),
            )
        except Exception:
            logger.exception(
                "failed to persist evaluation job failure",
                extra={"job_id": str(job.job_id), "original_error": repr(original_error)},
            )
