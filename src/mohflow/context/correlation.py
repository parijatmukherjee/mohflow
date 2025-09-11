"""
Correlation ID management for distributed tracing and request tracking.
Provides utilities for generating, propagating, and managing correlation IDs.
"""

import uuid
import threading
from typing import Optional, Dict, Any
from contextvars import ContextVar

from mohflow.static_config import CONTEXT_FIELDS


# Context variable for correlation ID
_correlation_id: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


def generate_correlation_id() -> str:
    """
    Generate a new correlation ID.

    Returns:
        A new UUID-based correlation ID
    """
    return str(uuid.uuid4())


def set_correlation_id(correlation_id: str):
    """
    Set the correlation ID for the current context.

    Args:
        correlation_id: The correlation ID to set
    """
    _correlation_id.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """
    Get the current correlation ID.

    Returns:
        The current correlation ID or None if not set
    """
    return _correlation_id.get()


def ensure_correlation_id() -> str:
    """
    Ensure a correlation ID exists, creating one if necessary.

    Returns:
        The current or newly created correlation ID
    """
    correlation_id = _correlation_id.get()
    if correlation_id is None:
        correlation_id = generate_correlation_id()
        _correlation_id.set(correlation_id)
    return correlation_id


def clear_correlation_id():
    """Clear the correlation ID from the current context."""
    _correlation_id.set(None)


class CorrelationIDManager:
    """
    Manager for correlation ID propagation and tracking.
    Handles automatic correlation ID generation and propagation.
    """

    def __init__(self, auto_generate: bool = True):
        """
        Initialize correlation ID manager.

        Args:
            auto_generate: Automatically generate correlation ID if not present
        """
        self.auto_generate = auto_generate

    def get_or_create_correlation_id(self) -> str:
        """
        Get existing correlation ID or create a new one.

        Returns:
            Correlation ID string
        """
        correlation_id = get_correlation_id()
        if correlation_id is None and self.auto_generate:
            correlation_id = generate_correlation_id()
            set_correlation_id(correlation_id)
        return correlation_id or ""

    def propagate_correlation_id(
        self, headers: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Add correlation ID to HTTP headers for propagation.

        Args:
            headers: Existing headers dictionary

        Returns:
            Headers with correlation ID added
        """
        correlation_id = self.get_or_create_correlation_id()
        if correlation_id:
            headers = headers.copy()
            headers["X-Correlation-ID"] = correlation_id
            headers["X-Request-ID"] = correlation_id  # Also set as request ID
        return headers

    def extract_correlation_id(self, headers: Dict[str, str]) -> Optional[str]:
        """
        Extract correlation ID from HTTP headers.

        Args:
            headers: HTTP headers dictionary

        Returns:
            Extracted correlation ID or None
        """
        # Try various header names (case-insensitive)
        header_names = [
            "X-Correlation-ID",
            "X-Request-ID",
            "Correlation-ID",
            "Request-ID",
            "X-Trace-ID",
            "Trace-ID",
        ]

        # Convert headers to lowercase for case-insensitive lookup
        lower_headers = {k.lower(): v for k, v in headers.items()}

        for header_name in header_names:
            value = lower_headers.get(header_name.lower())
            if value:
                return value

        return None

    def get_context_info(self) -> Dict[str, Any]:
        """
        Get correlation context information for logging.

        Returns:
            Dictionary with correlation context
        """
        correlation_id = get_correlation_id()
        if correlation_id:
            return {
                CONTEXT_FIELDS.CORRELATION_ID: correlation_id,
                CONTEXT_FIELDS.REQUEST_ID: correlation_id,  # Same value
            }
        return {}


class CorrelationContext:
    """Context manager for correlation ID scope"""

    def __init__(
        self, correlation_id: Optional[str] = None, auto_generate: bool = True
    ):
        """
        Initialize correlation context.

        Args:
            correlation_id: Specific correlation ID to use
                (auto-generated if None and auto_generate is True)
            auto_generate: Generate correlation ID if none provided
        """
        self.correlation_id = correlation_id
        self.auto_generate = auto_generate
        self._previous_id: Optional[str] = None

    def __enter__(self) -> str:
        """Enter correlation context"""
        # Save previous correlation ID
        self._previous_id = get_correlation_id()

        # Set new correlation ID
        if self.correlation_id:
            set_correlation_id(self.correlation_id)
            return self.correlation_id
        elif self.auto_generate:
            new_id = generate_correlation_id()
            set_correlation_id(new_id)
            return new_id
        else:
            return self._previous_id or ""

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit correlation context"""
        # Restore previous correlation ID
        if self._previous_id is not None:
            set_correlation_id(self._previous_id)
        else:
            clear_correlation_id()


def with_correlation_id(
    correlation_id: Optional[str] = None, auto_generate: bool = True
):
    """
    Decorator to set correlation ID for a function.

    Args:
        correlation_id: Specific correlation ID to use
        auto_generate: Generate correlation ID if none provided
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            with CorrelationContext(correlation_id, auto_generate):
                return func(*args, **kwargs)

        return wrapper

    return decorator


class ThreadLocalCorrelationManager:
    """
    Thread-local correlation ID manager for environments where contextvars
    might not be available or suitable.
    """

    def __init__(self):
        self._local = threading.local()

    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current thread"""
        self._local.correlation_id = correlation_id

    def get_correlation_id(self) -> Optional[str]:
        """Get correlation ID for current thread"""
        return getattr(self._local, "correlation_id", None)

    def clear_correlation_id(self):
        """Clear correlation ID for current thread"""
        if hasattr(self._local, "correlation_id"):
            delattr(self._local, "correlation_id")

    def ensure_correlation_id(self) -> str:
        """Ensure correlation ID exists for current thread"""
        correlation_id = self.get_correlation_id()
        if correlation_id is None:
            correlation_id = generate_correlation_id()
            self.set_correlation_id(correlation_id)
        return correlation_id


# Singleton instances for easy access
default_manager = CorrelationIDManager()
thread_local_manager = ThreadLocalCorrelationManager()


# Utility functions for framework integration
def flask_correlation_middleware():
    """
    Flask middleware for automatic correlation ID handling.

    Usage:
        from flask import Flask, request
        from mohflow.context.correlation import flask_correlation_middleware

        app = Flask(__name__)
        app.before_request(flask_correlation_middleware)
    """
    try:
        from flask import request

        # Extract correlation ID from request headers
        correlation_id = default_manager.extract_correlation_id(
            dict(request.headers)
        )

        if correlation_id:
            set_correlation_id(correlation_id)
        else:
            # Generate new correlation ID
            ensure_correlation_id()

    except ImportError:
        # Flask not available
        pass


def django_correlation_middleware(get_response):
    """
    Django middleware for automatic correlation ID handling.

    Usage:
        # In settings.py MIDDLEWARE:
        'mohflow.context.correlation.DjangoCorrelationMiddleware',
    """

    def middleware(request):
        # Extract correlation ID from request headers
        headers = {
            k.replace("HTTP_", "").replace("_", "-"): v
            for k, v in request.META.items()
            if k.startswith("HTTP_")
        }

        correlation_id = default_manager.extract_correlation_id(headers)

        if correlation_id:
            set_correlation_id(correlation_id)
        else:
            ensure_correlation_id()

        response = get_response(request)

        # Add correlation ID to response headers
        current_id = get_correlation_id()
        if current_id:
            response["X-Correlation-ID"] = current_id

        return response

    return middleware


def fastapi_correlation_dependency():
    """
    FastAPI dependency for correlation ID handling.

    Usage:
        from fastapi import Depends
        from mohflow.context.correlation import fastapi_correlation_dependency

        @app.get("/")
        async def endpoint(
            correlation_id: str = Depends(fastapi_correlation_dependency)
        ):
            return {"correlation_id": correlation_id}
    """
    try:
        from fastapi import Request

        def get_correlation_id(request: Request) -> str:
            # Extract from headers
            correlation_id = default_manager.extract_correlation_id(
                dict(request.headers)
            )

            if correlation_id:
                set_correlation_id(correlation_id)
                return correlation_id
            else:
                return ensure_correlation_id()

        return get_correlation_id

    except ImportError:
        # FastAPI not available
        def dummy_dependency() -> str:
            return ensure_correlation_id()

        return dummy_dependency
