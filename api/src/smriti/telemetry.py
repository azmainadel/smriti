"""OpenTelemetry tracing across API, workflow steps and model calls.

Active only when the `otel` extra is installed and OTEL_EXPORTER_OTLP_ENDPOINT is set;
otherwise every span is a no-op, so the core install has no tracing dependency.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_tracer: Any = None


def setup_tracing(service: str, app: Any = None) -> None:
    global _tracer
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("smriti")
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    if _tracer is None:
        yield
        return
    with _tracer.start_as_current_span(name) as s:
        for key, value in attributes.items():
            s.set_attribute(key, value)
        yield
