"""
Test graceful fallback behavior when optional dependencies are not available.
"""

import pytest
from datetime import datetime, timezone


class TestHubFallback:
    """Test hub graceful fallback when dependencies unavailable."""

    def test_hub_import_with_fastapi_fallback(self):
        """Test that hub imports gracefully handle missing FastAPI."""
        try:
            from mohflow.devui.hub import MohnitorHub

            # If this succeeds, FastAPI is available
            assert MohnitorHub is not None
        except ImportError as e:
            # Should gracefully report FastAPI unavailability
            assert (
                "FastAPI not available" in str(e)
                or "fastapi" in str(e).lower()
            )

    def test_basic_types_work_without_fastapi(self):
        """Test that basic types work without FastAPI."""
        try:
            from mohflow.devui.types import HubDescriptor, LogEvent
        except ImportError:
            pytest.skip("Basic types not available (missing dependencies)")

        # Test basic functionality
        descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

        log_event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test",
            message="Test message",
            logger="test.logger",
        )

        # Test serialization
        desc_data = descriptor.to_dict()
        event_data = log_event.to_dict()

        assert isinstance(desc_data, dict)
        assert isinstance(event_data, dict)
        assert desc_data["host"] == "127.0.0.1"
        assert event_data["level"] == "INFO"

    def test_discovery_graceful_fallback(self):
        """Test discovery works gracefully without dependencies."""
        try:
            from mohflow.devui.discovery import discover_hub
        except ImportError:
            pytest.skip("Discovery not available (missing dependencies)")

        # Should not crash even without all dependencies
        result = discover_hub()
        # Result should be None or a valid HubDescriptor
        assert result is None or hasattr(result, "host")

    def test_client_graceful_fallback(self):
        """Test client handles missing dependencies gracefully."""
        try:
            from mohflow.devui.client import MohnitorForwardingHandler
        except ImportError:
            pytest.skip("Client not available (missing dependencies)")

        # Should be able to create handler even if hub unavailable
        handler = MohnitorForwardingHandler(
            service="test-service", hub_host="127.0.0.1", hub_port=17361
        )

        assert handler.service == "test-service"
        assert handler.hub_host == "127.0.0.1"
        assert handler.hub_port == 17361

    def test_mohnitor_enable_graceful_fallback(self):
        """Test that enable_mohnitor works gracefully without hub."""
        from mohflow import get_logger

        # Should not crash even if dependencies missing or hub unavailable
        logger = get_logger("test-service", enable_mohnitor=True)

        # Should still be a functional logger
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")

        # Should be able to log without crashing
        logger.info("Test message")
        logger.error("Test error")
