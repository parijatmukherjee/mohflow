"""
T006: Test TracingFieldRegistry default fields and patterns
These tests MUST FAIL initially (TDD approach)
"""

import pytest
from mohflow.context.filters import TracingFieldRegistry


class TestTracingFieldRegistry:
    """Test TracingFieldRegistry entity from data model"""

    def test_tracing_registry_default_fields_constants(self):
        """Test DEFAULT_TRACING_FIELDS constant is defined correctly"""
        expected_fields = {
            "correlation_id",
            "request_id",
            "trace_id",
            "span_id",
            "transaction_id",
            "session_id",
            "operation_id",
            "parent_id",
            "root_id",
            "trace_context",
        }

        assert hasattr(TracingFieldRegistry, "DEFAULT_TRACING_FIELDS")
        assert TracingFieldRegistry.DEFAULT_TRACING_FIELDS == expected_fields

    def test_tracing_registry_default_patterns_constants(self):
        """Test DEFAULT_TRACING_PATTERNS constant is defined correctly"""
        expected_patterns = [
            r"^trace_.*",  # trace_*
            r"^span_.*",  # span_*
            r"^request_.*",  # request_*
            r"^correlation_.*",  # correlation_*
            r".*_trace_id$",  # *_trace_id
            r".*_span_id$",  # *_span_id
            r".*_request_id$",  # *_request_id
        ]

        assert hasattr(TracingFieldRegistry, "DEFAULT_TRACING_PATTERNS")
        assert (
            TracingFieldRegistry.DEFAULT_TRACING_PATTERNS == expected_patterns
        )

    def test_tracing_registry_initialization(self):
        """Test TracingFieldRegistry initialization"""
        registry = TracingFieldRegistry()

        assert (
            registry.default_fields
            == TracingFieldRegistry.DEFAULT_TRACING_FIELDS
        )
        assert (
            registry.default_patterns
            == TracingFieldRegistry.DEFAULT_TRACING_PATTERNS
        )
        assert registry.custom_fields == set()
        assert registry.custom_patterns == []

    def test_is_tracing_field_default_fields(self):
        """Test is_tracing_field returns True for all DEFAULT_TRACING_FIELDS"""
        registry = TracingFieldRegistry()

        for field in TracingFieldRegistry.DEFAULT_TRACING_FIELDS:
            assert registry.is_tracing_field(field) is True

    def test_is_tracing_field_default_patterns(self):
        """Test is_tracing_field returns True for fields matching DEFAULT_TRACING_PATTERNS"""
        registry = TracingFieldRegistry()

        # Test fields that should match default patterns
        test_cases = [
            "trace_abc123",  # matches ^trace_.*
            "span_operation",  # matches ^span_.*
            "request_handler",  # matches ^request_.*
            "correlation_uuid",  # matches ^correlation_.*
            "custom_trace_id",  # matches .*_trace_id$
            "service_span_id",  # matches .*_span_id$
            "http_request_id",  # matches .*_request_id$
        ]

        for field in test_cases:
            assert registry.is_tracing_field(field) is True

    def test_is_tracing_field_sensitive_fields_false(self):
        """Test is_tracing_field returns False for sensitive field names"""
        registry = TracingFieldRegistry()

        sensitive_fields = [
            "api_key",
            "password",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "private_key",
        ]

        for field in sensitive_fields:
            assert registry.is_tracing_field(field) is False

    def test_is_tracing_field_none_empty_input(self):
        """Test is_tracing_field handles None/empty input gracefully"""
        registry = TracingFieldRegistry()

        assert registry.is_tracing_field(None) is False
        assert registry.is_tracing_field("") is False
        assert registry.is_tracing_field("   ") is False

    def test_is_tracing_field_case_sensitivity(self):
        """Test is_tracing_field respects case sensitivity settings"""
        registry = TracingFieldRegistry(case_sensitive=False)

        # Should match regardless of case
        assert registry.is_tracing_field("CORRELATION_ID") is True
        assert registry.is_tracing_field("Trace_ID") is True
        assert registry.is_tracing_field("REQUEST_id") is True

        registry_sensitive = TracingFieldRegistry(case_sensitive=True)

        # Should only match exact case
        assert registry_sensitive.is_tracing_field("correlation_id") is True
        assert registry_sensitive.is_tracing_field("CORRELATION_ID") is False

    def test_add_custom_field_valid(self):
        """Test adding valid custom field to exemption list"""
        registry = TracingFieldRegistry()

        registry.add_custom_field("custom_trace_field")
        assert "custom_trace_field" in registry.custom_fields
        assert registry.is_tracing_field("custom_trace_field") is True

    def test_add_custom_field_empty_none_validation(self):
        """Test add_custom_field validates field name"""
        registry = TracingFieldRegistry()

        with pytest.raises(ValueError, match="field_name.*empty"):
            registry.add_custom_field("")

        with pytest.raises(ValueError, match="field_name.*None"):
            registry.add_custom_field(None)

    def test_add_custom_field_duplicate_prevention(self):
        """Test add_custom_field prevents duplicate additions"""
        registry = TracingFieldRegistry()

        registry.add_custom_field("duplicate_field")
        # Adding again should not raise error but also not duplicate
        registry.add_custom_field("duplicate_field")

        # Should only appear once
        custom_fields_list = list(registry.custom_fields)
        assert custom_fields_list.count("duplicate_field") == 1

    def test_add_custom_field_name_format_validation(self):
        """Test add_custom_field validates field name format"""
        registry = TracingFieldRegistry()

        # Valid field names should work
        registry.add_custom_field("valid_field")
        registry.add_custom_field("trace_123")
        registry.add_custom_field("span-id")

        # Invalid field names should fail
        with pytest.raises(ValueError, match="invalid.*format"):
            registry.add_custom_field("invalid field with spaces")

        with pytest.raises(ValueError, match="invalid.*format"):
            registry.add_custom_field("invalid@field")

    def test_remove_custom_field_valid(self):
        """Test removing custom field from exemption list"""
        registry = TracingFieldRegistry()

        registry.add_custom_field("removable_field")
        assert "removable_field" in registry.custom_fields

        registry.remove_custom_field("removable_field")
        assert "removable_field" not in registry.custom_fields
        assert registry.is_tracing_field("removable_field") is False

    def test_remove_custom_field_not_affect_builtin(self):
        """Test remove_custom_field does not affect built-in fields"""
        registry = TracingFieldRegistry()

        # Try to remove built-in field - should not work
        with pytest.raises(ValueError, match="cannot remove.*built-in"):
            registry.remove_custom_field("correlation_id")

        # Built-in field should still be there
        assert registry.is_tracing_field("correlation_id") is True

    def test_remove_custom_field_nonexistent_graceful(self):
        """Test remove_custom_field handles non-existent field gracefully"""
        registry = TracingFieldRegistry()

        # Should not raise error for non-existent field
        registry.remove_custom_field("nonexistent_field")

    def test_tracing_registry_immutable_defaults(self):
        """Test that default fields and patterns cannot be modified externally"""
        registry = TracingFieldRegistry()

        original_defaults = registry.default_fields.copy()

        # Try to modify the returned set
        returned_fields = registry.default_fields
        returned_fields.add("malicious_field")

        # Original should be unchanged
        assert registry.default_fields == original_defaults
        assert "malicious_field" not in registry.default_fields
