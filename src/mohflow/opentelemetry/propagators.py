"""
OpenTelemetry trace context propagation utilities.

This module provides utilities for extracting and injecting trace context
across service boundaries, enabling distributed tracing correlation.
"""

from typing import Dict, Any, Optional, Union
import logging

try:
    from opentelemetry import trace, propagate, context
    from opentelemetry.propagators.b3 import B3MultiFormat, B3SingleFormat
    from opentelemetry.propagators.jaeger import JaegerPropagator
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.propagators.composite import CompositePropagator

    HAS_OPENTELEMETRY = True
except ImportError:
    HAS_OPENTELEMETRY = False


def setup_trace_propagation(propagator_types: Optional[list] = None) -> bool:
    """
    Setup trace context propagation with specified propagators.

    Args:
        propagator_types: List of propagator types to use.
                         Supported: ["tracecontext", "b3", "b3single", "jaeger", "baggage"]
                         Default: ["tracecontext", "baggage"]

    Returns:
        True if setup successful, False otherwise
    """
    if not HAS_OPENTELEMETRY:
        return False

    if propagator_types is None:
        propagator_types = ["tracecontext", "baggage"]

    try:
        propagators = []

        for prop_type in propagator_types:
            if prop_type == "tracecontext":
                propagators.append(TraceContextTextMapPropagator())
            elif prop_type == "b3":
                propagators.append(B3MultiFormat())
            elif prop_type == "b3single":
                propagators.append(B3SingleFormat())
            elif prop_type == "jaeger":
                propagators.append(JaegerPropagator())
            elif prop_type == "baggage":
                propagators.append(W3CBaggagePropagator())

        if propagators:
            if len(propagators) == 1:
                propagate.set_global_textmap(propagators[0])
            else:
                composite = CompositePropagator(propagators)
                propagate.set_global_textmap(composite)

            return True

        return False

    except Exception:
        return False


def extract_trace_context(
    headers: Dict[str, str], propagator_types: Optional[list] = None
) -> Optional[Any]:
    """
    Extract trace context from HTTP headers or other carriers.

    Args:
        headers: Dictionary containing headers/metadata
        propagator_types: List of propagator types to try

    Returns:
        OpenTelemetry context or None if extraction failed
    """
    if not HAS_OPENTELEMETRY:
        return None

    if propagator_types is None:
        propagator_types = ["tracecontext", "baggage"]

    try:
        # Try each propagator type until one succeeds
        for prop_type in propagator_types:
            try:
                if prop_type == "tracecontext":
                    propagator = TraceContextTextMapPropagator()
                elif prop_type == "b3":
                    propagator = B3MultiFormat()
                elif prop_type == "b3single":
                    propagator = B3SingleFormat()
                elif prop_type == "jaeger":
                    propagator = JaegerPropagator()
                elif prop_type == "baggage":
                    propagator = W3CBaggagePropagator()
                else:
                    continue

                # Extract context
                ctx = propagator.extract(headers)

                # Check if we got a valid context
                if ctx and ctx != context.get_current():
                    return ctx

            except Exception:
                continue

        return None

    except Exception:
        return None


def inject_trace_context(
    headers: Dict[str, str],
    ctx: Optional[Any] = None,
    propagator_types: Optional[list] = None,
) -> Dict[str, str]:
    """
    Inject current trace context into headers or other carriers.

    Args:
        headers: Dictionary to inject headers into
        ctx: OpenTelemetry context (uses current if None)
        propagator_types: List of propagator types to use

    Returns:
        Updated headers dictionary
    """
    if not HAS_OPENTELEMETRY:
        return headers

    if propagator_types is None:
        propagator_types = ["tracecontext", "baggage"]

    if ctx is None:
        ctx = context.get_current()

    try:
        updated_headers = headers.copy()

        for prop_type in propagator_types:
            try:
                if prop_type == "tracecontext":
                    propagator = TraceContextTextMapPropagator()
                elif prop_type == "b3":
                    propagator = B3MultiFormat()
                elif prop_type == "b3single":
                    propagator = B3SingleFormat()
                elif prop_type == "jaeger":
                    propagator = JaegerPropagator()
                elif prop_type == "baggage":
                    propagator = W3CBaggagePropagator()
                else:
                    continue

                # Inject context
                propagator.inject(updated_headers, context=ctx)

            except Exception:
                continue

        return updated_headers

    except Exception:
        return headers


class TracePropagationMiddleware:
    """
    Middleware for automatic trace context extraction and injection.

    This can be used in web frameworks to automatically handle
    trace context propagation across HTTP requests.
    """

    def __init__(
        self,
        propagator_types: Optional[list] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize trace propagation middleware.

        Args:
            propagator_types: List of propagator types to use
            logger: Logger instance for debugging
        """
        self.propagator_types = propagator_types or ["tracecontext", "baggage"]
        self.logger = logger
        self._otel_available = HAS_OPENTELEMETRY

    def extract_from_headers(self, headers: Dict[str, str]) -> Optional[Any]:
        """Extract trace context from request headers."""
        if not self._otel_available:
            return None

        ctx = extract_trace_context(headers, self.propagator_types)

        if ctx and self.logger:
            self.logger.debug("Extracted trace context from headers")

        return ctx

    def inject_to_headers(
        self, headers: Dict[str, str], ctx: Optional[Any] = None
    ) -> Dict[str, str]:
        """Inject trace context into response headers."""
        if not self._otel_available:
            return headers

        updated_headers = inject_trace_context(
            headers, ctx, self.propagator_types
        )

        if self.logger:
            self.logger.debug("Injected trace context into headers")

        return updated_headers

    def create_child_context(
        self, parent_ctx: Optional[Any] = None
    ) -> Optional[Any]:
        """Create a child context for the current request."""
        if not self._otel_available:
            return None

        try:
            if parent_ctx:
                # Attach parent context
                token = context.attach(parent_ctx)
                return token
            else:
                return None

        except Exception:
            return None


def get_trace_headers(
    ctx: Optional[Any] = None, propagator_types: Optional[list] = None
) -> Dict[str, str]:
    """
    Get trace headers from current or provided context.

    Args:
        ctx: OpenTelemetry context (uses current if None)
        propagator_types: List of propagator types to use

    Returns:
        Dictionary of trace headers
    """
    headers = {}
    return inject_trace_context(headers, ctx, propagator_types)


def create_trace_logger(
    name: str,
    headers: Optional[Dict[str, str]] = None,
    propagator_types: Optional[list] = None,
) -> logging.Logger:
    """
    Create a logger with trace context extracted from headers.

    This is useful for creating loggers that automatically include
    trace context from incoming requests.

    Args:
        name: Logger name
        headers: Headers to extract context from
        propagator_types: List of propagator types to try

    Returns:
        Logger instance with trace context
    """
    logger = logging.getLogger(name)

    if not HAS_OPENTELEMETRY or not headers:
        return logger

    try:
        # Extract trace context
        ctx = extract_trace_context(headers, propagator_types)

        if ctx:
            # Attach context for this thread
            token = context.attach(ctx)

            # Add a context manager to the logger for cleanup
            def cleanup_context():
                try:
                    context.detach(token)
                except Exception:
                    pass

            # Store cleanup function on logger (not ideal but works)
            logger._otel_cleanup = cleanup_context

    except Exception:
        pass

    return logger


# Convenience functions for common frameworks
def flask_trace_middleware(app):
    """Add trace context extraction/injection to Flask app."""
    if not HAS_OPENTELEMETRY:
        return app

    try:
        from flask import request, g

        middleware = TracePropagationMiddleware()

        @app.before_request
        def extract_trace_context():
            headers = dict(request.headers)
            g.trace_context = middleware.extract_from_headers(headers)
            if g.trace_context:
                g.trace_token = context.attach(g.trace_context)

        @app.after_request
        def inject_trace_context(response):
            if hasattr(g, "trace_token"):
                try:
                    context.detach(g.trace_token)
                except Exception:
                    pass
            return response

    except ImportError:
        pass

    return app


def django_trace_middleware():
    """Django middleware class for trace context handling."""
    if not HAS_OPENTELEMETRY:
        return None

    try:

        class OpenTelemetryMiddleware:
            def __init__(self, get_response):
                self.get_response = get_response
                self.propagation_middleware = TracePropagationMiddleware()

            def __call__(self, request):
                # Extract trace context from request headers
                headers = {
                    key: value
                    for key, value in request.META.items()
                    if key.startswith("HTTP_")
                }

                # Remove HTTP_ prefix and convert to lowercase
                clean_headers = {}
                for key, value in headers.items():
                    clean_key = key[5:].replace("_", "-").lower()
                    clean_headers[clean_key] = value

                ctx = self.propagation_middleware.extract_from_headers(
                    clean_headers
                )

                token = None
                if ctx:
                    token = context.attach(ctx)

                try:
                    response = self.get_response(request)
                    return response
                finally:
                    if token:
                        try:
                            context.detach(token)
                        except Exception:
                            pass

        return OpenTelemetryMiddleware

    except ImportError:
        return None
