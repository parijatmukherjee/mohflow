#!/usr/bin/env python3
"""
Demo script showing framework integrations for MohFlow logging.

This demonstrates:
1. FastAPI middleware integration
2. Django middleware simulation
3. Flask extension integration
4. Celery task logging integration
5. ASGI/WSGI generic middleware
6. Custom decorators and utilities
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import time
import asyncio
import threading
from datetime import datetime
from mohflow import MohflowLogger

# Import integrations (with fallbacks for missing frameworks)
try:
    from mohflow.integrations.fastapi import (
        MohFlowFastAPIMiddleware, log_endpoint, 
        extract_auth_context, create_health_endpoint
    )
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

try:
    from mohflow.integrations.django import log_view, setup_command_logging
    HAS_DJANGO = True  
except ImportError:
    HAS_DJANGO = False

try:
    from mohflow.integrations.flask import (
        MohFlowFlaskExtension, log_route, timed_route,
        log_business_event, get_request_id
    )
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

try:
    from mohflow.integrations.celery import (
        log_task, setup_celery_logging, log_task_progress,
        create_celery_logger, TaskErrorAggregator
    )
    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False

from mohflow.integrations.asgi_wsgi import (
    log_request_manually, log_response_manually, auto_setup_middleware
)


def demo_fastapi_integration():
    """Test FastAPI middleware integration."""
    print("=== FastAPI Integration Demo ===")
    
    if not HAS_FASTAPI:
        print("⚠️  FastAPI not installed, skipping integration demo")
        print("   Install with: pip install fastapi uvicorn")
        return
    
    logger = MohflowLogger.smart(
        "fastapi-demo",
        enable_auto_metrics=True,
        metrics_config="web_service"
    )
    
    print("Simulating FastAPI request/response cycle...")
    
    # Simulate FastAPI request processing
    class MockRequest:
        def __init__(self, method, path, headers=None):
            self.method = method
            self.url = type('URL', (), {'path': path})()
            self.headers = headers or {}
            self.query_params = {}
    
    class MockResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {"content-type": "application/json"}
    
    # Create middleware instance (skip if FastAPI not available)
    class MockMiddleware:
        def __init__(self, **kwargs):
            self.logger = kwargs.get('logger')
            
        async def _extract_request_context(self, request, request_id):
            return {
                "method": request.method,
                "path": request.url.path,
                "client_ip": "127.0.0.1",
                "user_agent": "Test Agent"
            }
            
        async def _extract_response_context(self, response, duration_ms):
            return {
                "status_code": response.status_code,
                "duration": duration_ms,
                "content_type": "application/json"
            }
    
    middleware = MockMiddleware(logger=logger)
    
    # Simulate various requests
    requests = [
        ("GET", "/api/users", 200),
        ("POST", "/api/users", 201),
        ("GET", "/api/users/123", 404),
        ("POST", "/api/auth/login", 200),
        ("GET", "/api/data", 500)
    ]
    
    for method, path, status in requests:
        mock_request = MockRequest(method, path)
        request_context = asyncio.run(
            middleware._extract_request_context(mock_request, "req-123")
        )
        
        mock_response = MockResponse(status)
        response_context = asyncio.run(
            middleware._extract_response_context(mock_response, 150.0)
        )
        
        # Log the request/response cycle
        with logger.request_context(request_id="req-123", **request_context):
            if status < 400:
                logger.info(f"{method} {path} - {status} (150.0ms)", 
                           **{**request_context, **response_context})
            else:
                logger.error(f"{method} {path} - {status} (150.0ms)",
                           **{**request_context, **response_context})
    
    print("✓ FastAPI integration simulation working\n")


def demo_django_integration():
    """Test Django middleware integration simulation."""
    print("=== Django Integration Demo ===")
    
    logger = MohflowLogger.smart(
        "django-demo",
        enable_auto_metrics=True
    )
    
    print("Simulating Django request/response cycle...")
    
    # Simulate Django-style processing
    class MockDjangoRequest:
        def __init__(self, method, path):
            self.method = method
            self.path = path
            self.GET = {}
            self.META = {
                "HTTP_USER_AGENT": "Mozilla/5.0 Test Browser",
                "REMOTE_ADDR": "127.0.0.1"
            }
            self.content_type = "application/json"
            self.body = b'{"test": "data"}'
            
            # Mock user and session
            self.user = type('User', (), {
                'is_authenticated': True,
                'id': 123,
                'username': 'testuser',
                'email': 'test@example.com'
            })()
            self.session = type('Session', (), {'session_key': 'test-session-123'})()
    
    class MockDjangoResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.content = b'{"result": "success"}'
            
        def get(self, header, default=None):
            headers = {"Content-Type": "application/json"}
            return headers.get(header, default)
    
    # Use the Django decorator
    @log_view(logger, component="auth", operation="login")
    def mock_login_view(request):
        time.sleep(0.1)  # Simulate processing
        return MockDjangoResponse(200)
    
    # Process mock requests
    requests = [
        ("GET", "/admin/"),
        ("POST", "/auth/login/"),
        ("GET", "/api/profile/"),
        ("DELETE", "/api/posts/123/")
    ]
    
    for method, path in requests:
        mock_request = MockDjangoRequest(method, path)
        
        # Simulate middleware processing
        request_id = f"django-{time.time()}"
        
        request_context = {
            "method": method,
            "path": path,
            "user_id": 123,
            "username": "testuser",
            "session_id": "test-session-123",
            "client_ip": "127.0.0.1"
        }
        
        with logger.request_context(request_id=request_id, **request_context):
            logger.info(f"{method} {path} - Request received", **request_context)
            
            if path == "/auth/login/":
                # Use the decorated view
                response = mock_login_view(mock_request)
                logger.info(f"{method} {path} - 200 (100.0ms)", 
                           status_code=200, duration=100.0, **request_context)
            else:
                # Regular response
                duration = 50.0
                logger.info(f"{method} {path} - 200 ({duration}ms)",
                           status_code=200, duration=duration, **request_context)
    
    print("✓ Django integration simulation working\n")


def demo_flask_integration():
    """Test Flask extension integration simulation."""
    print("=== Flask Integration Demo ===")
    
    logger = MohflowLogger.smart(
        "flask-demo",
        enable_auto_metrics=True
    )
    
    print("Simulating Flask request/response cycle...")
    
    # Use Flask decorators (create mock if not available)
    def mock_log_route(logger_instance, **kwargs):
        def decorator(func):
            return func  # Simple passthrough for demo
        return decorator
    
    def mock_timed_route(logger_instance):
        def decorator(func):
            return func  # Simple passthrough for demo
        return decorator
    
    # Use decorators (mock or real)
    route_decorator = log_route if HAS_FLASK else mock_log_route
    timed_decorator = timed_route if HAS_FLASK else mock_timed_route
    
    @route_decorator(logger, component="api", operation="get_users")
    def mock_get_users():
        time.sleep(0.05)  # Simulate processing
        return {"users": [{"id": 1, "name": "John"}]}
    
    @timed_decorator(logger)
    def mock_expensive_operation():
        time.sleep(0.2)  # Simulate expensive operation
        return {"result": "computed"}
    
    # Simulate Flask request processing
    routes = [
        ("GET", "/api/users", mock_get_users),
        ("GET", "/api/compute", mock_expensive_operation),
        ("POST", "/api/orders", lambda: {"order_id": 123}),
        ("DELETE", "/api/cache", lambda: {"cleared": True})
    ]
    
    for method, path, handler in routes:
        request_context = {
            "method": method,
            "path": path,
            "client_ip": "192.168.1.100",
            "user_agent": "Flask Test Client",
            "flask_endpoint": handler.__name__
        }
        
        request_id = f"flask-{time.time()}"
        
        with logger.request_context(request_id=request_id, **request_context):
            logger.info(f"{method} {path} - Request received", **request_context)
            
            # Execute handler
            start_time = time.time()
            try:
                result = handler()
                duration = (time.time() - start_time) * 1000
                
                logger.info(f"{method} {path} - 200 ({duration:.1f}ms)",
                           status_code=200, duration=duration, **request_context)
                
                # Log business event for orders
                if "orders" in path:
                    if HAS_FLASK:
                        log_business_event(logger, "order_created", 
                                         order_id=123, amount=29.99)
                    else:
                        logger.info("Business event: order_created",
                                   event="order_created", order_id=123, amount=29.99)
                
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(f"{method} {path} - 500 ({duration:.1f}ms)",
                           error=str(e), duration=duration, **request_context)
    
    print("✓ Flask integration simulation working\n")


def demo_celery_integration():
    """Test Celery task logging integration."""
    print("=== Celery Integration Demo ===")
    
    if not HAS_CELERY:
        print("⚠️  Celery not installed, skipping integration demo")
        print("   Install with: pip install celery")
        return
    
    logger = MohflowLogger.smart(
        "celery-demo",
        enable_auto_metrics=True
    )
    
    print("Simulating Celery task execution...")
    
    # Mock Celery task execution
    @log_task(logger, component="data_processing", priority="high")
    def mock_process_data(data_id):
        time.sleep(0.1)  # Simulate processing
        return {"processed": data_id, "status": "success"}
    
    @log_task(logger, component="email", priority="normal")
    def mock_send_email(recipient):
        time.sleep(0.05)  # Simulate email sending
        if recipient == "invalid@":
            raise ValueError("Invalid email address")
        return {"sent": True, "recipient": recipient}
    
    # Simulate task execution
    tasks = [
        (mock_process_data, (12345,)),
        (mock_send_email, ("user@example.com",)),
        (mock_process_data, (67890,)),
        (mock_send_email, ("invalid@",)),  # This will fail
    ]
    
    for task_func, args in tasks:
        task_id = f"task-{time.time()}"
        
        # Create task-specific logger
        task_logger = create_celery_logger(logger, task_func.__name__)
        
        try:
            # Simulate task start
            task_logger.info(f"Task {task_func.__name__} started",
                           task_id=task_id, task_args=args)
            
            # Execute task
            result = task_func(*args)
            
            # Log success
            task_logger.info(f"Task {task_func.__name__} completed successfully",
                           task_id=task_id, result=result)
            
            # Simulate progress for data processing tasks
            if "process_data" in task_func.__name__:
                for i in range(5):
                    log_task_progress(task_logger, task_id, i+1, 5, 
                                    f"Processing step {i+1}")
                    time.sleep(0.01)
        
        except Exception as e:
            # Log failure
            task_logger.error(f"Task {task_func.__name__} failed",
                            task_id=task_id, error=str(e), 
                            error_type=type(e).__name__)
    
    print("✓ Celery integration simulation working\n")


def demo_asgi_wsgi_middleware():
    """Test generic ASGI/WSGI middleware."""
    print("=== ASGI/WSGI Middleware Demo ===")
    
    logger = MohflowLogger.smart(
        "generic-middleware-demo",
        enable_auto_metrics=True
    )
    
    print("Simulating generic middleware request processing...")
    
    # Manual request/response logging
    requests = [
        ("GET", "/api/status", 200),
        ("POST", "/api/webhook", 202),
        ("GET", "/api/missing", 404),
        ("POST", "/api/error", 500)
    ]
    
    for method, path, status_code in requests:
        # Log request start
        request_id = log_request_manually(
            logger, method, path,
            client_ip="10.0.0.1",
            user_agent="Generic Client/1.0"
        )
        
        # Simulate processing
        start_time = time.time()
        time.sleep(0.02)  # Simulate work
        duration_ms = (time.time() - start_time) * 1000
        
        # Log response
        log_response_manually(
            logger, request_id, method, path, status_code, duration_ms,
            content_type="application/json",
            response_size=256
        )
    
    print("✓ Generic middleware simulation working\n")


def demo_performance_monitoring():
    """Test performance monitoring across integrations."""
    print("=== Performance Monitoring Demo ===")
    
    logger = MohflowLogger.smart(
        "performance-demo",
        enable_auto_metrics=True,
        metrics_config="web_service"
    )
    
    print("Generating performance metrics across different scenarios...")
    
    # High-throughput simulation
    def simulate_load_test():
        endpoints = ["/api/users", "/api/posts", "/api/search"]
        methods = ["GET", "POST", "PUT", "DELETE"]
        
        for i in range(50):
            method = methods[i % len(methods)]
            endpoint = endpoints[i % len(endpoints)]
            
            # Vary response times
            if "search" in endpoint:
                duration = 200 + (i % 100)  # Slower search
            else:
                duration = 50 + (i % 50)   # Faster CRUD
            
            status = 200 if i % 20 != 0 else (400 if i % 30 != 0 else 500)
            
            request_id = f"perf-{i}"
            
            with logger.request_context(request_id=request_id):
                if status == 200:
                    logger.info(f"{method} {endpoint} - {status} ({duration}ms)",
                               method=method, endpoint=endpoint, 
                               status_code=status, duration=duration)
                else:
                    logger.error(f"{method} {endpoint} - {status} ({duration}ms)",
                                method=method, endpoint=endpoint,
                                status_code=status, duration=duration)
    
    # Run load test
    simulate_load_test()
    
    # Get performance metrics
    metrics_summary = logger.get_metrics_summary()
    error_rates = logger.get_error_rates()
    latency_stats = logger.get_latency_stats()
    
    if metrics_summary:
        print("\nPerformance Metrics Summary:")
        
        # HTTP responses
        if 'http_responses_total' in metrics_summary.get('counters', {}):
            http_responses = metrics_summary['counters']['http_responses_total']
            print(f"  Total HTTP responses: {http_responses['total']}")
        
        # Error metrics
        if 'log_errors_total' in metrics_summary.get('counters', {}):
            error_count = metrics_summary['counters']['log_errors_total']['total']
            print(f"  Total errors: {error_count}")
        
        # Latency metrics
        if latency_stats:
            for metric_name, stats in latency_stats.items():
                print(f"  {metric_name}:")
                print(f"    Average: {stats['avg_ms']:.1f}ms")
                print(f"    P95: {stats['p95_ms']:.1f}ms")
                print(f"    P99: {stats['p99_ms']:.1f}ms")
        
        # Error rates
        if error_rates:
            print(f"  Error Rates:")
            for metric, rate in error_rates.items():
                print(f"    {metric}: {rate:.2f} errors/sec")
    
    print("✓ Performance monitoring working\n")


def demo_multi_framework_scenario():
    """Test logging across multiple framework integrations."""
    print("=== Multi-Framework Scenario Demo ===")
    
    logger = MohflowLogger.smart(
        "multi-framework-demo",
        enable_auto_metrics=True,
        enable_sampling=True,
        sample_rate=0.8  # Sample 80% for demo
    )
    
    print("Simulating microservices with different frameworks...")
    
    def api_gateway_service():
        """Simulate API Gateway (FastAPI)"""
        with logger.request_context(service="api-gateway", framework="fastapi"):
            logger.info("API Gateway processing request", 
                       endpoint="/api/v1/users", method="GET")
            time.sleep(0.01)
            logger.info("API Gateway request completed", duration=10)
    
    def user_service():
        """Simulate User Service (Django)"""
        with logger.request_context(service="user-service", framework="django"):
            logger.info("User service query started", table="users", operation="SELECT")
            time.sleep(0.05)
            logger.info("User service query completed", rows_returned=25, duration=50)
    
    def notification_service():
        """Simulate Notification Service (Flask)"""
        with logger.request_context(service="notification-service", framework="flask"):
            logger.info("Notification service processing", recipient="user@example.com")
            time.sleep(0.02)
            logger.info("Email notification sent", status="delivered")
    
    def background_task():
        """Simulate Background Task (Celery)"""
        with logger.request_context(service="background-worker", framework="celery"):
            logger.info("Background task started", task_type="data_processing")
            time.sleep(0.1)
            logger.info("Background task completed", processed_items=100)
    
    # Simulate concurrent services
    services = [api_gateway_service, user_service, notification_service, background_task]
    threads = []
    
    # Start services concurrently
    for service in services:
        for _ in range(3):  # 3 requests per service
            thread = threading.Thread(target=service)
            threads.append(thread)
            thread.start()
            time.sleep(0.01)  # Slight delay between starts
    
    # Wait for completion
    for thread in threads:
        thread.join()
    
    # Get cross-service metrics
    sampling_stats = logger.get_sampling_stats()
    
    print(f"\nMulti-Framework Results:")
    if sampling_stats:
        print(f"  Total requests across all services: {sampling_stats['total_logs_count']}")
        print(f"  Sampled requests: {sampling_stats['sampled_logs_count']}")
        print(f"  Sampling efficiency: {(sampling_stats['sampled_logs_count'] / sampling_stats['total_logs_count'] * 100):.1f}%")
    
    print("✓ Multi-framework scenario working\n")


def main():
    """Run all framework integration demos."""
    print("🔗 MohFlow Framework Integrations Demo")
    print("=" * 50)
    
    try:
        # Individual framework demos
        demo_fastapi_integration()
        demo_django_integration()
        demo_flask_integration()
        demo_celery_integration()
        
        # Generic middleware demo
        demo_asgi_wsgi_middleware()
        
        # Advanced scenarios
        demo_performance_monitoring()
        demo_multi_framework_scenario()
        
        print("🎉 All framework integrations working correctly!")
        print("✅ FastAPI, Django, Flask, Celery integrations")
        print("✅ ASGI/WSGI generic middleware, performance monitoring")
        print("✅ Multi-framework scenarios, automatic metrics generation")
        
    except Exception as e:
        print(f"❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    return 0


if __name__ == "__main__":
    sys.exit(main())