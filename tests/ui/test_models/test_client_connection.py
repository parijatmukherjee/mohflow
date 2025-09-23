"""
Unit tests for ClientConnection lifecycle.

These tests MUST FAIL initially until the types.py implementation is complete.
"""

import pytest
from datetime import datetime, timedelta, timezone
from mohflow.devui.types import ClientConnection


class TestClientConnection:
    """Test ClientConnection lifecycle and validation."""

    def test_client_connection_creation(self):
        """Test basic ClientConnection creation."""
        connection = ClientConnection(
            connection_id="conn-123",
            service="test-service",
            host="127.0.0.1",
            pid=12345,
            connected_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )

        assert connection.connection_id == "conn-123"
        assert connection.service == "test-service"
        assert connection.host == "127.0.0.1"
        assert connection.pid == 12345

    def test_client_connection_heartbeat_tracking(self):
        """Test heartbeat and last_seen tracking."""
        connection = ClientConnection(
            connection_id="conn-123",
            service="test-service",
            host="127.0.0.1",
            pid=12345,
            connected_at=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )

        old_last_seen = connection.last_seen

        # Update heartbeat
        connection.update_heartbeat()
        assert connection.last_seen > old_last_seen

    def test_client_connection_is_stale(self):
        """Test stale connection detection."""
        old_time = datetime.now(timezone.utc) - timedelta(minutes=5)

        connection = ClientConnection(
            connection_id="conn-123",
            service="test-service",
            host="127.0.0.1",
            pid=12345,
            connected_at=old_time,
            last_seen=old_time,
        )

        # Should detect stale connections
        assert connection.is_stale(timeout_seconds=60)  # 1 minute timeout
        assert not connection.is_stale(
            timeout_seconds=600
        )  # 10 minute timeout
