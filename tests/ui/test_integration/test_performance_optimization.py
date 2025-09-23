#!/usr/bin/env python3
"""
Test performance optimizations for Mohnitor.

Tests caching, batching, memory optimization, and performance monitoring.
"""

import sys
import asyncio
import time
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_event_cache():
    """Test log event caching functionality."""
    print("🧪 Testing event cache...")

    try:
        from mohflow.devui.performance import LogEventCache

        cache = LogEventCache(max_size=100)

        # Test cache operations
        cache.put("test_key", "test_value")
        assert cache.get("test_key") == "test_value"

        # Test LRU eviction
        for i in range(150):
            cache.put(f"key_{i}", f"value_{i}")

        # First key should be evicted
        assert cache.get("test_key") is None
        assert cache.get("key_149") == "value_149"

        print("✅ Event cache working correctly")
        return True

    except Exception as e:
        print(f"❌ Event cache test failed: {e}")
        return False


@pytest.mark.asyncio
async def test_message_batcher():
    """Test message batching functionality."""
    print("🧪 Testing message batcher...")

    try:
        from mohflow.devui.performance import MessageBatcher

        batcher = MessageBatcher(batch_size=3, max_delay_ms=50)
        received_messages = []

        class MockWebSocket:
            async def send_text(self, message):
                received_messages.append(message)

        mock_ws = MockWebSocket()
        batcher.add_subscriber(mock_ws)

        # Add messages to trigger batch
        for i in range(5):
            batcher.add_message({"type": "test", "id": i})

        # Wait for batch to be sent
        await asyncio.sleep(0.1)

        # Should have at least one batch
        assert len(received_messages) > 0
        print(f"✅ Message batcher sent {len(received_messages)} batches")
        return True

    except Exception as e:
        print(f"❌ Message batcher test failed: {e}")
        return False


@pytest.mark.asyncio
async def test_memory_optimizer():
    """Test memory optimization functionality."""
    print("🧪 Testing memory optimizer...")

    try:
        from mohflow.devui.performance import MemoryOptimizer
        from mohflow.devui.types import LogEvent
        from datetime import datetime, timezone

        optimizer = MemoryOptimizer()

        # Create test event
        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            service="test-service",
            message="Test message with some content",
            logger="test.logger",
        )

        # Test size estimation
        size = optimizer.estimate_event_size(event)
        assert size > 0
        print(f"✅ Event size estimation: {size} bytes")

        # Test buffer size optimization
        optimal_size = optimizer.optimize_buffer_size(
            50, 1024
        )  # 50MB, 1KB per event
        expected = (50 * 1024 * 1024) // 1024  # Should be ~50K events
        assert optimal_size > 1000
        print(f"✅ Optimal buffer size: {optimal_size} events")

        return True

    except Exception as e:
        print(f"❌ Memory optimizer test failed: {e}")
        return False


@pytest.mark.asyncio
async def test_performance_monitor():
    """Test performance monitoring functionality."""
    print("🧪 Testing performance monitor...")

    try:
        from mohflow.devui.performance import PerformanceMonitor

        monitor = PerformanceMonitor()

        # Record some metrics
        for i in range(100):
            monitor.record_event_processed()
            monitor.record_broadcast_latency(50 + i % 20)  # 50-70ms

        for i in range(5):
            monitor.record_event_dropped()

        monitor.update_memory_usage(25.5)
        monitor.update_connection_count(10)

        # Get performance report
        report = monitor.get_performance_report()

        assert "throughput" in report
        assert "latency" in report
        assert "memory" in report

        # Check latency percentiles
        latency_stats = monitor.get_latency_percentiles()
        assert "p50" in latency_stats
        assert "p95" in latency_stats

        print(f"✅ Performance report generated")
        print(
            f"  📊 Throughput: {report['throughput']['events_per_second']:.1f} eps"
        )
        print(f"  ⏱️  P50 latency: {latency_stats['p50']:.1f}ms")
        print(f"  ⏱️  P95 latency: {latency_stats['p95']:.1f}ms")
        print(f"  💾 Memory usage: {report['memory']['usage_mb']:.1f}MB")

        return True

    except Exception as e:
        print(f"❌ Performance monitor test failed: {e}")
        return False


@pytest.mark.asyncio
async def test_integrated_performance():
    """Test integrated performance optimizations."""
    print("🧪 Testing integrated performance...")

    try:
        from mohflow.devui.performance import (
            event_cache,
            message_batcher,
            memory_optimizer,
            performance_monitor,
        )
        from mohflow.devui.types import LogEvent
        from datetime import datetime, timezone
        import json

        # Simulate high-volume log processing
        events_processed = 0
        start_time = time.time()

        for i in range(1000):
            # Create event
            event = LogEvent(
                timestamp=datetime.now(timezone.utc),
                level=["DEBUG", "INFO", "WARN", "ERROR"][i % 4],
                service=f"service-{i % 10}",
                message=f"Message {i} with some test content",
                logger="test.logger",
            )

            # Test caching
            event_key = f"{event.service}:{event.level}:{hash(event.message)}"
            cached = event_cache.get(event_key)

            if not cached:
                cached = json.dumps(event.to_dict())
                event_cache.put(event_key, cached)

            # Test size estimation
            size = memory_optimizer.estimate_event_size(event)

            # Record metrics
            performance_monitor.record_event_processed()
            performance_monitor.record_broadcast_latency(10 + (i % 50))

            events_processed += 1

        end_time = time.time()
        duration = end_time - start_time

        print(f"✅ Processed {events_processed} events in {duration:.2f}s")
        print(f"✅ Throughput: {events_processed / duration:.0f} events/sec")

        # Check if we meet performance targets
        throughput = events_processed / duration
        if throughput >= 5000:
            print("🎯 ✅ Throughput target met (≥5k events/sec)")
        else:
            print(
                f"🎯 ⚠️  Throughput below target: {throughput:.0f} < 5000 events/sec"
            )

        # Check latency targets
        latency_stats = performance_monitor.get_latency_percentiles()
        if latency_stats["p50"] <= 150:
            print("🎯 ✅ P50 latency target met (≤150ms)")
        else:
            print(
                f"🎯 ⚠️  P50 latency above target: {latency_stats['p50']:.1f} > 150ms"
            )

        if latency_stats["p95"] <= 300:
            print("🎯 ✅ P95 latency target met (≤300ms)")
        else:
            print(
                f"🎯 ⚠️  P95 latency above target: {latency_stats['p95']:.1f} > 300ms"
            )

        return True

    except Exception as e:
        print(f"❌ Integrated performance test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all performance tests."""
    print("🚀 Testing Mohnitor performance optimizations...")

    tests = [
        test_event_cache,
        test_message_batcher,
        test_memory_optimizer,
        test_performance_monitor,
        test_integrated_performance,
    ]

    passed = 0
    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")

    print(f"\n📊 Performance Tests: {passed}/{len(tests)} passed")

    if passed == len(tests):
        print("🎉 All performance optimization tests passed!")
        return True
    else:
        print("⚠️  Some performance tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
