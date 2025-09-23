"""
Contract test for GET /system endpoint.

This test MUST FAIL initially until the hub server is implemented.
"""

import pytest
import requests
import json
from ..conftest import requires_hub_server


@requires_hub_server
class TestSystemContract:
    """Test contract for /system endpoint according to hub-api.yaml."""

    def test_system_endpoint_returns_200(self):
        """Test that /system returns 200 status code."""
        # This will fail until hub server is implemented
        response = requests.get("http://127.0.0.1:17361/system")
        assert response.status_code == 200

    def test_system_response_has_required_fields(self):
        """Test that /system response contains all required fields."""
        response = requests.get("http://127.0.0.1:17361/system")
        assert response.status_code == 200

        data = response.json()

        # Check required top-level fields
        assert "buffer_stats" in data
        assert "client_stats" in data
        assert "uptime" in data
        assert "port" in data
        assert "started_at" in data

        # Validate buffer_stats
        buffer_stats = data["buffer_stats"]
        assert "total_events" in buffer_stats
        assert "max_events" in buffer_stats
        assert "dropped_events" in buffer_stats
        assert isinstance(buffer_stats["total_events"], int)
        assert isinstance(buffer_stats["max_events"], int)
        assert isinstance(buffer_stats["dropped_events"], int)
        assert buffer_stats["total_events"] >= 0
        assert buffer_stats["max_events"] > 0
        assert buffer_stats["dropped_events"] >= 0

        # Validate client_stats
        client_stats = data["client_stats"]
        assert "active_connections" in client_stats
        assert "total_connections" in client_stats
        assert "services" in client_stats
        assert isinstance(client_stats["active_connections"], int)
        assert isinstance(client_stats["total_connections"], int)
        assert isinstance(client_stats["services"], list)
        assert client_stats["active_connections"] >= 0
        assert client_stats["total_connections"] >= 0

    def test_system_response_optional_fields(self):
        """Test optional fields in /system response."""
        response = requests.get("http://127.0.0.1:17361/system")
        data = response.json()

        # Optional performance_stats
        if "performance_stats" in data:
            perf_stats = data["performance_stats"]
            if "events_per_second" in perf_stats:
                assert isinstance(
                    perf_stats["events_per_second"], (int, float)
                )
                assert perf_stats["events_per_second"] >= 0

        # Optional memory_usage_mb in buffer_stats
        if "memory_usage_mb" in data["buffer_stats"]:
            memory_usage = data["buffer_stats"]["memory_usage_mb"]
            assert isinstance(memory_usage, (int, float))
            assert memory_usage >= 0

    def test_system_buffer_stats_consistency(self):
        """Test that buffer stats are internally consistent."""
        response = requests.get("http://127.0.0.1:17361/system")
        data = response.json()

        buffer_stats = data["buffer_stats"]
        total_events = buffer_stats["total_events"]
        max_events = buffer_stats["max_events"]
        dropped_events = buffer_stats["dropped_events"]

        # Total events should not exceed max events
        assert total_events <= max_events

        # If dropped events exist, total should be at max
        if dropped_events > 0:
            assert total_events == max_events
