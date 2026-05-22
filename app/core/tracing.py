from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer
from opentelemetry.util.types import AttributeValue

OtelExporter = Literal["console", "otlp", "none"]
ActiveOtelExporter = Literal["console", "otlp"]


def configure_tracing(
    app: FastAPI,
    service_name: str,
    enabled: bool = True,
    exporter: OtelExporter = "console",
    otlp_endpoint: str | None = None,
) -> None:
    if not enabled or exporter == "none":
        return

    span_exporter = _build_span_exporter(exporter, otlp_endpoint)
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health/live,/health/ready")


def _build_span_exporter(exporter: ActiveOtelExporter, otlp_endpoint: str | None) -> SpanExporter:
    if exporter == "console":
        return ConsoleSpanExporter()

    if exporter == "otlp":
        if otlp_endpoint:
            return OTLPSpanExporter(endpoint=otlp_endpoint)
        return OTLPSpanExporter()

    raise ValueError(f"Unsupported OpenTelemetry exporter: {exporter}")


def get_tracer(name: str) -> Tracer:
    return trace.get_tracer(name)


@contextmanager
def traced_span(name: str, **attributes: AttributeValue | None) -> Iterator[None]:
    tracer = get_tracer("app")
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        yield
