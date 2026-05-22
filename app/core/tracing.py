from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from fastapi import FastAPI

OtelExporter = Literal["console", "otlp", "none"]

try:  # Optional at import time so tests can run before dev dependencies are installed.
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter,
        SimpleSpanProcessor,
        SpanExporter,
    )
except ImportError:  # pragma: no cover - exercised only in minimal environments
    trace = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    ConsoleSpanExporter = None  # type: ignore[assignment]
    SimpleSpanProcessor = None  # type: ignore[assignment]
    SpanExporter = None  # type: ignore[assignment]

try:  # Optional unless APP_OTEL_EXPORTER=otlp.
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
except ImportError:  # pragma: no cover - exercised only in minimal environments
    OTLPSpanExporter = None  # type: ignore[assignment]


def configure_tracing(
    app: FastAPI,
    service_name: str,
    enabled: bool = True,
    exporter: OtelExporter = "console",
    otlp_endpoint: str | None = None,
) -> None:
    if not enabled or exporter == "none" or trace is None or FastAPIInstrumentor is None:
        return

    span_exporter = _build_span_exporter(exporter, otlp_endpoint)
    if span_exporter is None:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health/live,/health/ready")


def _build_span_exporter(exporter: OtelExporter, otlp_endpoint: str | None) -> SpanExporter | None:
    if exporter == "console":
        return ConsoleSpanExporter()

    if exporter == "otlp":
        if OTLPSpanExporter is None:
            return None
        if otlp_endpoint:
            return OTLPSpanExporter(endpoint=otlp_endpoint)
        return OTLPSpanExporter()

    return None


def get_tracer(name: str):
    if trace is None:
        return None
    return trace.get_tracer(name)


@contextmanager
def traced_span(name: str, **attributes: object) -> Iterator[None]:
    tracer = get_tracer("app")
    if tracer is None:
        yield
        return
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield
