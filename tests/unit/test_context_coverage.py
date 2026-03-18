"""
Comprehensive tests for mohflow.context.correlation and
mohflow.context.scoped_context modules.

Targets near-100% line coverage on both files.
"""

import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest

from mohflow.context.correlation import (
    CorrelationContext,
    CorrelationIDManager,
    ThreadLocalCorrelationManager,
    clear_correlation_id,
    default_manager,
    django_correlation_middleware,
    ensure_correlation_id,
    fastapi_correlation_dependency,
    flask_correlation_middleware,
    generate_correlation_id,
    get_correlation_id,
    set_correlation_id,
    thread_local_manager,
    with_correlation_id,
)
from mohflow.context.scoped_context import (
    ContextScope,
    ContextualLogger,
    ContextualLoggerProxy,
    ScopedContextManager,
    _global_context_manager,
    _request_context,
    _temporary_context,
    _thread_context,
    clear_global_context,
    get_global_context,
    request_context,
    set_global_context,
    temporary_context,
    thread_context,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_all_context():
    """Reset every piece of context state between tests."""
    # Pre-test cleanup
    clear_correlation_id()
    _request_context.set({})
    _thread_context.set({})
    _temporary_context.set({})
    _global_context_manager.clear_all_context()

    yield

    # Post-test cleanup
    clear_correlation_id()
    _request_context.set({})
    _thread_context.set({})
    _temporary_context.set({})
    _global_context_manager.clear_all_context()


# ================================================================
# correlation.py tests
# ================================================================


class TestGenerateCorrelationId:
    """Tests for generate_correlation_id()."""

    def test_returns_string(self):
        cid = generate_correlation_id()
        assert isinstance(cid, str)

    def test_returns_valid_uuid4(self):
        cid = generate_correlation_id()
        parsed = uuid.UUID(cid, version=4)
        assert str(parsed) == cid

    def test_unique_on_repeated_calls(self):
        ids = {generate_correlation_id() for _ in range(50)}
        assert len(ids) == 50


class TestSetGetClearCorrelationId:
    """Tests for set / get / clear module-level helpers."""

    def test_get_returns_none_by_default(self):
        assert get_correlation_id() is None

    def test_set_then_get(self):
        set_correlation_id("abc-123")
        assert get_correlation_id() == "abc-123"

    def test_clear(self):
        set_correlation_id("abc-123")
        clear_correlation_id()
        assert get_correlation_id() is None


class TestEnsureCorrelationId:
    """Tests for ensure_correlation_id()."""

    def test_creates_when_none(self):
        cid = ensure_correlation_id()
        assert cid is not None
        assert get_correlation_id() == cid

    def test_returns_existing(self):
        set_correlation_id("existing-id")
        cid = ensure_correlation_id()
        assert cid == "existing-id"


# ── CorrelationIDManager ─────────────────────────────────────────


class TestCorrelationIDManager:
    """Tests for CorrelationIDManager class."""

    def test_init_defaults(self):
        mgr = CorrelationIDManager()
        assert mgr.auto_generate is True

    def test_init_no_auto(self):
        mgr = CorrelationIDManager(auto_generate=False)
        assert mgr.auto_generate is False

    def test_generate_id(self):
        mgr = CorrelationIDManager()
        cid = mgr.generate_id()
        uuid.UUID(cid, version=4)  # validates format

    def test_set_and_get_id(self):
        mgr = CorrelationIDManager()
        mgr.set_id("mgr-id-1")
        assert mgr.get_id() == "mgr-id-1"

    def test_clear_id(self):
        mgr = CorrelationIDManager()
        mgr.set_id("mgr-id-1")
        mgr.clear_id()
        assert mgr.get_id() is None

    def test_get_or_create_auto(self):
        mgr = CorrelationIDManager(auto_generate=True)
        cid = mgr.get_or_create_correlation_id()
        assert cid != ""
        assert get_correlation_id() == cid

    def test_get_or_create_returns_existing(self):
        set_correlation_id("pre-existing")
        mgr = CorrelationIDManager()
        assert mgr.get_or_create_correlation_id() == "pre-existing"

    def test_get_or_create_no_auto_returns_empty(self):
        mgr = CorrelationIDManager(auto_generate=False)
        cid = mgr.get_or_create_correlation_id()
        assert cid == ""

    # propagate_correlation_id

    def test_propagate_adds_headers(self):
        set_correlation_id("prop-id")
        mgr = CorrelationIDManager()
        headers = mgr.propagate_correlation_id({"Accept": "text/html"})
        assert headers["X-Correlation-ID"] == "prop-id"
        assert headers["X-Request-ID"] == "prop-id"
        assert headers["Accept"] == "text/html"

    def test_propagate_does_not_mutate_original(self):
        set_correlation_id("prop-id")
        mgr = CorrelationIDManager()
        original = {"Accept": "text/html"}
        mgr.propagate_correlation_id(original)
        assert "X-Correlation-ID" not in original

    def test_propagate_auto_generates(self):
        mgr = CorrelationIDManager(auto_generate=True)
        headers = mgr.propagate_correlation_id({})
        assert "X-Correlation-ID" in headers

    def test_propagate_no_id_no_auto(self):
        mgr = CorrelationIDManager(auto_generate=False)
        headers = mgr.propagate_correlation_id({"Foo": "bar"})
        # Empty string means no id added
        assert "X-Correlation-ID" not in headers

    # extract_correlation_id

    def test_extract_x_correlation_id(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"X-Correlation-ID": "c1"}) == "c1"

    def test_extract_x_request_id(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"X-Request-ID": "r1"}) == "r1"

    def test_extract_correlation_id_header(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"Correlation-ID": "c2"}) == "c2"

    def test_extract_request_id_header(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"Request-ID": "r2"}) == "r2"

    def test_extract_x_trace_id(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"X-Trace-ID": "t1"}) == "t1"

    def test_extract_trace_id(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"Trace-ID": "t2"}) == "t2"

    def test_extract_case_insensitive(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"x-correlation-id": "ci"}) == "ci"

    def test_extract_returns_none_when_absent(self):
        mgr = CorrelationIDManager()
        assert mgr.extract_correlation_id({"Foo": "bar"}) is None

    def test_extract_skips_none_keys(self):
        """Headers dict with None key should not crash."""
        mgr = CorrelationIDManager()
        headers = {None: "bad", "X-Correlation-ID": "ok"}
        assert mgr.extract_correlation_id(headers) == "ok"

    def test_extract_priority_order(self):
        """X-Correlation-ID should win over X-Request-ID."""
        mgr = CorrelationIDManager()
        headers = {
            "X-Correlation-ID": "first",
            "X-Request-ID": "second",
        }
        assert mgr.extract_correlation_id(headers) == "first"

    # get_context_info

    def test_get_context_info_with_id(self):
        set_correlation_id("ctx-id")
        mgr = CorrelationIDManager()
        info = mgr.get_context_info()
        assert info["correlation_id"] == "ctx-id"
        assert info["request_id"] == "ctx-id"

    def test_get_context_info_without_id(self):
        mgr = CorrelationIDManager()
        assert mgr.get_context_info() == {}


# ── CorrelationContext (context manager) ─────────────────────────


class TestCorrelationContext:
    """Tests for CorrelationContext context manager."""

    def test_enter_with_explicit_id(self):
        with CorrelationContext(correlation_id="explicit-1") as cid:
            assert cid == "explicit-1"
            assert get_correlation_id() == "explicit-1"

    def test_exit_restores_previous(self):
        set_correlation_id("outer")
        with CorrelationContext(correlation_id="inner"):
            assert get_correlation_id() == "inner"
        assert get_correlation_id() == "outer"

    def test_exit_clears_when_no_previous(self):
        with CorrelationContext(correlation_id="temp"):
            pass
        assert get_correlation_id() is None

    def test_auto_generate(self):
        with CorrelationContext(auto_generate=True) as cid:
            assert cid is not None
            assert len(cid) > 0
            uuid.UUID(cid, version=4)

    def test_no_id_no_auto_returns_empty(self):
        with CorrelationContext(
            correlation_id=None, auto_generate=False
        ) as cid:
            assert cid == ""

    def test_no_id_no_auto_with_previous(self):
        set_correlation_id("prev")
        with CorrelationContext(
            correlation_id=None, auto_generate=False
        ) as cid:
            assert cid == "prev"

    def test_nested_contexts(self):
        with CorrelationContext(correlation_id="outer") as outer_id:
            assert outer_id == "outer"
            with CorrelationContext(correlation_id="inner") as inner_id:
                assert inner_id == "inner"
                assert get_correlation_id() == "inner"
            assert get_correlation_id() == "outer"
        assert get_correlation_id() is None


# ── with_correlation_id decorator ────────────────────────────────


class TestWithCorrelationIdDecorator:
    """Tests for with_correlation_id decorator."""

    def test_explicit_id(self):
        @with_correlation_id(correlation_id="dec-id")
        def fn():
            return get_correlation_id()

        assert fn() == "dec-id"

    def test_auto_generate(self):
        @with_correlation_id()
        def fn():
            return get_correlation_id()

        cid = fn()
        assert cid is not None
        uuid.UUID(cid, version=4)

    def test_restores_after(self):
        set_correlation_id("before")

        @with_correlation_id(correlation_id="during")
        def fn():
            return get_correlation_id()

        fn()
        assert get_correlation_id() == "before"

    def test_passes_args_and_kwargs(self):
        @with_correlation_id(correlation_id="d-id")
        def fn(a, b, kw=None):
            return (a, b, kw, get_correlation_id())

        assert fn(1, 2, kw="three") == (1, 2, "three", "d-id")


# ── ThreadLocalCorrelationManager ────────────────────────────────


class TestThreadLocalCorrelationManager:
    """Tests for ThreadLocalCorrelationManager."""

    def test_set_and_get(self):
        mgr = ThreadLocalCorrelationManager()
        mgr.set_correlation_id("tl-1")
        assert mgr.get_correlation_id() == "tl-1"

    def test_get_returns_none_by_default(self):
        mgr = ThreadLocalCorrelationManager()
        assert mgr.get_correlation_id() is None

    def test_clear(self):
        mgr = ThreadLocalCorrelationManager()
        mgr.set_correlation_id("tl-2")
        mgr.clear_correlation_id()
        assert mgr.get_correlation_id() is None

    def test_clear_when_not_set(self):
        mgr = ThreadLocalCorrelationManager()
        mgr.clear_correlation_id()  # should not raise
        assert mgr.get_correlation_id() is None

    def test_ensure_creates(self):
        mgr = ThreadLocalCorrelationManager()
        cid = mgr.ensure_correlation_id()
        assert cid is not None
        assert mgr.get_correlation_id() == cid

    def test_ensure_returns_existing(self):
        mgr = ThreadLocalCorrelationManager()
        mgr.set_correlation_id("existing")
        assert mgr.ensure_correlation_id() == "existing"

    def test_thread_isolation(self):
        mgr = ThreadLocalCorrelationManager()
        results = {}

        def worker(name, value):
            mgr.set_correlation_id(value)
            import time

            time.sleep(0.01)
            results[name] = mgr.get_correlation_id()

        t1 = threading.Thread(target=worker, args=("a", "val-a"))
        t2 = threading.Thread(target=worker, args=("b", "val-b"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["a"] == "val-a"
        assert results["b"] == "val-b"


# ── Singleton instances ──────────────────────────────────────────


class TestSingletonInstances:
    """Tests for default_manager and thread_local_manager."""

    def test_default_manager_is_correlation_id_manager(self):
        assert isinstance(default_manager, CorrelationIDManager)

    def test_thread_local_manager_is_thread_local(self):
        assert isinstance(thread_local_manager, ThreadLocalCorrelationManager)


# ── Flask middleware ─────────────────────────────────────────────


class TestFlaskCorrelationMiddleware:
    """Tests for flask_correlation_middleware()."""

    def test_extracts_from_headers(self):
        mock_request = MagicMock()
        mock_request.headers = {"X-Correlation-ID": "flask-id"}

        with patch.dict("sys.modules", {"flask": MagicMock()}):
            with patch(
                "mohflow.context.correlation.request",
                mock_request,
                create=True,
            ):
                # Re-import to get the patched version
                import mohflow.context.correlation as mod

                # Manually inline the logic since the import
                # inside the function is tricky to mock.
                # Instead, we test the branch by mocking flask
                flask_mod = MagicMock()
                flask_mod.request = mock_request
                with patch.dict("sys.modules", {"flask": flask_mod}):
                    mod.flask_correlation_middleware()
                    assert get_correlation_id() == "flask-id"

    def test_generates_when_absent(self):
        mock_request = MagicMock()
        mock_request.headers = {"Accept": "text/html"}

        flask_mod = MagicMock()
        flask_mod.request = mock_request
        with patch.dict("sys.modules", {"flask": flask_mod}):
            import mohflow.context.correlation as mod

            mod.flask_correlation_middleware()
            cid = get_correlation_id()
            assert cid is not None

    def test_import_error_is_handled(self):
        """When flask is not importable, no error is raised."""
        with patch.dict("sys.modules", {"flask": None}):
            # Calling should not raise
            flask_correlation_middleware()


# ── Django middleware ────────────────────────────────────────────


class TestDjangoCorrelationMiddleware:
    """Tests for django_correlation_middleware()."""

    def test_extracts_from_meta(self):
        mock_get_response = MagicMock()
        mock_response = MagicMock()
        mock_get_response.return_value = mock_response

        middleware = django_correlation_middleware(mock_get_response)

        mock_request = MagicMock()
        mock_request.META = {
            "HTTP_X_CORRELATION_ID": "django-id",
        }

        middleware(mock_request)

        assert get_correlation_id() == "django-id"
        mock_response.__setitem__.assert_called_with(
            "X-Correlation-ID", "django-id"
        )

    def test_generates_when_absent(self):
        mock_get_response = MagicMock()
        mock_response = MagicMock()
        mock_get_response.return_value = mock_response

        middleware = django_correlation_middleware(mock_get_response)

        mock_request = MagicMock()
        # Use a real dict wrapped so .items() works correctly
        meta = {}
        mock_request.META = MagicMock(wraps=meta)

        middleware(mock_request)
        cid = get_correlation_id()
        assert cid is not None

    def test_response_header_set(self):
        mock_get_response = MagicMock()
        mock_response = MagicMock()
        mock_get_response.return_value = mock_response

        middleware = django_correlation_middleware(mock_get_response)

        mock_request = MagicMock()
        mock_request.META = {
            "HTTP_X_REQUEST_ID": "resp-hdr-id",
        }

        middleware(mock_request)
        mock_response.__setitem__.assert_called_with(
            "X-Correlation-ID", "resp-hdr-id"
        )

    def test_calls_get_response(self):
        mock_get_response = MagicMock()
        mock_response = MagicMock()
        mock_get_response.return_value = mock_response

        middleware = django_correlation_middleware(mock_get_response)

        mock_request = MagicMock()
        meta = {}
        mock_request.META = MagicMock(wraps=meta)

        result = middleware(mock_request)
        mock_get_response.assert_called_once_with(mock_request)
        assert result is mock_response


# ── FastAPI dependency ───────────────────────────────────────────


class TestFastapiCorrelationDependency:
    """Tests for fastapi_correlation_dependency()."""

    def test_with_fastapi_available(self):
        mock_fastapi = MagicMock()
        mock_request_cls = MagicMock()
        mock_fastapi.Request = mock_request_cls

        with patch.dict("sys.modules", {"fastapi": mock_fastapi}):
            import mohflow.context.correlation as mod

            dep = mod.fastapi_correlation_dependency()
            # dep should be a callable (the inner function)
            assert callable(dep)

            # Simulate a request with correlation header
            mock_request = MagicMock()
            mock_request.headers = {"X-Correlation-ID": "fast-id"}

            result = dep(mock_request)
            assert result == "fast-id"
            assert get_correlation_id() == "fast-id"

    def test_with_fastapi_generates_when_absent(self):
        mock_fastapi = MagicMock()
        mock_request_cls = MagicMock()
        mock_fastapi.Request = mock_request_cls

        with patch.dict("sys.modules", {"fastapi": mock_fastapi}):
            import mohflow.context.correlation as mod

            dep = mod.fastapi_correlation_dependency()

            mock_request = MagicMock()
            mock_request.headers = {}

            result = dep(mock_request)
            assert result is not None
            assert len(result) > 0

    def test_without_fastapi(self):
        with patch.dict("sys.modules", {"fastapi": None}):
            import mohflow.context.correlation as mod

            dep = mod.fastapi_correlation_dependency()
            assert callable(dep)

            # The dummy dependency takes no arguments
            cid = dep()
            assert cid is not None
            assert len(cid) > 0


# ================================================================
# scoped_context.py tests
# ================================================================


class TestContextScope:
    """Tests for ContextScope dataclass."""

    def test_defaults(self):
        scope = ContextScope()
        assert len(scope.scope_id) == 8
        assert scope.scope_type == "unknown"
        assert scope.parent_scope_id is None
        assert scope.context_data == {}
        assert scope.created_at is not None

    def test_custom_values(self):
        scope = ContextScope(
            scope_id="custom",
            scope_type="request",
            parent_scope_id="parent1",
            context_data={"key": "val"},
        )
        assert scope.scope_id == "custom"
        assert scope.scope_type == "request"
        assert scope.parent_scope_id == "parent1"
        assert scope.context_data == {"key": "val"}


# ── ScopedContextManager ────────────────────────────────────────


class TestScopedContextManager:
    """Tests for ScopedContextManager."""

    def test_init(self):
        mgr = ScopedContextManager()
        assert mgr._global_context == {}
        assert mgr._context_stack == {}

    # Global context

    def test_set_global_context(self):
        mgr = ScopedContextManager()
        mgr.set_global_context(app="myapp", env="prod")
        assert mgr.get_global_context() == {
            "app": "myapp",
            "env": "prod",
        }

    def test_get_global_context_returns_copy(self):
        mgr = ScopedContextManager()
        mgr.set_global_context(k="v")
        ctx = mgr.get_global_context()
        ctx["k"] = "modified"
        assert mgr.get_global_context()["k"] == "v"

    def test_clear_global_context(self):
        mgr = ScopedContextManager()
        mgr.set_global_context(k="v")
        mgr.clear_global_context()
        assert mgr.get_global_context() == {}

    # request_context

    def test_request_context_basic(self):
        mgr = ScopedContextManager()
        with mgr.request_context(request_id="r1", user="u1") as scope_id:
            assert isinstance(scope_id, str)
            assert len(scope_id) == 8
            ctx = mgr.get_current_context()
            assert ctx["request_id"] == "r1"
            assert ctx["user"] == "u1"

    def test_request_context_restores(self):
        mgr = ScopedContextManager()
        _request_context.set({"pre": "existing"})
        with mgr.request_context(new_key="val"):
            ctx = _request_context.get({})
            assert ctx["pre"] == "existing"
            assert ctx["new_key"] == "val"
        assert _request_context.get({}) == {"pre": "existing"}

    def test_request_context_cleans_stack(self):
        mgr = ScopedContextManager()
        with mgr.request_context(a=1) as sid:
            assert sid in mgr._context_stack
        assert sid not in mgr._context_stack

    # thread_context

    def test_thread_context_basic(self):
        mgr = ScopedContextManager()
        with mgr.thread_context(worker="w1") as scope_id:
            assert isinstance(scope_id, str)
            ctx = mgr.get_current_context()
            assert ctx["worker"] == "w1"

    def test_thread_context_restores(self):
        mgr = ScopedContextManager()
        _thread_context.set({"pre": "thr"})
        with mgr.thread_context(new_key="val"):
            ctx = _thread_context.get({})
            assert ctx["pre"] == "thr"
            assert ctx["new_key"] == "val"
        assert _thread_context.get({}) == {"pre": "thr"}

    def test_thread_context_cleans_stack(self):
        mgr = ScopedContextManager()
        with mgr.thread_context(a=1) as sid:
            assert sid in mgr._context_stack
        assert sid not in mgr._context_stack

    # temporary_context

    def test_temporary_context_basic(self):
        mgr = ScopedContextManager()
        with mgr.temporary_context(op="validate") as scope_id:
            assert isinstance(scope_id, str)
            ctx = mgr.get_current_context()
            assert ctx["op"] == "validate"

    def test_temporary_context_restores(self):
        mgr = ScopedContextManager()
        _temporary_context.set({"pre": "tmp"})
        with mgr.temporary_context(new_key="val"):
            ctx = _temporary_context.get({})
            assert ctx["pre"] == "tmp"
            assert ctx["new_key"] == "val"
        assert _temporary_context.get({}) == {"pre": "tmp"}

    def test_temporary_context_cleans_stack(self):
        mgr = ScopedContextManager()
        with mgr.temporary_context(a=1) as sid:
            assert sid in mgr._context_stack
        assert sid not in mgr._context_stack

    # get_current_context (merged from all scopes)

    def test_get_current_context_merges_all(self):
        mgr = ScopedContextManager()
        mgr.set_global_context(g="global")
        _thread_context.set({"t": "thread"})
        _request_context.set({"r": "request"})
        _temporary_context.set({"tmp": "temp"})

        ctx = mgr.get_current_context()
        assert ctx == {
            "g": "global",
            "t": "thread",
            "r": "request",
            "tmp": "temp",
        }

    def test_get_current_context_priority(self):
        """Later scopes override earlier scopes."""
        mgr = ScopedContextManager()
        mgr.set_global_context(key="global")
        _thread_context.set({"key": "thread"})
        _request_context.set({"key": "request"})
        _temporary_context.set({"key": "temporary"})

        ctx = mgr.get_current_context()
        assert ctx["key"] == "temporary"

    def test_get_current_context_empty(self):
        mgr = ScopedContextManager()
        assert mgr.get_current_context() == {}

    # get_context_info

    def test_get_context_info_empty(self):
        mgr = ScopedContextManager()
        info = mgr.get_context_info()
        assert info["global_context_keys"] == []
        assert info["active_scopes"] == []
        assert info["total_context_keys"] == 0
        assert info["request_context_active"] is False
        assert info["thread_context_active"] is False
        assert info["temporary_context_active"] is False

    def test_get_context_info_with_scopes(self):
        mgr = ScopedContextManager()
        mgr.set_global_context(app="test")
        with mgr.request_context(req="r1"):
            info = mgr.get_context_info()
            assert "app" in info["global_context_keys"]
            assert len(info["active_scopes"]) == 1
            scope_info = info["active_scopes"][0]
            assert scope_info["scope_type"] == "request"
            assert "req" in scope_info["context_keys"]
            assert scope_info["context_size"] == 1
            assert info["request_context_active"] is True
            assert info["total_context_keys"] == 2

    def test_get_context_info_multiple_scopes(self):
        mgr = ScopedContextManager()
        with mgr.request_context(r=1):
            with mgr.thread_context(t=2):
                with mgr.temporary_context(tmp=3):
                    info = mgr.get_context_info()
                    assert len(info["active_scopes"]) == 3
                    assert info["request_context_active"] is True
                    assert info["thread_context_active"] is True
                    assert info["temporary_context_active"] is True

    # clear_all_context

    def test_clear_all_context(self):
        mgr = ScopedContextManager()
        mgr.set_global_context(g="val")
        _request_context.set({"r": "val"})
        _thread_context.set({"t": "val"})
        _temporary_context.set({"tmp": "val"})
        mgr._context_stack["fake"] = ContextScope()

        mgr.clear_all_context()

        assert mgr._global_context == {}
        assert _request_context.get({}) == {}
        assert _thread_context.get({}) == {}
        assert _temporary_context.get({}) == {}
        assert mgr._context_stack == {}

    # Nested context managers

    def test_nested_request_contexts(self):
        mgr = ScopedContextManager()
        with mgr.request_context(outer="o"):
            with mgr.request_context(inner="i"):
                ctx = mgr.get_current_context()
                assert ctx["outer"] == "o"
                assert ctx["inner"] == "i"
            # inner should be gone, outer restored
            ctx = mgr.get_current_context()
            assert ctx.get("outer") == "o"
            assert "inner" not in ctx


# ── ContextualLogger ─────────────────────────────────────────────


class TestContextualLogger:
    """Tests for ContextualLogger mixin."""

    def test_init(self):
        cl = ContextualLogger()
        assert isinstance(cl.context_manager, ScopedContextManager)

    def test_with_context_returns_proxy(self):
        cl = ContextualLogger()
        proxy = cl.with_context(user="u1")
        assert isinstance(proxy, ContextualLoggerProxy)

    def test_request_context(self):
        cl = ContextualLogger()
        with cl.request_context(rid="r1") as scope_id:
            assert isinstance(scope_id, str)
            ctx = cl.get_current_context()
            assert ctx["rid"] == "r1"

    def test_thread_context(self):
        cl = ContextualLogger()
        with cl.thread_context(wid="w1") as scope_id:
            assert isinstance(scope_id, str)
            ctx = cl.get_current_context()
            assert ctx["wid"] == "w1"

    def test_temporary_context(self):
        cl = ContextualLogger()
        with cl.temporary_context(op="op1") as scope_id:
            assert isinstance(scope_id, str)
            ctx = cl.get_current_context()
            assert ctx["op"] == "op1"

    def test_get_current_context(self):
        cl = ContextualLogger()
        cl.set_context(service="svc")
        ctx = cl.get_current_context()
        assert ctx["service"] == "svc"

    def test_set_context(self):
        cl = ContextualLogger()
        cl.set_context(env="prod")
        assert cl.context_manager.get_global_context() == {"env": "prod"}


# ── ContextualLoggerProxy ────────────────────────────────────────


class TestContextualLoggerProxy:
    """Tests for ContextualLoggerProxy."""

    def _make_mock_logger(self):
        logger = MagicMock()
        logger.debug = MagicMock()
        logger.info = MagicMock()
        logger.warning = MagicMock()
        logger.error = MagicMock()
        logger.critical = MagicMock()
        return logger

    def test_init(self):
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"user": "u1"})
        assert proxy._logger is logger
        assert proxy._context == {"user": "u1"}

    def test_debug(self):
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"user": "u1"})
        proxy.debug("msg", extra="e1")
        logger.debug.assert_called_once_with("msg", user="u1", extra="e1")

    def test_info(self):
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"user": "u1"})
        proxy.info("msg")
        logger.info.assert_called_once_with("msg", user="u1")

    def test_warning(self):
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"ctx": "c"})
        proxy.warning("warn msg", k="v")
        logger.warning.assert_called_once_with("warn msg", ctx="c", k="v")

    def test_error(self):
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"env": "dev"})
        proxy.error("err msg")
        logger.error.assert_called_once_with("err msg", env="dev")

    def test_critical(self):
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"sev": "high"})
        proxy.critical("crit msg")
        logger.critical.assert_called_once_with("crit msg", sev="high")

    def test_kwargs_override_context(self):
        """Explicit kwargs should override proxy context."""
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"key": "from_context"})
        proxy.info("msg", key="from_kwargs")
        logger.info.assert_called_once_with("msg", key="from_kwargs")

    def test_log_with_context_method(self):
        """Directly test _log_with_context."""
        logger = self._make_mock_logger()
        proxy = ContextualLoggerProxy(logger, {"a": 1})
        proxy._log_with_context("info", "test", b=2)
        logger.info.assert_called_once_with("test", a=1, b=2)


# ── Global convenience functions ─────────────────────────────────


class TestGlobalConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_set_and_get_global_context(self):
        set_global_context(service="svc", version="1.0")
        ctx = get_global_context()
        assert ctx == {"service": "svc", "version": "1.0"}

    def test_get_global_context_returns_copy(self):
        set_global_context(k="v")
        ctx = get_global_context()
        ctx["k"] = "modified"
        assert get_global_context()["k"] == "v"

    def test_clear_global_context(self):
        set_global_context(k="v")
        clear_global_context()
        assert get_global_context() == {}

    def test_request_context_function(self):
        with request_context(request_id="r1") as scope_id:
            assert isinstance(scope_id, str)
            ctx = _global_context_manager.get_current_context()
            assert ctx["request_id"] == "r1"

    def test_thread_context_function(self):
        with thread_context(worker="w1") as scope_id:
            assert isinstance(scope_id, str)
            ctx = _global_context_manager.get_current_context()
            assert ctx["worker"] == "w1"

    def test_temporary_context_function(self):
        with temporary_context(op="validate") as scope_id:
            assert isinstance(scope_id, str)
            ctx = _global_context_manager.get_current_context()
            assert ctx["op"] == "validate"

    def test_request_context_restores_state(self):
        with request_context(a=1):
            pass
        ctx = _global_context_manager.get_current_context()
        assert "a" not in ctx

    def test_thread_context_restores_state(self):
        with thread_context(a=1):
            pass
        ctx = _global_context_manager.get_current_context()
        assert "a" not in ctx

    def test_temporary_context_restores_state(self):
        with temporary_context(a=1):
            pass
        ctx = _global_context_manager.get_current_context()
        assert "a" not in ctx
