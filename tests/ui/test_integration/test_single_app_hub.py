"""
Integration test for single app becoming hub.

This test MUST FAIL initially until hub/client implementation is complete.
"""

import pytest
import time
import requests
from mohflow import get_logger
from ..conftest import requires_hub_server


@requires_hub_server
class TestSingleAppHub:
    """Test single application becoming hub scenario."""

    def test_single_app_becomes_hub(self):
        """Test that first app with enable_mohnitor=True becomes hub."""
        # This will fail until integration is complete
        logger = get_logger(service="test-app", enable_mohnitor=True)

        # Should start hub automatically
        time.sleep(1)  # Give it time to start

        # Hub should be accessible
        response = requests.get("http://127.0.0.1:17361/healthz")
        assert response.status_code == 200

        # Should show service in system stats
        response = requests.get("http://127.0.0.1:17361/system")
        data = response.json()
        assert "test-app" in data["client_stats"]["services"]

    def test_single_app_logging_appears_in_ui(self):
        """Test that logs from single app appear in UI."""
        logger = get_logger(service="test-app", enable_mohnitor=True)

        # Log some messages
        logger.info("Test message 1")
        logger.error("Test error", error_code="E001")

        time.sleep(0.5)  # Allow processing

        # Check system shows events
        response = requests.get("http://127.0.0.1:17361/system")
        data = response.json()
        assert data["buffer_stats"]["total_events"] >= 2
