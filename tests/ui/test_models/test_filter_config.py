"""
Unit tests for FilterConfiguration parsing.

These tests MUST FAIL initially until the types.py implementation is complete.
"""

import pytest
from datetime import datetime
from mohflow.devui.types import FilterConfiguration


class TestFilterConfiguration:
    """Test FilterConfiguration parsing and validation."""

    def test_filter_configuration_basic(self):
        """Test basic filter configuration."""
        filter_config = FilterConfiguration(
            name="Error Logs",
            levels=["ERROR", "CRITICAL"],
            services=["api", "auth"],
        )

        assert filter_config.name == "Error Logs"
        assert filter_config.levels == ["ERROR", "CRITICAL"]
        assert filter_config.services == ["api", "auth"]

    def test_filter_configuration_mql_parsing(self):
        """Test MQL query parsing."""
        filter_config = FilterConfiguration(
            name="Complex Filter",
            query_expression="level:ERROR AND service:api",
        )

        # Should parse MQL expression
        parsed = filter_config.parse_mql()
        assert isinstance(parsed, dict)

    def test_filter_configuration_time_range_validation(self):
        """Test time range validation."""
        valid_ranges = ["5m", "15m", "1h", "24h"]

        for time_range in valid_ranges:
            filter_config = FilterConfiguration(
                name="Time Filter", time_range=time_range
            )
            assert filter_config.time_range == time_range

        # Invalid time ranges should fail
        with pytest.raises((ValueError, TypeError)):
            FilterConfiguration(name="Invalid Filter", time_range="invalid")
