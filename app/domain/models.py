from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvaluationRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=10_000)
    answer: str = Field(min_length=1, max_length=20_000)
    rubric: str | None = Field(default=None, max_length=10_000)


class EvaluationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    justification: str
    rubric_used: bool


class EvaluationJob(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    job_id: UUID
    tenant_id: str
    project_id: str
    status: JobStatus
    request: EvaluationRequest
    result: EvaluationResult | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def public_dict(self) -> dict[str, Any]:
        # Avoid returning the full prompt/answer in status responses by default.
        data = self.model_dump(exclude={"request": {"question", "answer"}})
        return data


class ErrorResponse(BaseModel):
    error: dict[str, str]
