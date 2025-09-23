"""
Simple end-to-end test for Mohnitor without browser automation.

Tests the complete flow:
1. Start app with MohFlow + Mohnitor
2. Generate logs
3. Verify hub endpoints respond correctly
4. Verify logs are captured and available
"""

import pytest
import time
import threading
import requests
import json
from .test_app import LogGenerator

# Import skip markers from conftest
try:
    from ..conftest import requires_fastapi
except ImportError:
    requires_fastapi = pytest.mark.skipif(True, reason="FastAPI not available")


class TestMohnitorE2E:
    """End-to-end tests for Mohnitor functionality."""

    def setup_method(self):
        """Set up each test method."""
        self.log_generator = LogGenerator("e2e-test-app")
        self.hub_url = "http://127.0.0.1:17361"

    def teardown_method(self):
        """Clean up each test method."""
        if self.log_generator:
            self.log_generator.stop()

    @requires_fastapi
    def test_complete_e2e_flow(self):
        """Test complete end-to-end flow from app startup to log visibility."""
        # Step 1: Start the test app (which starts Mohnitor hub)
        self.log_generator.start()

        # Step 2: Verify hub is running
        try:
            response = requests.get(f"{self.hub_url}/healthz", timeout=5)
            assert response.status_code == 200
            health_data = response.json()
            assert "uptime" in health_data
        except requests.exceptions.ConnectionError:
            pytest.fail("Mohnitor hub failed to start")

        # Step 3: Generate test logs
        self.log_generator.generate_test_scenarios()
        time.sleep(1)  # Allow logs to be processed

        # Step 4: Verify logs are captured
        response = requests.get(f"{self.hub_url}/system")
        assert response.status_code == 200
        system_data = response.json()

        # Should show our service
        services = system_data["client_stats"]["services"]
        assert "e2e-test-app" in services

        # Should have captured events
        total_events = system_data["buffer_stats"]["total_events"]
        assert total_events > 0, "No events captured by Mohnitor"

        # Step 5: Verify UI endpoint
        response = requests.get(self.hub_url)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Mohnitor" in response.text

        # Step 6: Verify version endpoint
        response = requests.get(f"{self.hub_url}/version")
        assert response.status_code == 200
        version_data = response.json()
        assert "version" in version_data

    @requires_fastapi
    def test_log_generation_and_capture(self):
        """Test that different types of logs are properly generated and captured."""
        self.log_generator.start()

        # Wait for hub to be ready
        max_retries = 10
        for _ in range(max_retries):
            try:
                response = requests.get(f"{self.hub_url}/healthz", timeout=2)
                if response.status_code == 200:
                    break
            except requests.exceptions.ConnectionError:
                time.sleep(0.5)
        else:
            pytest.fail("Hub failed to start within timeout")

        # Generate specific log scenarios
        scenarios = [
            (
                "info",
                "User login successful",
                {"user_id": "test123", "ip": "127.0.0.1"},
            ),
            ("warning", "High memory usage", {"memory_percent": 85}),
            ("error", "Database connection failed", {"error_code": "DB001"}),
            ("debug", "Processing request", {"request_id": "req-456"}),
        ]

        initial_stats = requests.get(f"{self.hub_url}/system").json()
        initial_events = initial_stats["buffer_stats"]["total_events"]

        # Generate the scenarios
        for level, message, context in scenarios:
            getattr(self.log_generator.logger, level)(message, **context)

        time.sleep(1)  # Allow processing

        # Verify events increased
        final_stats = requests.get(f"{self.hub_url}/system").json()
        final_events = final_stats["buffer_stats"]["total_events"]

        assert final_events > initial_events, "No new events captured"
        events_added = final_events - initial_events
        assert events_added >= len(
            scenarios
        ), f"Expected at least {len(scenarios)} new events, got {events_added}"

    @requires_fastapi
    def test_continuous_logging_performance(self):
        """Test that continuous logging doesn't break the system."""
        self.log_generator.start()

        # Wait for hub
        time.sleep(2)

        # Get initial stats
        initial_response = requests.get(f"{self.hub_url}/system")
        assert initial_response.status_code == 200
        initial_stats = initial_response.json()
        initial_events = initial_stats["buffer_stats"]["total_events"]

        # Let continuous logging run for a few seconds
        time.sleep(3)

        # Check that system is still responsive
        final_response = requests.get(f"{self.hub_url}/system")
        assert final_response.status_code == 200
        final_stats = final_response.json()
        final_events = final_stats["buffer_stats"]["total_events"]

        # Should have more events
        assert final_events > initial_events, "Continuous logging not working"

        # Hub should still be healthy
        health_response = requests.get(f"{self.hub_url}/healthz")
        assert health_response.status_code == 200

    @requires_fastapi
    def test_trace_correlation_e2e(self):
        """Test end-to-end trace correlation."""
        self.log_generator.start()
        time.sleep(2)

        # Generate correlated logs with same trace_id
        trace_id = "e2e-trace-123"

        self.log_generator.logger.info(
            "Request started", endpoint="/api/users", trace_id=trace_id
        )

        self.log_generator.logger.debug(
            "Database query", query="SELECT * FROM users", trace_id=trace_id
        )

        self.log_generator.logger.info(
            "Request completed",
            status=200,
            duration="150ms",
            trace_id=trace_id,
        )

        time.sleep(1)

        # Verify system captured the logs
        response = requests.get(f"{self.hub_url}/system")
        assert response.status_code == 200
        stats = response.json()
        assert stats["buffer_stats"]["total_events"] >= 3

    @requires_fastapi
    def test_error_handling_e2e(self):
        """Test error handling in end-to-end scenario."""
        self.log_generator.start()
        time.sleep(2)

        # Generate various error scenarios
        self.log_generator.logger.error(
            "Critical system error",
            component="payment_processor",
            error_code="PAY001",
            stack_trace="Mock stack trace",
        )

        self.log_generator.logger.warning(
            "Performance degradation", response_time="2.5s", threshold="1.0s"
        )

        time.sleep(1)

        # System should still be operational
        response = requests.get(f"{self.hub_url}/healthz")
        assert response.status_code == 200

        # Events should be captured
        response = requests.get(f"{self.hub_url}/system")
        stats = response.json()
        assert stats["buffer_stats"]["total_events"] > 0

    @requires_fastapi
    def test_multi_service_scenario(self):
        """Test scenario with multiple services logging."""
        # Start primary service
        self.log_generator.start()
        time.sleep(1)

        # Create additional log generators for different services
        auth_generator = LogGenerator("auth-service")
        api_generator = LogGenerator("api-service")

        try:
            auth_generator.start()
            api_generator.start()
            time.sleep(2)

            # Generate logs from all services
            self.log_generator.logger.info("Main app started")
            auth_generator.logger.info("Authentication service ready")
            api_generator.logger.info("API service ready")

            time.sleep(1)

            # Verify all services are registered
            response = requests.get(f"{self.hub_url}/system")
            stats = response.json()
            services = stats["client_stats"]["services"]

            expected_services = ["e2e-test-app", "auth-service", "api-service"]
            for service in expected_services:
                assert (
                    service in services
                ), f"Service {service} not found in hub"

        finally:
            auth_generator.stop()
            api_generator.stop()


# Utility function for manual testing
def run_manual_test():
    """Run a manual test to verify everything works."""
    print("Starting manual E2E test...")

    test = TestMohnitorE2E()
    test.setup_method()

    try:
        print("Testing complete E2E flow...")
        test.test_complete_e2e_flow()
        print("✓ E2E flow works")

        print("Testing log generation...")
        test.test_log_generation_and_capture()
        print("✓ Log generation works")

        print("Testing continuous logging...")
        test.test_continuous_logging_performance()
        print("✓ Continuous logging works")

        print("All E2E tests passed!")
        print(f"Mohnitor UI available at: http://127.0.0.1:17361")

    except Exception as e:
        print(f"Test failed: {e}")
        raise
    finally:
        test.teardown_method()


if __name__ == "__main__":
    run_manual_test()
