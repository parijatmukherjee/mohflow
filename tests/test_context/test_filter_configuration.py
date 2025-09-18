"""
T004: Test FilterConfiguration initialization and validation
These tests MUST FAIL initially (TDD approach)
"""

import pytest
from mohflow.context.filters import FilterConfiguration


class TestFilterConfiguration:
    """Test FilterConfiguration entity from data model"""

    def test_filter_configuration_initialization_defaults(self):
        """Test FilterConfiguration with default parameters"""
        config = FilterConfiguration()

        assert config.enabled is True
        assert config.exclude_tracing_fields is True
        assert config.custom_safe_fields == set()
        assert config.tracing_field_patterns == []
        assert config.sensitive_fields is not None
        assert config.sensitive_patterns is not None
        assert config.case_sensitive is False

    def test_filter_configuration_initialization_custom(self):
        """Test FilterConfiguration with custom parameters"""
        custom_safe_fields = {"custom_trace_id", "custom_span_id"}
        custom_patterns = ["custom_.*_id$", "^custom_trace_.*"]

        config = FilterConfiguration(
            enabled=False,
            exclude_tracing_fields=False,
            custom_safe_fields=custom_safe_fields,
            tracing_field_patterns=custom_patterns,
            case_sensitive=True,
        )

        assert config.enabled is False
        assert config.exclude_tracing_fields is False
        assert config.custom_safe_fields == custom_safe_fields
        assert config.tracing_field_patterns == custom_patterns
        assert config.case_sensitive is True

    def test_filter_configuration_validation_enabled_type(self):
        """Test that enabled must be boolean"""
        with pytest.raises(TypeError, match="enabled must be boolean"):
            FilterConfiguration(enabled="true")

    def test_filter_configuration_validation_empty_safe_fields(self):
        """Test that custom_safe_fields cannot contain empty strings"""
        with pytest.raises(ValueError, match="must not contain empty strings"):
            FilterConfiguration(custom_safe_fields={"valid_field", ""})

    def test_filter_configuration_validation_invalid_regex_patterns(self):
        """Test that tracing_field_patterns must be valid regex"""
        with pytest.raises(ValueError, match="invalid regex pattern"):
            FilterConfiguration(
                tracing_field_patterns=["valid_pattern", "[invalid"]
            )

    def test_filter_configuration_validation_no_overlap(self):
        """Test sensitive fields cannot overlap with tracing fields when exemptions enabled"""
        config = FilterConfiguration(
            exclude_tracing_fields=True,
            custom_safe_fields={
                "correlation_id"
            },  # This is a built-in tracing field
            sensitive_fields={"correlation_id"},  # Should conflict
        )

        with pytest.raises(ValueError, match="overlap.*tracing.*sensitive"):
            config.validate()

    def test_filter_configuration_runtime_modification(self):
        """Test configuration can be modified at runtime"""
        config = FilterConfiguration()

        # Test adding safe field
        config.add_safe_field("new_trace_field")
        assert "new_trace_field" in config.custom_safe_fields

        # Test removing safe field
        config.remove_safe_field("new_trace_field")
        assert "new_trace_field" not in config.custom_safe_fields

    def test_filter_configuration_pattern_compilation(self):
        """Test regex patterns are compiled during initialization"""
        patterns = ["trace_.*", "span_.*"]
        config = FilterConfiguration(tracing_field_patterns=patterns)

        # Should have compiled patterns available
        assert hasattr(config, "_compiled_patterns")
        assert len(config._compiled_patterns) == len(patterns)

    def test_filter_configuration_field_lookup_sets_rebuilt(self):
        """Test field lookup sets are rebuilt when fields added/removed"""
        config = FilterConfiguration(case_sensitive=False)

        # Add field should rebuild lookup sets
        config.add_safe_field("TEST_FIELD")
        assert "test_field" in config._safe_fields_lower

        # Remove field should rebuild lookup sets
        config.remove_safe_field("TEST_FIELD")
        assert "test_field" not in config._safe_fields_lower
