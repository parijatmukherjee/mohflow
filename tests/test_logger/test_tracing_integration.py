"""
T013: Test MohflowLogger with exclude_tracing_fields parameter
These tests MUST FAIL initially (TDD approach)
"""

from mohflow import MohflowLogger


class TestTracingIntegration:
    """Test MohflowLogger integration with enhanced filter"""

    def test_logger_exclude_tracing_fields_parameter(self):
        """Test MohflowLogger accepts exclude_tracing_fields parameter"""
        # Should accept parameter without error
        logger = MohflowLogger(
            service_name="test-service",
            enable_sensitive_filter=True,
            exclude_tracing_fields=True,
        )

        assert logger is not None
        assert hasattr(logger, "sensitive_filter")
        assert logger.sensitive_filter is not None

    def test_logger_exclude_tracing_fields_default_true(self):
        """Test exclude_tracing_fields defaults to True for better observability"""
        logger = MohflowLogger(
            service_name="test-service",
            enable_sensitive_filter=True,
            # exclude_tracing_fields not specified - should default to True
        )

        # Should have tracing field exemptions enabled by default
        config = logger.sensitive_filter.get_configuration()
        assert config.exclude_tracing_fields is True

    def test_logger_exclude_tracing_fields_disabled(self):
        """Test logger with exclude_tracing_fields=False"""
        logger = MohflowLogger(
            service_name="test-service",
            enable_sensitive_filter=True,
            exclude_tracing_fields=False,
        )

        config = logger.sensitive_filter.get_configuration()
        assert config.exclude_tracing_fields is False

    def test_logger_custom_safe_fields_parameter(self):
        """Test logger accepts custom_safe_fields parameter"""
        custom_fields = {"app_trace_id", "service_correlation_id"}
        logger = MohflowLogger(
            service_name="test-service",
            enable_sensitive_filter=True,
            exclude_tracing_fields=True,
            custom_safe_fields=custom_fields,
        )

        config = logger.sensitive_filter.get_configuration()
        for field in custom_fields:
            assert field in config.custom_safe_fields

    def test_logger_filter_integration_tracing_preserved(self):
        """Test logger preserves tracing fields in actual logging"""
        import io
        import json

        # Capture log output
        log_capture = io.StringIO()

        logger = MohflowLogger(
            service_name="test-service",
            enable_sensitive_filter=True,
            exclude_tracing_fields=True,
            log_level="INFO",
        )

        # Add custom handler to capture output
        import logging

        handler = logging.StreamHandler(log_capture)
        logger.logger.addHandler(handler)

        # Log message with mixed sensitive and tracing data
        logger.info(
            "Test message",
            correlation_id="req-123",
            trace_id="trace-456",
            api_key="secret-key",
            password="user-pass",
        )

        # Get captured log output
        log_output = log_capture.getvalue()

        # Parse JSON log entry
        log_entry = json.loads(log_output.strip())

        # Tracing fields should be preserved
        assert log_entry["correlation_id"] == "req-123"
        assert log_entry["trace_id"] == "trace-456"

        # Sensitive fields should be redacted
        assert log_entry["api_key"] == "[REDACTED]"
        assert log_entry["password"] == "[REDACTED]"
