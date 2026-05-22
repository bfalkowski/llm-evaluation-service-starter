import asyncio
from uuid import UUID, uuid4

import pytest

from app.services.queue import InMemoryJobQueue


@pytest.mark.asyncio
async def test_stop_waits_for_in_flight_job() -> None:
    queue = InMemoryJobQueue()
    job_id = uuid4()
    started = asyncio.Event()
    finish = asyncio.Event()
    processed: list[UUID] = []

    async def handler(current_job_id: UUID) -> None:
        started.set()
        await finish.wait()
        processed.append(current_job_id)

    queue.start(handler)
    await queue.enqueue(job_id)
    await started.wait()

    stop_task = asyncio.create_task(queue.stop())
    await asyncio.sleep(0)

    assert not stop_task.done()

    finish.set()
    await stop_task

    assert processed == [job_id]
