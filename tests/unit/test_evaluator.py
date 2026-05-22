import pytest

from app.domain.models import EvaluationRequest
from app.services.evaluator import Evaluator


@pytest.mark.asyncio
async def test_evaluator_returns_deterministic_score() -> None:
    evaluator = Evaluator()
    request = EvaluationRequest(
        tenant_id="tenant-a",
        project_id="project-a",
        question="How does tracing help platform services?",
        answer="Tracing helps platform services explain latency and failures.",
        rubric="Mention tracing and failures.",
    )

    first = await evaluator.score(request)
    second = await evaluator.score(request)

    assert first == second
    assert 0 <= first.score <= 100
    assert first.rubric_used is True


@pytest.mark.asyncio
async def test_evaluator_handles_missing_rubric() -> None:
    evaluator = Evaluator()
    request = EvaluationRequest(
        tenant_id="tenant-a",
        project_id="project-a",
        question="What is a readiness check?",
        answer="A readiness check indicates whether a service can receive traffic.",
    )

    result = await evaluator.score(request)

    assert result.rubric_used is False
    assert result.score > 0
