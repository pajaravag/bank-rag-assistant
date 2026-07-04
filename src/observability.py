"""Tracing setup: ships OpenTelemetry spans to a Phoenix container.

Disabled by default (PHOENIX_ENABLED=false) — spans become no-ops and
the system runs identically without any collector. When enabled, every
chat turn appears in the Phoenix UI as a nested trace:
chat -> condense_query -> retrieve -> generate.
"""

from __future__ import annotations

import logging

from src.config import Settings

logger = logging.getLogger(__name__)


def setup_tracing(settings: Settings) -> None:
    if not settings.phoenix_enabled:
        logger.info("Tracing disabled (PHOENIX_ENABLED=false)")
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": "bank-rag-assistant"})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint))
    )
    trace.set_tracer_provider(provider)
    logger.info("Tracing enabled -> %s", settings.otel_exporter_endpoint)
