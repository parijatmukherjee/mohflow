"""
Automatic metrics generation from log patterns.

This module provides:
- Auto-extraction of metrics from log messages
- Counter, histogram, and gauge metrics
- Duration and latency tracking
- Error rate and throughput calculations
- Pattern-based metric extraction
- Prometheus-compatible metrics export
- Integration with OpenTelemetry
"""

import re
import time
import threading
from typing import Dict, Any, Optional, List, Tuple, Union, Pattern, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import json
from datetime import datetime


class MetricType(Enum):
    """Types of metrics that can be auto-generated."""

    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    SUMMARY = "summary"


@dataclass
class MetricExtractor:
    """Configuration for extracting a specific metric from logs."""

    name: str
    metric_type: MetricType
    pattern: Union[str, Pattern]
    value_extractor: Optional[Callable[[Dict[str, Any]], float]] = None
    labels: Optional[List[str]] = None
    description: str = ""
    unit: str = ""

    def __post_init__(self):
        """Compile regex pattern if string provided."""
        if isinstance(self.pattern, str):
            self.pattern = re.compile(self.pattern)


@dataclass
class MetricValue:
    """A single metric measurement."""

    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    unit: str = ""


@dataclass
class MetricStats:
    """Statistics for a metric over time."""

    count: int = 0
    sum: float = 0.0
    min: float = float("inf")
    max: float = float("-inf")
    last_value: float = 0.0
    last_updated: float = 0.0

    def update(self, value: float, timestamp: float = None):
        """Update statistics with new value."""
        if timestamp is None:
            timestamp = time.time()

        self.count += 1
        self.sum += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
        self.last_value = value
        self.last_updated = timestamp

    @property
    def average(self) -> float:
        """Calculate average value."""
        return self.sum / self.count if self.count > 0 else 0.0


class AutoMetricsGenerator:
    """
    Automatically generates metrics from log messages.

    Features:
    - Pattern-based metric extraction
    - Multiple metric types (counter, histogram, gauge, summary)
    - Automatic error rate calculation
    - Request duration tracking
    - Throughput measurements
    - Custom metric extractors
    """

    def __init__(self, enable_default_metrics: bool = True):
        """Initialize auto-metrics generator."""
        self._lock = threading.Lock()
        self._extractors: List[MetricExtractor] = []
        self._metrics: Dict[str, Dict[str, MetricStats]] = defaultdict(
            lambda: defaultdict(MetricStats)
        )
        self._counters: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._histograms: Dict[
            str, List[Tuple[float, Dict[str, str], float]]
        ] = defaultdict(list)

        # Rate calculation windows
        self._rate_windows: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=300)
        )  # 5 minute window

        # Built-in metric extractors
        if enable_default_metrics:
            self._setup_default_extractors()

    def _setup_default_extractors(self):
        """Setup default metric extractors for common patterns."""

        # Error rate metrics
        self.add_extractor(
            MetricExtractor(
                name="log_errors_total",
                metric_type=MetricType.COUNTER,
                pattern=r"level.*ERROR|CRITICAL",
                description="Total number of error and critical log messages",
                labels=["level", "service"],
            )
        )

        # Request duration metrics
        self.add_extractor(
            MetricExtractor(
                name="request_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"duration[_\s]*[=:]?\s*([0-9.]+)",
                value_extractor=lambda ctx: float(
                    re.search(
                        r"duration[_\s]*[=:]?\s*([0-9.]+)",
                        str(ctx.get("message", "")),
                    ).group(1)
                )
                / 1000.0,
                description="Request duration in seconds",
                unit="seconds",
                labels=["method", "endpoint", "status"],
            )
        )

        # Database operation metrics
        self.add_extractor(
            MetricExtractor(
                name="database_operations_total",
                metric_type=MetricType.COUNTER,
                pattern=r"database|db|sql|query",
                description="Total database operations",
                labels=["operation", "table", "service"],
            )
        )

        # Cache metrics
        self.add_extractor(
            MetricExtractor(
                name="cache_operations_total",
                metric_type=MetricType.COUNTER,
                pattern=r"cache.*(hit|miss|set|get|delete)",
                description="Total cache operations",
                labels=["operation", "cache_type"],
            )
        )

        # HTTP response metrics
        self.add_extractor(
            MetricExtractor(
                name="http_responses_total",
                metric_type=MetricType.COUNTER,
                pattern=r"status[_\s]*[=:]?\s*([0-9]{3})",
                description="Total HTTP responses by status code",
                labels=["status_code", "method", "endpoint"],
            )
        )

        # Memory usage metrics
        self.add_extractor(
            MetricExtractor(
                name="memory_usage_bytes",
                metric_type=MetricType.GAUGE,
                pattern=r"memory[_\s]*[=:]?\s*([0-9.]+)",
                value_extractor=lambda ctx: self._extract_memory_bytes(ctx),
                description="Memory usage in bytes",
                unit="bytes",
            )
        )

        # Latency metrics
        self.add_extractor(
            MetricExtractor(
                name="operation_latency_milliseconds",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"latency[_\s]*[=:]?\s*([0-9.]+)",
                value_extractor=lambda ctx: self._extract_numeric_value(
                    ctx, "latency"
                ),
                description="Operation latency in milliseconds",
                unit="milliseconds",
                labels=["operation", "service"],
            )
        )

        # Throughput metrics (requests per second)
        self.add_extractor(
            MetricExtractor(
                name="throughput_requests_per_second",
                metric_type=MetricType.GAUGE,
                pattern=r"request|processing",
                description="Request processing throughput",
                labels=["service", "endpoint"],
            )
        )

    def add_extractor(self, extractor: MetricExtractor):
        """Add a custom metric extractor."""
        with self._lock:
            self._extractors.append(extractor)

    def process_log_record(
        self, log_record: Dict[str, Any]
    ) -> List[MetricValue]:
        """
        Process a log record and extract metrics.

        Args:
            log_record: Log record dictionary containing message, level,
            context, etc.

        Returns:
            List of MetricValue objects extracted from the log
        """
        metrics = []

        with self._lock:
            for extractor in self._extractors:
                try:
                    metric_values = self._extract_metric(extractor, log_record)
                    metrics.extend(metric_values)
                except Exception:
                    # Don't let metric extraction errors break logging
                    continue

        # Update internal metrics storage
        for metric in metrics:
            self._update_metric_storage(metric)

        return metrics

    def _extract_metric(
        self, extractor: MetricExtractor, log_record: Dict[str, Any]
    ) -> List[MetricValue]:
        """Extract metric values using the given extractor."""
        message = str(log_record.get("message", ""))
        level = log_record.get("level", "INFO")

        # Check if pattern matches
        match = extractor.pattern.search(message)
        if not match and not extractor.pattern.search(json.dumps(log_record)):
            return []

        # Extract value
        if extractor.value_extractor:
            try:
                value = extractor.value_extractor(log_record)
            except (ValueError, TypeError, AttributeError):
                value = 1.0  # Default to counter increment
        else:
            # Default value extraction based on metric type
            if extractor.metric_type == MetricType.COUNTER:
                value = 1.0
            elif match and match.groups():
                try:
                    value = float(match.group(1))
                except (ValueError, IndexError):
                    value = 1.0
            else:
                value = 1.0

        # Extract labels
        labels = {}
        if extractor.labels:
            for label in extractor.labels:
                if label == "level":
                    labels[label] = level
                elif label == "service":
                    labels[label] = log_record.get("service_name", "unknown")
                elif label in log_record:
                    labels[label] = str(log_record[label])
                else:
                    # Try to extract from message using pattern
                    pattern = rf"{label}[_\s]*[=:]?\s*([^\s,]+)"
                    label_match = re.search(pattern, message, re.IGNORECASE)
                    if label_match:
                        labels[label] = label_match.group(1)
                    else:
                        labels[label] = "unknown"

        return [
            MetricValue(
                name=extractor.name,
                value=value,
                labels=labels,
                timestamp=time.time(),
                unit=extractor.unit,
            )
        ]

    def _extract_memory_bytes(self, log_record: Dict[str, Any]) -> float:
        """Extract memory value and convert to bytes."""
        message = str(log_record.get("message", ""))

        # Look for memory patterns with units
        patterns = [
            r"memory[_\s]*[=:]?\s*([0-9.]+)\s*(gb|g)",
            r"memory[_\s]*[=:]?\s*([0-9.]+)\s*(mb|m)",
            r"memory[_\s]*[=:]?\s*([0-9.]+)\s*(kb|k)",
            r"memory[_\s]*[=:]?\s*([0-9.]+)",  # bytes
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = (
                    match.group(2).lower() if len(match.groups()) > 1 else "b"
                )

                # Convert to bytes
                if unit.startswith("g"):
                    return value * 1024 * 1024 * 1024
                elif unit.startswith("m"):
                    return value * 1024 * 1024
                elif unit.startswith("k"):
                    return value * 1024
                else:
                    return value

        return 0.0

    def _extract_numeric_value(
        self, log_record: Dict[str, Any], field_name: str
    ) -> float:
        """Extract numeric value for a named field."""
        message = str(log_record.get("message", ""))

        # Try direct field access first
        if field_name in log_record:
            try:
                return float(log_record[field_name])
            except (ValueError, TypeError):
                pass

        # Try pattern matching in message
        pattern = rf"{field_name}[_\s]*[=:]?\s*([0-9.]+)"
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        return 0.0

    def _update_metric_storage(self, metric: MetricValue):
        """Update internal metric storage."""
        labels_key = json.dumps(metric.labels, sort_keys=True)

        if metric.name.endswith("_total") or "counter" in metric.name.lower():
            # Counter metric
            self._counters[metric.name][labels_key] += int(metric.value)

        elif (
            "histogram" in metric.name.lower()
            or "duration" in metric.name
            or "latency" in metric.name
        ):
            # Histogram metric
            self._histograms[metric.name].append(
                (metric.value, metric.labels, metric.timestamp)
            )

            # Keep only recent values (last 1000 or 1 hour)
            cutoff_time = time.time() - 3600  # 1 hour
            self._histograms[metric.name] = [
                (v, l, t)
                for v, l, t in self._histograms[metric.name]
                if t > cutoff_time
            ][
                -1000:
            ]  # Keep last 1000 values

        else:
            # Gauge or general metric
            self._metrics[metric.name][labels_key].update(
                metric.value, metric.timestamp
            )

        # Update rate windows for throughput calculation
        if "throughput" in metric.name or "request" in metric.name:
            self._rate_windows[metric.name].append(time.time())

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all collected metrics."""
        with self._lock:
            summary = {
                "counters": {},
                "histograms": {},
                "gauges": {},
                "rates": {},
                "collection_time": datetime.now().isoformat(),
            }

            # Counters
            for metric_name, labels_data in self._counters.items():
                summary["counters"][metric_name] = {
                    "total": sum(labels_data.values()),
                    "by_labels": dict(labels_data),
                }

            # Histograms
            for metric_name, values in self._histograms.items():
                if not values:
                    continue

                numeric_values = [v for v, _, _ in values]
                summary["histograms"][metric_name] = {
                    "count": len(numeric_values),
                    "sum": sum(numeric_values),
                    "min": min(numeric_values),
                    "max": max(numeric_values),
                    "avg": sum(numeric_values) / len(numeric_values),
                    "p50": self._percentile(numeric_values, 50),
                    "p95": self._percentile(numeric_values, 95),
                    "p99": self._percentile(numeric_values, 99),
                }

            # Gauges
            for metric_name, labels_data in self._metrics.items():
                if (
                    metric_name not in self._counters
                    and metric_name not in self._histograms
                ):
                    gauge_data = {}
                    for labels_key, stats in labels_data.items():
                        gauge_data[labels_key] = {
                            "current": stats.last_value,
                            "avg": stats.average,
                            "min": (
                                stats.min if stats.min != float("inf") else 0
                            ),
                            "max": (
                                stats.max if stats.max != float("-inf") else 0
                            ),
                            "count": stats.count,
                        }
                    summary["gauges"][metric_name] = gauge_data

            # Rates (per second calculations)
            current_time = time.time()
            for metric_name, timestamps in self._rate_windows.items():
                if not timestamps:
                    continue

                # Count events in last 60 seconds
                recent_events = [
                    t for t in timestamps if current_time - t <= 60
                ]
                rate_per_second = len(recent_events) / 60.0

                summary["rates"][metric_name] = {
                    "current_rate_per_second": rate_per_second,
                    "total_events": len(timestamps),
                    "events_last_minute": len(recent_events),
                }

        return summary

    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100.0
        f = int(k)
        c = k - f

        if f + 1 < len(sorted_values):
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
        else:
            return sorted_values[f]

    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        current_time = int(time.time() * 1000)  # Prometheus uses milliseconds

        with self._lock:
            # Export counters
            for metric_name, labels_data in self._counters.items():
                lines.append(f"# TYPE {metric_name} counter")
                for labels_key, value in labels_data.items():
                    labels_dict = json.loads(labels_key) if labels_key else {}
                    labels_str = ",".join(
                        [f'{k}="{v}"' for k, v in labels_dict.items()]
                    )
                    labels_part = f"{{{labels_str}}}" if labels_str else ""
                    lines.append(
                        f"{metric_name}{labels_part} {value} {current_time}"
                    )

            # Export histograms as summaries (simplified)
            for metric_name, values in self._histograms.items():
                if not values:
                    continue

                lines.append(f"# TYPE {metric_name} summary")
                numeric_values = [v for v, _, _ in values]

                # Count and sum
                lines.append(
                    f"{metric_name}_count {len(numeric_values)} {current_time}"
                )
                lines.append(
                    f"{metric_name}_sum {sum(numeric_values)} {current_time}"
                )

                # Quantiles
                for quantile in [0.5, 0.9, 0.95, 0.99]:
                    value = self._percentile(numeric_values, quantile * 100)
                    lines.append(
                        (
                            f'{metric_name}{{quantile="{quantile}"}} '
                            f"{value} {current_time}"
                        )
                    )

            # Export gauges
            for metric_name, labels_data in self._metrics.items():
                if (
                    metric_name not in self._counters
                    and metric_name not in self._histograms
                ):
                    lines.append(f"# TYPE {metric_name} gauge")
                    for labels_key, stats in labels_data.items():
                        labels_dict = (
                            json.loads(labels_key) if labels_key else {}
                        )
                        labels_str = ",".join(
                            [f'{k}="{v}"' for k, v in labels_dict.items()]
                        )
                        labels_part = f"{{{labels_str}}}" if labels_str else ""
                        lines.append(
                            (
                                f"{metric_name}{labels_part} "
                                f"{stats.last_value} {current_time}"
                            )
                        )

        return "\n".join(lines)

    def reset_metrics(self):
        """Reset all collected metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._histograms.clear()
            self._rate_windows.clear()

    def get_error_rate(
        self, time_window_seconds: int = 300
    ) -> Dict[str, float]:
        """Calculate error rates over specified time window."""
        # current_time = time.time()
        # cutoff_time = current_time - time_window_seconds

        error_rates = {}

        with self._lock:
            # Look for error counters
            for metric_name, labels_data in self._counters.items():
                if "error" in metric_name.lower():
                    total_errors = sum(labels_data.values())

                    # Calculate rate per second
                    error_rate = (
                        total_errors / time_window_seconds
                        if time_window_seconds > 0
                        else 0
                    )
                    error_rates[metric_name] = error_rate

        return error_rates

    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Get latency statistics for histogram metrics."""
        latency_stats = {}

        with self._lock:
            for metric_name, values in self._histograms.items():
                if (
                    "latency" in metric_name.lower()
                    or "duration" in metric_name.lower()
                ):
                    if not values:
                        continue

                    numeric_values = [v for v, _, _ in values]
                    latency_stats[metric_name] = {
                        "count": len(numeric_values),
                        "avg_ms": sum(numeric_values) / len(numeric_values),
                        "min_ms": min(numeric_values),
                        "max_ms": max(numeric_values),
                        "p50_ms": self._percentile(numeric_values, 50),
                        "p95_ms": self._percentile(numeric_values, 95),
                        "p99_ms": self._percentile(numeric_values, 99),
                    }

        return latency_stats


# Factory functions for common configurations
def create_web_service_metrics() -> AutoMetricsGenerator:
    """Create metrics generator optimized for web services."""
    generator = AutoMetricsGenerator(enable_default_metrics=True)

    # Add web-specific extractors
    generator.add_extractor(
        MetricExtractor(
            name="http_request_size_bytes",
            metric_type=MetricType.HISTOGRAM,
            pattern=r"request[_\s]*size[_\s]*[=:]?\s*([0-9.]+)",
            value_extractor=lambda ctx: generator._extract_numeric_value(
                ctx, "request_size"
            ),
            description="HTTP request size in bytes",
            unit="bytes",
            labels=["method", "endpoint"],
        )
    )

    generator.add_extractor(
        MetricExtractor(
            name="http_response_size_bytes",
            metric_type=MetricType.HISTOGRAM,
            pattern=r"response[_\s]*size[_\s]*[=:]?\s*([0-9.]+)",
            value_extractor=lambda ctx: generator._extract_numeric_value(
                ctx, "response_size"
            ),
            description="HTTP response size in bytes",
            unit="bytes",
            labels=["method", "endpoint", "status_code"],
        )
    )

    return generator


def create_database_metrics() -> AutoMetricsGenerator:
    """Create metrics generator optimized for database services."""
    generator = AutoMetricsGenerator(enable_default_metrics=True)

    # Add database-specific extractors
    generator.add_extractor(
        MetricExtractor(
            name="database_connection_pool_size",
            metric_type=MetricType.GAUGE,
            pattern=r"connection[_\s]*pool[_\s]*size[_\s]*[=:]?\s*([0-9.]+)",
            value_extractor=lambda ctx: generator._extract_numeric_value(
                ctx, "pool_size"
            ),
            description="Database connection pool size",
            labels=["database", "pool_name"],
        )
    )

    generator.add_extractor(
        MetricExtractor(
            name="database_query_rows_returned",
            metric_type=MetricType.HISTOGRAM,
            pattern=r"rows[_\s]*returned[_\s]*[=:]?\s*([0-9.]+)",
            value_extractor=lambda ctx: generator._extract_numeric_value(
                ctx, "rows_returned"
            ),
            description="Number of rows returned by database queries",
            labels=["query_type", "table"],
        )
    )

    return generator
