"""Tests to improve coverage for context/enrichment.py."""

import pytest
from unittest.mock import patch, MagicMock
from mohflow.context.enrichment import (
    ContextEnricher,
    RequestContext,
    RequestContextManager,
    GlobalContextManager,
    set_request_context,
    get_request_context,
    clear_request_context,
    set_global_context,
    get_global_context,
    clear_global_context,
    update_request_context,
    with_request_context,
    with_request_context_decorator,
    with_global_context,
    _request_context,
    _global_context,
)


@pytest.fixture(autouse=True)
def _clean_enrichment():
    """Reset enrichment context between tests."""
    yield
    _request_context.set(None)
    _global_context.set({})


class TestRequestContext:
    def test_to_dict_with_operation(self):
        ctx = RequestContext(
            request_id="r1",
            correlation_id="c1",
            operation_name="my_op",
        )
        d = ctx.to_dict()
        assert d["request_id"] == "r1"
        assert "operation_name" in d
        assert d["operation_name"] == "my_op"

    def test_to_dict_without_operation(self):
        ctx = RequestContext(request_id="r1")
        d = ctx.to_dict()
        assert "operation_name" not in d

    def test_to_dict_with_custom_fields(self):
        ctx = RequestContext(
            request_id="r1",
            custom_fields={"foo": "bar", "num": 42},
        )
        d = ctx.to_dict()
        assert d["foo"] == "bar"
        assert d["num"] == 42

    def test_to_dict_all_fields(self):
        ctx = RequestContext(
            request_id="r1",
            correlation_id="c1",
            user_id="u1",
            session_id="s1",
            trace_id="t1",
            span_id="sp1",
        )
        d = ctx.to_dict()
        assert d["user_id"] == "u1"
        assert d["session_id"] == "s1"
        assert d["trace_id"] == "t1"
        assert d["span_id"] == "sp1"


class TestContextEnricher:
    def test_enrich_basic(self):
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=False,
        )
        result = enricher.enrich_dict({"msg": "hi"})
        assert result["msg"] == "hi"

    def test_enrich_with_system_info(self):
        enricher = ContextEnricher(
            include_system_info=True,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=False,
        )
        result = enricher.enrich_dict({})
        assert "process_id" in result
        assert "thread_id" in result
        assert "hostname" in result

    def test_enrich_with_timestamp(self):
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=True,
            include_global_context=False,
            include_request_context=False,
        )
        result = enricher.enrich_dict({})
        assert "timestamp" in result

    def test_enrich_with_global_context(self):
        set_global_context(env="prod")
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=False,
            include_global_context=True,
            include_request_context=False,
        )
        result = enricher.enrich_dict({})
        assert result["env"] == "prod"

    def test_enrich_with_request_context(self):
        ctx = RequestContext(request_id="r1", operation_name="test")
        set_request_context(ctx)
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=True,
        )
        result = enricher.enrich_dict({})
        assert result["request_id"] == "r1"

    def test_custom_enricher(self):
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=False,
        )
        enricher.add_custom_enricher("custom_val", lambda: "hello")
        result = enricher.enrich_dict({})
        assert result["custom_val"] == "hello"

    def test_custom_enricher_returns_none(self):
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=False,
        )
        enricher.add_custom_enricher("skip_me", lambda: None)
        result = enricher.enrich_dict({})
        assert "skip_me" not in result

    def test_custom_enricher_error(self):
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=False,
        )

        def failing():
            raise ValueError("boom")

        enricher.add_custom_enricher("bad", failing)
        result = enricher.enrich_dict({})
        assert "bad_error" in result
        assert "boom" in result["bad_error"]

    def test_remove_custom_enricher(self):
        enricher = ContextEnricher(
            include_system_info=False,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=False,
        )
        enricher.add_custom_enricher("x", lambda: 1)
        enricher.remove_custom_enricher("x")
        result = enricher.enrich_dict({})
        assert "x" not in result

    def test_system_info_caching(self):
        enricher = ContextEnricher(
            include_system_info=True,
            include_timestamp=False,
            include_global_context=False,
            include_request_context=False,
        )
        r1 = enricher.enrich_dict({})
        r2 = enricher.enrich_dict({})
        # Same process_id from cache
        assert r1["process_id"] == r2["process_id"]


class TestContextFunctions:
    def test_set_get_clear_request_context(self):
        ctx = RequestContext(request_id="r1")
        set_request_context(ctx)
        assert get_request_context() is ctx
        clear_request_context()
        assert get_request_context() is None

    def test_set_get_clear_global_context(self):
        set_global_context(env="test", region="us")
        result = get_global_context()
        assert result["env"] == "test"
        assert result["region"] == "us"
        clear_global_context()
        assert get_global_context() == {}

    def test_update_request_context(self):
        ctx = RequestContext(request_id="r1", custom_fields={"a": 1})
        set_request_context(ctx)
        update_request_context(b=2)
        updated = get_request_context()
        assert updated.custom_fields["b"] == 2

    def test_update_request_context_no_context(self):
        # Should not raise when no context
        update_request_context(x=1)


class TestRequestContextManager:
    def test_basic_usage(self):
        with RequestContextManager(request_id="r1") as ctx:
            assert ctx.request_id == "r1"
            assert get_request_context() is ctx
        assert get_request_context() is None

    def test_auto_correlation_id(self):
        with RequestContextManager(request_id="r1") as ctx:
            assert ctx.correlation_id is not None

    def test_explicit_correlation_id(self):
        with RequestContextManager(
            request_id="r1",
            correlation_id="my-corr-id",
        ) as ctx:
            assert ctx.correlation_id == "my-corr-id"

    def test_nested_contexts(self):
        with RequestContextManager(request_id="outer") as outer:
            assert get_request_context() is outer
            with RequestContextManager(request_id="inner") as inner:
                assert get_request_context() is inner
            assert get_request_context() is outer

    def test_restores_previous_on_exit(self):
        prev = RequestContext(
            request_id="prev",
            correlation_id="prev-corr",
        )
        set_request_context(prev)
        with RequestContextManager(request_id="temp"):
            pass
        restored = get_request_context()
        assert restored.request_id == "prev"

    def test_custom_fields_passed(self):
        with RequestContextManager(
            request_id="r1",
            user_id="u1",
            session_id="s1",
            operation_name="op1",
        ) as ctx:
            assert ctx.user_id == "u1"
            assert ctx.session_id == "s1"
            assert ctx.operation_name == "op1"


class TestGlobalContextManager:
    def test_basic_usage(self):
        with GlobalContextManager(env="staging"):
            ctx = get_global_context()
            assert ctx["env"] == "staging"
        assert get_global_context() == {}

    def test_nested_global_context(self):
        with GlobalContextManager(a=1):
            with GlobalContextManager(b=2):
                ctx = get_global_context()
                assert ctx["a"] == 1
                assert ctx["b"] == 2
            ctx = get_global_context()
            assert ctx["a"] == 1
            assert "b" not in ctx

    def test_restores_previous(self):
        set_global_context(before="yes")
        with GlobalContextManager(during="yes"):
            pass
        ctx = get_global_context()
        assert ctx["before"] == "yes"
        assert "during" not in ctx


class TestWithRequestContext:
    def test_with_request_context_obj(self):
        ctx = RequestContext(
            request_id="r1",
            correlation_id="c1",
            user_id="u1",
        )
        with with_request_context(ctx) as inner:
            assert inner.request_id == "r1"

    def test_with_request_context_as_decorator(self):
        @with_request_context(
            "req-123",
            correlation_id="c-456",
            user_id="u-789",
        )
        def my_func():
            ctx = get_request_context()
            return ctx.request_id

        result = my_func()
        assert result == "req-123"

    def test_decorator_uses_func_name(self):
        @with_request_context("r1")
        def my_operation():
            ctx = get_request_context()
            return ctx.operation_name

        result = my_operation()
        assert result == "my_operation"

    def test_decorator_custom_fields(self):
        @with_request_context("r1", custom_key="custom_val")
        def func_with_custom():
            ctx = get_request_context()
            return ctx.custom_fields.get("custom_key")

        result = func_with_custom()
        assert result == "custom_val"


class TestWithRequestContextDecorator:
    def test_basic(self):
        @with_request_context_decorator(request_id="r1")
        def my_func():
            return get_request_context().request_id

        assert my_func() == "r1"

    def test_auto_operation_name(self):
        @with_request_context_decorator()
        def auto_named():
            return get_request_context().operation_name

        assert auto_named() == "auto_named"

    def test_custom_fields(self):
        @with_request_context_decorator(user_id="u1", custom="val")
        def with_custom():
            ctx = get_request_context()
            return (
                ctx.user_id,
                ctx.custom_fields.get("custom"),
            )

        u, c = with_custom()
        assert u == "u1"
        assert c == "val"


class TestWithGlobalContext:
    def test_as_decorator(self):
        @with_global_context(env="test")
        def check_context():
            return get_global_context()

        result = check_context()
        assert result["env"] == "test"
        # After function returns, context should be restored
        assert "env" not in get_global_context()
