"""Tests for F5: contextvars-First Context API."""

import logging
import threading
import pytest
from mohflow.context_api import (
    bind_context,
    unbind_context,
    clear_context,
    get_bound_context,
)
from mohflow import MohflowLogger


@pytest.fixture(autouse=True)
def clean_context():
    """Ensure context is clean before and after each test."""
    clear_context()
    yield
    clear_context()


class TestBindContext:
    """Test bind_context function."""

    def test_bind_single_key(self):
        bind_context(user_id="u123")
        assert get_bound_context() == {"user_id": "u123"}

    def test_bind_multiple_keys(self):
        bind_context(user_id="u123", tenant="acme")
        ctx = get_bound_context()
        assert ctx["user_id"] == "u123"
        assert ctx["tenant"] == "acme"

    def test_bind_overwrites_existing(self):
        bind_context(user_id="old")
        bind_context(user_id="new")
        assert get_bound_context()["user_id"] == "new"

    def test_bind_accumulates(self):
        bind_context(a=1)
        bind_context(b=2)
        ctx = get_bound_context()
        assert ctx == {"a": 1, "b": 2}

    def test_bind_complex_values(self):
        bind_context(
            tags=["web", "api"],
            metadata={"version": "1.0"},
        )
        ctx = get_bound_context()
        assert ctx["tags"] == ["web", "api"]
        assert ctx["metadata"]["version"] == "1.0"


class TestUnbindContext:
    """Test unbind_context function."""

    def test_unbind_single_key(self):
        bind_context(a=1, b=2)
        unbind_context("a")
        assert get_bound_context() == {"b": 2}

    def test_unbind_multiple_keys(self):
        bind_context(a=1, b=2, c=3)
        unbind_context("a", "c")
        assert get_bound_context() == {"b": 2}

    def test_unbind_nonexistent_key(self):
        bind_context(a=1)
        unbind_context("nonexistent")  # Should not raise
        assert get_bound_context() == {"a": 1}

    def test_unbind_no_keys(self):
        bind_context(a=1)
        unbind_context()  # Should be a no-op
        assert get_bound_context() == {"a": 1}

    def test_unbind_all_keys(self):
        bind_context(a=1, b=2)
        unbind_context("a", "b")
        assert get_bound_context() == {}


class TestClearContext:
    """Test clear_context function."""

    def test_clear_removes_all(self):
        bind_context(a=1, b=2, c=3)
        clear_context()
        assert get_bound_context() == {}

    def test_clear_on_empty(self):
        clear_context()  # Should not raise
        assert get_bound_context() == {}


class TestGetBoundContext:
    """Test get_bound_context function."""

    def test_returns_copy(self):
        bind_context(a=1)
        ctx = get_bound_context()
        ctx["a"] = 999
        # Original should be unchanged
        assert get_bound_context()["a"] == 1

    def test_empty_by_default(self):
        assert get_bound_context() == {}


class TestContextVarsIsolation:
    """Test that context is isolated per-thread."""

    def test_thread_isolation(self):
        results = {}

        def thread_fn(name, value):
            clear_context()
            bind_context(key=value)
            import time

            time.sleep(0.01)
            results[name] = get_bound_context()

        t1 = threading.Thread(target=thread_fn, args=("t1", "val1"))
        t2 = threading.Thread(target=thread_fn, args=("t2", "val2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["t1"]["key"] == "val1"
        assert results["t2"]["key"] == "val2"


class TestContextIntegrationWithLogger:
    """Test that bound context flows into log records."""

    def test_bound_context_in_logs(self, caplog):
        logger = MohflowLogger(
            service_name="ctx-test",
            enable_sensitive_data_filter=False,
            enable_context_enrichment=False,
        )
        bind_context(user_id="u123", tenant="acme")
        with caplog.at_level(logging.INFO):
            logger.info("request")
        records = [r for r in caplog.records if "request" in r.message]
        assert len(records) == 1
        assert records[0].user_id == "u123"
        assert records[0].tenant == "acme"

    def test_unbind_removes_from_logs(self, caplog):
        logger = MohflowLogger(
            service_name="ctx-test2",
            enable_sensitive_data_filter=False,
            enable_context_enrichment=False,
        )
        bind_context(user_id="u123", tenant="acme")
        unbind_context("tenant")
        with caplog.at_level(logging.INFO):
            logger.info("after unbind")
        records = [r for r in caplog.records if "after unbind" in r.message]
        assert len(records) == 1
        assert records[0].user_id == "u123"
        assert not hasattr(records[0], "tenant")

    def test_clear_removes_all_from_logs(self, caplog):
        logger = MohflowLogger(
            service_name="ctx-test3",
            enable_sensitive_data_filter=False,
            enable_context_enrichment=False,
        )
        bind_context(user_id="u123")
        clear_context()
        with caplog.at_level(logging.INFO):
            logger.info("after clear")
        records = [r for r in caplog.records if "after clear" in r.message]
        assert len(records) == 1
        assert not hasattr(records[0], "user_id")

    def test_explicit_kwargs_override_bound_context(self, caplog):
        """Explicit log kwargs take precedence over bound context."""
        logger = MohflowLogger(
            service_name="ctx-test4",
            enable_sensitive_data_filter=False,
            enable_context_enrichment=False,
        )
        bind_context(user_id="from_context")
        with caplog.at_level(logging.INFO):
            logger.info("override", user_id="from_explicit")
        records = [r for r in caplog.records if "override" in r.message]
        assert records[0].user_id == "from_explicit"
