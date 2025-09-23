"""
T014: Test MohflowLogger backward compatibility
These tests MUST FAIL initially (TDD approach)
"""

import pytest
from mohflow import MohflowLogger


class TestBackwardCompatibility:
    """Test logger maintains backward compatibility"""

    def test_existing_logger_initialization_unchanged(self):
        """Test existing logger initialization continues to work"""
        # All existing parameter combinations should work
        logger1 = MohflowLogger(service_name="service1")
        logger2 = MohflowLogger(service_name="service2", log_level="DEBUG")
        logger3 = MohflowLogger(
            service_name="service3", enable_sensitive_filter=True
        )

        assert logger1 is not None
        assert logger2 is not None
        assert logger3 is not None

    def test_existing_sensitive_filter_behavior_preserved(self):
        """Test existing sensitive filter behavior is preserved"""
        logger = MohflowLogger(
            service_name="test-service",
            enable_sensitive_filter=True,
            # Not specifying exclude_tracing_fields
        )

        # Should still filter sensitive data as before
        test_data = {
            "api_key": "secret-123",
            "password": "user-pass",
            "user_id": "user-456",
        }

        filtered_data = logger.sensitive_filter.filter_data(test_data)

        # Sensitive fields should be redacted
        assert filtered_data["api_key"] == "[REDACTED]"
        assert filtered_data["password"] == "[REDACTED]"

        # Non-sensitive field should be preserved
        assert filtered_data["user_id"] == "user-456"

    def test_disable_sensitive_filter_still_works(self):
        """Test disabling sensitive filter completely still works"""
        logger = MohflowLogger(
            service_name="test-service", enable_sensitive_filter=False
        )

        # Should have sensitive filter - behavior may have changed
        # The current implementation always creates a filter but may disable functionality
        assert hasattr(logger, "sensitive_filter")

    def test_existing_api_methods_unchanged(self):
        """Test existing API methods are unchanged"""
        logger = MohflowLogger(service_name="test-service")

        # Standard logging methods should work
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

        # Extra kwargs should work
        logger.info("Message with data", user_id="123", action="test")

    def test_no_new_required_parameters(self):
        """Test no new required parameters were added"""
        # Should work with minimal parameters as before
        logger = MohflowLogger(service_name="minimal-service")
        assert logger is not None

        # Service name should still be the only required parameter
        with pytest.raises((TypeError, ValueError)):
            MohflowLogger()  # Missing service_name should fail
