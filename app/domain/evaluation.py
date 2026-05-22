from __future__ import annotations

from app.domain.models import EvaluationRequest, EvaluationResult


def score_mock_response(request: EvaluationRequest) -> EvaluationResult:
    """Deterministic mock scoring for portfolio/demo use.

    This intentionally avoids calling a model provider. It rewards non-empty,
    reasonably complete answers and small rubric alignment signals.
    """
    answer = request.answer.strip()
    question_terms = _significant_terms(request.question)
    answer_terms = _significant_terms(answer)

    length_score = min(len(answer) // 8, 40)
    overlap_score = min(len(question_terms & answer_terms) * 10, 40)
    rubric_bonus = 10 if request.rubric and _has_any_overlap(request.rubric, answer) else 0
    clarity_bonus = 10 if "." in answer or "\n" in answer else 0

    score = max(0, min(100, length_score + overlap_score + rubric_bonus + clarity_bonus))
    justification = (
        "Mock evaluation score based on answer length, question-term overlap, "
        "basic clarity signals, and optional rubric overlap."
    )
    return EvaluationResult(score=score, justification=justification, rubric_used=request.rubric is not None)


def _significant_terms(text: str) -> set[str]:
    stop_words = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "for", "on", "with"}
    return {token.lower().strip(".,!?;:()[]{}\"'") for token in text.split() if len(token) > 3} - stop_words


def _has_any_overlap(left: str, right: str) -> bool:
    return bool(_significant_terms(left) & _significant_terms(right))
