"""
Flask integration for MohFlow logging.

Provides Flask extension, decorators, and utilities for seamless integration
with automatic request/response logging and error handling.
"""

import time
import uuid
import functools
from typing import Optional, Dict, Any
from datetime import datetime
from werkzeug.exceptions import HTTPException

try:
    from flask import Flask, request, g, jsonify, current_app

    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    Flask = object
    request = None
    g = None


class MohFlowFlaskExtension:
    """
    Flask extension for MohFlow logging integration.

    Provides automatic request/response logging, error handling, and
    performance monitoring for Flask applications.
    """

    def __init__(self, app: Optional[Flask] = None, logger: Any = None):
        """
        Initialize Flask extension.

        Args:
            app: Flask application instance
            logger: MohFlow logger instance
        """
        self.logger = logger
        self.app = app

        if app is not None:
            self.init_app(app, logger)

    def init_app(self, app: Flask, logger: Any = None):
        """Initialize extension with Flask app."""
        if not HAS_FLASK:
            raise ImportError(
                "Flask is not installed. Install with: pip install flask"
            )

        if logger is not None:
            self.logger = logger

        if self.logger is None:
            raise ValueError("MohFlow logger is required")

        # Store extension in app
        app.extensions = getattr(app, "extensions", {})
        app.extensions["mohflow"] = self

        # Get configuration from app config
        self.log_requests = app.config.get("MOHFLOW_LOG_REQUESTS", True)
        self.log_responses = app.config.get("MOHFLOW_LOG_RESPONSES", True)
        self.log_request_body = app.config.get(
            "MOHFLOW_LOG_REQUEST_BODY", False
        )
        self.log_response_body = app.config.get(
            "MOHFLOW_LOG_RESPONSE_BODY", False
        )
        self.max_body_size = app.config.get("MOHFLOW_MAX_BODY_SIZE", 1024)
        self.exclude_paths = set(app.config.get("MOHFLOW_EXCLUDE_PATHS", []))
        self.exclude_status_codes = set(
            app.config.get("MOHFLOW_EXCLUDE_STATUS_CODES", [])
        )
        self.log_level_mapping = app.config.get(
            "MOHFLOW_LOG_LEVEL_MAPPING",
            {
                200: "info",
                201: "info",
                202: "info",
                204: "info",
                400: "warning",
                401: "warning",
                403: "warning",
                404: "warning",
                500: "error",
                501: "error",
                502: "error",
                503: "error",
            },
        )

        # Register handlers
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.errorhandler(Exception)(self._handle_exception)

        # Add helper methods to app
        app.mohflow_logger = self.logger
        app.mohflow_log_context = self._log_context

    def _before_request(self):
        """Handle request start."""
        # Skip excluded paths
        if request.path in self.exclude_paths:
            return

        # Generate request ID and store start time
        g.mohflow_request_id = str(uuid.uuid4())
        g.mohflow_start_time = time.time()

        # Extract request context
        request_context = self._extract_request_context()
        g.mohflow_context = request_context

        # Log incoming request
        if self.log_requests:
            with self.logger.request_context(
                request_id=g.mohflow_request_id, **request_context
            ):
                self.logger.info(
                    f"{request.method} {request.path} - Request received",
                    **request_context,
                )

    def _after_request(self, response):
        """Handle request completion."""
        # Skip if no MohFlow data (excluded paths)
        if not hasattr(g, "mohflow_request_id"):
            return response

        duration_ms = (time.time() - g.mohflow_start_time) * 1000

        # Skip excluded status codes
        if response.status_code in self.exclude_status_codes:
            return response

        # Extract response context
        response_context = self._extract_response_context(
            response, duration_ms
        )

        # Log response
        if self.log_responses:
            log_level = self.log_level_mapping.get(
                response.status_code, "info"
            )
            log_method = getattr(self.logger, log_level, self.logger.info)

            with self.logger.request_context(
                request_id=g.mohflow_request_id, **g.mohflow_context
            ):
                log_method(
                    f"{request.method} {request.path} - "
                    f"{response.status_code} "
                    f"({duration_ms:.1f}ms)",
                    **{**g.mohflow_context, **response_context},
                )

        # Add request ID to response headers
        response.headers["X-Request-ID"] = g.mohflow_request_id

        return response

    def _handle_exception(self, error):
        """Handle unhandled exceptions."""
        if not hasattr(g, "mohflow_request_id"):
            # Re-raise for Flask to handle
            raise error

        duration_ms = (time.time() - g.mohflow_start_time) * 1000

        # Log exception
        with self.logger.request_context(
            request_id=g.mohflow_request_id,
            **getattr(g, "mohflow_context", {}),
        ):
            if isinstance(error, HTTPException):
                # HTTP exceptions
                log_level = self.log_level_mapping.get(error.code, "warning")
                log_method = getattr(
                    self.logger, log_level, self.logger.warning
                )

                log_method(
                    f"{request.method} {request.path} - HTTP {error.code} "
                    f"({duration_ms:.1f}ms)",
                    error=error.description,
                    error_type="HTTPException",
                    status_code=error.code,
                    duration=duration_ms,
                    **getattr(g, "mohflow_context", {}),
                )
            else:
                # Unhandled exceptions
                self.logger.error(
                    f"{request.method} {request.path} - Unhandled exception "
                    f"({duration_ms:.1f}ms)",
                    error=str(error),
                    error_type=type(error).__name__,
                    duration=duration_ms,
                    **getattr(g, "mohflow_context", {}),
                )

        # Re-raise for Flask to handle
        raise error

    def _extract_request_context(self) -> Dict[str, Any]:
        """Extract context from Flask request."""
        context = {
            "method": request.method,
            "path": request.path,
            "query_params": (
                request.query_string.decode("utf-8")
                if request.query_string
                else None
            ),
            "user_agent": request.headers.get("User-Agent"),
            "client_ip": self._get_client_ip(),
            "content_type": request.content_type,
            "request_size": request.content_length,
            "timestamp": datetime.utcnow().isoformat(),
            "flask_endpoint": request.endpoint,
            "flask_view_args": (
                dict(request.view_args) if request.view_args else None
            ),
        }

        # Add request body if enabled
        if self.log_request_body and context.get(
            "content_type", ""
        ).startswith("application/json"):
            try:
                data = request.get_data(as_text=True)
                if len(data) <= self.max_body_size:
                    context["request_body"] = data[: self.max_body_size]
            except Exception:
                context["request_body"] = "[Unable to read body]"

        return {k: v for k, v in context.items() if v is not None}

    def _extract_response_context(
        self, response, duration_ms: float
    ) -> Dict[str, Any]:
        """Extract context from Flask response."""
        context = {
            "status_code": response.status_code,
            "content_type": response.content_type,
            "response_size": response.content_length,
            "duration": duration_ms,
        }

        # Add response body if enabled
        if self.log_response_body and context.get(
            "content_type", ""
        ).startswith("application/json"):
            try:
                data = response.get_data(as_text=True)
                if len(data) <= self.max_body_size:
                    context["response_body"] = data[: self.max_body_size]
            except Exception:
                context["response_body"] = "[Unable to read body]"

        return {k: v for k, v in context.items() if v is not None}

    def _get_client_ip(self) -> Optional[str]:
        """Extract client IP from request headers."""
        # Check common proxy headers
        ip_headers = [
            "X-Forwarded-For",
            "X-Real-IP",
            "X-Client-IP",
            "CF-Connecting-IP",  # Cloudflare
        ]

        for header in ip_headers:
            ip = request.headers.get(header)
            if ip:
                # Take first IP if comma-separated
                return ip.split(",")[0].strip()

        # Fallback to remote_addr
        return request.environ.get("REMOTE_ADDR")

    def _log_context(self, **kwargs):
        """Add context to current request logging."""
        if hasattr(g, "mohflow_context"):
            g.mohflow_context.update(kwargs)


# Decorators for Flask routes
def log_route(logger: Any = None, **log_kwargs):
    """
    Decorator for Flask routes to add logging context.

    Usage:
        @app.route('/login')
        @log_route(logger, component="auth", operation="login")
        def login():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            # Get logger from extension if not provided
            if logger is None:
                ext_logger = current_app.extensions.get("mohflow", {})
                route_logger = getattr(ext_logger, "logger", None)
            else:
                route_logger = logger

            # Add route context to g if middleware is active
            if hasattr(g, "mohflow_context"):
                g.mohflow_context.update(
                    {"flask_route": func.__name__, **log_kwargs}
                )

            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000

                if route_logger:
                    route_logger.info(
                        f"Route {func.__name__} completed successfully",
                        route=func.__name__,
                        duration=duration,
                        **log_kwargs,
                    )

                return result

            except Exception as e:
                duration = (time.time() - start_time) * 1000

                if route_logger:
                    route_logger.error(
                        f"Route {func.__name__} failed",
                        route=func.__name__,
                        duration=duration,
                        error=str(e),
                        error_type=type(e).__name__,
                        **log_kwargs,
                    )
                raise

        return wrapper

    return decorator


def timed_route(logger: Any = None):
    """
    Decorator to automatically log route execution time.

    Usage:
        @app.route('/expensive-operation')
        @timed_route(logger)
        def expensive_operation():
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000

                # Get logger from extension if not provided
                if logger is None:
                    ext_logger = current_app.extensions.get("mohflow", {})
                    route_logger = getattr(ext_logger, "logger", None)
                else:
                    route_logger = logger

                if route_logger:
                    route_logger.info(
                        f"Route {func.__name__} execution time",
                        route=func.__name__,
                        duration=duration,
                        performance_metric=True,
                    )

                return result

            except Exception as e:
                duration = (time.time() - start_time) * 1000

                # Log even for failures
                if logger:
                    logger.warning(
                        f"Route {func.__name__} failed after {duration:.1f}ms",
                        route=func.__name__,
                        duration=duration,
                        error=str(e),
                    )
                raise

        return wrapper

    return decorator


# Helper functions
def get_request_id() -> Optional[str]:
    """Get current request ID."""
    return getattr(g, "mohflow_request_id", None)


def log_business_event(logger: Any, event: str, **context):
    """
    Log business events with context.

    Usage:
        log_business_event(logger, "user_signup",
                          user_id=123, plan="premium")
    """
    request_id = get_request_id()

    context_data = {
        "business_event": event,
        "timestamp": datetime.utcnow().isoformat(),
        **context,
    }

    if request_id:
        context_data["request_id"] = request_id

    logger.info(f"Business event: {event}", **context_data)


def create_health_route(logger: Any):
    """
    Create a health check route with logging.

    Usage:
        health_check = create_health_route(logger)
        app.add_url_rule('/health', 'health', health_check)
    """

    def health_check():
        logger.info("Health check requested", endpoint="health", status="ok")
        return jsonify(
            {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": get_request_id(),
            }
        )

    return health_check


def create_metrics_route(logger: Any):
    """
    Create a metrics endpoint that exports MohFlow metrics.

    Usage:
        metrics_endpoint = create_metrics_route(logger)
        app.add_url_rule('/metrics', 'metrics', metrics_endpoint)
    """

    def metrics_endpoint():
        # Get Prometheus metrics if available
        if hasattr(logger, "export_prometheus_metrics"):
            metrics = logger.export_prometheus_metrics()
            if metrics:
                return (
                    metrics,
                    200,
                    {"Content-Type": "text/plain; version=0.0.4"},
                )

        # Fallback to JSON metrics
        if hasattr(logger, "get_metrics_summary"):
            summary = logger.get_metrics_summary()
            if summary:
                return jsonify(summary)

        return jsonify({"message": "No metrics available"}), 404

    return metrics_endpoint


# Configuration helper
def configure_mohflow_flask(
    app: Flask, logger: Any, **config
) -> MohFlowFlaskExtension:
    """
    Configure MohFlow extension for Flask app.

    Usage:
        mohflow = configure_mohflow_flask(app, logger,
                                         log_requests=True,
                                         exclude_paths=['/health'])
    """
    # Set Flask configuration
    app.config.setdefault(
        "MOHFLOW_LOG_REQUESTS", config.get("log_requests", True)
    )
    app.config.setdefault(
        "MOHFLOW_LOG_RESPONSES", config.get("log_responses", True)
    )
    app.config.setdefault(
        "MOHFLOW_LOG_REQUEST_BODY", config.get("log_request_body", False)
    )
    app.config.setdefault(
        "MOHFLOW_LOG_RESPONSE_BODY", config.get("log_response_body", False)
    )
    app.config.setdefault(
        "MOHFLOW_MAX_BODY_SIZE", config.get("max_body_size", 1024)
    )
    app.config.setdefault(
        "MOHFLOW_EXCLUDE_PATHS", config.get("exclude_paths", [])
    )
    app.config.setdefault(
        "MOHFLOW_EXCLUDE_STATUS_CODES", config.get("exclude_status_codes", [])
    )

    # Initialize extension
    extension = MohFlowFlaskExtension(app, logger)

    return extension
