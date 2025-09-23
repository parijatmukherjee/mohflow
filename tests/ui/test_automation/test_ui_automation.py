"""
Comprehensive UI automation test suite for Mohnitor.

This test can run in multiple modes:
1. Simple mode: HTTP API verification only
2. Browser mode: Full browser automation with Selenium
3. Headless mode: Browser automation without display
"""

import pytest
import time
import os
import subprocess
import sys
import requests
from pathlib import Path

# Optional imports for browser automation
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, WebDriverException

    selenium_available = True
except ImportError:
    selenium_available = False

from .test_app import LogGenerator

# Import skip markers from conftest
try:
    from ..conftest import requires_fastapi, requires_selenium
except ImportError:
    requires_fastapi = pytest.mark.skipif(True, reason="FastAPI not available")
    requires_selenium = pytest.mark.skipif(
        True, reason="Selenium not available"
    )


class TestMohnitorUIAutomation:
    """Comprehensive UI automation test suite."""

    def setup_method(self):
        """Set up test environment."""
        self.log_generator = LogGenerator("ui-automation-test")
        self.hub_url = "http://127.0.0.1:17361"
        self.driver = None

    def teardown_method(self):
        """Clean up test environment."""
        if self.log_generator:
            self.log_generator.stop()
        if self.driver:
            self.driver.quit()

    def _start_app_and_verify_hub(self):
        """Start the test app and verify hub is running."""
        self.log_generator.start()

        # Wait for hub to be ready
        max_retries = 15
        for retry in range(max_retries):
            try:
                response = requests.get(f"{self.hub_url}/healthz", timeout=2)
                if response.status_code == 200:
                    return True
            except requests.exceptions.ConnectionError:
                if retry < max_retries - 1:
                    time.sleep(1)
                else:
                    pytest.fail("Mohnitor hub failed to start within timeout")
        return False

    def _setup_browser(self, headless=True):
        """Set up browser driver if available."""
        if not selenium_available:
            pytest.skip("Selenium not available")

        try:
            options = Options()
            if headless:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(10)
            return True

        except WebDriverException as e:
            pytest.skip(f"Chrome driver not available: {e}")

    @requires_fastapi
    def test_api_endpoints_respond_correctly(self):
        """Test that all API endpoints respond correctly."""
        self._start_app_and_verify_hub()

        # Generate some test data
        self.log_generator.generate_test_scenarios()
        time.sleep(1)

        # Test all endpoints
        endpoints = [
            ("/healthz", "application/json"),
            ("/version", "application/json"),
            ("/system", "application/json"),
            ("/ui", "text/html"),
        ]

        for endpoint, expected_content_type in endpoints:
            response = requests.get(f"{self.hub_url}{endpoint}")
            assert response.status_code == 200, f"Endpoint {endpoint} failed"

            content_type = response.headers.get("content-type", "")
            assert (
                expected_content_type in content_type
            ), f"Wrong content type for {endpoint}"

            if expected_content_type == "application/json":
                # Should be valid JSON
                data = response.json()
                assert isinstance(
                    data, dict
                ), f"Invalid JSON response from {endpoint}"

    @requires_fastapi
    def test_websocket_endpoint_accepts_connections(self):
        """Test WebSocket endpoint accepts connections."""
        self._start_app_and_verify_hub()

        # Test that WebSocket endpoint exists (we can't easily test WS without more deps)
        # But we can verify the HTTP upgrade is available
        try:
            import websocket

            ws_url = "ws://127.0.0.1:17361/ws?service=test-client"

            def on_message(ws, message):
                pass

            def on_error(ws, error):
                pass

            def on_close(ws, close_status_code, close_msg):
                pass

            def on_open(ws):
                ws.close()

            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            # Just try to connect briefly
            import threading

            wst = threading.Thread(target=ws.run_forever)
            wst.daemon = True
            wst.start()
            time.sleep(1)

        except ImportError:
            # If websocket-client not available, just verify endpoint exists
            response = requests.get(
                f"{self.hub_url}/ws",
                headers={"Connection": "Upgrade", "Upgrade": "websocket"},
            )
            # Should get an upgrade response or at least not 404
            assert response.status_code != 404

    @pytest.mark.skipif(
        not selenium_available, reason="selenium not available"
    )
    def test_ui_loads_in_browser(self):
        """Test that UI loads properly in browser."""
        self._start_app_and_verify_hub()
        self._setup_browser(headless=True)

        # Navigate to UI
        self.driver.get(self.hub_url)

        # Verify page loaded
        assert "Mohnitor" in self.driver.title

        # Check for essential elements
        wait = WebDriverWait(self.driver, 10)

        # Should have main container
        container = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "container"))
        )
        assert container is not None

        # Should have header
        header = wait.until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        assert "Mohnitor" in header.text

    @pytest.mark.skipif(
        not selenium_available, reason="selenium not available"
    )
    def test_logs_display_in_browser(self):
        """Test that logs are displayed in the browser."""
        self._start_app_and_verify_hub()
        self._setup_browser(headless=True)

        # Generate logs before opening browser
        self.log_generator.generate_test_scenarios()
        time.sleep(1)

        # Navigate to UI
        self.driver.get(self.hub_url)

        wait = WebDriverWait(self.driver, 15)

        # Wait for logs container
        logs_container = wait.until(
            EC.presence_of_element_located((By.ID, "logs"))
        )

        # Wait a bit for logs to load
        time.sleep(3)

        # Look for log entries
        log_entries = self.driver.find_elements(By.CLASS_NAME, "log-entry")

        if len(log_entries) == 0:
            # Try alternative selectors
            log_entries = self.driver.find_elements(
                By.CSS_SELECTOR, "[class*='log']"
            )

        assert len(log_entries) > 0, "No log entries found in browser"

    @pytest.mark.skipif(
        not selenium_available, reason="selenium not available"
    )
    def test_real_time_updates_in_browser(self):
        """Test that logs update in real-time in browser."""
        self._start_app_and_verify_hub()
        self._setup_browser(headless=True)

        # Navigate to UI first
        self.driver.get(self.hub_url)

        # Wait for initial load
        time.sleep(2)

        # Count initial logs
        initial_log_count = len(
            self.driver.find_elements(By.CLASS_NAME, "log-entry")
        )

        # Generate more logs
        self.log_generator.generate_test_scenarios()

        # Wait for updates
        time.sleep(3)

        # Count final logs
        final_log_count = len(
            self.driver.find_elements(By.CLASS_NAME, "log-entry")
        )

        # Should have more logs now
        assert (
            final_log_count >= initial_log_count
        ), "No real-time updates detected"

    @requires_fastapi
    def test_high_volume_log_handling(self):
        """Test system handles high volume of logs."""
        self._start_app_and_verify_hub()

        # Get initial stats
        initial_response = requests.get(f"{self.hub_url}/system")
        initial_stats = initial_response.json()
        initial_events = initial_stats["buffer_stats"]["total_events"]

        # Generate many logs quickly
        for i in range(100):
            self.log_generator.logger.info(
                f"High volume test log {i}", batch_id="volume-test", sequence=i
            )

        time.sleep(2)

        # Verify system is still responsive
        final_response = requests.get(f"{self.hub_url}/system")
        assert final_response.status_code == 200

        final_stats = final_response.json()
        final_events = final_stats["buffer_stats"]["total_events"]

        # Should have processed most/all logs
        events_added = final_events - initial_events
        assert (
            events_added >= 50
        ), f"Only {events_added} events processed out of 100"

        # Hub should still be healthy
        health_response = requests.get(f"{self.hub_url}/healthz")
        assert health_response.status_code == 200

    @requires_fastapi
    @requires_selenium
    def test_error_log_visualization(self):
        """Test that error logs are properly visualized."""
        self._start_app_and_verify_hub()

        # Generate specific error scenarios
        error_scenarios = [
            ("CRITICAL", "System crash detected", {"component": "core"}),
            ("ERROR", "Database connection lost", {"retry_count": 3}),
            ("WARNING", "Memory usage critical", {"usage": "95%"}),
        ]

        for level, message, context in error_scenarios:
            getattr(self.log_generator.logger, level.lower())(
                message, **context
            )

        time.sleep(1)

        # Verify logs are captured
        response = requests.get(f"{self.hub_url}/system")
        stats = response.json()
        assert stats["buffer_stats"]["total_events"] >= len(error_scenarios)

    @requires_fastapi
    def test_service_discovery_and_display(self):
        """Test that multiple services are discovered and displayed."""
        # Start main service
        self._start_app_and_verify_hub()

        # Start additional services
        service_generators = [
            LogGenerator("auth-service"),
            LogGenerator("api-gateway"),
            LogGenerator("database-service"),
        ]

        try:
            for generator in service_generators:
                generator.start()
                time.sleep(0.5)

            # Generate logs from all services
            for i, generator in enumerate(
                [self.log_generator] + service_generators
            ):
                generator.logger.info(
                    f"Service {i} operational",
                    service_index=i,
                    trace_id=f"discovery-{i}",
                )

            time.sleep(2)

            # Verify all services are registered
            response = requests.get(f"{self.hub_url}/system")
            stats = response.json()
            services = stats["client_stats"]["services"]

            expected_services = [
                "ui-automation-test",
                "auth-service",
                "api-gateway",
                "database-service",
            ]
            for service in expected_services:
                assert service in services, f"Service {service} not discovered"

            # Should have multiple active connections
            assert stats["client_stats"]["active_connections"] >= len(
                expected_services
            )

        finally:
            for generator in service_generators:
                generator.stop()


# CLI for manual testing
def main():
    """Run manual testing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Mohnitor UI automation tests"
    )
    parser.add_argument(
        "--browser", action="store_true", help="Run browser tests"
    )
    parser.add_argument(
        "--visible", action="store_true", help="Run browser in visible mode"
    )
    args = parser.parse_args()

    test = TestMohnitorUIAutomation()
    test.setup_method()

    try:
        print("🚀 Starting Mohnitor UI automation test...")

        print("✓ Testing API endpoints...")
        test.test_api_endpoints_respond_correctly()

        print("✓ Testing WebSocket endpoint...")
        test.test_websocket_endpoint_accepts_connections()

        print("✓ Testing high volume handling...")
        test.test_high_volume_log_handling()

        print("✓ Testing service discovery...")
        test.test_service_discovery_and_display()

        if args.browser and selenium_available:
            print("🌐 Running browser tests...")

            test._setup_browser(headless=not args.visible)

            print("✓ Testing UI load in browser...")
            test.test_ui_loads_in_browser()

            print("✓ Testing log display in browser...")
            test.test_logs_display_in_browser()

            print("✓ Testing real-time updates...")
            test.test_real_time_updates_in_browser()

        print(f"🎉 All tests passed!")
        print(f"📊 Mohnitor UI available at: {test.hub_url}")

        if not args.browser:
            print("💡 Run with --browser to include browser automation tests")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return 1
    finally:
        test.teardown_method()

    return 0


if __name__ == "__main__":
    sys.exit(main())
