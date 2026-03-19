"""
Log-to-metric bridge for MohFlow.

Automatically extracts counters, histograms, and gauges from
structured log events and pushes them to remote metric stores
(Prometheus, StatsD, CloudWatch, Datadog).

Usage::

    from mohflow.metrics.bridge import MetricsBridge, PrometheusRemoteWriter

    bridge = MetricsBridge()
    bridge.add_rule("request_count", field="status_code", metric_type="counter")
    bridge.add_rule("request_duration", field="duration_ms", metric_type="histogram")

    # Process log events
    bridge.process({"status_code": 200, "duration_ms": 45.2})

    # Push to Prometheus (or export for scraping)
    writer = PrometheusRemoteWriter(endpoint="http://prometheus:9090/api/v1/write")
    bridge.export(writer)

Features:
- Rule-based metric extraction from log fields
- Counter, histogram, gauge metric types
- Label extraction for dimensional metrics
- Pluggable exporters (Prometheus, StatsD, custom)
- In-memory aggregation with configurable flush intervals
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
)


class MetricExporter(Protocol):
    """Protocol for metric exporters."""

    def write_counter(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None: ...

    def write_histogram(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None: ...

    def write_gauge(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None: ...

    def flush(self) -> None: ...


class ExtractionRule:
    """Defines how a metric is extracted from a log event.

    Parameters
    ----------
    metric_name : str
        Name of the metric to produce.
    field : str
        Log event field to read the value from.
    metric_type : str
        ``"counter"``, ``"histogram"``, or ``"gauge"``.
    label_fields : sequence of str
        Additional event fields to use as metric labels.
    condition : callable, optional
        A predicate ``(event) -> bool``.  The rule only fires
        when the predicate returns ``True``.
    transform : callable, optional
        A function ``(value) -> float`` applied before recording.
    """

    def __init__(
        self,
        metric_name: str,
        field: str,
        metric_type: str = "counter",
        label_fields: Optional[Sequence[str]] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        transform: Optional[Callable[[Any], float]] = None,
    ):
        if metric_type not in ("counter", "histogram", "gauge"):
            raise ValueError(
                f"metric_type must be 'counter', 'histogram', or "
                f"'gauge', got '{metric_type}'"
            )
        self.metric_name = metric_name
        self.field = field
        self.metric_type = metric_type
        self.label_fields = list(label_fields or [])
        self.condition = condition
        self.transform = transform

    def matches(self, event: Dict[str, Any]) -> bool:
        """Return True if this rule should fire for *event*."""
        if self.field not in event:
            return False
        if self.condition and not self.condition(event):
            return False
        return True

    def extract_value(self, event: Dict[str, Any]) -> float:
        """Pull the metric value out of *event*."""
        raw = event[self.field]
        if self.transform:
            return self.transform(raw)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 1.0  # default for counters

    def extract_labels(self, event: Dict[str, Any]) -> Dict[str, str]:
        """Pull label values out of *event*."""
        labels: Dict[str, str] = {}
        for lf in self.label_fields:
            if lf in event:
                labels[lf] = str(event[lf])
        return labels


class _HistogramAggregation:
    """In-memory histogram aggregation."""

    __slots__ = ("_values", "_sum", "_count")

    def __init__(self) -> None:
        self._values: List[float] = []
        self._sum: float = 0.0
        self._count: int = 0

    def observe(self, value: float) -> None:
        self._values.append(value)
        self._sum += value
        self._count += 1

    @property
    def count(self) -> int:
        return self._count

    @property
    def sum(self) -> float:
        return self._sum

    def percentile(self, p: float) -> float:
        if not self._values:
            return 0.0
        sorted_vals = sorted(self._values)
        idx = int(math.ceil(p / 100.0 * len(sorted_vals))) - 1
        return sorted_vals[max(0, idx)]

    def reset(self) -> None:
        self._values.clear()
        self._sum = 0.0
        self._count = 0


class MetricsBridge:
    """Extracts metrics from log events based on configured rules.

    Parameters
    ----------
    auto_flush_interval : float
        Seconds between automatic flushes to exporters (0 = manual only).
    """

    def __init__(
        self,
        auto_flush_interval: float = 0,
    ):
        self._rules: List[ExtractionRule] = []
        self._counters: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._histograms: Dict[str, Dict[str, _HistogramAggregation]] = (
            defaultdict(lambda: defaultdict(_HistogramAggregation))
        )
        self._gauges: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._exporters: List[MetricExporter] = []
        self._auto_flush_interval = auto_flush_interval
        self._last_flush = time.monotonic()
        self._events_processed = 0

    # ── configuration ────────────────────────────────────────

    def add_rule(
        self,
        metric_name: str,
        field: str,
        metric_type: str = "counter",
        label_fields: Optional[Sequence[str]] = None,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        transform: Optional[Callable[[Any], float]] = None,
    ) -> "MetricsBridge":
        """Add an extraction rule and return self for chaining."""
        self._rules.append(
            ExtractionRule(
                metric_name=metric_name,
                field=field,
                metric_type=metric_type,
                label_fields=label_fields,
                condition=condition,
                transform=transform,
            )
        )
        return self

    def add_exporter(self, exporter: MetricExporter) -> "MetricsBridge":
        """Register an exporter and return self for chaining."""
        self._exporters.append(exporter)
        return self

    @property
    def rules(self) -> List[ExtractionRule]:
        return list(self._rules)

    @property
    def events_processed(self) -> int:
        return self._events_processed

    # ── processing ───────────────────────────────────────────

    def process(self, event: Dict[str, Any]) -> None:
        """Extract metrics from a single log event."""
        self._events_processed += 1
        for rule in self._rules:
            if not rule.matches(event):
                continue
            value = rule.extract_value(event)
            labels = rule.extract_labels(event)
            label_key = _label_key(labels)

            if rule.metric_type == "counter":
                self._counters[rule.metric_name][label_key] += value
            elif rule.metric_type == "histogram":
                self._histograms[rule.metric_name][label_key].observe(value)
            elif rule.metric_type == "gauge":
                self._gauges[rule.metric_name][label_key] = value

        # Auto-flush check
        if self._auto_flush_interval > 0:
            now = time.monotonic()
            if now - self._last_flush >= self._auto_flush_interval:
                self.flush()
                self._last_flush = now

    # ── export ───────────────────────────────────────────────

    def flush(self) -> None:
        """Push accumulated metrics to all registered exporters."""
        ts = time.time()
        for exporter in self._exporters:
            for name, label_map in self._counters.items():
                for lk, value in label_map.items():
                    exporter.write_counter(
                        name, value, _parse_label_key(lk), ts
                    )
            for name, label_map in self._histograms.items():
                for lk, agg in label_map.items():
                    exporter.write_histogram(
                        name, agg.sum, _parse_label_key(lk), ts
                    )
            for name, label_map in self._gauges.items():
                for lk, value in label_map.items():
                    exporter.write_gauge(name, value, _parse_label_key(lk), ts)
            exporter.flush()

    def get_summary(self) -> Dict[str, Any]:
        """Return a snapshot of all accumulated metrics."""
        summary: Dict[str, Any] = {
            "events_processed": self._events_processed,
            "counters": {},
            "histograms": {},
            "gauges": {},
        }
        for name, label_map in self._counters.items():
            summary["counters"][name] = {lk: v for lk, v in label_map.items()}
        for name, label_map in self._histograms.items():
            summary["histograms"][name] = {
                lk: {
                    "count": agg.count,
                    "sum": agg.sum,
                    "p50": agg.percentile(50),
                    "p95": agg.percentile(95),
                    "p99": agg.percentile(99),
                }
                for lk, agg in label_map.items()
            }
        for name, label_map in self._gauges.items():
            summary["gauges"][name] = dict(label_map)
        return summary

    def reset(self) -> None:
        """Clear all accumulated metrics."""
        self._counters.clear()
        for label_map in self._histograms.values():
            for agg in label_map.values():
                agg.reset()
        self._histograms.clear()
        self._gauges.clear()
        self._events_processed = 0


class InMemoryExporter:
    """Simple in-memory exporter for testing."""

    def __init__(self) -> None:
        self.counters: List[Dict[str, Any]] = []
        self.histograms: List[Dict[str, Any]] = []
        self.gauges: List[Dict[str, Any]] = []
        self._flushed = 0

    def write_counter(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self.counters.append({"name": name, "value": value, "labels": labels})

    def write_histogram(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self.histograms.append(
            {"name": name, "value": value, "labels": labels}
        )

    def write_gauge(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self.gauges.append({"name": name, "value": value, "labels": labels})

    def flush(self) -> None:
        self._flushed += 1

    @property
    def flush_count(self) -> int:
        return self._flushed


class PrometheusTextExporter:
    """Export metrics in Prometheus text exposition format.

    Stores the formatted text; call :meth:`get_text` to retrieve it.
    Useful for a ``/metrics`` HTTP endpoint.
    """

    def __init__(self) -> None:
        self._lines: List[str] = []

    def write_counter(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self._lines.append(_prometheus_line(name + "_total", value, labels))

    def write_histogram(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self._lines.append(_prometheus_line(name + "_sum", value, labels))

    def write_gauge(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self._lines.append(_prometheus_line(name, value, labels))

    def flush(self) -> None:
        pass

    def get_text(self) -> str:
        """Return Prometheus text exposition."""
        return "\n".join(self._lines) + "\n" if self._lines else ""

    def clear(self) -> None:
        self._lines.clear()


class StatsDExporter:
    """Format metrics as StatsD lines.

    Stores formatted lines; call :meth:`get_lines` to retrieve.
    """

    def __init__(self, prefix: str = "mohflow") -> None:
        self._prefix = prefix
        self._lines: List[str] = []

    def write_counter(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self._lines.append(f"{self._prefix}.{name}:{value}|c")

    def write_histogram(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self._lines.append(f"{self._prefix}.{name}:{value}|ms")

    def write_gauge(
        self,
        name: str,
        value: float,
        labels: Dict[str, str],
        timestamp: Optional[float] = None,
    ) -> None:
        self._lines.append(f"{self._prefix}.{name}:{value}|g")

    def flush(self) -> None:
        pass

    def get_lines(self) -> List[str]:
        return list(self._lines)

    def clear(self) -> None:
        self._lines.clear()


# ── helpers ──────────────────────────────────────────────────


def _label_key(labels: Dict[str, str]) -> str:
    """Produce a stable string key from a label dict."""
    if not labels:
        return ""
    parts = sorted(labels.items())
    return ",".join(f"{k}={v}" for k, v in parts)


def _parse_label_key(key: str) -> Dict[str, str]:
    """Reverse of :func:`_label_key`."""
    if not key:
        return {}
    result: Dict[str, str] = {}
    for part in key.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result


def _prometheus_line(
    name: str,
    value: float,
    labels: Dict[str, str],
) -> str:
    """Format a single Prometheus text exposition line."""
    if labels:
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}} {value}"
    return f"{name} {value}"
