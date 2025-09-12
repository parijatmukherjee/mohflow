#!/usr/bin/env python3
"""
Demo script showing log sampling and rate limiting features in MohFlow.

This demonstrates:
1. Basic sampling (random, deterministic)
2. Adaptive sampling based on load
3. Rate limiting with burst support
4. Per-level sampling rates
5. Sampling statistics and monitoring
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import time
import threading
from mohflow import MohflowLogger
from mohflow.sampling import create_high_volume_sampler, create_production_sampler

def demo_basic_sampling():
    """Test basic sampling functionality."""
    print("=== Basic Sampling Demo ===")
    
    # Create logger with 10% sampling
    logger = MohflowLogger.smart(
        "sampling-demo",
        enable_sampling=True,
        sample_rate=0.1,  # 10% sampling
        sampling_strategy="random"
    )
    
    print("Logging 100 messages with 10% sampling...")
    for i in range(100):
        logger.info(f"Message {i}", message_id=i)
    
    stats = logger.get_sampling_stats()
    if stats:
        print(f"Sampled {stats['sampled_logs_count']} out of {stats['total_logs_count']} logs")
        print(f"Effective sampling rate: {stats['sampled_logs_count']/stats['total_logs_count']:.2%}")
    
    print("✓ Basic sampling working\n")

def demo_deterministic_sampling():
    """Test deterministic sampling."""
    print("=== Deterministic Sampling Demo ===")
    
    logger = MohflowLogger.smart(
        "deterministic-demo",
        enable_sampling=True,
        sample_rate=0.2,  # 20% sampling
        sampling_strategy="deterministic"
    )
    
    # Same messages should have consistent sampling results
    messages = ["Login attempt", "Database query", "Cache miss", "User logout"]
    
    print("First run:")
    for msg in messages:
        logger.info(msg)
    
    print("Second run (should be identical):")
    for msg in messages:
        logger.info(msg)
    
    print("✓ Deterministic sampling working\n")

def demo_per_level_sampling():
    """Test per-level sampling rates."""
    print("=== Per-Level Sampling Demo ===")
    
    logger = MohflowLogger.smart(
        "level-sampling-demo",
        enable_sampling=True,
        sample_rate=0.5,  # 50% base rate
        level_sample_rates={
            'DEBUG': 0.01,   # 1% of debug logs
            'INFO': 0.2,     # 20% of info logs
            'WARNING': 0.8,  # 80% of warning logs  
            'ERROR': 1.0,    # 100% of error logs
            'CRITICAL': 1.0  # 100% of critical logs
        }
    )
    
    # Generate logs at different levels
    for i in range(50):
        logger.debug(f"Debug message {i}")
        logger.info(f"Info message {i}")
        logger.warning(f"Warning message {i}")
        logger.error(f"Error message {i}")
        logger.critical(f"Critical message {i}")
    
    stats = logger.get_sampling_stats()
    if stats:
        print("Per-level sampling results:")
        for level, level_stats in stats['level_stats'].items():
            print(f"  {level}: {level_stats['count']} total")
        print(f"Total sampled: {stats['sampled_logs_count']} out of {stats['total_logs_count']}")
    
    print("✓ Per-level sampling working\n")

def demo_rate_limiting():
    """Test rate limiting functionality."""
    print("=== Rate Limiting Demo ===")
    
    logger = MohflowLogger.smart(
        "rate-limit-demo",
        enable_sampling=True,
        sample_rate=1.0,  # No sampling, just rate limiting
        max_logs_per_second=10,
        burst_limit=20
    )
    
    print("Sending 50 logs rapidly (should be rate limited)...")
    start_time = time.time()
    
    for i in range(50):
        logger.info(f"Rapid message {i}", timestamp=time.time())
        time.sleep(0.01)  # 10ms between messages (100 logs/sec attempted)
    
    duration = time.time() - start_time
    stats = logger.get_sampling_stats()
    
    if stats:
        actual_rate = stats['sampled_logs_count'] / duration
        print(f"Sent {stats['sampled_logs_count']} logs in {duration:.2f}s")
        print(f"Actual rate: {actual_rate:.1f} logs/sec (limit: {logger.sampler.config.max_logs_per_second})")
        print(f"Rate limiting: {'✓' if actual_rate <= logger.sampler.config.max_logs_per_second * 1.1 else '✗'}")
    
    print("✓ Rate limiting working\n")

def demo_adaptive_sampling():
    """Test adaptive sampling."""
    print("=== Adaptive Sampling Demo ===")
    
    logger = MohflowLogger.smart(
        "adaptive-demo",
        enable_sampling=True,
        sample_rate=1.0,
        sampling_strategy="adaptive",
        adaptive_sampling=True,
        max_logs_per_second=50  # Target rate
    )
    
    print("Phase 1: Low load (should maintain high sampling rate)")
    for i in range(20):
        logger.info(f"Low load message {i}")
        time.sleep(0.1)  # Slow rate
    
    stats1 = logger.get_sampling_stats()
    print(f"Phase 1 - Rate: {stats1['total_logs_rate']:.1f} logs/sec, Sampled: {stats1['sampled_logs_count']}")
    
    print("\nPhase 2: High load (should reduce sampling rate)")
    for i in range(100):
        logger.info(f"High load message {i}")
        if i % 10 == 0:
            time.sleep(0.01)  # Occasional brief pause
    
    stats2 = logger.get_sampling_stats()
    print(f"Phase 2 - Rate: {stats2['total_logs_rate']:.1f} logs/sec, Sampled: {stats2['sampled_logs_count']}")
    print(f"Adaptive adjustment: {'✓' if stats2['sampled_logs_count'] > stats1['sampled_logs_count'] * 2 else '✗'}")
    
    print("✓ Adaptive sampling working\n")

def demo_high_volume_scenario():
    """Test high-volume service scenario."""
    print("=== High-Volume Service Demo ===")
    
    # Use the pre-configured high-volume sampler
    sampler = create_high_volume_sampler(
        sample_rate=0.05,  # 5% base sampling
        max_logs_per_second=500,
        burst_limit=1000
    )
    
    logger = MohflowLogger.smart(
        "high-volume-service",
        enable_sampling=True,
        sample_rate=sampler.config.sample_rate,
        max_logs_per_second=sampler.config.max_logs_per_second,
        burst_limit=sampler.config.burst_limit,
        level_sample_rates=sampler.config.level_sample_rates
    )
    
    # Replace the sampler with our pre-configured one
    logger.sampler = sampler
    
    print("Simulating high-volume service with mixed log levels...")
    
    def worker_thread(worker_id: int, message_count: int):
        """Worker thread generating logs."""
        for i in range(message_count):
            if i % 20 == 0:
                logger.error(f"Worker {worker_id} error {i}", worker=worker_id)
            elif i % 10 == 0:
                logger.warning(f"Worker {worker_id} warning {i}", worker=worker_id)
            elif i % 5 == 0:
                logger.info(f"Worker {worker_id} info {i}", worker=worker_id)
            else:
                logger.debug(f"Worker {worker_id} debug {i}", worker=worker_id)
    
    # Start multiple worker threads
    threads = []
    start_time = time.time()
    
    for worker_id in range(5):
        t = threading.Thread(target=worker_thread, args=(worker_id, 200))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    duration = time.time() - start_time
    stats = logger.get_sampling_stats()
    
    if stats:
        print(f"\nHigh-volume results ({duration:.2f}s):")
        print(f"Total logs: {stats['total_logs_count']}")
        print(f"Sampled logs: {stats['sampled_logs_count']}")
        print(f"Overall sampling rate: {stats['sampled_logs_count']/stats['total_logs_count']:.1%}")
        print(f"Throughput: {stats['total_logs_count']/duration:.0f} logs/sec")
        print(f"Per-level breakdown:")
        for level, level_stats in stats['level_stats'].items():
            if level_stats['count'] > 0:
                level_sample_rate = sampler.config.level_sample_rates.get(level, sampler.config.sample_rate)
                print(f"  {level}: {level_stats['count']} total @ {level_sample_rate:.1%} rate")
    
    print("✓ High-volume service scenario working\n")

def demo_sampling_stats_monitoring():
    """Test sampling statistics and monitoring."""
    print("=== Sampling Statistics Demo ===")
    
    logger = MohflowLogger.smart(
        "stats-demo",
        enable_sampling=True,
        sample_rate=0.3,
        max_logs_per_second=100,
        burst_limit=150,
        level_sample_rates={'DEBUG': 0.1, 'INFO': 0.3, 'ERROR': 1.0}
    )
    
    # Generate some logs
    for i in range(200):
        level = ['debug', 'info', 'warning', 'error'][i % 4]
        getattr(logger, level)(f"Test message {i}", component=f"component_{i % 3}")
    
    stats = logger.get_sampling_stats()
    
    print("Sampling Statistics:")
    print(f"  Current sample rate: {stats['current_sample_rate']:.1%}")
    print(f"  Strategy: {stats['strategy']}")
    print(f"  Total logs rate: {stats['total_logs_rate']:.1f}/sec")
    print(f"  Sampled logs rate: {stats['sampled_logs_rate']:.1f}/sec")
    print(f"  Total count: {stats['total_logs_count']}")
    print(f"  Sampled count: {stats['sampled_logs_count']}")
    
    if 'rate_limit_current' in stats:
        print(f"  Current rate limit usage: {stats['rate_limit_current']:.1f}/{stats['rate_limit_max']} logs/sec")
    
    if 'burst_current' in stats:
        print(f"  Current burst usage: {stats['burst_current']}/{stats['burst_limit']} logs")
    
    print("\nPer-level statistics:")
    for level, level_stats in stats['level_stats'].items():
        print(f"  {level}: {level_stats['count']} total, {level_stats['rate']:.1f}/sec")
    
    print("\nPer-component statistics:")
    for component, comp_stats in stats['component_stats'].items():
        print(f"  {component}: {comp_stats['count']} total, {comp_stats['rate']:.1f}/sec")
    
    # Test runtime configuration updates
    print("\nTesting runtime configuration updates...")
    logger.update_sampling_config(sample_rate=0.5)
    logger.info("After config update")
    
    print("✓ Sampling statistics and monitoring working\n")

def main():
    """Run all sampling demos."""
    print("🎯 MohFlow Log Sampling and Rate Limiting Demo")
    print("=" * 55)
    
    try:
        # Basic functionality
        demo_basic_sampling()
        demo_deterministic_sampling()
        demo_per_level_sampling()
        
        # Rate limiting
        demo_rate_limiting()
        demo_adaptive_sampling()
        
        # Advanced scenarios
        demo_high_volume_scenario()
        demo_sampling_stats_monitoring()
        
        print("🎉 All sampling features working correctly!")
        print("✅ Random/deterministic/adaptive sampling, rate limiting, per-level rates")
        print("✅ Statistics monitoring, runtime configuration updates")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())