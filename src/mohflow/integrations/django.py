"""
Django integration for MohFlow logging.

Provides middleware, settings configuration, and utilities for seamless
Django integration with automatic request/response logging.
"""

import time
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from django.conf import settings
    from django.http import HttpRequest, HttpResponse
    from django.utils.deprecation import MiddlewareMixin
    from django.core.exceptions import ImproperlyConfigured

    HAS_DJANGO = True
except ImportError:
    HAS_DJANGO = False
    # Create dummy classes for type hints
    MiddlewareMixin = object
    HttpRequest = object
    HttpResponse = object


class MohFlowDjangoMiddleware(MiddlewareMixin):
    """
    Django middleware for automatic request/response logging with MohFlow.

    Features:
    - Automatic request/response logging
    - Performance monitoring with duration tracking
    - Error tracking and exception handling
    - Request ID generation and propagation
    - User context extraction
    - Configurable filtering and customization
    """

    def __init__(self, get_response=None):
        """Initialize Django middleware."""
        super().__init__(get_response)
        self.get_response = get_response

        # Get configuration from Django settings
        config = getattr(settings, "MOHFLOW_MIDDLEWARE", {})

        self.logger = self._get_logger(config)
        self.log_requests = config.get("log_requests", True)
        self.log_responses = config.get("log_responses", True)
        self.log_request_body = config.get("log_request_body", False)
        self.log_response_body = config.get("log_response_body", False)
        self.max_body_size = config.get("max_body_size", 1024)
        self.exclude_paths = set(config.get("exclude_paths", []))
        self.exclude_status_codes = set(config.get("exclude_status_codes", []))
        self.log_user_context = config.get("log_user_context", True)
        self.log_level_mapping = config.get(
            "log_level_mapping",
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

    def _get_logger(self, config: Dict[str, Any]):
        """Get MohFlow logger from configuration."""
        logger_path = config.get("logger")

        if logger_path:
            # Import logger from dotted path
            module_path, logger_name = logger_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[logger_name])
            return getattr(module, logger_name)
        elif hasattr(settings, "MOHFLOW_LOGGER"):
            return settings.MOHFLOW_LOGGER
        else:
            raise ImproperlyConfigured(
                "MohFlow Django middleware requires either "
                "MOHFLOW_MIDDLEWARE['logger'] or MOHFLOW_LOGGER setting"
            )

    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Process incoming request."""
        # Skip excluded paths
        if request.path in self.exclude_paths:
            return None

        # Generate request ID and store start time
        request.mohflow_request_id = str(uuid.uuid4())
        request.mohflow_start_time = time.time()

        # Extract request context
        request_context = self._extract_request_context(request)
        request.mohflow_context = request_context

        # Log incoming request
        if self.log_requests:
            with self.logger.request_context(
                request_id=request.mohflow_request_id, **request_context
            ):
                self.logger.info(
                    f"{request.method} {request.path} - Request received",
                    **request_context,
                )

        return None

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """Process outgoing response."""
        # Skip if no MohFlow data (excluded paths)
        if not hasattr(request, "mohflow_request_id"):
            return response

        duration_ms = (time.time() - request.mohflow_start_time) * 1000

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
                request_id=request.mohflow_request_id,
                **request.mohflow_context,
            ):
                log_method(
                    f"{request.method} {request.path} - "
                    f"{response.status_code} "
                    f"({duration_ms:.1f}ms)",
                    **{**request.mohflow_context, **response_context},
                )

        # Add request ID to response headers
        response["X-Request-ID"] = request.mohflow_request_id

        return response

    def process_exception(
        self, request: HttpRequest, exception: Exception
    ) -> Optional[HttpResponse]:
        """Process unhandled exceptions."""
        if not hasattr(request, "mohflow_request_id"):
            return None

        duration_ms = (time.time() - request.mohflow_start_time) * 1000

        # Log exception
        with self.logger.request_context(
            request_id=request.mohflow_request_id,
            **getattr(request, "mohflow_context", {}),
        ):
            self.logger.error(
                f"{request.method} {request.path} - Unhandled exception "
                f"({duration_ms:.1f}ms)",
                error=str(exception),
                error_type=type(exception).__name__,
                duration=duration_ms,
                **getattr(request, "mohflow_context", {}),
            )

        return None  # Let Django handle the exception

    def _extract_request_context(self, request: HttpRequest) -> Dict[str, Any]:
        """Extract context from Django request."""
        context = {
            "method": request.method,
            "path": request.path,
            "query_params": request.GET.urlencode() if request.GET else None,
            "user_agent": request.META.get("HTTP_USER_AGENT"),
            "client_ip": self._get_client_ip(request),
            "content_type": request.content_type,
            "request_size": (
                len(request.body) if hasattr(request, "body") else None
            ),
            "timestamp": datetime.utcnow().isoformat(),
            "django_view": None,  # Will be set by view decorator if used
        }

        # Add user context if authenticated
        if (
            self.log_user_context
            and hasattr(request, "user")
            and request.user.is_authenticated
        ):
            context["user_id"] = getattr(request.user, "id", None)
            context["username"] = getattr(request.user, "username", None)
            context["user_email"] = getattr(request.user, "email", None)

        # Add session context
        if hasattr(request, "session") and request.session.session_key:
            context["session_id"] = request.session.session_key

        # Add request body if enabled
        if (
            self.log_request_body
            and context.get("content_type", "").startswith("application/json")
            and hasattr(request, "body")
        ):
            try:
                body = request.body.decode("utf-8")
                if len(body) <= self.max_body_size:
                    context["request_body"] = body[: self.max_body_size]
            except Exception:
                context["request_body"] = "[Unable to read body]"

        return {k: v for k, v in context.items() if v is not None}

    def _extract_response_context(
        self, response: HttpResponse, duration_ms: float
    ) -> Dict[str, Any]:
        """Extract context from Django response."""
        context = {
            "status_code": response.status_code,
            "content_type": response.get("Content-Type"),
            "response_size": (
                len(response.content) if hasattr(response, "content") else None
            ),
            "duration": duration_ms,
        }

        # Add response body if enabled
        if (
            self.log_response_body
            and context.get("content_type", "").startswith("application/json")
            and hasattr(response, "content")
        ):
            try:
                body = response.content.decode("utf-8")
                if len(body) <= self.max_body_size:
                    context["response_body"] = body[: self.max_body_size]
            except Exception:
                context["response_body"] = "[Unable to read body]"

        return {k: v for k, v in context.items() if v is not None}

    def _get_client_ip(self, request: HttpRequest) -> Optional[str]:
        """Extract client IP from request headers."""
        # Check common proxy headers
        ip_headers = [
            "HTTP_X_FORWARDED_FOR",
            "HTTP_X_REAL_IP",
            "HTTP_X_CLIENT_IP",
            "HTTP_CF_CONNECTING_IP",  # Cloudflare
        ]

        for header in ip_headers:
            ip = request.META.get(header)
            if ip:
                # Take first IP if comma-separated
                return ip.split(",")[0].strip()

        # Fallback to REMOTE_ADDR
        return request.META.get("REMOTE_ADDR")


# View decorator for additional context
def log_view(logger: Any, **log_kwargs):
    """
    Decorator for Django views to add logging context.

    Usage:
        @log_view(logger, component="auth", operation="login")
        def login_view(request):
            ...
    """

    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            start_time = time.time()

            # Add view context to request if middleware is active
            if hasattr(request, "mohflow_context"):
                request.mohflow_context.update(
                    {"django_view": view_func.__name__, **log_kwargs}
                )

            try:
                result = view_func(request, *args, **kwargs)
                duration = (time.time() - start_time) * 1000

                logger.info(
                    f"View {view_func.__name__} completed successfully",
                    view=view_func.__name__,
                    duration=duration,
                    **log_kwargs,
                )

                return result

            except Exception as e:
                duration = (time.time() - start_time) * 1000

                logger.error(
                    f"View {view_func.__name__} failed",
                    view=view_func.__name__,
                    duration=duration,
                    error=str(e),
                    error_type=type(e).__name__,
                    **log_kwargs,
                )
                raise

        return wrapper

    return decorator


# Django management command logging
def setup_command_logging(logger: Any, command_name: str):
    """
    Setup logging for Django management commands.

    Usage:
        class Command(BaseCommand):
            def handle(self, *args, **options):
                logger = setup_command_logging(mohflow_logger, 'migrate')
                logger.info("Starting migration")
    """
    # Create command-specific context
    command_logger = type(logger)(
        service_name=logger.config.SERVICE_NAME,
        **{
            k: v
            for k, v in logger.__dict__.items()
            if not k.startswith("_")
        },
    )

    # Set command context
    command_logger.set_context(
        component="management_command",
        command=command_name,
        timestamp=datetime.utcnow().isoformat(),
    )

    return command_logger


# Settings configuration helper
def configure_mohflow_django(
    logger: Any, **middleware_config
) -> Dict[str, Any]:
    """
    Generate Django settings configuration for MohFlow.

    Usage:
        # In settings.py
        MOHFLOW_MIDDLEWARE = configure_mohflow_django(
            logger=mohflow_logger,
            log_requests=True,
            exclude_paths=['/health', '/metrics']
        )
    """
    config = {
        "logger": logger,
        "log_requests": True,
        "log_responses": True,
        "log_request_body": False,
        "log_response_body": False,
        "max_body_size": 1024,
        "exclude_paths": ["/admin/jsi18n/", "/static/", "/media/"],
        "exclude_status_codes": [],
        "log_user_context": True,
        **middleware_config,
    }

    return config


# Custom Django logging filter
class MohFlowDjangoFilter:
    """
    Django logging filter that adds MohFlow context to log records.

    Usage in Django LOGGING setting:
        'filters': {
            'mohflow_filter': {
                '()': 'mohflow.integrations.django.MohFlowDjangoFilter',
                'logger': mohflow_logger
            }
        }
    """

    def __init__(self, logger: Any):
        self.logger = logger

    def filter(self, record):
        """Add MohFlow context to Django log record."""
        # Add current context from MohFlow
        if hasattr(self.logger, "get_current_context"):
            context = self.logger.get_current_context()
            for key, value in context.items():
                setattr(record, f"mohflow_{key}", value)

        return True


# Django template context processor
def mohflow_context(request):
    """
    Django context processor to add MohFlow context to templates.

    Usage in settings.py:
        'context_processors': [
            'mohflow.integrations.django.mohflow_context',
        ]
    """
    context = {}

    # Add request ID if available
    if hasattr(request, "mohflow_request_id"):
        context["mohflow_request_id"] = request.mohflow_request_id

    # Add user context if available
    if hasattr(request, "mohflow_context"):
        mohflow_ctx = request.mohflow_context
        context.update(
            {
                "mohflow_user_id": mohflow_ctx.get("user_id"),
                "mohflow_session_id": mohflow_ctx.get("session_id"),
            }
        )

    return {"mohflow": context}
