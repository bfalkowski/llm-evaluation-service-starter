from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import FastAPI

try:  # Optional at import time so tests can run before dev dependencies are installed.
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
except ImportError:  # pragma: no cover - exercised only in minimal environments
    trace = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    ConsoleSpanExporter = None  # type: ignore[assignment]
    SimpleSpanProcessor = None  # type: ignore[assignment]


def configure_tracing(app: FastAPI, service_name: str, enabled: bool = True) -> None:
    if not enabled or trace is None or FastAPIInstrumentor is None:
        return
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health/live,/health/ready")


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
