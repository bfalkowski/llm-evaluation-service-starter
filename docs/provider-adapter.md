# Provider Adapter Boundary

The service currently uses a deterministic mock evaluator. That keeps tests local and
repeatable while the API, persistence, queue, and deployment boundaries take shape.

A real model provider should be added behind an adapter boundary rather than directly
inside API routes or job orchestration code.

## Current Shape

```text
EvaluationJobService
  -> Evaluator
  -> score_mock_response
```

`EvaluationJobService` owns job lifecycle behavior:

- create job
- enqueue job
- mark running
- call evaluator
- mark succeeded or failed
- write audit events

`Evaluator` owns scoring behavior:

- timeout policy
- retry policy
- tracing boundary
- call to the mock scoring function today
- future provider call tomorrow

## Target Shape

When adding a real provider, keep the job service unchanged:

```text
EvaluationJobService
  -> Evaluator
  -> ProviderAdapter
  -> model provider API
```

The adapter should translate between local domain models and provider-specific request
or response formats.

## Adapter Responsibilities

A provider adapter should own:

- provider request construction
- provider authentication
- provider timeout settings
- provider retryable error classification
- provider response parsing
- score and justification extraction
- provider-specific metrics metadata

It should not own:

- HTTP route behavior
- job state transitions
- tenant authorization
- database writes
- queue acknowledgement
- prompt/answer logging

## Error Handling

Provider errors should be classified before reaching job lifecycle code.

Useful categories:

- timeout
- rate limited
- transient provider failure
- invalid provider response
- provider authentication failure
- unsupported model or configuration

The job service can then store safe user-facing failure messages without leaking provider
internals.

## Observability

Provider spans and logs should follow `docs/observability-data-safety.md`.

Safe attributes:

```text
tenant_id
project_id
job_id
provider_name
model_name
attempt
timeout_seconds
error_type
status
```

Avoid:

```text
question
answer
rubric
prompt
raw_provider_request
raw_provider_response
api_key
```

## Testing

Provider adapter tests should not call real external APIs by default.

Use:

- deterministic fake adapters
- response fixtures without sensitive content
- timeout and retry tests
- provider error classification tests

Keep the existing mock evaluator available for local tests and demos.

## Future Interface Sketch

One possible future shape:

```python
class EvaluationProvider(Protocol):
    async def score(self, request: EvaluationRequest) -> EvaluationResult:
        ...
```

Then:

```text
MockEvaluationProvider
OpenAIStyleEvaluationProvider
InternalHttpEvaluationProvider
```

Do not add this abstraction until a real second implementation exists or the evaluator
starts accumulating provider-specific branching.
