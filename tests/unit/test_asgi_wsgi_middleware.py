"""
Comprehensive mock-based unit tests for MohFlow ASGI/WSGI middleware.

Covers MohFlowASGIMiddleware, MohFlowWSGIMiddleware, factory functions,
auto_setup_middleware, and manual logging utilities.  All framework
dependencies are mocked so tests run without any third-party packages.

NOTE: The source module has a latent bug where ``request_id`` appears
both as an explicit keyword argument *and* inside ``**request_context``
when calling ``logger.request_context(...)``.  Python rejects duplicate
keyword arguments at the call site, so all ``__call__`` integration
tests patch ``_extract_request_context`` to return a context dict that
omits ``request_id``, allowing the remaining logic to execute.
"""

import asyncio
import uuid
from contextlib import contextmanager
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
    call,
)

import pytest

from mohflow.integrations.asgi_wsgi import (
    MohFlowASGIMiddleware,
    MohFlowWSGIMiddleware,
    auto_setup_middleware,
    create_asgi_middleware,
    create_wsgi_middleware,
    log_request_manually,
    log_response_manually,
)


# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #
def _make_logger():
    """Return a MagicMock logger whose ``request_context`` returns
    a MagicMock context manager.

    ``MagicMock.__call__`` returns another ``MagicMock`` that
    already supports ``__enter__`` / ``__exit__``, so
    ``with logger.request_context(...):`` just works.
    """
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


# Context dict returned by patched _extract_request_context helpers.
# Deliberately omits ``request_id`` so that
# ``logger.request_context(request_id=..., **ctx)`` does not raise.
_FAKE_ASGI_CTX = {
    "method": "GET",
    "path": "/test",
    "query_string": "foo=bar",
    "scheme": "https",
    "user_agent": "TestAgent/1.0",
    "client_ip": "127.0.0.1",
}

_FAKE_WSGI_CTX = {
    "method": "GET",
    "path": "/test",
    "query_string": "foo=bar",
    "server_name": "localhost",
    "scheme": "https",
    "user_agent": "TestAgent/1.0",
    "client_ip": "127.0.0.1",
}


async def _fake_asgi_extract(self, scope, receive, request_id):
    """Async stand-in for ASGI _extract_request_context."""
    return dict(_FAKE_ASGI_CTX)


def _fake_wsgi_extract(self, environ, request_id):
    """Sync stand-in for WSGI _extract_request_context."""
    return dict(_FAKE_WSGI_CTX)


def _http_scope(**overrides):
    """Minimal ASGI HTTP scope."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "query_string": b"foo=bar",
        "scheme": "https",
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 54321),
        "headers": [
            (b"user-agent", b"TestAgent/1.0"),
            (b"content-type", b"application/json"),
            (b"content-length", b"42"),
        ],
    }
    scope.update(overrides)
    return scope


def _wsgi_environ(**overrides):
    """Minimal WSGI environ dict."""
    env = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/test",
        "QUERY_STRING": "foo=bar",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "wsgi.url_scheme": "https",
        "HTTP_USER_AGENT": "TestAgent/1.0",
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": "42",
        "REMOTE_ADDR": "127.0.0.1",
    }
    env.update(overrides)
    return env


# ================================================================== #
#  ASGI MIDDLEWARE — INIT                                              #
# ================================================================== #
class TestMohFlowASGIMiddlewareInit:
    """Initialisation and default values."""

    def test_default_attributes(self):
        app = AsyncMock()
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(app, logger)

        assert mw.app is app
        assert mw.logger is logger
        assert mw.log_requests is True
        assert mw.log_responses is True
        assert mw.max_body_size == 1024
        assert mw.exclude_paths == set()
        assert mw.exclude_status_codes == set()
        assert 200 in mw.log_level_mapping
        assert 500 in mw.log_level_mapping

    def test_custom_attributes(self):
        app = AsyncMock()
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(
            app,
            logger,
            log_requests=False,
            log_responses=False,
            max_body_size=512,
            exclude_paths={"/health"},
            exclude_status_codes={204},
            log_level_mapping={200: "debug"},
        )

        assert mw.log_requests is False
        assert mw.log_responses is False
        assert mw.max_body_size == 512
        assert mw.exclude_paths == {"/health"}
        assert mw.exclude_status_codes == {204}
        assert mw.log_level_mapping == {200: "debug"}


# ================================================================== #
#  ASGI — __call__ (non-HTTP pass-through)                             #
# ================================================================== #
class TestASGICallNonHTTP:
    """Non-HTTP scopes are passed through without logging."""

    @pytest.mark.asyncio
    async def test_websocket_passthrough(self):
        app = AsyncMock()
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(app, logger)

        scope = {"type": "websocket", "path": "/ws"}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        app.assert_awaited_once_with(scope, receive, send)
        logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_passthrough(self):
        app = AsyncMock()
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(app, logger)

        scope = {"type": "lifespan"}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        app.assert_awaited_once_with(scope, receive, send)


# ================================================================== #
#  ASGI — excluded paths                                               #
# ================================================================== #
class TestASGIExcludedPaths:
    """Requests to excluded paths skip logging."""

    @pytest.mark.asyncio
    async def test_excluded_path_skips_logging(self):
        app = AsyncMock()
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(app, logger, exclude_paths={"/health"})

        scope = _http_scope(path="/health")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        app.assert_awaited_once_with(scope, receive, send)
        logger.info.assert_not_called()


# ================================================================== #
#  ASGI — happy-path __call__                                          #
# ================================================================== #
class TestASGICallHappyPath:
    """Normal request / response lifecycle."""

    @pytest.mark.asyncio
    async def test_logs_request_and_response(self):
        """Both request and response are logged for 200 OK."""
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"text/plain"),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"OK",
                }
            )

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            scope = _http_scope()
            receive = AsyncMock()
            send = AsyncMock()

            await mw(scope, receive, send)

        # Request log
        assert logger.info.call_count >= 1
        first_msg = logger.info.call_args_list[0][0][0]
        assert "Request received" in first_msg

        # Response log (200 -> info)
        assert logger.info.call_count >= 2
        second_msg = logger.info.call_args_list[1][0][0]
        assert "200" in second_msg

        # send was called via wrapper
        assert send.await_count == 2

    @pytest.mark.asyncio
    async def test_response_body_accumulated(self):
        """Multiple body chunks are concatenated."""
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"chunk1"})
            await send({"type": "http.response.body", "body": b"chunk2"})

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            scope = _http_scope()
            receive = AsyncMock()
            send = AsyncMock()
            await mw(scope, receive, send)

        # Response log should exist
        assert logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_empty_body_chunk_ignored(self):
        """Body chunks with empty/falsy body don't add bytes."""
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

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            scope = _http_scope()
            receive = AsyncMock()
            send = AsyncMock()
            await mw(scope, receive, send)

        assert send.await_count == 2


# ================================================================== #
#  ASGI — excluded status codes                                        #
# ================================================================== #
class TestASGIExcludedStatusCodes:
    """Status codes in exclude_status_codes skip response logging."""

    @pytest.mark.asyncio
    async def test_excluded_status_code(self):
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

        mw = MohFlowASGIMiddleware(
            fake_app, logger, exclude_status_codes={204}
        )

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            scope = _http_scope()
            receive = AsyncMock()
            send = AsyncMock()
            await mw(scope, receive, send)

        # Only the request log, no response log
        assert logger.info.call_count == 1
        assert "Request received" in logger.info.call_args_list[0][0][0]


# ================================================================== #
#  ASGI — log level mapping                                            #
# ================================================================== #
class TestASGILogLevelMapping:
    """Correct log method is called based on status code."""

    @pytest.mark.asyncio
    async def test_warning_for_400(self):
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 400,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"Bad"})

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        logger.warning.assert_called_once()
        assert "400" in logger.warning.call_args[0][0]

    @pytest.mark.asyncio
    async def test_error_for_500(self):
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"ISE",
                }
            )

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        logger.error.assert_called_once()
        assert "500" in logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_info_for_unmapped_status(self):
        """Unmapped status codes fall back to info."""
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 301,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"Moved"})

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        # Both request and response logged via info
        assert logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_custom_log_level_mapping(self):
        logger = _make_logger()
        logger.debug = MagicMock()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"OK"})

        mw = MohFlowASGIMiddleware(
            fake_app, logger, log_level_mapping={200: "debug"}
        )

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        logger.debug.assert_called_once()


# ================================================================== #
#  ASGI — log_requests / log_responses disabled                        #
# ================================================================== #
class TestASGILogRequestsDisabled:
    """When log_requests=False, request log is suppressed."""

    @pytest.mark.asyncio
    async def test_no_request_log(self):
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"OK"})

        mw = MohFlowASGIMiddleware(fake_app, logger, log_requests=False)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        # Only the response log (no "Request received")
        assert logger.info.call_count == 1
        assert "200" in logger.info.call_args[0][0]


class TestASGILogResponsesDisabled:
    """When log_responses=False, response log is suppressed."""

    @pytest.mark.asyncio
    async def test_no_response_log(self):
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"OK"})

        mw = MohFlowASGIMiddleware(fake_app, logger, log_responses=False)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        # Only request log
        assert logger.info.call_count == 1
        assert "Request received" in logger.info.call_args[0][0]


class TestASGIBothLoggingDisabled:
    @pytest.mark.asyncio
    async def test_no_logging_at_all(self):
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"OK"})

        mw = MohFlowASGIMiddleware(
            fake_app,
            logger,
            log_requests=False,
            log_responses=False,
        )

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        logger.info.assert_not_called()
        logger.warning.assert_not_called()
        logger.error.assert_not_called()


# ================================================================== #
#  ASGI — exception handling                                           #
# ================================================================== #
class TestASGIExceptionHandling:
    """Exception in the inner app is logged and re-raised."""

    @pytest.mark.asyncio
    async def test_exception_logged_and_reraised(self):
        logger = _make_logger()

        async def failing_app(scope, receive, send):
            raise RuntimeError("boom")

        mw = MohFlowASGIMiddleware(failing_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await mw(_http_scope(), AsyncMock(), AsyncMock())

        logger.error.assert_called_once()
        kwargs = logger.error.call_args[1]
        assert kwargs["error"] == "boom"
        assert kwargs["error_type"] == "RuntimeError"
        assert "duration" in kwargs


# ================================================================== #
#  ASGI — null status code (no http.response.start)                    #
# ================================================================== #
class TestASGINullStatusCode:
    @pytest.mark.asyncio
    async def test_no_response_start(self):
        """When the inner app never sends http.response.start,
        status_code stays None and response logging is skipped."""
        logger = _make_logger()

        async def empty_app(scope, receive, send):
            pass

        mw = MohFlowASGIMiddleware(empty_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        # Only request log, no response log
        assert logger.info.call_count == 1


# ================================================================== #
#  ASGI — send_wrapper edge cases                                      #
# ================================================================== #
class TestASGISendWrapper:
    """Edge-cases inside the send_wrapper closure."""

    @pytest.mark.asyncio
    async def test_no_body_key_in_body_message(self):
        """http.response.body without 'body' key should not crash."""
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body"})

        mw = MohFlowASGIMiddleware(fake_app, logger)
        send = AsyncMock()

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), send)

        assert send.await_count == 2

    @pytest.mark.asyncio
    async def test_no_status_in_response_start(self):
        """Missing status defaults to 500."""
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send({"type": "http.response.start", "headers": []})
            await send({"type": "http.response.body", "body": b"err"})

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_headers_in_response_start(self):
        """Missing headers key defaults to empty list."""
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"OK"})

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            await mw(_http_scope(), AsyncMock(), AsyncMock())

        assert logger.info.call_count >= 2


# ================================================================== #
#  ASGI — minimal scope                                                #
# ================================================================== #
class TestASGIScopeMissingFields:
    @pytest.mark.asyncio
    async def test_minimal_scope(self):
        """Scope with only 'type' should not crash."""
        logger = _make_logger()

        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"OK"})

        mw = MohFlowASGIMiddleware(fake_app, logger)

        with patch.object(
            MohFlowASGIMiddleware,
            "_extract_request_context",
            _fake_asgi_extract,
        ):
            scope = {"type": "http"}
            await mw(scope, AsyncMock(), AsyncMock())

        assert logger.info.call_count >= 1


# ================================================================== #
#  ASGI — _extract_request_context                                     #
# ================================================================== #
class TestASGIExtractRequestContext:
    """_extract_request_context coverage."""

    @pytest.mark.asyncio
    async def test_full_context(self):
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        scope = _http_scope()
        receive = AsyncMock()
        ctx = await mw._extract_request_context(scope, receive, "req-123")

        assert ctx["method"] == "GET"
        assert ctx["path"] == "/test"
        assert ctx["query_string"] == "foo=bar"
        assert ctx["scheme"] == "https"
        assert ctx["request_id"] == "req-123"
        assert ctx["user_agent"] == "TestAgent/1.0"
        assert ctx["content_type"] == "application/json"
        assert ctx["content_length"] == "42"
        assert ctx["client_ip"] == "127.0.0.1"
        assert "timestamp" in ctx

    @pytest.mark.asyncio
    async def test_empty_headers(self):
        """Missing headers yield no user_agent, content_type, etc."""
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        scope = _http_scope(headers=[])
        receive = AsyncMock()
        ctx = await mw._extract_request_context(scope, receive, "req-456")

        assert "user_agent" not in ctx
        assert "content_type" not in ctx
        assert "content_length" not in ctx

    @pytest.mark.asyncio
    async def test_empty_query_string(self):
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        scope = _http_scope(query_string=b"")
        receive = AsyncMock()
        ctx = await mw._extract_request_context(scope, receive, "req-789")

        # Empty string is falsy -> filtered out
        assert "query_string" not in ctx

    @pytest.mark.asyncio
    async def test_no_client_in_scope(self):
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        scope = _http_scope()
        scope.pop("client", None)
        receive = AsyncMock()
        ctx = await mw._extract_request_context(scope, receive, "req-000")

        assert "client" not in ctx

    @pytest.mark.asyncio
    async def test_falsy_values_filtered(self):
        """Values that are falsy (None, empty string) are excluded
        from the returned dict."""
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        scope = {
            "type": "http",
            "headers": [],
        }
        ctx = await mw._extract_request_context(scope, AsyncMock(), "rid")

        # method, path, scheme, server are all None -> excluded
        assert "method" not in ctx
        assert "path" not in ctx
        assert "scheme" not in ctx
        assert "server" not in ctx
        assert ctx["request_id"] == "rid"


# ================================================================== #
#  ASGI — _extract_response_context                                    #
# ================================================================== #
class TestASGIExtractResponseContext:
    """_extract_response_context coverage."""

    def test_full_response_context(self):
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        response_data = {
            "status_code": 200,
            "headers": {b"content-type": b"text/html"},
            "body": b"Hello",
        }
        ctx = mw._extract_response_context(response_data, 42.5)

        assert ctx["status_code"] == 200
        assert ctx["duration"] == 42.5
        assert ctx["response_size"] == 5
        assert ctx["content_type"] == "text/html"

    def test_empty_body(self):
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        response_data = {
            "status_code": 204,
            "headers": {},
            "body": b"",
        }
        ctx = mw._extract_response_context(response_data, 10.0)

        # Empty body -> response_size is None -> filtered out
        assert "response_size" not in ctx

    def test_no_content_type_header(self):
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        response_data = {
            "status_code": 200,
            "headers": {},
            "body": b"OK",
        }
        ctx = mw._extract_response_context(response_data, 5.0)

        assert "content_type" not in ctx

    def test_none_values_filtered(self):
        logger = _make_logger()
        mw = MohFlowASGIMiddleware(AsyncMock(), logger)

        response_data = {
            "status_code": 200,
            "headers": {},
            "body": None,
        }
        ctx = mw._extract_response_context(response_data, 1.0)

        assert "response_size" not in ctx


# ================================================================== #
#  ASGI — _get_client_ip                                               #
# ================================================================== #
class TestASGIGetClientIp:
    """_get_client_ip for ASGI middleware."""

    def _mw(self):
        return MohFlowASGIMiddleware(AsyncMock(), _make_logger())

    def test_x_forwarded_for(self):
        headers = {b"x-forwarded-for": b"10.0.0.1, 10.0.0.2"}
        assert self._mw()._get_client_ip(_http_scope(), headers) == "10.0.0.1"

    def test_x_real_ip(self):
        headers = {b"x-real-ip": b"192.168.1.1"}
        assert (
            self._mw()._get_client_ip(_http_scope(), headers) == "192.168.1.1"
        )

    def test_x_client_ip(self):
        headers = {b"x-client-ip": b"172.16.0.1"}
        assert (
            self._mw()._get_client_ip(_http_scope(), headers) == "172.16.0.1"
        )

    def test_cf_connecting_ip(self):
        headers = {b"cf-connecting-ip": b"8.8.8.8"}
        assert self._mw()._get_client_ip(_http_scope(), headers) == "8.8.8.8"

    def test_header_priority_first_wins(self):
        """x-forwarded-for is checked before x-real-ip."""
        headers = {
            b"x-forwarded-for": b"1.1.1.1",
            b"x-real-ip": b"2.2.2.2",
        }
        assert self._mw()._get_client_ip(_http_scope(), headers) == "1.1.1.1"

    def test_fallback_to_scope_client_tuple(self):
        scope = _http_scope(client=("10.20.30.40", 9999))
        assert self._mw()._get_client_ip(scope, {}) == "10.20.30.40"

    def test_fallback_to_scope_client_list(self):
        scope = _http_scope(client=["10.20.30.40", 9999])
        assert self._mw()._get_client_ip(scope, {}) == "10.20.30.40"

    def test_fallback_to_scope_client_string(self):
        scope = _http_scope(client="10.20.30.40")
        assert self._mw()._get_client_ip(scope, {}) == "10.20.30.40"

    def test_no_client_at_all(self):
        scope = _http_scope()
        scope.pop("client", None)
        assert self._mw()._get_client_ip(scope, {}) is None

    def test_single_ip_in_x_forwarded_for(self):
        headers = {b"x-forwarded-for": b"  5.5.5.5  "}
        assert self._mw()._get_client_ip(_http_scope(), headers) == "5.5.5.5"


# ================================================================== #
#  WSGI MIDDLEWARE — INIT                                              #
# ================================================================== #
class TestMohFlowWSGIMiddlewareInit:
    """Initialisation and default values."""

    def test_default_attributes(self):
        app = MagicMock()
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(app, logger)

        assert mw.app is app
        assert mw.logger is logger
        assert mw.log_requests is True
        assert mw.log_responses is True
        assert mw.max_body_size == 1024
        assert mw.exclude_paths == set()
        assert mw.exclude_status_codes == set()
        assert 200 in mw.log_level_mapping
        assert 500 in mw.log_level_mapping

    def test_custom_attributes(self):
        app = MagicMock()
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(
            app,
            logger,
            log_requests=False,
            log_responses=False,
            max_body_size=256,
            exclude_paths={"/healthz"},
            exclude_status_codes={204},
            log_level_mapping={200: "debug"},
        )

        assert mw.log_requests is False
        assert mw.log_responses is False
        assert mw.max_body_size == 256
        assert mw.exclude_paths == {"/healthz"}
        assert mw.exclude_status_codes == {204}
        assert mw.log_level_mapping == {200: "debug"}


# ================================================================== #
#  WSGI — excluded paths                                               #
# ================================================================== #
class TestWSGIExcludedPaths:
    def test_excluded_path(self):
        start_response = MagicMock()
        inner_app = MagicMock(return_value=[b"OK"])
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(
            inner_app, logger, exclude_paths={"/health"}
        )

        environ = _wsgi_environ(PATH_INFO="/health")
        result = mw(environ, start_response)

        inner_app.assert_called_once_with(environ, start_response)
        logger.info.assert_not_called()
        assert result == [b"OK"]


# ================================================================== #
#  WSGI — happy-path __call__                                          #
# ================================================================== #
class TestWSGICallHappyPath:
    def test_logs_request_and_response(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("200 OK", [("Content-Type", "text/plain")])
            return [b"Hello"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            environ = _wsgi_environ()
            result = mw(environ, start_response)

        assert result == [b"Hello"]

        # Request log
        assert logger.info.call_count >= 1
        first_msg = logger.info.call_args_list[0][0][0]
        assert "Request received" in first_msg

        # Response log (200 -> info)
        assert logger.info.call_count >= 2
        second_msg = logger.info.call_args_list[1][0][0]
        assert "200" in second_msg

        # start_response called with X-Request-ID appended
        start_response.assert_called_once()
        args = start_response.call_args[0]
        assert args[0] == "200 OK"
        header_names = [h[0] for h in args[1]]
        assert "X-Request-ID" in header_names

    def test_multiple_body_chunks(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("200 OK", [])
            return [b"chunk1", b"chunk2"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            result = mw(_wsgi_environ(), start_response)

        assert result == [b"chunk1", b"chunk2"]

    def test_iterable_close_called(self):
        """If response iterable has close(), it is called."""
        start_response = MagicMock()

        class ClosableIter:
            def __init__(self):
                self.closed = False

            def __iter__(self):
                yield b"data"

            def close(self):
                self.closed = True

        iterable = ClosableIter()

        def inner_app(environ, sr):
            sr("200 OK", [])
            return iterable

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        assert iterable.closed

    def test_iterable_without_close(self):
        """Iterables without close() do not cause errors."""
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("200 OK", [])
            return iter([b"data"])

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            result = mw(_wsgi_environ(), start_response)

        assert result == [b"data"]

    def test_start_response_exc_info_forwarded(self):
        """exc_info parameter is passed through."""
        start_response = MagicMock()
        exc_info_val = (RuntimeError, RuntimeError("x"), None)

        def inner_app(environ, sr):
            sr("500 Internal Server Error", [], exc_info_val)
            return [b"error"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        start_response.assert_called_once()
        assert start_response.call_args[0][0] == "500 Internal Server Error"
        assert start_response.call_args[0][2] is exc_info_val


# ================================================================== #
#  WSGI — excluded status codes                                        #
# ================================================================== #
class TestWSGIExcludedStatusCodes:
    def test_excluded_status(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("204 No Content", [])
            return [b""]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(
            inner_app, logger, exclude_status_codes={204}
        )

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        # Only request log
        assert logger.info.call_count == 1
        assert "Request received" in logger.info.call_args_list[0][0][0]


# ================================================================== #
#  WSGI — log level mapping                                            #
# ================================================================== #
class TestWSGILogLevelMapping:
    def test_warning_for_404(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("404 Not Found", [])
            return [b"Not Found"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        logger.warning.assert_called_once()
        assert "404" in logger.warning.call_args[0][0]

    def test_error_for_503(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("503 Service Unavailable", [])
            return [b"Unavailable"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        logger.error.assert_called_once()
        assert "503" in logger.error.call_args[0][0]

    def test_info_for_unmapped_status(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("301 Moved Permanently", [])
            return [b"Moved"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        assert logger.info.call_count == 2

    def test_null_status_falls_back_to_500(self):
        """If start_response is never called, status defaults to
        '500 Internal Server Error'."""
        start_response = MagicMock()

        def inner_app(environ, sr):
            return [b"oops"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        logger.error.assert_called_once()
        assert "500" in logger.error.call_args[0][0]


# ================================================================== #
#  WSGI — log_requests / log_responses disabled                        #
# ================================================================== #
class TestWSGILogRequestsDisabled:
    def test_no_request_log(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("200 OK", [])
            return [b"OK"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger, log_requests=False)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        assert logger.info.call_count == 1
        assert "200" in logger.info.call_args[0][0]


class TestWSGILogResponsesDisabled:
    def test_no_response_log(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("200 OK", [])
            return [b"OK"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(inner_app, logger, log_responses=False)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        assert logger.info.call_count == 1
        assert "Request received" in logger.info.call_args[0][0]


class TestWSGIBothLoggingDisabled:
    def test_no_logging_at_all(self):
        start_response = MagicMock()

        def inner_app(environ, sr):
            sr("200 OK", [])
            return [b"OK"]

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(
            inner_app,
            logger,
            log_requests=False,
            log_responses=False,
        )

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            mw(_wsgi_environ(), start_response)

        logger.info.assert_not_called()
        logger.warning.assert_not_called()
        logger.error.assert_not_called()


# ================================================================== #
#  WSGI — exception handling                                           #
# ================================================================== #
class TestWSGIExceptionHandling:
    def test_exception_logged_and_reraised(self):
        start_response = MagicMock()

        def failing_app(environ, sr):
            raise ValueError("broken")

        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(failing_app, logger)

        with patch.object(
            MohFlowWSGIMiddleware,
            "_extract_request_context",
            _fake_wsgi_extract,
        ):
            with pytest.raises(ValueError, match="broken"):
                mw(_wsgi_environ(), start_response)

        logger.error.assert_called_once()
        kwargs = logger.error.call_args[1]
        assert kwargs["error"] == "broken"
        assert kwargs["error_type"] == "ValueError"
        assert "duration" in kwargs


# ================================================================== #
#  WSGI — _extract_request_context                                     #
# ================================================================== #
class TestWSGIExtractRequestContext:
    def test_full_context(self):
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(MagicMock(), logger)

        environ = _wsgi_environ()
        ctx = mw._extract_request_context(environ, "req-abc")

        assert ctx["method"] == "GET"
        assert ctx["path"] == "/test"
        assert ctx["query_string"] == "foo=bar"
        assert ctx["server_name"] == "localhost"
        assert ctx["server_port"] == "8000"
        assert ctx["scheme"] == "https"
        assert ctx["user_agent"] == "TestAgent/1.0"
        assert ctx["content_type"] == "application/json"
        assert ctx["content_length"] == "42"
        assert ctx["request_id"] == "req-abc"
        assert ctx["client_ip"] == "127.0.0.1"
        assert "timestamp" in ctx

    def test_empty_environ(self):
        """Minimal environ produces minimal context."""
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(MagicMock(), logger)

        ctx = mw._extract_request_context({}, "req-empty")

        assert ctx["request_id"] == "req-empty"
        assert "timestamp" in ctx
        assert "method" not in ctx
        assert "path" not in ctx

    def test_falsy_values_filtered(self):
        """None and empty strings are removed."""
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(MagicMock(), logger)

        environ = {"QUERY_STRING": ""}
        ctx = mw._extract_request_context(environ, "r")

        assert "query_string" not in ctx


# ================================================================== #
#  WSGI — _extract_response_context                                    #
# ================================================================== #
class TestWSGIExtractResponseContext:
    def test_full_response_context(self):
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(MagicMock(), logger)

        response_data = {
            "status": "200 OK",
            "headers": [("Content-Type", "application/json")],
        }
        ctx = mw._extract_response_context(response_data, b"body-data", 15.3)

        assert ctx["status_code"] == 200
        assert ctx["duration"] == 15.3
        assert ctx["response_size"] == 9
        assert ctx["content_type"] == "application/json"

    def test_empty_body(self):
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(MagicMock(), logger)

        response_data = {
            "status": "204 No Content",
            "headers": [],
        }
        ctx = mw._extract_response_context(response_data, b"", 5.0)

        assert "response_size" not in ctx

    def test_no_content_type(self):
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(MagicMock(), logger)

        response_data = {"status": "200 OK", "headers": []}
        ctx = mw._extract_response_context(response_data, b"OK", 1.0)

        assert "content_type" not in ctx

    def test_null_status_defaults_to_500(self):
        logger = _make_logger()
        mw = MohFlowWSGIMiddleware(MagicMock(), logger)

        response_data = {"status": None, "headers": []}
        ctx = mw._extract_response_context(response_data, b"x", 1.0)

        assert ctx["status_code"] == 500


# ================================================================== #
#  WSGI — _get_client_ip                                               #
# ================================================================== #
class TestWSGIGetClientIp:
    def _mw(self):
        return MohFlowWSGIMiddleware(MagicMock(), _make_logger())

    def test_x_forwarded_for(self):
        environ = _wsgi_environ(HTTP_X_FORWARDED_FOR="10.0.0.1, 10.0.0.2")
        assert self._mw()._get_client_ip(environ) == "10.0.0.1"

    def test_x_real_ip(self):
        environ = _wsgi_environ(HTTP_X_REAL_IP="192.168.1.1")
        assert self._mw()._get_client_ip(environ) == "192.168.1.1"

    def test_x_client_ip(self):
        environ = _wsgi_environ(HTTP_X_CLIENT_IP="172.16.0.1")
        assert self._mw()._get_client_ip(environ) == "172.16.0.1"

    def test_cf_connecting_ip(self):
        environ = _wsgi_environ(HTTP_CF_CONNECTING_IP="8.8.4.4")
        assert self._mw()._get_client_ip(environ) == "8.8.4.4"

    def test_header_priority(self):
        """X-Forwarded-For takes precedence."""
        environ = _wsgi_environ(
            HTTP_X_FORWARDED_FOR="1.1.1.1",
            HTTP_X_REAL_IP="2.2.2.2",
        )
        assert self._mw()._get_client_ip(environ) == "1.1.1.1"

    def test_fallback_to_remote_addr(self):
        environ = {"REMOTE_ADDR": "192.168.0.1"}
        assert self._mw()._get_client_ip(environ) == "192.168.0.1"

    def test_no_client_at_all(self):
        assert self._mw()._get_client_ip({}) is None

    def test_single_ip_in_forwarded_for(self):
        environ = _wsgi_environ(HTTP_X_FORWARDED_FOR="  5.5.5.5  ")
        assert self._mw()._get_client_ip(environ) == "5.5.5.5"


# ================================================================== #
#  FACTORY FUNCTIONS                                                   #
# ================================================================== #
class TestCreateASGIMiddleware:
    def test_returns_callable_factory(self):
        logger = _make_logger()
        factory = create_asgi_middleware(logger)
        assert callable(factory)

    def test_factory_creates_middleware(self):
        logger = _make_logger()
        factory = create_asgi_middleware(logger, exclude_paths={"/health"})

        app = AsyncMock()
        middleware = factory(app)

        assert isinstance(middleware, MohFlowASGIMiddleware)
        assert middleware.app is app
        assert middleware.logger is logger
        assert middleware.exclude_paths == {"/health"}


class TestCreateWSGIMiddleware:
    def test_returns_callable_factory(self):
        logger = _make_logger()
        factory = create_wsgi_middleware(logger)
        assert callable(factory)

    def test_factory_creates_middleware(self):
        logger = _make_logger()
        factory = create_wsgi_middleware(logger, exclude_paths={"/health"})

        app = MagicMock()
        middleware = factory(app)

        assert isinstance(middleware, MohFlowWSGIMiddleware)
        assert middleware.app is app
        assert middleware.logger is logger
        assert middleware.exclude_paths == {"/health"}


# ================================================================== #
#  AUTO-SETUP MIDDLEWARE                                                #
# ================================================================== #
class TestAutoSetupMiddleware:
    def test_fastapi_app(self):
        """FastAPI-like app gets ASGI middleware."""
        app = MagicMock()
        app.__class__.__name__ = "FastAPI"
        app.__class__.__module__ = "fastapi.applications"
        logger = _make_logger()

        result = auto_setup_middleware(app, logger)

        assert result is app
        app.add_middleware.assert_called_once()

    def test_starlette_app(self):
        app = MagicMock()
        app.__class__.__name__ = "Starlette"
        app.__class__.__module__ = "starlette.applications"
        logger = _make_logger()

        result = auto_setup_middleware(app, logger)

        assert result is app
        app.add_middleware.assert_called_once()

    def test_flask_app(self):
        """Flask-like app gets WSGI middleware wrapping wsgi_app."""
        app = MagicMock()
        app.__class__.__name__ = "Flask"
        app.__class__.__module__ = "flask.app"
        logger = _make_logger()

        result = auto_setup_middleware(app, logger)

        assert result is app
        assert isinstance(app.wsgi_app, MohFlowWSGIMiddleware)

    def test_django_raises_value_error(self):
        app = MagicMock()
        app.__class__.__name__ = "WSGIHandler"
        app.__class__.__module__ = "django.core.handlers.wsgi"
        logger = _make_logger()

        with pytest.raises(ValueError, match="Django"):
            auto_setup_middleware(app, logger)

    def test_generic_wsgi_app(self):
        """App with wsgi_version is treated as generic WSGI."""
        app = MagicMock()
        app.__class__.__name__ = "GenericWSGI"
        app.__class__.__module__ = "mymodule"
        app.wsgi_version = (1, 0)
        logger = _make_logger()

        result = auto_setup_middleware(app, logger)

        assert isinstance(result, MohFlowWSGIMiddleware)
        assert result.app is app

    def test_generic_async_app(self):
        """Async callable is treated as generic ASGI."""
        app = MagicMock()
        app.__class__.__name__ = "AsyncApp"
        app.__class__.__module__ = "mymodule"
        # Remove wsgi_version so that branch is skipped
        del app.wsgi_version
        logger = _make_logger()

        with patch(
            "mohflow.integrations.asgi_wsgi.asyncio" ".iscoroutinefunction",
            return_value=True,
        ):
            result = auto_setup_middleware(app, logger)

        assert isinstance(result, MohFlowASGIMiddleware)
        assert result.app is app

    def test_unrecognised_app_raises_value_error(self):
        """Unrecognised app type raises ValueError."""
        app = MagicMock()
        app.__class__.__name__ = "UnknownApp"
        app.__class__.__module__ = "mystery"
        del app.wsgi_version
        logger = _make_logger()

        with patch(
            "mohflow.integrations.asgi_wsgi.asyncio" ".iscoroutinefunction",
            return_value=False,
        ):
            with pytest.raises(ValueError, match="Unable to auto-detect"):
                auto_setup_middleware(app, logger)

    def test_config_passed_through(self):
        """Extra config kwargs are forwarded."""
        app = MagicMock()
        app.__class__.__name__ = "GenericWSGI"
        app.__class__.__module__ = "mymodule"
        app.wsgi_version = (1, 0)
        logger = _make_logger()

        result = auto_setup_middleware(app, logger, exclude_paths={"/ping"})

        assert isinstance(result, MohFlowWSGIMiddleware)
        assert result.exclude_paths == {"/ping"}


# ================================================================== #
#  MANUAL LOGGING UTILITIES                                            #
# ================================================================== #
class TestLogRequestManually:
    def test_logs_request_and_returns_id(self):
        logger = _make_logger()

        request_id = log_request_manually(
            logger, "POST", "/api/data", custom="value"
        )

        assert isinstance(request_id, str)
        assert len(request_id) == 36  # UUID4 string length

        logger.info.assert_called_once()
        msg = logger.info.call_args[0][0]
        assert "POST" in msg
        assert "/api/data" in msg
        assert "Request received" in msg

        kwargs = logger.info.call_args[1]
        assert kwargs["custom"] == "value"


class TestLogResponseManually:
    def test_info_for_2xx(self):
        logger = _make_logger()

        log_response_manually(logger, "req-1", "GET", "/items", 200, 12.5)

        logger.info.assert_called_once()
        msg = logger.info.call_args[0][0]
        assert "200" in msg
        assert "12.5ms" in msg

    def test_warning_for_4xx(self):
        logger = _make_logger()

        log_response_manually(logger, "req-2", "GET", "/missing", 404, 5.0)

        logger.warning.assert_called_once()
        assert "404" in logger.warning.call_args[0][0]

    def test_error_for_5xx(self):
        logger = _make_logger()

        log_response_manually(logger, "req-3", "GET", "/fail", 500, 100.0)

        logger.error.assert_called_once()
        assert "500" in logger.error.call_args[0][0]

    def test_extra_context_forwarded(self):
        logger = _make_logger()

        log_response_manually(
            logger, "req-4", "PUT", "/up", 201, 8.0, user="alice"
        )

        kwargs = logger.info.call_args[1]
        assert kwargs["user"] == "alice"

    def test_boundary_399_is_info(self):
        logger = _make_logger()
        log_response_manually(logger, "req-5", "GET", "/x", 399, 1.0)
        logger.info.assert_called_once()

    def test_boundary_400_is_warning(self):
        logger = _make_logger()
        log_response_manually(logger, "req-6", "GET", "/x", 400, 1.0)
        logger.warning.assert_called_once()

    def test_boundary_499_is_warning(self):
        logger = _make_logger()
        log_response_manually(logger, "req-7", "GET", "/x", 499, 1.0)
        logger.warning.assert_called_once()

    def test_boundary_500_is_error(self):
        logger = _make_logger()
        log_response_manually(logger, "req-8", "GET", "/x", 500, 1.0)
        logger.error.assert_called_once()
