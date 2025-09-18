"""
T009: Test SensitiveDataFilter.is_tracing_field() method
These tests MUST FAIL initially (TDD approach)
"""

from mohflow.context.filters import SensitiveDataFilter


class TestIsTracingField:
    """Test SensitiveDataFilter.is_tracing_field() method from contract"""

    def test_is_tracing_field_builtin_fields_enabled(self):
        """Test is_tracing_field returns True for built-in tracing fields when enabled"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        builtin_fields = [
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
        ]

        for field in builtin_fields:
            assert filter_obj.is_tracing_field(field) is True

    def test_is_tracing_field_builtin_fields_disabled(self):
        """Test is_tracing_field returns False when exclude_tracing_fields=False"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=False)

        builtin_fields = [
            "correlation_id",
            "request_id",
            "trace_id",
            "span_id",
        ]

        for field in builtin_fields:
            assert filter_obj.is_tracing_field(field) is False

    def test_is_tracing_field_custom_safe_fields(self):
        """Test is_tracing_field returns True for custom safe fields"""
        custom_safe_fields = {
            "custom_trace_id",
            "app_span_id",
            "service_correlation",
        }
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, custom_safe_fields=custom_safe_fields
        )

        for field in custom_safe_fields:
            assert filter_obj.is_tracing_field(field) is True

        # Non-custom field should still work if it's built-in
        assert filter_obj.is_tracing_field("correlation_id") is True

        # Non-safe field should return False
        assert filter_obj.is_tracing_field("api_key") is False

    def test_is_tracing_field_pattern_matching(self):
        """Test is_tracing_field returns True for fields matching tracing patterns"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True,
            tracing_field_patterns=[
                r"^trace_.*",
                r".*_trace_id$",
                r"^request_.*",
            ],
        )

        # Should match patterns
        pattern_matches = [
            "trace_operation",
            "trace_123",
            "service_trace_id",
            "custom_trace_id",
            "request_handler",
            "request_uuid",
        ]

        for field in pattern_matches:
            assert filter_obj.is_tracing_field(field) is True

        # Should not match patterns
        non_matches = [
            "operation_trace",  # doesn't start with trace_ or end with _trace_id
            "user_id",  # doesn't match any pattern
            "api_key",  # sensitive field
        ]

        for field in non_matches:
            assert filter_obj.is_tracing_field(field) is False

    def test_is_tracing_field_edge_cases_none_empty(self):
        """Test is_tracing_field handles None/empty input gracefully"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        # None input
        assert filter_obj.is_tracing_field(None) is False

        # Empty string
        assert filter_obj.is_tracing_field("") is False

        # Whitespace only
        assert filter_obj.is_tracing_field("   ") is False
        assert filter_obj.is_tracing_field("\t\n") is False

    def test_is_tracing_field_edge_cases_malformed(self):
        """Test is_tracing_field handles malformed input gracefully"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        malformed_inputs = [
            123,  # integer
            [],  # list
            {},  # dict
            True,  # boolean
            0.5,  # float
        ]

        for malformed_input in malformed_inputs:
            # Should handle gracefully, not crash
            result = filter_obj.is_tracing_field(malformed_input)
            assert isinstance(result, bool)
            assert result is False

    def test_is_tracing_field_case_sensitivity_disabled(self):
        """Test is_tracing_field case insensitive matching when case_sensitive=False"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, case_sensitive=False
        )

        # Should match regardless of case
        case_variations = [
            ("correlation_id", True),
            ("CORRELATION_ID", True),
            ("Correlation_Id", True),
            ("TRACE_ID", True),
            ("trace_id", True),
            ("Request_ID", True),
        ]

        for field, expected in case_variations:
            assert filter_obj.is_tracing_field(field) is expected

    def test_is_tracing_field_case_sensitivity_enabled(self):
        """Test is_tracing_field case sensitive matching when case_sensitive=True"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, case_sensitive=True
        )

        # Should only match exact case
        case_variations = [
            ("correlation_id", True),  # exact match
            ("CORRELATION_ID", False),  # wrong case
            ("Correlation_Id", False),  # wrong case
            ("trace_id", True),  # exact match
            ("TRACE_ID", False),  # wrong case
        ]

        for field, expected in case_variations:
            assert filter_obj.is_tracing_field(field) is expected

    def test_is_tracing_field_pattern_compilation_error_handling(self):
        """Test is_tracing_field handles regex compilation errors gracefully"""
        # This should not crash during initialization or usage
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True,
            tracing_field_patterns=[
                r"valid_pattern_.*",
                r"[invalid_pattern",  # Invalid regex
            ],
        )

        # Should handle gracefully - either compile valid patterns only
        # or fall back to string matching
        result = filter_obj.is_tracing_field("valid_pattern_test")
        assert isinstance(result, bool)

    def test_is_tracing_field_performance_optimization(self):
        """Test is_tracing_field performance with lookups"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        import time

        # Test that field lookup is fast (should use set lookup, not linear search)
        start_time = time.time()
        for _ in range(1000):
            filter_obj.is_tracing_field("correlation_id")
        end_time = time.time()

        # Should be very fast - less than 5ms for 1000 lookups
        assert (end_time - start_time) < 0.005

    def test_is_tracing_field_priority_over_sensitive(self):
        """Test is_tracing_field takes priority over sensitive field detection"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True,
            custom_safe_fields={
                "auth_trace_id"
            },  # Contains "auth" but should be safe
        )

        # Should return True for tracing field even if it contains sensitive pattern
        assert filter_obj.is_tracing_field("auth_trace_id") is True

        # Regular sensitive field should return False
        assert filter_obj.is_tracing_field("api_key") is False

    def test_is_tracing_field_dynamic_modification(self):
        """Test is_tracing_field works with dynamically added/removed fields"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        # Initially not a tracing field
        assert filter_obj.is_tracing_field("dynamic_field") is False

        # Add as safe field dynamically
        filter_obj.add_safe_field("dynamic_field")
        assert filter_obj.is_tracing_field("dynamic_field") is True

        # Remove safe field dynamically
        filter_obj.remove_safe_field("dynamic_field")
        assert filter_obj.is_tracing_field("dynamic_field") is False
