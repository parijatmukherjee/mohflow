#!/usr/bin/env python3
"""
Quick benchmark runner for MohFlow performance testing.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from performance_benchmark import PerformanceBenchmark, BenchmarkConfig


def quick_benchmark():
    """Run a quick performance benchmark with reasonable defaults."""
    
    config = BenchmarkConfig(
        message_count=50_000,  # Smaller for quick testing
        thread_count=2,
        async_task_count=500,
        message_size="medium",
        include_context=True,
        warmup_messages=5_000
    )
    
    print("🚀 Running Quick MohFlow Performance Benchmark")
    print(f"📊 Testing {config.message_count:,} messages with {config.message_size} size")
    
    benchmark = PerformanceBenchmark(config)
    
    try:
        results = benchmark.run_all_benchmarks()
        benchmark.print_results()
        
        # Save results with timestamp
        import time
        filename = f"benchmark_results_{int(time.time())}.json"
        benchmark.save_results(filename)
        
        return results
        
    finally:
        benchmark.cleanup()


def comprehensive_benchmark():
    """Run comprehensive benchmark with full testing."""
    
    config = BenchmarkConfig(
        message_count=500_000,  # Large scale testing
        thread_count=8,
        async_task_count=2000,
        message_size="medium",
        include_context=True,
        warmup_messages=50_000
    )
    
    print("🎯 Running Comprehensive MohFlow Performance Benchmark")
    print(f"📊 Testing {config.message_count:,} messages - this may take a few minutes...")
    
    benchmark = PerformanceBenchmark(config)
    
    try:
        results = benchmark.run_all_benchmarks()
        benchmark.print_results()
        
        # Save results with timestamp
        import time
        filename = f"comprehensive_benchmark_{int(time.time())}.json"
        benchmark.save_results(filename)
        
        return results
        
    finally:
        benchmark.cleanup()


def compare_message_sizes():
    """Compare performance across different message sizes."""
    
    print("📏 Comparing Performance Across Message Sizes")
    print("=" * 60)
    
    all_results = []
    
    for size in ["small", "medium", "large"]:
        print(f"\n🔍 Testing {size} messages...")
        
        config = BenchmarkConfig(
            message_count=25_000,
            message_size=size,
            include_context=True,
            warmup_messages=2_500
        )
        
        benchmark = PerformanceBenchmark(config)
        
        try:
            results = benchmark.run_all_benchmarks()
            all_results.extend(results)
            
            # Print size-specific results
            print(f"\n{size.title()} Message Results:")
            for result in results:
                if "MohFlow" in result.name:
                    print(f"  {result.name}: {result.messages_per_second:,.0f} msg/sec")
        
        finally:
            benchmark.cleanup()
    
    print(f"\n📊 Tested {len(all_results)} configurations across all message sizes")
    return all_results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MohFlow Benchmark Runner")
    parser.add_argument("--type", choices=["quick", "comprehensive", "sizes"], 
                       default="quick", help="Type of benchmark to run")
    
    args = parser.parse_args()
    
    if args.type == "quick":
        quick_benchmark()
    elif args.type == "comprehensive":
        comprehensive_benchmark()
    elif args.type == "sizes":
        compare_message_sizes()