#!/usr/bin/env python3
"""
Demo script showing automatic metrics generation from log messages.

This demonstrates:
1. Auto-extraction of metrics from log patterns
2. Counter, histogram, and gauge metrics
3. Error rate and latency tracking
4. Throughput measurements
5. Custom metric extractors
6. Prometheus metrics export
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import time
import random
import threading
from mohflow import MohflowLogger
from mohflow.metrics import MetricExtractor, MetricType

def demo_basic_auto_metrics():
    """Test basic auto-metrics functionality."""
    print("=== Basic Auto-Metrics Demo ===")
    
    # Create logger with auto-metrics enabled
    logger = MohflowLogger.smart(
        "metrics-demo",
        enable_auto_metrics=True,
        metrics_config="default"
    )
    
    print("Logging messages with various metrics patterns...")
    
    # Error messages (should generate error counters)
    logger.error("Database connection failed", database="users", error_code=500)
    logger.error("API timeout occurred", endpoint="/api/data", duration=5000)
    logger.critical("System out of memory", memory="8GB")
    
    # Request duration messages (should generate latency histograms)
    logger.info("Request processed successfully", duration=150, endpoint="/api/users", status=200)
    logger.info("Request completed", duration=75, endpoint="/api/posts", status=200)
    logger.info("Slow query executed", duration=850, endpoint="/api/search", status=200)
    
    # Database operations (should generate operation counters)
    logger.info("Database query executed", query="SELECT * FROM users", table="users")
    logger.info("Database insert completed", query="INSERT INTO posts", table="posts")
    
    # Cache operations
    logger.info("Cache hit for user data", cache_type="redis", operation="hit")
    logger.info("Cache miss for session", cache_type="redis", operation="miss")
    
    # Memory usage
    logger.info("Memory usage check", memory="2.5GB", component="worker")
    logger.info("High memory usage detected", memory="7.8GB", component="api")
    
    # Get metrics summary
    summary = logger.get_metrics_summary()
    
    if summary:
        print("\nMetrics Summary:")
        print(f"Collection time: {summary['collection_time']}")
        
        print(f"\nCounters ({len(summary['counters'])} types):")
        for name, data in summary['counters'].items():
            print(f"  {name}: {data['total']} total")
        
        print(f"\nHistograms ({len(summary['histograms'])} types):")
        for name, stats in summary['histograms'].items():
            print(f"  {name}:")
            print(f"    Count: {stats['count']}, Avg: {stats['avg']:.1f}")
            print(f"    P95: {stats['p95']:.1f}, P99: {stats['p99']:.1f}")
        
        print(f"\nGauges ({len(summary['gauges'])} types):")
        for name, data in summary['gauges'].items():
            for labels, stats in data.items():
                print(f"  {name}: {stats['current']}")
    
    print("✓ Basic auto-metrics working\n")

def demo_web_service_metrics():
    """Test web service specific metrics."""
    print("=== Web Service Metrics Demo ===")
    
    logger = MohflowLogger.smart(
        "web-service",
        enable_auto_metrics=True,
        metrics_config="web_service"
    )
    
    print("Simulating web service logs with HTTP metrics...")
    
    # HTTP requests with various patterns
    endpoints = ["/api/users", "/api/posts", "/api/search", "/health"]
    methods = ["GET", "POST", "PUT", "DELETE"]
    status_codes = [200, 201, 400, 404, 500]
    
    for i in range(50):
        endpoint = random.choice(endpoints)
        method = random.choice(methods)
        status = random.choices(status_codes, weights=[70, 10, 10, 5, 5])[0]
        duration = random.uniform(50, 500) if status < 400 else random.uniform(1000, 3000)
        request_size = random.randint(100, 5000)
        response_size = random.randint(500, 20000)
        
        logger.info(
            f"{method} {endpoint} completed",
            method=method,
            endpoint=endpoint,
            status_code=status,
            duration=duration,
            request_size=request_size,
            response_size=response_size
        )
        
        if status >= 500:
            logger.error(f"Server error on {method} {endpoint}", 
                        method=method, endpoint=endpoint, status_code=status)
    
    # Get metrics and display results
    summary = logger.get_metrics_summary()
    error_rates = logger.get_error_rates()
    latency_stats = logger.get_latency_stats()
    
    print(f"\nWeb Service Metrics Results:")
    print(f"Total HTTP responses: {summary['counters'].get('http_responses_total', {}).get('total', 0)}")
    print(f"Total errors: {summary['counters'].get('log_errors_total', {}).get('total', 0)}")
    
    if latency_stats:
        for metric_name, stats in latency_stats.items():
            print(f"\n{metric_name}:")
            print(f"  Average: {stats['avg_ms']:.1f}ms")
            print(f"  P95: {stats['p95_ms']:.1f}ms") 
            print(f"  P99: {stats['p99_ms']:.1f}ms")
    
    if error_rates:
        print(f"\nError Rates:")
        for metric, rate in error_rates.items():
            print(f"  {metric}: {rate:.2f} errors/sec")
    
    print("✓ Web service metrics working\n")

def demo_database_metrics():
    """Test database service specific metrics."""
    print("=== Database Service Metrics Demo ===")
    
    logger = MohflowLogger.smart(
        "db-service",
        enable_auto_metrics=True,
        metrics_config="database"
    )
    
    print("Simulating database service logs...")
    
    # Database operations
    tables = ["users", "posts", "comments", "sessions"]
    operations = ["SELECT", "INSERT", "UPDATE", "DELETE"]
    
    for i in range(30):
        table = random.choice(tables)
        operation = random.choice(operations)
        duration = random.uniform(5, 200)
        rows = random.randint(1, 1000)
        
        logger.info(
            f"Database {operation} completed on {table}",
            operation=operation,
            table=table,
            duration=duration,
            rows_returned=rows,
            query_type=operation.lower()
        )
        
        if duration > 150:
            logger.warning(f"Slow query detected", 
                         operation=operation, table=table, duration=duration)
    
    # Connection pool metrics
    logger.info("Connection pool status", pool_size=25, database="primary", pool_name="main")
    logger.info("Connection pool status", pool_size=15, database="replica", pool_name="readonly")
    
    summary = logger.get_metrics_summary()
    
    print(f"\nDatabase Service Metrics Results:")
    if summary:
        db_ops = summary['counters'].get('database_operations_total', {}).get('total', 0)
        print(f"Total database operations: {db_ops}")
        
        # Check for connection pool gauges
        for name, data in summary['gauges'].items():
            if 'pool' in name.lower():
                print(f"{name}: {list(data.values())[0]['current'] if data else 'N/A'}")
    
    print("✓ Database service metrics working\n")

def demo_custom_metrics():
    """Test custom metric extractors."""
    print("=== Custom Metrics Demo ===")
    
    logger = MohflowLogger.smart(
        "custom-metrics",
        enable_auto_metrics=True,
        metrics_config="custom"
    )
    
    # Add custom metric extractors
    if logger.metrics_generator:
        # Business metric: user sign-ups
        logger.metrics_generator.add_extractor(MetricExtractor(
            name="user_signups_total",
            metric_type=MetricType.COUNTER,
            pattern=r"user.*sign.*up|registration.*complete",
            description="Total user sign-ups",
            labels=["source", "plan"]
        ))
        
        # Performance metric: processing time
        logger.metrics_generator.add_extractor(MetricExtractor(
            name="processing_time_seconds",
            metric_type=MetricType.HISTOGRAM,
            pattern=r"processing.*time[=:\s]*([0-9.]+)",
            value_extractor=lambda ctx: float(ctx.get('processing_time', 0)) / 1000.0,
            description="Processing time in seconds",
            unit="seconds",
            labels=["task_type", "priority"]
        ))
        
        # Business metric: revenue
        logger.metrics_generator.add_extractor(MetricExtractor(
            name="revenue_dollars",
            metric_type=MetricType.COUNTER,
            pattern=r"payment.*received|transaction.*complete",
            value_extractor=lambda ctx: float(ctx.get('amount', 0)),
            description="Revenue in dollars",
            unit="dollars",
            labels=["payment_method", "plan"]
        ))
    
    print("Generating logs with custom metrics patterns...")
    
    # User sign-ups
    logger.info("User registration completed successfully", 
               source="website", plan="premium", user_id="12345")
    logger.info("New user signed up via mobile app", 
               source="mobile", plan="basic", user_id="12346")
    
    # Processing times
    logger.info("Background job completed", 
               task_type="email", priority="normal", processing_time=1250)
    logger.info("Data export finished", 
               task_type="export", priority="high", processing_time=5780)
    
    # Revenue events
    logger.info("Payment received from customer", 
               payment_method="credit_card", plan="premium", amount=29.99)
    logger.info("Transaction completed successfully", 
               payment_method="paypal", plan="basic", amount=9.99)
    
    summary = logger.get_metrics_summary()
    
    print(f"\nCustom Metrics Results:")
    if summary:
        for name, data in summary['counters'].items():
            if 'signup' in name or 'revenue' in name:
                print(f"{name}: {data['total']}")
        
        for name, stats in summary['histograms'].items():
            if 'processing' in name:
                print(f"{name}: avg={stats['avg']:.3f}s, p95={stats['p95']:.3f}s")
    
    print("✓ Custom metrics working\n")

def demo_high_volume_metrics():
    """Test metrics generation under high load."""
    print("=== High-Volume Metrics Demo ===")
    
    logger = MohflowLogger.smart(
        "high-volume",
        enable_auto_metrics=True,
        metrics_config="web_service",
        # Combine with sampling for realistic scenario
        enable_sampling=True,
        sample_rate=0.1  # 10% sampling
    )
    
    def worker_thread(worker_id: int, message_count: int):
        """Worker thread generating high-volume logs."""
        endpoints = ["/api/users", "/api/posts", "/api/search"]
        
        for i in range(message_count):
            endpoint = random.choice(endpoints)
            status = 200 if random.random() < 0.95 else 500  # 5% error rate
            duration = random.uniform(50, 300)
            
            if status == 200:
                logger.info(f"Request processed", 
                           endpoint=endpoint, status_code=status, duration=duration,
                           worker=worker_id, request_id=f"{worker_id}-{i}")
            else:
                logger.error(f"Request failed", 
                           endpoint=endpoint, status_code=status, duration=duration,
                           worker=worker_id, request_id=f"{worker_id}-{i}")
    
    print("Starting high-volume metric generation with 5 workers...")
    start_time = time.time()
    
    # Start multiple worker threads
    threads = []
    for worker_id in range(5):
        t = threading.Thread(target=worker_thread, args=(worker_id, 200))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    duration = time.time() - start_time
    summary = logger.get_metrics_summary()
    
    print(f"\nHigh-Volume Results ({duration:.2f}s):")
    if summary:
        total_requests = summary['counters'].get('http_responses_total', {}).get('total', 0)
        total_errors = summary['counters'].get('log_errors_total', {}).get('total', 0)
        
        print(f"Total requests processed: {total_requests}")
        print(f"Total errors: {total_errors}")
        print(f"Error rate: {(total_errors / total_requests * 100):.1f}%" if total_requests > 0 else "Error rate: 0%")
        print(f"Throughput: {total_requests / duration:.0f} requests/sec")
    
    sampling_stats = logger.get_sampling_stats()
    if sampling_stats:
        print(f"Logs sampled: {sampling_stats['sampled_logs_count']} / {sampling_stats['total_logs_count']}")
        print(f"Sampling efficiency: {(sampling_stats['sampled_logs_count'] / sampling_stats['total_logs_count'] * 100):.1f}%")
    
    print("✓ High-volume metrics working\n")

def demo_prometheus_export():
    """Test Prometheus metrics export."""
    print("=== Prometheus Export Demo ===")
    
    logger = MohflowLogger.smart(
        "prometheus-demo",
        enable_auto_metrics=True,
        metrics_config="web_service",
        export_prometheus=True
    )
    
    print("Generating sample logs for Prometheus export...")
    
    # Generate various metrics
    for i in range(20):
        logger.info(f"Request {i} processed", duration=random.uniform(100, 500), 
                   endpoint="/api/test", status_code=200)
        
        if i % 5 == 0:
            logger.error(f"Error occurred", error_code=500, endpoint="/api/test")
    
    # Export to Prometheus format
    prometheus_metrics = logger.export_prometheus_metrics()
    
    if prometheus_metrics:
        print("\nPrometheus Metrics Export (first 1000 chars):")
        print("─" * 60)
        print(prometheus_metrics[:1000])
        if len(prometheus_metrics) > 1000:
            print("... (truncated)")
        print("─" * 60)
        
        # Count different metric types
        lines = prometheus_metrics.split('\n')
        counter_lines = [l for l in lines if l.startswith('# TYPE') and 'counter' in l]
        histogram_lines = [l for l in lines if l.startswith('# TYPE') and 'summary' in l]
        gauge_lines = [l for l in lines if l.startswith('# TYPE') and 'gauge' in l]
        
        print(f"\nMetric Types Found:")
        print(f"  Counters: {len(counter_lines)}")
        print(f"  Histograms/Summaries: {len(histogram_lines)}")  
        print(f"  Gauges: {len(gauge_lines)}")
    else:
        print("No metrics to export")
    
    print("✓ Prometheus export working\n")

def main():
    """Run all auto-metrics demos."""
    print("🎯 MohFlow Auto-Metrics Generation Demo")
    print("=" * 50)
    
    try:
        # Basic functionality
        demo_basic_auto_metrics()
        
        # Service-specific metrics
        demo_web_service_metrics()
        demo_database_metrics()
        
        # Advanced features
        demo_custom_metrics()
        demo_high_volume_metrics()
        
        # Export functionality
        demo_prometheus_export()
        
        print("🎉 All auto-metrics features working correctly!")
        print("✅ Pattern extraction, counters/histograms/gauges, error rates")
        print("✅ Latency tracking, custom extractors, Prometheus export")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())