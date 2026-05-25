# OTLP Collector Deployment Notes

The service can export traces through OTLP using the standard OpenTelemetry Python
exporter. The application should not know which observability backend receives those
traces. That routing belongs in deployment configuration.

## Service Configuration

Use OTLP mode when a collector or compatible backend is available:

```bash
APP_OTEL_ENABLED=true
APP_OTEL_EXPORTER=otlp
APP_OTEL_OTLP_ENDPOINT=http://otel-collector:4317
```

The endpoint should point at an OpenTelemetry Collector service, sidecar, agent, or
managed OTLP endpoint.

## Why Use A Collector

A collector keeps backend-specific concerns out of application code:

- routing traces to Jaeger, Tempo, Honeycomb, Datadog, New Relic, or another backend
- batching and retrying telemetry delivery
- adding deployment metadata
- filtering or redacting attributes
- changing observability vendors without changing app code

The service should continue using standard OpenTelemetry exporters rather than custom
exporters.

## Local Kubernetes Shape

The current starter manifests reference:

```text
http://otel-collector:4317
```

That assumes a collector Service named `otel-collector` exists in the same namespace.
The service still starts if the collector is unavailable, but trace export attempts may
fail in the background depending on exporter behavior.

For local demos, prefer one of:

```bash
APP_OTEL_EXPORTER=console
APP_OTEL_EXPORTER=none
```

Use `otlp` only when a collector is actually running.

## Managed Kubernetes Shape

In managed Kubernetes, the deployment/config repository should own collector wiring.

Possible patterns:

- namespace-level collector Deployment and Service
- node-level collector DaemonSet
- sidecar collector
- managed platform OTLP endpoint

The application values should only need:

```text
APP_OTEL_EXPORTER=otlp
APP_OTEL_OTLP_ENDPOINT=<collector-or-platform-endpoint>
```

## Data Safety

Collector configuration must preserve the data-safety policy in
`docs/observability-data-safety.md`.

Do not add processors that enrich spans with prompt, answer, rubric, raw provider
requests, raw provider responses, tokens, credentials, or full request bodies.

## Future Deployment Repo Work

The Helm deployment repo can eventually add:

- optional collector endpoint values
- example collector manifests or links to platform setup
- vendor-neutral OTLP configuration docs
- environment-specific telemetry settings

Do not add a vendor-specific collector pipeline until there is a real target backend.
