from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request, status

from app.domain.models import EvaluationRequest
from app.services.job_service import EvaluationJobService

router = APIRouter(prefix="/v1", tags=["evaluations"])


def get_job_service(request: Request) -> EvaluationJobService:
    return cast(EvaluationJobService, request.app.state.job_service)


@router.post("/evaluations", status_code=status.HTTP_202_ACCEPTED)
async def submit_evaluation(payload: EvaluationRequest, request: Request) -> dict[str, object]:
    service = get_job_service(request)
    job = await service.submit(payload)
    return {
        "job_id": str(job.job_id),
        "status": job.status,
        "request_id": request.state.request_id,
    }


@router.get("/evaluations/{job_id}")
async def get_evaluation(job_id: UUID, request: Request) -> dict[str, object]:
    service = get_job_service(request)
    job = await service.get(job_id)
    response = job.public_dict()
    response["request_id"] = request.state.request_id
    return response
