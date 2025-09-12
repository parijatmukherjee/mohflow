"""
FastAPI integration for MohFlow logging.

Provides automatic request/response logging, error tracking, and performance monitoring
for FastAPI applications with minimal configuration.
"""

import time
import uuid
from typing import Optional, Dict, Any, Callable, List, Set
from datetime import datetime
import json

try:
    from fastapi import Request, Response, FastAPI
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.types import ASGIApp

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    # Create dummy classes for type hints
    BaseHTTPMiddleware = object
    Request = object
    Response = object
    FastAPI = object
    ASGIApp = object


class MohFlowFastAPIMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic request/response logging with MohFlow.

    Features:
    - Automatic request/response logging
    - Performance monitoring with duration tracking
    - Error tracking and status code monitoring
    - Request ID generation and tracking
    - Custom field extraction
    - Configurable filtering
    """

    def __init__(
        self,
        app: ASGIApp,
        logger: Any,
        log_requests: bool = True,
        log_responses: bool = True,
        log_request_body: bool = False,
        log_response_body: bool = False,
        max_body_size: int = 1024,
        exclude_paths: Optional[Set[str]] = None,
        exclude_status_codes: Optional[Set[int]] = None,
        custom_extractors: Optional[
            List[Callable[[Request], Dict[str, Any]]]
        ] = None,
        enable_metrics: bool = True,
        log_level_mapping: Optional[Dict[int, str]] = None,
    ):
        """
        Initialize FastAPI middleware.

        Args:
            app: FastAPI application
            logger: MohFlow logger instance
            log_requests: Whether to log incoming requests
            log_responses: Whether to log outgoing responses
            log_request_body: Whether to include request body in logs
            log_response_body: Whether to include response body in logs
            max_body_size: Maximum body size to log (bytes)
            exclude_paths: Set of paths to exclude from logging
            exclude_status_codes: Set of status codes to exclude from logging
            custom_extractors: Custom functions to extract additional context
            enable_metrics: Whether to generate automatic metrics
            log_level_mapping: Map status codes to log levels
        """
        super().__init__(app)
        self.logger = logger
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.max_body_size = max_body_size
        self.exclude_paths = exclude_paths or set()
        self.exclude_status_codes = exclude_status_codes or set()
        self.custom_extractors = custom_extractors or []
        self.enable_metrics = enable_metrics
        self.log_level_mapping = log_level_mapping or {
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
        }

    async def dispatch(self, request: Request, call_next):
        """Process request and response with logging."""
        # Skip excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Generate request ID
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Extract request context
        request_context = await self._extract_request_context(
            request, request_id
        )

        # Log incoming request
        if self.log_requests:
            with self.logger.request_context(
                request_id=request_id, **request_context
            ):
                self.logger.info(
                    f"{request.method} {request.url.path} - Request received",
                    **request_context,
                )

        # Process request
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # Extract response context
            response_context = await self._extract_response_context(
                response, duration_ms
            )

            # Skip excluded status codes
            if response.status_code in self.exclude_status_codes:
                return response

            # Log response
            if self.log_responses:
                log_level = self.log_level_mapping.get(
                    response.status_code, "info"
                )
                log_method = getattr(self.logger, log_level, self.logger.info)

                with self.logger.request_context(
                    request_id=request_id, **request_context
                ):
                    log_method(
                        f"{request.method} {request.url.path} - {response.status_code} "
                        f"({duration_ms:.1f}ms)",
                        **{**request_context, **response_context},
                    )

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            with self.logger.request_context(
                request_id=request_id, **request_context
            ):
                self.logger.error(
                    f"{request.method} {request.url.path} - Unhandled exception "
                    f"({duration_ms:.1f}ms)",
                    error=str(e),
                    error_type=type(e).__name__,
                    duration=duration_ms,
                    **request_context,
                )

            # Return error response
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )

    async def _extract_request_context(
        self, request: Request, request_id: str
    ) -> Dict[str, Any]:
        """Extract context from request."""
        context = {
            "method": request.method,
            "path": request.url.path,
            "query_params": (
                str(request.query_params) if request.query_params else None
            ),
            "user_agent": request.headers.get("user-agent"),
            "client_ip": self._get_client_ip(request),
            "request_size": request.headers.get("content-length"),
            "content_type": request.headers.get("content-type"),
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Add request body if enabled
        if self.log_request_body and context.get(
            "content_type", ""
        ).startswith("application/json"):
            try:
                body = await request.body()
                if len(body) <= self.max_body_size:
                    context["request_body"] = body.decode("utf-8")[
                        : self.max_body_size
                    ]
            except Exception:
                context["request_body"] = "[Unable to read body]"

        # Apply custom extractors
        for extractor in self.custom_extractors:
            try:
                custom_context = extractor(request)
                if isinstance(custom_context, dict):
                    context.update(custom_context)
            except Exception:
                pass  # Ignore extractor errors

        # Remove None values
        return {k: v for k, v in context.items() if v is not None}

    async def _extract_response_context(
        self, response: Response, duration_ms: float
    ) -> Dict[str, Any]:
        """Extract context from response."""
        context = {
            "status_code": response.status_code,
            "response_size": response.headers.get("content-length"),
            "content_type": response.headers.get("content-type"),
            "duration": duration_ms,
        }

        # Add response body if enabled and it's JSON
        if (
            self.log_response_body
            and hasattr(response, "body")
            and context.get("content_type", "").startswith("application/json")
        ):
            try:
                body = getattr(response, "body", b"")
                if isinstance(body, bytes) and len(body) <= self.max_body_size:
                    context["response_body"] = body.decode("utf-8")[
                        : self.max_body_size
                    ]
            except Exception:
                context["response_body"] = "[Unable to read body]"

        return {k: v for k, v in context.items() if v is not None}

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP from request headers."""
        # Check common proxy headers
        ip_headers = [
            "x-forwarded-for",
            "x-real-ip",
            "x-client-ip",
            "cf-connecting-ip",  # Cloudflare
        ]

        for header in ip_headers:
            ip = request.headers.get(header)
            if ip:
                # Take first IP if comma-separated
                return ip.split(",")[0].strip()

        # Fallback to client host
        if hasattr(request, "client") and request.client:
            return getattr(request.client, "host", None)

        return None


def setup_fastapi_logging(
    app: FastAPI, logger: Any, **middleware_kwargs
) -> FastAPI:
    """
    Setup MohFlow logging for FastAPI application.

    Args:
        app: FastAPI application instance
        logger: MohFlow logger instance
        **middleware_kwargs: Additional middleware configuration

    Returns:
        FastAPI app with middleware configured
    """
    if not HAS_FASTAPI:
        raise ImportError(
            "FastAPI is not installed. Install with: pip install fastapi"
        )

    app.add_middleware(
        MohFlowFastAPIMiddleware, logger=logger, **middleware_kwargs
    )
    return app


# Convenience decorators
def log_endpoint(logger: Any, **log_kwargs):
    """
    Decorator for logging specific endpoints with additional context.

    Usage:
        @log_endpoint(logger, component="auth", operation="login")
        async def login(request: LoginRequest):
            ...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000

                logger.info(
                    f"Endpoint {func.__name__} completed successfully",
                    endpoint=func.__name__,
                    duration=duration,
                    **log_kwargs,
                )

                return result

            except Exception as e:
                duration = (time.time() - start_time) * 1000

                logger.error(
                    f"Endpoint {func.__name__} failed",
                    endpoint=func.__name__,
                    duration=duration,
                    error=str(e),
                    error_type=type(e).__name__,
                    **log_kwargs,
                )
                raise

        return wrapper

    return decorator


def create_health_endpoint(logger: Any):
    """
    Create a health check endpoint with logging.

    Usage:
        health_check = create_health_endpoint(logger)
        app.add_api_route("/health", health_check, methods=["GET"])
    """

    async def health_check():
        logger.info("Health check requested", endpoint="health", status="ok")
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }

    return health_check


# Custom extractors for common use cases
def extract_auth_context(request: Request) -> Dict[str, Any]:
    """Extract authentication context from request."""
    context = {}

    # Extract JWT token info (basic)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        context["auth_type"] = "bearer"
        # Could add JWT parsing here if needed
    elif auth_header.startswith("Basic "):
        context["auth_type"] = "basic"

    # Extract user ID from custom headers
    user_id = request.headers.get("x-user-id")
    if user_id:
        context["user_id"] = user_id

    return context


def extract_trace_context(request: Request) -> Dict[str, Any]:
    """Extract distributed tracing context."""
    context = {}

    # OpenTelemetry trace headers
    trace_id = request.headers.get("x-trace-id")
    span_id = request.headers.get("x-span-id")

    if trace_id:
        context["trace_id"] = trace_id
    if span_id:
        context["span_id"] = span_id

    # Jaeger headers
    jaeger_trace = request.headers.get("uber-trace-id")
    if jaeger_trace:
        context["jaeger_trace_id"] = jaeger_trace

    return context


def extract_business_context(request: Request) -> Dict[str, Any]:
    """Extract business-specific context."""
    context = {}

    # Extract tenant/organization info
    tenant_id = request.headers.get("x-tenant-id")
    org_id = request.headers.get("x-organization-id")

    if tenant_id:
        context["tenant_id"] = tenant_id
    if org_id:
        context["organization_id"] = org_id

    # Extract API version
    api_version = request.headers.get("x-api-version", "v1")
    context["api_version"] = api_version

    return context
