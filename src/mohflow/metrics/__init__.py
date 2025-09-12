"""
MohFlow Automatic Metrics Generation

This package provides intelligent auto-generation of metrics from log messages:

- Pattern-based metric extraction from log content
- Multiple metric types: counters, histograms, gauges, summaries
- Automatic error rate and latency tracking
- Throughput and performance metrics
- Prometheus-compatible metrics export
- OpenTelemetry integration ready
- Customizable metric extractors

Example usage:

    from mohflow.metrics import (
        AutoMetricsGenerator, MetricExtractor, MetricType,
        create_web_service_metrics, create_database_metrics
    )

    # Web service metrics
    metrics_gen = create_web_service_metrics()

    # Process log record to extract metrics
    log_record = {
        'message': 'Request processed in 250ms',
        'level': 'INFO',
        'status_code': 200,
        'endpoint': '/api/users'
    }

    metrics = metrics_gen.process_log_record(log_record)

    # Get metrics summary
    summary = metrics_gen.get_metrics_summary()
    print(f"Request latency p95: {summary['histograms']['request_duration_seconds']['p95']}")

    # Export to Prometheus
    prometheus_metrics = metrics_gen.export_prometheus_metrics()
"""

from .auto_metrics import (
    AutoMetricsGenerator,
    MetricExtractor,
    MetricValue,
    MetricStats,
    MetricType,
    create_web_service_metrics,
    create_database_metrics,
)

__all__ = [
    "AutoMetricsGenerator",
    "MetricExtractor",
    "MetricValue",
    "MetricStats",
    "MetricType",
    "create_web_service_metrics",
    "create_database_metrics",
]
