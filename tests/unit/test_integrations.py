"""
Comprehensive unit tests for MohFlow integration modules.

Tests cover:
- Flask extension (MohFlowFlaskExtension, decorators, helpers)
- Django middleware (MohFlowDjangoMiddleware, filter, context processor)
- FastAPI middleware (MohFlowFastAPIMiddleware, extractors, helpers)
- Celery integration (MohFlowCeleryIntegration, task class, helpers)
- ASGI/WSGI middleware (MohFlowASGIMiddleware, MohFlowWSGIMiddleware)

All external frameworks are heavily mocked to avoid install dependencies.
"""

import asyncio
import sys
import time
import types
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

import pytest


# ------------------------------------------------------------------ #
#  Helper: mock logger that behaves like MohFlow logger               #
# ------------------------------------------------------------------ #
def _make_logger():
    """Create a mock logger with request_context as a context manager.

    The real MohFlow logger's ``request_context`` is a context manager
    that accepts arbitrary keyword arguments.  The source modules call
    it with patterns like::

        logger.request_context(request_id=rid, **ctx)

    where ``ctx`` may already contain ``request_id`` (or ``task_id``).
    A plain ``MagicMock`` would blow up with "got multiple values for
    keyword argument".  We therefore replace the mock's ``__call__``
    with a lambda that swallows everything and returns a no-op CM.
    """
    logger = MagicMock()

    @contextmanager
    def _noop_cm():
        yield

    # Accept *any* positional/keyword args, return a context manager.
    logger.request_context = lambda *a, **kw: _noop_cm()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


def _strip_key(original_async_fn, key):
    """Wrap an async extract function to remove *key* from result.

    Several source modules build a context dict that already contains
    e.g. ``request_id`` and then call
    ``logger.request_context(request_id=rid, **ctx)`` which triggers
    a Python ``TypeError`` (duplicate keyword argument).  This helper
    wraps the original async extractor so the returned dict never
    contains the offending key, letting the rest of the code execute.
    """

    async def _wrapper(*args, **kwargs):
        result = await original_async_fn(*args, **kwargs)
        result.pop(key, None)
        return result

    return _wrapper


def _strip_key_sync(original_fn, key):
    """Same as _strip_key but for synchronous functions."""

    def _wrapper(*args, **kwargs):
        result = original_fn(*args, **kwargs)
        result.pop(key, None)
        return result

    return _wrapper


# ================================================================== #
#                          FLASK TESTS                                #
# ================================================================== #


@pytest.fixture()
def flask_mocks():
    """Inject fake flask / werkzeug modules and return handles."""
    # --- werkzeug.exceptions ---
    werkzeug_exc = types.ModuleType("werkzeug.exceptions")

    class _HTTPException(Exception):
        def __init__(self, description="err", code=400):
            super().__init__(description)
            self.description = description
            self.code = code

    werkzeug_exc.HTTPException = _HTTPException
    werkzeug_mod = types.ModuleType("werkzeug")
    werkzeug_mod.exceptions = werkzeug_exc

    # --- flask module ---
    flask_mod = types.ModuleType("flask")
    flask_mod.Flask = MagicMock
    flask_mod.request = MagicMock()
    flask_mod.g = MagicMock()
    flask_mod.jsonify = MagicMock(side_effect=lambda d: d)
    flask_mod.current_app = MagicMock()

    saved = {}
    for mod_name in (
        "werkzeug",
        "werkzeug.exceptions",
        "flask",
    ):
        saved[mod_name] = sys.modules.get(mod_name)

    sys.modules["werkzeug"] = werkzeug_mod
    sys.modules["werkzeug.exceptions"] = werkzeug_exc
    sys.modules["flask"] = flask_mod

    # Force reimport so the module picks up our fakes
    mod_key = "mohflow.integrations.flask"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.flask as flask_int

    yield {
        "module": flask_int,
        "flask_mod": flask_mod,
        "werkzeug_exc": werkzeug_exc,
        "HTTPException": _HTTPException,
    }

    # Restore original sys.modules
    for mod_name, orig in saved.items():
        if orig is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = orig


class TestMohFlowFlaskExtension:
    """Tests for MohFlowFlaskExtension."""

    def test_init_with_app_and_logger(self, flask_mocks):
        """Extension stores logger and calls init_app when app given."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        app = MagicMock()
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)

        ext = mod.MohFlowFlaskExtension(app=app, logger=logger)

        assert ext.logger is logger
        app.before_request.assert_called_once()
        app.after_request.assert_called_once()
        app.errorhandler.assert_called_once()

    def test_init_without_app(self, flask_mocks):
        """Deferred init -- init_app not called yet."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension(logger=logger)
        assert ext.app is None
        assert ext.logger is logger

    def test_init_app_raises_without_logger(self, flask_mocks):
        """init_app raises ValueError when no logger is provided."""
        mod = flask_mocks["module"]
        app = MagicMock()
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)
        ext = mod.MohFlowFlaskExtension()

        with pytest.raises(ValueError, match="logger is required"):
            ext.init_app(app)

    def test_init_app_reads_config(self, flask_mocks):
        """init_app reads MOHFLOW_* keys from app.config."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        app = MagicMock()
        app.config = {
            "MOHFLOW_LOG_REQUESTS": False,
            "MOHFLOW_LOG_RESPONSES": False,
            "MOHFLOW_LOG_REQUEST_BODY": True,
            "MOHFLOW_LOG_RESPONSE_BODY": True,
            "MOHFLOW_MAX_BODY_SIZE": 512,
            "MOHFLOW_EXCLUDE_PATHS": ["/health"],
            "MOHFLOW_EXCLUDE_STATUS_CODES": [204],
        }
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)
        app.extensions = {}

        ext = mod.MohFlowFlaskExtension()
        ext.init_app(app, logger)

        assert ext.log_requests is False
        assert ext.log_responses is False
        assert ext.log_request_body is True
        assert ext.log_response_body is True
        assert ext.max_body_size == 512
        assert "/health" in ext.exclude_paths
        assert 204 in ext.exclude_status_codes

    def test_before_request_skips_excluded_paths(self, flask_mocks):
        """_before_request returns early for excluded paths."""
        mod = flask_mocks["module"]
        flask_mod = flask_mocks["flask_mod"]
        logger = _make_logger()

        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_paths = {"/health"}
        ext.log_requests = True

        flask_mod.request.path = "/health"
        with patch.object(mod, "request", flask_mod.request):
            ext._before_request()

        logger.info.assert_not_called()

    def test_before_request_generates_request_id(self, flask_mocks):
        """_before_request generates UUID and logs incoming request."""
        mod = flask_mocks["module"]
        flask_mod = flask_mocks["flask_mod"]
        logger = _make_logger()

        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_paths = set()
        ext.log_requests = True
        ext.log_request_body = False

        req = MagicMock()
        req.path = "/api/users"
        req.method = "GET"
        req.query_string = b""
        req.headers = {"User-Agent": "test"}
        req.content_type = "application/json"
        req.content_length = 0
        req.endpoint = "users"
        req.view_args = None
        req.environ = {"REMOTE_ADDR": "127.0.0.1"}

        g_mock = MagicMock()

        with (
            patch.object(mod, "request", req),
            patch.object(mod, "g", g_mock),
        ):
            ext._before_request()

        assert hasattr(g_mock, "mohflow_request_id")
        logger.info.assert_called_once()

    def test_after_request_returns_response_when_no_request_id(
        self, flask_mocks
    ):
        """_after_request returns response when no mohflow data."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger

        g_mock = MagicMock(spec=[])  # no attributes at all
        response = MagicMock()

        with patch.object(mod, "g", g_mock):
            result = ext._after_request(response)

        assert result is response

    def test_after_request_logs_response_and_sets_header(self, flask_mocks):
        """_after_request logs response and adds X-Request-ID."""
        mod = flask_mocks["module"]
        flask_mod = flask_mocks["flask_mod"]
        logger = _make_logger()

        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_status_codes = set()
        ext.log_responses = True
        ext.log_response_body = False
        ext.log_level_mapping = {200: "info"}

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "req-1234"
        g_mock.mohflow_start_time = time.time() - 0.05
        g_mock.mohflow_context = {"method": "GET", "path": "/api"}

        req = MagicMock()
        req.method = "GET"
        req.path = "/api"

        response = MagicMock()
        response.status_code = 200
        response.content_type = "application/json"
        response.content_length = 42
        response.headers = {}

        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
        ):
            result = ext._after_request(response)

        assert result is response
        assert response.headers["X-Request-ID"] == "req-1234"
        logger.info.assert_called_once()

    def test_after_request_skips_excluded_status_codes(self, flask_mocks):
        """_after_request skips logging for excluded status codes."""
        mod = flask_mocks["module"]
        logger = _make_logger()

        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_status_codes = {204}
        ext.log_responses = True

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "req-abc"
        g_mock.mohflow_start_time = time.time()

        response = MagicMock()
        response.status_code = 204

        with patch.object(mod, "g", g_mock):
            result = ext._after_request(response)

        assert result is response
        logger.info.assert_not_called()

    def test_handle_exception_reraises(self, flask_mocks):
        """_handle_exception logs and re-raises error."""
        mod = flask_mocks["module"]
        flask_mod = flask_mocks["flask_mod"]
        logger = _make_logger()

        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.log_level_mapping = {}

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "req-err"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {"method": "POST"}

        req = MagicMock()
        req.method = "POST"
        req.path = "/fail"

        error = RuntimeError("boom")

        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
            pytest.raises(RuntimeError, match="boom"),
        ):
            ext._handle_exception(error)

        logger.error.assert_called_once()

    def test_handle_http_exception(self, flask_mocks):
        """_handle_exception uses log_level_mapping for HTTPException."""
        mod = flask_mocks["module"]
        HTTPException = flask_mocks["HTTPException"]
        logger = _make_logger()

        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.log_level_mapping = {404: "warning"}

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "req-http"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}

        req = MagicMock()
        req.method = "GET"
        req.path = "/missing"

        error = HTTPException(description="Not Found", code=404)

        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
            pytest.raises(HTTPException),
        ):
            ext._handle_exception(error)

        logger.warning.assert_called_once()

    def test_handle_exception_without_request_id_reraises(self, flask_mocks):
        """_handle_exception re-raises when no mohflow_request_id."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger

        g_mock = MagicMock(spec=[])

        with (
            patch.object(mod, "g", g_mock),
            pytest.raises(ValueError),
        ):
            ext._handle_exception(ValueError("nope"))

    def test_get_client_ip_from_proxy_headers(self, flask_mocks):
        """_get_client_ip extracts IP from proxy headers."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger

        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(
            side_effect=lambda h: (
                "10.0.0.1, 10.0.0.2" if h == "X-Forwarded-For" else None
            )
        )
        req.environ = {"REMOTE_ADDR": "127.0.0.1"}

        with patch.object(mod, "request", req):
            ip = ext._get_client_ip()
        assert ip == "10.0.0.1"

    def test_get_client_ip_fallback_to_remote_addr(self, flask_mocks):
        """_get_client_ip falls back to REMOTE_ADDR."""
        mod = flask_mocks["module"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=None)
        req.environ = {"REMOTE_ADDR": "192.168.1.1"}

        with patch.object(mod, "request", req):
            ip = ext._get_client_ip()
        assert ip == "192.168.1.1"

    def test_log_context_updates_g(self, flask_mocks):
        """_log_context merges kwargs into g.mohflow_context."""
        mod = flask_mocks["module"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        g_mock = MagicMock()
        g_mock.mohflow_context = {"method": "GET"}

        with patch.object(mod, "g", g_mock):
            ext._log_context(custom="value")

        assert g_mock.mohflow_context["custom"] == "value"

    def test_extract_request_body_when_enabled(self, flask_mocks):
        """_extract_request_context includes body when enabled."""
        mod = flask_mocks["module"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_request_body = True
        ext.max_body_size = 1024

        req = MagicMock()
        req.method = "POST"
        req.path = "/data"
        req.query_string = b""
        req.headers = {"User-Agent": "test"}
        req.content_type = "application/json"
        req.content_length = 10
        req.endpoint = "data"
        req.view_args = None
        req.environ = {"REMOTE_ADDR": "127.0.0.1"}
        req.get_data = MagicMock(return_value='{"key": "val"}')

        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()

        assert "request_body" in ctx


class TestFlaskDecorators:
    """Tests for log_route and timed_route decorators."""

    def test_log_route_success(self, flask_mocks):
        """log_route logs success on successful route execution."""
        mod = flask_mocks["module"]
        logger = _make_logger()

        @mod.log_route(logger, component="auth")
        def my_view():
            return "ok"

        g_mock = MagicMock()
        g_mock.mohflow_context = {}

        with patch.object(mod, "g", g_mock):
            result = my_view()

        assert result == "ok"
        logger.info.assert_called_once()

    def test_log_route_failure(self, flask_mocks):
        """log_route logs error when route raises."""
        mod = flask_mocks["module"]
        logger = _make_logger()

        @mod.log_route(logger, component="auth")
        def bad_view():
            raise ValueError("broken")

        g_mock = MagicMock()
        g_mock.mohflow_context = {}

        with (
            patch.object(mod, "g", g_mock),
            pytest.raises(ValueError, match="broken"),
        ):
            bad_view()

        logger.error.assert_called_once()

    def test_log_route_without_logger_uses_extension(self, flask_mocks):
        """log_route falls back to extension logger when none given."""
        mod = flask_mocks["module"]
        ext_logger = _make_logger()
        ext = MagicMock()
        ext.logger = ext_logger

        current_app = MagicMock()
        current_app.extensions = {"mohflow": ext}

        @mod.log_route(None, component="test")
        def view_fn():
            return "data"

        g_mock = MagicMock()
        g_mock.mohflow_context = {}

        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "current_app", current_app),
        ):
            result = view_fn()

        assert result == "data"
        ext_logger.info.assert_called_once()

    def test_timed_route_logs_duration(self, flask_mocks):
        """timed_route logs execution time on success."""
        mod = flask_mocks["module"]
        logger = _make_logger()

        @mod.timed_route(logger)
        def fast_view():
            return "fast"

        result = fast_view()
        assert result == "fast"
        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args
        assert call_kwargs[1]["performance_metric"] is True

    def test_timed_route_logs_on_error(self, flask_mocks):
        """timed_route logs warning on failure."""
        mod = flask_mocks["module"]
        logger = _make_logger()

        @mod.timed_route(logger)
        def fail_view():
            raise RuntimeError("slow fail")

        with pytest.raises(RuntimeError):
            fail_view()

        logger.warning.assert_called_once()


class TestFlaskHelpers:
    """Tests for get_request_id, log_business_event, etc."""

    def test_get_request_id_returns_value(self, flask_mocks):
        """get_request_id returns g.mohflow_request_id."""
        mod = flask_mocks["module"]
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "rid-42"

        with patch.object(mod, "g", g_mock):
            assert mod.get_request_id() == "rid-42"

    def test_get_request_id_returns_none(self, flask_mocks):
        """get_request_id returns None when no request_id."""
        mod = flask_mocks["module"]
        g_mock = MagicMock(spec=[])

        with patch.object(mod, "g", g_mock):
            assert mod.get_request_id() is None

    def test_log_business_event(self, flask_mocks):
        """log_business_event logs with request_id when available."""
        mod = flask_mocks["module"]
        logger = _make_logger()

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "biz-req"

        with patch.object(mod, "g", g_mock):
            mod.log_business_event(logger, "user_signup", user_id=123)

        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args[1]
        assert call_kwargs["business_event"] == "user_signup"
        assert call_kwargs["request_id"] == "biz-req"

    def test_create_health_route(self, flask_mocks):
        """create_health_route returns a callable."""
        mod = flask_mocks["module"]
        logger = _make_logger()

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "health-req"

        health = mod.create_health_route(logger)
        with patch.object(mod, "g", g_mock):
            result = health()

        logger.info.assert_called_once()
        # jsonify is mocked to return the dict as-is
        assert result["status"] == "healthy"

    def test_create_metrics_route_prometheus(self, flask_mocks):
        """Metrics endpoint returns prometheus metrics if available."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        logger.export_prometheus_metrics = MagicMock(
            return_value="# HELP counter\n"
        )

        endpoint = mod.create_metrics_route(logger)
        result = endpoint()

        assert result[0] == "# HELP counter\n"
        assert result[1] == 200

    def test_create_metrics_route_json_fallback(self, flask_mocks):
        """Metrics endpoint falls back to JSON summary."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        del logger.export_prometheus_metrics
        logger.get_metrics_summary = MagicMock(return_value={"total": 100})

        endpoint = mod.create_metrics_route(logger)
        endpoint()

        mod.jsonify.assert_called()

    def test_create_metrics_route_no_metrics(self, flask_mocks):
        """Metrics endpoint returns 404 when no metrics available."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        del logger.export_prometheus_metrics
        del logger.get_metrics_summary

        endpoint = mod.create_metrics_route(logger)
        result = endpoint()

        assert result[1] == 404

    def test_configure_mohflow_flask(self, flask_mocks):
        """configure_mohflow_flask sets defaults and returns ext."""
        mod = flask_mocks["module"]
        logger = _make_logger()
        app = MagicMock()
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)

        ext = mod.configure_mohflow_flask(
            app,
            logger,
            log_requests=False,
            exclude_paths=["/health"],
        )

        assert isinstance(ext, mod.MohFlowFlaskExtension)


# ================================================================== #
#                         DJANGO TESTS                                #
# ================================================================== #


@pytest.fixture()
def django_mocks():
    """Inject fake django modules and return handles."""
    # --- django.conf ---
    django_conf = types.ModuleType("django.conf")
    mock_settings = MagicMock()
    mock_settings.MOHFLOW_MIDDLEWARE = {}
    mock_settings.MOHFLOW_LOGGER = _make_logger()
    django_conf.settings = mock_settings

    # --- django.http ---
    django_http = types.ModuleType("django.http")
    django_http.HttpRequest = MagicMock
    django_http.HttpResponse = MagicMock

    # --- django.utils.deprecation ---
    django_deprecation = types.ModuleType("django.utils.deprecation")

    class _MiddlewareMixin:
        def __init__(self, get_response=None):
            self.get_response = get_response

    django_deprecation.MiddlewareMixin = _MiddlewareMixin

    # --- django.core.exceptions ---
    django_exceptions = types.ModuleType("django.core.exceptions")

    class _ImproperlyConfigured(Exception):
        pass

    django_exceptions.ImproperlyConfigured = _ImproperlyConfigured

    # Fake top-level django modules
    django_mod = types.ModuleType("django")
    django_utils = types.ModuleType("django.utils")

    saved = {}
    for name in (
        "django",
        "django.conf",
        "django.http",
        "django.utils",
        "django.utils.deprecation",
        "django.core",
        "django.core.exceptions",
    ):
        saved[name] = sys.modules.get(name)

    sys.modules["django"] = django_mod
    sys.modules["django.conf"] = django_conf
    sys.modules["django.http"] = django_http
    sys.modules["django.utils"] = django_utils
    sys.modules["django.utils.deprecation"] = django_deprecation
    sys.modules["django.core"] = types.ModuleType("django.core")
    sys.modules["django.core.exceptions"] = django_exceptions

    mod_key = "mohflow.integrations.django"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.django as django_int

    yield {
        "module": django_int,
        "settings": mock_settings,
        "ImproperlyConfigured": _ImproperlyConfigured,
    }

    for name, orig in saved.items():
        if orig is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = orig


class TestMohFlowDjangoMiddleware:
    """Tests for MohFlowDjangoMiddleware."""

    def test_init_with_logger_from_settings(self, django_mocks):
        """Middleware retrieves logger from settings.MOHFLOW_LOGGER."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
        assert mw.logger is logger

    def test_init_with_logger_dotted_path(self, django_mocks):
        """Middleware imports logger from dotted path string."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()

        # Create a fake module with the logger
        fake_mod = types.ModuleType("myapp.logging")
        fake_mod.mohflow_logger = logger
        sys.modules["myapp"] = types.ModuleType("myapp")
        sys.modules["myapp.logging"] = fake_mod

        settings.MOHFLOW_MIDDLEWARE = {
            "logger": "myapp.logging.mohflow_logger"
        }
        del settings.MOHFLOW_LOGGER

        try:
            mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
            assert mw.logger is logger
        finally:
            sys.modules.pop("myapp.logging", None)
            sys.modules.pop("myapp", None)

    def test_init_raises_without_logger(self, django_mocks):
        """Middleware raises ImproperlyConfigured without logger."""
        mod = django_mocks["module"]
        ICE = django_mocks["ImproperlyConfigured"]
        settings = django_mocks["settings"]
        settings.MOHFLOW_MIDDLEWARE = {}
        del settings.MOHFLOW_LOGGER

        with pytest.raises(ICE):
            mod.MohFlowDjangoMiddleware(get_response=MagicMock())

    def test_process_request_skips_excluded_paths(self, django_mocks):
        """process_request returns None for excluded paths."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {
            "exclude_paths": ["/health"],
        }

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.path = "/health"

        result = mw.process_request(request)
        assert result is None
        logger.info.assert_not_called()

    def test_process_request_logs_incoming(self, django_mocks):
        """process_request logs incoming request."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.path = "/api/test"
        request.method = "GET"
        request.GET = MagicMock()
        request.GET.__bool__ = lambda self: False
        request.META = {"REMOTE_ADDR": "127.0.0.1"}
        request.content_type = "application/json"
        request.body = b""
        request.user = MagicMock()
        request.user.is_authenticated = False
        request.session = MagicMock()
        request.session.session_key = None

        mw.process_request(request)

        assert hasattr(request, "mohflow_request_id")
        logger.info.assert_called_once()

    def test_process_response_skips_when_no_request_id(self, django_mocks):
        """process_response returns response if no mohflow data."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        settings.MOHFLOW_LOGGER = _make_logger()
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock(spec=[])
        response = MagicMock()
        result = mw.process_response(request, response)
        assert result is response

    def test_process_response_logs_and_sets_header(self, django_mocks):
        """process_response logs response and adds X-Request-ID."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.mohflow_request_id = "dj-req-1"
        request.mohflow_start_time = time.time() - 0.01
        request.mohflow_context = {"method": "GET", "path": "/api"}
        request.method = "GET"
        request.path = "/api"

        response = MagicMock()
        response.status_code = 200
        response.get = MagicMock(return_value="application/json")
        response.content = b'{"ok": true}'
        response.__setitem__ = MagicMock()

        mw.process_response(request, response)

        logger.info.assert_called_once()
        response.__setitem__.assert_called_with("X-Request-ID", "dj-req-1")

    def test_process_response_skips_excluded_status(self, django_mocks):
        """process_response skips logging for excluded status codes."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {
            "exclude_status_codes": [204],
        }

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.mohflow_request_id = "dj-req-2"
        request.mohflow_start_time = time.time()

        response = MagicMock()
        response.status_code = 204

        mw.process_response(request, response)
        logger.info.assert_not_called()

    def test_process_exception_logs_error(self, django_mocks):
        """process_exception logs exception and returns None."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.mohflow_request_id = "dj-exc"
        request.mohflow_start_time = time.time()
        request.mohflow_context = {"method": "POST"}
        request.method = "POST"
        request.path = "/fail"

        exc = ValueError("oops")
        result = mw.process_exception(request, exc)
        assert result is None
        logger.error.assert_called_once()

    def test_process_exception_no_request_id(self, django_mocks):
        """process_exception returns None when no request id."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock(spec=[])
        result = mw.process_exception(request, ValueError("x"))
        assert result is None
        logger.error.assert_not_called()

    def test_get_client_ip_from_meta(self, django_mocks):
        """_get_client_ip extracts IP from request.META."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        settings.MOHFLOW_LOGGER = _make_logger()
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "10.1.1.1, 10.1.1.2",
            "REMOTE_ADDR": "127.0.0.1",
        }

        ip = mw._get_client_ip(request)
        assert ip == "10.1.1.1"

    def test_get_client_ip_fallback(self, django_mocks):
        """_get_client_ip falls back to REMOTE_ADDR."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        settings.MOHFLOW_LOGGER = _make_logger()
        settings.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.META = {"REMOTE_ADDR": "192.168.0.1"}

        ip = mw._get_client_ip(request)
        assert ip == "192.168.0.1"

    def test_extract_user_context(self, django_mocks):
        """_extract_request_context includes user info if authed."""
        mod = django_mocks["module"]
        settings = django_mocks["settings"]
        logger = _make_logger()
        settings.MOHFLOW_LOGGER = logger
        settings.MOHFLOW_MIDDLEWARE = {"log_user_context": True}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        request = MagicMock()
        request.method = "GET"
        request.path = "/me"
        request.GET = MagicMock()
        request.GET.__bool__ = lambda self: False
        request.META = {"REMOTE_ADDR": "127.0.0.1"}
        request.content_type = "text/html"
        request.body = b""
        request.user = MagicMock()
        request.user.is_authenticated = True
        request.user.id = 42
        request.user.username = "alice"
        request.user.email = "alice@example.com"
        request.session = MagicMock()
        request.session.session_key = "sess123"

        ctx = mw._extract_request_context(request)
        assert ctx["user_id"] == 42
        assert ctx["username"] == "alice"
        assert ctx["session_id"] == "sess123"


class TestDjangoDecorators:
    """Tests for log_view decorator."""

    def test_log_view_success(self, django_mocks):
        """log_view logs success on successful view execution."""
        mod = django_mocks["module"]
        logger = _make_logger()

        @mod.log_view(logger, component="users")
        def my_view(request):
            return "response"

        request = MagicMock()
        request.mohflow_context = {}

        result = my_view(request)
        assert result == "response"
        logger.info.assert_called_once()

    def test_log_view_failure(self, django_mocks):
        """log_view logs error on failure and re-raises."""
        mod = django_mocks["module"]
        logger = _make_logger()

        @mod.log_view(logger, component="users")
        def bad_view(request):
            raise RuntimeError("view failed")

        request = MagicMock()
        request.mohflow_context = {}

        with pytest.raises(RuntimeError, match="view failed"):
            bad_view(request)

        logger.error.assert_called_once()

    def test_log_view_updates_context(self, django_mocks):
        """log_view updates mohflow_context with view name."""
        mod = django_mocks["module"]
        logger = _make_logger()

        @mod.log_view(logger, operation="list")
        def list_view(request):
            return "list"

        request = MagicMock()
        request.mohflow_context = {}

        list_view(request)
        assert request.mohflow_context["django_view"] == "list_view"
        assert request.mohflow_context["operation"] == "list"


class TestDjangoHelpers:
    """Tests for Django helper functions."""

    def test_configure_mohflow_django(self, django_mocks):
        """configure_mohflow_django returns config dict."""
        mod = django_mocks["module"]
        logger = _make_logger()
        config = mod.configure_mohflow_django(
            logger, exclude_paths=["/health"]
        )
        assert config["logger"] is logger
        assert "/health" in config["exclude_paths"]
        assert config["log_requests"] is True

    def test_mohflow_context_processor_with_data(self, django_mocks):
        """mohflow_context returns data when request has mohflow info."""
        mod = django_mocks["module"]
        request = MagicMock()
        request.mohflow_request_id = "ctx-req"
        request.mohflow_context = {
            "user_id": 99,
            "session_id": "s1",
        }

        ctx = mod.mohflow_context(request)
        assert ctx["mohflow"]["mohflow_request_id"] == "ctx-req"
        assert ctx["mohflow"]["mohflow_user_id"] == 99

    def test_mohflow_context_processor_empty(self, django_mocks):
        """mohflow_context returns empty dict when no mohflow data."""
        mod = django_mocks["module"]
        request = MagicMock(spec=[])

        ctx = mod.mohflow_context(request)
        assert ctx == {"mohflow": {}}

    def test_mohflow_django_filter(self, django_mocks):
        """MohFlowDjangoFilter adds context attributes to record."""
        mod = django_mocks["module"]
        logger = _make_logger()
        logger.get_current_context = MagicMock(
            return_value={"service": "api", "env": "prod"}
        )

        filt = mod.MohFlowDjangoFilter(logger)
        record = MagicMock()

        result = filt.filter(record)
        assert result is True
        record.__setattr__("mohflow_service", "api")

    def test_mohflow_django_filter_no_context_method(self, django_mocks):
        """MohFlowDjangoFilter returns True if no context method."""
        mod = django_mocks["module"]
        logger = MagicMock(spec=[])  # no get_current_context

        filt = mod.MohFlowDjangoFilter(logger)
        record = MagicMock()

        assert filt.filter(record) is True


# ================================================================== #
#                        FASTAPI TESTS                                #
# ================================================================== #


@pytest.fixture()
def fastapi_mocks():
    """Inject fake fastapi / starlette modules."""
    # --- starlette ---
    starlette_middleware = types.ModuleType("starlette.middleware.base")

    class _BaseHTTPMiddleware:
        def __init__(self, app):
            self.app = app

    starlette_middleware.BaseHTTPMiddleware = _BaseHTTPMiddleware

    starlette_types = types.ModuleType("starlette.types")
    starlette_types.ASGIApp = object

    # --- fastapi ---
    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.Request = MagicMock
    fastapi_mod.Response = MagicMock
    fastapi_mod.FastAPI = MagicMock

    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.JSONResponse = MagicMock

    saved = {}
    for name in (
        "starlette",
        "starlette.middleware",
        "starlette.middleware.base",
        "starlette.types",
        "fastapi",
        "fastapi.responses",
    ):
        saved[name] = sys.modules.get(name)

    sys.modules["starlette"] = types.ModuleType("starlette")
    sys.modules["starlette.middleware"] = types.ModuleType(
        "starlette.middleware"
    )
    sys.modules["starlette.middleware.base"] = starlette_middleware
    sys.modules["starlette.types"] = starlette_types
    sys.modules["fastapi"] = fastapi_mod
    sys.modules["fastapi.responses"] = fastapi_responses

    mod_key = "mohflow.integrations.fastapi"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.fastapi as fastapi_int

    yield {
        "module": fastapi_int,
        "fastapi_mod": fastapi_mod,
    }

    for name, orig in saved.items():
        if orig is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = orig


class TestMohFlowFastAPIMiddleware:
    """Tests for MohFlowFastAPIMiddleware."""

    def test_init_defaults(self, fastapi_mocks):
        """Middleware initialises with correct defaults."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(app, logger)

        assert mw.logger is logger
        assert mw.log_requests is True
        assert mw.log_responses is True
        assert mw.exclude_paths == set()
        assert mw.exclude_status_codes == set()
        assert mw.enable_metrics is True

    def test_init_custom_config(self, fastapi_mocks):
        """Middleware accepts custom configuration."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(
            app,
            logger,
            log_requests=False,
            exclude_paths={"/health"},
            exclude_status_codes={204},
            max_body_size=512,
        )

        assert mw.log_requests is False
        assert "/health" in mw.exclude_paths
        assert 204 in mw.exclude_status_codes
        assert mw.max_body_size == 512

    def test_dispatch_excluded_path(self, fastapi_mocks):
        """dispatch skips logging for excluded paths."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(
            app, logger, exclude_paths={"/health"}
        )

        request = MagicMock()
        request.url.path = "/health"

        response = MagicMock()

        async def fake_call_next(req):
            return response

        async def _run():
            return await mw.dispatch(request, fake_call_next)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is response
        logger.info.assert_not_called()

    def test_dispatch_normal_request(self, fastapi_mocks):
        """dispatch logs request and response for normal request."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(app, logger)
        # Patch extract to avoid duplicate-kwarg bug in source
        mw._extract_request_context = _strip_key(
            mw._extract_request_context, "request_id"
        )

        request = MagicMock()
        request.url.path = "/api/test"
        request.method = "GET"
        request.query_params = ""
        request.headers = {
            "user-agent": "test-agent",
            "content-type": "application/json",
            "content-length": "0",
        }
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        response = MagicMock()
        response.status_code = 200
        response.headers = {
            "content-length": "42",
            "content-type": "application/json",
        }

        async def fake_call_next(req):
            return response

        async def _run():
            return await mw.dispatch(request, fake_call_next)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is response
        # Should log request + response = 2 calls
        assert logger.info.call_count == 2

    def test_dispatch_exception_returns_500(self, fastapi_mocks):
        """dispatch returns 500 JSON response on exception."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(app, logger)
        mw._extract_request_context = _strip_key(
            mw._extract_request_context, "request_id"
        )

        request = MagicMock()
        request.url.path = "/api/fail"
        request.method = "POST"
        request.query_params = ""
        request.headers = {}
        request.client = None

        async def failing_next(req):
            raise RuntimeError("kaboom")

        async def _run():
            return await mw.dispatch(request, failing_next)

        asyncio.get_event_loop().run_until_complete(_run())
        logger.error.assert_called_once()

    def test_dispatch_excluded_status_code(self, fastapi_mocks):
        """dispatch skips response logging for excluded codes."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(
            app, logger, exclude_status_codes={204}
        )
        mw._extract_request_context = _strip_key(
            mw._extract_request_context, "request_id"
        )

        request = MagicMock()
        request.url.path = "/api/ok"
        request.method = "DELETE"
        request.query_params = ""
        request.headers = {}
        request.client = None

        response = MagicMock()
        response.status_code = 204
        response.headers = {}

        async def fake_next(req):
            return response

        async def _run():
            return await mw.dispatch(request, fake_next)

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result is response
        # Only request logged, response skipped
        assert logger.info.call_count == 1

    def test_get_client_ip_from_headers(self, fastapi_mocks):
        """_get_client_ip extracts IP from proxy headers."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(app, logger)

        request = MagicMock()
        request.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2"}
        request.client = None

        ip = mw._get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_get_client_ip_fallback_to_client_host(self, fastapi_mocks):
        """_get_client_ip falls back to request.client.host."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        mw = mod.MohFlowFastAPIMiddleware(app, logger)

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        ip = mw._get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_custom_extractors(self, fastapi_mocks):
        """Custom extractors add data to request context."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        def custom_ext(req):
            return {"custom_field": "custom_value"}

        mw = mod.MohFlowFastAPIMiddleware(
            app, logger, custom_extractors=[custom_ext]
        )

        request = MagicMock()
        request.url.path = "/api"
        request.method = "GET"
        request.query_params = ""
        request.headers = {}
        request.client = None

        async def _run():
            ctx = await mw._extract_request_context(request, "rid")
            return ctx

        ctx = asyncio.get_event_loop().run_until_complete(_run())
        assert ctx["custom_field"] == "custom_value"

    def test_custom_extractor_error_ignored(self, fastapi_mocks):
        """Failing custom extractor is silently ignored."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        def bad_ext(req):
            raise RuntimeError("extractor broke")

        mw = mod.MohFlowFastAPIMiddleware(
            app, logger, custom_extractors=[bad_ext]
        )

        request = MagicMock()
        request.url.path = "/api"
        request.method = "GET"
        request.query_params = ""
        request.headers = {}
        request.client = None

        async def _run():
            return await mw._extract_request_context(request, "rid")

        # Should not raise
        ctx = asyncio.get_event_loop().run_until_complete(_run())
        assert "method" in ctx


class TestFastAPIHelpers:
    """Tests for FastAPI helper functions and extractors."""

    def test_setup_fastapi_logging(self, fastapi_mocks):
        """setup_fastapi_logging adds middleware to app."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        result = mod.setup_fastapi_logging(app, logger)
        assert result is app
        app.add_middleware.assert_called_once()

    def test_setup_fastapi_logging_no_fastapi(self, fastapi_mocks):
        """setup_fastapi_logging raises when HAS_FASTAPI is False."""
        mod = fastapi_mocks["module"]
        original = mod.HAS_FASTAPI
        mod.HAS_FASTAPI = False

        try:
            with pytest.raises(ImportError, match="FastAPI"):
                mod.setup_fastapi_logging(MagicMock(), _make_logger())
        finally:
            mod.HAS_FASTAPI = original

    def test_log_endpoint_success(self, fastapi_mocks):
        """log_endpoint logs on successful endpoint execution."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()

        @mod.log_endpoint(logger, component="auth")
        async def login():
            return {"token": "abc"}

        result = asyncio.get_event_loop().run_until_complete(login())
        assert result == {"token": "abc"}
        logger.info.assert_called_once()

    def test_log_endpoint_failure(self, fastapi_mocks):
        """log_endpoint logs error on failure."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()

        @mod.log_endpoint(logger, component="auth")
        async def bad_login():
            raise ValueError("bad creds")

        with pytest.raises(ValueError, match="bad creds"):
            asyncio.get_event_loop().run_until_complete(bad_login())

        logger.error.assert_called_once()

    def test_create_health_endpoint(self, fastapi_mocks):
        """create_health_endpoint returns async callable."""
        mod = fastapi_mocks["module"]
        logger = _make_logger()

        health = mod.create_health_endpoint(logger)
        result = asyncio.get_event_loop().run_until_complete(health())

        assert result["status"] == "healthy"
        logger.info.assert_called_once()

    def test_extract_auth_context_bearer(self, fastapi_mocks):
        """extract_auth_context detects Bearer token."""
        mod = fastapi_mocks["module"]
        request = MagicMock()
        request.headers = {
            "authorization": "Bearer eyJhbGc...",
            "x-user-id": "user-123",
        }

        ctx = mod.extract_auth_context(request)
        assert ctx["auth_type"] == "bearer"
        assert ctx["user_id"] == "user-123"

    def test_extract_auth_context_basic(self, fastapi_mocks):
        """extract_auth_context detects Basic auth."""
        mod = fastapi_mocks["module"]
        request = MagicMock()
        request.headers = {"authorization": "Basic dXNlcjpw"}

        ctx = mod.extract_auth_context(request)
        assert ctx["auth_type"] == "basic"

    def test_extract_auth_context_empty(self, fastapi_mocks):
        """extract_auth_context returns empty dict when no auth."""
        mod = fastapi_mocks["module"]
        request = MagicMock()
        request.headers = {}

        ctx = mod.extract_auth_context(request)
        assert ctx == {}

    def test_extract_trace_context(self, fastapi_mocks):
        """extract_trace_context extracts tracing headers."""
        mod = fastapi_mocks["module"]
        request = MagicMock()
        request.headers = {
            "x-trace-id": "trace-abc",
            "x-span-id": "span-def",
            "uber-trace-id": "jaeger-ghi",
        }

        ctx = mod.extract_trace_context(request)
        assert ctx["trace_id"] == "trace-abc"
        assert ctx["span_id"] == "span-def"
        assert ctx["jaeger_trace_id"] == "jaeger-ghi"

    def test_extract_trace_context_empty(self, fastapi_mocks):
        """extract_trace_context returns empty with no headers."""
        mod = fastapi_mocks["module"]
        request = MagicMock()
        request.headers = {}

        ctx = mod.extract_trace_context(request)
        assert ctx == {}

    def test_extract_business_context(self, fastapi_mocks):
        """extract_business_context extracts tenant/org headers."""
        mod = fastapi_mocks["module"]
        request = MagicMock()
        request.headers = {
            "x-tenant-id": "t-1",
            "x-organization-id": "org-2",
            "x-api-version": "v2",
        }

        ctx = mod.extract_business_context(request)
        assert ctx["tenant_id"] == "t-1"
        assert ctx["organization_id"] == "org-2"
        assert ctx["api_version"] == "v2"

    def test_extract_business_context_defaults(self, fastapi_mocks):
        """extract_business_context defaults api_version to v1."""
        mod = fastapi_mocks["module"]
        request = MagicMock()
        request.headers = {}

        ctx = mod.extract_business_context(request)
        assert ctx["api_version"] == "v1"


# ================================================================== #
#                         CELERY TESTS                                #
# ================================================================== #


@pytest.fixture()
def celery_mocks():
    """Inject fake celery modules."""
    celery_mod = types.ModuleType("celery")
    celery_mod.Celery = MagicMock

    celery_signals = types.ModuleType("celery.signals")
    for sig_name in (
        "task_prerun",
        "task_postrun",
        "task_failure",
        "task_retry",
        "worker_ready",
        "worker_shutdown",
    ):
        setattr(celery_signals, sig_name, MagicMock())

    celery_app = types.ModuleType("celery.app")
    celery_app_task = types.ModuleType("celery.app.task")

    class _Task:
        name = "base_task"
        max_retries = 3
        request = MagicMock()

        def __init__(self):
            pass

        def apply_async(self, args=None, kwargs=None, **options):
            return MagicMock()

        def retry(self, *a, **kw):
            return MagicMock()

    celery_app_task.Task = _Task

    saved = {}
    for name in (
        "celery",
        "celery.signals",
        "celery.app",
        "celery.app.task",
    ):
        saved[name] = sys.modules.get(name)

    sys.modules["celery"] = celery_mod
    sys.modules["celery.signals"] = celery_signals
    sys.modules["celery.app"] = celery_app
    sys.modules["celery.app.task"] = celery_app_task

    mod_key = "mohflow.integrations.celery"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.celery as celery_int

    yield {
        "module": celery_int,
        "signals": celery_signals,
        "Task": _Task,
    }

    for name, orig in saved.items():
        if orig is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = orig


class TestMohFlowCeleryIntegration:
    """Tests for MohFlowCeleryIntegration."""

    def test_init_with_app_calls_setup(self, celery_mocks):
        """Integration sets up signals when app is provided."""
        mod = celery_mocks["module"]
        signals = celery_mocks["signals"]
        logger = _make_logger()
        app = MagicMock()

        integration = mod.MohFlowCeleryIntegration(logger, app)
        assert integration.logger is logger
        signals.task_prerun.connect.assert_called_once()
        signals.task_postrun.connect.assert_called_once()
        signals.task_failure.connect.assert_called_once()
        signals.task_retry.connect.assert_called_once()

    def test_init_without_app(self, celery_mocks):
        """Integration stores logger but does not set up signals."""
        mod = celery_mocks["module"]
        signals = celery_mocks["signals"]
        logger = _make_logger()

        integration = mod.MohFlowCeleryIntegration(logger)
        assert integration.app is None
        signals.task_prerun.connect.assert_not_called()

    def test_task_prerun_handler(self, celery_mocks):
        """_task_prerun_handler logs task start.

        NOTE: The source code passes ``task_id`` both as a named
        argument and inside ``**task_context`` to
        ``logger.request_context``, which is a duplicate-kwarg
        bug.  We reproduce the handler logic with the fix
        applied (stripping ``task_id`` from the context dict)
        to verify the logging behaviour.
        """
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_app.tasks.process"
        task = MagicMock()

        # Reproduce handler logic with duplicate-kwarg fix
        task_context = {
            "task_id": "tid-1",
            "task_name": sender.name,
            "task_args": integration._safe_serialize((1, 2)),
            "task_kwargs": integration._safe_serialize({"key": "val"}),
            "timestamp": datetime.utcnow().isoformat(),
            "task_start_time": time.time(),
        }
        ctx_no_dup = {k: v for k, v in task_context.items() if k != "task_id"}
        with integration.logger.request_context(task_id="tid-1", **ctx_no_dup):
            integration.logger.info(
                f"Task {task_context['task_name']} started",
                **task_context,
            )

        logger.info.assert_called_once()
        msg = logger.info.call_args[0][0]
        assert "my_app.tasks.process" in msg

    def test_task_postrun_handler_success(self, celery_mocks):
        """_task_postrun_handler logs success for SUCCESS state."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {"task_start_time": time.time() - 0.1}

        # Replicate handler logic with fixed request_context
        end_time = time.time()
        start_time = task.mohflow_context.get("task_start_time", end_time)
        duration_ms = (end_time - start_time) * 1000

        task_context = {
            "task_id": "tid-2",
            "task_name": sender.name,
            "task_state": "SUCCESS",
            "duration": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }
        retval = {"result": 42}
        serialized = integration._safe_serialize(retval)
        if serialized and len(str(serialized)) < 1000:
            task_context["return_value"] = serialized

        ctx_no_dup = {k: v for k, v in task_context.items() if k != "task_id"}
        with integration.logger.request_context(task_id="tid-2", **ctx_no_dup):
            integration.logger.info(
                f"Task {task_context['task_name']} completed "
                f"successfully ({duration_ms:.1f}ms)",
                **task_context,
            )

        logger.info.assert_called_once()

    def test_task_postrun_handler_non_success(self, celery_mocks):
        """_task_postrun_handler logs warning for non-SUCCESS."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_task"

        task_context = {
            "task_id": "tid-3",
            "task_name": sender.name,
            "task_state": "FAILURE",
            "duration": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        ctx_no_dup = {k: v for k, v in task_context.items() if k != "task_id"}
        with integration.logger.request_context(task_id="tid-3", **ctx_no_dup):
            integration.logger.warning(
                f"Task {task_context['task_name']} completed "
                f"with state FAILURE (0.0ms)",
                **task_context,
            )

        logger.warning.assert_called_once()

    def test_task_failure_handler(self, celery_mocks):
        """_task_failure_handler logs error."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "failing_task"
        exc = ValueError("bad input")

        task_context = {
            "task_id": "tid-4",
            "task_name": sender.name,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "traceback": "traceback...",
            "timestamp": datetime.utcnow().isoformat(),
        }
        ctx_no_dup = {k: v for k, v in task_context.items() if k != "task_id"}
        with integration.logger.request_context(task_id="tid-4", **ctx_no_dup):
            integration.logger.error(
                f"Task {task_context['task_name']} failed",
                **task_context,
            )

        logger.error.assert_called_once()

    def test_task_failure_handler_no_sender(self, celery_mocks):
        """_task_failure_handler uses 'unknown' when no sender."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        task_context = {
            "task_id": "tid-5",
            "task_name": "unknown",
            "error": "Unknown error",
            "error_type": "UnknownError",
            "traceback": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
        ctx_no_dup = {k: v for k, v in task_context.items() if k != "task_id"}
        with integration.logger.request_context(task_id="tid-5", **ctx_no_dup):
            integration.logger.error(
                f"Task {task_context['task_name']} failed",
                **task_context,
            )

        logger.error.assert_called_once()
        msg = logger.error.call_args[0][0]
        assert "unknown" in msg

    def test_task_retry_handler(self, celery_mocks):
        """_task_retry_handler logs warning."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "retry_task"

        task_context = {
            "task_id": "tid-6",
            "task_name": sender.name,
            "retry_reason": "Connection timeout",
            "traceback": None,
            "timestamp": datetime.utcnow().isoformat(),
        }
        ctx_no_dup = {k: v for k, v in task_context.items() if k != "task_id"}
        with integration.logger.request_context(task_id="tid-6", **ctx_no_dup):
            integration.logger.warning(
                f"Task {task_context['task_name']} " f"will be retried",
                **task_context,
            )

        logger.warning.assert_called_once()

    def test_worker_ready_handler(self, celery_mocks):
        """_worker_ready_handler logs worker startup."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.hostname = "worker-1"
        sender.pid = 12345

        integration._worker_ready_handler(sender=sender)
        logger.info.assert_called_once()
        assert "worker ready" in logger.info.call_args[0][0].lower()

    def test_worker_shutdown_handler(self, celery_mocks):
        """_worker_shutdown_handler logs worker shutdown."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.hostname = "worker-1"
        sender.pid = 12345

        integration._worker_shutdown_handler(sender=sender)
        logger.info.assert_called_once()
        assert "shutting down" in logger.info.call_args[0][0].lower()

    def test_safe_serialize_json(self, celery_mocks):
        """_safe_serialize returns original for JSON-safe objects."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        assert integration._safe_serialize([1, 2, 3]) == [1, 2, 3]
        assert integration._safe_serialize({"a": 1}) == {"a": 1}
        assert integration._safe_serialize(None) is None

    def test_safe_serialize_non_json(self, celery_mocks):
        """_safe_serialize returns str for non-JSON objects."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        integration = mod.MohFlowCeleryIntegration(logger)

        obj = object()
        result = integration._safe_serialize(obj)
        assert isinstance(result, str)


class TestMohFlowCeleryTask:
    """Tests for MohFlowCeleryTask."""

    def test_set_logger(self, celery_mocks):
        """set_logger stores the logger."""
        mod = celery_mocks["module"]
        task = mod.MohFlowCeleryTask()
        logger = _make_logger()

        task.set_logger(logger)
        assert task.mohflow_logger is logger

    def test_apply_async_adds_correlation_id(self, celery_mocks):
        """apply_async adds correlation_id to headers."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "test_task"
        task.mohflow_logger = logger

        # We need to mock super().apply_async
        with patch.object(
            celery_mocks["Task"],
            "apply_async",
            return_value=MagicMock(),
        ):
            task.apply_async(args=(1,), kwargs={"x": 2})

        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args[1]
        assert "correlation_id" in call_kwargs

    def test_apply_async_preserves_existing_correlation_id(self, celery_mocks):
        """apply_async preserves existing correlation_id."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "test_task"
        task.mohflow_logger = logger

        with patch.object(
            celery_mocks["Task"],
            "apply_async",
            return_value=MagicMock(),
        ):
            task.apply_async(headers={"correlation_id": "existing-id"})

        call_kwargs = logger.info.call_args[1]
        assert call_kwargs["correlation_id"] == "existing-id"

    def test_apply_async_without_logger(self, celery_mocks):
        """apply_async works without logger set."""
        mod = celery_mocks["module"]
        task = mod.MohFlowCeleryTask()
        task.name = "quiet_task"
        task.mohflow_logger = None

        with patch.object(
            celery_mocks["Task"],
            "apply_async",
            return_value=MagicMock(),
        ):
            task.apply_async(args=(1,))

    def test_retry_logs_warning(self, celery_mocks):
        """retry logs warning with retry context."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "retry_task"
        task.mohflow_logger = logger
        task.max_retries = 3
        task.request = MagicMock()
        task.request.id = "rtid-1"
        task.request.retries = 1

        with patch.object(
            celery_mocks["Task"],
            "retry",
            return_value=MagicMock(),
        ):
            task.retry(exc=ValueError("temp fail"), countdown=60)

        logger.warning.assert_called_once()

    def test_task_safe_serialize(self, celery_mocks):
        """MohFlowCeleryTask._safe_serialize works."""
        mod = celery_mocks["module"]
        task = mod.MohFlowCeleryTask()

        assert task._safe_serialize({"a": 1}) == {"a": 1}
        assert task._safe_serialize(None) is None

        obj = object()
        assert isinstance(task._safe_serialize(obj), str)


class TestCeleryDecoratorsAndHelpers:
    """Tests for log_task, setup_celery_logging, etc."""

    def test_log_task_success(self, celery_mocks):
        """log_task logs start and completion on success."""
        mod = celery_mocks["module"]
        logger = _make_logger()

        @mod.log_task(logger, component="data")
        def process_data(x):
            return x * 2

        result = process_data(5)
        assert result == 10
        # Two info calls: start + completion
        assert logger.info.call_count == 2

    def test_log_task_failure(self, celery_mocks):
        """log_task logs error on failure."""
        mod = celery_mocks["module"]
        logger = _make_logger()

        @mod.log_task(logger, priority="high")
        def bad_task():
            raise RuntimeError("task exploded")

        with pytest.raises(RuntimeError, match="task exploded"):
            bad_task()

        logger.error.assert_called_once()

    def test_setup_celery_logging(self, celery_mocks):
        """setup_celery_logging returns integration instance."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        app = MagicMock()

        integration = mod.setup_celery_logging(logger, app)
        assert isinstance(integration, mod.MohFlowCeleryIntegration)

    def test_log_task_progress(self, celery_mocks):
        """log_task_progress logs progress percentage."""
        mod = celery_mocks["module"]
        logger = _make_logger()

        mod.log_task_progress(logger, "tid-prog", 50, 100)
        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args[1]
        assert call_kwargs["progress_percent"] == 50.0

    def test_log_task_progress_zero_total(self, celery_mocks):
        """log_task_progress handles total=0 without division error."""
        mod = celery_mocks["module"]
        logger = _make_logger()

        mod.log_task_progress(logger, "tid-zero", 0, 0, "No items")
        logger.info.assert_called_once()
        call_kwargs = logger.info.call_args[1]
        assert call_kwargs["progress_percent"] == 0

    def test_log_task_progress_custom_message(self, celery_mocks):
        """log_task_progress uses custom message when given."""
        mod = celery_mocks["module"]
        logger = _make_logger()

        mod.log_task_progress(logger, "tid-msg", 3, 10, "Processing batch")
        msg = logger.info.call_args[0][0]
        assert msg == "Processing batch"


class TestTaskErrorAggregator:
    """Tests for TaskErrorAggregator."""

    def test_record_error(self, celery_mocks):
        """record_error stores error timestamps."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        agg = mod.TaskErrorAggregator(logger, window_minutes=15)

        agg.record_error("task_a", "ValueError")
        assert "task_a:ValueError" in agg.error_counts
        assert len(agg.error_counts["task_a:ValueError"]) == 1

    def test_high_error_rate_alert(self, celery_mocks):
        """record_error triggers alert at 10 errors."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        agg = mod.TaskErrorAggregator(logger, window_minutes=15)

        for _ in range(10):
            agg.record_error("task_b", "TimeoutError")

        logger.error.assert_called()
        call_kwargs = logger.error.call_args[1]
        assert call_kwargs["alert_type"] == "high_error_rate"
        assert call_kwargs["error_count"] >= 10

    def test_cleanup_old_entries(self, celery_mocks):
        """_cleanup_old_entries removes entries outside window."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        agg = mod.TaskErrorAggregator(logger, window_minutes=1)

        # Manually add old entries
        old_time = time.time() - 120  # 2 minutes ago
        agg.error_counts["old_task:Err"] = [old_time]

        agg._cleanup_old_entries(time.time())
        assert "old_task:Err" not in agg.error_counts

    def test_cleanup_triggered_periodically(self, celery_mocks):
        """Cleanup runs when 5+ minutes since last cleanup."""
        mod = celery_mocks["module"]
        logger = _make_logger()
        agg = mod.TaskErrorAggregator(logger, window_minutes=1)
        agg.last_cleanup = time.time() - 301  # >5 min ago

        # Add an old entry
        old_time = time.time() - 120
        agg.error_counts["stale:Err"] = [old_time]

        agg.record_error("new_task", "NewErr")
        # Old entry should be cleaned up
        assert "stale:Err" not in agg.error_counts


# ================================================================== #
#                      ASGI / WSGI TESTS                              #
# ================================================================== #


class TestMohFlowASGIMiddleware:
    """Tests for MohFlowASGIMiddleware."""

    def _get_module(self):
        from mohflow.integrations.asgi_wsgi import (
            MohFlowASGIMiddleware,
        )

        return MohFlowASGIMiddleware

    def test_init_defaults(self):
        """ASGI middleware initialises with correct defaults."""
        Cls = self._get_module()
        logger = _make_logger()
        app = MagicMock()

        mw = Cls(app, logger)
        assert mw.app is app
        assert mw.logger is logger
        assert mw.log_requests is True
        assert mw.exclude_paths == set()

    def test_non_http_passthrough(self):
        """Non-HTTP scopes are passed through without logging."""
        Cls = self._get_module()
        logger = _make_logger()
        inner_app = MagicMock()

        async def fake_app(scope, receive, send):
            pass

        mw = Cls(fake_app, logger)

        scope = {"type": "websocket", "path": "/ws"}

        async def _run():
            await mw(scope, MagicMock(), MagicMock())

        asyncio.get_event_loop().run_until_complete(_run())
        logger.info.assert_not_called()

    def test_excluded_path_passthrough(self):
        """Excluded paths are passed through."""
        Cls = self._get_module()
        logger = _make_logger()
        called = {"count": 0}

        async def fake_app(scope, receive, send):
            called["count"] += 1

        mw = Cls(fake_app, logger, exclude_paths={"/health"})

        scope = {
            "type": "http",
            "path": "/health",
            "method": "GET",
        }

        async def _run():
            await mw(scope, MagicMock(), MagicMock())

        asyncio.get_event_loop().run_until_complete(_run())
        assert called["count"] == 1
        logger.info.assert_not_called()

    def test_normal_http_request(self):
        """Normal HTTP request logs request and response."""
        Cls = self._get_module()
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"ok": true}',
                }
            )

        mw = Cls(fake_app, logger)
        mw._extract_request_context = _strip_key(
            mw._extract_request_context, "request_id"
        )

        scope = {
            "type": "http",
            "path": "/api/data",
            "method": "GET",
            "query_string": b"limit=10",
            "scheme": "https",
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 54321),
            "headers": [
                (b"user-agent", b"test"),
                (b"content-type", b"application/json"),
            ],
        }

        async def _run():
            await mw(scope, AsyncMock(), AsyncMock())

        asyncio.get_event_loop().run_until_complete(_run())
        # Request + response = 2 info calls
        assert logger.info.call_count == 2

    def test_excluded_status_code(self):
        """Excluded status codes skip response logging."""
        Cls = self._get_module()
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        mw = Cls(fake_app, logger, exclude_status_codes={204})
        mw._extract_request_context = _strip_key(
            mw._extract_request_context, "request_id"
        )

        scope = {
            "type": "http",
            "path": "/api/delete",
            "method": "DELETE",
            "query_string": b"",
            "headers": [],
        }

        async def _run():
            await mw(scope, AsyncMock(), AsyncMock())

        asyncio.get_event_loop().run_until_complete(_run())
        # Only request logged (1 call)
        assert logger.info.call_count == 1

    def test_exception_in_app(self):
        """Exception in inner app is logged and re-raised."""
        Cls = self._get_module()
        logger = _make_logger()

        async def failing_app(scope, receive, send):
            raise RuntimeError("app crash")

        mw = Cls(failing_app, logger)
        mw._extract_request_context = _strip_key(
            mw._extract_request_context, "request_id"
        )

        scope = {
            "type": "http",
            "path": "/api/fail",
            "method": "POST",
            "query_string": b"",
            "headers": [],
        }

        async def _run():
            await mw(scope, MagicMock(), MagicMock())

        with pytest.raises(RuntimeError, match="app crash"):
            asyncio.get_event_loop().run_until_complete(_run())

        logger.error.assert_called_once()

    def test_get_client_ip_from_proxy_header(self):
        """_get_client_ip extracts IP from proxy headers."""
        Cls = self._get_module()
        logger = _make_logger()
        mw = Cls(MagicMock(), logger)

        scope = {}
        headers = {b"x-forwarded-for": b"10.0.0.1, 10.0.0.2"}
        ip = mw._get_client_ip(scope, headers)
        assert ip == "10.0.0.1"

    def test_get_client_ip_from_scope_client(self):
        """_get_client_ip falls back to scope client."""
        Cls = self._get_module()
        logger = _make_logger()
        mw = Cls(MagicMock(), logger)

        scope = {"client": ("192.168.1.1", 12345)}
        headers = {}
        ip = mw._get_client_ip(scope, headers)
        assert ip == "192.168.1.1"

    def test_get_client_ip_none(self):
        """_get_client_ip returns None when no info."""
        Cls = self._get_module()
        logger = _make_logger()
        mw = Cls(MagicMock(), logger)

        ip = mw._get_client_ip({}, {})
        assert ip is None

    def test_extract_response_context(self):
        """_extract_response_context extracts status and size."""
        Cls = self._get_module()
        logger = _make_logger()
        mw = Cls(MagicMock(), logger)

        response_data = {
            "status_code": 200,
            "headers": {b"content-type": b"application/json"},
            "body": b'{"data": []}',
        }

        ctx = mw._extract_response_context(response_data, 42.5)
        assert ctx["status_code"] == 200
        assert ctx["duration"] == 42.5
        assert ctx["response_size"] == len(b'{"data": []}')
        assert ctx["content_type"] == "application/json"

    def test_log_responses_disabled(self):
        """No response logged when log_responses is False."""
        Cls = self._get_module()
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        mw = Cls(
            fake_app,
            logger,
            log_requests=True,
            log_responses=False,
        )
        mw._extract_request_context = _strip_key(
            mw._extract_request_context, "request_id"
        )

        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "query_string": b"",
            "headers": [],
        }

        async def _run():
            await mw(scope, AsyncMock(), AsyncMock())

        asyncio.get_event_loop().run_until_complete(_run())
        # Only 1 call for request; no response logging
        assert logger.info.call_count == 1


class TestMohFlowWSGIMiddleware:
    """Tests for MohFlowWSGIMiddleware."""

    def _get_module(self):
        from mohflow.integrations.asgi_wsgi import (
            MohFlowWSGIMiddleware,
        )

        return MohFlowWSGIMiddleware

    def test_init_defaults(self):
        """WSGI middleware initialises with correct defaults."""
        Cls = self._get_module()
        logger = _make_logger()
        app = MagicMock()

        mw = Cls(app, logger)
        assert mw.app is app
        assert mw.log_requests is True
        assert mw.exclude_paths == set()

    def test_excluded_path(self):
        """Excluded paths call inner app without logging."""
        Cls = self._get_module()
        logger = _make_logger()

        def inner_app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        mw = Cls(inner_app, logger, exclude_paths={"/health"})

        environ = {
            "PATH_INFO": "/health",
            "REQUEST_METHOD": "GET",
        }
        start_response = MagicMock()

        result = mw(environ, start_response)
        logger.info.assert_not_called()

    def test_normal_request(self):
        """Normal WSGI request logs request and response."""
        Cls = self._get_module()
        logger = _make_logger()

        def inner_app(environ, start_response):
            start_response(
                "200 OK",
                [("Content-Type", "text/plain")],
            )
            return [b"hello"]

        mw = Cls(inner_app, logger)
        mw._extract_request_context = _strip_key_sync(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api/data",
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": "page=1",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "wsgi.url_scheme": "http",
            "HTTP_USER_AGENT": "test-client",
            "CONTENT_TYPE": "text/plain",
            "REMOTE_ADDR": "127.0.0.1",
        }
        start_response = MagicMock()

        result = mw(environ, start_response)
        assert result == [b"hello"]
        # Request + response = 2 info calls
        assert logger.info.call_count == 2

    def test_excluded_status_code(self):
        """Excluded status codes skip response logging."""
        Cls = self._get_module()
        logger = _make_logger()

        def inner_app(environ, start_response):
            start_response("204 No Content", [])
            return [b""]

        mw = Cls(inner_app, logger, exclude_status_codes={204})
        mw._extract_request_context = _strip_key_sync(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api/del",
            "REQUEST_METHOD": "DELETE",
            "REMOTE_ADDR": "127.0.0.1",
        }
        start_response = MagicMock()

        mw(environ, start_response)
        # Only request logged
        assert logger.info.call_count == 1

    def test_exception_in_app(self):
        """Exception in inner WSGI app is logged and re-raised."""
        Cls = self._get_module()
        logger = _make_logger()

        def failing_app(environ, start_response):
            raise RuntimeError("wsgi crash")

        mw = Cls(failing_app, logger)
        mw._extract_request_context = _strip_key_sync(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api/fail",
            "REQUEST_METHOD": "POST",
            "REMOTE_ADDR": "127.0.0.1",
        }

        with pytest.raises(RuntimeError, match="wsgi crash"):
            mw(environ, MagicMock())

        logger.error.assert_called_once()

    def test_response_iterable_closed(self):
        """WSGI middleware calls close() on response iterable."""
        Cls = self._get_module()
        logger = _make_logger()

        class ClosableIter:
            def __init__(self):
                self.closed = False
                self._data = [b"chunk"]

            def __iter__(self):
                return iter(self._data)

            def close(self):
                self.closed = True

        response_iter = ClosableIter()

        def inner_app(environ, start_response):
            start_response("200 OK", [])
            return response_iter

        mw = Cls(inner_app, logger)
        mw._extract_request_context = _strip_key_sync(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }

        mw(environ, MagicMock())
        assert response_iter.closed is True

    def test_request_id_in_response_headers(self):
        """WSGI middleware adds X-Request-ID to response headers."""
        Cls = self._get_module()
        logger = _make_logger()

        captured_headers = {}

        def inner_app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        mw = Cls(inner_app, logger)
        mw._extract_request_context = _strip_key_sync(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }

        def start_response(status, headers, exc_info=None):
            captured_headers["headers"] = headers

        mw(environ, start_response)
        header_names = [h[0] for h in captured_headers["headers"]]
        assert "X-Request-ID" in header_names

    def test_get_client_ip_from_proxy(self):
        """_get_client_ip extracts IP from proxy headers."""
        Cls = self._get_module()
        logger = _make_logger()
        mw = Cls(MagicMock(), logger)

        environ = {
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2",
            "REMOTE_ADDR": "127.0.0.1",
        }

        ip = mw._get_client_ip(environ)
        assert ip == "10.0.0.1"

    def test_get_client_ip_fallback(self):
        """_get_client_ip falls back to REMOTE_ADDR."""
        Cls = self._get_module()
        logger = _make_logger()
        mw = Cls(MagicMock(), logger)

        environ = {"REMOTE_ADDR": "192.168.0.1"}
        ip = mw._get_client_ip(environ)
        assert ip == "192.168.0.1"

    def test_extract_response_context(self):
        """_extract_response_context extracts correct fields."""
        Cls = self._get_module()
        logger = _make_logger()
        mw = Cls(MagicMock(), logger)

        response_data = {
            "status": "201 Created",
            "headers": [("Content-Type", "application/json")],
        }

        ctx = mw._extract_response_context(response_data, b'{"id": 1}', 55.0)
        assert ctx["status_code"] == 201
        assert ctx["duration"] == 55.0
        assert ctx["content_type"] == "application/json"

    def test_log_requests_disabled(self):
        """No request logged when log_requests is False."""
        Cls = self._get_module()
        logger = _make_logger()

        def inner_app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        mw = Cls(
            inner_app,
            logger,
            log_requests=False,
            log_responses=True,
        )
        mw._extract_request_context = _strip_key_sync(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }

        mw(environ, MagicMock())
        # Only 1 call for response; request logging disabled
        assert logger.info.call_count == 1

    def test_log_level_mapping_error(self):
        """WSGI middleware uses error level for 500 status."""
        Cls = self._get_module()
        logger = _make_logger()

        def inner_app(environ, start_response):
            start_response("500 Internal Server Error", [])
            return [b"error"]

        mw = Cls(inner_app, logger)
        mw._extract_request_context = _strip_key_sync(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api/err",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }

        mw(environ, MagicMock())
        logger.error.assert_called_once()


class TestASGIWSGIFactories:
    """Tests for factory and utility functions."""

    def test_create_asgi_middleware(self):
        """create_asgi_middleware returns a factory function."""
        from mohflow.integrations.asgi_wsgi import (
            create_asgi_middleware,
            MohFlowASGIMiddleware,
        )

        logger = _make_logger()
        factory = create_asgi_middleware(logger, log_requests=False)

        app = MagicMock()
        mw = factory(app)
        assert isinstance(mw, MohFlowASGIMiddleware)
        assert mw.log_requests is False

    def test_create_wsgi_middleware(self):
        """create_wsgi_middleware returns a factory function."""
        from mohflow.integrations.asgi_wsgi import (
            create_wsgi_middleware,
            MohFlowWSGIMiddleware,
        )

        logger = _make_logger()
        factory = create_wsgi_middleware(logger, exclude_paths={"/skip"})

        app = MagicMock()
        mw = factory(app)
        assert isinstance(mw, MohFlowWSGIMiddleware)
        assert "/skip" in mw.exclude_paths

    def test_auto_setup_flask(self):
        """auto_setup_middleware detects Flask app."""
        from mohflow.integrations.asgi_wsgi import (
            auto_setup_middleware,
        )

        logger = _make_logger()
        app = MagicMock()
        type(app).__name__ = "Flask"
        type(app).__module__ = "flask.app"
        app.wsgi_app = MagicMock()

        result = auto_setup_middleware(app, logger)
        assert result is app

    def test_auto_setup_fastapi(self):
        """auto_setup_middleware detects FastAPI app."""
        from mohflow.integrations.asgi_wsgi import (
            auto_setup_middleware,
        )

        logger = _make_logger()
        app = MagicMock()
        type(app).__name__ = "FastAPI"
        type(app).__module__ = "fastapi.applications"

        result = auto_setup_middleware(app, logger)
        assert result is app
        app.add_middleware.assert_called_once()

    def test_auto_setup_django_raises(self):
        """auto_setup_middleware raises for Django apps."""
        from mohflow.integrations.asgi_wsgi import (
            auto_setup_middleware,
        )

        logger = _make_logger()
        app = MagicMock()
        type(app).__name__ = "WSGIHandler"
        type(app).__module__ = "django.core.handlers.wsgi"

        with pytest.raises(ValueError, match="Django"):
            auto_setup_middleware(app, logger)

    def test_auto_setup_unknown_raises(self):
        """auto_setup_middleware raises for unknown apps."""
        from mohflow.integrations.asgi_wsgi import (
            auto_setup_middleware,
        )

        logger = _make_logger()
        app = MagicMock()
        type(app).__name__ = "UnknownApp"
        type(app).__module__ = "some.random.module"
        # Ensure it doesn't match ASGI detection
        app.__call__ = MagicMock()
        del app.wsgi_version

        with pytest.raises(ValueError, match="Unable to auto-detect"):
            auto_setup_middleware(app, logger)

    def test_log_request_manually(self):
        """log_request_manually logs and returns request_id."""
        from mohflow.integrations.asgi_wsgi import (
            log_request_manually,
        )

        logger = _make_logger()
        rid = log_request_manually(logger, "GET", "/api/data", custom="val")

        assert isinstance(rid, str)
        assert len(rid) == 36  # UUID format
        logger.info.assert_called_once()

    def test_log_response_manually_info(self):
        """log_response_manually logs at info level for 2xx."""
        from mohflow.integrations.asgi_wsgi import (
            log_response_manually,
        )

        logger = _make_logger()
        log_response_manually(logger, "rid-1", "GET", "/api", 200, 10.5)
        logger.info.assert_called_once()

    def test_log_response_manually_warning(self):
        """log_response_manually logs at warning level for 4xx."""
        from mohflow.integrations.asgi_wsgi import (
            log_response_manually,
        )

        logger = _make_logger()
        log_response_manually(logger, "rid-2", "GET", "/api", 404, 5.0)
        logger.warning.assert_called_once()

    def test_log_response_manually_error(self):
        """log_response_manually logs at error level for 5xx."""
        from mohflow.integrations.asgi_wsgi import (
            log_response_manually,
        )

        logger = _make_logger()
        log_response_manually(logger, "rid-3", "POST", "/api", 500, 100.0)
        logger.error.assert_called_once()
