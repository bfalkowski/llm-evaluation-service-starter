# Operations Runbook

This runbook covers common operational checks for the service in Docker or Kubernetes.
Commands use the example Kubernetes namespace from the starter manifests:

```text
llm-evaluation
```

Adjust namespace, release name, and image tag for your environment.

## Quick Health Checks

Local or port-forwarded:

```bash
curl -s http://localhost:8000/health/live
curl -s http://localhost:8000/health/ready
curl -s http://localhost:8000/metrics
```

Kubernetes:

```bash
kubectl -n llm-evaluation get pods
kubectl -n llm-evaluation rollout status deployment/llm-evaluation-service
kubectl -n llm-evaluation logs deployment/llm-evaluation-service
```

`/health/live` only checks that the process is alive. `/health/ready` checks whether the
repository dependency is healthy.

`/metrics` returns Prometheus-compatible text metrics for request counts, request
latency, job status counts, scoring latency, and stale worker recovery counts.

## Service Is Not Ready

Symptoms:

- `/health/live` returns `200`
- `/health/ready` returns `503`
- readiness probe fails

Likely causes:

- Postgres is unavailable
- `APP_DATABASE_URL` is wrong
- network policy blocks database traffic
- migration has not run
- credentials are invalid

Checks:

```bash
kubectl -n llm-evaluation describe pod -l app=llm-evaluation-service
kubectl -n llm-evaluation logs deployment/llm-evaluation-service
kubectl -n llm-evaluation get secret llm-evaluation-service-secrets
```

For managed deployments, confirm migrations have run:

```bash
APP_DATABASE_URL=<managed-postgres-connection-url> alembic upgrade head
```

## Jobs Are Stuck In `queued`

Current local/starter shape:

- jobs are processed by an in-process worker inside the API pod
- the queue is in-memory

Likely causes:

- worker task did not start
- API pod restarted and in-memory queue was lost
- evaluator is hanging or timing out
- multiple pods are being used with the in-memory queue model

Checks:

```bash
kubectl -n llm-evaluation logs deployment/llm-evaluation-service
curl -s 'http://localhost:8000/v1/evaluations?tenant_id=<tenant-id>'
```

Mitigation:

- restart the deployment for local/demo environments
- keep one replica while using the in-memory queue
- move to a durable queue before scaling API and worker independently

See `docs/api-worker-split.md` for the production-shaped queue and worker model.

## Jobs Are Failing

Symptoms:

- job status moves to `failed`
- logs contain `evaluation job failed`

Likely causes:

- evaluator timeout
- provider adapter error when a real provider is added
- invalid provider response
- database write failure while recording result

Checks:

```bash
kubectl -n llm-evaluation logs deployment/llm-evaluation-service
curl -s 'http://localhost:8000/v1/evaluations/<job-id>?tenant_id=<tenant-id>'
```

Operational logs should include `job_id`, `tenant_id`, and `project_id` where available,
but should not include prompt, answer, or rubric content.

## Postgres Is Unavailable

Symptoms:

- readiness fails
- status/list routes may fail
- logs show SQLAlchemy or asyncpg connection errors

Checks:

```bash
kubectl -n llm-evaluation get pods
kubectl -n llm-evaluation describe service postgres
kubectl -n llm-evaluation logs deployment/postgres
```

For managed Postgres:

- confirm credentials
- confirm TLS requirements
- confirm network access from the cluster
- confirm database name and user permissions
- confirm migrations have run

## OTLP Export Is Failing

Symptoms:

- application works, but traces do not appear in the backend
- logs may show OTLP exporter connection errors

Checks:

```bash
kubectl -n llm-evaluation get service otel-collector
kubectl -n llm-evaluation get pods
kubectl -n llm-evaluation logs deployment/llm-evaluation-service
```

Mitigation:

- set `APP_OTEL_EXPORTER=console` for local debugging
- set `APP_OTEL_EXPORTER=none` if trace export noise blocks local work
- confirm `APP_OTEL_OTLP_ENDPOINT` points at a reachable collector or managed endpoint

See `docs/otlp-collector.md`.

## Rate Limits Are Too Aggressive

The current rate limiter is in-memory and per process. It is suitable for local demos,
not coordinated multi-replica production enforcement.

Relevant settings:

```text
APP_RATE_LIMIT_ENABLED
APP_RATE_LIMIT_SUBMIT_PER_MINUTE
APP_RATE_LIMIT_READ_PER_MINUTE
APP_RATE_LIMIT_LIST_PER_MINUTE
```

Mitigation:

- increase the relevant limit
- disable rate limiting in local development
- use gateway, ingress, or shared-store rate limiting for production

## Bad Image Was Deployed

If using Helm:

```bash
helm history llm-evaluation-service --namespace llm-evaluation
helm rollback llm-evaluation-service <revision> --namespace llm-evaluation
```

If using raw Kubernetes manifests:

```bash
kubectl -n llm-evaluation rollout history deployment/llm-evaluation-service
kubectl -n llm-evaluation rollout undo deployment/llm-evaluation-service
```

Prefer immutable image tags for managed deployments so rollbacks are reproducible.

## Useful Debug Commands

```bash
kubectl -n llm-evaluation describe deployment llm-evaluation-service
kubectl -n llm-evaluation describe pod -l app=llm-evaluation-service
kubectl -n llm-evaluation logs deployment/llm-evaluation-service --tail=100
kubectl -n llm-evaluation get events --sort-by=.lastTimestamp
kubectl -n llm-evaluation port-forward service/llm-evaluation-service 8000:80
```

## Escalation Notes

Before collecting request payloads for debugging, review
`docs/observability-data-safety.md`. Prefer request IDs, job IDs, tenant/project IDs,
status, timing, and error type over raw prompt or answer content.
