# AGENTS.md

Guidance for AI coding agents working in this repository.

## Clean-room constraints

- Do not use or imitate proprietary employer code, internal package names, confidential architecture, or company-specific patterns.
- Keep the project generic and suitable for a public GitHub portfolio repository.
- Do not introduce secrets, credentials, API keys, private URLs, or private dataset references.

## Coding style

- Keep code simple, typed, and explicit.
- Prefer clear names over clever abstractions.
- Keep functions small and behavior easy to explain in an interview.
- Avoid adding external dependencies unless the benefit is obvious and documented.
- Do not turn this template into a large framework.

## Behavior changes

- Add or update tests for meaningful behavior changes.
- Keep tests deterministic and local-only.
- Tests should default to the in-memory repository. Do not require Postgres, a queue, model provider, auth provider, or observability backend for tests.

## Observability and data handling

- Preserve structured JSON logging.
- Preserve request/correlation ID behavior.
- Do not log prompt, answer, or rubric content by default.
- Do not emit prompt, answer, or rubric content into traces by default.
- Span attributes should use metadata such as tenant_id, project_id, job_id, and status.

## Intended extension points

- Database: PostgreSQL is the default runtime repository. Use the repository interface when changing persistence behavior, and keep the in-memory repository available for tests.
- Real queue: replace `services/queue.py` with a durable queue adapter.
- Real model provider: replace the mock operation in `services/evaluator.py`.
- Auth/RBAC: add FastAPI dependencies at the API boundary.
- Audit log: replace the in-memory audit recorder with a durable append-only store.

- Do not add custom OpenTelemetry exporters unless there is a specific, documented need. Prefer standard console or OTLP export.
