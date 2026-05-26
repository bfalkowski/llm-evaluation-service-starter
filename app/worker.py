from __future__ import annotations

import asyncio
import logging
import signal

from app.core.audit import AuditRecorder
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.tracing import configure_worker_tracing
from app.services.evaluator import Evaluator
from app.services.job_service import EvaluationJobService
from app.services.queue import InMemoryJobQueue
from app.services.worker import EvaluationWorker
from app.storage.factory import build_repository

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_worker_tracing(
        settings.service_name,
        settings.otel_enabled,
        settings.otel_exporter,
        settings.otel_otlp_endpoint,
    )

    repository = await build_repository(settings)
    queue = InMemoryJobQueue()
    evaluator = Evaluator(timeout_seconds=settings.evaluator_timeout_seconds)
    audit = AuditRecorder()
    job_service = EvaluationJobService(repository, queue, evaluator, audit)
    worker = EvaluationWorker(job_service, poll_seconds=settings.worker_poll_seconds)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        loop.add_signal_handler(getattr(signal, signal_name), stop_event.set)

    worker.start()
    logger.info("worker process started")
    try:
        await stop_event.wait()
    finally:
        await worker.stop()
        await repository.close()
        logger.info("worker process stopped")


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
