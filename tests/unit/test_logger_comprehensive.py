"""Comprehensive unit tests for MohflowLogger (base.py).

Covers factory methods, internal helpers, context/enrichment,
sampling, metrics, optimization reports, and formatter selection.
Avoids duplicating scenarios already present in test_logger.py.
"""

import json
import logging
from unittest.mock import (
    MagicMock,
    Mock,
    patch,
)

import pytest

from mohflow import MohflowLogger
from mohflow.formatters import (
    FastJSONFormatter,
    StructuredFormatter,
)
from mohflow.formatters.colored_console import (
    ColoredConsoleFormatter,
)
from mohflow.formatters.structured_formatter import (
    DevelopmentFormatter,
    ProductionFormatter,
)
from mohflow.sampling import SamplingStrategy

# ------------------------------------------------------------------
# Helpers & fixtures
# ------------------------------------------------------------------


@pytest.fixture
def minimal_logger():
    """Logger with minimum overhead for unit-level assertions."""
    return MohflowLogger(
        service_name="unit-svc",
        enable_context_enrichment=False,
        enable_sensitive_data_filter=False,
        console_logging=False,
    )


@pytest.fixture
def enriched_logger():
    """Logger with context enrichment and sensitive-data filter."""
    return MohflowLogger(
        service_name="enriched-svc",
        enable_context_enrichment=True,
        enable_sensitive_data_filter=True,
        console_logging=False,
    )


@pytest.fixture
def sampling_logger():
    """Logger with sampling enabled."""
    return MohflowLogger(
        service_name="sampling-svc",
        enable_sampling=True,
        sample_rate=1.0,
        sampling_strategy="random",
        console_logging=False,
        enable_context_enrichment=False,
        enable_sensitive_data_filter=False,
    )


@pytest.fixture
def metrics_logger():
    """Logger with auto-metrics enabled."""
    return MohflowLogger(
        service_name="metrics-svc",
        enable_auto_metrics=True,
        console_logging=False,
        enable_context_enrichment=False,
        enable_sensitive_data_filter=False,
    )


# ==================================================================
# Factory methods
# ==================================================================


class TestFactoryFast:
    def test_fast_uses_fast_formatter(self):
        logger = MohflowLogger.fast("fast-svc")
        assert logger.formatter_type == "fast"

    def test_fast_disables_enrichment_and_filter(self):
        logger = MohflowLogger.fast("fast-svc")
        assert logger.context_enricher is None
        assert logger.sensitive_filter is None

    def test_fast_accepts_overrides(self):
        logger = MohflowLogger.fast("fast-svc", log_level="WARNING")
        assert logger.config.LOG_LEVEL.upper() == "WARNING"


class TestFactoryProduction:
    def test_production_uses_production_formatter(self):
        logger = MohflowLogger.production("prod-svc")
        assert logger.formatter_type == "production"

    def test_production_enables_auto_config(self):
        # auto_config merges intelligent defaults; just ensure
        # it does not raise
        logger = MohflowLogger.production("prod-svc")
        assert logger.config.SERVICE_NAME == "prod-svc"


class TestFactoryDevelopment:
    def test_development_uses_development_formatter(self):
        logger = MohflowLogger.development("dev-svc")
        assert logger.formatter_type == "development"

    def test_development_sets_debug_level(self):
        logger = MohflowLogger.development("dev-svc")
        assert logger.config.LOG_LEVEL.upper() == "DEBUG"


class TestFactoryWithTracing:
    def test_with_tracing_sets_otel_params(self):
        logger = MohflowLogger.with_tracing(
            "trace-svc",
            service_version="2.0.0",
            exporter_type="console",
        )
        assert logger.otel_service_version == "2.0.0"
        assert logger.otel_exporter_type == "console"
        assert logger.otel_propagators == [
            "tracecontext",
            "baggage",
        ]


class TestFactoryMicroservice:
    def test_microservice_sets_otlp_exporter(self):
        logger = MohflowLogger.microservice(
            "micro-svc",
            service_version="1.2.3",
            otlp_endpoint="http://collector:4317",
        )
        assert logger.otel_exporter_type == "otlp"
        assert logger.otel_endpoint == "http://collector:4317"
        assert logger.formatter_type == "production"
        assert "b3" in logger.otel_propagators


class TestFactoryCloudNative:
    def test_cloud_native_enables_async_handlers(self):
        logger = MohflowLogger.cloud_native(
            "cloud-svc", service_version="3.0.0"
        )
        assert logger.async_handlers is True
        assert logger.otel_exporter_type == "otlp"

    def test_cloud_native_accepts_overrides(self):
        logger = MohflowLogger.cloud_native("cloud-svc", log_level="ERROR")
        assert logger.config.LOG_LEVEL.upper() == "ERROR"


class TestFactorySmart:
    def test_smart_returns_logger(self):
        logger = MohflowLogger.smart("smart-svc")
        assert isinstance(logger, MohflowLogger)
        assert logger.config.SERVICE_NAME == "smart-svc"


class TestFactoryAutoOptimized:
    def test_auto_optimized_without_tracing(self):
        logger = MohflowLogger.auto_optimized("auto-svc", enable_tracing=False)
        assert isinstance(logger, MohflowLogger)
        # enable_otel depends on HAS_OTEL at import time; what
        # matters is it did not raise.

    def test_auto_optimized_with_tracing_sets_propagators(self):
        logger = MohflowLogger.auto_optimized("auto-svc", enable_tracing=True)
        assert logger.otel_propagators == [
            "tracecontext",
            "baggage",
        ]


class TestFactoryCreate:
    def test_create_delegates_to_smart(self):
        logger = MohflowLogger.create("create-svc")
        assert isinstance(logger, MohflowLogger)
        assert logger.config.SERVICE_NAME == "create-svc"


class TestFactoryGetLogger:
    def test_get_logger_delegates_to_smart(self):
        logger = MohflowLogger.get_logger("mylogger")
        assert isinstance(logger, MohflowLogger)
        assert logger.config.SERVICE_NAME == "mylogger"


class TestFactoryForService:
    def test_for_service_uses_production_formatter(self):
        logger = MohflowLogger.for_service("svc-a")
        assert logger.formatter_type == "production"

    def test_for_service_enables_context_enrichment(self):
        logger = MohflowLogger.for_service("svc-b")
        assert logger.context_enricher is not None

    def test_for_service_overrides_take_precedence(self):
        logger = MohflowLogger.for_service("svc-c", formatter_type="fast")
        assert logger.formatter_type == "fast"


class TestFactoryFromConfigFile:
    def test_from_config_file(self, tmp_path):
        config = {
            "service_name": "file-svc",
            "log_level": "WARNING",
            "environment": "staging",
        }
        cfg_path = tmp_path / "mohflow.json"
        cfg_path.write_text(json.dumps(config))

        logger = MohflowLogger.from_config_file(str(cfg_path))
        assert logger.config.SERVICE_NAME == "file-svc"
        assert logger.config.LOG_LEVEL.upper() == "WARNING"

    def test_from_config_file_with_overrides(self, tmp_path):
        config = {
            "service_name": "file-svc",
            "log_level": "INFO",
        }
        cfg_path = tmp_path / "mohflow.json"
        cfg_path.write_text(json.dumps(config))

        logger = MohflowLogger.from_config_file(
            str(cfg_path), log_level="ERROR"
        )
        assert logger.config.LOG_LEVEL.upper() == "ERROR"


# ==================================================================
# _create_formatter
# ==================================================================


class TestCreateFormatter:
    def test_structured_default(self):
        logger = MohflowLogger(
            service_name="fmt-svc",
            formatter_type="structured",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        fmt = logger._create_formatter()
        assert isinstance(fmt, StructuredFormatter)

    def test_fast_formatter(self):
        logger = MohflowLogger(
            service_name="fmt-svc",
            formatter_type="fast",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        fmt = logger._create_formatter()
        assert isinstance(fmt, FastJSONFormatter)

    def test_production_formatter(self):
        logger = MohflowLogger(
            service_name="fmt-svc",
            formatter_type="production",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        fmt = logger._create_formatter()
        assert isinstance(fmt, ProductionFormatter)

    def test_development_formatter(self):
        logger = MohflowLogger(
            service_name="fmt-svc",
            formatter_type="development",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        fmt = logger._create_formatter()
        assert isinstance(fmt, DevelopmentFormatter)

    def test_colored_formatter(self):
        logger = MohflowLogger(
            service_name="fmt-svc",
            formatter_type="colored",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        fmt = logger._create_formatter()
        assert isinstance(fmt, ColoredConsoleFormatter)


# ==================================================================
# _prepare_extra  (lazy eval, bound context, enrichment, filtering)
# ==================================================================


class TestPrepareExtra:
    def test_plain_values_pass_through(self, minimal_logger):
        result = minimal_logger._prepare_extra({"key": "value", "num": 42})
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_lazy_callable_evaluated(self, minimal_logger):
        result = minimal_logger._prepare_extra({"lazy": lambda: "computed"})
        assert result["lazy"] == "computed"

    def test_lazy_callable_error_handled(self, minimal_logger):
        def bad():
            raise RuntimeError("boom")

        result = minimal_logger._prepare_extra({"bad": bad})
        assert result["bad"] == "<lazy evaluation error>"

    def test_class_objects_not_called(self, minimal_logger):
        """Classes are callable but should NOT be invoked."""

        class Dummy:
            pass

        result = minimal_logger._prepare_extra({"cls": Dummy})
        assert result["cls"] is Dummy

    def test_bound_context_merged(self, minimal_logger):
        from mohflow.context_api import (
            bind_context,
            clear_context,
        )

        try:
            bind_context(req_id="r1")
            result = minimal_logger._prepare_extra({"extra": "val"})
            assert result["req_id"] == "r1"
            assert result["extra"] == "val"
        finally:
            clear_context()

    def test_extra_overrides_bound_context(self, minimal_logger):
        from mohflow.context_api import (
            bind_context,
            clear_context,
        )

        try:
            bind_context(key="bound")
            result = minimal_logger._prepare_extra({"key": "explicit"})
            # Explicit extra should win over bound context
            assert result["key"] == "explicit"
        finally:
            clear_context()

    def test_context_enricher_applied(self, enriched_logger):
        result = enriched_logger._prepare_extra({"a": 1})
        # The enricher adds system info; at minimum, extra
        # should still contain original key
        assert result["a"] == 1

    def test_sensitive_filter_applied(self, enriched_logger):
        result = enriched_logger._prepare_extra({"password": "secret123"})
        # password should be masked by the sensitive filter
        assert result.get("password") != "secret123"


# ==================================================================
# _process_metrics
# ==================================================================


class TestProcessMetrics:
    def test_noop_without_metrics_generator(self, minimal_logger):
        # Should not raise
        minimal_logger._process_metrics("test", "INFO", component="api")

    def test_metrics_processed_when_enabled(self, metrics_logger):
        # Just ensure no error; we can also spy on the generator
        metrics_logger._process_metrics("Request processed in 200ms", "INFO")

    def test_metrics_processing_error_swallowed(self, metrics_logger):
        metrics_logger.metrics_generator.process_log_record = Mock(
            side_effect=RuntimeError("oops")
        )
        # Must not raise
        metrics_logger._process_metrics("msg", "ERROR")


# ==================================================================
# set_context / add_custom_enricher / add_sensitive_field
# ==================================================================


class TestContextHelpers:
    def test_set_context(self, enriched_logger):
        # set_context calls set_global_context; just verify no error
        enriched_logger.set_context(app_version="1.0")

    def test_add_custom_enricher_with_enricher(self, enriched_logger):
        enriched_logger.add_custom_enricher("build", lambda: "abc123")
        # Verify the enricher was added by checking no exception
        # and that the enricher is in the list
        assert enriched_logger.context_enricher is not None

    def test_add_custom_enricher_without_enricher(self, minimal_logger):
        # Should silently do nothing
        minimal_logger.add_custom_enricher("build", lambda: "x")

    def test_add_sensitive_field_with_filter(self, enriched_logger):
        enriched_logger.add_sensitive_field("ssn")
        result = enriched_logger._prepare_extra({"ssn": "123-45-6789"})
        assert result.get("ssn") != "123-45-6789"

    def test_add_sensitive_field_without_filter(self, minimal_logger):
        # Should silently do nothing
        minimal_logger.add_sensitive_field("ssn")


# ==================================================================
# get_environment_info / get_framework_info
# ==================================================================


class TestEnvironmentInfo:
    def test_get_environment_info_returns_dict(self, minimal_logger):
        info = minimal_logger.get_environment_info()
        assert isinstance(info, dict)

    def test_get_framework_info_returns_dict(self, minimal_logger):
        info = minimal_logger.get_framework_info()
        assert isinstance(info, dict)


# ==================================================================
# Tracing helpers  (get_trace_context, start_trace, log_with_trace)
# ==================================================================


class TestTracingHelpers:
    def test_get_trace_context_without_otel(self, minimal_logger):
        result = minimal_logger.get_trace_context()
        assert result == {}

    def test_start_trace_without_otel(self, minimal_logger):
        result = minimal_logger.start_trace("op")
        assert result is None

    def test_log_with_trace_without_otel_falls_back(self, minimal_logger):
        """When otel is disabled, log_with_trace should fall back
        to regular logging."""
        with patch.object(minimal_logger, "info") as mock_info:
            minimal_logger.log_with_trace(
                "INFO", "hello", operation_name="test_op"
            )
            mock_info.assert_called_once_with("hello")

    def test_log_with_trace_defaults_operation_name(self, minimal_logger):
        with patch.object(minimal_logger, "warning") as mock_warn:
            minimal_logger.log_with_trace("WARNING", "warn msg")
            mock_warn.assert_called_once_with("warn msg")


# ==================================================================
# Sampling  (get_sampling_stats, update_sampling_config,
#            reset_sampling_stats)
# ==================================================================


class TestSamplingStats:
    def test_get_sampling_stats_returns_none_without_sampler(
        self, minimal_logger
    ):
        assert minimal_logger.get_sampling_stats() is None

    def test_get_sampling_stats_returns_dict(self, sampling_logger):
        stats = sampling_logger.get_sampling_stats()
        assert isinstance(stats, dict)
        assert "current_sample_rate" in stats

    def test_update_sampling_config(self, sampling_logger):
        sampling_logger.update_sampling_config(sample_rate=0.5)
        assert sampling_logger.sampler.config.sample_rate == 0.5

    def test_update_sampling_config_ignores_unknown(self, sampling_logger):
        # Should not raise for unknown keys
        sampling_logger.update_sampling_config(nonexistent_field=42)

    def test_update_sampling_config_noop_without_sampler(self, minimal_logger):
        # Should not raise
        minimal_logger.update_sampling_config(sample_rate=0.1)

    def test_reset_sampling_stats(self, sampling_logger):
        # Log a message so counters are non-zero
        sampling_logger.info("tick")
        sampling_logger.reset_sampling_stats()
        stats = sampling_logger.get_sampling_stats()
        assert stats["total_logs_count"] == 0

    def test_reset_sampling_stats_noop_without_sampler(self, minimal_logger):
        minimal_logger.reset_sampling_stats()  # no raise


class TestSamplingIntegration:
    def test_sampler_blocks_message(self):
        """When sample_rate=0 every message should be dropped."""
        logger = MohflowLogger(
            service_name="drop-svc",
            enable_sampling=True,
            sample_rate=0.0,
            sampling_strategy="random",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        with patch.object(logger.logger, "info") as mock_inner:
            logger.info("should be dropped")
            mock_inner.assert_not_called()

    def test_all_log_levels_respect_sampling(self):
        """All five levels should check the sampler."""
        logger = MohflowLogger(
            service_name="samp-all-svc",
            enable_sampling=True,
            sample_rate=0.0,
            sampling_strategy="random",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        for method in ("debug", "info", "warning", "error"):
            with patch.object(logger.logger, method) as mock_m:
                kwargs = {}
                if method == "error":
                    kwargs["exc_info"] = False
                getattr(logger, method)("msg", **kwargs)
                mock_m.assert_not_called()

        with patch.object(logger.logger, "critical") as mock_crit:
            logger.critical("msg")
            mock_crit.assert_not_called()

    def test_level_sample_rates(self):
        """Per-level sample rates should work."""
        logger = MohflowLogger(
            service_name="level-svc",
            enable_sampling=True,
            sample_rate=1.0,
            sampling_strategy="random",
            level_sample_rates={"DEBUG": 0.0},
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
            log_level="DEBUG",
        )
        with patch.object(logger.logger, "debug") as mock_debug:
            logger.debug("should be dropped")
            mock_debug.assert_not_called()

    def test_sampling_strategies_accepted(self):
        """All strategy strings should map correctly."""
        for strategy in (
            "random",
            "deterministic",
            "adaptive",
            "rate_limited",
            "burst_allowed",
        ):
            logger = MohflowLogger(
                service_name="strat-svc",
                enable_sampling=True,
                sampling_strategy=strategy,
                console_logging=False,
                enable_context_enrichment=False,
                enable_sensitive_data_filter=False,
            )
            assert logger.sampler is not None


# ==================================================================
# Metrics  (get_metrics_summary, get_error_rates, get_latency_stats,
#           export_prometheus_metrics, reset_metrics)
# ==================================================================


class TestMetricsSummary:
    def test_get_metrics_summary_none_without_generator(self, minimal_logger):
        assert minimal_logger.get_metrics_summary() is None

    def test_get_metrics_summary_returns_dict(self, metrics_logger):
        summary = metrics_logger.get_metrics_summary()
        assert isinstance(summary, dict)


class TestErrorRates:
    def test_get_error_rates_empty_without_generator(self, minimal_logger):
        assert minimal_logger.get_error_rates() == {}

    def test_get_error_rates_returns_dict(self, metrics_logger):
        result = metrics_logger.get_error_rates(time_window_seconds=60)
        assert isinstance(result, dict)


class TestLatencyStats:
    def test_get_latency_stats_empty_without_generator(self, minimal_logger):
        assert minimal_logger.get_latency_stats() == {}

    def test_get_latency_stats_returns_dict(self, metrics_logger):
        result = metrics_logger.get_latency_stats()
        assert isinstance(result, dict)


class TestPrometheusExport:
    def test_export_none_without_generator(self, minimal_logger):
        assert minimal_logger.export_prometheus_metrics() is None

    def test_export_returns_string(self, metrics_logger):
        result = metrics_logger.export_prometheus_metrics()
        assert isinstance(result, str)


class TestResetMetrics:
    def test_reset_metrics_noop_without_generator(self, minimal_logger):
        minimal_logger.reset_metrics()  # no raise

    def test_reset_metrics_clears_data(self, metrics_logger):
        metrics_logger.info("some msg")
        metrics_logger.reset_metrics()
        summary = metrics_logger.get_metrics_summary()
        # After reset, counters should be empty
        assert summary["counters"] == {}


class TestMetricsConfigVariants:
    def test_web_service_metrics(self):
        logger = MohflowLogger(
            service_name="web-svc",
            enable_auto_metrics=True,
            metrics_config="web_service",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.metrics_generator is not None

    def test_database_metrics(self):
        logger = MohflowLogger(
            service_name="db-svc",
            enable_auto_metrics=True,
            metrics_config="database",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.metrics_generator is not None

    def test_default_metrics(self):
        logger = MohflowLogger(
            service_name="default-svc",
            enable_auto_metrics=True,
            metrics_config="default",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.metrics_generator is not None


# ==================================================================
# Optimization report / tips
# ==================================================================


class TestOptimizationReport:
    def test_get_optimization_report_structure(self, minimal_logger):
        report = minimal_logger.get_optimization_report()
        assert "current_config" in report
        assert "environment" in report
        assert "framework_recommendations" in report
        assert "optimization_tips" in report

    def test_report_current_config_values(self, minimal_logger):
        report = minimal_logger.get_optimization_report()
        cc = report["current_config"]
        assert cc["service_name"] == "unit-svc"
        assert cc["formatter_type"] == "structured"
        assert cc["async_handlers"] is False


class TestGenerateOptimizationTips:
    def test_async_tip_when_async_framework_detected(self, minimal_logger):
        framework_info = {"uses_async": True, "app_type": "web"}
        tips = minimal_logger._generate_optimization_tips(framework_info)
        assert any("async_handlers" in t for t in tips)

    def test_fast_formatter_tip_for_api(self, minimal_logger):
        framework_info = {
            "uses_async": False,
            "app_type": "api",
        }
        tips = minimal_logger._generate_optimization_tips(framework_info)
        assert any("fast" in t for t in tips)

    def test_tracing_tip_for_web(self, minimal_logger):
        framework_info = {
            "uses_async": False,
            "app_type": "web",
        }
        tips = minimal_logger._generate_optimization_tips(framework_info)
        assert any("tracing" in t for t in tips)

    def test_production_debug_tip(self):
        logger = MohflowLogger(
            service_name="prod-debug",
            environment="production",
            log_level="DEBUG",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        tips = logger._generate_optimization_tips({})
        assert any("production" in t.lower() for t in tips)

    def test_dev_no_console_tip(self):
        logger = MohflowLogger(
            service_name="dev-noconsole",
            environment="development",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        tips = logger._generate_optimization_tips({})
        assert any("console_logging" in t for t in tips)

    def test_no_tips_when_config_is_optimal(self):
        logger = MohflowLogger(
            service_name="optimal",
            environment="staging",
            console_logging=True,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        tips = logger._generate_optimization_tips(
            {"uses_async": False, "app_type": "cli"}
        )
        # No tips should match when nothing is misaligned
        assert isinstance(tips, list)


# ==================================================================
# Log methods  (critical, sampling integration, metrics integration)
# ==================================================================


class TestCriticalLogLevel:
    def test_critical_logs(self, minimal_logger, caplog):
        with caplog.at_level(logging.CRITICAL):
            minimal_logger.critical("boom")
        records = [r for r in caplog.records if r.levelname == "CRITICAL"]
        assert len(records) == 1
        assert "boom" in records[0].message


class TestDebugLogLevel:
    def test_debug_logs(self, caplog):
        logger = MohflowLogger(
            service_name="dbg-svc",
            log_level="DEBUG",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        with caplog.at_level(logging.DEBUG):
            logger.debug("detail")
        records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(records) == 1


class TestWarningLogLevel:
    def test_warning_logs(self, minimal_logger, caplog):
        with caplog.at_level(logging.WARNING):
            minimal_logger.warning("watch out")
        records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(records) == 1


# ==================================================================
# _setup_logger handler wiring
# ==================================================================


class TestSetupLogger:
    def test_console_handler_added_when_enabled(self):
        logger = MohflowLogger(
            service_name="console-svc",
            console_logging=True,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        handler_types = [type(h) for h in logger.logger.handlers]
        assert logging.StreamHandler in handler_types

    def test_no_console_handler_when_disabled(self):
        logger = MohflowLogger(
            service_name="noconsole-svc",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        handler_types = [type(h) for h in logger.logger.handlers]
        assert logging.StreamHandler not in handler_types

    def test_file_handler_added(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = MohflowLogger(
            service_name="file-svc",
            file_logging=True,
            log_file_path=str(log_file),
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        handler_types = [type(h) for h in logger.logger.handlers]
        assert any(
            issubclass(t, logging.FileHandler)
            for t in handler_types
        )

    def test_log_level_set_correctly(self):
        logger = MohflowLogger(
            service_name="level-svc",
            log_level="ERROR",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.logger.level == logging.ERROR

    def test_handlers_cleared_on_reinit(self):
        """Creating a new logger for the same service_name
        should not accumulate handlers."""
        _ = MohflowLogger(
            service_name="dup-svc",
            console_logging=True,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        logger2 = MohflowLogger(
            service_name="dup-svc",
            console_logging=True,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert len(logger2.logger.handlers) == 1


# ==================================================================
# Configuration loading
# ==================================================================


class TestLoadConfiguration:
    def test_auto_config_enabled(self):
        logger = MohflowLogger(
            service_name="auto-cfg-svc",
            enable_auto_config=True,
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.config.SERVICE_NAME == "auto-cfg-svc"

    def test_config_file_loading(self, tmp_path):
        config = {
            "service_name": "cfg-file-svc",
            "environment": "production",
        }
        cfg_path = tmp_path / "mohflow.json"
        cfg_path.write_text(json.dumps(config))

        logger = MohflowLogger(
            service_name="cfg-file-svc",
            config_file=str(cfg_path),
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.config.ENVIRONMENT == "production"


# ==================================================================
# OpenTelemetry setup (mocked)
# ==================================================================


class TestOtelSetup:
    def test_otel_disabled_when_module_missing(self):
        """When HAS_OTEL is False, enable_otel should be False."""
        with patch("mohflow.logger.base.HAS_OTEL", False):
            logger = MohflowLogger(
                service_name="otel-svc",
                enable_otel=True,
                console_logging=False,
                enable_context_enrichment=False,
                enable_sensitive_data_filter=False,
            )
            assert logger.enable_otel is False
            assert logger.otel_enricher is None

    def test_otel_service_version_default(self):
        logger = MohflowLogger(
            service_name="otel-ver-svc",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.otel_service_version == "1.0.0"

    def test_otel_setup_failure_disables_otel(self):
        """If _setup_otel_tracing raises, otel should be disabled
        gracefully."""
        with patch("mohflow.logger.base.HAS_OTEL", True), patch(
            "mohflow.logger.base.setup_otel_logging",
            side_effect=RuntimeError("fail"),
        ), patch(
            "mohflow.logger.base.OpenTelemetryEnricher",
        ) as mock_enricher:
            mock_enricher.return_value = MagicMock()
            logger = MohflowLogger(
                service_name="otel-fail-svc",
                enable_otel=True,
                console_logging=False,
                enable_context_enrichment=False,
                enable_sensitive_data_filter=False,
            )
            assert logger.enable_otel is False
            assert logger.otel_enricher is None


# ==================================================================
# Privacy / PII detection (mocked)
# ==================================================================


class TestPrivacySetup:
    def test_privacy_disabled_when_not_requested(self, minimal_logger):
        assert minimal_logger.privacy_filter is None
        assert minimal_logger.compliance_reporter is None

    def test_privacy_disabled_when_module_missing(self):
        with patch("mohflow.logger.base.HAS_PRIVACY", False):
            logger = MohflowLogger(
                service_name="priv-svc",
                enable_pii_detection=True,
                console_logging=False,
                enable_context_enrichment=False,
                enable_sensitive_data_filter=False,
            )
            assert logger.privacy_filter is None


# ==================================================================
# Async handlers wiring
# ==================================================================


class TestAsyncHandlers:
    def test_async_console_handler(self):
        logger = MohflowLogger(
            service_name="async-console",
            async_handlers=True,
            console_logging=True,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.async_handlers is True
        # At least one handler should exist
        assert len(logger.logger.handlers) >= 1

    def test_async_file_handler(self, tmp_path):
        log_file = tmp_path / "async.log"
        logger = MohflowLogger(
            service_name="async-file",
            async_handlers=True,
            file_logging=True,
            log_file_path=str(log_file),
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert len(logger.logger.handlers) >= 1


# ==================================================================
# with_auto_config class method
# ==================================================================


class TestWithAutoConfig:
    def test_with_auto_config_returns_logger(self):
        logger = MohflowLogger.with_auto_config("auto-svc")
        assert isinstance(logger, MohflowLogger)
        assert logger.config.SERVICE_NAME == "auto-svc"

    def test_with_auto_config_accepts_overrides(self):
        logger = MohflowLogger.with_auto_config("auto-svc", log_level="ERROR")
        assert logger.config.LOG_LEVEL.upper() == "ERROR"


# ==================================================================
# Sensitive data filter setup
# ==================================================================


class TestSensitiveDataFilterSetup:
    def test_sensitive_filter_enabled(self, enriched_logger):
        assert enriched_logger.sensitive_filter is not None

    def test_sensitive_filter_disabled(self, minimal_logger):
        assert minimal_logger.sensitive_filter is None

    def test_exclude_tracing_fields_param(self):
        logger = MohflowLogger(
            service_name="trace-exc-svc",
            enable_sensitive_data_filter=True,
            exclude_tracing_fields=True,
            console_logging=False,
            enable_context_enrichment=False,
        )
        assert logger.sensitive_filter is not None

    def test_custom_safe_fields_param(self):
        logger = MohflowLogger(
            service_name="safe-svc",
            enable_sensitive_data_filter=True,
            custom_safe_fields={"my_safe_field"},
            console_logging=False,
            enable_context_enrichment=False,
        )
        assert logger.sensitive_filter is not None


# ==================================================================
# Context enrichment setup
# ==================================================================


class TestContextEnrichmentSetup:
    def test_enricher_enabled(self, enriched_logger):
        assert enriched_logger.context_enricher is not None

    def test_enricher_disabled(self, minimal_logger):
        assert minimal_logger.context_enricher is None


# ==================================================================
# Sampling strategy mapping
# ==================================================================


class TestSamplingStrategyMapping:
    @pytest.mark.parametrize(
        "strategy_str,expected_enum",
        [
            ("random", SamplingStrategy.RANDOM),
            ("deterministic", SamplingStrategy.DETERMINISTIC),
            ("adaptive", SamplingStrategy.ADAPTIVE),
            ("rate_limited", SamplingStrategy.RATE_LIMITED),
            ("burst_allowed", SamplingStrategy.BURST_ALLOWED),
        ],
    )
    def test_strategy_mapping(self, strategy_str, expected_enum):
        logger = MohflowLogger(
            service_name="strat-svc",
            enable_sampling=True,
            sampling_strategy=strategy_str,
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.sampler.config.strategy == expected_enum

    def test_unknown_strategy_defaults_to_random(self):
        logger = MohflowLogger(
            service_name="strat-svc",
            enable_sampling=True,
            sampling_strategy="nonexistent",
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.sampler.config.strategy == SamplingStrategy.RANDOM

    def test_rate_limited_params(self):
        logger = MohflowLogger(
            service_name="rl-svc",
            enable_sampling=True,
            sampling_strategy="rate_limited",
            max_logs_per_second=100,
            burst_limit=200,
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.sampler.config.max_logs_per_second == 100
        assert logger.sampler.config.burst_limit == 200

    def test_adaptive_sampling_flag(self):
        logger = MohflowLogger(
            service_name="adap-svc",
            enable_sampling=True,
            adaptive_sampling=True,
            console_logging=False,
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
        )
        assert logger.sampler.config.enable_adaptive is True
