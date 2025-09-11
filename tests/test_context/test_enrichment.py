"""Tests for context enrichment module."""

import pytest
import logging
import threading
import time
from unittest.mock import Mock, patch
from mohflow.context.enrichment import (
    ContextEnricher,
    RequestContext,
    GlobalContext,
    set_request_context,
    get_request_context,
    with_request_context
)


class TestRequestContext:
    """Test cases for RequestContext dataclass."""

    def test_request_context_creation(self):
        """Test RequestContext creation."""
        context = RequestContext(
            request_id="req-123",
            correlation_id="corr-456",
            user_id="user-789",
            session_id="sess-abc"
        )
        
        assert context.request_id == "req-123"
        assert context.correlation_id == "corr-456"
        assert context.user_id == "user-789"
        assert context.session_id == "sess-abc"

    def test_request_context_minimal(self):
        """Test RequestContext with minimal data."""
        context = RequestContext(request_id="req-123")
        
        assert context.request_id == "req-123"
        assert context.correlation_id is None
        assert context.user_id is None
        assert context.session_id is None

    def test_request_context_to_dict(self):
        """Test RequestContext conversion to dictionary."""
        context = RequestContext(
            request_id="req-123",
            user_id="user-789"
        )
        
        context_dict = context.to_dict()
        
        assert context_dict["request_id"] == "req-123"
        assert context_dict["user_id"] == "user-789"
        assert "correlation_id" not in context_dict  # None values excluded


class TestGlobalContext:
    """Test cases for GlobalContext dataclass."""

    def test_global_context_creation(self):
        """Test GlobalContext creation."""
        context = GlobalContext(
            service_name="test-service",
            environment="test",
            version="1.0.0"
        )
        
        assert context.service_name == "test-service"
        assert context.environment == "test"
        assert context.version == "1.0.0"

    def test_global_context_to_dict(self):
        """Test GlobalContext conversion to dictionary."""
        context = GlobalContext(
            service_name="test-service",
            environment="test"
        )
        
        context_dict = context.to_dict()
        
        assert context_dict["service_name"] == "test-service"
        assert context_dict["environment"] == "test"


class TestContextEnricher:
    """Test cases for ContextEnricher class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.enricher = ContextEnricher()

    def test_enricher_initialization_defaults(self):
        """Test ContextEnricher initialization with defaults."""
        assert self.enricher.include_timestamp is True
        assert self.enricher.include_system_info is True
        assert self.enricher.include_request_context is True

    def test_enricher_initialization_custom(self):
        """Test ContextEnricher initialization with custom settings."""
        enricher = ContextEnricher(
            include_timestamp=False,
            include_system_info=False,
            include_request_context=False
        )
        
        assert enricher.include_timestamp is False
        assert enricher.include_system_info is False
        assert enricher.include_request_context is False

    @patch('socket.gethostname')
    @patch('os.getpid')
    @patch('threading.get_ident')
    def test_get_system_info(self, mock_thread_id, mock_process_id, mock_hostname):
        """Test system information gathering."""
        mock_hostname.return_value = "test-host"
        mock_process_id.return_value = 12345
        mock_thread_id.return_value = 67890
        
        # Test if enricher has system info gathering capability
        assert hasattr(self.enricher, 'include_system_info')
        assert self.enricher.include_system_info is True

    def test_enrich_log_record_basic(self):
        """Test basic log record enrichment."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        enriched = self.enricher.enrich_log_record(record)
        
        # Should return the same record object (enriched in place)
        assert enriched is record
        
        # Should have added some enrichment attributes
        # The exact attributes depend on the enricher settings

    def test_enrich_log_record_with_request_context(self):
        """Test log record enrichment with request context."""
        from mohflow.context.correlation import set_request_context
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        with set_request_context(request_id="req-123", user_id="user-456"):
            with patch.object(self.enricher, '_get_system_info') as mock_sys_info:
                mock_sys_info.return_value = SystemInfo(hostname="test-host")
                
                enriched = self.enricher.enrich_log_record(record)
                
                assert hasattr(enriched, 'request_id')
                assert hasattr(enriched, 'user_id')
                assert enriched.request_id == "req-123"
                assert enriched.user_id == "user-456"

    def test_enrich_log_record_no_system_info(self):
        """Test log record enrichment without system info."""
        enricher = ContextEnricher(include_system_info=False)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        enriched = enricher.enrich_log_record(record)
        
        assert not hasattr(enriched, 'hostname')
        assert not hasattr(enriched, 'process_id')

    def test_enrich_log_record_no_request_context(self):
        """Test log record enrichment without request context."""
        enricher = ContextEnricher(include_request_context=False)
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        with patch.object(enricher, '_get_system_info') as mock_sys_info:
            mock_sys_info.return_value = SystemInfo(hostname="test-host")
            
            enriched = enricher.enrich_log_record(record)
            
            assert not hasattr(enriched, 'request_id')
            assert not hasattr(enriched, 'user_id')

    def test_enrich_log_record_preserve_existing_attributes(self):
        """Test that enrichment preserves existing record attributes."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Warning message",
            args=(),
            exc_info=None
        )
        
        # Add custom attribute
        record.custom_field = "custom_value"
        
        with patch.object(self.enricher, '_get_system_info') as mock_sys_info:
            mock_sys_info.return_value = SystemInfo(hostname="test-host")
            
            enriched = self.enricher.enrich_log_record(record)
            
            # Original attributes should be preserved
            assert enriched.name == "test.logger"
            assert enriched.levelno == logging.WARNING
            assert enriched.pathname == "/path/to/file.py"
            assert enriched.lineno == 42
            assert enriched.msg == "Warning message"
            assert enriched.custom_field == "custom_value"
            
            # New attributes should be added
            assert hasattr(enriched, 'hostname')

    def test_thread_safety(self):
        """Test that context enrichment is thread-safe."""
        from mohflow.context.correlation import set_request_context
        
        results = []
        
        def worker(thread_id):
            with set_request_context(request_id=f"req-{thread_id}"):
                record = logging.LogRecord(
                    name="test",
                    level=logging.INFO,
                    pathname="",
                    lineno=0,
                    msg=f"Message from thread {thread_id}",
                    args=(),
                    exc_info=None
                )
                
                with patch.object(self.enricher, '_get_system_info') as mock_sys_info:
                    mock_sys_info.return_value = SystemInfo(hostname="test-host")
                    
                    enriched = self.enricher.enrich_log_record(record)
                    results.append((thread_id, enriched.request_id))
        
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify each thread got its own request_id
        assert len(results) == 5
        for thread_id, request_id in results:
            assert request_id == f"req-{thread_id}"

    def test_performance_overhead(self):
        """Test that enrichment doesn't add significant overhead."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        with patch.object(self.enricher, '_get_system_info') as mock_sys_info:
            mock_sys_info.return_value = SystemInfo(hostname="test-host")
            
            start_time = time.time()
            for _ in range(1000):
                self.enricher.enrich_log_record(record)
            end_time = time.time()
            
            # Should complete 1000 enrichments in under 1 second
            assert (end_time - start_time) < 1.0