from __future__ import annotations

import asyncio
import logging

from app.services.job_service import EvaluationJobService

logger = logging.getLogger(__name__)


class EvaluationWorker:
    def __init__(self, job_service: EvaluationJobService, *, poll_seconds: float) -> None:
        self.job_service = job_service
        self.poll_seconds = poll_seconds
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
                claimed = await self.job_service.repository.claim_next_queued()
                if claimed is None:
                    await asyncio.sleep(self.poll_seconds)
                    continue

                await self.job_service.process_claimed(claimed)
        finally:
            logger.info("evaluation worker stopped")
