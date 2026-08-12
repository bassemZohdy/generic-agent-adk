"""Optional OpenTelemetry setup for local ADK observability."""

from __future__ import annotations

import os
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def configure_telemetry() -> trace.Tracer:
    """Configure OTLP only when an endpoint is supplied; otherwise no-op."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint and not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": os.getenv(
                        "OTEL_SERVICE_NAME", "basic-adk-agent"
                    ),
                    "service.version": "0.1.0",
                }
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(provider)
    return trace.get_tracer("basic_agent")


tracer = configure_telemetry()


def invocation_attributes(invocation_context: Any) -> dict[str, str]:
    """Return stable low-cardinality attributes for an ADK invocation span."""
    return {
        "adk.invocation_id": str(invocation_context.invocation_id),
        "adk.app_name": str(getattr(invocation_context, "app_name", "basic_agent")),
    }
