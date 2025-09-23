"""
Test datetime handling and LogEvent serialization.
"""

import pytest
import logging
from datetime import datetime, timezone


class TestDatetimeHandling:
    """Test datetime handling and serialization issues."""

    def test_log_record_timestamp_conversion(self):
        """Test LogRecord timestamp conversion to datetime."""
        # Create a mock LogRecord
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=123,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Test timestamp conversion
        assert isinstance(record.created, float)

        timestamp = datetime.fromtimestamp(record.created, timezone.utc)
        assert isinstance(timestamp, datetime)

        # Should be able to get ISO format
        iso_str = timestamp.isoformat()
        assert isinstance(iso_str, str)
        assert "T" in iso_str  # ISO format should contain T separator

    def test_log_event_serialization(self):
        """Test LogEvent creation and serialization."""
        try:
            from mohflow.devui.types import LogEvent
        except ImportError:
            pytest.skip("LogEvent not available (missing dependencies)")

        timestamp = datetime.now(timezone.utc)

        event = LogEvent(
            timestamp=timestamp,
            level="INFO",
            service="test-service",
            message="Test message",
            logger="test.logger",
        )

        # Should be able to serialize to dict
        data = event.to_dict()
        assert isinstance(data, dict)
        assert "timestamp" in data
        assert "level" in data
        assert "service" in data
        assert "message" in data
        assert data["level"] == "INFO"
        assert data["service"] == "test-service"
        assert data["message"] == "Test message"

    def test_mohnitor_handler_emit(self):
        """Test MohnitorForwardingHandler emit method."""
        try:
            from mohflow.devui.client import MohnitorForwardingHandler
        except ImportError:
            pytest.skip(
                "MohnitorForwardingHandler not available (missing dependencies)"
            )

        # Create handler
        handler = MohnitorForwardingHandler(
            service="test-service", hub_host="127.0.0.1", hub_port=17361
        )

        # Create a record to emit
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=123,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Should not raise exception even if hub is not available
        handler.emit(record)  # Should gracefully handle connection failure

    def test_datetime_timezone_handling(self):
        """Test timezone-aware datetime handling."""
        # Test with UTC timezone
        utc_time = datetime.now(timezone.utc)
        iso_utc = utc_time.isoformat()
        assert "+00:00" in iso_utc or "Z" in iso_utc

        # Test conversion from timestamp
        import time

        current_timestamp = time.time()
        converted_time = datetime.fromtimestamp(
            current_timestamp, timezone.utc
        )

        assert isinstance(converted_time, datetime)
        assert converted_time.tzinfo is timezone.utc
