"""
Test application that generates logs for browser automation testing.
"""

import time
import threading
from mohflow import get_logger


class LogGenerator:
    """Generates various types of logs for testing the UI."""

    def __init__(self, service_name="test-app"):
        self.logger = get_logger(service=service_name, enable_mohnitor=True)
        self.running = False
        self.thread = None

    def start(self):
        """Start generating logs in background."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._generate_logs, daemon=True)
        self.thread.start()

        # Give it a moment to start the hub
        time.sleep(2)

    def stop(self):
        """Stop generating logs."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def _generate_logs(self):
        """Generate various types of log messages."""
        counter = 0

        while self.running:
            counter += 1

            # Generate different types of logs
            if counter % 5 == 0:
                self.logger.error(
                    "Database connection failed",
                    error_code="DB001",
                    trace_id=f"trace-{counter}",
                    user_id="user123",
                )
            elif counter % 3 == 0:
                self.logger.warning(
                    "High memory usage detected",
                    memory_usage="85%",
                    trace_id=f"trace-{counter}",
                )
            elif counter % 2 == 0:
                self.logger.info(
                    "User login successful",
                    user_id="user123",
                    ip_address="192.168.1.100",
                    trace_id=f"trace-{counter}",
                )
            else:
                self.logger.debug(
                    "Processing request",
                    request_id=f"req-{counter}",
                    trace_id=f"trace-{counter}",
                )

            time.sleep(0.5)  # Generate log every 500ms

    def generate_test_scenarios(self):
        """Generate specific test scenarios."""
        # Authentication scenario
        self.logger.info(
            "User authentication started",
            user_id="testuser",
            trace_id="auth-001",
        )
        time.sleep(0.1)
        self.logger.info(
            "Password validated", user_id="testuser", trace_id="auth-001"
        )
        time.sleep(0.1)
        self.logger.info(
            "Session created",
            user_id="testuser",
            session_id="sess-123",
            trace_id="auth-001",
        )

        # Error scenario
        self.logger.error(
            "Payment processing failed",
            payment_id="pay-456",
            error="Card declined",
            trace_id="payment-001",
        )

        # Performance scenario
        self.logger.warning(
            "Slow query detected",
            query_time="2.5s",
            query="SELECT * FROM users",
            trace_id="perf-001",
        )

        # API scenario
        self.logger.info(
            "API request received",
            endpoint="/api/users",
            method="GET",
            trace_id="api-001",
        )
        self.logger.info("Database query executed", trace_id="api-001")
        self.logger.info("Response sent", status_code=200, trace_id="api-001")


if __name__ == "__main__":
    # Run standalone for manual testing
    generator = LogGenerator()
    generator.start()

    # Generate some test scenarios
    time.sleep(1)
    generator.generate_test_scenarios()

    print(
        "Test app running. Mohnitor UI should be available at http://127.0.0.1:17361"
    )
    print("Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        generator.stop()
        print("Test app stopped.")
