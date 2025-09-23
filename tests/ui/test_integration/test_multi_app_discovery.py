"""
Integration test for multi-app auto-discovery.

This test MUST FAIL initially until discovery implementation is complete.
"""

import pytest
import time
import requests
import multiprocessing
from mohflow import get_logger
from ..conftest import requires_hub_server


def start_second_app():
    """Start second app that should connect to existing hub."""
    logger = get_logger(service="second-app", enable_mohnitor=True)
    logger.info("Second app started")
    time.sleep(2)  # Keep alive


@requires_hub_server
class TestMultiAppDiscovery:
    """Test multi-application auto-discovery scenario."""

    def test_second_app_discovers_existing_hub(self):
        """Test that second app connects to existing hub."""
        # Start first app (becomes hub)
        logger1 = get_logger(service="first-app", enable_mohnitor=True)
        logger1.info("First app started")

        time.sleep(1)  # Let hub start

        # Start second app in subprocess
        process = multiprocessing.Process(target=start_second_app)
        process.start()

        time.sleep(2)  # Let second app connect

        # Check both services in hub
        response = requests.get("http://127.0.0.1:17361/system")
        data = response.json()
        services = data["client_stats"]["services"]

        assert "first-app" in services
        assert "second-app" in services
        assert data["client_stats"]["active_connections"] >= 1

        process.terminate()
        process.join()

    def test_hub_descriptor_file_creation(self):
        """Test that hub creates descriptor file for discovery."""
        logger = get_logger(service="test-app", enable_mohnitor=True)

        time.sleep(1)

        # Check descriptor file exists
        import os

        descriptor_path = "/tmp/mohnitor/hub.json"
        assert os.path.exists(descriptor_path)

        # Check descriptor contents
        import json

        with open(descriptor_path) as f:
            data = json.load(f)

        assert data["host"] == "127.0.0.1"
        assert data["port"] == 17361
        assert "pid" in data
