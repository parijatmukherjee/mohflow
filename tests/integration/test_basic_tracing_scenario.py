"""
T015: Test basic usage scenario - tracing fields preserved
These tests MUST FAIL initially (TDD approach)
"""

from mohflow import MohflowLogger


class TestBasicTracingScenario:
    """Test basic usage scenario from quickstart.md"""

    def test_basic_usage_scenario_quickstart(self):
        """Test exact scenario from quickstart - basic usage"""
        # From quickstart.md - basic usage scenario
        logger = MohflowLogger(
            service_name="my-service",
            enable_sensitive_filter=True,
            exclude_tracing_fields=True,
        )

        # Test data from quickstart example
        test_log_data = {
            "correlation_id": "req-123",  # Should be PRESERVED
            "request_id": "trace-456",  # Should be PRESERVED
            "user_id": "user-789",  # Should be PRESERVED (neutral)
            "api_key": "secret-key-123",  # Should be REDACTED
            "password": "user-password",  # Should be REDACTED
        }

        # Filter the data (simulating what happens during logging)
        filtered_data = logger.sensitive_filter.filter_data(test_log_data)

        # For audit trail, use the enhanced method
        result = logger.sensitive_filter.filter_data_with_audit(test_log_data)

        # Expected behavior from quickstart
        assert filtered_data["correlation_id"] == "req-123"  # Preserved!
        assert filtered_data["request_id"] == "trace-456"  # Preserved!
        assert filtered_data["user_id"] == "user-789"  # Preserved!
        assert (
            filtered_data["api_key"] == "[REDACTED]"
        )  # Redacted for security
        assert (
            filtered_data["password"] == "[REDACTED]"
        )  # Redacted for security

        # Verify audit trail
        # Only tracing fields get marked as "preserved"
        preserved_tracing_fields = {"correlation_id", "request_id"}
        redacted_fields = {"api_key", "password"}

        for field in preserved_tracing_fields:
            assert field in result.preserved_fields

        for field in redacted_fields:
            assert field in result.redacted_fields

        # user_id should be neither preserved nor redacted (neutral field)
        assert "user_id" not in result.preserved_fields
        assert "user_id" not in result.redacted_fields
