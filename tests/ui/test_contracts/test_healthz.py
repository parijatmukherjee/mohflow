"""
Contract test for GET /healthz endpoint.

This test MUST FAIL initially until the hub server is implemented.
"""

import pytest
import requests
import json
from datetime import datetime
from ..conftest import requires_hub_server


@requires_hub_server
class TestHealthzContract:
    """Test contract for /healthz endpoint according to hub-api.yaml."""

    def test_healthz_endpoint_returns_200(self):
        """Test that /healthz returns 200 status code."""
        # This will fail until hub server is implemented
        response = requests.get("http://127.0.0.1:17361/healthz")
        assert response.status_code == 200

    def test_healthz_response_has_required_fields(self):
        """Test that /healthz response contains all required fields."""
        response = requests.get("http://127.0.0.1:17361/healthz")
        assert response.status_code == 200

        data = response.json()

        # Check required fields according to contract
        assert "status" in data
        assert "uptime" in data
        assert "version" in data

        # Validate field types and values
        assert data["status"] == "healthy"
        assert isinstance(data["uptime"], (int, float))
        assert data["uptime"] >= 0
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_healthz_response_content_type_is_json(self):
        """Test that /healthz returns JSON content type."""
        response = requests.get("http://127.0.0.1:17361/healthz")
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_healthz_uptime_increases_over_time(self):
        """Test that uptime increases between calls."""
        response1 = requests.get("http://127.0.0.1:17361/healthz")
        uptime1 = response1.json()["uptime"]

        # Small delay
        import time

        time.sleep(0.1)

        response2 = requests.get("http://127.0.0.1:17361/healthz")
        uptime2 = response2.json()["uptime"]

        assert uptime2 > uptime1
