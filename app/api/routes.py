from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from app.core.config import get_settings
from app.core.errors import BadRequestError
from app.core.rate_limit import InMemoryRateLimiter, client_key
from app.domain.models import (
    EvaluationJobResponse,
    EvaluationListResponse,
    EvaluationRequest,
    SubmitEvaluationResponse,
)
from app.services.job_service import EvaluationJobService

router = APIRouter(prefix="/v1", tags=["evaluations"])


def get_job_service(request: Request) -> EvaluationJobService:
    return cast(EvaluationJobService, request.app.state.job_service)


def check_rate_limit(
    request: Request,
    *,
    route_name: str,
    limit: int,
    tenant_id: str | None = None,
) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    limiter = cast(InMemoryRateLimiter, request.app.state.rate_limiter)
    limiter.check(client_key(request, route_name, tenant_id), limit)


@router.post(
    "/evaluations",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmitEvaluationResponse,
)
async def submit_evaluation(
    payload: EvaluationRequest,
    request: Request,
) -> SubmitEvaluationResponse:
    settings = get_settings()
    check_rate_limit(
        request,
        route_name="submit_evaluation",
        limit=settings.rate_limit_submit_per_minute,
        tenant_id=payload.tenant_id,
    )
    service = get_job_service(request)
    job = await service.submit(payload)
    return SubmitEvaluationResponse(
        job_id=job.job_id,
        status=job.status,
        request_id=request.state.request_id,
    )


@router.get("/evaluations", response_model=EvaluationListResponse)
async def list_evaluations(
    request: Request,
    tenant_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    project_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvaluationListResponse:
    if tenant_id is None:
        raise BadRequestError("tenant_id is required.")

    settings = get_settings()
    check_rate_limit(
        request,
        route_name="list_evaluations",
        limit=settings.rate_limit_list_per_minute,
        tenant_id=tenant_id,
    )
    service = get_job_service(request)
    jobs = await service.list_recent(tenant_id=tenant_id, project_id=project_id, limit=limit)
    return EvaluationListResponse(
        jobs=[job.to_summary() for job in jobs],
        request_id=request.state.request_id,
    )


@router.get("/evaluations/{job_id}", response_model=EvaluationJobResponse)
async def get_evaluation(job_id: UUID, request: Request) -> EvaluationJobResponse:
    tenant_id = request.query_params.get("tenant_id")
    if tenant_id is None:
        raise BadRequestError("tenant_id is required.")

    settings = get_settings()
    check_rate_limit(
        request,
        route_name="get_evaluation",
        limit=settings.rate_limit_read_per_minute,
        tenant_id=tenant_id,
    )
    service = get_job_service(request)
    job = await service.get_for_tenant(job_id, tenant_id)
    return job.to_response(request.state.request_id)
