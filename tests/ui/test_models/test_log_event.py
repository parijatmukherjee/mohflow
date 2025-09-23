"""
Unit tests for LogEvent serialization and validation.

These tests MUST FAIL initially until the types.py implementation is complete.
"""

import pytest
import json
from datetime import datetime, timezone
from mohflow.devui.types import LogEvent


class TestLogEvent:
    """Test LogEvent serialization and validation."""

    def test_log_event_creation(self):
        """Test basic LogEvent creation."""
        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Test message",
            logger="test.logger",
        )

        assert event.level == "INFO"
        assert event.service == "test-service"
        assert event.message == "Test message"
        assert event.logger == "test.logger"
        assert isinstance(event.timestamp, datetime)

    def test_log_event_with_trace_id(self):
        """Test LogEvent with trace ID for correlation."""
        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Traced message",
            logger="test.logger",
            trace_id="abc123-def456",
        )

        assert event.trace_id == "abc123-def456"

    def test_log_event_with_context(self):
        """Test LogEvent with structured context."""
        context = {
            "user_id": "12345",
            "session_id": "session-abc",
            "request_id": "req-123",
        }

        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Request processed",
            logger="api.handler",
            context=context,
        )

        assert event.context == context
        assert event.context["user_id"] == "12345"

    def test_log_event_level_validation(self):
        """Test that log level must be valid."""
        valid_levels = ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"]

        for level in valid_levels:
            event = LogEvent(
                timestamp=datetime.now(timezone.utc),
                level=level,
                service="test-service",
                message="Test message",
                logger="test.logger",
            )
            assert event.level == level

        # Invalid levels should raise validation error
        invalid_levels = ["TRACE", "FATAL", "invalid", ""]

        for level in invalid_levels:
            with pytest.raises((ValueError, TypeError)):
                LogEvent(
                    timestamp=datetime.now(timezone.utc),
                    level=level,
                    service="test-service",
                    message="Test message",
                    logger="test.logger",
                )

    def test_log_event_service_validation(self):
        """Test that service name must be non-empty."""
        # Valid service names
        valid_services = [
            "test-service",
            "auth",
            "checkout-api",
            "user-service-v2",
        ]

        for service in valid_services:
            event = LogEvent(
                timestamp=datetime.now(timezone.utc),
                level="INFO",
                service=service,
                message="Test message",
                logger="test.logger",
            )
            assert event.service == service

        # Invalid service names
        with pytest.raises((ValueError, TypeError)):
            LogEvent(
                timestamp=datetime.now(timezone.utc),
                level="INFO",
                service="",  # Empty service
                message="Test message",
                logger="test.logger",
            )

    def test_log_event_serialization_to_json(self):
        """Test that LogEvent can be serialized to JSON."""
        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="ERROR",
            service="payment-service",
            message="Payment failed",
            logger="payment.processor",
            trace_id="trace-123",
            context={"error_code": "E001", "amount": 99.99},
        )

        # Should have to_dict method
        data = event.to_dict()
        assert isinstance(data, dict)
        assert data["level"] == "ERROR"
        assert data["service"] == "payment-service"
        assert data["message"] == "Payment failed"
        assert data["trace_id"] == "trace-123"
        assert data["context"]["error_code"] == "E001"

        # Should be JSON serializable
        json_str = json.dumps(data, default=str)
        assert isinstance(json_str, str)

        # Should be parseable back
        parsed = json.loads(json_str)
        assert parsed["level"] == "ERROR"

    def test_log_event_deserialization_from_dict(self):
        """Test that LogEvent can be created from dict."""
        data = {
            "timestamp": "2025-09-23T10:30:00.123456Z",
            "level": "WARN",
            "service": "auth-service",
            "message": "Login attempt failed",
            "logger": "auth.handler",
            "trace_id": "trace-456",
            "context": {"ip_address": "192.168.1.100"},
        }

        # Should have from_dict class method
        event = LogEvent.from_dict(data)
        assert event.level == "WARN"
        assert event.service == "auth-service"
        assert event.message == "Login attempt failed"
        assert event.trace_id == "trace-456"
        assert event.context["ip_address"] == "192.168.1.100"

    def test_log_event_size_validation(self):
        """Test that LogEvent validates size limits."""
        # Normal sized event should work
        normal_event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Normal message",
            logger="test.logger",
        )

        # Should validate size
        size = normal_event.serialized_size()
        assert isinstance(size, int)
        assert size > 0

        # Oversized event should fail validation
        large_context = {"large_field": "x" * (65 * 1024)}  # 65KB

        oversized_event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Oversized message",
            logger="test.logger",
            context=large_context,
        )

        with pytest.raises((ValueError, TypeError)):
            oversized_event.validate_size(max_size=64 * 1024)  # 64KB limit

    def test_log_event_timestamp_formats(self):
        """Test different timestamp format handling."""
        # UTC datetime should work
        utc_time = datetime.now(timezone.utc)
        event = LogEvent(
            timestamp=utc_time,
            level="INFO",
            service="test-service",
            message="Test message",
            logger="test.logger",
        )
        assert event.timestamp == utc_time

        # Should handle ISO string timestamps in from_dict
        iso_string = "2025-09-23T10:30:00.123Z"
        data = {
            "timestamp": iso_string,
            "level": "INFO",
            "service": "test-service",
            "message": "Test message",
            "logger": "test.logger",
        }

        event = LogEvent.from_dict(data)
        assert isinstance(event.timestamp, datetime)

    def test_log_event_mohnitor_metadata(self):
        """Test Mohnitor-specific metadata fields."""
        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Test message",
            logger="test.logger",
            source_host="dev-machine",
            source_pid=12345,
        )

        assert event.source_host == "dev-machine"
        assert event.source_pid == 12345
        assert event.received_at is None  # Set by hub

        # Hub should set received_at
        event.set_received_at()
        assert event.received_at is not None
        assert isinstance(event.received_at, datetime)
