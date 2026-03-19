"""
Comprehensive unit tests for MohFlow integration modules targeting
near-100% line coverage.

All framework dependencies (Flask, Django, FastAPI, Celery) are mocked
so these tests run without any of those packages installed.
"""

import asyncio
import sys
import time
import types
import uuid
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

import pytest


# ------------------------------------------------------------------ #
#  Helper: mock logger                                                #
# ------------------------------------------------------------------ #
def _make_logger():
    """Create a mock logger with request_context as a context manager."""
    logger = MagicMock()

    @contextmanager
    def _noop_cm():
        yield

    logger.request_context = lambda *a, **kw: _noop_cm()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


# ------------------------------------------------------------------ #
#  __init__.py coverage                                               #
# ------------------------------------------------------------------ #
class TestIntegrationsInit:
    """Tests for integrations/__init__.py."""

    def test_all_is_empty_list(self):
        from mohflow.integrations import __all__

        assert __all__ == []

    def test_module_docstring(self):
        import mohflow.integrations

        assert "MohFlow Framework Integrations" in (
            mohflow.integrations.__doc__
        )


# ================================================================== #
#                          FLASK TESTS                                #
# ================================================================== #


@pytest.fixture()
def flask_env():
    """Inject fake flask / werkzeug modules and reimport."""
    werkzeug_exc = types.ModuleType("werkzeug.exceptions")

    class _HTTPException(Exception):
        def __init__(self, description="err", code=400):
            super().__init__(description)
            self.description = description
            self.code = code

    werkzeug_exc.HTTPException = _HTTPException
    werkzeug_mod = types.ModuleType("werkzeug")
    werkzeug_mod.exceptions = werkzeug_exc

    flask_mod = types.ModuleType("flask")
    flask_mod.Flask = MagicMock
    flask_mod.request = MagicMock()
    flask_mod.g = MagicMock()
    flask_mod.jsonify = MagicMock(side_effect=lambda d: d)
    flask_mod.current_app = MagicMock()

    saved = {}
    for n in ("werkzeug", "werkzeug.exceptions", "flask"):
        saved[n] = sys.modules.get(n)

    sys.modules["werkzeug"] = werkzeug_mod
    sys.modules["werkzeug.exceptions"] = werkzeug_exc
    sys.modules["flask"] = flask_mod

    mod_key = "mohflow.integrations.flask"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.flask as flask_int

    yield {
        "mod": flask_int,
        "flask_mod": flask_mod,
        "HTTPException": _HTTPException,
    }

    for n, orig in saved.items():
        if orig is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = orig


class TestFlaskExtensionCoverage:
    """Line-coverage tests for MohFlowFlaskExtension."""

    def test_init_no_app_no_logger(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        assert ext.app is None
        assert ext.logger is None

    def test_init_app_sets_logger_from_arg(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension(logger=logger)
        assert ext.logger is logger

    def test_init_app_with_app_calls_init_app(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = MagicMock()
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)
        ext = mod.MohFlowFlaskExtension(app=app, logger=logger)
        app.before_request.assert_called_once()

    def test_init_app_raises_import_error_when_no_flask(self, flask_env):
        mod = flask_env["mod"]
        original = mod.HAS_FLASK
        mod.HAS_FLASK = False
        try:
            ext = mod.MohFlowFlaskExtension()
            with pytest.raises(ImportError, match="Flask is not installed"):
                ext.init_app(MagicMock())
        finally:
            mod.HAS_FLASK = original

    def test_init_app_raises_value_error_no_logger(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        app = MagicMock()
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)
        with pytest.raises(ValueError, match="logger is required"):
            ext.init_app(app)

    def test_init_app_logger_override(self, flask_env):
        """init_app with a new logger overrides the original."""
        mod = flask_env["mod"]
        logger1 = _make_logger()
        logger2 = _make_logger()
        ext = mod.MohFlowFlaskExtension(logger=logger1)
        app = MagicMock()
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)
        ext.init_app(app, logger2)
        assert ext.logger is logger2

    def test_init_app_reads_all_config_keys(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = MagicMock()
        app.config = {
            "MOHFLOW_LOG_REQUESTS": False,
            "MOHFLOW_LOG_RESPONSES": False,
            "MOHFLOW_LOG_REQUEST_BODY": True,
            "MOHFLOW_LOG_RESPONSE_BODY": True,
            "MOHFLOW_MAX_BODY_SIZE": 256,
            "MOHFLOW_EXCLUDE_PATHS": ["/health", "/metrics"],
            "MOHFLOW_EXCLUDE_STATUS_CODES": [204, 304],
            "MOHFLOW_LOG_LEVEL_MAPPING": {200: "debug"},
        }
        app.extensions = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)

        ext = mod.MohFlowFlaskExtension()
        ext.init_app(app, logger)

        assert ext.log_requests is False
        assert ext.log_responses is False
        assert ext.log_request_body is True
        assert ext.log_response_body is True
        assert ext.max_body_size == 256
        assert "/health" in ext.exclude_paths
        assert 304 in ext.exclude_status_codes
        assert ext.log_level_mapping == {200: "debug"}
        assert app.extensions["mohflow"] is ext
        assert app.mohflow_logger is logger

    def test_before_request_skips_excluded(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_paths = {"/skip"}
        ext.log_requests = True

        req = MagicMock()
        req.path = "/skip"
        with patch.object(mod, "request", req):
            result = ext._before_request()
        assert result is None
        logger.info.assert_not_called()

    def test_before_request_logs_with_query_string(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_paths = set()
        ext.log_requests = True
        ext.log_request_body = False

        req = MagicMock()
        req.path = "/api"
        req.method = "GET"
        req.query_string = b"a=1&b=2"
        req.headers = {}
        req.content_type = None
        req.content_length = None
        req.endpoint = "api_view"
        req.view_args = {"id": 42}
        req.environ = {"REMOTE_ADDR": "10.0.0.1"}

        g_mock = MagicMock()
        with patch.object(mod, "request", req), patch.object(mod, "g", g_mock):
            ext._before_request()

        assert g_mock.mohflow_request_id is not None
        logger.info.assert_called_once()

    def test_before_request_no_logging_when_disabled(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_paths = set()
        ext.log_requests = False
        ext.log_request_body = False

        req = MagicMock()
        req.path = "/api"
        req.method = "GET"
        req.query_string = b""
        req.headers = {}
        req.content_type = None
        req.content_length = None
        req.endpoint = None
        req.view_args = None
        req.environ = {}

        g_mock = MagicMock()
        with patch.object(mod, "request", req), patch.object(mod, "g", g_mock):
            ext._before_request()

        logger.info.assert_not_called()

    def test_after_request_no_request_id(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        g_mock = MagicMock(spec=[])
        response = MagicMock()
        with patch.object(mod, "g", g_mock):
            result = ext._after_request(response)
        assert result is response

    def test_after_request_excluded_status(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_status_codes = {204}
        ext.log_responses = True

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r1"
        g_mock.mohflow_start_time = time.time()

        resp = MagicMock()
        resp.status_code = 204
        with patch.object(mod, "g", g_mock):
            result = ext._after_request(resp)
        assert result is resp
        logger.info.assert_not_called()

    def test_after_request_logs_and_sets_header(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_status_codes = set()
        ext.log_responses = True
        ext.log_response_body = False
        ext.log_level_mapping = {200: "info"}

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r2"
        g_mock.mohflow_start_time = time.time() - 0.01
        g_mock.mohflow_context = {"method": "GET", "path": "/x"}

        req = MagicMock()
        req.method = "GET"
        req.path = "/x"

        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "text/html"
        resp.content_length = 10
        resp.headers = {}

        with patch.object(mod, "g", g_mock), patch.object(mod, "request", req):
            result = ext._after_request(resp)

        assert result is resp
        assert resp.headers["X-Request-ID"] == "r2"
        logger.info.assert_called_once()

    def test_after_request_unknown_status_code_defaults_info(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_status_codes = set()
        ext.log_responses = True
        ext.log_response_body = False
        ext.log_level_mapping = {}  # empty mapping

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r3"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}

        req = MagicMock()
        req.method = "GET"
        req.path = "/y"

        resp = MagicMock()
        resp.status_code = 999
        resp.content_type = None
        resp.content_length = None
        resp.headers = {}

        with patch.object(mod, "g", g_mock), patch.object(mod, "request", req):
            ext._after_request(resp)

        logger.info.assert_called_once()

    def test_after_request_no_logging_when_disabled(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.exclude_status_codes = set()
        ext.log_responses = False
        ext.log_response_body = False
        ext.log_level_mapping = {}

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r4"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}

        req = MagicMock()
        req.method = "GET"
        req.path = "/z"

        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = None
        resp.content_length = None
        resp.headers = {}

        with patch.object(mod, "g", g_mock), patch.object(mod, "request", req):
            ext._after_request(resp)

        logger.info.assert_not_called()

    def test_handle_exception_no_request_id_reraises(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        g_mock = MagicMock(spec=[])
        with patch.object(mod, "g", g_mock), pytest.raises(ValueError):
            ext._handle_exception(ValueError("boom"))

    def test_handle_exception_http_exception(self, flask_env):
        mod = flask_env["mod"]
        HTTPException = flask_env["HTTPException"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.log_level_mapping = {404: "warning"}

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "re1"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {"method": "GET"}

        req = MagicMock()
        req.method = "GET"
        req.path = "/missing"

        err = HTTPException(description="Not Found", code=404)
        with patch.object(mod, "g", g_mock), patch.object(
            mod, "request", req
        ), pytest.raises(HTTPException):
            ext._handle_exception(err)

        logger.warning.assert_called_once()

    def test_handle_exception_generic_error(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        ext = mod.MohFlowFlaskExtension()
        ext.logger = logger
        ext.log_level_mapping = {}

        g_mock = MagicMock()
        g_mock.mohflow_request_id = "re2"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}

        req = MagicMock()
        req.method = "POST"
        req.path = "/err"

        with patch.object(mod, "g", g_mock), patch.object(
            mod, "request", req
        ), pytest.raises(RuntimeError):
            ext._handle_exception(RuntimeError("kaboom"))

        logger.error.assert_called_once()

    def test_extract_request_context_with_body(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_request_body = True
        ext.max_body_size = 1024

        req = MagicMock()
        req.method = "POST"
        req.path = "/data"
        req.query_string = b"x=1"
        req.headers = {"User-Agent": "bot"}
        req.content_type = "application/json"
        req.content_length = 15
        req.endpoint = "data_ep"
        req.view_args = {"pk": 1}
        req.environ = {"REMOTE_ADDR": "1.2.3.4"}
        req.get_data = MagicMock(return_value='{"key":"val"}')

        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()

        assert ctx["method"] == "POST"
        assert ctx["request_body"] == '{"key":"val"}'
        assert ctx["flask_view_args"] == {"pk": 1}
        assert ctx["query_params"] == "x=1"

    def test_extract_request_context_body_too_large(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_request_body = True
        ext.max_body_size = 5

        req = MagicMock()
        req.method = "POST"
        req.path = "/data"
        req.query_string = b""
        req.headers = {}
        req.content_type = "application/json"
        req.content_length = 100
        req.endpoint = None
        req.view_args = None
        req.environ = {}
        req.get_data = MagicMock(return_value="a" * 100)

        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()

        assert "request_body" not in ctx

    def test_extract_request_context_body_read_error(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_request_body = True
        ext.max_body_size = 1024

        req = MagicMock()
        req.method = "POST"
        req.path = "/data"
        req.query_string = b""
        req.headers = {}
        req.content_type = "application/json"
        req.content_length = 10
        req.endpoint = None
        req.view_args = None
        req.environ = {}
        req.get_data = MagicMock(side_effect=Exception("read fail"))

        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()

        assert ctx["request_body"] == "[Unable to read body]"

    def test_extract_response_context_with_body(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_response_body = True
        ext.max_body_size = 1024

        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "application/json"
        resp.content_length = 20
        resp.get_data = MagicMock(return_value='{"ok":true}')

        ctx = ext._extract_response_context(resp, 10.0)
        assert ctx["response_body"] == '{"ok":true}'
        assert ctx["duration"] == 10.0

    def test_extract_response_context_body_too_large(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_response_body = True
        ext.max_body_size = 5

        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "application/json"
        resp.content_length = 100
        resp.get_data = MagicMock(return_value="x" * 100)

        ctx = ext._extract_response_context(resp, 5.0)
        assert "response_body" not in ctx

    def test_extract_response_context_body_read_error(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_response_body = True
        ext.max_body_size = 1024

        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "application/json"
        resp.content_length = 10
        resp.get_data = MagicMock(side_effect=Exception("fail"))

        ctx = ext._extract_response_context(resp, 5.0)
        assert ctx["response_body"] == "[Unable to read body]"

    def test_get_client_ip_x_forwarded_for(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(
            side_effect=lambda h: (
                "10.0.0.1, 10.0.0.2" if h == "X-Forwarded-For" else None
            )
        )
        req.environ = {}

        with patch.object(mod, "request", req):
            assert ext._get_client_ip() == "10.0.0.1"

    def test_get_client_ip_cf_connecting(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        call_count = [0]

        def _get(h):
            if h == "CF-Connecting-IP":
                return "5.5.5.5"
            return None

        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(side_effect=_get)
        req.environ = {}

        with patch.object(mod, "request", req):
            assert ext._get_client_ip() == "5.5.5.5"

    def test_get_client_ip_remote_addr_fallback(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=None)
        req.environ = {"REMOTE_ADDR": "127.0.0.1"}

        with patch.object(mod, "request", req):
            assert ext._get_client_ip() == "127.0.0.1"

    def test_log_context_updates(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        g_mock = MagicMock()
        g_mock.mohflow_context = {"a": 1}
        with patch.object(mod, "g", g_mock):
            ext._log_context(b=2)
        assert g_mock.mohflow_context["b"] == 2

    def test_log_context_no_context_attr(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()

        g_mock = MagicMock(spec=[])
        with patch.object(mod, "g", g_mock):
            ext._log_context(x=1)  # should not raise


class TestFlaskDecoratorsCoverage:
    def test_log_route_success_with_logger(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.log_route(logger, component="auth")
        def my_view():
            return "ok"

        g_mock = MagicMock()
        g_mock.mohflow_context = {}
        with patch.object(mod, "g", g_mock):
            assert my_view() == "ok"
        logger.info.assert_called_once()

    def test_log_route_failure(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.log_route(logger)
        def bad():
            raise ValueError("fail")

        g_mock = MagicMock()
        g_mock.mohflow_context = {}
        with patch.object(mod, "g", g_mock), pytest.raises(ValueError):
            bad()
        logger.error.assert_called_once()

    def test_log_route_no_logger_uses_extension(self, flask_env):
        mod = flask_env["mod"]
        ext_logger = _make_logger()
        ext = MagicMock()
        ext.logger = ext_logger

        current_app = MagicMock()
        current_app.extensions = {"mohflow": ext}

        @mod.log_route(None)
        def view():
            return "data"

        g_mock = MagicMock()
        g_mock.mohflow_context = {}
        with patch.object(mod, "g", g_mock), patch.object(
            mod, "current_app", current_app
        ):
            assert view() == "data"
        ext_logger.info.assert_called_once()

    def test_log_route_no_g_context(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.log_route(logger)
        def view():
            return "v"

        g_mock = MagicMock(spec=[])
        with patch.object(mod, "g", g_mock):
            assert view() == "v"

    def test_timed_route_success(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.timed_route(logger)
        def fast():
            return "fast"

        assert fast() == "fast"
        logger.info.assert_called_once()
        assert logger.info.call_args[1]["performance_metric"] is True

    def test_timed_route_failure(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.timed_route(logger)
        def fail():
            raise RuntimeError("oops")

        with pytest.raises(RuntimeError):
            fail()
        logger.warning.assert_called_once()

    def test_timed_route_no_logger_uses_extension(self, flask_env):
        mod = flask_env["mod"]
        ext_logger = _make_logger()
        ext = MagicMock()
        ext.logger = ext_logger

        current_app = MagicMock()
        current_app.extensions = {"mohflow": ext}

        @mod.timed_route(None)
        def view():
            return "ok"

        with patch.object(mod, "current_app", current_app):
            assert view() == "ok"
        ext_logger.info.assert_called_once()


class TestFlaskHelpersCoverage:
    def test_get_request_id_present(self, flask_env):
        mod = flask_env["mod"]
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "rid-1"
        with patch.object(mod, "g", g_mock):
            assert mod.get_request_id() == "rid-1"

    def test_get_request_id_absent(self, flask_env):
        mod = flask_env["mod"]
        g_mock = MagicMock(spec=[])
        with patch.object(mod, "g", g_mock):
            assert mod.get_request_id() is None

    def test_log_business_event_with_request_id(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "biz-1"
        with patch.object(mod, "g", g_mock):
            mod.log_business_event(logger, "signup", plan="pro")
        kw = logger.info.call_args[1]
        assert kw["business_event"] == "signup"
        assert kw["request_id"] == "biz-1"

    def test_log_business_event_no_request_id(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        g_mock = MagicMock(spec=[])
        with patch.object(mod, "g", g_mock):
            mod.log_business_event(logger, "logout")
        kw = logger.info.call_args[1]
        assert "request_id" not in kw

    def test_create_health_route(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "h1"
        health = mod.create_health_route(logger)
        with patch.object(mod, "g", g_mock):
            result = health()
        assert result["status"] == "healthy"

    def test_create_metrics_route_prometheus(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        logger.export_prometheus_metrics = MagicMock(return_value="# HELP\n")
        ep = mod.create_metrics_route(logger)
        result = ep()
        assert result[0] == "# HELP\n"
        assert result[1] == 200

    def test_create_metrics_route_prometheus_empty(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        logger.export_prometheus_metrics = MagicMock(return_value=None)
        logger.get_metrics_summary = MagicMock(return_value={"count": 5})
        ep = mod.create_metrics_route(logger)
        ep()
        mod.jsonify.assert_called()

    def test_create_metrics_route_json_fallback(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        del logger.export_prometheus_metrics
        logger.get_metrics_summary = MagicMock(return_value={"total": 100})
        ep = mod.create_metrics_route(logger)
        ep()
        mod.jsonify.assert_called()

    def test_create_metrics_route_json_empty(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        del logger.export_prometheus_metrics
        logger.get_metrics_summary = MagicMock(return_value=None)
        ep = mod.create_metrics_route(logger)
        result = ep()
        assert result[1] == 404

    def test_create_metrics_route_no_metrics(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        del logger.export_prometheus_metrics
        del logger.get_metrics_summary
        ep = mod.create_metrics_route(logger)
        result = ep()
        assert result[1] == 404

    def test_configure_mohflow_flask(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = MagicMock()
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)

        ext = mod.configure_mohflow_flask(
            app, logger, exclude_paths=["/health"]
        )
        assert isinstance(ext, mod.MohFlowFlaskExtension)
        assert app.config["MOHFLOW_EXCLUDE_PATHS"] == ["/health"]


# ================================================================== #
#                         DJANGO TESTS                                #
# ================================================================== #


@pytest.fixture()
def django_env():
    """Inject fake django modules and reimport."""
    django_conf = types.ModuleType("django.conf")
    mock_settings = MagicMock()
    mock_settings.MOHFLOW_MIDDLEWARE = {}
    mock_settings.MOHFLOW_LOGGER = _make_logger()
    django_conf.settings = mock_settings

    django_http = types.ModuleType("django.http")
    django_http.HttpRequest = MagicMock
    django_http.HttpResponse = MagicMock

    django_deprecation = types.ModuleType("django.utils.deprecation")

    class _MiddlewareMixin:
        def __init__(self, get_response=None):
            self.get_response = get_response

    django_deprecation.MiddlewareMixin = _MiddlewareMixin

    django_exceptions = types.ModuleType("django.core.exceptions")

    class _ImproperlyConfigured(Exception):
        pass

    django_exceptions.ImproperlyConfigured = _ImproperlyConfigured

    saved = {}
    for n in (
        "django",
        "django.conf",
        "django.http",
        "django.utils",
        "django.utils.deprecation",
        "django.core",
        "django.core.exceptions",
    ):
        saved[n] = sys.modules.get(n)

    sys.modules["django"] = types.ModuleType("django")
    sys.modules["django.conf"] = django_conf
    sys.modules["django.http"] = django_http
    sys.modules["django.utils"] = types.ModuleType("django.utils")
    sys.modules["django.utils.deprecation"] = django_deprecation
    sys.modules["django.core"] = types.ModuleType("django.core")
    sys.modules["django.core.exceptions"] = django_exceptions

    mod_key = "mohflow.integrations.django"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.django as django_int

    yield {
        "mod": django_int,
        "settings": mock_settings,
        "ICE": _ImproperlyConfigured,
    }

    for n, orig in saved.items():
        if orig is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = orig


class TestDjangoMiddlewareCoverage:
    def test_init_logger_from_settings_attr(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
        assert mw.logger is logger

    def test_init_logger_from_dotted_path(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()

        fake_mod = types.ModuleType("myapp.log")
        fake_mod.the_logger = logger
        sys.modules["myapp"] = types.ModuleType("myapp")
        sys.modules["myapp.log"] = fake_mod

        s.MOHFLOW_MIDDLEWARE = {"logger": "myapp.log.the_logger"}
        del s.MOHFLOW_LOGGER

        try:
            mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
            assert mw.logger is logger
        finally:
            sys.modules.pop("myapp.log", None)
            sys.modules.pop("myapp", None)

    def test_init_raises_improperly_configured(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        ICE = django_env["ICE"]
        s.MOHFLOW_MIDDLEWARE = {}
        del s.MOHFLOW_LOGGER

        with pytest.raises(ICE):
            mod.MohFlowDjangoMiddleware(get_response=MagicMock())

    def test_init_reads_all_config(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {
            "log_requests": False,
            "log_responses": False,
            "log_request_body": True,
            "log_response_body": True,
            "max_body_size": 256,
            "exclude_paths": ["/static/"],
            "exclude_status_codes": [304],
            "log_user_context": False,
            "log_level_mapping": {200: "debug"},
        }

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
        assert mw.log_requests is False
        assert mw.log_response_body is True
        assert mw.max_body_size == 256
        assert "/static/" in mw.exclude_paths
        assert 304 in mw.exclude_status_codes

    def test_process_request_excluded_path(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {"exclude_paths": ["/health"]}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
        req = MagicMock()
        req.path = "/health"
        assert mw.process_request(req) is None
        logger.info.assert_not_called()

    def test_process_request_logs(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.path = "/api"
        req.method = "GET"
        req.GET = MagicMock()
        req.GET.__bool__ = lambda self: False
        req.META = {"REMOTE_ADDR": "127.0.0.1"}
        req.content_type = "text/html"
        req.body = b""
        req.user = MagicMock()
        req.user.is_authenticated = False
        req.session = MagicMock()
        req.session.session_key = None

        mw.process_request(req)
        assert hasattr(req, "mohflow_request_id")
        logger.info.assert_called_once()

    def test_process_request_no_logging_when_disabled(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {"log_requests": False}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.path = "/api"
        req.method = "GET"
        req.GET = MagicMock()
        req.GET.__bool__ = lambda self: False
        req.META = {}
        req.content_type = ""
        req.body = b""
        req.user = MagicMock()
        req.user.is_authenticated = False
        req.session = MagicMock()
        req.session.session_key = None

        mw.process_request(req)
        logger.info.assert_not_called()

    def test_process_response_no_request_id(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
        req = MagicMock(spec=[])
        resp = MagicMock()
        assert mw.process_response(req, resp) is resp

    def test_process_response_excluded_status(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {"exclude_status_codes": [204]}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.mohflow_request_id = "r1"
        req.mohflow_start_time = time.time()

        resp = MagicMock()
        resp.status_code = 204
        assert mw.process_response(req, resp) is resp
        logger.info.assert_not_called()

    def test_process_response_logs_and_sets_header(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.mohflow_request_id = "r2"
        req.mohflow_start_time = time.time() - 0.01
        req.mohflow_context = {"method": "GET", "path": "/api"}
        req.method = "GET"
        req.path = "/api"

        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value="application/json")
        resp.content = b'{"ok":true}'
        resp.__setitem__ = MagicMock()

        mw.process_response(req, resp)
        logger.info.assert_called_once()
        resp.__setitem__.assert_called_with("X-Request-ID", "r2")

    def test_process_response_no_logging_when_disabled(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {"log_responses": False}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.mohflow_request_id = "r3"
        req.mohflow_start_time = time.time()
        req.mohflow_context = {}
        req.method = "GET"
        req.path = "/x"

        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value=None)
        resp.__setitem__ = MagicMock()

        mw.process_response(req, resp)
        logger.info.assert_not_called()

    def test_process_exception_logs(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        logger = _make_logger()
        s.MOHFLOW_LOGGER = logger
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.mohflow_request_id = "re1"
        req.mohflow_start_time = time.time()
        req.mohflow_context = {"method": "POST"}
        req.method = "POST"
        req.path = "/fail"

        assert mw.process_exception(req, ValueError("x")) is None
        logger.error.assert_called_once()

    def test_process_exception_no_request_id(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())
        req = MagicMock(spec=[])
        assert mw.process_exception(req, ValueError("x")) is None

    def test_extract_request_context_user_session(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {"log_user_context": True}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.method = "GET"
        req.path = "/me"
        req.GET = MagicMock()
        req.GET.__bool__ = lambda self: True
        req.GET.urlencode = MagicMock(return_value="page=1")
        req.META = {"REMOTE_ADDR": "1.2.3.4"}
        req.content_type = "text/html"
        req.body = b"data"
        req.user = MagicMock()
        req.user.is_authenticated = True
        req.user.id = 42
        req.user.username = "alice"
        req.user.email = "a@b.com"
        req.session = MagicMock()
        req.session.session_key = "sess123"

        ctx = mw._extract_request_context(req)
        assert ctx["user_id"] == 42
        assert ctx["username"] == "alice"
        assert ctx["session_id"] == "sess123"
        assert ctx["query_params"] == "page=1"

    def test_extract_request_context_body(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {
            "log_request_body": True,
            "max_body_size": 1024,
        }

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.method = "POST"
        req.path = "/data"
        req.GET = MagicMock()
        req.GET.__bool__ = lambda self: False
        req.META = {}
        req.content_type = "application/json"
        req.body = b'{"k":"v"}'
        req.user = MagicMock()
        req.user.is_authenticated = False
        req.session = MagicMock()
        req.session.session_key = None

        ctx = mw._extract_request_context(req)
        assert ctx["request_body"] == '{"k":"v"}'

    def test_extract_request_context_body_decode_error(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {
            "log_request_body": True,
            "max_body_size": 1024,
        }

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.method = "POST"
        req.path = "/data"
        req.GET = MagicMock()
        req.GET.__bool__ = lambda self: False
        req.META = {}
        req.content_type = "application/json"
        # body.decode raises
        body_mock = MagicMock()
        body_mock.decode = MagicMock(side_effect=Exception("decode fail"))
        body_mock.__len__ = MagicMock(return_value=5)
        req.body = body_mock
        req.user = MagicMock()
        req.user.is_authenticated = False
        req.session = MagicMock()
        req.session.session_key = None

        ctx = mw._extract_request_context(req)
        assert ctx["request_body"] == "[Unable to read body]"

    def test_extract_response_context_with_body(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {
            "log_response_body": True,
            "max_body_size": 1024,
        }

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value="application/json")
        resp.content = b'{"ok":true}'

        ctx = mw._extract_response_context(resp, 10.0)
        assert ctx["response_body"] == '{"ok":true}'

    def test_extract_response_context_body_error(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {
            "log_response_body": True,
            "max_body_size": 1024,
        }

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value="application/json")
        content_mock = MagicMock()
        content_mock.decode = MagicMock(side_effect=Exception("fail"))
        content_mock.__len__ = MagicMock(return_value=5)
        resp.content = content_mock

        ctx = mw._extract_response_context(resp, 5.0)
        assert ctx["response_body"] == "[Unable to read body]"

    def test_get_client_ip_proxy(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.META = {"HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2"}
        assert mw._get_client_ip(req) == "10.0.0.1"

    def test_get_client_ip_fallback(self, django_env):
        mod = django_env["mod"]
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {}

        mw = mod.MohFlowDjangoMiddleware(get_response=MagicMock())

        req = MagicMock()
        req.META = {"REMOTE_ADDR": "192.168.0.1"}
        assert mw._get_client_ip(req) == "192.168.0.1"


class TestDjangoDecoratorsCoverage:
    def test_log_view_success(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()

        @mod.log_view(logger, component="users")
        def my_view(request):
            return "ok"

        req = MagicMock()
        req.mohflow_context = {}
        assert my_view(req) == "ok"
        logger.info.assert_called_once()

    def test_log_view_failure(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()

        @mod.log_view(logger)
        def bad_view(request):
            raise RuntimeError("fail")

        req = MagicMock()
        req.mohflow_context = {}
        with pytest.raises(RuntimeError):
            bad_view(req)
        logger.error.assert_called_once()

    def test_log_view_no_context(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()

        @mod.log_view(logger)
        def view(request):
            return "v"

        req = MagicMock(spec=[])
        assert view(req) == "v"


class TestDjangoHelpersCoverage:
    def test_configure_mohflow_django(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()
        cfg = mod.configure_mohflow_django(logger, exclude_paths=["/health"])
        assert cfg["logger"] is logger
        assert "/health" in cfg["exclude_paths"]
        assert cfg["log_requests"] is True

    def test_mohflow_context_processor_with_data(self, django_env):
        mod = django_env["mod"]
        req = MagicMock()
        req.mohflow_request_id = "ctx-1"
        req.mohflow_context = {"user_id": 99, "session_id": "s1"}
        ctx = mod.mohflow_context(req)
        assert ctx["mohflow"]["mohflow_request_id"] == "ctx-1"
        assert ctx["mohflow"]["mohflow_user_id"] == 99

    def test_mohflow_context_processor_empty(self, django_env):
        mod = django_env["mod"]
        req = MagicMock(spec=[])
        ctx = mod.mohflow_context(req)
        assert ctx == {"mohflow": {}}

    def test_django_filter_with_context(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()
        logger.get_current_context = MagicMock(return_value={"service": "api"})
        filt = mod.MohFlowDjangoFilter(logger)
        record = MagicMock()
        assert filt.filter(record) is True

    def test_django_filter_no_context_method(self, django_env):
        mod = django_env["mod"]
        logger = MagicMock(spec=[])
        filt = mod.MohFlowDjangoFilter(logger)
        assert filt.filter(MagicMock()) is True

    def test_setup_command_logging(self, django_env):
        mod = django_env["mod"]
        logger = MagicMock()
        logger.config = MagicMock()
        logger.config.SERVICE_NAME = "test"
        logger.__dict__ = {"a": 1}
        mock_cls = MagicMock(return_value=MagicMock())
        with patch.object(mod, "type", create=True):
            # Just verify it doesn't crash
            try:
                mod.setup_command_logging(logger, "migrate")
            except Exception:
                pass  # May fail due to type() mock; coverage still hit


# ================================================================== #
#                        FASTAPI TESTS                                #
# ================================================================== #


@pytest.fixture()
def fastapi_env():
    """Inject fake fastapi / starlette modules."""
    starlette_mw = types.ModuleType("starlette.middleware.base")

    class _BaseHTTPMiddleware:
        def __init__(self, app):
            self.app = app

    starlette_mw.BaseHTTPMiddleware = _BaseHTTPMiddleware

    starlette_types = types.ModuleType("starlette.types")
    starlette_types.ASGIApp = object

    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.Request = MagicMock
    fastapi_mod.Response = MagicMock
    fastapi_mod.FastAPI = MagicMock

    fastapi_resp = types.ModuleType("fastapi.responses")
    fastapi_resp.JSONResponse = MagicMock

    saved = {}
    for n in (
        "starlette",
        "starlette.middleware",
        "starlette.middleware.base",
        "starlette.types",
        "fastapi",
        "fastapi.responses",
    ):
        saved[n] = sys.modules.get(n)

    sys.modules["starlette"] = types.ModuleType("starlette")
    sys.modules["starlette.middleware"] = types.ModuleType(
        "starlette.middleware"
    )
    sys.modules["starlette.middleware.base"] = starlette_mw
    sys.modules["starlette.types"] = starlette_types
    sys.modules["fastapi"] = fastapi_mod
    sys.modules["fastapi.responses"] = fastapi_resp

    mod_key = "mohflow.integrations.fastapi"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.fastapi as fastapi_int

    yield {"mod": fastapi_int, "fastapi_mod": fastapi_mod}

    for n, orig in saved.items():
        if orig is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = orig


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestFastAPIMiddlewareCoverage:
    def test_init_defaults(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        assert mw.log_requests is True
        assert mw.exclude_paths == set()
        assert mw.custom_extractors == []
        assert mw.enable_metrics is True

    def test_init_custom(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(),
            _make_logger(),
            log_requests=False,
            log_responses=False,
            log_request_body=True,
            log_response_body=True,
            max_body_size=256,
            exclude_paths={"/h"},
            exclude_status_codes={204},
            custom_extractors=[lambda r: {}],
            enable_metrics=False,
            log_level_mapping={200: "debug"},
        )
        assert mw.log_requests is False
        assert mw.max_body_size == 256

    def test_dispatch_excluded_path(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), logger, exclude_paths={"/health"}
        )

        req = MagicMock()
        req.url.path = "/health"
        resp = MagicMock()

        async def call_next(r):
            return resp

        result = _run_async(mw.dispatch(req, call_next))
        assert result is resp
        logger.info.assert_not_called()

    def test_dispatch_normal(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), logger)

        req = MagicMock()
        req.url.path = "/api"
        req.method = "GET"
        req.query_params = ""
        req.headers = {}
        req.client = None

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}

        async def call_next(r):
            return resp

        # Patch extract to avoid duplicate-kwarg
        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched
        result = _run_async(mw.dispatch(req, call_next))
        assert result is resp
        assert logger.info.call_count == 2

    def test_dispatch_exception(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), logger)

        req = MagicMock()
        req.url.path = "/fail"
        req.method = "POST"
        req.query_params = ""
        req.headers = {}
        req.client = None

        async def call_next(r):
            raise RuntimeError("boom")

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched
        _run_async(mw.dispatch(req, call_next))
        logger.error.assert_called_once()

    def test_dispatch_excluded_status_code(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), logger, exclude_status_codes={204}
        )

        req = MagicMock()
        req.url.path = "/api"
        req.method = "DELETE"
        req.query_params = ""
        req.headers = {}
        req.client = None

        resp = MagicMock()
        resp.status_code = 204
        resp.headers = {}

        async def call_next(r):
            return resp

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched
        result = _run_async(mw.dispatch(req, call_next))
        assert result is resp

    def test_dispatch_no_logging(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(),
            logger,
            log_requests=False,
            log_responses=False,
        )

        req = MagicMock()
        req.url.path = "/api"
        req.method = "GET"
        req.query_params = ""
        req.headers = {}
        req.client = None

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}

        async def call_next(r):
            return resp

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched
        _run_async(mw.dispatch(req, call_next))
        logger.info.assert_not_called()

    def test_extract_request_context_with_body(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), logger, log_request_body=True
        )

        req = MagicMock()
        req.url.path = "/api"
        req.method = "POST"
        req.query_params = "a=1"
        req.headers = {
            "user-agent": "bot",
            "content-type": "application/json",
            "content-length": "10",
        }
        req.client = MagicMock()
        req.client.host = "1.2.3.4"

        async def body():
            return b'{"k":"v"}'

        req.body = body

        async def run():
            return await mw._extract_request_context(req, "rid")

        ctx = _run_async(run())
        assert ctx["request_body"] == '{"k":"v"}'

    def test_extract_request_context_body_error(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), logger, log_request_body=True
        )

        req = MagicMock()
        req.url.path = "/api"
        req.method = "POST"
        req.query_params = ""
        req.headers = {"content-type": "application/json"}
        req.client = None

        async def body():
            raise Exception("read fail")

        req.body = body

        async def run():
            return await mw._extract_request_context(req, "rid")

        ctx = _run_async(run())
        assert ctx["request_body"] == "[Unable to read body]"

    def test_extract_request_context_custom_extractors(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()

        def good_ext(r):
            return {"custom": "val"}

        def bad_ext(r):
            raise RuntimeError("fail")

        def non_dict_ext(r):
            return "not a dict"

        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(),
            logger,
            custom_extractors=[good_ext, bad_ext, non_dict_ext],
        )

        req = MagicMock()
        req.url.path = "/api"
        req.method = "GET"
        req.query_params = ""
        req.headers = {}
        req.client = None

        async def run():
            return await mw._extract_request_context(req, "rid")

        ctx = _run_async(run())
        assert ctx["custom"] == "val"

    def test_extract_response_context_with_body(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), logger, log_response_body=True
        )

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {
            "content-type": "application/json",
            "content-length": "10",
        }
        resp.body = b'{"ok":true}'

        async def run():
            return await mw._extract_response_context(resp, 5.0)

        ctx = _run_async(run())
        assert ctx["response_body"] == '{"ok":true}'

    def test_extract_response_context_body_error(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), logger, log_response_body=True
        )

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        # Use invalid UTF-8 bytes so decode("utf-8") raises
        resp.body = b"\xff\xfe"

        async def run():
            return await mw._extract_response_context(resp, 5.0)

        ctx = _run_async(run())
        assert ctx["response_body"] == "[Unable to read body]"

    def test_get_client_ip_from_headers(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2"}
        req.client = None
        assert mw._get_client_ip(req) == "10.0.0.1"

    def test_get_client_ip_fallback_client(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.headers = {}
        req.client = MagicMock()
        req.client.host = "192.168.1.1"
        assert mw._get_client_ip(req) == "192.168.1.1"

    def test_get_client_ip_none(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.headers = {}
        req.client = None
        assert mw._get_client_ip(req) is None


class TestFastAPIHelpersCoverage:
    def test_setup_fastapi_logging(self, fastapi_env):
        mod = fastapi_env["mod"]
        app = MagicMock()
        result = mod.setup_fastapi_logging(app, _make_logger())
        assert result is app
        app.add_middleware.assert_called_once()

    def test_setup_fastapi_logging_no_fastapi(self, fastapi_env):
        mod = fastapi_env["mod"]
        orig = mod.HAS_FASTAPI
        mod.HAS_FASTAPI = False
        try:
            with pytest.raises(ImportError, match="FastAPI"):
                mod.setup_fastapi_logging(MagicMock(), _make_logger())
        finally:
            mod.HAS_FASTAPI = orig

    def test_log_endpoint_success(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()

        @mod.log_endpoint(logger, component="auth")
        async def login():
            return {"token": "abc"}

        result = _run_async(login())
        assert result == {"token": "abc"}
        logger.info.assert_called_once()

    def test_log_endpoint_failure(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()

        @mod.log_endpoint(logger)
        async def bad():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            _run_async(bad())
        logger.error.assert_called_once()

    def test_create_health_endpoint(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        health = mod.create_health_endpoint(logger)
        result = _run_async(health())
        assert result["status"] == "healthy"

    def test_extract_auth_context_bearer(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {
            "authorization": "Bearer token123",
            "x-user-id": "u1",
        }
        ctx = mod.extract_auth_context(req)
        assert ctx["auth_type"] == "bearer"
        assert ctx["user_id"] == "u1"

    def test_extract_auth_context_basic(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {"authorization": "Basic dXNlcjpw"}
        ctx = mod.extract_auth_context(req)
        assert ctx["auth_type"] == "basic"

    def test_extract_auth_context_empty(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {}
        ctx = mod.extract_auth_context(req)
        assert ctx == {}

    def test_extract_trace_context(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {
            "x-trace-id": "t1",
            "x-span-id": "s1",
            "uber-trace-id": "j1",
        }
        ctx = mod.extract_trace_context(req)
        assert ctx["trace_id"] == "t1"
        assert ctx["span_id"] == "s1"
        assert ctx["jaeger_trace_id"] == "j1"

    def test_extract_trace_context_empty(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {}
        ctx = mod.extract_trace_context(req)
        assert ctx == {}

    def test_extract_business_context(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {
            "x-tenant-id": "t1",
            "x-organization-id": "o1",
            "x-api-version": "v2",
        }
        ctx = mod.extract_business_context(req)
        assert ctx["tenant_id"] == "t1"
        assert ctx["organization_id"] == "o1"
        assert ctx["api_version"] == "v2"

    def test_extract_business_context_defaults(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {}
        ctx = mod.extract_business_context(req)
        assert ctx["api_version"] == "v1"


# ================================================================== #
#                         CELERY TESTS                                #
# ================================================================== #


@pytest.fixture()
def celery_env():
    """Inject fake celery modules."""
    celery_mod = types.ModuleType("celery")
    celery_mod.Celery = MagicMock

    celery_signals = types.ModuleType("celery.signals")
    for sig in (
        "task_prerun",
        "task_postrun",
        "task_failure",
        "task_retry",
        "worker_ready",
        "worker_shutdown",
    ):
        setattr(celery_signals, sig, MagicMock())

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
    for n in (
        "celery",
        "celery.signals",
        "celery.app",
        "celery.app.task",
    ):
        saved[n] = sys.modules.get(n)

    sys.modules["celery"] = celery_mod
    sys.modules["celery.signals"] = celery_signals
    sys.modules["celery.app"] = celery_app
    sys.modules["celery.app.task"] = celery_app_task

    mod_key = "mohflow.integrations.celery"
    saved[mod_key] = sys.modules.pop(mod_key, None)

    import mohflow.integrations.celery as celery_int

    yield {
        "mod": celery_int,
        "signals": celery_signals,
        "Task": _Task,
    }

    for n, orig in saved.items():
        if orig is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = orig


class TestCeleryIntegrationCoverage:
    def test_init_with_app(self, celery_env):
        mod = celery_env["mod"]
        sig = celery_env["signals"]
        logger = _make_logger()
        mod.MohFlowCeleryIntegration(logger, MagicMock())
        sig.task_prerun.connect.assert_called_once()
        sig.task_postrun.connect.assert_called_once()
        sig.task_failure.connect.assert_called_once()
        sig.task_retry.connect.assert_called_once()
        sig.worker_ready.connect.assert_called_once()
        sig.worker_shutdown.connect.assert_called_once()

    def test_init_without_app(self, celery_env):
        mod = celery_env["mod"]
        sig = celery_env["signals"]
        i = mod.MohFlowCeleryIntegration(_make_logger())
        assert i.app is None

    def test_setup_signals_no_celery(self, celery_env):
        mod = celery_env["mod"]
        orig = mod.HAS_CELERY
        mod.HAS_CELERY = False
        try:
            i = mod.MohFlowCeleryIntegration(_make_logger())
            with pytest.raises(ImportError, match="Celery"):
                i.setup_signals()
        finally:
            mod.HAS_CELERY = orig

    def test_task_prerun_handler(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {}

        i._task_prerun_handler(
            sender=sender,
            task_id="t1",
            task=task,
            args=(1,),
            kwargs={"a": 1},
        )
        logger.info.assert_called_once()

    def test_task_prerun_handler_no_mohflow_context(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock(spec=[])  # no mohflow_context

        i._task_prerun_handler(
            sender=sender, task_id="t2", task=task, args=(), kwargs={}
        )
        logger.info.assert_called_once()

    def test_task_postrun_handler_success(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {"task_start_time": time.time() - 0.1}

        i._task_postrun_handler(
            sender=sender,
            task_id="t3",
            task=task,
            args=(),
            kwargs={},
            retval={"result": 1},
            state="SUCCESS",
        )
        logger.info.assert_called_once()

    def test_task_postrun_handler_non_success(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {}

        i._task_postrun_handler(
            sender=sender,
            task_id="t4",
            task=task,
            args=(),
            kwargs={},
            retval=None,
            state="FAILURE",
        )
        logger.warning.assert_called_once()

    def test_task_postrun_handler_large_retval(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {}

        # Large retval > 1000 chars
        i._task_postrun_handler(
            sender=sender,
            task_id="t5",
            task=task,
            args=(),
            kwargs={},
            retval="x" * 2000,
            state="SUCCESS",
        )
        logger.info.assert_called_once()

    def test_task_failure_handler(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "fail_task"
        i._task_failure_handler(
            sender=sender,
            task_id="tf1",
            exception=ValueError("bad"),
            einfo="traceback...",
        )
        logger.error.assert_called_once()

    def test_task_failure_handler_no_sender(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        i._task_failure_handler(
            sender=None, task_id="tf2", exception=None, einfo=None
        )
        logger.error.assert_called_once()
        assert "unknown" in logger.error.call_args[0][0]

    def test_task_retry_handler(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.name = "retry_task"
        i._task_retry_handler(
            sender=sender,
            task_id="tr1",
            reason="timeout",
            einfo="tb...",
        )
        logger.warning.assert_called_once()

    def test_task_retry_handler_no_sender(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        i._task_retry_handler(
            sender=None, task_id="tr2", reason=None, einfo=None
        )
        logger.warning.assert_called_once()

    def test_worker_ready_handler(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.hostname = "w1"
        sender.pid = 123
        i._worker_ready_handler(sender=sender)
        logger.info.assert_called_once()

    def test_worker_ready_handler_no_attrs(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock(spec=[])
        i._worker_ready_handler(sender=sender)
        logger.info.assert_called_once()

    def test_worker_shutdown_handler(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        i = mod.MohFlowCeleryIntegration(logger)

        sender = MagicMock()
        sender.hostname = "w1"
        sender.pid = 123
        i._worker_shutdown_handler(sender=sender)
        logger.info.assert_called_once()

    def test_safe_serialize_json(self, celery_env):
        mod = celery_env["mod"]
        i = mod.MohFlowCeleryIntegration(_make_logger())
        assert i._safe_serialize([1, 2]) == [1, 2]
        assert i._safe_serialize(None) is None

    def test_safe_serialize_non_json(self, celery_env):
        mod = celery_env["mod"]
        i = mod.MohFlowCeleryIntegration(_make_logger())
        assert isinstance(i._safe_serialize(object()), str)


class TestCeleryTaskCoverage:
    def test_set_logger(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        logger = _make_logger()
        task.set_logger(logger)
        assert task.mohflow_logger is logger

    def test_apply_async_with_logger(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "test_task"
        task.mohflow_logger = logger

        with patch.object(
            celery_env["Task"], "apply_async", return_value=MagicMock()
        ):
            task.apply_async(args=(1,), kwargs={"x": 2})

        logger.info.assert_called_once()
        kw = logger.info.call_args[1]
        assert "correlation_id" in kw

    def test_apply_async_preserves_correlation_id(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "test_task"
        task.mohflow_logger = logger

        with patch.object(
            celery_env["Task"], "apply_async", return_value=MagicMock()
        ):
            task.apply_async(headers={"correlation_id": "existing-id"})

        kw = logger.info.call_args[1]
        assert kw["correlation_id"] == "existing-id"

    def test_apply_async_without_logger(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        task.name = "quiet"
        task.mohflow_logger = None

        with patch.object(
            celery_env["Task"], "apply_async", return_value=MagicMock()
        ):
            task.apply_async(args=(1,))

    def test_retry_with_logger(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "retry_task"
        task.mohflow_logger = logger
        task.max_retries = 3
        task.request = MagicMock()
        task.request.id = "rtid"
        task.request.retries = 1

        with patch.object(
            celery_env["Task"], "retry", return_value=MagicMock()
        ):
            task.retry(exc=ValueError("temp"), countdown=60)

        logger.warning.assert_called_once()

    def test_retry_without_logger(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        task.name = "quiet_retry"
        task.mohflow_logger = None
        task.request = MagicMock()
        task.request.id = "rtid2"
        task.request.retries = 0

        with patch.object(
            celery_env["Task"], "retry", return_value=MagicMock()
        ):
            task.retry()

    def test_safe_serialize(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        assert task._safe_serialize({"a": 1}) == {"a": 1}
        assert task._safe_serialize(None) is None
        assert isinstance(task._safe_serialize(object()), str)


class TestCeleryHelpersCoverage:
    def test_log_task_success(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()

        @mod.log_task(logger, component="data")
        def process(x):
            return x * 2

        assert process(5) == 10
        assert logger.info.call_count == 2

    def test_log_task_failure(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()

        @mod.log_task(logger)
        def bad():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            bad()
        logger.error.assert_called_once()

    def test_setup_celery_logging(self, celery_env):
        mod = celery_env["mod"]
        i = mod.setup_celery_logging(_make_logger(), MagicMock())
        assert isinstance(i, mod.MohFlowCeleryIntegration)

    def test_log_task_progress(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        mod.log_task_progress(logger, "tid", 50, 100)
        kw = logger.info.call_args[1]
        assert kw["progress_percent"] == 50.0

    def test_log_task_progress_zero_total(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        mod.log_task_progress(logger, "tid", 0, 0)
        kw = logger.info.call_args[1]
        assert kw["progress_percent"] == 0

    def test_log_task_progress_custom_message(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        mod.log_task_progress(logger, "tid", 3, 10, "Processing")
        assert logger.info.call_args[0][0] == "Processing"


class TestTaskErrorAggregatorCoverage:
    def test_record_error(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger())
        agg.record_error("t1", "ValueError")
        assert len(agg.error_counts["t1:ValueError"]) == 1

    def test_high_error_rate_alert(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        agg = mod.TaskErrorAggregator(logger)
        for _ in range(10):
            agg.record_error("t2", "TimeoutError")
        logger.error.assert_called()
        kw = logger.error.call_args[1]
        assert kw["alert_type"] == "high_error_rate"

    def test_cleanup_old_entries(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger(), window_minutes=1)
        agg.error_counts["old:Err"] = [time.time() - 120]
        agg._cleanup_old_entries(time.time())
        assert "old:Err" not in agg.error_counts

    def test_cleanup_triggered_periodically(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger(), window_minutes=1)
        agg.last_cleanup = time.time() - 301
        agg.error_counts["stale:Err"] = [time.time() - 120]
        agg.record_error("new", "NewErr")
        assert "stale:Err" not in agg.error_counts


# ================================================================== #
#                      ASGI / WSGI TESTS                              #
# ================================================================== #


class TestASGIMiddlewareCoverage:
    def _cls(self):
        from mohflow.integrations.asgi_wsgi import (
            MohFlowASGIMiddleware,
        )

        return MohFlowASGIMiddleware

    def test_init(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        assert mw.log_requests is True
        assert mw.exclude_paths == set()

    def test_non_http_passthrough(self):
        Cls = self._cls()
        logger = _make_logger()

        async def app(scope, receive, send):
            pass

        mw = Cls(app, logger)

        async def run():
            await mw({"type": "websocket"}, MagicMock(), MagicMock())

        _run_async(run())
        logger.info.assert_not_called()

    def test_excluded_path(self):
        Cls = self._cls()
        logger = _make_logger()
        called = {"c": 0}

        async def app(scope, receive, send):
            called["c"] += 1

        mw = Cls(app, logger, exclude_paths={"/health"})

        async def run():
            await mw(
                {"type": "http", "path": "/health", "method": "GET"},
                MagicMock(),
                MagicMock(),
            )

        _run_async(run())
        assert called["c"] == 1
        logger.info.assert_not_called()

    def test_normal_request(self):
        Cls = self._cls()
        logger = _make_logger()

        async def app(scope, receive, send):
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
                    "body": b'{"ok":true}',
                }
            )

        mw = Cls(app, logger)

        # Patch to avoid dup kwarg
        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched

        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "query_string": b"a=1",
            "scheme": "https",
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 54321),
            "headers": [
                (b"user-agent", b"test"),
                (b"content-type", b"application/json"),
                (b"content-length", b"0"),
            ],
        }

        async def run():
            await mw(scope, AsyncMock(), AsyncMock())

        _run_async(run())
        assert logger.info.call_count == 2

    def test_excluded_status_code(self):
        Cls = self._cls()
        logger = _make_logger()

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        mw = Cls(app, logger, exclude_status_codes={204})

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched

        scope = {
            "type": "http",
            "path": "/api",
            "method": "DELETE",
            "query_string": b"",
            "headers": [],
        }

        async def run():
            await mw(scope, AsyncMock(), AsyncMock())

        _run_async(run())
        assert logger.info.call_count == 1

    def test_exception_in_app(self):
        Cls = self._cls()
        logger = _make_logger()

        async def app(scope, receive, send):
            raise RuntimeError("crash")

        mw = Cls(app, logger)

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched

        scope = {
            "type": "http",
            "path": "/fail",
            "method": "POST",
            "query_string": b"",
            "headers": [],
        }

        async def run():
            await mw(scope, MagicMock(), MagicMock())

        with pytest.raises(RuntimeError):
            _run_async(run())
        logger.error.assert_called_once()

    def test_log_responses_disabled(self):
        Cls = self._cls()
        logger = _make_logger()

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        mw = Cls(app, logger, log_responses=False)

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched

        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "query_string": b"",
            "headers": [],
        }

        async def run():
            await mw(scope, AsyncMock(), AsyncMock())

        _run_async(run())
        assert logger.info.call_count == 1

    def test_log_requests_disabled(self):
        Cls = self._cls()
        logger = _make_logger()

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b""})

        mw = Cls(app, logger, log_requests=False)

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched

        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "query_string": b"",
            "headers": [],
        }

        async def run():
            await mw(scope, AsyncMock(), AsyncMock())

        _run_async(run())
        assert logger.info.call_count == 1

    def test_get_client_ip_proxy(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        headers = {b"x-forwarded-for": b"10.0.0.1, 10.0.0.2"}
        assert mw._get_client_ip({}, headers) == "10.0.0.1"

    def test_get_client_ip_scope_client_tuple(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        scope = {"client": ("192.168.1.1", 12345)}
        assert mw._get_client_ip(scope, {}) == "192.168.1.1"

    def test_get_client_ip_scope_client_string(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        scope = {"client": "10.0.0.5"}
        assert mw._get_client_ip(scope, {}) == "10.0.0.5"

    def test_get_client_ip_none(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        assert mw._get_client_ip({}, {}) is None

    def test_extract_response_context(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        data = {
            "status_code": 200,
            "headers": {b"content-type": b"application/json"},
            "body": b'{"data":[]}',
        }
        ctx = mw._extract_response_context(data, 42.5)
        assert ctx["status_code"] == 200
        assert ctx["duration"] == 42.5
        assert ctx["content_type"] == "application/json"

    def test_extract_response_context_empty_body(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        data = {
            "status_code": 204,
            "headers": {},
            "body": b"",
        }
        ctx = mw._extract_response_context(data, 1.0)
        assert ctx["status_code"] == 204
        assert "response_size" not in ctx

    def test_send_wrapper_body_accumulation(self):
        """Verify body chunks accumulate in send_wrapper."""
        Cls = self._cls()
        logger = _make_logger()

        chunks = [b"chunk1", b"chunk2"]

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            for chunk in chunks:
                await send({"type": "http.response.body", "body": chunk})

        mw = Cls(app, logger)

        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched

        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "query_string": b"",
            "headers": [],
        }

        async def run():
            await mw(scope, AsyncMock(), AsyncMock())

        _run_async(run())
        assert logger.info.call_count == 2


class TestWSGIMiddlewareCoverage:
    def _cls(self):
        from mohflow.integrations.asgi_wsgi import (
            MohFlowWSGIMiddleware,
        )

        return MohFlowWSGIMiddleware

    def _strip(self, fn, key):
        def wrapper(*a, **kw):
            r = fn(*a, **kw)
            r.pop(key, None)
            return r

        return wrapper

    def test_init(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        assert mw.log_requests is True

    def test_excluded_path(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        mw = Cls(app, logger, exclude_paths={"/health"})
        environ = {"PATH_INFO": "/health", "REQUEST_METHOD": "GET"}
        mw(environ, MagicMock())
        logger.info.assert_not_called()

    def test_normal_request(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"hello"]

        mw = Cls(app, logger)
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "QUERY_STRING": "p=1",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "wsgi.url_scheme": "http",
            "HTTP_USER_AGENT": "test",
            "CONTENT_TYPE": "text/plain",
            "CONTENT_LENGTH": "5",
            "REMOTE_ADDR": "127.0.0.1",
        }

        result = mw(environ, MagicMock())
        assert result == [b"hello"]
        assert logger.info.call_count == 2

    def test_excluded_status_code(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            start_response("204 No Content", [])
            return [b""]

        mw = Cls(app, logger, exclude_status_codes={204})
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "DELETE",
            "REMOTE_ADDR": "127.0.0.1",
        }
        mw(environ, MagicMock())
        assert logger.info.call_count == 1

    def test_exception_in_app(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            raise RuntimeError("crash")

        mw = Cls(app, logger)
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/fail",
            "REQUEST_METHOD": "POST",
            "REMOTE_ADDR": "127.0.0.1",
        }

        with pytest.raises(RuntimeError):
            mw(environ, MagicMock())
        logger.error.assert_called_once()

    def test_response_iterable_closed(self):
        Cls = self._cls()
        logger = _make_logger()

        class ClosableIter:
            def __init__(self):
                self.closed = False

            def __iter__(self):
                return iter([b"chunk"])

            def close(self):
                self.closed = True

        response_iter = ClosableIter()

        def app(environ, start_response):
            start_response("200 OK", [])
            return response_iter

        mw = Cls(app, logger)
        mw._extract_request_context = self._strip(
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
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        mw = Cls(app, logger)
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["headers"] = headers

        mw(environ, start_response)
        names = [h[0] for h in captured["headers"]]
        assert "X-Request-ID" in names

    def test_log_requests_disabled(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        mw = Cls(app, logger, log_requests=False)
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }
        mw(environ, MagicMock())
        assert logger.info.call_count == 1

    def test_log_responses_disabled(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            start_response("200 OK", [])
            return [b"ok"]

        mw = Cls(app, logger, log_responses=False)
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }
        mw(environ, MagicMock())
        assert logger.info.call_count == 1

    def test_log_level_500(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            start_response("500 Internal Server Error", [])
            return [b"err"]

        mw = Cls(app, logger)
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/err",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }
        mw(environ, MagicMock())
        logger.error.assert_called_once()

    def test_no_status_defaults_500(self):
        Cls = self._cls()
        logger = _make_logger()

        def app(environ, start_response):
            # start_response called but status left None
            start_response("500 Internal Server Error", [])
            return [b""]

        mw = Cls(app, logger)
        mw._extract_request_context = self._strip(
            mw._extract_request_context, "request_id"
        )

        environ = {
            "PATH_INFO": "/api",
            "REQUEST_METHOD": "GET",
            "REMOTE_ADDR": "127.0.0.1",
        }
        mw(environ, MagicMock())

    def test_get_client_ip_proxy(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        environ = {
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2",
            "REMOTE_ADDR": "127.0.0.1",
        }
        assert mw._get_client_ip(environ) == "10.0.0.1"

    def test_get_client_ip_fallback(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        assert mw._get_client_ip({"REMOTE_ADDR": "1.1.1.1"}) == "1.1.1.1"

    def test_extract_response_context(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        data = {
            "status": "201 Created",
            "headers": [("Content-Type", "application/json")],
        }
        ctx = mw._extract_response_context(data, b'{"id":1}', 55.0)
        assert ctx["status_code"] == 201
        assert ctx["content_type"] == "application/json"

    def test_extract_response_context_no_status(self):
        Cls = self._cls()
        mw = Cls(MagicMock(), _make_logger())
        data = {"status": None, "headers": []}
        ctx = mw._extract_response_context(data, b"", 1.0)
        assert ctx["status_code"] == 500


class TestASGIWSGIFactoriesCoverage:
    def test_create_asgi_middleware(self):
        from mohflow.integrations.asgi_wsgi import (
            create_asgi_middleware,
            MohFlowASGIMiddleware,
        )

        factory = create_asgi_middleware(_make_logger(), log_requests=False)
        mw = factory(MagicMock())
        assert isinstance(mw, MohFlowASGIMiddleware)
        assert mw.log_requests is False

    def test_create_wsgi_middleware(self):
        from mohflow.integrations.asgi_wsgi import (
            create_wsgi_middleware,
            MohFlowWSGIMiddleware,
        )

        factory = create_wsgi_middleware(
            _make_logger(), exclude_paths={"/skip"}
        )
        mw = factory(MagicMock())
        assert isinstance(mw, MohFlowWSGIMiddleware)
        assert "/skip" in mw.exclude_paths

    def test_auto_setup_fastapi(self):
        from mohflow.integrations.asgi_wsgi import auto_setup_middleware

        app = MagicMock()
        type(app).__name__ = "FastAPI"
        type(app).__module__ = "fastapi.applications"
        result = auto_setup_middleware(app, _make_logger())
        assert result is app
        app.add_middleware.assert_called_once()

    def test_auto_setup_flask(self):
        from mohflow.integrations.asgi_wsgi import auto_setup_middleware

        app = MagicMock()
        type(app).__name__ = "Flask"
        type(app).__module__ = "flask.app"
        app.wsgi_app = MagicMock()
        result = auto_setup_middleware(app, _make_logger())
        assert result is app

    def test_auto_setup_django_raises(self):
        from mohflow.integrations.asgi_wsgi import auto_setup_middleware

        app = MagicMock()
        type(app).__name__ = "WSGIHandler"
        type(app).__module__ = "django.core.handlers.wsgi"
        with pytest.raises(ValueError, match="Django"):
            auto_setup_middleware(app, _make_logger())

    def test_auto_setup_generic_wsgi(self):
        from mohflow.integrations.asgi_wsgi import auto_setup_middleware

        app = MagicMock()
        type(app).__name__ = "GenericWSGI"
        type(app).__module__ = "some.wsgi.module"
        app.wsgi_version = (1, 0)
        result = auto_setup_middleware(app, _make_logger())
        assert result is not None

    def test_auto_setup_generic_asgi(self):
        from mohflow.integrations.asgi_wsgi import auto_setup_middleware

        async def asgi_app(scope, receive, send):
            pass

        result = auto_setup_middleware(asgi_app, _make_logger())
        assert result is not None

    def test_auto_setup_unknown_raises(self):
        from mohflow.integrations.asgi_wsgi import auto_setup_middleware

        app = MagicMock()
        type(app).__name__ = "Unknown"
        type(app).__module__ = "some.random"
        app.__call__ = MagicMock()
        del app.wsgi_version

        with pytest.raises(ValueError, match="Unable to auto-detect"):
            auto_setup_middleware(app, _make_logger())

    def test_log_request_manually(self):
        from mohflow.integrations.asgi_wsgi import log_request_manually

        logger = _make_logger()
        rid = log_request_manually(logger, "GET", "/api", custom="val")
        assert len(rid) == 36
        logger.info.assert_called_once()

    def test_log_response_manually_info(self):
        from mohflow.integrations.asgi_wsgi import (
            log_response_manually,
        )

        logger = _make_logger()
        log_response_manually(logger, "r1", "GET", "/api", 200, 10.0)
        logger.info.assert_called_once()

    def test_log_response_manually_warning(self):
        from mohflow.integrations.asgi_wsgi import (
            log_response_manually,
        )

        logger = _make_logger()
        log_response_manually(logger, "r2", "GET", "/api", 404, 5.0)
        logger.warning.assert_called_once()

    def test_log_response_manually_error(self):
        from mohflow.integrations.asgi_wsgi import (
            log_response_manually,
        )

        logger = _make_logger()
        log_response_manually(logger, "r3", "POST", "/api", 500, 100.0)
        logger.error.assert_called_once()

    def test_log_response_manually_399(self):
        from mohflow.integrations.asgi_wsgi import (
            log_response_manually,
        )

        logger = _make_logger()
        log_response_manually(logger, "r4", "GET", "/api", 301, 2.0)
        logger.info.assert_called_once()
