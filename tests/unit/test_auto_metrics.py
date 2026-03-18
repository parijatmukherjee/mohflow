"""Tests for automatic metrics generation from log patterns."""

import json
import re
import time
from unittest.mock import patch

import pytest

from mohflow.metrics.auto_metrics import (
    AutoMetricsGenerator,
    MetricExtractor,
    MetricStats,
    MetricType,
    MetricValue,
    create_database_metrics,
    create_web_service_metrics,
)


# ──────────────────────────────────────────────────────────────
# MetricType enum
# ──────────────────────────────────────────────────────────────
class TestMetricType:
    """Tests for the MetricType enum."""

    def test_counter_value(self):
        assert MetricType.COUNTER.value == "counter"

    def test_histogram_value(self):
        assert MetricType.HISTOGRAM.value == "histogram"

    def test_gauge_value(self):
        assert MetricType.GAUGE.value == "gauge"

    def test_summary_value(self):
        assert MetricType.SUMMARY.value == "summary"

    def test_all_members_present(self):
        names = {m.name for m in MetricType}
        assert names == {"COUNTER", "HISTOGRAM", "GAUGE", "SUMMARY"}


# ──────────────────────────────────────────────────────────────
# MetricExtractor dataclass
# ──────────────────────────────────────────────────────────────
class TestMetricExtractor:
    """Tests for MetricExtractor configuration."""

    def test_string_pattern_compiled_to_regex(self):
        ext = MetricExtractor(
            name="test",
            metric_type=MetricType.COUNTER,
            pattern=r"error",
        )
        assert isinstance(ext.pattern, re.Pattern)

    def test_compiled_pattern_left_as_is(self):
        compiled = re.compile(r"error")
        ext = MetricExtractor(
            name="test",
            metric_type=MetricType.COUNTER,
            pattern=compiled,
        )
        assert ext.pattern is compiled

    def test_default_fields(self):
        ext = MetricExtractor(
            name="test",
            metric_type=MetricType.COUNTER,
            pattern=r"test",
        )
        assert ext.value_extractor is None
        assert ext.labels is None
        assert ext.description == ""
        assert ext.unit == ""

    def test_custom_fields(self):
        extractor_fn = lambda ctx: 42.0  # noqa: E731
        ext = MetricExtractor(
            name="my_metric",
            metric_type=MetricType.HISTOGRAM,
            pattern=r"duration=([0-9.]+)",
            value_extractor=extractor_fn,
            labels=["method", "path"],
            description="Request duration",
            unit="ms",
        )
        assert ext.name == "my_metric"
        assert ext.metric_type == MetricType.HISTOGRAM
        assert ext.value_extractor is extractor_fn
        assert ext.labels == ["method", "path"]
        assert ext.description == "Request duration"
        assert ext.unit == "ms"


# ──────────────────────────────────────────────────────────────
# MetricValue dataclass
# ──────────────────────────────────────────────────────────────
class TestMetricValue:
    """Tests for MetricValue measurement objects."""

    def test_defaults(self):
        mv = MetricValue(name="test", value=1.0)
        assert mv.name == "test"
        assert mv.value == 1.0
        assert mv.labels == {}
        assert mv.unit == ""
        assert isinstance(mv.timestamp, float)

    def test_custom_labels_and_unit(self):
        mv = MetricValue(
            name="m",
            value=5.0,
            labels={"a": "1"},
            unit="bytes",
        )
        assert mv.labels == {"a": "1"}
        assert mv.unit == "bytes"


# ──────────────────────────────────────────────────────────────
# MetricStats dataclass
# ──────────────────────────────────────────────────────────────
class TestMetricStats:
    """Tests for MetricStats statistics tracking."""

    def test_initial_state(self):
        stats = MetricStats()
        assert stats.count == 0
        assert stats.sum == 0.0
        assert stats.min == float("inf")
        assert stats.max == float("-inf")
        assert stats.last_value == 0.0
        assert stats.last_updated == 0.0

    def test_single_update(self):
        stats = MetricStats()
        stats.update(10.0, timestamp=100.0)
        assert stats.count == 1
        assert stats.sum == 10.0
        assert stats.min == 10.0
        assert stats.max == 10.0
        assert stats.last_value == 10.0
        assert stats.last_updated == 100.0

    def test_multiple_updates(self):
        stats = MetricStats()
        stats.update(5.0, timestamp=1.0)
        stats.update(15.0, timestamp=2.0)
        stats.update(10.0, timestamp=3.0)

        assert stats.count == 3
        assert stats.sum == 30.0
        assert stats.min == 5.0
        assert stats.max == 15.0
        assert stats.last_value == 10.0
        assert stats.last_updated == 3.0

    def test_average_with_values(self):
        stats = MetricStats()
        stats.update(4.0)
        stats.update(6.0)
        assert stats.average == 5.0

    def test_average_with_no_values(self):
        stats = MetricStats()
        assert stats.average == 0.0

    def test_update_without_explicit_timestamp(self):
        stats = MetricStats()
        before = time.time()
        stats.update(7.0)
        after = time.time()
        assert before <= stats.last_updated <= after


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – initialisation
# ──────────────────────────────────────────────────────────────
class TestAutoMetricsGeneratorInit:
    """Tests for AutoMetricsGenerator initialisation."""

    def test_default_extractors_added(self):
        gen = AutoMetricsGenerator(enable_default_metrics=True)
        assert len(gen._extractors) > 0

    def test_no_default_extractors(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        assert len(gen._extractors) == 0

    def test_add_custom_extractor(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        ext = MetricExtractor(
            name="custom_total",
            metric_type=MetricType.COUNTER,
            pattern=r"custom event",
        )
        gen.add_extractor(ext)
        assert len(gen._extractors) == 1
        assert gen._extractors[0].name == "custom_total"


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – process_log_record
# ──────────────────────────────────────────────────────────────
class TestProcessLogRecord:
    """Tests for processing individual log records."""

    def test_no_match_returns_empty(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="test_total",
                metric_type=MetricType.COUNTER,
                pattern=r"NEVER_MATCHES_XYZ",
            )
        )
        result = gen.process_log_record({"message": "normal message"})
        assert result == []

    def test_counter_match(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="errors_total",
                metric_type=MetricType.COUNTER,
                pattern=r"ERROR",
            )
        )
        result = gen.process_log_record({"message": "An ERROR occurred"})
        assert len(result) == 1
        assert result[0].name == "errors_total"
        assert result[0].value == 1.0

    def test_histogram_extracts_value_from_group(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="size_bytes",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"size=([0-9.]+)",
            )
        )
        result = gen.process_log_record({"message": "size=256.5 bytes"})
        assert len(result) == 1
        assert result[0].value == 256.5

    def test_custom_value_extractor(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="custom_metric",
                metric_type=MetricType.GAUGE,
                pattern=r"temp",
                value_extractor=lambda ctx: ctx.get("temperature", 0.0),
            )
        )
        result = gen.process_log_record(
            {"message": "temp reading", "temperature": 36.6}
        )
        assert len(result) == 1
        assert result[0].value == 36.6

    def test_value_extractor_error_falls_back_to_one(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="bad_extractor",
                metric_type=MetricType.GAUGE,
                pattern=r"event",
                value_extractor=lambda ctx: float("not_a_number"),
            )
        )
        result = gen.process_log_record({"message": "an event"})
        assert len(result) == 1
        assert result[0].value == 1.0

    def test_label_extraction_from_level(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="lvl_counter",
                metric_type=MetricType.COUNTER,
                pattern=r"msg",
                labels=["level"],
            )
        )
        result = gen.process_log_record({"message": "msg", "level": "WARNING"})
        assert result[0].labels["level"] == "WARNING"

    def test_label_extraction_from_service_name(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="svc_counter",
                metric_type=MetricType.COUNTER,
                pattern=r"msg",
                labels=["service"],
            )
        )
        result = gen.process_log_record(
            {"message": "msg", "service_name": "api"}
        )
        assert result[0].labels["service"] == "api"

    def test_label_service_defaults_to_unknown(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="svc_counter",
                metric_type=MetricType.COUNTER,
                pattern=r"msg",
                labels=["service"],
            )
        )
        result = gen.process_log_record({"message": "msg"})
        assert result[0].labels["service"] == "unknown"

    def test_label_from_log_record_field(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="endpoint_counter",
                metric_type=MetricType.COUNTER,
                pattern=r"request",
                labels=["endpoint"],
            )
        )
        result = gen.process_log_record(
            {"message": "request", "endpoint": "/api/v1/users"}
        )
        assert result[0].labels["endpoint"] == "/api/v1/users"

    def test_label_extracted_from_message_pattern(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="method_counter",
                metric_type=MetricType.COUNTER,
                pattern=r"http",
                labels=["method"],
            )
        )
        result = gen.process_log_record(
            {"message": "http method=GET path=/api"}
        )
        assert result[0].labels["method"] == "GET"

    def test_label_falls_back_to_unknown(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="x_counter",
                metric_type=MetricType.COUNTER,
                pattern=r"ping",
                labels=["nonexistent_label"],
            )
        )
        result = gen.process_log_record({"message": "ping"})
        assert result[0].labels["nonexistent_label"] == "unknown"

    def test_pattern_match_via_json_dumps_fallback(self):
        """Pattern not found in message but found via
        json.dumps(log_record)."""
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="json_counter",
                metric_type=MetricType.COUNTER,
                pattern=r"secret_field",
            )
        )
        result = gen.process_log_record(
            {
                "message": "nothing here",
                "secret_field": "present",
            }
        )
        assert len(result) == 1

    def test_extractor_exception_is_swallowed(self):
        """Metric extraction errors must not break logging."""
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        bad = MetricExtractor(
            name="bad",
            metric_type=MetricType.COUNTER,
            pattern=r"hello",
        )
        # Sabotage the pattern object
        bad.pattern = None  # type: ignore[assignment]
        gen._extractors.append(bad)

        good = MetricExtractor(
            name="good_total",
            metric_type=MetricType.COUNTER,
            pattern=r"hello",
        )
        gen.add_extractor(good)

        result = gen.process_log_record({"message": "hello"})
        # The good extractor should still produce a metric
        assert any(m.name == "good_total" for m in result)

    def test_default_level_is_info_when_missing(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="lvl_check",
                metric_type=MetricType.COUNTER,
                pattern=r"msg",
                labels=["level"],
            )
        )
        result = gen.process_log_record({"message": "msg"})
        assert result[0].labels["level"] == "INFO"

    def test_histogram_no_groups_defaults_to_one(self):
        """If pattern has no capture group, value should default
        to 1.0."""
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="no_group",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"event",
            )
        )
        result = gen.process_log_record({"message": "an event occurred"})
        assert result[0].value == 1.0

    def test_histogram_invalid_group_defaults_to_one(self):
        """If captured group cannot convert to float, default 1.0."""
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="bad_group",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"val=(\w+)",
            )
        )
        result = gen.process_log_record({"message": "val=abc"})
        assert result[0].value == 1.0


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – _update_metric_storage
# ──────────────────────────────────────────────────────────────
class TestUpdateMetricStorage:
    """Tests for internal metric storage updates."""

    def test_counter_storage(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="hits_total",
                metric_type=MetricType.COUNTER,
                pattern=r"hit",
            )
        )
        gen.process_log_record({"message": "cache hit"})
        gen.process_log_record({"message": "cache hit"})

        labels_key = json.dumps({}, sort_keys=True)
        assert gen._counters["hits_total"][labels_key] == 2

    def test_histogram_storage(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="request_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"dur=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "dur=100"})
        gen.process_log_record({"message": "dur=200"})

        assert len(gen._histograms["request_duration_seconds"]) == 2
        values = [v for v, _, _ in gen._histograms["request_duration_seconds"]]
        assert 100.0 in values
        assert 200.0 in values

    def test_gauge_storage(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="temperature_celsius",
                metric_type=MetricType.GAUGE,
                pattern=r"temp=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "temp=22.5"})

        labels_key = json.dumps({}, sort_keys=True)
        stats = gen._metrics["temperature_celsius"][labels_key]
        assert stats.last_value == 22.5

    def test_rate_window_updated_for_throughput(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="throughput_rps",
                metric_type=MetricType.GAUGE,
                pattern=r"request",
            )
        )
        gen.process_log_record({"message": "request received"})
        assert len(gen._rate_windows["throughput_rps"]) == 1

    def test_rate_window_updated_for_request_metric(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="my_request_metric",
                metric_type=MetricType.GAUGE,
                pattern=r"event",
            )
        )
        gen.process_log_record({"message": "event"})
        assert len(gen._rate_windows["my_request_metric"]) == 1

    def test_histogram_pruning_by_time(self):
        """Old histogram entries beyond 1 hour should be pruned."""
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        old_time = time.time() - 7200  # 2 hours ago
        gen._histograms["request_duration_seconds"].append((1.0, {}, old_time))
        # Process a new entry to trigger pruning
        gen.add_extractor(
            MetricExtractor(
                name="request_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"dur=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "dur=50"})
        values = gen._histograms["request_duration_seconds"]
        # Old entry should have been pruned
        assert all(t > time.time() - 3700 for _, _, t in values)

    def test_histogram_cap_at_1000(self):
        """Histograms should keep at most 1000 entries."""
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        name = "request_duration_seconds"
        now = time.time()
        # Pre-fill with 1005 recent entries
        gen._histograms[name] = [(float(i), {}, now) for i in range(1005)]
        gen.add_extractor(
            MetricExtractor(
                name=name,
                metric_type=MetricType.HISTOGRAM,
                pattern=r"dur=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "dur=999"})
        assert len(gen._histograms[name]) <= 1000


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – _extract_memory_bytes
# ──────────────────────────────────────────────────────────────
class TestExtractMemoryBytes:
    """Tests for memory value extraction and unit conversion."""

    def setup_method(self):
        self.gen = AutoMetricsGenerator(enable_default_metrics=False)

    def test_gigabytes(self):
        record = {"message": "memory=2.5 GB"}
        result = self.gen._extract_memory_bytes(record)
        expected = 2.5 * 1024 * 1024 * 1024
        assert result == expected

    def test_megabytes(self):
        record = {"message": "memory=512 MB"}
        result = self.gen._extract_memory_bytes(record)
        expected = 512 * 1024 * 1024
        assert result == expected

    def test_kilobytes(self):
        record = {"message": "memory=1024 KB"}
        result = self.gen._extract_memory_bytes(record)
        expected = 1024 * 1024
        assert result == expected

    def test_bytes_no_unit(self):
        record = {"message": "memory=4096"}
        result = self.gen._extract_memory_bytes(record)
        assert result == 4096.0

    def test_no_memory_pattern(self):
        record = {"message": "no memory info here"}
        result = self.gen._extract_memory_bytes(record)
        assert result == 0.0

    def test_lowercase_unit_g(self):
        record = {"message": "memory: 1 g"}
        result = self.gen._extract_memory_bytes(record)
        assert result == 1.0 * 1024 * 1024 * 1024

    def test_lowercase_unit_m(self):
        record = {"message": "memory: 256 m"}
        result = self.gen._extract_memory_bytes(record)
        assert result == 256.0 * 1024 * 1024

    def test_lowercase_unit_k(self):
        record = {"message": "memory=64 k"}
        result = self.gen._extract_memory_bytes(record)
        assert result == 64.0 * 1024

    def test_colon_separator(self):
        record = {"message": "memory: 128 mb"}
        result = self.gen._extract_memory_bytes(record)
        assert result == 128.0 * 1024 * 1024

    def test_equals_separator(self):
        record = {"message": "memory=128 mb"}
        result = self.gen._extract_memory_bytes(record)
        assert result == 128.0 * 1024 * 1024


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – _extract_numeric_value
# ──────────────────────────────────────────────────────────────
class TestExtractNumericValue:
    """Tests for numeric value extraction from log records."""

    def setup_method(self):
        self.gen = AutoMetricsGenerator(enable_default_metrics=False)

    def test_direct_field_access(self):
        record = {"message": "op", "latency": 42.0}
        result = self.gen._extract_numeric_value(record, "latency")
        assert result == 42.0

    def test_direct_field_string_convertible(self):
        record = {"message": "op", "latency": "55"}
        result = self.gen._extract_numeric_value(record, "latency")
        assert result == 55.0

    def test_direct_field_non_numeric_falls_through(self):
        record = {"message": "latency=99", "latency": "not_num"}
        result = self.gen._extract_numeric_value(record, "latency")
        # Should fall through to pattern matching
        assert result == 99.0

    def test_pattern_match_in_message(self):
        record = {"message": "latency=123.4 ms"}
        result = self.gen._extract_numeric_value(record, "latency")
        assert result == 123.4

    def test_no_match_returns_zero(self):
        record = {"message": "no relevant info"}
        result = self.gen._extract_numeric_value(record, "latency")
        assert result == 0.0


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – percentile
# ──────────────────────────────────────────────────────────────
class TestPercentile:
    """Tests for percentile calculation."""

    def setup_method(self):
        self.gen = AutoMetricsGenerator(enable_default_metrics=False)

    def test_empty_list(self):
        assert self.gen._percentile([], 50) == 0.0

    def test_single_value(self):
        assert self.gen._percentile([10.0], 50) == 10.0

    def test_p50_even_count(self):
        values = [1.0, 2.0, 3.0, 4.0]
        result = self.gen._percentile(values, 50)
        assert result == 2.5

    def test_p0(self):
        values = [5.0, 10.0, 15.0]
        assert self.gen._percentile(values, 0) == 5.0

    def test_p100(self):
        values = [5.0, 10.0, 15.0]
        assert self.gen._percentile(values, 100) == 15.0

    def test_p95_large_dataset(self):
        values = list(range(1, 101))
        values = [float(v) for v in values]
        result = self.gen._percentile(values, 95)
        assert 95.0 <= result <= 96.0

    def test_unsorted_input(self):
        values = [50.0, 10.0, 30.0, 20.0, 40.0]
        p50 = self.gen._percentile(values, 50)
        assert p50 == 30.0


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – get_metrics_summary
# ──────────────────────────────────────────────────────────────
class TestGetMetricsSummary:
    """Tests for the metrics summary report."""

    def test_empty_summary_structure(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        summary = gen.get_metrics_summary()
        assert "counters" in summary
        assert "histograms" in summary
        assert "gauges" in summary
        assert "rates" in summary
        assert "collection_time" in summary

    def test_counter_summary(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="events_total",
                metric_type=MetricType.COUNTER,
                pattern=r"event",
            )
        )
        gen.process_log_record({"message": "event A"})
        gen.process_log_record({"message": "event B"})

        summary = gen.get_metrics_summary()
        assert summary["counters"]["events_total"]["total"] == 2

    def test_histogram_summary(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="request_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"dur=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "dur=100"})
        gen.process_log_record({"message": "dur=200"})
        gen.process_log_record({"message": "dur=300"})

        summary = gen.get_metrics_summary()
        hist = summary["histograms"]["request_duration_seconds"]
        assert hist["count"] == 3
        assert hist["sum"] == 600.0
        assert hist["min"] == 100.0
        assert hist["max"] == 300.0
        assert hist["avg"] == 200.0
        assert "p50" in hist
        assert "p95" in hist
        assert "p99" in hist

    def test_gauge_summary(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="temperature",
                metric_type=MetricType.GAUGE,
                pattern=r"temp=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "temp=20"})
        gen.process_log_record({"message": "temp=25"})

        summary = gen.get_metrics_summary()
        assert "temperature" in summary["gauges"]
        labels_key = json.dumps({}, sort_keys=True)
        gauge = summary["gauges"]["temperature"][labels_key]
        assert gauge["current"] == 25.0
        assert gauge["count"] == 2
        assert gauge["avg"] == 22.5

    def test_gauge_summary_min_max_defaults(self):
        """Gauge with inf min/max should show as 0."""
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        # Manually inject a MetricStats with no updates
        labels_key = json.dumps({}, sort_keys=True)
        gen._metrics["empty_gauge"][labels_key] = MetricStats()

        summary = gen.get_metrics_summary()
        gauge = summary["gauges"]["empty_gauge"][labels_key]
        assert gauge["min"] == 0
        assert gauge["max"] == 0

    def test_rate_summary(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="throughput_rps",
                metric_type=MetricType.GAUGE,
                pattern=r"request",
            )
        )
        gen.process_log_record({"message": "request 1"})
        gen.process_log_record({"message": "request 2"})

        summary = gen.get_metrics_summary()
        assert "throughput_rps" in summary["rates"]
        rate_info = summary["rates"]["throughput_rps"]
        assert rate_info["total_events"] == 2
        assert rate_info["events_last_minute"] == 2
        assert rate_info["current_rate_per_second"] > 0

    def test_empty_histogram_skipped(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen._histograms["empty_hist"] = []
        summary = gen.get_metrics_summary()
        assert "empty_hist" not in summary["histograms"]


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – export_prometheus_metrics
# ──────────────────────────────────────────────────────────────
class TestExportPrometheusMetrics:
    """Tests for Prometheus metrics export format."""

    def test_empty_export(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        output = gen.export_prometheus_metrics()
        assert output == ""

    def test_counter_export_format(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="errors_total",
                metric_type=MetricType.COUNTER,
                pattern=r"ERROR",
                labels=["level"],
            )
        )
        gen.process_log_record({"message": "ERROR happened", "level": "ERROR"})

        output = gen.export_prometheus_metrics()
        assert "# TYPE errors_total counter" in output
        assert 'errors_total{level="ERROR"}' in output

    def test_histogram_export_as_summary(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="request_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"dur=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "dur=100"})
        gen.process_log_record({"message": "dur=200"})

        output = gen.export_prometheus_metrics()
        assert "# TYPE request_duration_seconds summary" in output
        assert "request_duration_seconds_count 2" in output
        assert "request_duration_seconds_sum 300.0" in output
        assert 'quantile="0.5"' in output
        assert 'quantile="0.9"' in output
        assert 'quantile="0.95"' in output
        assert 'quantile="0.99"' in output

    def test_gauge_export_format(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="temperature",
                metric_type=MetricType.GAUGE,
                pattern=r"temp=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "temp=42.0"})

        output = gen.export_prometheus_metrics()
        assert "# TYPE temperature gauge" in output
        assert "temperature" in output
        assert "42.0" in output

    def test_counter_with_empty_labels(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="simple_total",
                metric_type=MetricType.COUNTER,
                pattern=r"event",
            )
        )
        gen.process_log_record({"message": "event"})

        output = gen.export_prometheus_metrics()
        # With no labels the metric line should not have braces
        lines = output.strip().split("\n")
        metric_lines = [
            ln
            for ln in lines
            if not ln.startswith("#") and "simple_total" in ln
        ]
        assert len(metric_lines) == 1
        # Should look like "simple_total 1 <timestamp>"
        assert metric_lines[0].startswith("simple_total ")

    def test_gauge_with_labels(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="cpu_usage",
                metric_type=MetricType.GAUGE,
                pattern=r"cpu=([0-9.]+)",
                labels=["service"],
            )
        )
        gen.process_log_record(
            {
                "message": "cpu=75.5",
                "service_name": "web",
            }
        )

        output = gen.export_prometheus_metrics()
        assert "# TYPE cpu_usage gauge" in output
        assert 'service="web"' in output

    def test_empty_histogram_skipped_in_export(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen._histograms["empty_hist"] = []
        output = gen.export_prometheus_metrics()
        assert "empty_hist" not in output


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – reset_metrics
# ──────────────────────────────────────────────────────────────
class TestResetMetrics:
    """Tests for resetting all collected metrics."""

    def test_reset_clears_everything(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="hits_total",
                metric_type=MetricType.COUNTER,
                pattern=r"hit",
            )
        )
        gen.process_log_record({"message": "cache hit"})

        # Pre-condition
        assert len(gen._counters) > 0

        gen.reset_metrics()
        assert len(gen._metrics) == 0
        assert len(gen._counters) == 0
        assert len(gen._histograms) == 0
        assert len(gen._rate_windows) == 0


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – get_error_rate
# ──────────────────────────────────────────────────────────────
class TestGetErrorRate:
    """Tests for error rate calculations."""

    def test_no_errors(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        rates = gen.get_error_rate()
        assert rates == {}

    def test_error_rate_calculation(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="log_errors_total",
                metric_type=MetricType.COUNTER,
                pattern=r"ERROR",
            )
        )
        for _ in range(10):
            gen.process_log_record({"message": "ERROR"})

        rates = gen.get_error_rate(time_window_seconds=100)
        assert "log_errors_total" in rates
        assert rates["log_errors_total"] == 10 / 100.0

    def test_error_rate_default_window(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="app_errors_total",
                metric_type=MetricType.COUNTER,
                pattern=r"error",
            )
        )
        gen.process_log_record({"message": "error"})

        rates = gen.get_error_rate()
        assert "app_errors_total" in rates
        assert rates["app_errors_total"] == 1 / 300.0

    def test_error_rate_zero_window(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="err_errors_total",
                metric_type=MetricType.COUNTER,
                pattern=r"err",
            )
        )
        gen.process_log_record({"message": "err"})

        rates = gen.get_error_rate(time_window_seconds=0)
        assert rates["err_errors_total"] == 0

    def test_non_error_counters_excluded(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="requests_total",
                metric_type=MetricType.COUNTER,
                pattern=r"request",
            )
        )
        gen.process_log_record({"message": "request"})

        rates = gen.get_error_rate()
        assert "requests_total" not in rates


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – get_latency_stats
# ──────────────────────────────────────────────────────────────
class TestGetLatencyStats:
    """Tests for latency statistics retrieval."""

    def test_no_latency_metrics(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        stats = gen.get_latency_stats()
        assert stats == {}

    def test_latency_stats_content(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="operation_latency_ms",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"lat=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "lat=10"})
        gen.process_log_record({"message": "lat=20"})
        gen.process_log_record({"message": "lat=30"})

        stats = gen.get_latency_stats()
        assert "operation_latency_ms" in stats
        lat = stats["operation_latency_ms"]
        assert lat["count"] == 3
        assert lat["avg_ms"] == 20.0
        assert lat["min_ms"] == 10.0
        assert lat["max_ms"] == 30.0
        assert "p50_ms" in lat
        assert "p95_ms" in lat
        assert "p99_ms" in lat

    def test_duration_metrics_included(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="request_duration_seconds",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"dur=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "dur=0.5"})

        stats = gen.get_latency_stats()
        assert "request_duration_seconds" in stats

    def test_non_latency_histogram_excluded(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="request_size_bytes",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"size=([0-9.]+)",
            )
        )
        gen.process_log_record({"message": "size=1024"})

        stats = gen.get_latency_stats()
        assert "request_size_bytes" not in stats

    def test_empty_histogram_skipped(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen._histograms["operation_latency_ms"] = []

        stats = gen.get_latency_stats()
        assert "operation_latency_ms" not in stats


# ──────────────────────────────────────────────────────────────
# AutoMetricsGenerator – default extractors integration
# ──────────────────────────────────────────────────────────────
class TestDefaultExtractorsIntegration:
    """Integration tests exercising the default extractors."""

    def setup_method(self):
        self.gen = AutoMetricsGenerator(enable_default_metrics=True)

    def test_error_log_counted(self):
        self.gen.process_log_record(
            {
                "message": "level=ERROR Something failed",
                "level": "ERROR",
            }
        )
        summary = self.gen.get_metrics_summary()
        assert summary["counters"]["log_errors_total"]["total"] >= 1

    def test_request_duration_extracted(self):
        self.gen.process_log_record({"message": "duration=250 ms"})
        assert len(self.gen._histograms["request_duration_seconds"]) >= 1

    def test_database_operation_counted(self):
        self.gen.process_log_record(
            {"message": "Executing database query SELECT *"}
        )
        summary = self.gen.get_metrics_summary()
        assert summary["counters"]["database_operations_total"]["total"] >= 1

    def test_cache_hit_counted(self):
        self.gen.process_log_record({"message": "cache hit for key user:123"})
        summary = self.gen.get_metrics_summary()
        assert summary["counters"]["cache_operations_total"]["total"] >= 1

    def test_http_status_counted(self):
        self.gen.process_log_record({"message": "status=200 GET /api/users"})
        summary = self.gen.get_metrics_summary()
        assert summary["counters"]["http_responses_total"]["total"] >= 1

    def test_memory_usage_gauge(self):
        self.gen.process_log_record({"message": "memory=512 MB used"})
        summary = self.gen.get_metrics_summary()
        assert "memory_usage_bytes" in summary["gauges"]

    def test_latency_extracted(self):
        self.gen.process_log_record({"message": "latency=45.2 ms"})
        assert len(self.gen._histograms["operation_latency_milliseconds"]) >= 1

    def test_throughput_rate_tracked(self):
        self.gen.process_log_record({"message": "processing request id=abc"})
        assert (
            len(self.gen._rate_windows["throughput_requests_per_second"]) >= 1
        )


# ──────────────────────────────────────────────────────────────
# Factory functions
# ──────────────────────────────────────────────────────────────
class TestCreateWebServiceMetrics:
    """Tests for the web service metrics factory."""

    def test_returns_generator(self):
        gen = create_web_service_metrics()
        assert isinstance(gen, AutoMetricsGenerator)

    def test_has_default_plus_web_extractors(self):
        gen = create_web_service_metrics()
        names = [e.name for e in gen._extractors]
        assert "http_request_size_bytes" in names
        assert "http_response_size_bytes" in names

    def test_request_size_extraction(self):
        gen = create_web_service_metrics()
        metrics = gen.process_log_record(
            {
                "message": "request_size=4096",
                "request_size": 4096,
            }
        )
        # The extractor fires; storage routing is name-based
        # so the metric may land in _metrics (gauge bucket)
        # rather than _histograms since the name lacks
        # "histogram"/"duration"/"latency".
        names = [m.name for m in metrics]
        assert "http_request_size_bytes" in names

    def test_response_size_extraction(self):
        gen = create_web_service_metrics()
        metrics = gen.process_log_record(
            {
                "message": "response_size=2048",
                "response_size": 2048,
            }
        )
        names = [m.name for m in metrics]
        assert "http_response_size_bytes" in names


class TestCreateDatabaseMetrics:
    """Tests for the database metrics factory."""

    def test_returns_generator(self):
        gen = create_database_metrics()
        assert isinstance(gen, AutoMetricsGenerator)

    def test_has_default_plus_db_extractors(self):
        gen = create_database_metrics()
        names = [e.name for e in gen._extractors]
        assert "database_connection_pool_size" in names
        assert "database_query_rows_returned" in names

    def test_pool_size_extraction(self):
        gen = create_database_metrics()
        gen.process_log_record(
            {
                "message": "connection pool size=10",
                "pool_size": 10,
            }
        )
        summary = gen.get_metrics_summary()
        assert "database_connection_pool_size" in summary["gauges"]

    def test_rows_returned_extraction(self):
        gen = create_database_metrics()
        metrics = gen.process_log_record(
            {
                "message": "rows returned=50",
                "rows_returned": 50,
            }
        )
        names = [m.name for m in metrics]
        assert "database_query_rows_returned" in names


# ──────────────────────────────────────────────────────────────
# Thread safety
# ──────────────────────────────────────────────────────────────
class TestThreadSafety:
    """Tests verifying thread-safe operation."""

    def test_concurrent_process_log_record(self):
        import threading

        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="concurrent_total",
                metric_type=MetricType.COUNTER,
                pattern=r"event",
            )
        )

        errors = []

        def worker():
            try:
                for _ in range(100):
                    gen.process_log_record({"message": "event"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        labels_key = json.dumps({}, sort_keys=True)
        assert gen._counters["concurrent_total"][labels_key] == 400

    def test_concurrent_add_extractor(self):
        import threading

        gen = AutoMetricsGenerator(enable_default_metrics=False)
        errors = []

        def worker(idx):
            try:
                gen.add_extractor(
                    MetricExtractor(
                        name=f"metric_{idx}",
                        metric_type=MetricType.COUNTER,
                        pattern=rf"pat_{idx}",
                    )
                )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(gen._extractors) == 20


# ──────────────────────────────────────────────────────────────
# Edge cases / miscellaneous
# ──────────────────────────────────────────────────────────────
class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_message(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="x_total",
                metric_type=MetricType.COUNTER,
                pattern=r"x",
            )
        )
        result = gen.process_log_record({"message": ""})
        assert result == []

    def test_missing_message_key(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="x_total",
                metric_type=MetricType.COUNTER,
                pattern=r"x",
            )
        )
        result = gen.process_log_record({})
        assert isinstance(result, list)

    def test_none_value_in_log_record(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="x_total",
                metric_type=MetricType.COUNTER,
                pattern=r"data",
                labels=["level"],
            )
        )
        result = gen.process_log_record({"message": "data", "level": None})
        assert len(result) == 1

    def test_metric_unit_propagated(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="size",
                metric_type=MetricType.HISTOGRAM,
                pattern=r"size=([0-9.]+)",
                unit="bytes",
            )
        )
        result = gen.process_log_record({"message": "size=100"})
        assert result[0].unit == "bytes"

    def test_prometheus_timestamp_is_milliseconds(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="check_total",
                metric_type=MetricType.COUNTER,
                pattern=r"check",
            )
        )
        gen.process_log_record({"message": "check"})
        output = gen.export_prometheus_metrics()
        # Parse the timestamp from the counter line
        lines = [
            ln
            for ln in output.split("\n")
            if not ln.startswith("#") and "check_total" in ln
        ]
        parts = lines[0].split()
        ts = int(parts[-1])
        # Should be in milliseconds (> 1e12)
        assert ts > 1_000_000_000_000

    def test_multiple_extractors_match_same_record(self):
        gen = AutoMetricsGenerator(enable_default_metrics=False)
        gen.add_extractor(
            MetricExtractor(
                name="a_total",
                metric_type=MetricType.COUNTER,
                pattern=r"event",
            )
        )
        gen.add_extractor(
            MetricExtractor(
                name="b_total",
                metric_type=MetricType.COUNTER,
                pattern=r"event",
            )
        )
        result = gen.process_log_record({"message": "event occurred"})
        names = [m.name for m in result]
        assert "a_total" in names
        assert "b_total" in names

    def test_full_workflow_end_to_end(self):
        """End-to-end: process, summarise, export, reset."""
        gen = AutoMetricsGenerator(enable_default_metrics=True)

        gen.process_log_record(
            {
                "message": "level=ERROR db query failed",
                "level": "ERROR",
                "service_name": "api",
            }
        )
        gen.process_log_record({"message": "duration=150 ms, status=200"})
        gen.process_log_record({"message": "latency=42 ms"})
        gen.process_log_record({"message": "memory=256 MB"})

        summary = gen.get_metrics_summary()
        assert summary["counters"]
        assert summary["histograms"] or summary["gauges"]

        prom = gen.export_prometheus_metrics()
        assert "# TYPE" in prom

        error_rates = gen.get_error_rate()
        assert len(error_rates) > 0

        latency = gen.get_latency_stats()
        assert len(latency) > 0

        gen.reset_metrics()
        summary_after = gen.get_metrics_summary()
        assert summary_after["counters"] == {}
        assert summary_after["histograms"] == {}
