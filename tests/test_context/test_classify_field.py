"""
T008: Test SensitiveDataFilter.classify_field() method
These tests MUST FAIL initially (TDD approach)
"""

from mohflow.context.filters import (
    SensitiveDataFilter,
    FieldType,
)


class TestClassifyField:
    """Test SensitiveDataFilter.classify_field() method from contract"""

    def test_classify_field_tracing_fields_when_enabled(self):
        """Test classify_field returns TRACING for tracing fields when exclude_tracing_fields=True"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        tracing_fields = [
            "correlation_id",
            "request_id",
            "trace_id",
            "span_id",
            "transaction_id",
            "session_id",
            "operation_id",
        ]

        for field in tracing_fields:
            classification = filter_obj.classify_field(field)
            assert classification.classification == FieldType.TRACING
            assert classification.exempted is True
            assert classification.field_name == field

    def test_classify_field_sensitive_fields(self):
        """Test classify_field returns SENSITIVE for sensitive fields"""
        filter_obj = SensitiveDataFilter()

        sensitive_fields = [
            "api_key",
            "password",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "private_key",
            "jwt",
        ]

        for field in sensitive_fields:
            classification = filter_obj.classify_field(field)
            assert classification.classification == FieldType.SENSITIVE
            assert classification.exempted is False
            assert classification.field_name == field

    def test_classify_field_neutral_fields(self):
        """Test classify_field returns NEUTRAL for unknown fields"""
        filter_obj = SensitiveDataFilter()

        neutral_fields = [
            "user_id",
            "email",
            "name",
            "address",
            "phone_number",
            "timestamp",
            "status",
        ]

        for field in neutral_fields:
            classification = filter_obj.classify_field(field)
            assert classification.classification == FieldType.NEUTRAL
            assert classification.exempted is False
            assert classification.field_name == field

    def test_classify_field_tracing_disabled(self):
        """Test classify_field when exclude_tracing_fields=False"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=False)

        # Even tracing fields should not be classified as TRACING when disabled
        classification = filter_obj.classify_field("correlation_id")
        assert classification.classification != FieldType.TRACING
        assert classification.exempted is False

    def test_classify_field_custom_safe_fields(self):
        """Test classify_field with custom safe fields"""
        custom_safe_fields = {"custom_trace_id", "custom_span_id"}
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, custom_safe_fields=custom_safe_fields
        )

        for field in custom_safe_fields:
            classification = filter_obj.classify_field(field)
            assert classification.classification == FieldType.TRACING
            assert classification.exempted is True

    def test_classify_field_pattern_matching(self):
        """Test classify_field with tracing patterns"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True,
            tracing_field_patterns=[r".*_trace_id$", r"^custom_.*"],
        )

        # Should match patterns
        test_cases = [
            ("service_trace_id", FieldType.TRACING),
            ("custom_field", FieldType.TRACING),
            ("custom_trace_field", FieldType.TRACING),
        ]

        for field_name, expected_type in test_cases:
            classification = filter_obj.classify_field(field_name)
            assert classification.classification == expected_type
            assert classification.matched_pattern is not None
            if expected_type == FieldType.TRACING:
                assert classification.exempted is True

    def test_classify_field_case_sensitivity_disabled(self):
        """Test classify_field respects case sensitivity settings when disabled"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, case_sensitive=False
        )

        # Should classify regardless of case
        test_cases = [
            "CORRELATION_ID",
            "Trace_Id",
            "REQUEST_id",
            "API_KEY",
            "Password",
            "SECRET",
        ]

        for field in test_cases:
            classification = filter_obj.classify_field(field)
            # Should get classified based on lowercase match
            assert classification.classification in [
                FieldType.TRACING,
                FieldType.SENSITIVE,
            ]

    def test_classify_field_case_sensitivity_enabled(self):
        """Test classify_field respects case sensitivity when enabled"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True, case_sensitive=True
        )

        # Should only match exact case
        classification_lower = filter_obj.classify_field("correlation_id")
        assert classification_lower.classification == FieldType.TRACING

        classification_upper = filter_obj.classify_field("CORRELATION_ID")
        assert (
            classification_upper.classification == FieldType.NEUTRAL
        )  # No match

    def test_classify_field_none_empty_input(self):
        """Test classify_field handles None/empty input gracefully"""
        filter_obj = SensitiveDataFilter()

        # None input
        classification = filter_obj.classify_field(None)
        assert classification.classification == FieldType.NEUTRAL
        assert classification.field_name is None

        # Empty string input
        classification = filter_obj.classify_field("")
        assert classification.classification == FieldType.NEUTRAL
        assert classification.field_name == ""

        # Whitespace only
        classification = filter_obj.classify_field("   ")
        assert classification.classification == FieldType.NEUTRAL

    def test_classify_field_priority_order(self):
        """Test classify_field applies correct priority order"""
        # Tracing exemptions should take priority over sensitive patterns
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True,
            custom_safe_fields={
                "auth_trace_id"
            },  # Contains "auth" but is safe
        )

        classification = filter_obj.classify_field("auth_trace_id")
        # Should be TRACING (safe) not SENSITIVE despite containing "auth"
        assert classification.classification == FieldType.TRACING
        assert classification.exempted is True

    def test_classify_field_complex_patterns(self):
        """Test classify_field with complex regex patterns"""
        filter_obj = SensitiveDataFilter(
            exclude_tracing_fields=True,
            tracing_field_patterns=[
                r"^(trace|span|request)_\w+_id$",  # prefix_*_id
                r".*_(trace|span)_.*",  # *_trace_* or *_span_*
            ],
        )

        test_cases = [
            ("trace_operation_id", FieldType.TRACING),
            ("span_service_id", FieldType.TRACING),
            ("request_handler_id", FieldType.TRACING),
            ("service_trace_context", FieldType.TRACING),
            ("operation_span_data", FieldType.TRACING),
            ("user_profile_id", FieldType.NEUTRAL),  # Should not match
        ]

        for field_name, expected_type in test_cases:
            classification = filter_obj.classify_field(field_name)
            assert classification.classification == expected_type

    def test_classify_field_performance(self):
        """Test classify_field performance characteristics"""
        filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)

        import time

        # Run multiple trials to account for system variability
        trials = []
        for _ in range(3):
            start_time = time.perf_counter()
            for _ in range(1000):
                filter_obj.classify_field("correlation_id")
            end_time = time.perf_counter()
            trials.append(end_time - start_time)

        # Use median to be more robust against outliers
        median_time = sorted(trials)[1]

        # Should be very fast - less than 100ms for 1000 classifications
        # (allows for CI environment variability while maintaining performance)
        # Performance target: ~10μs per operation, allowing for CI overhead
        assert median_time < 0.1, f"Performance test failed: median {median_time:.3f}s > 0.1s"
