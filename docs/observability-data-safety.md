# Observability Data Safety

This service accepts evaluation content that may include user data, business-sensitive
data, or regulated data. Operational telemetry should help operators understand service
behavior without copying that content into logs or traces by default.

## Default Policy

Logs and traces may include operational metadata:

- `request_id`
- `tenant_id`
- `project_id`
- `job_id`
- job status
- route, method, and status code
- timing, retry, timeout, and error metadata
- whether an optional rubric was present

Logs and traces should not include these fields by default:

- question or prompt text
- answer text
- rubric text
- provider raw responses
- authentication tokens
- database URLs or credentials
- full request or response bodies

## Product API Versus Operational Telemetry

Avoiding content in logs and traces does not prevent the product from showing that
content.

User-facing APIs and UI views may return evaluation details to an authorized caller when
the product needs that workflow. Operational telemetry is different: it is often copied
to centralized systems, retained for longer periods, searched by broader audiences, and
sampled or exported across tools.

The intended boundary is:

- Product/API layer: may expose evaluation content through explicit, authorized endpoints.
- Logs/traces: default to metadata that explains behavior without exposing content.

## Adding Log Fields Or Span Attributes

Before adding a new log field or span attribute, ask:

1. Is this needed to operate the service?
2. Could the value contain user-provided content?
3. Could the value identify a person, customer, account, or private workflow?
4. Does the same debugging value exist as safer metadata?
5. Should this be sampled, redacted, hashed, or omitted?

Prefer stable identifiers and state:

```text
job_id
tenant_id
project_id
status
request_id
duration_ms
error_type
```

Avoid raw content:

```text
question
answer
rubric
prompt
provider_response
```

## Detail Endpoints

The service exposes a detail endpoint that can show the submitted question, answer, and
rubric to the tenant that owns the job. This is an explicit product API workflow, not a
reason to mine logs or traces for content.

Endpoint shape:

```text
GET /v1/evaluations/{job_id}/details
```

The current starter requires `tenant_id` and hides cross-tenant jobs with `404`. A
production system should replace query-parameter tenant context with authenticated
tenant/user authorization and should review retention, audit, and redaction expectations.

## Production Considerations

Before enabling richer telemetry or content capture, define:

- data retention windows
- tenant isolation guarantees
- access controls for observability tools
- redaction rules
- sampling policies
- audit requirements
- incident response procedures for accidental capture

The default implementation should stay conservative until those controls exist.
