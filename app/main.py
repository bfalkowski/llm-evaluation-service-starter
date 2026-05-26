from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.api.health import router as health_router
from app.api.routes import router as evaluation_router
from app.core.audit import AuditRecorder
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler, unhandled_error_handler
from app.core.logging import configure_logging, new_request_id, request_id_var
from app.core.rate_limit import InMemoryRateLimiter
from app.core.tracing import configure_tracing
from app.services.evaluator import Evaluator
from app.services.job_service import EvaluationJobService
from app.services.queue import InMemoryJobQueue
from app.services.worker import EvaluationWorker
from app.storage.factory import build_repository

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
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
    rate_limiter = InMemoryRateLimiter()
    job_service = EvaluationJobService(repository, queue, evaluator, audit)
    worker = EvaluationWorker(job_service, poll_seconds=settings.worker_poll_seconds)

    app.state.repository = repository
    app.state.queue = queue
    app.state.evaluator = evaluator
    app.state.audit = audit
    app.state.rate_limiter = rate_limiter
    app.state.job_service = job_service
    app.state.worker = worker

    if settings.process_role == "combined":
        queue.start(job_service.process)
    logger.info("service started", extra={"process_role": settings.process_role})
    try:
        yield
    finally:
        await queue.stop()
        await worker.stop()
        await repository.close()
        logger.info("service stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="LLM Evaluation Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type", "x-request-id"],
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(health_router)
    app.include_router(evaluation_router)
    configure_tracing(
        app,
        settings.service_name,
        settings.otel_enabled,
        settings.otel_exporter,
        settings.otel_otlp_endpoint,
    )
    return app


app = create_app()
