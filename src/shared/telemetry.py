"""Shared telemetry helpers for all mafia-ai services.

Provides three functions used at service startup:

- ``setup_tracing``   — configure OTEL TracerProvider with OTLP gRPC export
                        and auto-instrument all httpx clients.
- ``configure_loguru`` — switch loguru to JSON stdout with ``service``,
                         ``trace_id``, and ``span_id`` injected into every
                         record for log–trace correlation in Grafana.
- ``instrument_app``  — attach OTEL FastAPI middleware and expose a
                         Prometheus ``/metrics`` endpoint.

Usage (FastAPI services)::

    from shared.telemetry import configure_loguru, instrument_app, setup_tracing

    setup_tracing('my-service')
    configure_loguru('my-service')

    app = FastAPI(...)
    instrument_app(app, 'my-service')

Usage (Streamlit / non-FastAPI)::

    configure_loguru('admin')
"""

import sys
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_fastapi_instrumentator import Instrumentator


def setup_tracing(service_name: str) -> None:
    """Configure the global OTEL TracerProvider with OTLP gRPC export.

    Reads ``OTEL_EXPORTER_OTLP_ENDPOINT`` from the environment
    (defaults to ``http://localhost:4317`` per the OTEL SDK spec).
    Also patches all ``httpx`` clients for automatic outbound HTTP tracing.

    Args:
        service_name: Logical service name reported in traces.
    """
    resource = Resource.create({'service.name': service_name})
    exporter = OTLPSpanExporter()
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument()


def _make_patcher(service_name: str) -> Callable[[dict[str, Any]], None]:
    def _patcher(record: dict[str, Any]) -> None:
        record['extra']['service'] = service_name
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            record['extra']['trace_id'] = format(ctx.trace_id, '032x')
            record['extra']['span_id'] = format(ctx.span_id, '016x')
        else:
            record['extra']['trace_id'] = ''
            record['extra']['span_id'] = ''

    return _patcher


def configure_loguru(service_name: str) -> None:
    """Switch loguru to structured JSON output with OTEL trace context.

    Removes the default stderr sink and adds a JSON sink on stdout.
    Every record is extended with ``service``, ``trace_id``, and ``span_id``
    fields for log–trace correlation in Grafana / Loki.

    Args:
        service_name: Injected into every log record as ``service``.
    """
    logger.remove()
    logger.configure(patcher=_make_patcher(service_name))
    logger.add(sys.stdout, serialize=True, level='DEBUG')


def instrument_app(app: FastAPI, service_name: str) -> None:
    """Attach OTEL FastAPI tracing and a Prometheus ``/metrics`` endpoint.

    Must be called after the ``FastAPI`` instance is created.

    Args:
        app: The FastAPI application to instrument.
        service_name: Service label for Prometheus metrics.
    """
    FastAPIInstrumentor().instrument_app(app)
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
    ).instrument(app).expose(app, tags=['observability'])
