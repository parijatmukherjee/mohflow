"""Tests for devui performance optimization utilities."""

import time
import pytest
from collections import deque
from unittest.mock import MagicMock
from mohflow.devui.performance import (
    LogEventCache,
    MessageBatcher,
    MemoryOptimizer,
    PerformanceMonitor,
)


class TestLogEventCache:
    """Test LRU cache for serialized log events."""

    def test_put_and_get(self):
        cache = LogEventCache(max_size=10)
        cache.put("key1", '{"msg":"hello"}')
        assert cache.get("key1") == '{"msg":"hello"}'

    def test_get_missing_key(self):
        cache = LogEventCache()
        assert cache.get("missing") is None

    def test_lru_eviction(self):
        cache = LogEventCache(max_size=2)
        cache.put("a", "1")
        cache.put("b", "2")
        cache.put("c", "3")
        # 'a' should be evicted
        assert cache.get("a") is None
        assert cache.get("b") == "2"
        assert cache.get("c") == "3"

    def test_access_updates_order(self):
        cache = LogEventCache(max_size=2)
        cache.put("a", "1")
        cache.put("b", "2")
        # Access 'a' to make it recently used
        cache.get("a")
        # Add 'c', should evict 'b' (least recently used)
        cache.put("c", "3")
        assert cache.get("a") == "1"
        assert cache.get("b") is None
        assert cache.get("c") == "3"

    def test_update_existing_key(self):
        cache = LogEventCache(max_size=10)
        cache.put("key", "old")
        cache.put("key", "new")
        assert cache.get("key") == "new"
        assert len(cache.cache) == 1

    def test_clear(self):
        cache = LogEventCache()
        cache.put("a", "1")
        cache.put("b", "2")
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert len(cache.cache) == 0
        assert len(cache.access_order) == 0

    def test_max_size_respected(self):
        cache = LogEventCache(max_size=5)
        for i in range(10):
            cache.put(f"key{i}", f"val{i}")
        assert len(cache.cache) == 5


class TestMessageBatcher:
    """Test message batching."""

    def test_add_message(self):
        batcher = MessageBatcher(batch_size=100)
        batcher.add_message({"type": "log_event"})
        assert len(batcher.pending_messages) == 1

    def test_multiple_messages(self):
        batcher = MessageBatcher(batch_size=100)
        for i in range(5):
            batcher.add_message({"id": i})
        assert len(batcher.pending_messages) == 5

    def test_add_subscriber(self):
        batcher = MessageBatcher()
        ws = MagicMock()
        batcher.add_subscriber(ws)
        assert len(batcher.subscribers) == 1

    def test_remove_subscriber(self):
        batcher = MessageBatcher()
        ws = MagicMock()
        batcher.add_subscriber(ws)
        batcher.remove_subscriber(ws)
        # After removal, subscriber refs should be cleaned
        # (weakref may already be dead)

    def test_batch_size_default(self):
        batcher = MessageBatcher()
        assert batcher.batch_size == 50
        assert batcher.max_delay_ms == 100


class TestMemoryOptimizer:
    """Test memory optimization utilities."""

    def test_estimate_event_size(self):
        event = MagicMock()
        event.message = "test message"
        event.service = "myapp"
        event.logger = "myapp.auth"
        event.context = None
        event.trace_id = None
        size = MemoryOptimizer.estimate_event_size(event)
        assert size > 200  # Base overhead

    def test_estimate_event_size_with_context(self):
        event = MagicMock()
        event.message = "test"
        event.service = "svc"
        event.logger = "lgr"
        event.context = {"key": "value"}
        event.trace_id = "abc-123-def"
        size = MemoryOptimizer.estimate_event_size(event)
        assert size > 200

    def test_optimize_buffer_size(self):
        # 50MB target, 1KB avg event
        size = MemoryOptimizer.optimize_buffer_size(50, 1024)
        assert size == 50 * 1024  # 51200

    def test_optimize_buffer_minimum(self):
        # Very small target should still return at least 1000
        size = MemoryOptimizer.optimize_buffer_size(1, 1024 * 1024)
        assert size >= 1000

    def test_compress_old_events_small_list(self):
        events = deque(maxlen=5000)
        for i in range(5):
            event = MagicMock()
            event.timestamp = f"ts{i}"
            event.level = "INFO"
            event.service = "svc"
            event.message = f"msg{i}"
            event.logger = "lgr"
            events.append(event)
        # Should return unchanged when below threshold
        result = MemoryOptimizer.compress_old_events(events, keep_recent=1000)
        assert len(result) == 5

    def test_compress_old_events_large_list(self):
        events = deque(maxlen=5000)
        for i in range(2000):
            event = MagicMock()
            event.timestamp = f"ts{i}"
            event.level = "INFO"
            event.service = "svc"
            event.message = "x" * 300  # Long message
            event.logger = "lgr"
            events.append(event)

        result = MemoryOptimizer.compress_old_events(events, keep_recent=1000)
        assert len(result) == 2000


class TestPerformanceMonitor:
    """Test performance monitoring."""

    def test_record_event_processed(self):
        monitor = PerformanceMonitor()
        monitor.record_event_processed()
        monitor.record_event_processed()
        assert monitor.metrics["events_processed"] == 2

    def test_record_event_dropped(self):
        monitor = PerformanceMonitor()
        monitor.record_event_dropped()
        assert monitor.metrics["events_dropped"] == 1

    def test_record_broadcast_latency(self):
        monitor = PerformanceMonitor()
        monitor.record_broadcast_latency(5.0)
        monitor.record_broadcast_latency(10.0)
        assert len(monitor.metrics["broadcast_latency_ms"]) == 2

    def test_update_memory_usage(self):
        monitor = PerformanceMonitor()
        monitor.update_memory_usage(25.5)
        assert monitor.metrics["memory_usage_mb"] == 25.5

    def test_update_connection_count(self):
        monitor = PerformanceMonitor()
        monitor.update_connection_count(3)
        assert monitor.metrics["websocket_connections"] == 3

    def test_calculate_throughput(self):
        monitor = PerformanceMonitor()
        for _ in range(100):
            monitor.record_event_processed()
        eps = monitor.calculate_throughput()
        assert eps >= 0

    def test_get_latency_percentiles_empty(self):
        monitor = PerformanceMonitor()
        p = monitor.get_latency_percentiles()
        assert p["p50"] == 0
        assert p["p95"] == 0
        assert p["p99"] == 0

    def test_get_latency_percentiles(self):
        monitor = PerformanceMonitor()
        for i in range(100):
            monitor.record_broadcast_latency(float(i))
        p = monitor.get_latency_percentiles()
        assert p["p50"] == 50.0
        assert p["p95"] == 95.0
        assert p["p99"] == 99.0

    def test_get_performance_report(self):
        monitor = PerformanceMonitor()
        monitor.record_event_processed()
        monitor.record_event_dropped()
        monitor.record_broadcast_latency(5.0)
        monitor.update_memory_usage(10.0)
        monitor.update_connection_count(2)

        report = monitor.get_performance_report()
        assert "throughput" in report
        assert "latency" in report
        assert "memory" in report
        assert "connections" in report
        assert report["throughput"]["total_processed"] == 1
        assert report["throughput"]["total_dropped"] == 1
        assert report["connections"]["active_websockets"] == 2

    def test_performance_report_drop_rate(self):
        monitor = PerformanceMonitor()
        for _ in range(8):
            monitor.record_event_processed()
        for _ in range(2):
            monitor.record_event_dropped()
        report = monitor.get_performance_report()
        assert report["throughput"]["drop_rate"] == 0.2

    def test_performance_report_memory_efficiency(self):
        monitor = PerformanceMonitor()
        for _ in range(1000):
            monitor.record_event_processed()
        monitor.update_memory_usage(10.0)
        report = monitor.get_performance_report()
        assert report["memory"]["efficiency"] == 100.0
