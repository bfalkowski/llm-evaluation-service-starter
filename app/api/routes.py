from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

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


@router.post(
    "/evaluations",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmitEvaluationResponse,
)
async def submit_evaluation(
    payload: EvaluationRequest,
    request: Request,
) -> SubmitEvaluationResponse:
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
    service = get_job_service(request)
    jobs = await service.list_recent(tenant_id=tenant_id, project_id=project_id, limit=limit)
    return EvaluationListResponse(
        jobs=[job.to_summary() for job in jobs],
        request_id=request.state.request_id,
    )


@router.get("/evaluations/{job_id}", response_model=EvaluationJobResponse)
async def get_evaluation(job_id: UUID, request: Request) -> EvaluationJobResponse:
    service = get_job_service(request)
    job = await service.get(job_id)
    return job.to_response(request.state.request_id)
