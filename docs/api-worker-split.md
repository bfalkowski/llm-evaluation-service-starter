# API And Worker Split

The service supports two runtime shapes:

- `combined`: API traffic and in-process job processing in one process.
- `api` plus `python -m app.worker`: separate API and worker processes sharing Postgres.

`combined` keeps local development simple. The split worker entrypoint gives managed
deployments a clearer scale boundary.

For a managed Kubernetes deployment, the natural next shape is:

```text
API deployment
  -> durable queue
  -> worker deployment
  -> managed Postgres
```

## Local Combined Shape

By default, the FastAPI process owns both API traffic and background job processing:

```text
POST /v1/evaluations
  -> create job row
  -> enqueue job_id in memory
  -> in-process worker evaluates job
  -> update job row
```

This is useful for:

- deterministic local tests
- simple Docker Compose demos
- easy debugging
- avoiding a queue dependency before the service boundary is clear

Current limitations:

- queued jobs are not durable across process restarts
- API and worker capacity cannot scale independently
- a long-running evaluation shares process resources with API traffic
- multiple `combined` API replicas would each have their own in-memory queue

## Split Worker Shape

For split deployments, the API process only creates queued job rows. A separate worker
process polls the repository, atomically claims the oldest queued job, and processes it:

```text
POST /v1/evaluations
  -> create queued job row
  -> worker claims queued job from Postgres
  -> worker evaluates job
  -> update job row
```

Run a worker process with:

```bash
APP_PROCESS_ROLE=worker python -m app.worker
```

Run API-only mode with:

```bash
APP_PROCESS_ROLE=api uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Docker Compose uses this split shape locally.

## Target Durable Queue Shape

In a production-shaped deployment, the API and worker become separate workloads:

```text
Client
  -> API Deployment
  -> Durable Queue
  -> Worker Deployment
  -> Managed Postgres
```

The API is responsible for:

- request validation
- auth/RBAC checks when added
- tenant-scoped API behavior
- creating durable job metadata
- publishing a durable queue message
- returning job IDs and status responses

The worker is responsible for:

- consuming queue messages
- moving jobs through `queued`, `running`, `succeeded`, and `failed`
- calling the evaluator/provider adapter
- applying timeout, retry, and circuit-breaker policy
- writing results and failure metadata

## Queue Boundary

The current split worker uses Postgres-backed queued-job claims. A future durable queue
adapter should preserve the same conceptual contract:

```text
enqueue(job_id)
consume job_id
acknowledge or retry
dead-letter after retry exhaustion
```

Possible adapters:

- AWS SQS
- Google Pub/Sub
- Azure Service Bus
- Redis streams
- RabbitMQ
- Celery, Dramatiq, or Arq

Do not pick a vendor-specific queue until the deployment target is known.

## Kubernetes Shape

The Helm deployment repo can eventually model this as:

```text
api Deployment
worker Deployment
shared ConfigMap
shared Secret
queue configuration
managed Postgres Secret
optional autoscaling per workload
```

API and worker replicas should scale on different signals:

- API: request rate, latency, CPU, memory
- Worker: queue depth, job age, provider latency, error rate

## Migration Path

Current status:

1. Keep the current in-process worker for local development.
2. Add a worker entrypoint that can process jobs without serving HTTP.
3. Claim queued jobs through the repository so API and worker processes can split.

Next steps:

1. Add a second worker Deployment in Helm.
2. Add a durable queue adapter when the target platform is known.
3. Keep tests using in-memory storage by default.

This keeps the starter usable while making the managed runtime path explicit.
