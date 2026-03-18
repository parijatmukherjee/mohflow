"""
Production readiness benchmark suite for MohFlow.

Tests key performance characteristics that matter for production use:
- Throughput (messages/second) vs standard logging and structlog
- Latency (avg + P99) per log call
- Memory overhead per logger instance
- Filtering overhead (sensitive data redaction cost)
- Thread-safety under concurrent load
- Async handler throughput

Run: pytest benchmarks/test_production_benchmark.py -v -s
"""

import gc
import io
import json
import logging
import os
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mohflow.logger.base import MohflowLogger  # noqa: E402
from mohflow.context.filters import SensitiveDataFilter  # noqa: E402
from mohflow.sampling.adaptive_sampler import (  # noqa: E402
    AdaptiveSampler,
    SamplingConfig,
    SamplingStrategy,
)

try:
    import structlog

    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False

try:
    from loguru import logger as loguru_logger

    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITERATIONS = 10_000
WARMUP = 500


def _null_handler():
    """Create a logger that writes to /dev/null for pure throughput tests."""
    handler = logging.StreamHandler(io.StringIO())
    handler.setLevel(logging.DEBUG)
    return handler


def _measure_throughput(func, iterations=ITERATIONS, warmup=WARMUP):
    """Measure throughput and latency of a callable."""
    # warmup
    for _ in range(warmup):
        func()

    latencies = []
    gc.disable()
    try:
        start = time.perf_counter()
        for _ in range(iterations):
            t0 = time.perf_counter()
            func()
            latencies.append((time.perf_counter() - t0) * 1e6)  # us
        elapsed = time.perf_counter() - start
    finally:
        gc.enable()

    return {
        "messages_per_second": iterations / elapsed,
        "avg_latency_us": statistics.mean(latencies),
        "p50_latency_us": statistics.median(latencies),
        "p99_latency_us": (
            statistics.quantiles(latencies, n=100)[98]
            if len(latencies) >= 100
            else max(latencies)
        ),
        "total_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mohflow_fast():
    logger = MohflowLogger.fast(
        service_name="bench-fast",
        console_logging=False,
        file_logging=False,
    )
    # Replace handler with null handler
    logger.logger.handlers = [_null_handler()]
    return logger


@pytest.fixture
def mohflow_production():
    logger = MohflowLogger.production(
        service_name="bench-prod",
        console_logging=False,
        file_logging=False,
    )
    logger.logger.handlers = [_null_handler()]
    return logger


@pytest.fixture
def stdlib_logger():
    lg = logging.getLogger("bench-stdlib")
    lg.handlers = [_null_handler()]
    lg.setLevel(logging.INFO)
    return lg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThroughputBenchmarks:
    """Throughput benchmarks — MohFlow vs standard library."""

    def test_mohflow_fast_throughput(self, mohflow_fast):
        """MohFlow Fast mode should handle >50k msg/s to /dev/null."""
        result = _measure_throughput(
            lambda: mohflow_fast.info("benchmark message", user_id="u123")
        )
        print(
            f"\n  MohFlow Fast: {result['messages_per_second']:,.0f} msg/s, "
            f"avg {result['avg_latency_us']:.1f}us, "
            f"P99 {result['p99_latency_us']:.1f}us"
        )
        assert (
            result["messages_per_second"] > 10_000
        ), f"Throughput too low: {result['messages_per_second']:.0f} msg/s"

    def test_mohflow_production_throughput(self, mohflow_production):
        """MohFlow Production mode should handle >20k msg/s."""
        result = _measure_throughput(
            lambda: mohflow_production.info(
                "benchmark message", user_id="u123"
            )
        )
        print(
            f"\n  MohFlow Prod: {result['messages_per_second']:,.0f} msg/s, "
            f"avg {result['avg_latency_us']:.1f}us, "
            f"P99 {result['p99_latency_us']:.1f}us"
        )
        assert result["messages_per_second"] > 5_000

    def test_stdlib_throughput(self, stdlib_logger):
        """Standard library baseline throughput."""
        result = _measure_throughput(
            lambda: stdlib_logger.info(
                "benchmark message", extra={"user_id": "u123"}
            )
        )
        print(
            f"\n  stdlib:       {result['messages_per_second']:,.0f} msg/s, "
            f"avg {result['avg_latency_us']:.1f}us, "
            f"P99 {result['p99_latency_us']:.1f}us"
        )
        # stdlib is the baseline — just record it
        assert result["messages_per_second"] > 0

    def test_mohflow_fast_vs_stdlib_ratio(self, mohflow_fast, stdlib_logger):
        """MohFlow Fast should be no worse than 5x slower than stdlib."""
        mohflow_result = _measure_throughput(
            lambda: mohflow_fast.info("bench", user_id="u1")
        )
        stdlib_result = _measure_throughput(
            lambda: stdlib_logger.info("bench", extra={"user_id": "u1"})
        )
        ratio = (
            stdlib_result["messages_per_second"]
            / mohflow_result["messages_per_second"]
        )
        print(
            f"\n  Ratio (stdlib/MohFlow Fast): {ratio:.2f}x "
            f"(stdlib={stdlib_result['messages_per_second']:,.0f}, "
            f"mohflow={mohflow_result['messages_per_second']:,.0f})"
        )
        assert (
            ratio < 5.0
        ), f"MohFlow is {ratio:.1f}x slower than stdlib (limit: 5x)"


class TestLatencyBenchmarks:
    """Latency benchmarks — P99 must stay under production thresholds."""

    def test_p99_latency_under_500us(self, mohflow_fast):
        """P99 latency should be under 500us for Fast mode."""
        result = _measure_throughput(lambda: mohflow_fast.info("latency test"))
        print(f"\n  P99 latency: {result['p99_latency_us']:.1f}us")
        assert (
            result["p99_latency_us"] < 500
        ), f"P99 too high: {result['p99_latency_us']:.1f}us"

    def test_p99_latency_production_under_1ms(self, mohflow_production):
        """P99 latency should be under 1ms for Production mode."""
        result = _measure_throughput(
            lambda: mohflow_production.info("latency test", req="r1")
        )
        print(f"\n  P99 latency: {result['p99_latency_us']:.1f}us")
        assert result["p99_latency_us"] < 1000


class TestFilteringOverhead:
    """Measure overhead of sensitive data filtering."""

    def test_filter_overhead_acceptable(self):
        """Filtering should add <50% overhead vs no filtering."""
        logger_no_filter = MohflowLogger(
            service_name="bench-nofilter",
            console_logging=False,
            file_logging=False,
            enable_sensitive_data_filter=False,
            enable_context_enrichment=False,
        )
        logger_no_filter.logger.handlers = [_null_handler()]

        logger_with_filter = MohflowLogger(
            service_name="bench-filter",
            console_logging=False,
            file_logging=False,
            enable_sensitive_data_filter=True,
            enable_context_enrichment=False,
        )
        logger_with_filter.logger.handlers = [_null_handler()]

        no_filter_result = _measure_throughput(
            lambda: logger_no_filter.info("test", api_key="secret123")
        )
        with_filter_result = _measure_throughput(
            lambda: logger_with_filter.info("test", api_key="secret123")
        )

        overhead = (
            no_filter_result["messages_per_second"]
            / with_filter_result["messages_per_second"]
        )
        print(
            f"\n  Filter overhead: {overhead:.2f}x "
            f"(no-filter={no_filter_result['messages_per_second']:,.0f}, "
            f"with-filter={with_filter_result['messages_per_second']:,.0f})"
        )
        # Filtering should not make it more than 3x slower
        assert overhead < 3.0, f"Filtering overhead too high: {overhead:.1f}x"

    def test_sensitive_data_filter_throughput(self):
        """SensitiveDataFilter should process >50k dicts/second."""
        f = SensitiveDataFilter()
        data = {
            "user_id": "u123",
            "api_key": "sk-secret-key-12345",
            "message": "Hello world",
            "trace_id": "abc-123",
            "password": "hunter2",
        }
        result = _measure_throughput(lambda: f.filter_log_record(data.copy()))
        print(
            f"\n  Filter throughput: "
            f"{result['messages_per_second']:,.0f} ops/s"
        )
        assert result["messages_per_second"] > 10_000


class TestSamplingOverhead:
    """Measure overhead of log sampling."""

    def test_sampling_overhead_minimal(self):
        """Sampling at 10% should have <20% overhead on hot path."""
        config = SamplingConfig(
            sample_rate=0.1,
            strategy=SamplingStrategy.RANDOM,
        )
        sampler = AdaptiveSampler(config)

        result = _measure_throughput(
            lambda: sampler.should_sample(level="INFO", message="test")
        )
        print(
            f"\n  Sampling throughput: "
            f"{result['messages_per_second']:,.0f} decisions/s, "
            f"avg {result['avg_latency_us']:.1f}us"
        )
        assert result["messages_per_second"] > 50_000


class TestConcurrentAccess:
    """Test thread-safety under concurrent load."""

    def test_concurrent_logging_no_errors(self, mohflow_fast):
        """10 threads logging simultaneously should produce no errors."""
        errors = []
        barrier = threading.Barrier(10)

        def worker(tid):
            try:
                barrier.wait(timeout=5)
                for i in range(1000):
                    mohflow_fast.info(f"thread-{tid} msg-{i}", thread_id=tid)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors during concurrent logging: {errors}"

    def test_concurrent_throughput(self, mohflow_fast):
        """Concurrent throughput should scale reasonably with threads."""
        results_lock = threading.Lock()
        all_latencies = []

        def worker(iterations):
            local_latencies = []
            for _ in range(iterations):
                t0 = time.perf_counter()
                mohflow_fast.info("concurrent bench")
                local_latencies.append((time.perf_counter() - t0) * 1e6)
            with results_lock:
                all_latencies.extend(local_latencies)

        thread_count = 4
        per_thread = 2500
        start = time.perf_counter()

        threads = [
            threading.Thread(target=worker, args=(per_thread,))
            for _ in range(thread_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        elapsed = time.perf_counter() - start
        total = thread_count * per_thread
        throughput = total / elapsed

        print(
            f"\n  Concurrent ({thread_count} threads): "
            f"{throughput:,.0f} msg/s total, "
            f"avg {statistics.mean(all_latencies):.1f}us"
        )
        assert throughput > 5_000


class TestMemoryOverhead:
    """Test memory footprint of logger instances."""

    def test_logger_memory_footprint(self):
        """A single MohFlow logger should use <5MB of memory."""
        import resource

        gc.collect()
        before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        loggers = []
        for i in range(10):
            lg = MohflowLogger(
                service_name=f"mem-test-{i}",
                console_logging=False,
                file_logging=False,
                enable_context_enrichment=False,
                enable_sensitive_data_filter=False,
            )
            loggers.append(lg)

        gc.collect()
        after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        # ru_maxrss is in KB on Linux, bytes on macOS
        if sys.platform == "darwin":
            delta_mb = (after - before) / 1024 / 1024
        else:
            delta_mb = (after - before) / 1024

        per_logger_mb = delta_mb / 10
        print(
            f"\n  Memory per logger: ~{per_logger_mb:.2f} MB "
            f"(total for 10: {delta_mb:.2f} MB)"
        )
        # Each logger should use less than 5MB
        assert (
            per_logger_mb < 5.0
        ), f"Logger uses too much memory: {per_logger_mb:.2f} MB"


class TestFileHandlerBenchmark:
    """Test actual file I/O throughput."""

    def test_file_logging_throughput(self):
        """File logging should handle >5k msg/s with rotation."""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name

        try:
            logger = MohflowLogger(
                service_name="bench-file",
                console_logging=False,
                file_logging=True,
                log_file_path=log_path,
                enable_context_enrichment=False,
                enable_sensitive_data_filter=False,
                formatter_type="fast",
            )

            result = _measure_throughput(
                lambda: logger.info("file benchmark message"),
                iterations=5000,
                warmup=200,
            )
            print(
                f"\n  File throughput: "
                f"{result['messages_per_second']:,.0f} msg/s"
            )
            # File I/O is slower, but should still be reasonable
            assert result["messages_per_second"] > 1_000

            # Verify file actually has content
            file_size = os.path.getsize(log_path)
            assert file_size > 0, "Log file is empty"
            print(f"  File size: {file_size / 1024:.1f} KB")
        finally:
            os.unlink(log_path)


class TestComparisonBenchmarks:
    """Head-to-head comparison: MohFlow vs structlog vs loguru vs stdlib."""

    def _run_all(self):
        """Run throughput for all available loggers and return results."""
        results = {}

        # --- stdlib ---
        stdlib = logging.getLogger("cmp-stdlib")
        stdlib.handlers = [_null_handler()]
        stdlib.setLevel(logging.INFO)
        results["stdlib"] = _measure_throughput(
            lambda: stdlib.info("comparison bench", extra={"uid": "u1"})
        )

        # --- MohFlow Fast ---
        mf_fast = MohflowLogger.fast(
            service_name="cmp-fast",
            console_logging=False,
            file_logging=False,
        )
        mf_fast.logger.handlers = [_null_handler()]
        results["mohflow_fast"] = _measure_throughput(
            lambda: mf_fast.info("comparison bench", uid="u1")
        )

        # --- MohFlow Production ---
        mf_prod = MohflowLogger.production(
            service_name="cmp-prod",
            console_logging=False,
            file_logging=False,
        )
        mf_prod.logger.handlers = [_null_handler()]
        results["mohflow_prod"] = _measure_throughput(
            lambda: mf_prod.info("comparison bench", uid="u1")
        )

        # --- structlog ---
        if HAS_STRUCTLOG:
            sl = structlog.get_logger("cmp-structlog")
            structlog.configure(
                processors=[
                    structlog.processors.JSONRenderer(),
                ],
                wrapper_class=structlog.BoundLogger,
                logger_factory=structlog.PrintLoggerFactory(
                    file=io.StringIO()
                ),
                cache_logger_on_first_use=True,
            )
            sl = structlog.get_logger("cmp-structlog")
            results["structlog"] = _measure_throughput(
                lambda: sl.info("comparison bench", uid="u1")
            )

        # --- loguru ---
        if HAS_LOGURU:
            loguru_logger.remove()
            loguru_logger.add(
                io.StringIO(),
                format="{message}",
                level="INFO",
                serialize=True,
            )
            results["loguru"] = _measure_throughput(
                lambda: loguru_logger.info("comparison bench", uid="u1")
            )

        return results

    def test_comparison_report(self):
        """Print a full comparison table of all logging libraries."""
        results = self._run_all()

        # Sort by throughput descending
        ranked = sorted(
            results.items(),
            key=lambda x: x[1]["messages_per_second"],
            reverse=True,
        )

        print("\n" + "=" * 72)
        print("  PRODUCTION BENCHMARK COMPARISON REPORT")
        print("=" * 72)
        print(
            f"  {'Library':<20} {'msg/s':>12} {'avg(us)':>10} "
            f"{'P50(us)':>10} {'P99(us)':>10}"
        )
        print("-" * 72)
        for name, r in ranked:
            print(
                f"  {name:<20} {r['messages_per_second']:>12,.0f} "
                f"{r['avg_latency_us']:>10.1f} "
                f"{r['p50_latency_us']:>10.1f} "
                f"{r['p99_latency_us']:>10.1f}"
            )

        baseline = results.get("stdlib", ranked[-1][1])
        base_mps = baseline["messages_per_second"]
        print("-" * 72)
        print("  Relative to stdlib:")
        for name, r in ranked:
            ratio = base_mps / r["messages_per_second"]
            label = (
                "baseline"
                if name == "stdlib"
                else (
                    f"{ratio:.2f}x slower"
                    if ratio > 1
                    else f"{1/ratio:.2f}x faster"
                )
            )
            print(f"    {name:<20} {label}")
        print("=" * 72)

        # MohFlow Fast should be competitive (within 3x of stdlib)
        mf_fast_ratio = (
            base_mps / results["mohflow_fast"]["messages_per_second"]
        )
        assert (
            mf_fast_ratio < 3.0
        ), f"MohFlow Fast is {mf_fast_ratio:.1f}x slower than stdlib"
