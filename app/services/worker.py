from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.metrics import record_worker_recovered_jobs
from app.services.job_service import EvaluationJobService

logger = logging.getLogger(__name__)


class EvaluationWorker:
    def __init__(
        self,
        job_service: EvaluationJobService,
        *,
        poll_seconds: float,
        stale_job_seconds: float,
    ) -> None:
        self.job_service = job_service
        self.poll_seconds = poll_seconds
        self.stale_job_seconds = stale_job_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            await self._task

    async def run(self) -> None:
        logger.info("evaluation worker started")
        try:
            while not self._stopping.is_set():
                cutoff = datetime.now(UTC) - timedelta(seconds=self.stale_job_seconds)
                recovered = await self.job_service.repository.recover_stale_running(cutoff=cutoff)
                if recovered:
                    record_worker_recovered_jobs(recovered)
                    logger.warning("recovered stale running jobs", extra={"job_count": recovered})

                claimed = await self.job_service.repository.claim_next_queued()
                if claimed is None:
                    await asyncio.sleep(self.poll_seconds)
                    continue

                await self.job_service.process_claimed(claimed)
        finally:
            logger.info("evaluation worker stopped")
