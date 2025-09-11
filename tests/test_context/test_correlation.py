"""Tests for correlation and context management module."""

import pytest
import threading
import time
from unittest.mock import Mock, patch
from mohflow.context.correlation import (
    generate_correlation_id,
    set_correlation_id,
    get_correlation_id,
    clear_correlation_id,
    CorrelationIDManager
)
from mohflow.context.enrichment import (
    RequestContext,
    set_request_context,
    get_request_context,
    clear_request_context,
    with_request_context
)


class TestCorrelationFunctions:
    """Test cases for correlation functions."""

    def test_generate_correlation_id(self):
        """Test correlation ID generation."""
        correlation_id = generate_correlation_id()
        
        assert correlation_id is not None
        assert isinstance(correlation_id, str)
        assert len(correlation_id) > 0

    def test_generate_correlation_id_uniqueness(self):
        """Test that generated correlation IDs are unique."""
        ids = [generate_correlation_id() for _ in range(10)]
        
        # All IDs should be unique
        assert len(set(ids)) == len(ids)

    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID."""
        test_id = "test-correlation-123"
        
        set_correlation_id(test_id)
        retrieved_id = get_correlation_id()
        
        assert retrieved_id == test_id

    def test_clear_correlation_id(self):
        """Test clearing correlation ID."""
        set_correlation_id("test-id")
        assert get_correlation_id() is not None
        
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_correlation_id_thread_isolation(self):
        """Test that correlation IDs are isolated between threads."""
        results = {}
        
        def worker(thread_id):
            set_correlation_id(f"corr-{thread_id}")
            time.sleep(0.01)  # Allow other threads to run
            results[thread_id] = get_correlation_id()
        
        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Each thread should have its own correlation ID
        for i in range(3):
            assert results[i] == f"corr-{i}"


class TestRequestContextFunctions:
    """Test cases for request context functions."""

    def test_set_and_get_request_context(self):
        """Test setting and getting request context."""
        context = RequestContext(request_id="req-123", user_id="user-456")
        
        set_request_context(context)
        retrieved_context = get_request_context()
        
        assert retrieved_context is not None
        assert retrieved_context.request_id == "req-123"
        assert retrieved_context.user_id == "user-456"

    def test_get_request_context_none_when_not_set(self):
        """Test that get_request_context returns None when not set."""
        clear_request_context()
        context = get_request_context()
        assert context is None

    def test_clear_request_context(self):
        """Test clearing request context."""
        context = RequestContext(request_id="req-123")
        set_request_context(context)
        
        assert get_request_context() is not None
        
        clear_request_context()
        assert get_request_context() is None

    def test_with_request_context_manager(self):
        """Test context manager for request context."""
        context = RequestContext(request_id="req-123", user_id="user-456")
        
        with with_request_context(context):
            retrieved_context = get_request_context()
            
            assert retrieved_context is not None
            assert retrieved_context.request_id == "req-123"
            assert retrieved_context.user_id == "user-456"
        
        # Context should be cleared after exiting context manager
        assert get_request_context() is None

    def test_request_context_thread_isolation(self):
        """Test that request context is isolated between threads."""
        results = {}
        
        def worker(thread_id):
            context = RequestContext(request_id=f"req-{thread_id}")
            set_request_context(context)
            time.sleep(0.01)  # Allow other threads to run
            
            retrieved = get_request_context()
            results[thread_id] = retrieved.request_id if retrieved else None
        
        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Each thread should have its own context
        for i in range(3):
            assert results[i] == f"req-{i}"


class TestCorrelationIDManager:
    """Test cases for CorrelationIDManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = CorrelationIDManager()

    def test_manager_initialization(self):
        """Test CorrelationIDManager initialization."""
        assert self.manager is not None

    def test_manager_generate_id(self):
        """Test ID generation through manager."""
        correlation_id = self.manager.generate_id()
        
        assert correlation_id is not None
        assert isinstance(correlation_id, str)
        assert len(correlation_id) > 0

    def test_manager_set_and_get_id(self):
        """Test setting and getting ID through manager."""
        test_id = "manager-test-id"
        
        self.manager.set_id(test_id)
        retrieved_id = self.manager.get_id()
        
        assert retrieved_id == test_id

    def test_manager_clear_id(self):
        """Test clearing ID through manager."""
        self.manager.set_id("test-id")
        assert self.manager.get_id() is not None
        
        self.manager.clear_id()
        assert self.manager.get_id() is None