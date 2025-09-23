"""
Integration test for hub failover when primary crashes.

This test MUST FAIL initially until failover implementation is complete.
"""

import pytest
import time
import requests
import signal
import os
import multiprocessing
from mohflow import get_logger
from ..conftest import requires_hub_server


def start_backup_app():
    """Start app that should become new hub after primary fails."""
    logger = get_logger(service="backup-app", enable_mohnitor=True)
    logger.info("Backup app ready")
    time.sleep(5)  # Stay alive to take over


@requires_hub_server
class TestHubFailover:
    """Test hub failover scenarios."""

    def test_hub_failover_on_crash(self):
        """Test that another app takes over when hub crashes."""
        # Start primary hub
        logger1 = get_logger(service="primary-app", enable_mohnitor=True)
        logger1.info("Primary hub started")

        time.sleep(1)

        # Verify primary hub is running
        response = requests.get("http://127.0.0.1:17361/healthz")
        assert response.status_code == 200

        # Start backup app
        backup_process = multiprocessing.Process(target=start_backup_app)
        backup_process.start()

        time.sleep(1)

        # Simulate primary hub crash (in real scenario, would kill hub process)
        # For test, we'll simulate by stopping logger and clearing descriptor

        # Remove descriptor file to simulate crash
        import os

        descriptor_path = "/tmp/mohnitor/hub.json"
        if os.path.exists(descriptor_path):
            os.remove(descriptor_path)

        time.sleep(3)  # Give backup time to take over

        # New hub should be running (backup app should have taken over)
        response = requests.get("http://127.0.0.1:17361/healthz")
        assert response.status_code == 200

        # Should show backup service
        response = requests.get("http://127.0.0.1:17361/system")
        data = response.json()
        assert "backup-app" in data["client_stats"]["services"]

        backup_process.terminate()
        backup_process.join()

    def test_stale_descriptor_handling(self):
        """Test handling of stale hub descriptor files."""
        # Create stale descriptor file
        import json

        descriptor_data = {
            "host": "127.0.0.1",
            "port": 17361,
            "pid": 99999,  # Non-existent PID
            "token": None,
            "created_at": "2025-09-23T10:00:00.000Z",
            "version": "1.0.0",
        }

        os.makedirs("/tmp/mohnitor", exist_ok=True)
        with open("/tmp/mohnitor/hub.json", "w") as f:
            json.dump(descriptor_data, f)

        # Start new app - should detect stale descriptor and take over
        logger = get_logger(service="new-hub", enable_mohnitor=True)

        time.sleep(1)

        # Should have created new descriptor with current PID
        with open("/tmp/mohnitor/hub.json") as f:
            new_data = json.load(f)

        assert new_data["pid"] != 99999
        assert new_data["pid"] == os.getpid()
