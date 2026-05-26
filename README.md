# llm-evaluation-service

A clean-room FastAPI starter for a small **LLM Evaluation Job Service**.

This repository provides a small AI-adjacent platform service with clean API boundaries, typed domain models, deterministic tests, async job processing, structured logging, demo JWT authentication, OpenTelemetry tracing, durable job metadata, and deployable local/runtime configuration. It does not require a real model provider, external queue, external auth provider, or observability backend.

Companion repositories:

- Deployment config: `https://github.com/bfalkowski/llm-evaluation-service-deploy`
- Streamlit console: `https://github.com/bfalkowski/llm-evaluation-console`

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
- Companion Streamlit console available as a separate deployable component.

## Out of scope

- No real model provider integration.
- No durable external queue.
- No production identity provider or RBAC integration.
- No production audit log store.
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

Companion deployment shape:

```text
llm-evaluation-service-starter   FastAPI API, worker, storage, telemetry
llm-evaluation-console           Streamlit operator console
llm-evaluation-service-deploy    Helm chart and environment values
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
5. A worker claims the job, records attempt metadata, calls the mock evaluator, then marks it `succeeded` or `failed`.
6. `GET /v1/evaluations/{job_id}` returns status and result metadata.

Prompt and answer content are accepted by the service but are not returned in the default job status response.

The default `combined` process role runs API traffic and in-process job processing for
local simplicity. The service also includes a worker entrypoint for split API/worker
deployments backed by repository-level queued-job claims. See `docs/api-worker-split.md`.

Split workers recover stale `running` jobs after `APP_WORKER_STALE_JOB_SECONDS` and
retry them until the job's attempt budget is exhausted.

The evaluator is intentionally mocked and deterministic. See `docs/provider-adapter.md`
for the future provider adapter boundary.

For common operational checks and rollback commands, see `docs/operations-runbook.md`.

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

## Quick local smoke test

Free stuck dev ports, start the API and Streamlit console (sibling
`llm-evaluation-console` checkout), and run a smoke test:

```bash
./scripts/local_e2e.sh
```

Open the console at `http://localhost:8501` and paste the printed demo bearer token
into the sidebar.

Stop the API, console, and free ports:

```bash
./scripts/local_e2e.sh --stop
```

API only (no Streamlit): `./scripts/local_e2e.sh --no-console`

If Docker Compose Postgres fails with a port conflict on `5432`:

```bash
./scripts/local_e2e.sh --free-postgres --stop
cd deploy && docker compose up --build
```

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

Enable demo auth for local testing:

```bash
APP_AUTH_ENABLED=true \
APP_AUTH_DEMO_SECRET=local-demo-secret \
uvicorn app.main:app --reload
```

Create a demo bearer token:

```bash
APP_AUTH_DEMO_SECRET=local-demo-secret \
python scripts/create_demo_jwt.py --tenant-id tenant-a --subject local-user
```

When auth is enabled, tenant context comes from the bearer token. The transitional
`tenant_id` body/query fields remain available only for auth-disabled local workflows.

```bash
TOKEN="<paste-token>"

curl -s -X POST http://localhost:8000/v1/evaluations \
  -H 'content-type: application/json' \
  -H "authorization: Bearer ${TOKEN}" \
  -d '{
    "project_id": "project-a",
    "question": "Why is observability important for AI platform services?",
    "answer": "Observability helps teams understand latency, failures, cost, and quality behavior across AI workflows.",
    "rubric": "Mention latency, failures, or quality."
  }'
```

Retrieve a job:

```bash
curl -s 'http://localhost:8000/v1/evaluations/<job_id>?tenant_id=tenant-a'
```

With auth enabled:

```bash
curl -s -H "authorization: Bearer ${TOKEN}" \
  'http://localhost:8000/v1/evaluations/<job_id>'
```

Retrieve full request details for a tenant-scoped job:

```bash
curl -s 'http://localhost:8000/v1/evaluations/<job_id>/details?tenant_id=tenant-a'
```

List recent jobs for a tenant:

```bash
curl -s 'http://localhost:8000/v1/evaluations?tenant_id=tenant-a&limit=20'
```

With auth enabled:

```bash
curl -s -H "authorization: Bearer ${TOKEN}" \
  'http://localhost:8000/v1/evaluations?limit=20'
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

Allow browser-based local clients to call the API:

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

Docker Compose runs the API and worker as separate containers against the same Postgres
database. The API uses `APP_PROCESS_ROLE=api`; the worker runs `python -m app.worker`.

## Kubernetes notes

The manifests in `deploy/k8s` are basic starting points.
See `deploy/k8s/README.md` for local Kubernetes setup, image options, port-forwarding,
and cleanup commands.

For Helm-based managed Kubernetes configuration, see the companion deployment repo:
`https://github.com/bfalkowski/llm-evaluation-service-deploy`.

That chart can deploy this service, optional demo Postgres, migration jobs, and the
companion Streamlit console. The console image is published from:
`https://github.com/bfalkowski/llm-evaluation-console`.

For the broader deployment roadmap, see:
`https://github.com/bfalkowski/llm-evaluation-service-deploy/blob/main/docs/roadmap.md`.

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
- Combined API/worker process role.
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

The service also exposes Prometheus-compatible text metrics at:

```bash
curl -s http://localhost:8000/metrics
```

Current metrics include HTTP request counts and latency, evaluation job status counts,
scoring latency, and stale worker job recoveries. Metrics use low-cardinality labels and
do not include prompt, answer, rubric, or request body content.

OpenTelemetry instrumentation is enabled by default. FastAPI requests are instrumented, and custom spans are added around:

- `job.create`
- `job.process`
- `evaluation.scoring`

Span attributes include metadata such as `tenant_id`, `project_id`, `job_id`, and rubric presence. Full prompt, answer, and rubric content are not emitted into logs or traces by default because those fields may contain user data, business-sensitive data, or regulated content. See `docs/observability-data-safety.md` for the data-safety policy behind that boundary.

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

See `docs/otlp-collector.md` for deployment notes around collector-based trace export.

Disable tracing locally with:

```bash
APP_OTEL_EXPORTER=none uvicorn app.main:app --reload
```

## Security and governance notes

The service includes an optional demo JWT boundary for local and portfolio workflows. Set `APP_AUTH_ENABLED=true` and provide `APP_AUTH_DEMO_SECRET` to require `Authorization: Bearer <token>` on evaluation routes. Demo tokens are HMAC-signed and can be generated with `scripts/create_demo_jwt.py`.

Production deployments should replace the demo shared-secret validator with an identity-provider-backed OIDC/JWKS validator, tenant/project authorization checks, token rotation, and platform-managed secrets. External read endpoints return `404` for cross-tenant job lookups. This is an application-level guard for the starter, not a replacement for production authorization or database-level isolation. Production deployments may add Postgres Row-Level Security or equivalent database controls.

The service includes a small in-memory fixed-window rate limiter for local development and single-process demos. It protects job submission, job reads, and job listing with separate configurable limits. Production deployments should enforce shared rate limits at the API gateway, ingress, or with a shared backend such as Redis so limits apply consistently across replicas.

Recommended production additions:

- Production authentication and authorization.
- Tenant-aware data isolation.
- Audit logging to an append-only durable store.
- Prompt/answer redaction or classification before optional logging.
- Rate limits and request size limits.
- Model provider allowlists and policy checks.
- Secrets managed by the deployment platform, not source control.
- Supply-chain scanning before image promotion.
- SLOs for queue latency, provider latency, failure rate, and evaluation throughput.

## Resilience and platform patterns

`app/core/resilience.py` includes small timeout and retry helpers. The mock evaluator does not need them, but the evaluator service uses them in the same place a real provider call would be protected.

The main extension points are:

- Replace `PostgresJobRepository` with DynamoDB, Redis, or another durable store if the workload requires it.
- Replace `InMemoryJobQueue` with SQS, Kafka, Celery, Dramatiq, Arq, or another queue/worker system.
- Replace `Evaluator.score` with a real provider adapter.
- Replace `AuditRecorder` with a durable audit event writer.
- Replace demo JWT validation with production OIDC/JWKS auth and RBAC dependencies.

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
