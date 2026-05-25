# API And Worker Split

The current service processes evaluation jobs with an in-process background worker. That
keeps local development simple and makes the job lifecycle easy to inspect.

For a managed Kubernetes deployment, the natural next shape is:

```text
API deployment
  -> durable queue
  -> worker deployment
  -> managed Postgres
```

## Current Shape

Today, the FastAPI process owns both API traffic and background job processing:

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
- multiple API replicas would each have their own in-memory queue

## Target Production Shape

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

The current `InMemoryJobQueue` is intentionally small. A durable queue adapter should
preserve the same conceptual contract:

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

A conservative path:

1. Keep the current in-process worker for local development.
2. Introduce a queue protocol around the current in-memory queue.
3. Add a worker entrypoint that can process queue messages without serving HTTP.
4. Add a durable queue adapter.
5. Add a second worker Deployment in Helm.
6. Keep tests using the in-memory queue by default.

This keeps the starter usable while making the managed runtime path explicit.
