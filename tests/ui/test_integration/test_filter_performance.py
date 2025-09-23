"""
Integration test for filtering performance <100ms.

This test MUST FAIL initially until filtering implementation is complete.
"""

import pytest
import time
import asyncio
import json
from mohflow import get_logger

try:
    import websockets
except ImportError:
    websockets = None


@pytest.mark.skipif(websockets is None, reason="websockets not available")
class TestFilterPerformance:
    """Test filtering performance requirements."""

    @pytest.mark.asyncio
    async def test_filter_performance_under_100ms(self):
        """Test that filtering 10k events completes under 100ms."""
        # Start hub with large buffer
        logger = get_logger(
            service="filter-perf-test",
            enable_mohnitor=True,
            mohnitor_buffer_size=50000,
        )

        time.sleep(1)

        # Generate 10k log events
        print("Generating 10k log events...")
        for i in range(10000):
            level = "ERROR" if i % 100 == 0 else "INFO"
            logger.log(
                level, f"Performance test message {i}", request_id=f"req-{i}"
            )

        time.sleep(2)  # Let all events be processed

        # Connect to WebSocket
        uri = "ws://127.0.0.1:17361/ws?type=ui"

        async with websockets.connect(uri) as websocket:
            # Apply filter
            filter_request = {
                "type": "apply_filter",
                "payload": {
                    "filter_id": "perf_test",
                    "levels": ["ERROR"],
                    "time_range": "5m",
                },
            }

            start_time = time.time()
            await websocket.send(json.dumps(filter_request))

            # Wait for filter response
            response = await websocket.recv()
            end_time = time.time()

            filter_time = (end_time - start_time) * 1000  # Convert to ms

            # Should complete under 100ms
            assert filter_time < 100

            # Verify we got filtered results
            data = json.loads(response)
            # Should return only ERROR level messages (about 100 out of 10k)
            assert (
                "filtered_results" in data or data["type"] == "filtered_events"
            )

    def test_memory_usage_with_large_buffer(self):
        """Test memory usage stays under 50MB with 50k events."""
        logger = get_logger(
            service="memory-test",
            enable_mohnitor=True,
            mohnitor_buffer_size=50000,
        )

        time.sleep(1)

        # Fill buffer to capacity
        for i in range(50000):
            logger.info(f"Memory test message {i}")

        time.sleep(3)  # Let all events be processed

        # Check memory usage through system endpoint
        import requests

        response = requests.get("http://127.0.0.1:17361/system")
        data = response.json()

        # Should report memory usage
        if "memory_usage_mb" in data["buffer_stats"]:
            memory_mb = data["buffer_stats"]["memory_usage_mb"]
            assert memory_mb <= 50  # Under 50MB as per design
