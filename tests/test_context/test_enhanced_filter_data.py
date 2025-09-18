"""
T011: Test SensitiveDataFilter.filter_data() enhanced method
These tests MUST FAIL initially (TDD approach)
"""

from mohflow.context.filters import SensitiveDataFilter, FilterResult


class TestEnhancedFilterData:
    """Test enhanced SensitiveDataFilter.filter_data() method from contract"""

    def test_filter_data_preserve_tracing_fields_enabled(self):
        """Test filter_data preserves tracing fields when exclude_tracing_fields=True"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        test_data = {
            "correlation_id": "req-123",
            "trace_id": "trace-456",
            "span_id": "span-789",
            "api_key": "secret-key-123",
            "password": "user-password",
            "user_id": "user-456",
        }

        result = filter_obj.filter_data_with_audit(test_data)

        # Assert return type
        assert isinstance(result, FilterResult)

        # Tracing fields should be preserved
        assert result.filtered_data["correlation_id"] == "req-123"
        assert result.filtered_data["trace_id"] == "trace-456"
        assert result.filtered_data["span_id"] == "span-789"

        # Sensitive fields should be redacted
        assert result.filtered_data["api_key"] == "[REDACTED]"
        assert result.filtered_data["password"] == "[REDACTED]"

        # Neutral fields should be preserved
        assert result.filtered_data["user_id"] == "user-456"

        # Audit information should be correct
        assert "correlation_id" in result.preserved_fields
        assert "trace_id" in result.preserved_fields
        assert "span_id" in result.preserved_fields
        assert "api_key" in result.redacted_fields
        assert "password" in result.redacted_fields

    def test_filter_data_redact_sensitive_regardless_of_tracing(self):
        """Test filter_data redacts sensitive fields regardless of tracing settings"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        test_data = {
            "correlation_id": "req-123",  # Should be preserved
            "api_key": "secret-123",  # Should be redacted
            "trace_password": "secret",  # Should be redacted even with "trace" in name
            "secret_trace_id": "secret",  # Should be redacted - sensitive takes priority
        }

        result = filter_obj.filter_data_with_audit(test_data)

        # Tracing field preserved
        assert result.filtered_data["correlation_id"] == "req-123"
        assert "correlation_id" in result.preserved_fields

        # Sensitive fields redacted
        assert result.filtered_data["api_key"] == "[REDACTED]"
        assert result.filtered_data["trace_password"] == "[REDACTED]"
        assert result.filtered_data["secret_trace_id"] == "[REDACTED]"

    def test_filter_data_nested_data_structures(self):
        """Test filter_data handles nested data structures correctly"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        test_data = {
            "request": {
                "correlation_id": "req-123",
                "headers": {
                    "authorization": "Bearer token123",
                    "x-trace-id": "trace-456",
                },
            },
            "response": {
                "data": ["trace_id", "secret_data"],
                "metadata": {"span_id": "span-789", "api_key": "secret-key"},
            },
        }

        result = filter_obj.filter_data_with_audit(test_data)

        # Nested tracing fields preserved
        assert result.filtered_data["request"]["correlation_id"] == "req-123"
        assert (
            result.filtered_data["request"]["headers"]["x-trace-id"]
            == "trace-456"
        )
        assert (
            result.filtered_data["response"]["metadata"]["span_id"]
            == "span-789"
        )

        # Nested sensitive fields redacted
        assert (
            result.filtered_data["request"]["headers"]["authorization"]
            == "[REDACTED]"
        )
        assert (
            result.filtered_data["response"]["metadata"]["api_key"]
            == "[REDACTED]"
        )

        # Audit should track nested paths
        assert "request.correlation_id" in result.preserved_fields
        assert "request.headers.authorization" in result.redacted_fields

    def test_filter_data_processing_time_tracking(self):
        """Test filter_data tracks processing time accurately"""
        filter_obj = SensitiveDataFilter()

        test_data = {"key": "value"}

        result = filter_obj.filter_data_with_audit(test_data)

        # Should have measured processing time
        assert result.processing_time >= 0
        assert result.processing_time < 1.0  # Should be fast

        # Processing time should be reasonable for small data
        assert result.processing_time < 0.01  # Less than 10ms

    def test_filter_data_backward_compatibility_existing_behavior(self):
        """Test filter_data maintains existing behavior when tracing disabled"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=False)

        test_data = {
            "correlation_id": "req-123",
            "api_key": "secret-123",
            "user_id": "user-456",
        }

        result = filter_obj.filter_data_with_audit(test_data)

        # With tracing disabled, correlation_id should be treated normally
        # (not redacted unless it matches sensitive patterns)
        assert result.filtered_data["correlation_id"] == "req-123"
        assert result.filtered_data["api_key"] == "[REDACTED]"
        assert result.filtered_data["user_id"] == "user-456"

    def test_filter_data_custom_safe_fields(self):
        """Test filter_data works with custom safe fields"""
        custom_safe_fields = {"custom_trace_id", "app_correlation_id"}
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, custom_safe_fields=custom_safe_fields
        )

        test_data = {
            "custom_trace_id": "custom-123",
            "app_correlation_id": "app-456",
            "api_key": "secret-789",
        }

        result = filter_obj.filter_data_with_audit(test_data)

        # Custom safe fields preserved
        assert result.filtered_data["custom_trace_id"] == "custom-123"
        assert result.filtered_data["app_correlation_id"] == "app-456"
        assert "custom_trace_id" in result.preserved_fields
        assert "app_correlation_id" in result.preserved_fields

        # Sensitive field redacted
        assert result.filtered_data["api_key"] == "[REDACTED]"
        assert "api_key" in result.redacted_fields

    def test_filter_data_edge_cases_none_empty(self):
        """Test filter_data handles edge cases gracefully"""
        filter_obj = SensitiveDataFilter()

        # None input
        result_none = filter_obj.filter_data_with_audit(None)
        assert result_none.filtered_data is None
        assert result_none.redacted_fields == []
        assert result_none.preserved_fields == []

        # Empty dict
        result_empty = filter_obj.filter_data_with_audit({})
        assert result_empty.filtered_data == {}
        assert result_empty.redacted_fields == []
        assert result_empty.preserved_fields == []

        # Empty list
        result_list = filter_obj.filter_data_with_audit([])
        assert result_list.filtered_data == []

    def test_filter_data_complex_data_types(self):
        """Test filter_data handles various data types"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        test_data = {
            "string_field": "value",
            "int_field": 123,
            "float_field": 45.67,
            "bool_field": True,
            "null_field": None,
            "list_field": ["item1", "item2"],
            "dict_field": {"nested": "value"},
            "correlation_id": "req-123",
            "api_key": "secret",
        }

        result = filter_obj.filter_data_with_audit(test_data)

        # Non-string fields should be preserved as-is
        assert result.filtered_data["int_field"] == 123
        assert result.filtered_data["float_field"] == 45.67
        assert result.filtered_data["bool_field"] is True
        assert result.filtered_data["null_field"] is None

        # Complex types should be processed recursively
        assert result.filtered_data["list_field"] == ["item1", "item2"]
        assert result.filtered_data["dict_field"] == {"nested": "value"}

        # String fields should follow filtering rules
        assert result.filtered_data["correlation_id"] == "req-123"
        assert result.filtered_data["api_key"] == "[REDACTED]"

    def test_filter_data_performance_large_data(self):
        """Test filter_data performance with larger data structures"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        # Create large test data
        large_data = {}
        for i in range(1000):
            large_data[f"field_{i}"] = f"value_{i}"
            if i % 10 == 0:
                large_data[f"trace_id_{i}"] = f"trace_{i}"
            if i % 15 == 0:
                large_data[f"api_key_{i}"] = f"secret_{i}"

        import time

        start_time = time.time()
        result = filter_obj.filter_data_with_audit(large_data)
        end_time = time.time()

        # Should complete within reasonable time (allow generous threshold for CI)
        assert (
            end_time - start_time
        ) < 0.5  # Less than 500ms (generous for CI)

        # Should have processed and classified special fields
        # Expected: ~100 trace_id fields preserved + ~67 api_key fields redacted
        total_special_fields = len(result.preserved_fields) + len(
            result.redacted_fields
        )
        assert (
            total_special_fields > 100
        )  # Should have classified the special fields
        assert (
            len(result.preserved_fields) > 0
        )  # Should have some tracing fields
        assert (
            len(result.redacted_fields) > 0
        )  # Should have some sensitive fields

    def test_filter_data_circular_reference_handling(self):
        """Test filter_data handles circular references gracefully"""
        filter_obj = SensitiveDataFilter()

        # Create circular reference
        data_a = {"name": "A", "correlation_id": "req-123"}
        data_b = {"name": "B", "api_key": "secret"}
        data_a["ref"] = data_b
        data_b["ref"] = data_a

        # Should not crash with circular reference
        result = filter_obj.filter_data_with_audit(data_a)

        # Should have processed the data (may truncate circular parts)
        assert isinstance(result, FilterResult)
        assert result.filtered_data is not None
