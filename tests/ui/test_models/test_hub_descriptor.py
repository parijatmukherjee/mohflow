"""
Unit tests for HubDescriptor validation.

These tests MUST FAIL initially until the types.py implementation is complete.
"""

import pytest
from datetime import datetime, timezone
from mohflow.devui.types import HubDescriptor


class TestHubDescriptor:
    """Test HubDescriptor validation and functionality."""

    def test_hub_descriptor_creation(self):
        """Test basic HubDescriptor creation."""
        descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

        assert descriptor.host == "127.0.0.1"
        assert descriptor.port == 17361
        assert descriptor.pid == 12345
        assert descriptor.token is None
        assert isinstance(descriptor.created_at, datetime)
        assert descriptor.version == "1.0.0"

    def test_hub_descriptor_with_token(self):
        """Test HubDescriptor creation with authentication token."""
        descriptor = HubDescriptor(
            host="192.168.1.100",
            port=17362,
            pid=54321,
            token="abc123def456",
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

        assert descriptor.host == "192.168.1.100"
        assert descriptor.token == "abc123def456"

    def test_hub_descriptor_port_validation(self):
        """Test that port must be in valid range."""
        # Valid ports should work
        valid_descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )
        assert valid_descriptor.port == 17361

        # Invalid ports should raise validation error
        with pytest.raises((ValueError, TypeError)):
            HubDescriptor(
                host="127.0.0.1",
                port=100,  # Too low
                pid=12345,
                token=None,
                created_at=datetime.now(timezone.utc),
                version="1.0.0",
            )

        with pytest.raises((ValueError, TypeError)):
            HubDescriptor(
                host="127.0.0.1",
                port=70000,  # Too high
                pid=12345,
                token=None,
                created_at=datetime.now(timezone.utc),
                version="1.0.0",
            )

    def test_hub_descriptor_host_validation(self):
        """Test that host must be valid IP or hostname."""
        # Valid localhost hosts should work without token
        localhost_hosts = ["127.0.0.1", "localhost"]
        for host in localhost_hosts:
            descriptor = HubDescriptor(
                host=host,
                port=17361,
                pid=12345,
                token=None,
                created_at=datetime.now(timezone.utc),
                version="1.0.0",
            )
            assert descriptor.host == host

        # Valid remote hosts should work with token
        remote_hosts = ["192.168.1.100", "hub.example.com"]
        for host in remote_hosts:
            descriptor = HubDescriptor(
                host=host,
                port=17361,
                pid=12345,
                token="test-token",  # Required for remote hosts
                created_at=datetime.now(timezone.utc),
                version="1.0.0",
            )
            assert descriptor.host == host

        # Invalid hosts should raise validation error
        invalid_hosts = ["", "not..valid", "256.256.256.256"]

        for host in invalid_hosts:
            with pytest.raises((ValueError, TypeError)):
                HubDescriptor(
                    host=host,
                    port=17361,
                    pid=12345,
                    token=None,
                    created_at=datetime.now(timezone.utc),
                    version="1.0.0",
                )

    def test_hub_descriptor_token_required_for_remote(self):
        """Test that token is required for non-localhost hosts."""
        # Localhost should work without token
        local_descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )
        assert local_descriptor.token is None

        # Remote host should require token
        with pytest.raises((ValueError, TypeError)):
            HubDescriptor(
                host="192.168.1.100",
                port=17361,
                pid=12345,
                token=None,  # Should require token for remote
                created_at=datetime.now(timezone.utc),
                version="1.0.0",
            )

    def test_hub_descriptor_pid_validation(self):
        """Test that PID must be positive integer."""
        # Valid PID
        descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )
        assert descriptor.pid == 12345

        # Invalid PIDs
        with pytest.raises((ValueError, TypeError)):
            HubDescriptor(
                host="127.0.0.1",
                port=17361,
                pid=-1,  # Negative PID
                token=None,
                created_at=datetime.now(timezone.utc),
                version="1.0.0",
            )

        with pytest.raises((ValueError, TypeError)):
            HubDescriptor(
                host="127.0.0.1",
                port=17361,
                pid=0,  # Zero PID
                token=None,
                created_at=datetime.now(timezone.utc),
                version="1.0.0",
            )

    def test_hub_descriptor_serialization(self):
        """Test that HubDescriptor can be serialized to/from dict."""
        original = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token="test-token",
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

        # Should have to_dict method
        data = original.to_dict()
        assert isinstance(data, dict)
        assert data["host"] == "127.0.0.1"
        assert data["port"] == 17361
        assert data["pid"] == 12345
        assert data["token"] == "test-token"
        assert "created_at" in data
        assert data["version"] == "1.0.0"

        # Should have from_dict class method
        restored = HubDescriptor.from_dict(data)
        assert restored.host == original.host
        assert restored.port == original.port
        assert restored.pid == original.pid
        assert restored.token == original.token
        assert restored.version == original.version

    def test_hub_descriptor_age_calculation(self):
        """Test that HubDescriptor can calculate its age."""
        old_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=old_time,
            version="1.0.0",
        )

        # Should have age_seconds method
        age = descriptor.age_seconds()
        assert isinstance(age, (int, float))
        assert age >= 0
