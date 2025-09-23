"""
Test basic Mohnitor integration scenarios.
"""

import pytest
import sys
import time
from mohflow import get_logger


class TestMohnitorIntegration:
    """Test Mohnitor integration scenarios."""

    def test_mohnitor_enable_without_server(self):
        """Test that enable_mohnitor works gracefully without server."""
        # This should not crash even if no hub server is running
        logger = get_logger("test-service", enable_mohnitor=True)

        # Test basic logging
        logger.info("Test message", user_id="123")
        logger.error("Test error", error_code="E001")
        logger.warning("Test warning", memory_usage="85%")

        # Should still be a functional logger
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "warning")

    def test_mohnitor_with_context_data(self):
        """Test Mohnitor with various context data."""
        logger = get_logger("context-test-service", enable_mohnitor=True)

        # Test with various data types
        logger.info(
            "User action",
            user_id=12345,
            action="login",
            success=True,
            metadata={"ip": "192.168.1.1", "agent": "test-browser"},
        )

        logger.error(
            "Payment failed",
            payment_id="pay_123",
            amount=99.99,
            currency="USD",
            error_details={"code": "insufficient_funds", "retry": False},
        )

    def test_mohnitor_performance_logging(self):
        """Test Mohnitor with performance-related logging."""
        logger = get_logger("perf-test-service", enable_mohnitor=True)

        # Simulate performance logging
        start_time = time.time()
        time.sleep(0.01)  # Small delay
        end_time = time.time()

        logger.info(
            "API request completed",
            endpoint="/api/users",
            method="GET",
            duration_ms=int((end_time - start_time) * 1000),
            status_code=200,
        )

        logger.warning(
            "Slow query detected",
            query="SELECT * FROM large_table",
            duration_ms=2500,
            threshold_ms=1000,
        )

    def test_mohnitor_with_trace_correlation(self):
        """Test Mohnitor with trace correlation."""
        logger = get_logger("trace-test-service", enable_mohnitor=True)

        trace_id = "trace-abc-123"

        # Simulate distributed trace
        logger.info("Request received", trace_id=trace_id, span_id="span-1")
        logger.debug(
            "Database query",
            trace_id=trace_id,
            span_id="span-2",
            parent_span="span-1",
        )
        logger.info(
            "Response sent", trace_id=trace_id, span_id="span-1", status=200
        )

    def test_mohnitor_error_scenarios(self):
        """Test Mohnitor with various error scenarios."""
        logger = get_logger("error-test-service", enable_mohnitor=True)

        # Test different error types
        logger.error(
            "Validation error",
            field="email",
            value="invalid-email",
            error_type="validation",
        )

        logger.error(
            "Database connection failed",
            host="db.example.com",
            port=5432,
            retry_count=3,
            error_type="connection",
        )

        logger.critical(
            "System out of memory",
            memory_usage="98%",
            available_mb=50,
            error_type="resource",
        )


def test_mohnitor_types_serialization():
    """Test that our types work properly."""
    try:
        from mohflow.devui.types import LogEvent, HubDescriptor
        from datetime import datetime, timezone

        # Test LogEvent creation and serialization
        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Test message",
            logger="test.logger",
        )

        data = event.to_dict()
        assert isinstance(data, dict)
        assert data["level"] == "INFO"

        # Test HubDescriptor creation
        descriptor = HubDescriptor(
            host="127.0.0.1",
            port=17361,
            pid=12345,
            token=None,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

        desc_data = descriptor.to_dict()
        assert isinstance(desc_data, dict)
        assert desc_data["host"] == "127.0.0.1"

        print("✅ Mohnitor types serialization works correctly")
        return True

    except Exception as e:
        print(f"❌ Types serialization failed: {e}")
        return False


def test_mohnitor_discovery():
    """Test discovery without requiring server."""
    try:
        from mohflow.devui.discovery import discover_hub

        # Should gracefully handle no server
        result = discover_hub()

        print(f"✅ Discovery works gracefully: {result}")
        return True

    except Exception as e:
        print(f"❌ Discovery failed: {e}")
        return False


def main():
    """Run integration tests."""
    print("🧪 Testing Mohnitor integration...")

    tests = [
        test_mohnitor_types_serialization,
        test_mohnitor_discovery,
    ]

    passed = 0
    for test in tests:
        if test():
            passed += 1

    print(f"\n📊 Integration Tests: {passed}/{len(tests)} passed")

    if passed == len(tests):
        print("🎉 All integration tests passed!")
        return True
    else:
        print("⚠️  Some integration tests failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
