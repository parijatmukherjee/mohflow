"""
T007: Test FilterResult audit information
These tests MUST FAIL initially (TDD approach)
"""

import pytest
from mohflow.context.filters import FilterResult


class TestFilterResult:
    """Test FilterResult entity from data model"""

    def test_filter_result_initialization_valid(self):
        """Test FilterResult with valid parameters"""
        filtered_data = {"correlation_id": "req-123", "api_key": "[REDACTED]"}
        redacted_fields = ["api_key", "password"]
        preserved_fields = ["correlation_id", "trace_id"]
        processing_time = 0.002

        result = FilterResult(
            filtered_data=filtered_data,
            redacted_fields=redacted_fields,
            preserved_fields=preserved_fields,
            processing_time=processing_time,
        )

        assert result.filtered_data == filtered_data
        assert result.redacted_fields == redacted_fields
        assert result.preserved_fields == preserved_fields
        assert result.processing_time == processing_time

    def test_filter_result_initialization_empty_lists(self):
        """Test FilterResult with empty field lists"""
        result = FilterResult(
            filtered_data={},
            redacted_fields=[],
            preserved_fields=[],
            processing_time=0.0,
        )

        assert result.filtered_data == {}
        assert result.redacted_fields == []
        assert result.preserved_fields == []
        assert result.processing_time == 0.0

    def test_filter_result_validation_no_overlap_redacted_preserved(self):
        """Test redacted_fields and preserved_fields don't overlap"""
        with pytest.raises(
            ValueError, match="redacted_fields.*preserved_fields.*overlap"
        ):
            FilterResult(
                filtered_data={},
                redacted_fields=["api_key", "correlation_id"],
                preserved_fields=[
                    "correlation_id",
                    "trace_id",
                ],  # correlation_id overlaps
                processing_time=0.001,
            )

    def test_filter_result_validation_processing_time_non_negative(self):
        """Test processing_time must be non-negative"""
        # Positive time should work
        FilterResult(
            filtered_data={},
            redacted_fields=[],
            preserved_fields=[],
            processing_time=0.001,
        )

        # Zero time should work
        FilterResult(
            filtered_data={},
            redacted_fields=[],
            preserved_fields=[],
            processing_time=0.0,
        )

        # Negative time should fail
        with pytest.raises(ValueError, match="processing_time.*non-negative"):
            FilterResult(
                filtered_data={},
                redacted_fields=[],
                preserved_fields=[],
                processing_time=-0.001,
            )

    def test_filter_result_validation_none_filtered_data(self):
        """Test FilterResult handles None filtered_data appropriately"""
        result = FilterResult(
            filtered_data=None,
            redacted_fields=[],
            preserved_fields=[],
            processing_time=0.0,
        )

        assert result.filtered_data is None

    def test_filter_result_validation_field_lists_contain_strings(self):
        """Test field lists contain only strings"""
        # Valid string lists should work
        FilterResult(
            filtered_data={},
            redacted_fields=["api_key", "password"],
            preserved_fields=["correlation_id"],
            processing_time=0.0,
        )

        # Non-string in redacted_fields should fail
        with pytest.raises(
            TypeError, match="redacted_fields.*contain.*strings"
        ):
            FilterResult(
                filtered_data={},
                redacted_fields=["api_key", 123],
                preserved_fields=[],
                processing_time=0.0,
            )

        # Non-string in preserved_fields should fail
        with pytest.raises(
            TypeError, match="preserved_fields.*contain.*strings"
        ):
            FilterResult(
                filtered_data={},
                redacted_fields=[],
                preserved_fields=["correlation_id", None],
                processing_time=0.0,
            )

    def test_filter_result_audit_summary(self):
        """Test FilterResult provides audit summary"""
        result = FilterResult(
            filtered_data={"trace_id": "123", "api_key": "[REDACTED]"},
            redacted_fields=["api_key", "password"],
            preserved_fields=["trace_id", "correlation_id"],
            processing_time=0.003,
        )

        summary = result.get_audit_summary()

        assert "redacted" in summary
        assert "preserved" in summary
        assert "processing_time" in summary
        assert "2 redacted" in summary
        assert "2 preserved" in summary

    def test_filter_result_performance_metrics(self):
        """Test FilterResult tracks performance metrics"""
        result = FilterResult(
            filtered_data={},
            redacted_fields=["field1", "field2", "field3"],
            preserved_fields=["field4", "field5"],
            processing_time=0.005,
        )

        metrics = result.get_performance_metrics()

        assert metrics["fields_processed"] == 5  # 3 redacted + 2 preserved
        assert metrics["redaction_rate"] == 0.6  # 3/5
        assert metrics["processing_time"] == 0.005
        assert metrics["fields_per_second"] == 1000  # 5 fields / 0.005 seconds

    def test_filter_result_equality(self):
        """Test FilterResult equality comparison"""
        result1 = FilterResult(
            filtered_data={"key": "value"},
            redacted_fields=["api_key"],
            preserved_fields=["trace_id"],
            processing_time=0.001,
        )

        result2 = FilterResult(
            filtered_data={"key": "value"},
            redacted_fields=["api_key"],
            preserved_fields=["trace_id"],
            processing_time=0.001,
        )

        result3 = FilterResult(
            filtered_data={"key": "different"},
            redacted_fields=["api_key"],
            preserved_fields=["trace_id"],
            processing_time=0.001,
        )

        assert result1 == result2
        assert result1 != result3

    def test_filter_result_string_representation(self):
        """Test FilterResult string representation"""
        result = FilterResult(
            filtered_data={"trace_id": "123"},
            redacted_fields=["api_key"],
            preserved_fields=["trace_id"],
            processing_time=0.002,
        )

        str_repr = str(result)
        assert "1 redacted" in str_repr
        assert "1 preserved" in str_repr
        assert "0.002" in str_repr

    def test_filter_result_nested_data_handling(self):
        """Test FilterResult with nested data structures"""
        nested_data = {
            "user": {"correlation_id": "req-123", "credentials": "[REDACTED]"},
            "request": ["trace_id", "[REDACTED]"],
        }

        result = FilterResult(
            filtered_data=nested_data,
            redacted_fields=["user.credentials", "request[1]"],
            preserved_fields=["user.correlation_id", "request[0]"],
            processing_time=0.004,
        )

        assert result.filtered_data == nested_data
        assert "user.credentials" in result.redacted_fields
        assert "user.correlation_id" in result.preserved_fields
