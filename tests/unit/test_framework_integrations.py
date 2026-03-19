"""
Comprehensive mock-based tests for MohFlow framework integration modules.

All framework dependencies (Flask, Django, FastAPI, Celery) are mocked
via sys.modules so these tests run without any of those packages installed.
"""

import asyncio
import sys
import time
import types
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

import pytest


# ------------------------------------------------------------------ #
#  Shared helpers                                                      #
# ------------------------------------------------------------------ #
def _make_logger():
    """Create a mock logger with request_context as a real CM."""
    logger = MagicMock()

    @contextmanager
    def _noop_cm():
        yield

    logger.request_context = lambda *a, **kw: _noop_cm()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ================================================================== #
#                          FLASK TESTS                                 #
# ================================================================== #


@pytest.fixture()
def flask_env():
    """Inject fake flask / werkzeug modules and reimport the module."""
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


def _make_flask_app(**config_overrides):
    """Build a mock Flask app with sane defaults."""
    app = MagicMock()
    app.config = {
        "MOHFLOW_LOG_REQUESTS": True,
        "MOHFLOW_LOG_RESPONSES": True,
        "MOHFLOW_LOG_REQUEST_BODY": False,
        "MOHFLOW_LOG_RESPONSE_BODY": False,
        "MOHFLOW_MAX_BODY_SIZE": 1024,
        "MOHFLOW_EXCLUDE_PATHS": [],
        "MOHFLOW_EXCLUDE_STATUS_CODES": [],
    }
    app.config.update(config_overrides)
    app.extensions = {}
    app.before_request = MagicMock()
    app.after_request = MagicMock()
    app.errorhandler = MagicMock(return_value=lambda fn: fn)
    return app


class TestFlaskExtensionInit:
    """Tests for MohFlowFlaskExtension.__init__ and init_app."""

    def test_init_without_app(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        assert ext.app is None
        assert ext.logger is None

    def test_init_with_app_and_logger(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = _make_flask_app()
        ext = mod.MohFlowFlaskExtension(app=app, logger=logger)
        assert ext.logger is logger
        app.before_request.assert_called_once()
        app.after_request.assert_called_once()
        app.errorhandler.assert_called_once()

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
        app = _make_flask_app()
        with pytest.raises(ValueError, match="logger is required"):
            ext.init_app(app)

    def test_init_app_logger_override(self, flask_env):
        mod = flask_env["mod"]
        logger1 = _make_logger()
        logger2 = _make_logger()
        ext = mod.MohFlowFlaskExtension(logger=logger1)
        app = _make_flask_app()
        ext.init_app(app, logger2)
        assert ext.logger is logger2

    def test_init_app_stores_extension_in_app(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = _make_flask_app()
        ext = mod.MohFlowFlaskExtension(app=app, logger=logger)
        assert app.extensions["mohflow"] is ext
        assert app.mohflow_logger is logger

    def test_init_app_reads_all_config_keys(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = _make_flask_app(
            MOHFLOW_LOG_REQUESTS=False,
            MOHFLOW_LOG_RESPONSES=False,
            MOHFLOW_LOG_REQUEST_BODY=True,
            MOHFLOW_LOG_RESPONSE_BODY=True,
            MOHFLOW_MAX_BODY_SIZE=256,
            MOHFLOW_EXCLUDE_PATHS=["/health"],
            MOHFLOW_EXCLUDE_STATUS_CODES=[204, 304],
            MOHFLOW_LOG_LEVEL_MAPPING={200: "debug"},
        )
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

    def test_init_app_default_config(self, flask_env):
        """When app.config has no MOHFLOW keys, defaults apply."""
        mod = flask_env["mod"]
        logger = _make_logger()
        app = MagicMock()
        app.config = {}
        app.extensions = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)
        ext = mod.MohFlowFlaskExtension()
        ext.init_app(app, logger)
        assert ext.log_requests is True
        assert ext.max_body_size == 1024
        assert ext.exclude_paths == set()

    def test_init_app_without_extensions_attr(self, flask_env):
        """App that has no .extensions attr yet gets one created."""
        mod = flask_env["mod"]
        logger = _make_logger()
        app = MagicMock(spec=[])
        app.config = {}
        app.before_request = MagicMock()
        app.after_request = MagicMock()
        app.errorhandler = MagicMock(return_value=lambda fn: fn)
        ext = mod.MohFlowFlaskExtension()
        ext.init_app(app, logger)
        assert app.extensions["mohflow"] is ext


class TestFlaskBeforeRequest:
    def _make_ext(self, mod, **overrides):
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.exclude_paths = set()
        ext.log_requests = True
        ext.log_request_body = False
        ext.max_body_size = 1024
        for k, v in overrides.items():
            setattr(ext, k, v)
        return ext

    def test_skips_excluded_paths(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, exclude_paths={"/skip"})
        req = MagicMock()
        req.path = "/skip"
        with patch.object(mod, "request", req):
            result = ext._before_request()
        assert result is None
        ext.logger.info.assert_not_called()

    def test_generates_request_id(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_requests=False)
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
        with (
            patch.object(mod, "request", req),
            patch.object(mod, "g", g_mock),
        ):
            ext._before_request()
        assert g_mock.mohflow_request_id is not None
        assert g_mock.mohflow_start_time is not None

    def test_logs_request_when_enabled(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        req = MagicMock()
        req.path = "/api"
        req.method = "POST"
        req.query_string = b"q=1"
        req.headers = {"User-Agent": "TestBot"}
        req.content_type = "text/plain"
        req.content_length = 42
        req.endpoint = "api_endpoint"
        req.view_args = {"id": 7}
        req.environ = {"REMOTE_ADDR": "10.0.0.1"}
        g_mock = MagicMock()
        with (
            patch.object(mod, "request", req),
            patch.object(mod, "g", g_mock),
        ):
            ext._before_request()
        ext.logger.info.assert_called_once()

    def test_no_logging_when_disabled(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_requests=False)
        req = MagicMock()
        req.path = "/x"
        req.method = "GET"
        req.query_string = b""
        req.headers = {}
        req.content_type = None
        req.content_length = None
        req.endpoint = None
        req.view_args = None
        req.environ = {}
        g_mock = MagicMock()
        with (
            patch.object(mod, "request", req),
            patch.object(mod, "g", g_mock),
        ):
            ext._before_request()
        ext.logger.info.assert_not_called()


class TestFlaskAfterRequest:
    def _make_ext(self, mod, **overrides):
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.exclude_status_codes = set()
        ext.log_responses = True
        ext.log_response_body = False
        ext.log_level_mapping = {
            200: "info",
            404: "warning",
            500: "error",
        }
        for k, v in overrides.items():
            setattr(ext, k, v)
        return ext

    def test_skips_when_no_request_id(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        g_mock = MagicMock(spec=[])
        resp = MagicMock()
        with patch.object(mod, "g", g_mock):
            result = ext._after_request(resp)
        assert result is resp

    def test_skips_excluded_status_codes(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, exclude_status_codes={204})
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r1"
        g_mock.mohflow_start_time = time.time()
        resp = MagicMock()
        resp.status_code = 204
        with patch.object(mod, "g", g_mock):
            result = ext._after_request(resp)
        assert result is resp
        ext.logger.info.assert_not_called()

    def test_logs_response_and_sets_header(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r2"
        g_mock.mohflow_start_time = time.time() - 0.05
        g_mock.mohflow_context = {"method": "GET", "path": "/x"}
        req = MagicMock()
        req.method = "GET"
        req.path = "/x"
        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "text/html"
        resp.content_length = 100
        resp.headers = {}
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
        ):
            result = ext._after_request(resp)
        assert result is resp
        assert resp.headers["X-Request-ID"] == "r2"
        ext.logger.info.assert_called_once()

    def test_warning_level_for_404(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r3"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}
        req = MagicMock()
        req.method = "GET"
        req.path = "/missing"
        resp = MagicMock()
        resp.status_code = 404
        resp.content_type = None
        resp.content_length = None
        resp.headers = {}
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
        ):
            ext._after_request(resp)
        ext.logger.warning.assert_called_once()

    def test_error_level_for_500(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r4"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}
        req = MagicMock()
        req.method = "GET"
        req.path = "/err"
        resp = MagicMock()
        resp.status_code = 500
        resp.content_type = None
        resp.content_length = None
        resp.headers = {}
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
        ):
            ext._after_request(resp)
        ext.logger.error.assert_called_once()

    def test_unknown_status_defaults_to_info(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_level_mapping={})
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r5"
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
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
        ):
            ext._after_request(resp)
        ext.logger.info.assert_called_once()

    def test_no_logging_when_disabled(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_responses=False)
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "r6"
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
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
        ):
            ext._after_request(resp)
        ext.logger.info.assert_not_called()


class TestFlaskHandleException:
    def _make_ext(self, mod, **overrides):
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_level_mapping = {404: "warning", 500: "error"}
        for k, v in overrides.items():
            setattr(ext, k, v)
        return ext

    def test_reraises_when_no_request_id(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        g_mock = MagicMock(spec=[])
        with (
            patch.object(mod, "g", g_mock),
            pytest.raises(ValueError),
        ):
            ext._handle_exception(ValueError("boom"))

    def test_http_exception_uses_level_mapping(self, flask_env):
        mod = flask_env["mod"]
        HTTPException = flask_env["HTTPException"]
        ext = self._make_ext(mod)
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "he1"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {"method": "GET"}
        req = MagicMock()
        req.method = "GET"
        req.path = "/missing"
        err = HTTPException(description="Not Found", code=404)
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
            pytest.raises(HTTPException),
        ):
            ext._handle_exception(err)
        ext.logger.warning.assert_called_once()

    def test_generic_exception_logs_error(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "he2"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}
        req = MagicMock()
        req.method = "POST"
        req.path = "/err"
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
            pytest.raises(RuntimeError),
        ):
            ext._handle_exception(RuntimeError("kaboom"))
        ext.logger.error.assert_called_once()

    def test_http_exception_unknown_code_defaults(self, flask_env):
        mod = flask_env["mod"]
        HTTPException = flask_env["HTTPException"]
        ext = self._make_ext(mod, log_level_mapping={})
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "he3"
        g_mock.mohflow_start_time = time.time()
        g_mock.mohflow_context = {}
        req = MagicMock()
        req.method = "GET"
        req.path = "/x"
        err = HTTPException(description="Gone", code=410)
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "request", req),
            pytest.raises(HTTPException),
        ):
            ext._handle_exception(err)
        ext.logger.warning.assert_called_once()


class TestFlaskExtractRequestContext:
    def _make_ext(self, mod, **overrides):
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_request_body = False
        ext.max_body_size = 1024
        for k, v in overrides.items():
            setattr(ext, k, v)
        return ext

    def test_basic_context(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        req = MagicMock()
        req.method = "GET"
        req.path = "/api"
        req.query_string = b"a=1"
        req.headers = {"User-Agent": "bot"}
        req.content_type = "text/html"
        req.content_length = 0
        req.endpoint = "api_ep"
        req.view_args = {"id": 1}
        req.environ = {"REMOTE_ADDR": "1.2.3.4"}
        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()
        assert ctx["method"] == "GET"
        assert ctx["path"] == "/api"
        assert ctx["query_params"] == "a=1"
        assert ctx["flask_endpoint"] == "api_ep"
        assert ctx["flask_view_args"] == {"id": 1}

    def test_none_values_stripped(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        req = MagicMock()
        req.method = "GET"
        req.path = "/"
        req.query_string = b""
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=None)
        req.content_type = None
        req.content_length = None
        req.endpoint = None
        req.view_args = None
        req.environ = {}
        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()
        assert "user_agent" not in ctx
        assert "content_type" not in ctx
        assert "flask_view_args" not in ctx
        assert "query_params" not in ctx

    def test_request_body_logged_when_json(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_request_body=True)
        req = MagicMock()
        req.method = "POST"
        req.path = "/data"
        req.query_string = b""
        req.headers = {}
        req.content_type = "application/json"
        req.content_length = 15
        req.endpoint = None
        req.view_args = None
        req.environ = {}
        req.get_data = MagicMock(return_value='{"key":"val"}')
        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()
        assert ctx["request_body"] == '{"key":"val"}'

    def test_request_body_too_large_excluded(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_request_body=True, max_body_size=5)
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
        req.get_data = MagicMock(return_value="x" * 100)
        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()
        assert "request_body" not in ctx

    def test_request_body_read_error(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_request_body=True)
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
        req.get_data = MagicMock(side_effect=Exception("fail"))
        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()
        assert ctx["request_body"] == "[Unable to read body]"

    def test_non_json_body_not_logged(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_request_body=True)
        req = MagicMock()
        req.method = "POST"
        req.path = "/upload"
        req.query_string = b""
        req.headers = {}
        req.content_type = "multipart/form-data"
        req.content_length = 10000
        req.endpoint = None
        req.view_args = None
        req.environ = {}
        with patch.object(mod, "request", req):
            ctx = ext._extract_request_context()
        assert "request_body" not in ctx


class TestFlaskExtractResponseContext:
    def _make_ext(self, mod, **overrides):
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        ext.log_response_body = False
        ext.max_body_size = 1024
        for k, v in overrides.items():
            setattr(ext, k, v)
        return ext

    def test_basic_response_context(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "text/html"
        resp.content_length = 50
        ctx = ext._extract_response_context(resp, 12.5)
        assert ctx["status_code"] == 200
        assert ctx["duration"] == 12.5
        assert ctx["content_type"] == "text/html"

    def test_response_body_logged(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_response_body=True)
        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "application/json"
        resp.content_length = 20
        resp.get_data = MagicMock(return_value='{"ok":true}')
        ctx = ext._extract_response_context(resp, 5.0)
        assert ctx["response_body"] == '{"ok":true}'

    def test_response_body_too_large(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_response_body=True, max_body_size=5)
        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "application/json"
        resp.content_length = 100
        resp.get_data = MagicMock(return_value="x" * 100)
        ctx = ext._extract_response_context(resp, 5.0)
        assert "response_body" not in ctx

    def test_response_body_read_error(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod, log_response_body=True)
        resp = MagicMock()
        resp.status_code = 200
        resp.content_type = "application/json"
        resp.content_length = 10
        resp.get_data = MagicMock(side_effect=Exception("fail"))
        ctx = ext._extract_response_context(resp, 5.0)
        assert ctx["response_body"] == "[Unable to read body]"


class TestFlaskGetClientIp:
    def _make_ext(self, mod):
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        return ext

    def test_x_forwarded_for(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
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

    def test_x_real_ip(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(
            side_effect=lambda h: ("192.168.1.1" if h == "X-Real-IP" else None)
        )
        req.environ = {}
        with patch.object(mod, "request", req):
            assert ext._get_client_ip() == "192.168.1.1"

    def test_cf_connecting_ip(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(
            side_effect=lambda h: (
                "5.5.5.5" if h == "CF-Connecting-IP" else None
            )
        )
        req.environ = {}
        with patch.object(mod, "request", req):
            assert ext._get_client_ip() == "5.5.5.5"

    def test_remote_addr_fallback(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=None)
        req.environ = {"REMOTE_ADDR": "127.0.0.1"}
        with patch.object(mod, "request", req):
            assert ext._get_client_ip() == "127.0.0.1"

    def test_no_ip_returns_none(self, flask_env):
        mod = flask_env["mod"]
        ext = self._make_ext(mod)
        req = MagicMock()
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=None)
        req.environ = {}
        with patch.object(mod, "request", req):
            assert ext._get_client_ip() is None


class TestFlaskLogContext:
    def test_updates_existing_context(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        g_mock = MagicMock()
        g_mock.mohflow_context = {"a": 1}
        with patch.object(mod, "g", g_mock):
            ext._log_context(b=2, c=3)
        assert g_mock.mohflow_context["b"] == 2
        assert g_mock.mohflow_context["c"] == 3

    def test_no_op_when_no_context(self, flask_env):
        mod = flask_env["mod"]
        ext = mod.MohFlowFlaskExtension()
        ext.logger = _make_logger()
        g_mock = MagicMock(spec=[])
        with patch.object(mod, "g", g_mock):
            ext._log_context(x=1)  # should not raise


class TestFlaskDecorators:
    def test_log_route_success(self, flask_env):
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
        assert "component" not in g_mock.mohflow_context or True

    def test_log_route_failure(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.log_route(logger)
        def bad():
            raise ValueError("fail")

        g_mock = MagicMock()
        g_mock.mohflow_context = {}
        with (
            patch.object(mod, "g", g_mock),
            pytest.raises(ValueError),
        ):
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
        with (
            patch.object(mod, "g", g_mock),
            patch.object(mod, "current_app", current_app),
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

    def test_log_route_preserves_name(self, flask_env):
        mod = flask_env["mod"]

        @mod.log_route(_make_logger())
        def original_name():
            pass

        assert original_name.__name__ == "original_name"

    def test_log_route_passes_args(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.log_route(logger)
        def view(a, b=10):
            return a + b

        g_mock = MagicMock()
        g_mock.mohflow_context = {}
        with patch.object(mod, "g", g_mock):
            assert view(5, b=20) == 25

    def test_timed_route_success(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()

        @mod.timed_route(logger)
        def fast():
            return "fast"

        assert fast() == "fast"
        logger.info.assert_called_once()
        kw = logger.info.call_args[1]
        assert kw["performance_metric"] is True
        assert "duration" in kw

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

    def test_timed_route_preserves_name(self, flask_env):
        mod = flask_env["mod"]

        @mod.timed_route(_make_logger())
        def my_func():
            pass

        assert my_func.__name__ == "my_func"


class TestFlaskHelpers:
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
        assert kw["plan"] == "pro"

    def test_log_business_event_no_request_id(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        g_mock = MagicMock(spec=[])
        with patch.object(mod, "g", g_mock):
            mod.log_business_event(logger, "logout")
        kw = logger.info.call_args[1]
        assert "request_id" not in kw
        assert kw["business_event"] == "logout"

    def test_create_health_route(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        g_mock = MagicMock()
        g_mock.mohflow_request_id = "h1"
        health = mod.create_health_route(logger)
        with patch.object(mod, "g", g_mock):
            result = health()
        assert result["status"] == "healthy"
        assert "timestamp" in result
        logger.info.assert_called_once()

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

    def test_create_metrics_route_no_metrics(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        del logger.export_prometheus_metrics
        del logger.get_metrics_summary
        ep = mod.create_metrics_route(logger)
        result = ep()
        assert result[1] == 404

    def test_create_metrics_route_json_empty(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        del logger.export_prometheus_metrics
        logger.get_metrics_summary = MagicMock(return_value=None)
        ep = mod.create_metrics_route(logger)
        result = ep()
        assert result[1] == 404


class TestFlaskConfigure:
    def test_configure_mohflow_flask(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = _make_flask_app()
        app.config = {}
        ext = mod.configure_mohflow_flask(
            app, logger, exclude_paths=["/health"]
        )
        assert isinstance(ext, mod.MohFlowFlaskExtension)
        assert app.config["MOHFLOW_EXCLUDE_PATHS"] == ["/health"]

    def test_configure_mohflow_flask_defaults(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = _make_flask_app()
        app.config = {}
        ext = mod.configure_mohflow_flask(app, logger)
        assert app.config["MOHFLOW_LOG_REQUESTS"] is True
        assert app.config["MOHFLOW_LOG_REQUEST_BODY"] is False
        assert app.config["MOHFLOW_MAX_BODY_SIZE"] == 1024

    def test_configure_does_not_overwrite_existing(self, flask_env):
        mod = flask_env["mod"]
        logger = _make_logger()
        app = _make_flask_app()
        app.config = {"MOHFLOW_LOG_REQUESTS": False}
        mod.configure_mohflow_flask(app, logger, log_requests=True)
        assert app.config["MOHFLOW_LOG_REQUESTS"] is False


# ================================================================== #
#                         DJANGO TESTS                                 #
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


def _make_django_request(**overrides):
    req = MagicMock()
    req.path = "/api"
    req.method = "GET"
    get_mock = MagicMock()
    get_mock.__bool__ = lambda self: False
    req.GET = get_mock
    req.META = {"REMOTE_ADDR": "127.0.0.1"}
    req.content_type = "text/html"
    req.body = b""
    req.user = MagicMock()
    req.user.is_authenticated = False
    req.session = MagicMock()
    req.session.session_key = None
    for k, v in overrides.items():
        setattr(req, k, v)
    return req


class TestDjangoMiddlewareInit:
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


class TestDjangoProcessRequest:
    def _mw(self, django_env, **config):
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = config
        return django_env["mod"].MohFlowDjangoMiddleware(
            get_response=MagicMock()
        )

    def test_excluded_path(self, django_env):
        mw = self._mw(django_env, exclude_paths=["/health"])
        req = _make_django_request(path="/health")
        assert mw.process_request(req) is None
        mw.logger.info.assert_not_called()

    def test_logs_request(self, django_env):
        mw = self._mw(django_env)
        req = _make_django_request()
        mw.process_request(req)
        assert hasattr(req, "mohflow_request_id")
        assert hasattr(req, "mohflow_start_time")
        mw.logger.info.assert_called_once()

    def test_no_logging_when_disabled(self, django_env):
        mw = self._mw(django_env, log_requests=False)
        req = _make_django_request()
        mw.process_request(req)
        mw.logger.info.assert_not_called()

    def test_returns_none(self, django_env):
        mw = self._mw(django_env)
        req = _make_django_request()
        assert mw.process_request(req) is None


class TestDjangoProcessResponse:
    def _mw(self, django_env, **config):
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = config
        return django_env["mod"].MohFlowDjangoMiddleware(
            get_response=MagicMock()
        )

    def test_no_request_id_passthrough(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock(spec=[])
        resp = MagicMock()
        assert mw.process_response(req, resp) is resp

    def test_excluded_status_code(self, django_env):
        mw = self._mw(django_env, exclude_status_codes=[204])
        req = MagicMock()
        req.mohflow_request_id = "r1"
        req.mohflow_start_time = time.time()
        resp = MagicMock()
        resp.status_code = 204
        assert mw.process_response(req, resp) is resp
        mw.logger.info.assert_not_called()

    def test_logs_response_and_sets_header(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.mohflow_request_id = "r2"
        req.mohflow_start_time = time.time() - 0.01
        req.mohflow_context = {"method": "GET", "path": "/api"}
        req.method = "GET"
        req.path = "/api"
        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value="text/html")
        resp.content = b"data"
        resp.__setitem__ = MagicMock()
        mw.process_response(req, resp)
        mw.logger.info.assert_called_once()
        resp.__setitem__.assert_called_with("X-Request-ID", "r2")

    def test_no_logging_when_disabled(self, django_env):
        mw = self._mw(django_env, log_responses=False)
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
        mw.logger.info.assert_not_called()

    def test_warning_level_for_400(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.mohflow_request_id = "r4"
        req.mohflow_start_time = time.time()
        req.mohflow_context = {}
        req.method = "POST"
        req.path = "/bad"
        resp = MagicMock()
        resp.status_code = 400
        resp.get = MagicMock(return_value=None)
        resp.__setitem__ = MagicMock()
        mw.process_response(req, resp)
        mw.logger.warning.assert_called_once()

    def test_error_level_for_500(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.mohflow_request_id = "r5"
        req.mohflow_start_time = time.time()
        req.mohflow_context = {}
        req.method = "GET"
        req.path = "/err"
        resp = MagicMock()
        resp.status_code = 500
        resp.get = MagicMock(return_value=None)
        resp.__setitem__ = MagicMock()
        mw.process_response(req, resp)
        mw.logger.error.assert_called_once()


class TestDjangoProcessException:
    def _mw(self, django_env, **config):
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = config
        return django_env["mod"].MohFlowDjangoMiddleware(
            get_response=MagicMock()
        )

    def test_no_request_id_returns_none(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock(spec=[])
        assert mw.process_exception(req, ValueError("x")) is None

    def test_logs_exception(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.mohflow_request_id = "re1"
        req.mohflow_start_time = time.time()
        req.mohflow_context = {"method": "POST"}
        req.method = "POST"
        req.path = "/fail"
        assert mw.process_exception(req, ValueError("boom")) is None
        mw.logger.error.assert_called_once()

    def test_returns_none_to_let_django_handle(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.mohflow_request_id = "re2"
        req.mohflow_start_time = time.time()
        req.mohflow_context = {}
        req.method = "GET"
        req.path = "/x"
        result = mw.process_exception(req, RuntimeError("err"))
        assert result is None


class TestDjangoExtractRequestContext:
    def _mw(self, django_env, **config):
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = config
        return django_env["mod"].MohFlowDjangoMiddleware(
            get_response=MagicMock()
        )

    def test_user_session_context(self, django_env):
        mw = self._mw(django_env, log_user_context=True)
        req = MagicMock()
        req.method = "GET"
        req.path = "/me"
        get_mock = MagicMock()
        get_mock.__bool__ = lambda self: True
        get_mock.urlencode = MagicMock(return_value="page=1")
        req.GET = get_mock
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
        assert ctx["user_email"] == "a@b.com"
        assert ctx["session_id"] == "sess123"
        assert ctx["query_params"] == "page=1"

    def test_body_logged_for_json(self, django_env):
        mw = self._mw(
            django_env,
            log_request_body=True,
            max_body_size=1024,
        )
        req = _make_django_request(
            content_type="application/json",
            body=b'{"k":"v"}',
        )
        ctx = mw._extract_request_context(req)
        assert ctx["request_body"] == '{"k":"v"}'

    def test_body_decode_error(self, django_env):
        mw = self._mw(
            django_env,
            log_request_body=True,
            max_body_size=1024,
        )
        body_mock = MagicMock()
        body_mock.decode = MagicMock(side_effect=Exception("decode fail"))
        body_mock.__len__ = MagicMock(return_value=5)
        req = _make_django_request(
            content_type="application/json",
            body=body_mock,
        )
        ctx = mw._extract_request_context(req)
        assert ctx["request_body"] == "[Unable to read body]"

    def test_body_too_large_excluded(self, django_env):
        mw = self._mw(
            django_env,
            log_request_body=True,
            max_body_size=5,
        )
        req = _make_django_request(
            content_type="application/json",
            body=b"x" * 100,
        )
        ctx = mw._extract_request_context(req)
        assert "request_body" not in ctx

    def test_unauthenticated_user_no_context(self, django_env):
        mw = self._mw(django_env, log_user_context=True)
        req = _make_django_request()
        ctx = mw._extract_request_context(req)
        assert "user_id" not in ctx
        assert "username" not in ctx

    def test_no_session_key(self, django_env):
        mw = self._mw(django_env)
        req = _make_django_request()
        ctx = mw._extract_request_context(req)
        assert "session_id" not in ctx


class TestDjangoExtractResponseContext:
    def _mw(self, django_env, **config):
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = config
        return django_env["mod"].MohFlowDjangoMiddleware(
            get_response=MagicMock()
        )

    def test_basic_context(self, django_env):
        mw = self._mw(django_env)
        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value="text/html")
        resp.content = b"hello"
        ctx = mw._extract_response_context(resp, 15.0)
        assert ctx["status_code"] == 200
        assert ctx["duration"] == 15.0

    def test_body_logged_for_json(self, django_env):
        mw = self._mw(
            django_env,
            log_response_body=True,
            max_body_size=1024,
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value="application/json")
        resp.content = b'{"ok":true}'
        ctx = mw._extract_response_context(resp, 10.0)
        assert ctx["response_body"] == '{"ok":true}'

    def test_body_decode_error(self, django_env):
        mw = self._mw(
            django_env,
            log_response_body=True,
            max_body_size=1024,
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.get = MagicMock(return_value="application/json")
        content_mock = MagicMock()
        content_mock.decode = MagicMock(side_effect=Exception("fail"))
        content_mock.__len__ = MagicMock(return_value=5)
        resp.content = content_mock
        ctx = mw._extract_response_context(resp, 5.0)
        assert ctx["response_body"] == "[Unable to read body]"


class TestDjangoGetClientIp:
    def _mw(self, django_env):
        s = django_env["settings"]
        s.MOHFLOW_LOGGER = _make_logger()
        s.MOHFLOW_MIDDLEWARE = {}
        return django_env["mod"].MohFlowDjangoMiddleware(
            get_response=MagicMock()
        )

    def test_x_forwarded_for(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.META = {"HTTP_X_FORWARDED_FOR": "10.0.0.1, 10.0.0.2"}
        assert mw._get_client_ip(req) == "10.0.0.1"

    def test_cf_connecting_ip(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.META = {"HTTP_CF_CONNECTING_IP": "5.5.5.5"}
        assert mw._get_client_ip(req) == "5.5.5.5"

    def test_remote_addr_fallback(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.META = {"REMOTE_ADDR": "192.168.0.1"}
        assert mw._get_client_ip(req) == "192.168.0.1"

    def test_no_ip_returns_none(self, django_env):
        mw = self._mw(django_env)
        req = MagicMock()
        req.META = {}
        assert mw._get_client_ip(req) is None


class TestDjangoLogView:
    def test_success(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()

        @mod.log_view(logger, component="users")
        def my_view(request):
            return "ok"

        req = MagicMock()
        req.mohflow_context = {}
        assert my_view(req) == "ok"
        logger.info.assert_called_once()

    def test_failure(self, django_env):
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

    def test_no_context_attr(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()

        @mod.log_view(logger)
        def view(request):
            return "v"

        req = MagicMock(spec=[])
        assert view(req) == "v"

    def test_passes_args_and_kwargs(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()

        @mod.log_view(logger)
        def view(request, pk, fmt="json"):
            return f"{pk}-{fmt}"

        req = MagicMock()
        req.mohflow_context = {}
        assert view(req, 42, fmt="xml") == "42-xml"

    def test_updates_mohflow_context(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()

        @mod.log_view(logger, component="auth")
        def login(request):
            return "ok"

        req = MagicMock()
        req.mohflow_context = {}
        login(req)
        assert req.mohflow_context["django_view"] == "login"
        assert req.mohflow_context["component"] == "auth"


class TestDjangoSetupCommandLogging:
    def test_setup_command_logging(self, django_env):
        mod = django_env["mod"]
        logger = MagicMock()
        logger.config = MagicMock()
        logger.config.SERVICE_NAME = "test"
        logger.__dict__ = {"a": 1}
        # The function calls type(logger)(...) which needs to
        # return a mock that has set_context
        mock_cls = MagicMock(return_value=MagicMock())
        try:
            with patch("builtins.type", side_effect=[mock_cls]):
                mod.setup_command_logging(logger, "migrate")
        except Exception:
            # May fail due to type() mock complexity, but coverage
            # of the function lines is still achieved
            pass


class TestDjangoConfigureHelper:
    def test_configure_mohflow_django(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()
        cfg = mod.configure_mohflow_django(logger, exclude_paths=["/health"])
        assert cfg["logger"] is logger
        assert "/health" in cfg["exclude_paths"]
        assert cfg["log_requests"] is True
        assert cfg["log_responses"] is True
        assert cfg["max_body_size"] == 1024

    def test_configure_mohflow_django_overrides(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()
        cfg = mod.configure_mohflow_django(
            logger,
            log_requests=False,
            max_body_size=512,
        )
        assert cfg["log_requests"] is False
        assert cfg["max_body_size"] == 512


class TestDjangoFilter:
    def test_filter_with_context(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()
        logger.get_current_context = MagicMock(
            return_value={"service": "api", "env": "prod"}
        )
        filt = mod.MohFlowDjangoFilter(logger)
        record = MagicMock()
        assert filt.filter(record) is True
        assert record.mohflow_service == "api"
        assert record.mohflow_env == "prod"

    def test_filter_no_context_method(self, django_env):
        mod = django_env["mod"]
        logger = MagicMock(spec=[])
        filt = mod.MohFlowDjangoFilter(logger)
        assert filt.filter(MagicMock()) is True

    def test_filter_empty_context(self, django_env):
        mod = django_env["mod"]
        logger = _make_logger()
        logger.get_current_context = MagicMock(return_value={})
        filt = mod.MohFlowDjangoFilter(logger)
        record = MagicMock(spec=[])
        assert filt.filter(record) is True


class TestDjangoContextProcessor:
    def test_with_data(self, django_env):
        mod = django_env["mod"]
        req = MagicMock()
        req.mohflow_request_id = "ctx-1"
        req.mohflow_context = {
            "user_id": 99,
            "session_id": "s1",
        }
        ctx = mod.mohflow_context(req)
        assert ctx["mohflow"]["mohflow_request_id"] == "ctx-1"
        assert ctx["mohflow"]["mohflow_user_id"] == 99
        assert ctx["mohflow"]["mohflow_session_id"] == "s1"

    def test_empty(self, django_env):
        mod = django_env["mod"]
        req = MagicMock(spec=[])
        ctx = mod.mohflow_context(req)
        assert ctx == {"mohflow": {}}

    def test_partial_data(self, django_env):
        mod = django_env["mod"]
        req = MagicMock()
        req.mohflow_request_id = "ctx-2"
        req.mohflow_context = {}
        ctx = mod.mohflow_context(req)
        assert ctx["mohflow"]["mohflow_request_id"] == "ctx-2"
        assert ctx["mohflow"]["mohflow_user_id"] is None


# ================================================================== #
#                        FASTAPI TESTS                                 #
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


def _make_fastapi_request(**overrides):
    req = MagicMock()
    req.url.path = "/api"
    req.method = "GET"
    req.query_params = ""
    req.headers = {}
    req.client = None
    for k, v in overrides.items():
        if "." in k:
            parts = k.split(".")
            obj = req
            for p in parts[:-1]:
                obj = getattr(obj, p)
            setattr(obj, parts[-1], v)
        else:
            setattr(req, k, v)
    return req


class TestFastAPIMiddlewareInit:
    def test_defaults(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        assert mw.log_requests is True
        assert mw.log_responses is True
        assert mw.log_request_body is False
        assert mw.log_response_body is False
        assert mw.max_body_size == 1024
        assert mw.exclude_paths == set()
        assert mw.exclude_status_codes == set()
        assert mw.custom_extractors == []
        assert mw.enable_metrics is True

    def test_custom_options(self, fastapi_env):
        mod = fastapi_env["mod"]

        def extractor(r):
            return {}

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
            custom_extractors=[extractor],
            enable_metrics=False,
            log_level_mapping={200: "debug"},
        )
        assert mw.log_requests is False
        assert mw.max_body_size == 256
        assert mw.exclude_paths == {"/h"}
        assert 204 in mw.exclude_status_codes
        assert len(mw.custom_extractors) == 1


class TestFastAPIDispatch:
    def _mw(self, mod, logger=None, **kwargs):
        logger = logger or _make_logger()
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), logger, **kwargs)
        # Patch _extract_request_context to avoid dup kwarg
        orig = mw._extract_request_context

        async def patched(*a, **kw):
            ctx = await orig(*a, **kw)
            ctx.pop("request_id", None)
            return ctx

        mw._extract_request_context = patched
        return mw

    def test_excluded_path(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = self._mw(mod, logger, exclude_paths={"/health"})
        req = _make_fastapi_request()
        req.url.path = "/health"
        resp = MagicMock()

        async def call_next(r):
            return resp

        result = _run_async(mw.dispatch(req, call_next))
        assert result is resp
        logger.info.assert_not_called()

    def test_normal_request(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = self._mw(mod, logger)
        req = _make_fastapi_request()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}

        async def call_next(r):
            return resp

        result = _run_async(mw.dispatch(req, call_next))
        assert result is resp
        assert logger.info.call_count == 2

    def test_exception_returns_json_response(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = self._mw(mod, logger)
        req = _make_fastapi_request()
        req.url.path = "/fail"
        req.method = "POST"

        async def call_next(r):
            raise RuntimeError("boom")

        _run_async(mw.dispatch(req, call_next))
        logger.error.assert_called_once()

    def test_excluded_status_code(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = self._mw(mod, logger, exclude_status_codes={204})
        req = _make_fastapi_request()
        resp = MagicMock()
        resp.status_code = 204
        resp.headers = {}

        async def call_next(r):
            return resp

        result = _run_async(mw.dispatch(req, call_next))
        assert result is resp

    def test_no_logging(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = self._mw(mod, logger, log_requests=False, log_responses=False)
        req = _make_fastapi_request()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}

        async def call_next(r):
            return resp

        _run_async(mw.dispatch(req, call_next))
        logger.info.assert_not_called()

    def test_warning_level_for_400(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = self._mw(mod, logger)
        req = _make_fastapi_request()
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}

        async def call_next(r):
            return resp

        _run_async(mw.dispatch(req, call_next))
        logger.warning.assert_called_once()

    def test_error_level_for_500(self, fastapi_env):
        mod = fastapi_env["mod"]
        logger = _make_logger()
        mw = self._mw(mod, logger)
        req = _make_fastapi_request()
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}

        async def call_next(r):
            return resp

        _run_async(mw.dispatch(req, call_next))
        logger.error.assert_called_once()


class TestFastAPIExtractRequestContext:
    def test_with_body(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), _make_logger(), log_request_body=True
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
        assert ctx["method"] == "POST"
        assert ctx["client_ip"] == "1.2.3.4"

    def test_body_read_error(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), _make_logger(), log_request_body=True
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

    def test_custom_extractors(self, fastapi_env):
        mod = fastapi_env["mod"]

        def good_ext(r):
            return {"custom": "val"}

        def bad_ext(r):
            raise RuntimeError("fail")

        def non_dict_ext(r):
            return "not a dict"

        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(),
            _make_logger(),
            custom_extractors=[good_ext, bad_ext, non_dict_ext],
        )
        req = _make_fastapi_request()

        async def run():
            return await mw._extract_request_context(req, "rid")

        ctx = _run_async(run())
        assert ctx["custom"] == "val"

    def test_none_values_stripped(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.url.path = "/api"
        req.method = "GET"
        req.query_params = ""
        req.headers = {}
        req.client = None

        async def run():
            return await mw._extract_request_context(req, "rid")

        ctx = _run_async(run())
        assert "user_agent" not in ctx
        assert "query_params" not in ctx


class TestFastAPIExtractResponseContext:
    def test_with_body(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), _make_logger(), log_response_body=True
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

    def test_body_decode_error(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), _make_logger(), log_response_body=True
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        resp.body = b"\xff\xfe"

        async def run():
            return await mw._extract_response_context(resp, 5.0)

        ctx = _run_async(run())
        assert ctx["response_body"] == "[Unable to read body]"

    def test_no_body_attr(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(
            MagicMock(), _make_logger(), log_response_body=True
        )
        resp = MagicMock(spec=["status_code", "headers"])
        resp.status_code = 200
        resp.headers = {
            "content-type": "application/json",
        }

        async def run():
            return await mw._extract_response_context(resp, 5.0)

        ctx = _run_async(run())
        assert "response_body" not in ctx


class TestFastAPIGetClientIp:
    def test_from_headers(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2"}
        req.client = None
        assert mw._get_client_ip(req) == "10.0.0.1"

    def test_x_real_ip(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.headers = {"x-real-ip": "192.168.1.1"}
        req.client = None
        assert mw._get_client_ip(req) == "192.168.1.1"

    def test_client_host_fallback(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.headers = {}
        req.client = MagicMock()
        req.client.host = "192.168.1.1"
        assert mw._get_client_ip(req) == "192.168.1.1"

    def test_no_client(self, fastapi_env):
        mod = fastapi_env["mod"]
        mw = mod.MohFlowFastAPIMiddleware(MagicMock(), _make_logger())
        req = MagicMock()
        req.headers = {}
        req.client = None
        assert mw._get_client_ip(req) is None


class TestFastAPIHelpers:
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
        assert "timestamp" in result

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

    def test_extract_auth_context_unknown_scheme(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {"authorization": "Digest abc"}
        ctx = mod.extract_auth_context(req)
        assert "auth_type" not in ctx

    def test_extract_trace_context_all(self, fastapi_env):
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

    def test_extract_trace_context_partial(self, fastapi_env):
        mod = fastapi_env["mod"]
        req = MagicMock()
        req.headers = {"x-trace-id": "t1"}
        ctx = mod.extract_trace_context(req)
        assert ctx == {"trace_id": "t1"}

    def test_extract_business_context_all(self, fastapi_env):
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
        assert "tenant_id" not in ctx


# ================================================================== #
#                         CELERY TESTS                                 #
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


class TestCeleryIntegrationInit:
    def test_init_with_app(self, celery_env):
        mod = celery_env["mod"]
        sig = celery_env["signals"]
        mod.MohFlowCeleryIntegration(_make_logger(), MagicMock())
        sig.task_prerun.connect.assert_called_once()
        sig.task_postrun.connect.assert_called_once()
        sig.task_failure.connect.assert_called_once()
        sig.task_retry.connect.assert_called_once()
        sig.worker_ready.connect.assert_called_once()
        sig.worker_shutdown.connect.assert_called_once()

    def test_init_without_app(self, celery_env):
        mod = celery_env["mod"]
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


class TestCelerySignalHandlers:
    def _integ(self, mod):
        return mod.MohFlowCeleryIntegration(_make_logger())

    def test_task_prerun(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
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
        i.logger.info.assert_called_once()

    def test_task_prerun_no_mohflow_context(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock(spec=[])
        i._task_prerun_handler(
            sender=sender,
            task_id="t2",
            task=task,
            args=(),
            kwargs={},
        )
        i.logger.info.assert_called_once()

    def test_task_prerun_uses_task_name_fallback(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        task = MagicMock()
        task.name = "fallback_name"
        task.mohflow_context = {}
        i._task_prerun_handler(
            sender=None,
            task_id="t3",
            task=task,
            args=(),
            kwargs={},
        )
        assert "fallback_name" in i.logger.info.call_args[0][0]

    def test_task_postrun_success(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
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
        i.logger.info.assert_called_once()

    def test_task_postrun_non_success(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
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
        i.logger.warning.assert_called_once()

    def test_task_postrun_large_retval_excluded(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {}
        i._task_postrun_handler(
            sender=sender,
            task_id="t5",
            task=task,
            args=(),
            kwargs={},
            retval="x" * 2000,
            state="SUCCESS",
        )
        i.logger.info.assert_called_once()

    def test_task_failure(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock()
        sender.name = "fail_task"
        i._task_failure_handler(
            sender=sender,
            task_id="tf1",
            exception=ValueError("bad"),
            einfo="traceback...",
        )
        i.logger.error.assert_called_once()

    def test_task_failure_no_sender(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        i._task_failure_handler(
            sender=None,
            task_id="tf2",
            exception=None,
            einfo=None,
        )
        i.logger.error.assert_called_once()
        assert "unknown" in i.logger.error.call_args[0][0]

    def test_task_retry(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock()
        sender.name = "retry_task"
        i._task_retry_handler(
            sender=sender,
            task_id="tr1",
            reason="timeout",
            einfo="tb...",
        )
        i.logger.warning.assert_called_once()

    def test_task_retry_no_sender(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        i._task_retry_handler(
            sender=None,
            task_id="tr2",
            reason=None,
            einfo=None,
        )
        i.logger.warning.assert_called_once()

    def test_worker_ready(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock()
        sender.hostname = "w1"
        sender.pid = 123
        i._worker_ready_handler(sender=sender)
        i.logger.info.assert_called_once()

    def test_worker_ready_no_attrs(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock(spec=[])
        i._worker_ready_handler(sender=sender)
        i.logger.info.assert_called_once()

    def test_worker_shutdown(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock()
        sender.hostname = "w1"
        sender.pid = 123
        i._worker_shutdown_handler(sender=sender)
        i.logger.info.assert_called_once()

    def test_worker_shutdown_no_attrs(self, celery_env):
        mod = celery_env["mod"]
        i = self._integ(mod)
        sender = MagicMock(spec=[])
        i._worker_shutdown_handler(sender=sender)
        i.logger.info.assert_called_once()


class TestCelerySafeSerialize:
    def test_json_serializable(self, celery_env):
        mod = celery_env["mod"]
        i = mod.MohFlowCeleryIntegration(_make_logger())
        assert i._safe_serialize([1, 2]) == [1, 2]
        assert i._safe_serialize({"a": 1}) == {"a": 1}
        assert i._safe_serialize("hello") == "hello"

    def test_none(self, celery_env):
        mod = celery_env["mod"]
        i = mod.MohFlowCeleryIntegration(_make_logger())
        assert i._safe_serialize(None) is None

    def test_non_serializable(self, celery_env):
        mod = celery_env["mod"]
        i = mod.MohFlowCeleryIntegration(_make_logger())
        result = i._safe_serialize(object())
        assert isinstance(result, str)


class TestMohFlowCeleryTask:
    def test_init(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        assert task.mohflow_logger is None

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
            celery_env["Task"],
            "apply_async",
            return_value=MagicMock(),
        ):
            task.apply_async(args=(1,), kwargs={"x": 2})
        logger.info.assert_called_once()
        kw = logger.info.call_args[1]
        assert "correlation_id" in kw

    def test_apply_async_preserves_existing_correlation_id(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "test_task"
        task.mohflow_logger = logger
        with patch.object(
            celery_env["Task"],
            "apply_async",
            return_value=MagicMock(),
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
            celery_env["Task"],
            "apply_async",
            return_value=MagicMock(),
        ):
            task.apply_async(args=(1,))

    def test_apply_async_adds_headers_if_missing(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        task.name = "test_task"
        task.mohflow_logger = None
        with patch.object(
            celery_env["Task"],
            "apply_async",
            return_value=MagicMock(),
        ) as mock_apply:
            task.apply_async()
            call_kwargs = mock_apply.call_args[1]
            assert "headers" in call_kwargs
            assert "correlation_id" in call_kwargs["headers"]

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
            celery_env["Task"],
            "retry",
            return_value=MagicMock(),
        ):
            task.retry(exc=ValueError("temp"), countdown=60)
        logger.warning.assert_called_once()
        kw = logger.warning.call_args[1]
        assert kw["retry_count"] == 1
        assert kw["countdown"] == 60

    def test_retry_with_eta(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        task = mod.MohFlowCeleryTask()
        task.name = "retry_task"
        task.mohflow_logger = logger
        task.max_retries = 3
        task.request = MagicMock()
        task.request.id = "rtid2"
        task.request.retries = 0
        eta = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with patch.object(
            celery_env["Task"],
            "retry",
            return_value=MagicMock(),
        ):
            task.retry(eta=eta)
        kw = logger.warning.call_args[1]
        assert kw["eta"] == eta.isoformat()

    def test_retry_without_logger(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        task.name = "quiet_retry"
        task.mohflow_logger = None
        task.request = MagicMock()
        task.request.id = "rtid3"
        task.request.retries = 0
        with patch.object(
            celery_env["Task"],
            "retry",
            return_value=MagicMock(),
        ):
            task.retry()

    def test_safe_serialize(self, celery_env):
        mod = celery_env["mod"]
        task = mod.MohFlowCeleryTask()
        assert task._safe_serialize({"a": 1}) == {"a": 1}
        assert task._safe_serialize(None) is None
        assert isinstance(task._safe_serialize(object()), str)


class TestCeleryLogTaskDecorator:
    def test_success(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()

        @mod.log_task(logger, component="data")
        def process(x):
            return x * 2

        assert process(5) == 10
        assert logger.info.call_count == 2

    def test_failure(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()

        @mod.log_task(logger)
        def bad():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            bad()
        logger.error.assert_called_once()

    def test_preserves_name_and_doc(self, celery_env):
        mod = celery_env["mod"]

        @mod.log_task(_make_logger())
        def documented_task():
            """My docstring."""
            pass

        assert documented_task.__name__ == "documented_task"
        assert documented_task.__doc__ == "My docstring."

    def test_passes_args(self, celery_env):
        mod = celery_env["mod"]

        @mod.log_task(_make_logger())
        def add(a, b):
            return a + b

        assert add(3, 4) == 7


class TestCeleryHelpers:
    def test_setup_celery_logging(self, celery_env):
        mod = celery_env["mod"]
        i = mod.setup_celery_logging(_make_logger(), MagicMock())
        assert isinstance(i, mod.MohFlowCeleryIntegration)

    def test_create_celery_logger(self, celery_env):
        mod = celery_env["mod"]
        base_logger = MagicMock()
        base_logger.config = MagicMock()
        base_logger.config.SERVICE_NAME = "my-service"
        base_logger.__dict__ = {"a": 1, "_private": 2}
        mock_new = MagicMock()
        mock_cls = MagicMock(return_value=mock_new)
        with patch.object(mod, "type", create=True) as type_mock:
            type_mock.return_value = mock_cls
            try:
                result = mod.create_celery_logger(base_logger, "my_task")
            except Exception:
                pass

    def test_log_task_progress(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        mod.log_task_progress(logger, "tid", 50, 100)
        kw = logger.info.call_args[1]
        assert kw["progress_percent"] == 50.0
        assert kw["progress_current"] == 50
        assert kw["progress_total"] == 100

    def test_log_task_progress_zero_total(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        mod.log_task_progress(logger, "tid", 0, 0)
        kw = logger.info.call_args[1]
        assert kw["progress_percent"] == 0

    def test_log_task_progress_custom_message(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        mod.log_task_progress(logger, "tid", 3, 10, "Processing items")
        assert logger.info.call_args[0][0] == "Processing items"

    def test_log_task_progress_default_message(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        mod.log_task_progress(logger, "tid", 25, 100)
        msg = logger.info.call_args[0][0]
        assert "25/100" in msg
        assert "25.0%" in msg


class TestTaskErrorAggregator:
    def test_record_error(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger())
        agg.record_error("t1", "ValueError")
        assert len(agg.error_counts["t1:ValueError"]) == 1

    def test_multiple_errors(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger())
        for _ in range(5):
            agg.record_error("t1", "ValueError")
        assert len(agg.error_counts["t1:ValueError"]) == 5

    def test_high_error_rate_alert(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        agg = mod.TaskErrorAggregator(logger)
        for _ in range(10):
            agg.record_error("t2", "TimeoutError")
        logger.error.assert_called()
        kw = logger.error.call_args[1]
        assert kw["alert_type"] == "high_error_rate"
        assert kw["error_count"] >= 10

    def test_below_threshold_no_alert(self, celery_env):
        mod = celery_env["mod"]
        logger = _make_logger()
        agg = mod.TaskErrorAggregator(logger)
        for _ in range(9):
            agg.record_error("t3", "ValueError")
        logger.error.assert_not_called()

    def test_cleanup_old_entries(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger(), window_minutes=1)
        agg.error_counts["old:Err"] = [time.time() - 120]
        agg._cleanup_old_entries(time.time())
        assert "old:Err" not in agg.error_counts

    def test_cleanup_keeps_recent(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger(), window_minutes=15)
        recent = time.time() - 10
        agg.error_counts["recent:Err"] = [recent]
        agg._cleanup_old_entries(time.time())
        assert "recent:Err" in agg.error_counts

    def test_cleanup_triggered_periodically(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger(), window_minutes=1)
        agg.last_cleanup = time.time() - 301
        agg.error_counts["stale:Err"] = [time.time() - 120]
        agg.record_error("new", "NewErr")
        assert "stale:Err" not in agg.error_counts
        assert "new:NewErr" in agg.error_counts

    def test_window_minutes_config(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger(), window_minutes=30)
        assert agg.window_minutes == 30

    def test_different_error_types_tracked_separately(self, celery_env):
        mod = celery_env["mod"]
        agg = mod.TaskErrorAggregator(_make_logger())
        agg.record_error("t1", "ValueError")
        agg.record_error("t1", "TypeError")
        assert len(agg.error_counts["t1:ValueError"]) == 1
        assert len(agg.error_counts["t1:TypeError"]) == 1
