"""
ASGI/WSGI middleware for MohFlow logging.

Provides generic middleware that works with any ASGI or WSGI framework,
offering automatic request/response logging and performance monitoring.
"""

import time
import uuid
import asyncio
from typing import Optional, Dict, Any, Callable, List, Set
from datetime import datetime


class MohFlowASGIMiddleware:
    """
    ASGI middleware for MohFlow logging.

    Compatible with FastAPI, Starlette, Django Channels, Quart,
    and other ASGI frameworks.
    """

    def __init__(
        self,
        app,
        logger: Any,
        log_requests: bool = True,
        log_responses: bool = True,
        max_body_size: int = 1024,
        exclude_paths: Optional[Set[str]] = None,
        exclude_status_codes: Optional[Set[int]] = None,
        log_level_mapping: Optional[Dict[int, str]] = None,
    ):
        """
        Initialize ASGI middleware.

        Args:
            app: ASGI application
            logger: MohFlow logger instance
            log_requests: Whether to log incoming requests
            log_responses: Whether to log outgoing responses
            max_body_size: Maximum body size to log (bytes)
            exclude_paths: Set of paths to exclude from logging
            exclude_status_codes: Set of status codes to exclude
            log_level_mapping: Map status codes to log levels
        """
        self.app = app
        self.logger = logger
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.max_body_size = max_body_size
        self.exclude_paths = exclude_paths or set()
        self.exclude_status_codes = exclude_status_codes or set()
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

    async def __call__(
        self, scope: Dict[str, Any], receive: Callable, send: Callable
    ):
        """ASGI middleware entry point."""
        if scope["type"] != "http":
            # Pass through non-HTTP requests (WebSocket, etc.)
            await self.app(scope, receive, send)
            return

        # Extract request info
        path = scope.get("path", "")
        method = scope.get("method", "")

        # Skip excluded paths
        if path in self.exclude_paths:
            await self.app(scope, receive, send)
            return

        # Generate request context
        request_id = str(uuid.uuid4())
        start_time = time.time()

        request_context = await self._extract_request_context(
            scope, receive, request_id
        )

        # Log incoming request
        if self.log_requests:
            with self.logger.request_context(
                request_id=request_id, **request_context
            ):
                self.logger.info(
                    f"{method} {path} - Request received", **request_context
                )

        # Wrap send to capture response
        response_data = {"status_code": None, "headers": {}, "body": b""}

        async def send_wrapper(message: Dict[str, Any]):
            if message["type"] == "http.response.start":
                response_data["status_code"] = message.get("status", 500)
                response_data["headers"] = dict(message.get("headers", []))
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body:
                    response_data["body"] += body

            await send(message)

        # Process request
        try:
            await self.app(scope, receive, send_wrapper)
            duration_ms = (time.time() - start_time) * 1000

            # Skip excluded status codes
            status_code = response_data["status_code"]
            if status_code and status_code not in self.exclude_status_codes:
                # Extract response context
                response_context = self._extract_response_context(
                    response_data, duration_ms
                )

                # Log response
                if self.log_responses:
                    log_level = self.log_level_mapping.get(status_code, "info")
                    log_method = getattr(
                        self.logger, log_level, self.logger.info
                    )

                    with self.logger.request_context(
                        request_id=request_id, **request_context
                    ):
                        log_method(
                            (
                                f"{method} {path} - {status_code} "
                                f"({duration_ms:.1f}ms)"
                            ),
                            **{**request_context, **response_context},
                        )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # Log exception
            with self.logger.request_context(
                request_id=request_id, **request_context
            ):
                self.logger.error(
                    (
                        f"{method} {path} - Unhandled exception "
                        f"({duration_ms:.1f}ms)"
                    ),
                    error=str(e),
                    error_type=type(e).__name__,
                    duration=duration_ms,
                    **request_context,
                )
            raise

    async def _extract_request_context(
        self, scope: Dict[str, Any], receive: Callable, request_id: str
    ) -> Dict[str, Any]:
        """Extract context from ASGI scope."""
        context = {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "query_string": scope.get("query_string", b"").decode("utf-8"),
            "scheme": scope.get("scheme"),
            "server": scope.get("server"),
            "client": scope.get("client"),
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Extract headers
        headers = dict(scope.get("headers", []))
        context["user_agent"] = headers.get(b"user-agent", b"").decode("utf-8")
        context["content_type"] = headers.get(b"content-type", b"").decode(
            "utf-8"
        )
        context["content_length"] = headers.get(b"content-length", b"").decode(
            "utf-8"
        )

        # Extract client IP
        context["client_ip"] = self._get_client_ip(scope, headers)

        return {k: v for k, v in context.items() if v}

    def _extract_response_context(
        self, response_data: Dict[str, Any], duration_ms: float
    ) -> Dict[str, Any]:
        """Extract context from response data."""
        context = {
            "status_code": response_data["status_code"],
            "duration": duration_ms,
            "response_size": (
                len(response_data["body"]) if response_data["body"] else None
            ),
        }

        # Extract response headers
        headers = response_data["headers"]
        if b"content-type" in headers:
            context["content_type"] = headers[b"content-type"].decode("utf-8")

        return {k: v for k, v in context.items() if v is not None}

    def _get_client_ip(
        self, scope: Dict[str, Any], headers: Dict[bytes, bytes]
    ) -> Optional[str]:
        """Extract client IP from scope and headers."""
        # Check proxy headers
        ip_headers = [
            b"x-forwarded-for",
            b"x-real-ip",
            b"x-client-ip",
            b"cf-connecting-ip",
        ]

        for header in ip_headers:
            if header in headers:
                ip = headers[header].decode("utf-8")
                return ip.split(",")[0].strip()

        # Fallback to client from scope
        client = scope.get("client")
        if client:
            return (
                client[0] if isinstance(client, (list, tuple)) else str(client)
            )

        return None


class MohFlowWSGIMiddleware:
    """
    WSGI middleware for MohFlow logging.

    Compatible with Django, Flask, Pyramid, and other WSGI frameworks.
    """

    def __init__(
        self,
        app,
        logger: Any,
        log_requests: bool = True,
        log_responses: bool = True,
        max_body_size: int = 1024,
        exclude_paths: Optional[Set[str]] = None,
        exclude_status_codes: Optional[Set[int]] = None,
        log_level_mapping: Optional[Dict[int, str]] = None,
    ):
        """
        Initialize WSGI middleware.

        Args:
            app: WSGI application
            logger: MohFlow logger instance
            log_requests: Whether to log incoming requests
            log_responses: Whether to log outgoing responses
            max_body_size: Maximum body size to log (bytes)
            exclude_paths: Set of paths to exclude from logging
            exclude_status_codes: Set of status codes to exclude
            log_level_mapping: Map status codes to log levels
        """
        self.app = app
        self.logger = logger
        self.log_requests = log_requests
        self.log_responses = log_responses
        self.max_body_size = max_body_size
        self.exclude_paths = exclude_paths or set()
        self.exclude_status_codes = exclude_status_codes or set()
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

    def __call__(self, environ: Dict[str, Any], start_response: Callable):
        """WSGI middleware entry point."""
        # Extract request info
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "")

        # Skip excluded paths
        if path in self.exclude_paths:
            return self.app(environ, start_response)

        # Generate request context
        request_id = str(uuid.uuid4())
        start_time = time.time()

        request_context = self._extract_request_context(environ, request_id)

        # Log incoming request
        if self.log_requests:
            with self.logger.request_context(
                request_id=request_id, **request_context
            ):
                self.logger.info(
                    f"{method} {path} - Request received", **request_context
                )

        # Wrap start_response to capture response info
        response_data = {"status": None, "headers": []}

        def start_response_wrapper(status: str, headers: List, exc_info=None):
            response_data["status"] = status
            response_data["headers"] = headers

            # Add request ID header
            headers.append(("X-Request-ID", request_id))

            return start_response(status, headers, exc_info)

        # Process request
        try:
            response_iterable = self.app(environ, start_response_wrapper)

            # Collect response body
            response_body = b""
            response_list = []

            for data in response_iterable:
                response_body += data
                response_list.append(data)

            # Close iterable if it has close method
            if hasattr(response_iterable, "close"):
                response_iterable.close()

            duration_ms = (time.time() - start_time) * 1000

            # Extract status code
            status_line = (
                response_data["status"] or "500 Internal Server Error"
            )
            status_code = int(status_line.split()[0])

            # Skip excluded status codes
            if status_code not in self.exclude_status_codes:
                # Extract response context
                response_context = self._extract_response_context(
                    response_data, response_body, duration_ms
                )

                # Log response
                if self.log_responses:
                    log_level = self.log_level_mapping.get(status_code, "info")
                    log_method = getattr(
                        self.logger, log_level, self.logger.info
                    )

                    with self.logger.request_context(
                        request_id=request_id, **request_context
                    ):
                        log_method(
                            (
                                f"{method} {path} - {status_code} "
                                f"({duration_ms:.1f}ms)"
                            ),
                            **{**request_context, **response_context},
                        )

            return response_list

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # Log exception
            with self.logger.request_context(
                request_id=request_id, **request_context
            ):
                self.logger.error(
                    (
                        f"{method} {path} - Unhandled exception "
                        f"({duration_ms:.1f}ms)"
                    ),
                    error=str(e),
                    error_type=type(e).__name__,
                    duration=duration_ms,
                    **request_context,
                )
            raise

    def _extract_request_context(
        self, environ: Dict[str, Any], request_id: str
    ) -> Dict[str, Any]:
        """Extract context from WSGI environ."""
        context = {
            "method": environ.get("REQUEST_METHOD"),
            "path": environ.get("PATH_INFO"),
            "query_string": environ.get("QUERY_STRING"),
            "server_name": environ.get("SERVER_NAME"),
            "server_port": environ.get("SERVER_PORT"),
            "scheme": environ.get("wsgi.url_scheme"),
            "user_agent": environ.get("HTTP_USER_AGENT"),
            "content_type": environ.get("CONTENT_TYPE"),
            "content_length": environ.get("CONTENT_LENGTH"),
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Extract client IP
        context["client_ip"] = self._get_client_ip(environ)

        return {k: v for k, v in context.items() if v}

    def _extract_response_context(
        self, response_data: Dict[str, Any], body: bytes, duration_ms: float
    ) -> Dict[str, Any]:
        """Extract context from response data."""
        # Parse status
        status_line = response_data["status"] or "500 Internal Server Error"
        status_code = int(status_line.split()[0])

        context = {
            "status_code": status_code,
            "duration": duration_ms,
            "response_size": len(body) if body else None,
        }

        # Extract content type from headers
        headers = dict(response_data.get("headers", []))
        if "Content-Type" in headers:
            context["content_type"] = headers["Content-Type"]

        return {k: v for k, v in context.items() if v is not None}

    def _get_client_ip(self, environ: Dict[str, Any]) -> Optional[str]:
        """Extract client IP from WSGI environ."""
        # Check proxy headers
        ip_headers = [
            "HTTP_X_FORWARDED_FOR",
            "HTTP_X_REAL_IP",
            "HTTP_X_CLIENT_IP",
            "HTTP_CF_CONNECTING_IP",
        ]

        for header in ip_headers:
            ip = environ.get(header)
            if ip:
                return ip.split(",")[0].strip()

        # Fallback to REMOTE_ADDR
        return environ.get("REMOTE_ADDR")


# Factory functions for easy setup
def create_asgi_middleware(logger: Any, **config):
    """
    Create ASGI middleware with MohFlow logging.

    Usage:
        app = FastAPI()
        app.add_middleware(create_asgi_middleware(logger))
    """

    def middleware_factory(app):
        return MohFlowASGIMiddleware(app, logger, **config)

    return middleware_factory


def create_wsgi_middleware(logger: Any, **config):
    """
    Create WSGI middleware with MohFlow logging.

    Usage:
        app = Flask(__name__)
        app.wsgi_app = create_wsgi_middleware(logger)(app.wsgi_app)
    """

    def middleware_factory(app):
        return MohFlowWSGIMiddleware(app, logger, **config)

    return middleware_factory


# Generic framework detection and auto-setup
def auto_setup_middleware(app, logger: Any, **config):
    """
    Automatically detect framework type and setup appropriate middleware.

    Usage:
        app = FastAPI()  # or Flask(), Django app, etc.
        auto_setup_middleware(app, logger)
    """
    app_type = type(app).__name__
    module_name = type(app).__module__

    # FastAPI/Starlette (ASGI)
    if "fastapi" in module_name or "starlette" in module_name:
        middleware_class = create_asgi_middleware(logger, **config)
        app.add_middleware(middleware_class)
        return app

    # Flask (WSGI)
    elif "flask" in module_name:
        middleware_class = create_wsgi_middleware(logger, **config)
        app.wsgi_app = middleware_class(app.wsgi_app)
        return app

    # Django (WSGI, but has its own middleware system)
    elif "django" in module_name:
        # Django should use the Django-specific middleware
        raise ValueError(
            (
                "For Django apps, use "
                "mohflow.integrations.django.MohFlowDjangoMiddleware"
            )
        )

    # Generic WSGI app
    elif hasattr(app, "__call__") and hasattr(app, "wsgi_version"):
        middleware_class = create_wsgi_middleware(logger, **config)
        return middleware_class(app)

    # Generic ASGI app
    elif hasattr(app, "__call__") and asyncio.iscoroutinefunction(app):
        middleware_class = create_asgi_middleware(logger, **config)
        return middleware_class(app)

    else:
        raise ValueError(
            f"Unable to auto-detect framework type for {app_type}"
        )


# Utility functions for manual instrumentation
def log_request_manually(logger: Any, method: str, path: str, **context):
    """Manually log a request (useful for custom protocols)."""
    request_id = str(uuid.uuid4())

    request_context = {
        "method": method,
        "path": path,
        "timestamp": datetime.utcnow().isoformat(),
        **context,
    }

    with logger.request_context(request_id=request_id, **request_context):
        logger.info(f"{method} {path} - Request received", **request_context)

    return request_id


def log_response_manually(
    logger: Any,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **context,
):
    """Manually log a response (useful for custom protocols)."""
    response_context = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration": duration_ms,
        "timestamp": datetime.utcnow().isoformat(),
        **context,
    }

    # Determine log level based on status code
    if status_code < 400:
        log_level = "info"
    elif status_code < 500:
        log_level = "warning"
    else:
        log_level = "error"

    log_method = getattr(logger, log_level, logger.info)

    with logger.request_context(request_id=request_id, **response_context):
        log_method(
            f"{method} {path} - {status_code} ({duration_ms:.1f}ms)",
            **response_context,
        )
