"""Tests for mohflow.metrics.bridge: log-to-metric extraction and export."""

import time
from unittest.mock import MagicMock, patch

import pytest

from mohflow.metrics.bridge import (
    ExtractionRule,
    InMemoryExporter,
    MetricsBridge,
    PrometheusTextExporter,
    StatsDExporter,
    _HistogramAggregation,
    _label_key,
    _parse_label_key,
    _prometheus_line,
)

# -----------------------------------------------------------
# _label_key / _parse_label_key helpers
# -----------------------------------------------------------


class TestLabelKey:
    """Verify stable key generation and parsing."""

    def test_empty_labels(self):
        assert _label_key({}) == ""

    def test_single_label(self):
        assert _label_key({"method": "GET"}) == "method=GET"

    def test_multiple_labels_sorted(self):
        result = _label_key({"method": "GET", "code": "200"})
        assert result == "code=200,method=GET"

    def test_round_trip(self):
        labels = {"host": "web-1", "region": "us-east"}
        key = _label_key(labels)
        parsed = _parse_label_key(key)
        assert parsed == labels

    def test_parse_empty(self):
        assert _parse_label_key("") == {}

    def test_parse_single(self):
        assert _parse_label_key("method=GET") == {"method": "GET"}

    def test_parse_multiple(self):
        result = _parse_label_key("code=200,method=POST")
        assert result == {"code": "200", "method": "POST"}

    def test_parse_value_with_equals(self):
        """Values containing '=' should be handled via split(=, 1)."""
        result = _parse_label_key("query=a=b")
        assert result == {"query": "a=b"}


# -----------------------------------------------------------
# _prometheus_line helper
# -----------------------------------------------------------


class TestPrometheusLine:
    """Verify Prometheus text exposition formatting."""

    def test_no_labels(self):
        line = _prometheus_line("requests_total", 42.0, {})
        assert line == "requests_total 42.0"

    def test_with_labels(self):
        line = _prometheus_line("requests_total", 5.0, {"method": "GET"})
        assert line == 'requests_total{method="GET"} 5.0'

    def test_labels_sorted(self):
        line = _prometheus_line("x", 1.0, {"z": "1", "a": "2"})
        assert line == 'x{a="2",z="1"} 1.0'


# -----------------------------------------------------------
# _HistogramAggregation
# -----------------------------------------------------------


class TestHistogramAggregation:
    """In-memory histogram stats."""

    def test_empty(self):
        h = _HistogramAggregation()
        assert h.count == 0
        assert h.sum == 0.0
        assert h.percentile(50) == 0.0

    def test_observe(self):
        h = _HistogramAggregation()
        h.observe(10.0)
        h.observe(20.0)
        assert h.count == 2
        assert h.sum == 30.0

    def test_percentile_p50(self):
        h = _HistogramAggregation()
        for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            h.observe(float(v))
        p50 = h.percentile(50)
        assert p50 == 5.0

    def test_percentile_p99(self):
        h = _HistogramAggregation()
        for v in range(1, 101):
            h.observe(float(v))
        p99 = h.percentile(99)
        assert p99 == 99.0

    def test_percentile_p0_returns_min(self):
        h = _HistogramAggregation()
        h.observe(5.0)
        h.observe(10.0)
        p = h.percentile(0)
        # ceil(0) = 0, max(0, idx-1) = max(0, -1) = 0
        assert p == 5.0

    def test_reset(self):
        h = _HistogramAggregation()
        h.observe(10.0)
        h.observe(20.0)
        h.reset()
        assert h.count == 0
        assert h.sum == 0.0

    def test_single_value(self):
        h = _HistogramAggregation()
        h.observe(42.0)
        assert h.percentile(50) == 42.0
        assert h.percentile(99) == 42.0


# -----------------------------------------------------------
# ExtractionRule
# -----------------------------------------------------------


class TestExtractionRule:
    """Rule creation, matching, and extraction."""

    def test_invalid_metric_type_raises(self):
        with pytest.raises(ValueError, match="metric_type"):
            ExtractionRule("x", "f", metric_type="invalid")

    def test_valid_types(self):
        for t in ("counter", "histogram", "gauge"):
            rule = ExtractionRule("x", "f", metric_type=t)
            assert rule.metric_type == t

    def test_matches_when_field_present(self):
        rule = ExtractionRule("req_count", "status_code")
        assert rule.matches({"status_code": 200}) is True

    def test_no_match_when_field_missing(self):
        rule = ExtractionRule("req_count", "status_code")
        assert rule.matches({"method": "GET"}) is False

    def test_condition_filters(self):
        rule = ExtractionRule(
            "errors",
            "status_code",
            condition=lambda e: e.get("status_code", 0) >= 400,
        )
        assert rule.matches({"status_code": 200}) is False
        assert rule.matches({"status_code": 500}) is True

    def test_extract_value_numeric(self):
        rule = ExtractionRule(
            "latency", "duration_ms", metric_type="histogram"
        )
        val = rule.extract_value({"duration_ms": 45.2})
        assert val == 45.2

    def test_extract_value_non_numeric_defaults_to_one(self):
        rule = ExtractionRule("events", "status")
        val = rule.extract_value({"status": "ok"})
        assert val == 1.0

    def test_extract_value_with_transform(self):
        rule = ExtractionRule(
            "latency_seconds",
            "duration_ms",
            transform=lambda x: x / 1000.0,
        )
        val = rule.extract_value({"duration_ms": 1500})
        assert val == 1.5

    def test_extract_labels(self):
        rule = ExtractionRule(
            "req_count",
            "status",
            label_fields=["method", "path"],
        )
        labels = rule.extract_labels(
            {"status": 200, "method": "GET", "path": "/api"}
        )
        assert labels == {"method": "GET", "path": "/api"}

    def test_extract_labels_missing_fields(self):
        rule = ExtractionRule(
            "req_count",
            "status",
            label_fields=["method", "path"],
        )
        labels = rule.extract_labels({"status": 200, "method": "GET"})
        assert labels == {"method": "GET"}

    def test_default_label_fields_empty(self):
        rule = ExtractionRule("x", "f")
        assert rule.label_fields == []

    def test_extract_labels_empty_when_no_label_fields(self):
        rule = ExtractionRule("x", "f")
        assert rule.extract_labels({"f": 1}) == {}


# -----------------------------------------------------------
# MetricsBridge initialization
# -----------------------------------------------------------


class TestMetricsBridgeInit:
    """Bridge construction."""

    def test_default_auto_flush_zero(self):
        bridge = MetricsBridge()
        assert bridge._auto_flush_interval == 0

    def test_custom_auto_flush_interval(self):
        bridge = MetricsBridge(auto_flush_interval=30.0)
        assert bridge._auto_flush_interval == 30.0

    def test_initial_events_processed_zero(self):
        bridge = MetricsBridge()
        assert bridge.events_processed == 0

    def test_initial_rules_empty(self):
        bridge = MetricsBridge()
        assert bridge.rules == []


# -----------------------------------------------------------
# MetricsBridge.add_rule and chaining
# -----------------------------------------------------------


class TestMetricsBridgeAddRule:
    """add_rule returns self for chaining."""

    def test_add_rule_returns_self(self):
        bridge = MetricsBridge()
        result = bridge.add_rule("x", "f")
        assert result is bridge

    def test_chain_multiple_rules(self):
        bridge = (
            MetricsBridge()
            .add_rule("a", "f1")
            .add_rule("b", "f2")
            .add_rule("c", "f3")
        )
        assert len(bridge.rules) == 3

    def test_rule_stored_correctly(self):
        bridge = MetricsBridge()
        bridge.add_rule(
            "req_count",
            "status_code",
            metric_type="counter",
            label_fields=["method"],
        )
        rule = bridge.rules[0]
        assert rule.metric_name == "req_count"
        assert rule.field == "status_code"
        assert rule.metric_type == "counter"
        assert rule.label_fields == ["method"]


# -----------------------------------------------------------
# MetricsBridge.process()
# -----------------------------------------------------------


class TestMetricsBridgeProcess:
    """Processing events through rules."""

    def test_counter_accumulation(self):
        bridge = MetricsBridge()
        bridge.add_rule("req_count", "status_code", metric_type="counter")
        bridge.process({"status_code": 200})
        bridge.process({"status_code": 200})
        summary = bridge.get_summary()
        assert summary["counters"]["req_count"][""] == 400.0

    def test_counter_with_labels(self):
        bridge = MetricsBridge()
        bridge.add_rule(
            "req_count",
            "status_code",
            metric_type="counter",
            label_fields=["method"],
        )
        bridge.process({"status_code": 200, "method": "GET"})
        bridge.process({"status_code": 200, "method": "POST"})
        summary = bridge.get_summary()
        assert "method=GET" in summary["counters"]["req_count"]
        assert "method=POST" in summary["counters"]["req_count"]

    def test_histogram_accumulation(self):
        bridge = MetricsBridge()
        bridge.add_rule("latency", "duration_ms", metric_type="histogram")
        bridge.process({"duration_ms": 10.0})
        bridge.process({"duration_ms": 20.0})
        bridge.process({"duration_ms": 30.0})
        summary = bridge.get_summary()
        hist = summary["histograms"]["latency"][""]
        assert hist["count"] == 3
        assert hist["sum"] == 60.0

    def test_gauge_last_value_wins(self):
        bridge = MetricsBridge()
        bridge.add_rule("temp", "cpu_temp", metric_type="gauge")
        bridge.process({"cpu_temp": 60.0})
        bridge.process({"cpu_temp": 75.0})
        summary = bridge.get_summary()
        assert summary["gauges"]["temp"][""] == 75.0

    def test_events_processed_increments(self):
        bridge = MetricsBridge()
        bridge.add_rule("x", "f")
        bridge.process({"f": 1})
        bridge.process({"other": 2})  # no match but still counts
        assert bridge.events_processed == 2

    def test_no_match_skips_accumulation(self):
        bridge = MetricsBridge()
        bridge.add_rule("x", "f")
        bridge.process({"other": 1})
        summary = bridge.get_summary()
        assert summary["counters"] == {}

    def test_multiple_rules_same_event(self):
        bridge = MetricsBridge()
        bridge.add_rule("count", "status", metric_type="counter")
        bridge.add_rule("latency", "duration", metric_type="histogram")
        bridge.process({"status": 200, "duration": 45.0})
        summary = bridge.get_summary()
        assert "count" in summary["counters"]
        assert "latency" in summary["histograms"]

    def test_condition_skips_non_matching(self):
        bridge = MetricsBridge()
        bridge.add_rule(
            "errors",
            "status",
            metric_type="counter",
            condition=lambda e: e.get("status", 0) >= 400,
        )
        bridge.process({"status": 200})
        bridge.process({"status": 500})
        summary = bridge.get_summary()
        assert summary["counters"]["errors"][""] == 500.0

    def test_transform_applied(self):
        bridge = MetricsBridge()
        bridge.add_rule(
            "latency_s",
            "duration_ms",
            metric_type="histogram",
            transform=lambda x: x / 1000.0,
        )
        bridge.process({"duration_ms": 2500})
        summary = bridge.get_summary()
        assert summary["histograms"]["latency_s"][""]["sum"] == 2.5


# -----------------------------------------------------------
# MetricsBridge.get_summary()
# -----------------------------------------------------------


class TestMetricsBridgeGetSummary:
    """Summary snapshot."""

    def test_empty_summary(self):
        bridge = MetricsBridge()
        s = bridge.get_summary()
        assert s == {
            "events_processed": 0,
            "counters": {},
            "histograms": {},
            "gauges": {},
        }

    def test_summary_histogram_includes_percentiles(self):
        bridge = MetricsBridge()
        bridge.add_rule("lat", "d", metric_type="histogram")
        for v in [10, 20, 30, 40, 50]:
            bridge.process({"d": float(v)})
        hist = bridge.get_summary()["histograms"]["lat"][""]
        assert "p50" in hist
        assert "p95" in hist
        assert "p99" in hist
        assert "count" in hist
        assert "sum" in hist


# -----------------------------------------------------------
# MetricsBridge.reset()
# -----------------------------------------------------------


class TestMetricsBridgeReset:
    """Clear accumulated state."""

    def test_reset_clears_counters(self):
        bridge = MetricsBridge()
        bridge.add_rule("x", "f")
        bridge.process({"f": 1})
        bridge.reset()
        assert bridge.get_summary()["counters"] == {}

    def test_reset_clears_histograms(self):
        bridge = MetricsBridge()
        bridge.add_rule("h", "f", metric_type="histogram")
        bridge.process({"f": 5.0})
        bridge.reset()
        assert bridge.get_summary()["histograms"] == {}

    def test_reset_clears_gauges(self):
        bridge = MetricsBridge()
        bridge.add_rule("g", "f", metric_type="gauge")
        bridge.process({"f": 42.0})
        bridge.reset()
        assert bridge.get_summary()["gauges"] == {}

    def test_reset_clears_events_processed(self):
        bridge = MetricsBridge()
        bridge.add_rule("x", "f")
        bridge.process({"f": 1})
        bridge.reset()
        assert bridge.events_processed == 0

    def test_rules_survive_reset(self):
        bridge = MetricsBridge()
        bridge.add_rule("x", "f")
        bridge.reset()
        assert len(bridge.rules) == 1


# -----------------------------------------------------------
# MetricsBridge.flush()
# -----------------------------------------------------------


class TestMetricsBridgeFlush:
    """Flush pushes metrics to exporters."""

    def test_flush_calls_exporter(self):
        bridge = MetricsBridge()
        exporter = InMemoryExporter()
        bridge.add_exporter(exporter)
        bridge.add_rule("count", "status", metric_type="counter")
        bridge.process({"status": 200})
        bridge.flush()
        assert len(exporter.counters) == 1
        assert exporter.counters[0]["name"] == "count"
        assert exporter.counters[0]["value"] == 200.0

    def test_flush_histogram_to_exporter(self):
        bridge = MetricsBridge()
        exporter = InMemoryExporter()
        bridge.add_exporter(exporter)
        bridge.add_rule("lat", "d", metric_type="histogram")
        bridge.process({"d": 10.0})
        bridge.process({"d": 20.0})
        bridge.flush()
        assert len(exporter.histograms) == 1
        assert exporter.histograms[0]["value"] == 30.0  # sum

    def test_flush_gauge_to_exporter(self):
        bridge = MetricsBridge()
        exporter = InMemoryExporter()
        bridge.add_exporter(exporter)
        bridge.add_rule("temp", "cpu", metric_type="gauge")
        bridge.process({"cpu": 65.0})
        bridge.flush()
        assert len(exporter.gauges) == 1
        assert exporter.gauges[0]["value"] == 65.0

    def test_flush_calls_exporter_flush(self):
        bridge = MetricsBridge()
        exporter = InMemoryExporter()
        bridge.add_exporter(exporter)
        bridge.flush()
        assert exporter.flush_count == 1

    def test_flush_multiple_exporters(self):
        bridge = MetricsBridge()
        e1 = InMemoryExporter()
        e2 = InMemoryExporter()
        bridge.add_exporter(e1).add_exporter(e2)
        bridge.add_rule("x", "f")
        bridge.process({"f": 1})
        bridge.flush()
        assert len(e1.counters) == 1
        assert len(e2.counters) == 1

    def test_flush_with_labels(self):
        bridge = MetricsBridge()
        exporter = InMemoryExporter()
        bridge.add_exporter(exporter)
        bridge.add_rule("req", "status", label_fields=["method"])
        bridge.process({"status": 200, "method": "GET"})
        bridge.flush()
        assert exporter.counters[0]["labels"] == {"method": "GET"}


# -----------------------------------------------------------
# Auto-flush interval
# -----------------------------------------------------------


class TestAutoFlush:
    """auto_flush_interval triggers flush during process()."""

    def test_auto_flush_triggers(self):
        bridge = MetricsBridge(auto_flush_interval=0.01)
        exporter = InMemoryExporter()
        bridge.add_exporter(exporter)
        bridge.add_rule("x", "f")
        # Force last_flush to be in the past
        bridge._last_flush = time.monotonic() - 1.0
        bridge.process({"f": 1})
        assert exporter.flush_count >= 1

    def test_no_auto_flush_when_zero(self):
        bridge = MetricsBridge(auto_flush_interval=0)
        exporter = InMemoryExporter()
        bridge.add_exporter(exporter)
        bridge.add_rule("x", "f")
        bridge.process({"f": 1})
        assert exporter.flush_count == 0


# -----------------------------------------------------------
# InMemoryExporter
# -----------------------------------------------------------


class TestInMemoryExporter:
    """Simple test exporter."""

    def test_write_counter(self):
        e = InMemoryExporter()
        e.write_counter("req", 5.0, {"method": "GET"})
        assert len(e.counters) == 1
        assert e.counters[0] == {
            "name": "req",
            "value": 5.0,
            "labels": {"method": "GET"},
        }

    def test_write_histogram(self):
        e = InMemoryExporter()
        e.write_histogram("lat", 100.0, {})
        assert len(e.histograms) == 1

    def test_write_gauge(self):
        e = InMemoryExporter()
        e.write_gauge("temp", 72.0, {})
        assert len(e.gauges) == 1

    def test_flush_count(self):
        e = InMemoryExporter()
        assert e.flush_count == 0
        e.flush()
        assert e.flush_count == 1
        e.flush()
        assert e.flush_count == 2


# -----------------------------------------------------------
# PrometheusTextExporter
# -----------------------------------------------------------


class TestPrometheusTextExporter:
    """Prometheus text exposition format."""

    def test_counter_format(self):
        e = PrometheusTextExporter()
        e.write_counter("requests", 42.0, {})
        text = e.get_text()
        assert "requests_total 42.0" in text

    def test_histogram_format(self):
        e = PrometheusTextExporter()
        e.write_histogram("latency", 123.0, {})
        text = e.get_text()
        assert "latency_sum 123.0" in text

    def test_gauge_format(self):
        e = PrometheusTextExporter()
        e.write_gauge("temperature", 72.5, {})
        text = e.get_text()
        assert "temperature 72.5" in text

    def test_with_labels(self):
        e = PrometheusTextExporter()
        e.write_counter("requests", 5.0, {"method": "POST"})
        text = e.get_text()
        assert 'requests_total{method="POST"} 5.0' in text

    def test_empty_get_text(self):
        e = PrometheusTextExporter()
        assert e.get_text() == ""

    def test_text_ends_with_newline(self):
        e = PrometheusTextExporter()
        e.write_counter("x", 1.0, {})
        assert e.get_text().endswith("\n")

    def test_clear(self):
        e = PrometheusTextExporter()
        e.write_counter("x", 1.0, {})
        e.clear()
        assert e.get_text() == ""

    def test_flush_is_noop(self):
        e = PrometheusTextExporter()
        e.flush()  # should not raise

    def test_multiple_lines(self):
        e = PrometheusTextExporter()
        e.write_counter("a", 1.0, {})
        e.write_gauge("b", 2.0, {})
        text = e.get_text()
        lines = text.strip().split("\n")
        assert len(lines) == 2


# -----------------------------------------------------------
# StatsDExporter
# -----------------------------------------------------------


class TestStatsDExporter:
    """StatsD line format."""

    def test_default_prefix(self):
        e = StatsDExporter()
        e.write_counter("req", 5.0, {})
        assert e.get_lines() == ["mohflow.req:5.0|c"]

    def test_custom_prefix(self):
        e = StatsDExporter(prefix="myapp")
        e.write_counter("req", 5.0, {})
        assert e.get_lines() == ["myapp.req:5.0|c"]

    def test_counter_format(self):
        e = StatsDExporter()
        e.write_counter("hits", 10.0, {})
        assert "mohflow.hits:10.0|c" in e.get_lines()

    def test_histogram_format(self):
        e = StatsDExporter()
        e.write_histogram("latency", 42.5, {})
        assert "mohflow.latency:42.5|ms" in e.get_lines()

    def test_gauge_format(self):
        e = StatsDExporter()
        e.write_gauge("cpu", 75.0, {})
        assert "mohflow.cpu:75.0|g" in e.get_lines()

    def test_get_lines_returns_copy(self):
        e = StatsDExporter()
        e.write_counter("x", 1.0, {})
        lines = e.get_lines()
        lines.append("hacked")
        assert "hacked" not in e.get_lines()

    def test_clear(self):
        e = StatsDExporter()
        e.write_counter("x", 1.0, {})
        e.clear()
        assert e.get_lines() == []

    def test_flush_is_noop(self):
        e = StatsDExporter()
        e.flush()  # should not raise

    def test_multiple_lines(self):
        e = StatsDExporter()
        e.write_counter("a", 1.0, {})
        e.write_gauge("b", 2.0, {})
        e.write_histogram("c", 3.0, {})
        assert len(e.get_lines()) == 3


# -----------------------------------------------------------
# add_exporter chaining
# -----------------------------------------------------------


class TestAddExporterChaining:
    """add_exporter returns self for chaining."""

    def test_returns_self(self):
        bridge = MetricsBridge()
        result = bridge.add_exporter(InMemoryExporter())
        assert result is bridge

    def test_chain_multiple(self):
        bridge = (
            MetricsBridge()
            .add_exporter(InMemoryExporter())
            .add_exporter(InMemoryExporter())
        )
        assert len(bridge._exporters) == 2
