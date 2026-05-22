from __future__ import annotations

import asyncio

from app.core.resilience import retry_async, with_timeout
from app.core.tracing import traced_span
from app.domain.evaluation import score_mock_response
from app.domain.models import EvaluationRequest, EvaluationResult


class Evaluator:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def score(self, request: EvaluationRequest) -> EvaluationResult:
        async def operation() -> EvaluationResult:
            # Replace this method body with a real model provider call later.
            await asyncio.sleep(0.01)
            return score_mock_response(request)

        with traced_span(
            "evaluation.scoring",
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            rubric_present=request.rubric is not None,
        ):
            return await retry_async(lambda: with_timeout(operation(), self.timeout_seconds), attempts=2)
