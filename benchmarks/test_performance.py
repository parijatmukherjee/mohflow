"""
Integration tests for MohFlow performance features.
"""

import asyncio
import tempfile
import time
import threading
from pathlib import Path
import sys
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mohflow.logger.base import MohflowLogger
from mohflow.formatters import OrjsonFormatter, FastJSONFormatter, StructuredFormatter


def test_basic_logging_performance():
    """Test basic logging performance without external dependencies."""
    
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "test.log"
        
        # Test MohFlow fast configuration
        logger = MohflowLogger.fast(
            service_name="test",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True
        )
        
        # Measure logging performance
        message_count = 10_000
        start_time = time.perf_counter()
        
        for i in range(message_count):
            logger.info(f"Test message {i}", user_id=i, action="test")
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        
        messages_per_second = message_count / duration
        
        print(f"✓ Basic Performance: {messages_per_second:,.0f} messages/second")
        
        # Verify log file was created and contains data
        assert log_file.exists(), "Log file should exist"
        assert log_file.stat().st_size > 0, "Log file should contain data"
        
        # Verify JSON format
        with open(log_file) as f:
            first_line = f.readline().strip()
            log_data = json.loads(first_line)
            assert "message" in log_data
            assert "user_id" in log_data
            assert log_data["level"] == "INFO"
        
        return messages_per_second


def test_formatter_performance():
    """Test different formatter performance."""
    
    with tempfile.TemporaryDirectory() as temp_dir:
        results = {}
        
        formatters = {
            "fast": ("fast", FastJSONFormatter),
            "structured": ("structured", StructuredFormatter), 
            "orjson": ("production", OrjsonFormatter)
        }
        
        for name, (formatter_type, formatter_class) in formatters.items():
            log_file = Path(temp_dir) / f"test_{name}.log"
            
            logger = MohflowLogger(
                service_name="test",
                formatter_type=formatter_type,
                log_file_path=str(log_file),
                console_logging=False,
                file_logging=True
            )
            
            # Measure performance
            message_count = 5_000
            start_time = time.perf_counter()
            
            for i in range(message_count):
                logger.info(f"Test message {i}", 
                           user_id=i, 
                           action="test",
                           metadata={"key": "value", "number": i})
            
            end_time = time.perf_counter()
            duration = end_time - start_time
            
            messages_per_second = message_count / duration
            results[name] = messages_per_second
            
            print(f"✓ {name.title()} Formatter: {messages_per_second:,.0f} msg/sec")
        
        # Verify FastJSONFormatter is faster than StructuredFormatter
        assert results["fast"] >= results["structured"], \
            "FastJSONFormatter should be at least as fast as StructuredFormatter"
        
        return results


def test_async_handler_performance():
    """Test async handler performance."""
    
    async def async_logging_test():
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "async_test.log"
            
            # Create async logger
            logger = MohflowLogger(
                service_name="async_test",
                formatter_type="fast",
                async_handlers=True,
                log_file_path=str(log_file),
                console_logging=False,
                file_logging=True
            )
            
            # Test concurrent logging
            message_count = 5_000
            start_time = time.perf_counter()
            
            # Create multiple concurrent logging tasks
            async def log_worker(worker_id, messages):
                for i in range(messages):
                    logger.info(f"Async message {i} from worker {worker_id}",
                               worker_id=worker_id, message_id=i)
                    
                    # Yield control occasionally
                    if i % 100 == 0:
                        await asyncio.sleep(0)
            
            # Run multiple workers concurrently
            workers = 10
            messages_per_worker = message_count // workers
            
            tasks = [
                log_worker(i, messages_per_worker) 
                for i in range(workers)
            ]
            
            await asyncio.gather(*tasks)
            
            end_time = time.perf_counter()
            duration = end_time - start_time
            
            messages_per_second = message_count / duration
            
            print(f"✓ Async Handler: {messages_per_second:,.0f} msg/sec")
            
            # Give async handlers time to flush
            await asyncio.sleep(0.1)
            
            return messages_per_second
    
    return asyncio.run(async_logging_test())


def test_threaded_performance():
    """Test performance under threading conditions."""
    
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "threaded_test.log"
        
        logger = MohflowLogger.fast(
            service_name="threaded_test",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True
        )
        
        message_count = 10_000
        thread_count = 4
        messages_per_thread = message_count // thread_count
        
        results = []
        
        def thread_worker(worker_id):
            start_time = time.perf_counter()
            
            for i in range(messages_per_thread):
                logger.info(f"Thread message {i} from worker {worker_id}",
                           worker_id=worker_id, message_id=i, thread_name=threading.current_thread().name)
            
            end_time = time.perf_counter()
            duration = end_time - start_time
            thread_mps = messages_per_thread / duration
            results.append(thread_mps)
        
        # Start all threads
        start_time = time.perf_counter()
        threads = []
        
        for i in range(thread_count):
            thread = threading.Thread(target=thread_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        end_time = time.perf_counter()
        total_duration = end_time - start_time
        
        total_messages_per_second = message_count / total_duration
        avg_thread_performance = sum(results) / len(results)
        
        print(f"✓ Threaded Performance: {total_messages_per_second:,.0f} msg/sec total")
        print(f"  Average per thread: {avg_thread_performance:,.0f} msg/sec")
        
        return total_messages_per_second


def test_memory_efficiency():
    """Test memory usage of different configurations."""
    
    try:
        import psutil
        import gc
    except ImportError:
        print("⚠ Skipping memory test (psutil not available)")
        return {}
    
    process = psutil.Process()
    
    def measure_memory(logger_factory, name):
        gc.collect()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / f"memory_test_{name}.log"
            logger = logger_factory(log_file)
            
            # Log messages to measure memory growth
            for i in range(5_000):
                logger.info(f"Memory test message {i}",
                           user_id=i, data={"key": "value", "list": [1, 2, 3]})
        
        gc.collect()
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_used = memory_after - memory_before
        
        print(f"✓ Memory usage {name}: {memory_used:.1f} MB")
        return memory_used
    
    results = {}
    
    # Test different configurations
    configs = {
        "fast": lambda log_file: MohflowLogger.fast(
            service_name="memory_test", log_file_path=str(log_file),
            console_logging=False, file_logging=True
        ),
        "production": lambda log_file: MohflowLogger.production(
            service_name="memory_test", log_file_path=str(log_file),
            console_logging=False, file_logging=True
        ),
        "async": lambda log_file: MohflowLogger(
            service_name="memory_test", log_file_path=str(log_file),
            console_logging=False, file_logging=True, async_handlers=True,
            formatter_type="fast"
        )
    }
    
    for name, factory in configs.items():
        try:
            memory_usage = measure_memory(factory, name)
            results[name] = memory_usage
        except Exception as e:
            print(f"✗ Memory test failed for {name}: {e}")
    
    return results


def run_performance_tests():
    """Run all performance tests."""
    
    print("🚀 Running MohFlow Performance Tests")
    print("=" * 50)
    
    results = {}
    
    try:
        results['basic'] = test_basic_logging_performance()
    except Exception as e:
        print(f"✗ Basic performance test failed: {e}")
    
    try:
        results['formatters'] = test_formatter_performance()
    except Exception as e:
        print(f"✗ Formatter performance test failed: {e}")
    
    try:
        results['async'] = test_async_handler_performance()
    except Exception as e:
        print(f"✗ Async performance test failed: {e}")
    
    try:
        results['threaded'] = test_threaded_performance()
    except Exception as e:
        print(f"✗ Threaded performance test failed: {e}")
    
    try:
        results['memory'] = test_memory_efficiency()
    except Exception as e:
        print(f"✗ Memory efficiency test failed: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Performance Tests Complete")
    
    return results


if __name__ == "__main__":
    results = run_performance_tests()
    
    # Print summary
    print("\n📊 PERFORMANCE SUMMARY")
    print("=" * 30)
    
    if 'basic' in results:
        print(f"Basic Performance: {results['basic']:,.0f} msg/sec")
    
    if 'async' in results:
        print(f"Async Performance: {results['async']:,.0f} msg/sec")
    
    if 'threaded' in results:
        print(f"Threaded Performance: {results['threaded']:,.0f} msg/sec")
    
    if 'formatters' in results and isinstance(results['formatters'], dict):
        fastest_formatter = max(results['formatters'].items(), key=lambda x: x[1])
        print(f"Fastest Formatter: {fastest_formatter[0]} ({fastest_formatter[1]:,.0f} msg/sec)")
    
    if 'memory' in results and isinstance(results['memory'], dict) and results['memory']:
        most_efficient = min(results['memory'].items(), key=lambda x: x[1])
        print(f"Most Memory Efficient: {most_efficient[0]} ({most_efficient[1]:.1f} MB)")