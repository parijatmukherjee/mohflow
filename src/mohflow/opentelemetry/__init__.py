"""OpenTelemetry integration for MohFlow logging."""

from .trace_integration import (
    TraceContext,
    OpenTelemetryEnricher,
    setup_otel_logging,
    get_current_trace_context,
    trace_correlation_middleware,
)

from .exporters import (
    setup_jaeger_exporter,
    setup_otlp_exporter,
    setup_console_exporter,
)

from .propagators import (
    setup_trace_propagation,
    extract_trace_context,
    inject_trace_context,
)

__all__ = [
    # Trace integration
    "TraceContext",
    "OpenTelemetryEnricher",
    "setup_otel_logging",
    "get_current_trace_context",
    "trace_correlation_middleware",
    # Exporters
    "setup_jaeger_exporter",
    "setup_otlp_exporter",
    "setup_console_exporter",
    # Propagators
    "setup_trace_propagation",
    "extract_trace_context",
    "inject_trace_context",
]
