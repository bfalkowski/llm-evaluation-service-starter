from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.health import router as health_router
from app.api.routes import router as evaluation_router
from app.core.audit import AuditRecorder
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler, unhandled_error_handler
from app.core.logging import configure_logging, new_request_id, request_id_var
from app.core.tracing import configure_tracing
from app.services.evaluator import Evaluator
from app.services.job_service import EvaluationJobService
from app.services.queue import InMemoryJobQueue
from app.storage.base import JobRepository
from app.storage.in_memory import InMemoryJobRepository

logger = logging.getLogger(__name__)


async def build_repository(settings) -> JobRepository:
    if settings.storage_backend == "memory":
        return InMemoryJobRepository()
    if settings.storage_backend == "postgres":
        from app.storage.postgres import PostgresJobRepository

        repository = PostgresJobRepository(settings.database_url)
        await repository.init_schema()
        return repository
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", new_request_id())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            request_id_var.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    repository = await build_repository(settings)
    queue = InMemoryJobQueue()
    evaluator = Evaluator(timeout_seconds=settings.evaluator_timeout_seconds)
    audit = AuditRecorder()
    job_service = EvaluationJobService(repository, queue, evaluator, audit)

    app.state.repository = repository
    app.state.queue = queue
    app.state.evaluator = evaluator
    app.state.audit = audit
    app.state.job_service = job_service

    queue.start(job_service.process)
    logger.info("service started")
    try:
        yield
    finally:
        await queue.stop()
        await repository.close()
        logger.info("service stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="LLM Evaluation Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(health_router)
    app.include_router(evaluation_router)
    configure_tracing(app, settings.service_name, settings.otel_enabled)
    return app


app = create_app()
