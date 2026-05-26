from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from app.core.metrics import record_queue_depth

logger = logging.getLogger(__name__)

JobHandler = Callable[[UUID], Awaitable[None]]


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[UUID | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def enqueue(self, job_id: UUID) -> None:
        await self._queue.put(job_id)
        record_queue_depth(self._queue.qsize())

    def start(self, handler: JobHandler) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(handler))

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            await self._queue.put(None)
            await self._task

    async def _run(self, handler: JobHandler) -> None:
        while not self._stopping.is_set():
            job_id = await self._queue.get()
            try:
                if job_id is None:
                    return
                await handler(job_id)
            except Exception:
                logger.exception("background job handler failed", extra={"job_id": str(job_id)})
            finally:
                self._queue.task_done()
                record_queue_depth(self._queue.qsize())

    async def join(self) -> None:
        await self._queue.join()
