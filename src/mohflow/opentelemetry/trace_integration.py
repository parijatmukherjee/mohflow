"""
OpenTelemetry trace integration for automatic correlation of logs with
distributed traces.

This module provides seamless integration between MohFlow logging and
OpenTelemetry distributed tracing, enabling automatic correlation of log
entries with trace spans.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from contextlib import contextmanager

try:
    from opentelemetry import trace
    from opentelemetry.baggage import get_all as get_all_baggage
    from opentelemetry.sdk.trace import TracerProvider, Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION

    HAS_OPENTELEMETRY = True
except ImportError:
    HAS_OPENTELEMETRY = False


@dataclass
class TraceContext:
    """Container for trace context information."""

    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    trace_flags: Optional[str] = None
    trace_state: Optional[str] = None
    baggage: Optional[Dict[str, Any]] = None
    service_name: Optional[str] = None
    service_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert trace context to dictionary for logging."""
        context = {}

        if self.trace_id:
            context["trace_id"] = self.trace_id
        if self.span_id:
            context["span_id"] = self.span_id
        if self.trace_flags:
            context["trace_flags"] = self.trace_flags
        if self.trace_state:
            context["trace_state"] = self.trace_state
        if self.service_name:
            context["service_name"] = self.service_name
        if self.service_version:
            context["service_version"] = self.service_version

        # Add baggage items as individual fields
        if self.baggage:
            context.update(self.baggage)

        return context

    @classmethod
    def from_current_span(cls) -> "TraceContext":
        """Create TraceContext from current OpenTelemetry span."""
        if not HAS_OPENTELEMETRY:
            return cls()

        current_span = trace.get_current_span()
        if not current_span or not current_span.is_recording():
            return cls()

        span_context = current_span.get_span_context()

        # Extract trace information
        trace_id = None
        span_id = None
        trace_flags = None
        trace_state = None

        if span_context.is_valid:
            trace_id = f"{span_context.trace_id:032x}"
            span_id = f"{span_context.span_id:016x}"
            trace_flags = f"{span_context.trace_flags:02x}"

            if span_context.trace_state:
                trace_state = span_context.trace_state.to_header()

        # Get baggage
        baggage_items = get_all_baggage() if HAS_OPENTELEMETRY else {}

        # Try to get service info from resource
        service_name = None
        service_version = None

        try:
            tracer_provider = trace.get_tracer_provider()
            if hasattr(tracer_provider, "_resource"):
                resource = tracer_provider._resource
                if resource:
                    service_name = resource.attributes.get(SERVICE_NAME)
                    service_version = resource.attributes.get(SERVICE_VERSION)
        except Exception:
            pass

        return cls(
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=trace_flags,
            trace_state=trace_state,
            baggage=dict(baggage_items) if baggage_items else None,
            service_name=service_name,
            service_version=service_version,
        )


class OpenTelemetryEnricher:
    """
    Log enricher that automatically adds OpenTelemetry trace context to log
    records.

    This enricher extracts trace information from the current OpenTelemetry
    context and adds it to log records for distributed tracing correlation.
    """

    def __init__(
        self,
        include_trace_id: bool = True,
        include_span_id: bool = True,
        include_trace_flags: bool = False,
        include_trace_state: bool = False,
        include_baggage: bool = True,
        include_service_info: bool = True,
        trace_id_field: str = "trace_id",
        span_id_field: str = "span_id",
        baggage_prefix: str = "",
    ):
        """
        Initialize OpenTelemetry enricher.

        Args:
            include_trace_id: Include trace ID in logs
            include_span_id: Include span ID in logs
            include_trace_flags: Include trace flags in logs
            include_trace_state: Include trace state in logs
            include_baggage: Include baggage items in logs
            include_service_info: Include service name/version from resource
            trace_id_field: Field name for trace ID
            span_id_field: Field name for span ID
            baggage_prefix: Prefix for baggage fields
        """
        self.include_trace_id = include_trace_id
        self.include_span_id = include_span_id
        self.include_trace_flags = include_trace_flags
        self.include_trace_state = include_trace_state
        self.include_baggage = include_baggage
        self.include_service_info = include_service_info
        self.trace_id_field = trace_id_field
        self.span_id_field = span_id_field
        self.baggage_prefix = baggage_prefix

        self._otel_available = HAS_OPENTELEMETRY

    def _get_baggage_field_name(self, key: str) -> str:
        """Get the field name for a baggage key, applying prefix if
        configured."""
        return (
            f"{self.baggage_prefix}{key}"
            if self.baggage_prefix
            else key
        )

    def enrich_record(self, record: logging.LogRecord) -> logging.LogRecord:
        """Enrich log record with OpenTelemetry trace context."""
        if not self._otel_available:
            return record

        trace_context = TraceContext.from_current_span()

        # Add trace ID
        if self.include_trace_id and trace_context.trace_id:
            setattr(record, self.trace_id_field, trace_context.trace_id)

        # Add span ID
        if self.include_span_id and trace_context.span_id:
            setattr(record, self.span_id_field, trace_context.span_id)

        # Add trace flags
        if self.include_trace_flags and trace_context.trace_flags:
            setattr(record, "trace_flags", trace_context.trace_flags)

        # Add trace state
        if self.include_trace_state and trace_context.trace_state:
            setattr(record, "trace_state", trace_context.trace_state)

        # Add service information
        if self.include_service_info:
            if trace_context.service_name:
                setattr(
                    record, "otel_service_name", trace_context.service_name
                )
            if trace_context.service_version:
                setattr(
                    record,
                    "otel_service_version",
                    trace_context.service_version,
                )

        # Add baggage items
        if self.include_baggage and trace_context.baggage:
            for key, value in trace_context.baggage.items():
                field_name = self._get_baggage_field_name(key)
                setattr(record, field_name, value)

        return record

    def enrich_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich dictionary with OpenTelemetry trace context."""
        if not self._otel_available:
            return data

        trace_context = TraceContext.from_current_span()
        enriched_data = data.copy()

        # Add trace information
        if self.include_trace_id and trace_context.trace_id:
            enriched_data[self.trace_id_field] = trace_context.trace_id

        if self.include_span_id and trace_context.span_id:
            enriched_data[self.span_id_field] = trace_context.span_id

        if self.include_trace_flags and trace_context.trace_flags:
            enriched_data["trace_flags"] = trace_context.trace_flags

        if self.include_trace_state and trace_context.trace_state:
            enriched_data["trace_state"] = trace_context.trace_state

        # Add service information
        if self.include_service_info:
            if trace_context.service_name:
                enriched_data["otel_service_name"] = trace_context.service_name
            if trace_context.service_version:
                enriched_data["otel_service_version"] = (
                    trace_context.service_version
                )

        # Add baggage items
        if self.include_baggage and trace_context.baggage:
            for key, value in trace_context.baggage.items():
                field_name = self._get_baggage_field_name(key)
                enriched_data[field_name] = value

        return enriched_data


def setup_otel_logging(
    service_name: str,
    service_version: str = "1.0.0",
    endpoint: Optional[str] = None,
    exporter_type: str = "console",
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Setup OpenTelemetry tracing for the application.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        endpoint: OTLP endpoint URL (for OTLP exporter)
        exporter_type: Type of exporter ("console", "jaeger", "otlp")
        resource_attributes: Additional resource attributes

    Returns:
        True if setup was successful, False otherwise
    """
    if not HAS_OPENTELEMETRY:
        return False

    try:
        # Create resource with service information
        attributes = {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }

        if resource_attributes:
            attributes.update(resource_attributes)

        resource = Resource.create(attributes)

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Setup exporter based on type
        if exporter_type == "console":
            from opentelemetry.exporter.console import ConsoleSpanExporter

            exporter = ConsoleSpanExporter()
        elif exporter_type == "jaeger":
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter

            exporter = JaegerExporter(
                agent_host_name="localhost",
                agent_port=6831,
            )
        elif exporter_type == "otlp" and endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
        else:
            # Default to console exporter
            from opentelemetry.exporter.console import ConsoleSpanExporter

            exporter = ConsoleSpanExporter()

        # Add batch span processor
        span_processor = BatchSpanProcessor(exporter)
        tracer_provider.add_span_processor(span_processor)

        return True

    except Exception:
        return False


def get_current_trace_context() -> TraceContext:
    """Get the current OpenTelemetry trace context."""
    return TraceContext.from_current_span()


@contextmanager
def trace_correlation_middleware(operation_name: str = "log_operation"):
    """
    Context manager that creates a span for log correlation.

    This is useful for creating explicit spans around operations
    that you want to correlate with logs.
    """
    if not HAS_OPENTELEMETRY:
        yield
        return

    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span(operation_name) as span:
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise


class OpenTelemetryFilter(logging.Filter):
    """
    Logging filter that adds OpenTelemetry trace context to log records.

    This filter can be added to any handler to automatically enrich
    log records with trace information.
    """

    def __init__(self, enricher: Optional[OpenTelemetryEnricher] = None):
        super().__init__()
        self.enricher = enricher or OpenTelemetryEnricher()

    def filter(self, record: logging.LogRecord) -> bool:
        """Add OpenTelemetry context to the log record."""
        self.enricher.enrich_record(record)
        return True


# Convenience function for backward compatibility
def add_otel_context_to_logger(
    logger: logging.Logger, enricher: Optional[OpenTelemetryEnricher] = None
):
    """Add OpenTelemetry context filter to a logger."""
    otel_filter = OpenTelemetryFilter(enricher)
    logger.addFilter(otel_filter)
