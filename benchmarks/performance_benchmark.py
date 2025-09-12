#!/usr/bin/env python3
"""
Performance benchmarking suite for MohFlow vs top Python logging libraries.

Benchmarks:
- Raw logging performance (messages/second)
- JSON serialization speed
- Memory usage patterns
- Async performance under load
- Handler throughput comparison

Libraries tested:
- MohFlow (various configurations)
- Loguru
- Structlog
- Standard logging with python-json-logger
- Picologging (if available)
"""

import asyncio
import gc
import json
import logging
import sys
import time
import threading
import statistics
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
import tempfile
import os

# Third-party benchmarking libraries
try:
    import loguru
    HAS_LOGURU = True
except ImportError:
    HAS_LOGURU = False

try:
    import structlog
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False

try:
    import picologging
    HAS_PICOLOGGING = True
except ImportError:
    HAS_PICOLOGGING = False

try:
    from pythonjsonlogger import jsonlogger
    HAS_PYTHONJSONLOGGER = True
except ImportError:
    HAS_PYTHONJSONLOGGER = False

# Import MohFlow components
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from mohflow.logger.base import MohflowLogger
from mohflow.formatters import OrjsonFormatter, FastJSONFormatter


@dataclass
class BenchmarkResult:
    """Results from a single benchmark test."""
    name: str
    messages_per_second: float
    memory_mb: float
    avg_latency_us: float
    p99_latency_us: float
    success_rate: float
    error_count: int
    metadata: Dict[str, Any]


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark tests."""
    message_count: int = 100_000
    thread_count: int = 4
    async_task_count: int = 1000
    message_size: str = "medium"  # "small", "medium", "large"
    include_context: bool = True
    warmup_messages: int = 10_000


class PerformanceBenchmark:
    """Comprehensive performance benchmarking suite."""
    
    def __init__(self, config: BenchmarkConfig = None):
        self.config = config or BenchmarkConfig()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="mohflow_benchmark_"))
        self.results: List[BenchmarkResult] = []
        
        # Test messages of different sizes
        self.messages = {
            "small": "Test message",
            "medium": f"Medium test message with some context: {{'user_id': 12345, 'action': 'login', 'ip': '192.168.1.1'}}",
            "large": f"Large message " + "x" * 500 + f" with extensive context: {json.dumps({'user_id': 12345, 'session_id': 'abc123', 'request_data': {'path': '/api/users', 'method': 'GET', 'headers': {'user-agent': 'Mozilla/5.0'}, 'query_params': {'page': 1, 'limit': 50}}, 'response_time': 123.45, 'status_code': 200})}"
        }
        
        self.context_data = {
            "request_id": "req_123456789",
            "user_id": "user_987654321", 
            "session_id": "sess_abcdefgh",
            "trace_id": "trace_xyz123",
            "span_id": "span_456789",
            "operation": "user_login",
            "service_version": "1.2.3",
            "environment": "benchmark"
        }
    
    @contextmanager
    def memory_profiler(self):
        """Context manager to track memory usage."""
        import psutil
        process = psutil.Process()
        
        gc.collect()  # Clean up before measurement
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        
        yield
        
        gc.collect()  # Clean up after test
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        self._last_memory_usage = memory_after - memory_before
    
    def _create_temp_log_file(self) -> Path:
        """Create a temporary log file for testing."""
        return self.temp_dir / f"benchmark_{int(time.time())}.log"
    
    def _benchmark_mohflow_fast(self) -> BenchmarkResult:
        """Benchmark MohFlow with fast configuration."""
        log_file = self._create_temp_log_file()
        
        logger = MohflowLogger.fast(
            service_name="benchmark",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True
        )
        
        return self._run_logging_benchmark(
            name="MohFlow Fast",
            log_func=lambda msg, ctx: logger.info(msg, **ctx),
            cleanup=lambda: log_file.unlink(missing_ok=True)
        )
    
    def _benchmark_mohflow_production(self) -> BenchmarkResult:
        """Benchmark MohFlow with production configuration."""
        log_file = self._create_temp_log_file()
        
        logger = MohflowLogger.production(
            service_name="benchmark",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True
        )
        
        return self._run_logging_benchmark(
            name="MohFlow Production",
            log_func=lambda msg, ctx: logger.info(msg, **ctx),
            cleanup=lambda: log_file.unlink(missing_ok=True)
        )
    
    def _benchmark_mohflow_async(self) -> BenchmarkResult:
        """Benchmark MohFlow with async handlers."""
        log_file = self._create_temp_log_file()
        
        logger = MohflowLogger(
            service_name="benchmark",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True,
            async_handlers=True,
            formatter_type="fast"
        )
        
        return self._run_async_logging_benchmark(
            name="MohFlow Async",
            log_func=lambda msg, ctx: logger.info(msg, **ctx),
            cleanup=lambda: log_file.unlink(missing_ok=True)
        )
    
    def _benchmark_loguru(self) -> Optional[BenchmarkResult]:
        """Benchmark Loguru."""
        if not HAS_LOGURU:
            return None
        
        log_file = self._create_temp_log_file()
        
        # Configure loguru
        loguru.logger.remove()  # Remove default handler
        loguru.logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            serialize=True,
            level="INFO"
        )
        
        return self._run_logging_benchmark(
            name="Loguru",
            log_func=lambda msg, ctx: loguru.logger.bind(**ctx).info(msg),
            cleanup=lambda: (loguru.logger.remove(), log_file.unlink(missing_ok=True))
        )
    
    def _benchmark_structlog(self) -> Optional[BenchmarkResult]:
        """Benchmark Structlog."""
        if not HAS_STRUCTLOG:
            return None
        
        log_file = self._create_temp_log_file()
        
        # Configure structlog
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        # Setup file handler
        handler = logging.FileHandler(str(log_file))
        handler.setFormatter(logging.Formatter("%(message)s"))
        
        stdlib_logger = logging.getLogger("structlog_benchmark")
        stdlib_logger.addHandler(handler)
        stdlib_logger.setLevel(logging.INFO)
        
        struct_logger = structlog.get_logger("structlog_benchmark")
        
        return self._run_logging_benchmark(
            name="Structlog",
            log_func=lambda msg, ctx: struct_logger.info(msg, **ctx),
            cleanup=lambda: log_file.unlink(missing_ok=True)
        )
    
    def _benchmark_standard_logging(self) -> BenchmarkResult:
        """Benchmark standard Python logging with JSON formatter."""
        log_file = self._create_temp_log_file()
        
        logger = logging.getLogger("standard_benchmark")
        logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        handler = logging.FileHandler(str(log_file))
        
        if HAS_PYTHONJSONLOGGER:
            formatter = jsonlogger.JsonFormatter(
                '%(asctime)s %(name)s %(levelname)s %(message)s'
            )
        else:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return self._run_logging_benchmark(
            name="Standard Logging (JSON)" if HAS_PYTHONJSONLOGGER else "Standard Logging",
            log_func=lambda msg, ctx: logger.info(msg, extra=ctx),
            cleanup=lambda: log_file.unlink(missing_ok=True)
        )
    
    def _benchmark_picologging(self) -> Optional[BenchmarkResult]:
        """Benchmark Picologging (faster standard logging)."""
        if not HAS_PICOLOGGING:
            return None
        
        log_file = self._create_temp_log_file()
        
        logger = picologging.getLogger("picologging_benchmark")
        logger.setLevel(picologging.INFO)
        
        handler = picologging.FileHandler(str(log_file))
        formatter = picologging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return self._run_logging_benchmark(
            name="Picologging",
            log_func=lambda msg, ctx: logger.info(msg, extra=ctx),
            cleanup=lambda: log_file.unlink(missing_ok=True)
        )
    
    def _run_logging_benchmark(
        self,
        name: str,
        log_func: Callable,
        cleanup: Callable = None
    ) -> BenchmarkResult:
        """Run a logging benchmark test."""
        message = self.messages[self.config.message_size]
        context = self.context_data if self.config.include_context else {}
        
        # Warmup
        for _ in range(min(1000, self.config.warmup_messages)):
            try:
                log_func(message, context)
            except Exception:
                pass
        
        latencies = []
        errors = 0
        
        with self.memory_profiler():
            start_time = time.perf_counter()
            
            for _ in range(self.config.message_count):
                latency_start = time.perf_counter()
                try:
                    log_func(message, context)
                    latency = (time.perf_counter() - latency_start) * 1_000_000  # microseconds
                    latencies.append(latency)
                except Exception:
                    errors += 1
            
            end_time = time.perf_counter()
        
        # Cleanup
        if cleanup:
            try:
                cleanup()
            except Exception:
                pass
        
        duration = end_time - start_time
        messages_per_second = self.config.message_count / duration
        success_rate = (self.config.message_count - errors) / self.config.message_count
        
        return BenchmarkResult(
            name=name,
            messages_per_second=messages_per_second,
            memory_mb=self._last_memory_usage,
            avg_latency_us=statistics.mean(latencies) if latencies else 0,
            p99_latency_us=statistics.quantiles(latencies, n=100)[98] if latencies else 0,
            success_rate=success_rate,
            error_count=errors,
            metadata={
                "message_count": self.config.message_count,
                "duration_seconds": duration,
                "message_size": self.config.message_size,
                "include_context": self.config.include_context
            }
        )
    
    def _run_async_logging_benchmark(
        self,
        name: str,
        log_func: Callable,
        cleanup: Callable = None
    ) -> BenchmarkResult:
        """Run an async logging benchmark test."""
        
        async def async_log_worker(task_count: int) -> List[float]:
            """Async worker for logging messages."""
            message = self.messages[self.config.message_size]
            context = self.context_data if self.config.include_context else {}
            
            latencies = []
            
            for _ in range(task_count):
                latency_start = time.perf_counter()
                try:
                    log_func(message, context)
                    latency = (time.perf_counter() - latency_start) * 1_000_000
                    latencies.append(latency)
                except Exception:
                    pass
                
                # Yield control to event loop
                if _ % 100 == 0:
                    await asyncio.sleep(0)
            
            return latencies
        
        async def run_benchmark():
            """Run the async benchmark."""
            tasks_per_worker = self.config.message_count // self.config.async_task_count
            
            with self.memory_profiler():
                start_time = time.perf_counter()
                
                tasks = [
                    async_log_worker(tasks_per_worker) 
                    for _ in range(self.config.async_task_count)
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                end_time = time.perf_counter()
            
            # Process results
            all_latencies = []
            errors = 0
            
            for result in results:
                if isinstance(result, Exception):
                    errors += tasks_per_worker
                else:
                    all_latencies.extend(result)
            
            return end_time - start_time, all_latencies, errors
        
        # Run the async benchmark
        duration, latencies, errors = asyncio.run(run_benchmark())
        
        # Cleanup
        if cleanup:
            try:
                cleanup()
            except Exception:
                pass
        
        messages_per_second = self.config.message_count / duration
        success_rate = (self.config.message_count - errors) / self.config.message_count
        
        return BenchmarkResult(
            name=name,
            messages_per_second=messages_per_second,
            memory_mb=self._last_memory_usage,
            avg_latency_us=statistics.mean(latencies) if latencies else 0,
            p99_latency_us=statistics.quantiles(latencies, n=100)[98] if latencies else 0,
            success_rate=success_rate,
            error_count=errors,
            metadata={
                "message_count": self.config.message_count,
                "duration_seconds": duration,
                "async_task_count": self.config.async_task_count,
                "message_size": self.config.message_size,
                "include_context": self.config.include_context
            }
        )
    
    def _run_threading_benchmark(self, name: str, log_func: Callable) -> BenchmarkResult:
        """Run a multi-threaded logging benchmark."""
        message = self.messages[self.config.message_size]
        context = self.context_data if self.config.include_context else {}
        
        def thread_worker(messages_per_thread: int) -> tuple:
            """Worker function for threading benchmark."""
            latencies = []
            errors = 0
            
            for _ in range(messages_per_thread):
                latency_start = time.perf_counter()
                try:
                    log_func(message, context)
                    latency = (time.perf_counter() - latency_start) * 1_000_000
                    latencies.append(latency)
                except Exception:
                    errors += 1
            
            return latencies, errors
        
        messages_per_thread = self.config.message_count // self.config.thread_count
        
        with self.memory_profiler():
            start_time = time.perf_counter()
            
            with ThreadPoolExecutor(max_workers=self.config.thread_count) as executor:
                futures = [
                    executor.submit(thread_worker, messages_per_thread)
                    for _ in range(self.config.thread_count)
                ]
                
                results = [future.result() for future in futures]
            
            end_time = time.perf_counter()
        
        # Aggregate results
        all_latencies = []
        total_errors = 0
        
        for latencies, errors in results:
            all_latencies.extend(latencies)
            total_errors += errors
        
        duration = end_time - start_time
        messages_per_second = self.config.message_count / duration
        success_rate = (self.config.message_count - total_errors) / self.config.message_count
        
        return BenchmarkResult(
            name=f"{name} (Threaded)",
            messages_per_second=messages_per_second,
            memory_mb=self._last_memory_usage,
            avg_latency_us=statistics.mean(all_latencies) if all_latencies else 0,
            p99_latency_us=statistics.quantiles(all_latencies, n=100)[98] if all_latencies else 0,
            success_rate=success_rate,
            error_count=total_errors,
            metadata={
                "message_count": self.config.message_count,
                "duration_seconds": duration,
                "thread_count": self.config.thread_count,
                "message_size": self.config.message_size,
                "include_context": self.config.include_context
            }
        )
    
    def run_all_benchmarks(self) -> List[BenchmarkResult]:
        """Run all available benchmarks."""
        benchmarks = [
            ("MohFlow Fast", self._benchmark_mohflow_fast),
            ("MohFlow Production", self._benchmark_mohflow_production),
            ("MohFlow Async", self._benchmark_mohflow_async),
            ("Standard Logging", self._benchmark_standard_logging),
        ]
        
        # Add optional benchmarks based on available libraries
        if HAS_LOGURU:
            benchmarks.append(("Loguru", self._benchmark_loguru))
        
        if HAS_STRUCTLOG:
            benchmarks.append(("Structlog", self._benchmark_structlog))
        
        if HAS_PICOLOGGING:
            benchmarks.append(("Picologging", self._benchmark_picologging))
        
        results = []
        
        print("Running Performance Benchmarks...")
        print(f"Configuration: {self.config.message_count:,} messages, {self.config.message_size} size")
        print("=" * 70)
        
        for name, benchmark_func in benchmarks:
            print(f"Running {name}...", end=" ", flush=True)
            try:
                result = benchmark_func()
                if result:
                    results.append(result)
                    print(f"✓ {result.messages_per_second:,.0f} msg/sec")
                else:
                    print("⚠ Skipped (library not available)")
            except Exception as e:
                print(f"✗ Error: {e}")
        
        self.results = results
        return results
    
    def print_results(self):
        """Print benchmark results in a formatted table."""
        if not self.results:
            print("No benchmark results available.")
            return
        
        print("\n" + "=" * 100)
        print("PERFORMANCE BENCHMARK RESULTS")
        print("=" * 100)
        
        # Sort by messages per second
        sorted_results = sorted(self.results, key=lambda r: r.messages_per_second, reverse=True)
        
        # Print header
        print(f"{'Library':<20} {'Msg/Sec':<12} {'Memory (MB)':<12} {'Avg Lat (μs)':<12} {'P99 Lat (μs)':<12} {'Success %':<10}")
        print("-" * 100)
        
        # Print results
        for result in sorted_results:
            print(f"{result.name:<20} {result.messages_per_second:>11,.0f} "
                  f"{result.memory_mb:>11.1f} {result.avg_latency_us:>11.1f} "
                  f"{result.p99_latency_us:>11.1f} {result.success_rate*100:>9.1f}")
        
        # Performance analysis
        print("\n" + "=" * 60)
        print("PERFORMANCE ANALYSIS")
        print("=" * 60)
        
        fastest = sorted_results[0]
        print(f"🏆 Fastest: {fastest.name} ({fastest.messages_per_second:,.0f} msg/sec)")
        
        mohflow_results = [r for r in sorted_results if "MohFlow" in r.name]
        if mohflow_results:
            best_mohflow = mohflow_results[0]
            if best_mohflow != fastest:
                performance_gap = fastest.messages_per_second / best_mohflow.messages_per_second
                print(f"📊 MohFlow Performance: {performance_gap:.2f}x slower than fastest")
            else:
                print("🎯 MohFlow is the fastest logger!")
        
        # Memory efficiency
        most_efficient = min(sorted_results, key=lambda r: r.memory_mb)
        print(f"💾 Most Memory Efficient: {most_efficient.name} ({most_efficient.memory_mb:.1f} MB)")
        
        # Latency analysis
        lowest_latency = min(sorted_results, key=lambda r: r.avg_latency_us)
        print(f"⚡ Lowest Latency: {lowest_latency.name} ({lowest_latency.avg_latency_us:.1f} μs avg)")
    
    def save_results(self, filename: str = None):
        """Save benchmark results to JSON file."""
        if not filename:
            timestamp = int(time.time())
            filename = f"mohflow_benchmark_{timestamp}.json"
        
        data = {
            "timestamp": time.time(),
            "config": {
                "message_count": self.config.message_count,
                "thread_count": self.config.thread_count,
                "async_task_count": self.config.async_task_count,
                "message_size": self.config.message_size,
                "include_context": self.config.include_context,
                "warmup_messages": self.config.warmup_messages
            },
            "system_info": {
                "python_version": sys.version,
                "platform": sys.platform
            },
            "results": [
                {
                    "name": r.name,
                    "messages_per_second": r.messages_per_second,
                    "memory_mb": r.memory_mb,
                    "avg_latency_us": r.avg_latency_us,
                    "p99_latency_us": r.p99_latency_us,
                    "success_rate": r.success_rate,
                    "error_count": r.error_count,
                    "metadata": r.metadata
                }
                for r in self.results
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n📁 Results saved to: {filename}")
    
    def cleanup(self):
        """Clean up temporary files."""
        try:
            import shutil
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass


def main():
    """Run the performance benchmark suite."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MohFlow Performance Benchmark Suite")
    parser.add_argument("--messages", type=int, default=100_000, help="Number of messages to log")
    parser.add_argument("--threads", type=int, default=4, help="Number of threads for threading tests")
    parser.add_argument("--async-tasks", type=int, default=1000, help="Number of async tasks")
    parser.add_argument("--message-size", choices=["small", "medium", "large"], 
                       default="medium", help="Size of log messages")
    parser.add_argument("--no-context", action="store_true", help="Disable context data")
    parser.add_argument("--save", type=str, help="Save results to file")
    parser.add_argument("--warmup", type=int, default=10_000, help="Warmup message count")
    
    args = parser.parse_args()
    
    config = BenchmarkConfig(
        message_count=args.messages,
        thread_count=args.threads,
        async_task_count=args.async_tasks,
        message_size=args.message_size,
        include_context=not args.no_context,
        warmup_messages=args.warmup
    )
    
    benchmark = PerformanceBenchmark(config)
    
    try:
        benchmark.run_all_benchmarks()
        benchmark.print_results()
        
        if args.save:
            benchmark.save_results(args.save)
        
    finally:
        benchmark.cleanup()


if __name__ == "__main__":
    main()