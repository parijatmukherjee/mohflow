"""
Performance optimization utilities for Mohnitor.

Provides caching, batching, and memory optimization features.
"""

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any
import weakref


class LogEventCache:
    """LRU cache for serialized log events to avoid repeated JSON serialization."""

    def __init__(self, max_size: int = 10000):
        self.cache: Dict[str, str] = {}
        self.access_order: deque = deque()
        self.max_size = max_size

    def get(self, event_key: str) -> Optional[str]:
        """Get cached serialized log event."""
        if event_key in self.cache:
            # Move to end (most recently used)
            self.access_order.remove(event_key)
            self.access_order.append(event_key)
            return self.cache[event_key]
        return None

    def put(self, event_key: str, serialized_event: str) -> None:
        """Cache a serialized log event."""
        if event_key in self.cache:
            # Update existing
            self.access_order.remove(event_key)
        elif len(self.cache) >= self.max_size:
            # Remove least recently used
            oldest = self.access_order.popleft()
            del self.cache[oldest]

        self.cache[event_key] = serialized_event
        self.access_order.append(event_key)

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()
        self.access_order.clear()


class MessageBatcher:
    """Batches multiple log events into single WebSocket messages for better performance."""

    def __init__(self, batch_size: int = 50, max_delay_ms: int = 100):
        self.batch_size = batch_size
        self.max_delay_ms = max_delay_ms
        self.pending_messages: List[Dict[str, Any]] = []
        self.last_batch_time = time.time()
        self.subscribers: Set[Any] = set()  # Weak references to websockets

    def add_message(self, message: Dict[str, Any]) -> None:
        """Add a message to the current batch."""
        self.pending_messages.append(message)

        # Send batch if size threshold reached
        if len(self.pending_messages) >= self.batch_size:
            asyncio.create_task(self._send_batch())

    async def _send_batch(self) -> None:
        """Send the current batch to all subscribers."""
        if not self.pending_messages:
            return

        batch = {
            "type": "batch",
            "events": self.pending_messages,
            "count": len(self.pending_messages),
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

        batch_json = json.dumps(batch)

        # Send to all active subscribers
        disconnected = set()
        for ws_ref in self.subscribers:
            ws = ws_ref() if hasattr(ws_ref, "__call__") else ws_ref
            if ws is None:
                disconnected.add(ws_ref)
                continue

            try:
                await ws.send_text(batch_json)
            except Exception:
                disconnected.add(ws_ref)

        # Clean up disconnected subscribers
        self.subscribers -= disconnected

        # Reset batch
        self.pending_messages.clear()
        self.last_batch_time = time.time()

    def add_subscriber(self, websocket) -> None:
        """Add a WebSocket subscriber."""
        self.subscribers.add(weakref.ref(websocket))

    def remove_subscriber(self, websocket) -> None:
        """Remove a WebSocket subscriber."""
        to_remove = set()
        for ws_ref in self.subscribers:
            ws = ws_ref() if hasattr(ws_ref, "__call__") else ws_ref
            if ws is None or ws == websocket:
                to_remove.add(ws_ref)
        self.subscribers -= to_remove

    async def start_timer(self) -> None:
        """Start the timer-based batch sending."""
        while True:
            await asyncio.sleep(self.max_delay_ms / 1000.0)

            # Send batch if max delay exceeded
            current_time = time.time()
            if (
                self.pending_messages
                and (current_time - self.last_batch_time) * 1000
                >= self.max_delay_ms
            ):
                await self._send_batch()


class MemoryOptimizer:
    """Optimizes memory usage for log storage."""

    @staticmethod
    def estimate_event_size(event) -> int:
        """Estimate memory size of a log event in bytes."""
        # Rough estimation based on string lengths
        size = 200  # Base overhead
        size += len(event.message) * 2  # Unicode overhead
        size += len(event.service) * 2
        size += len(event.logger) * 2

        if hasattr(event, "context") and event.context:
            size += len(str(event.context)) * 2

        if hasattr(event, "trace_id") and event.trace_id:
            size += len(event.trace_id) * 2

        return size

    @staticmethod
    def optimize_buffer_size(
        target_memory_mb: int, avg_event_size_bytes: int
    ) -> int:
        """Calculate optimal buffer size for target memory usage."""
        target_bytes = target_memory_mb * 1024 * 1024
        return max(1000, target_bytes // avg_event_size_bytes)

    @staticmethod
    def compress_old_events(events: deque, keep_recent: int = 1000) -> deque:
        """Compress older events by removing less important fields."""
        if len(events) <= keep_recent:
            return events

        # Keep recent events full, compress older ones
        compressed = deque(maxlen=events.maxlen)
        total_events = len(events)

        for i, event in enumerate(events):
            if i >= total_events - keep_recent:
                # Keep recent events unchanged
                compressed.append(event)
            else:
                # Create compressed version
                compressed_event = type(event)(
                    timestamp=event.timestamp,
                    level=event.level,
                    service=event.service,
                    message=(
                        event.message[:200] + "..."
                        if len(event.message) > 200
                        else event.message
                    ),
                    logger=event.logger,
                )
                compressed.append(compressed_event)

        return compressed


class PerformanceMonitor:
    """Monitors and reports performance metrics."""

    def __init__(self):
        self.metrics = {
            "events_processed": 0,
            "events_dropped": 0,
            "broadcast_latency_ms": deque(maxlen=1000),
            "memory_usage_mb": 0,
            "websocket_connections": 0,
            "events_per_second": 0,
        }
        self.start_time = time.time()
        self.last_count = 0

    def record_event_processed(self) -> None:
        """Record that an event was processed."""
        self.metrics["events_processed"] += 1

    def record_event_dropped(self) -> None:
        """Record that an event was dropped."""
        self.metrics["events_dropped"] += 1

    def record_broadcast_latency(self, latency_ms: float) -> None:
        """Record WebSocket broadcast latency."""
        self.metrics["broadcast_latency_ms"].append(latency_ms)

    def update_memory_usage(self, usage_mb: float) -> None:
        """Update memory usage metric."""
        self.metrics["memory_usage_mb"] = usage_mb

    def update_connection_count(self, count: int) -> None:
        """Update WebSocket connection count."""
        self.metrics["websocket_connections"] = count

    def calculate_throughput(self) -> float:
        """Calculate events per second throughput."""
        current_time = time.time()
        elapsed = current_time - self.start_time

        if elapsed > 0:
            current_count = self.metrics["events_processed"]
            eps = (current_count - self.last_count) / max(1, elapsed)
            self.metrics["events_per_second"] = eps
            self.last_count = current_count
            self.start_time = current_time
            return eps
        return 0.0

    def get_latency_percentiles(self) -> Dict[str, float]:
        """Get latency percentiles."""
        latencies = list(self.metrics["broadcast_latency_ms"])
        if not latencies:
            return {"p50": 0, "p95": 0, "p99": 0}

        latencies.sort()
        n = len(latencies)

        return {
            "p50": latencies[int(n * 0.5)] if n > 0 else 0,
            "p95": latencies[int(n * 0.95)] if n > 0 else 0,
            "p99": latencies[int(n * 0.99)] if n > 0 else 0,
        }

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        latency_stats = self.get_latency_percentiles()
        throughput = self.calculate_throughput()

        return {
            "throughput": {
                "events_per_second": throughput,
                "total_processed": self.metrics["events_processed"],
                "total_dropped": self.metrics["events_dropped"],
                "drop_rate": (
                    self.metrics["events_dropped"]
                    / max(
                        1,
                        self.metrics["events_processed"]
                        + self.metrics["events_dropped"],
                    )
                ),
            },
            "latency": latency_stats,
            "memory": {
                "usage_mb": self.metrics["memory_usage_mb"],
                "efficiency": self.metrics["events_processed"]
                / max(1, self.metrics["memory_usage_mb"]),
            },
            "connections": {
                "active_websockets": self.metrics["websocket_connections"]
            },
        }


# Global performance instances for the hub
event_cache = LogEventCache()
message_batcher = MessageBatcher()
memory_optimizer = MemoryOptimizer()
performance_monitor = PerformanceMonitor()
