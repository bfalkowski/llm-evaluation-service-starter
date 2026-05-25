# llm-evaluation-service

A clean-room FastAPI starter for a small **LLM Evaluation Job Service**.

This repository provides a small AI-adjacent platform service with clean API boundaries, typed domain models, deterministic tests, async job processing, structured logging, OpenTelemetry tracing, durable job metadata, and deployable local/runtime configuration. It does not require a real model provider, external queue, auth system, or observability backend.

## Features

- FastAPI service design with versioned evaluation endpoints.
- Async job submission and processing through a replaceable in-memory queue abstraction.
- PostgreSQL-backed job repository by default, with an in-memory repository available for tests and lightweight demos.
- Explicit job state transitions: `queued`, `running`, `succeeded`, and `failed`.
- Typed application errors mapped to consistent JSON error responses.
- Structured JSON logs with request/correlation IDs.
- OpenTelemetry FastAPI instrumentation and custom spans around job creation, job processing, and scoring.
- A deterministic mock evaluator that stands in for a real LLM provider call.
- Unit and integration tests using pytest and FastAPI TestClient.
- Dockerfile, docker-compose, and basic Kubernetes manifests with liveness/readiness probes.

## Out of scope

- No real model provider integration.
- No durable external queue.
- No authentication or RBAC.
- No production audit log store.
- No migration framework such as Alembic yet.
- No metrics backend or trace collector requirement.
- No prompt/answer logging by default.

These are left out so the service stays focused and easy to adapt.

## Architecture overview

```text
app/
  main.py                 FastAPI app factory, lifespan, middleware, dependency wiring
  api/                    HTTP routes and health checks
  core/                   config, logging, tracing, errors, resilience, audit helpers
  domain/                 Pydantic models and deterministic scoring logic
  services/               evaluator, job service, in-memory queue abstraction
  storage/                repository protocol, Postgres repository, in-memory repository

tests/
  unit/                   evaluator and job transition tests
  integration/            API endpoint tests

deploy/
  docker-compose.yml      Service plus local Postgres
  k8s/                    Deployment, Service, ConfigMap, demo Postgres manifest
```

```mermaid
flowchart LR
    client["API client"] --> api["FastAPI app<br/>request ID middleware<br/>error handlers"]
    api --> routes["Evaluation routes<br/>POST /v1/evaluations<br/>GET /v1/evaluations/{job_id}"]
    api --> health["Health routes<br/>/health/live<br/>/health/ready"]

    routes --> service["Job service"]
    service --> repo["Repository interface"]
    repo --> postgres["PostgreSQL repository<br/>default runtime"]
    repo --> memory["In-memory repository<br/>tests and demos"]

    service --> queue["In-memory queue"]
    queue --> worker["Background worker"]
    worker --> evaluator["Mock evaluator"]
    evaluator --> scoring["Deterministic scoring logic"]
    worker --> repo

    api -. "structured JSON logs" .-> logs["stdout logs"]
    service -. "safe span attributes" .-> tracing["OpenTelemetry SDK"]
    evaluator -. "safe span attributes" .-> tracing
    tracing --> console["Console exporter"]
    tracing --> collector["OTLP exporter<br/>OpenTelemetry Collector"]

    audit["Audit recorder<br/>in-memory extension point"] -.-> service
```

The main flow is:

1. `POST /v1/evaluations` validates the request.
2. The job service creates a job with status `queued`.
3. The job is stored in PostgreSQL by default.
4. The job ID is placed on the in-memory queue.
5. A background worker marks it `running`, calls the mock evaluator, then marks it `succeeded` or `failed`.
6. `GET /v1/evaluations/{job_id}` returns status and result metadata.

Prompt and answer content are accepted by the service but are not returned in the default job status response.

## Storage

PostgreSQL is the default storage backend:

```bash
APP_STORAGE_BACKEND=postgres
APP_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/llm_evaluations
```

For tests or very lightweight local experiments, you can switch to in-memory storage:

```bash
APP_STORAGE_BACKEND=memory uvicorn app.main:app --reload
```

The Postgres repository creates its table on startup to keep local setup simple. Production deployments should replace that with Alembic migrations and a reviewed schema rollout process.

Run migrations against Postgres:

```bash
APP_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/llm_evaluations \
  alembic upgrade head
```

For managed deployments, set `APP_AUTO_CREATE_SCHEMA=false` and run migrations as an
explicit deployment step before starting new application pods.

## API examples

Start Postgres and the service:

```bash
cd deploy
docker compose up --build
```

Submit an evaluation:

```bash
curl -s -X POST http://localhost:8000/v1/evaluations \
  -H 'content-type: application/json' \
  -H 'x-request-id: demo-request-001' \
  -d '{
    "tenant_id": "tenant-a",
    "project_id": "project-a",
    "question": "Why is observability important for AI platform services?",
    "answer": "Observability helps teams understand latency, failures, cost, and quality behavior across AI workflows.",
    "rubric": "Mention latency, failures, or quality."
  }'
```

Example response:

```json
{
  "job_id": "00000000-0000-0000-0000-000000000000",
  "status": "queued",
  "request_id": "demo-request-001"
}
```

Retrieve a job:

```bash
curl -s 'http://localhost:8000/v1/evaluations/<job_id>?tenant_id=tenant-a'
```

List recent jobs for a tenant:

```bash
curl -s 'http://localhost:8000/v1/evaluations?tenant_id=tenant-a&limit=20'
```

Health checks:

```bash
curl -s http://localhost:8000/health/live
curl -s http://localhost:8000/health/ready
```

Swagger UI is available while the service is running:

```text
http://localhost:8000/docs
```

Export the OpenAPI spec:

```bash
python scripts/export_openapi.py
```

## Local development

Create a virtual environment and install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run Postgres locally:

```bash
cd deploy
docker compose up postgres
```

Run the service against Postgres:

```bash
APP_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/llm_evaluations \
uvicorn app.main:app --reload
```

Run the service without Postgres:

```bash
APP_STORAGE_BACKEND=memory uvicorn app.main:app --reload
```

Allow a local dashboard to call the API:

```bash
APP_CORS_ALLOWED_ORIGINS='["http://localhost:5173","http://localhost:3000"]'
```

Configure local rate limits:

```bash
APP_RATE_LIMIT_ENABLED=true
APP_RATE_LIMIT_SUBMIT_PER_MINUTE=30
APP_RATE_LIMIT_READ_PER_MINUTE=120
APP_RATE_LIMIT_LIST_PER_MINUTE=60
```

Run tests:

```bash
pytest
```

Run linting:

```bash
ruff check .
```

Run type checks:

```bash
mypy app tests
```

GitHub Actions runs the same test, lint, and type-check commands on pushes to `main` and on pull requests.

## Docker

Build and run directly against a reachable Postgres database:

```bash
docker build -t llm-evaluation-service:latest .
docker run --rm -p 8000:8000 \
  -e APP_DATABASE_URL='postgresql+asyncpg://app:app@host.docker.internal:5432/llm_evaluations' \
  llm-evaluation-service:latest
```

Run the service and Postgres together:

```bash
cd deploy
docker compose up --build
```

## Kubernetes notes

The manifests in `deploy/k8s` are basic starting points.
See `deploy/k8s/README.md` for local Kubernetes setup, image options, port-forwarding,
and cleanup commands.

For Helm-based managed Kubernetes configuration, see the companion deployment repo:
`https://github.com/bfalkowski/llm-evaluation-service-deploy`.

```bash
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.local.yaml
# Edit deploy/k8s/secret.local.yaml before applying it.

kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secret.local.yaml
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/postgres.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
```

The demo deployment includes:

- One service replica.
- Liveness probe on `/health/live`.
- Readiness probe on `/health/ready`.
- ConfigMap-driven environment variables.
- Secret-driven database connection configuration.
- A dedicated `llm-evaluation` namespace.
- Conservative CPU and memory requests/limits.
- A simple demo Postgres deployment.

For a real cluster, use managed Postgres or a properly operated database, inject Secrets from your deployment platform, add persistent volumes, ingress, TLS, service accounts, network policies, and observability collector configuration.

## Observability notes

The service emits structured JSON logs to stdout. Each request gets a request ID from `x-request-id` or a generated UUID. The request ID is included in logs and response headers.

OpenTelemetry instrumentation is enabled by default. FastAPI requests are instrumented, and custom spans are added around:

- `job.create`
- `job.process`
- `evaluation.scoring`

Span attributes include metadata such as `tenant_id`, `project_id`, `job_id`, and rubric presence. Full prompt, answer, and rubric content are not emitted into logs or traces by default because those fields may contain user data, business-sensitive data, or regulated content. A production system should make data capture explicit, governed, redacted, access-controlled, and auditable.

Tracing uses standard OpenTelemetry exporters rather than a custom exporter. The application owns meaningful span boundaries and safe attributes, while the deployment environment decides where telemetry goes.

Supported exporter modes:

```bash
APP_OTEL_ENABLED=true
APP_OTEL_EXPORTER=console  # console, otlp, or none
APP_OTEL_OTLP_ENDPOINT=http://otel-collector:4317
```

Recommended usage:

- `console` for local demos where visible spans are useful.
- `none` for quieter local development.
- `otlp` for deployment through an OpenTelemetry Collector to Jaeger, Tempo, Honeycomb, Datadog, New Relic, or another backend.

Disable tracing locally with:

```bash
APP_OTEL_EXPORTER=none uvicorn app.main:app --reload
```

## Security and governance notes

Auth is outside the scope of this starter. Production deployments should add authentication at the API boundary through FastAPI dependencies or middleware. Tenant and project authorization should be checked before creating or reading jobs.

External read endpoints require tenant context and return `404` for cross-tenant job lookups. This is an application-level guard for the starter, not a replacement for production authentication, authorization, or database-level isolation. Production deployments should derive tenant context from auth claims and may add Postgres Row-Level Security or equivalent database controls.

The service includes a small in-memory fixed-window rate limiter for local development and single-process demos. It protects job submission, job reads, and job listing with separate configurable limits. Production deployments should enforce shared rate limits at the API gateway, ingress, or with a shared backend such as Redis so limits apply consistently across replicas.

Recommended production additions:

- Authentication and authorization.
- Tenant-aware data isolation.
- Audit logging to an append-only durable store.
- Prompt/answer redaction or classification before optional logging.
- Rate limits and request size limits.
- Model provider allowlists and policy checks.
- Secrets managed by the deployment platform, not source control.
- SLOs for queue latency, provider latency, failure rate, and evaluation throughput.

## Resilience and platform patterns

`app/core/resilience.py` includes small timeout and retry helpers. The mock evaluator does not need them, but the evaluator service uses them in the same place a real provider call would be protected.

The main extension points are:

- Replace `PostgresJobRepository` with DynamoDB, Redis, or another durable store if the workload requires it.
- Replace `InMemoryJobQueue` with SQS, Kafka, Celery, Dramatiq, Arq, or another queue/worker system.
- Replace `Evaluator.score` with a real provider adapter.
- Replace `AuditRecorder` with a durable audit event writer.
- Add auth/RBAC as dependencies on the route layer.

## Production Extensions

Common production additions include:

1. Alembic migrations instead of startup schema creation.
2. Durable queue with retry/dead-letter behavior.
3. AuthN/AuthZ and tenant-aware access checks.
4. Real model provider adapter with request budgets, rate-limit handling, and circuit breakers.
5. Metrics export for queue depth, job latency, scoring latency, provider errors, and cost signals.
6. Trace collector integration instead of console span export.
7. CI pipeline running tests, linting, type checks, image build, and vulnerability scanning.
8. Deployment overlays for local, staging, and production environments.
9. Explicit prompt/answer retention policy and governance controls.
