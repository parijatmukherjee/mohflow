"""
T005: Test FieldClassification enum and validation
These tests MUST FAIL initially (TDD approach)
"""

import pytest
from mohflow.context.filters import FieldClassification, FieldType


class TestFieldClassification:
    """Test FieldClassification entity from data model"""

    def test_field_classification_initialization_valid(self):
        """Test FieldClassification with valid parameters"""
        classification = FieldClassification(
            field_name="correlation_id",
            classification=FieldType.TRACING,
            matched_pattern="correlation_.*",
            exempted=True,
        )

        assert classification.field_name == "correlation_id"
        assert classification.classification == FieldType.TRACING
        assert classification.matched_pattern == "correlation_.*"
        assert classification.exempted is True

    def test_field_classification_initialization_minimal(self):
        """Test FieldClassification with minimal parameters"""
        classification = FieldClassification(
            field_name="user_id", classification=FieldType.NEUTRAL
        )

        assert classification.field_name == "user_id"
        assert classification.classification == FieldType.NEUTRAL
        assert classification.matched_pattern is None
        assert classification.exempted is False

    def test_field_classification_validation_field_name_not_none(self):
        """Test field_name must not be None"""
        with pytest.raises(ValueError, match="field_name must not be None"):
            FieldClassification(
                field_name=None, classification=FieldType.NEUTRAL
            )

    def test_field_classification_validation_field_name_not_empty(self):
        """Test field_name must not be empty"""
        with pytest.raises(ValueError, match="field_name must not be empty"):
            FieldClassification(
                field_name="", classification=FieldType.NEUTRAL
            )

    def test_field_classification_validation_invalid_classification_type(self):
        """Test classification must be valid FieldType enum"""
        with pytest.raises(ValueError, match="must be valid FieldType"):
            FieldClassification(
                field_name="test_field", classification="invalid_type"
            )

    def test_field_classification_validation_exempted_only_for_tracing(self):
        """Test exempted=True only allowed for TRACING fields"""
        # This should work - TRACING field can be exempted
        FieldClassification(
            field_name="trace_id",
            classification=FieldType.TRACING,
            exempted=True,
        )

        # This should fail - SENSITIVE field cannot be exempted
        with pytest.raises(ValueError, match="exempted.*only.*TRACING"):
            FieldClassification(
                field_name="api_key",
                classification=FieldType.SENSITIVE,
                exempted=True,
            )

        # This should fail - NEUTRAL field cannot be exempted
        with pytest.raises(ValueError, match="exempted.*only.*TRACING"):
            FieldClassification(
                field_name="user_id",
                classification=FieldType.NEUTRAL,
                exempted=True,
            )

    def test_field_classification_validation_matched_pattern_valid_regex(self):
        """Test matched_pattern must be valid regex if provided"""
        # Valid regex should work
        FieldClassification(
            field_name="test_field",
            classification=FieldType.TRACING,
            matched_pattern="trace_.*",
        )

        # Invalid regex should fail
        with pytest.raises(ValueError, match="matched_pattern.*valid regex"):
            FieldClassification(
                field_name="test_field",
                classification=FieldType.TRACING,
                matched_pattern="[invalid",
            )

    def test_field_type_enum_values(self):
        """Test FieldType enum has expected values"""
        assert FieldType.TRACING.value == "tracing"
        assert FieldType.SENSITIVE.value == "sensitive"
        assert FieldType.NEUTRAL.value == "neutral"

    def test_field_classification_string_representation(self):
        """Test string representation of FieldClassification"""
        classification = FieldClassification(
            field_name="correlation_id",
            classification=FieldType.TRACING,
            exempted=True,
        )

        str_repr = str(classification)
        assert "correlation_id" in str_repr
        assert "TRACING" in str_repr
        assert "exempted=True" in str_repr

    def test_field_classification_equality(self):
        """Test FieldClassification equality comparison"""
        classification1 = FieldClassification(
            field_name="trace_id", classification=FieldType.TRACING
        )

        classification2 = FieldClassification(
            field_name="trace_id", classification=FieldType.TRACING
        )

        classification3 = FieldClassification(
            field_name="span_id", classification=FieldType.TRACING
        )

        assert classification1 == classification2
        assert classification1 != classification3
