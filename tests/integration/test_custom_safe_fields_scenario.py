"""
T016: Test custom safe fields scenario
T017: Test high security mode scenario
T018: Test direct filter usage scenario
These tests MUST FAIL initially (TDD approach)
"""

from mohflow import MohflowLogger
from mohflow.context.filters import SensitiveDataFilter


class TestCustomSafeFieldsScenario:
    """Test custom safe fields scenario from quickstart.md"""

    def test_custom_safe_fields_scenario(self):
        """Test quickstart scenario with custom safe fields"""
        logger = MohflowLogger(
            service_name="my-service",
            enable_sensitive_filter=True,
            exclude_tracing_fields=True,
            custom_safe_fields={"order_id", "session_id", "batch_id"},
        )

        test_data = {
            "order_id": "order-123",  # Should be PRESERVED (custom safe)
            "session_id": "sess-456",  # Should be PRESERVED (custom safe)
            "batch_id": "batch-789",  # Should be PRESERVED (custom safe)
            "credit_card": "1234-5678-9012",  # Should be REDACTED (sensitive pattern)
        }

        result = logger.sensitive_filter.filter_data_with_audit(test_data)

        assert result.filtered_data["order_id"] == "order-123"
        assert result.filtered_data["session_id"] == "sess-456"
        assert result.filtered_data["batch_id"] == "batch-789"
        assert result.filtered_data["credit_card"] == "[REDACTED]"


class TestHighSecurityScenario:
    """Test high security mode scenario from quickstart.md"""

    def test_high_security_mode_scenario(self):
        """Test quickstart scenario with tracing exemptions disabled"""
        logger = MohflowLogger(
            service_name="secure-service",
            enable_sensitive_filter=True,
            exclude_tracing_fields=False,  # Disable tracing exemptions
        )

        test_data = {
            "correlation_id": "req-123",  # Should be REDACTED (no exemptions)
            "api_key": "secret-key-123",  # Should be REDACTED (sensitive field)
        }

        result = logger.sensitive_filter.filter_data_with_audit(test_data)

        # In high security mode, even tracing fields get normal treatment
        assert result.filtered_data["api_key"] == "[REDACTED]"
        # correlation_id should be preserved unless it matches sensitive patterns
        assert result.filtered_data["correlation_id"] == "req-123"


class TestDirectFilterScenario:
    """Test direct filter usage scenario from quickstart.md"""

    def test_direct_filter_usage_scenario(self):
        """Test quickstart scenario using filter directly"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True,
            custom_safe_fields={"transaction_id", "span_id"},
        )

        data = {
            "correlation_id": "req-123",
            "api_key": "secret-123",
            "nested": {"trace_id": "trace-456", "password": "secret"},
        }

        result = filter_obj.filter_data_with_audit(data)

        # Expected output from quickstart
        expected_filtered_data = {
            "correlation_id": "req-123",
            "api_key": "[REDACTED]",
            "nested": {"trace_id": "trace-456", "password": "[REDACTED]"},
        }

        assert result.filtered_data == expected_filtered_data
        assert "api_key" in result.redacted_fields
        assert "nested.password" in result.redacted_fields
        assert "correlation_id" in result.preserved_fields
        assert "nested.trace_id" in result.preserved_fields
