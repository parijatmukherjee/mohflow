"""
Example: OpenTelemetry Integration with MohFlow

This example demonstrates how to use MohFlow with OpenTelemetry for
distributed tracing and log correlation in microservices.

Prerequisites:
    pip install opentelemetry-api opentelemetry-sdk
    pip install opentelemetry-exporter-jaeger  # Optional for Jaeger
    pip install opentelemetry-exporter-otlp    # Optional for OTLP
"""

import time
from pathlib import Path
import sys

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from opentelemetry import trace
    HAS_OTEL = True
except ImportError:
    print("OpenTelemetry not available. Install with:")
    print("pip install opentelemetry-api opentelemetry-sdk")
    HAS_OTEL = False

from mohflow.logger.base import MohflowLogger


def basic_tracing_example():
    """Basic example of OpenTelemetry integration."""
    
    print("=== Basic OpenTelemetry Integration ===")
    
    # Create logger with tracing enabled
    logger = MohflowLogger.with_tracing(
        service_name="example-service",
        service_version="1.0.0",
        exporter_type="console",  # Outputs traces to console
        console_logging=True,
        formatter_type="structured"
    )
    
    if not HAS_OTEL:
        print("OpenTelemetry not available - using regular logging")
        logger.info("This message will not have trace correlation")
        return
    
    # Get tracer for creating spans
    tracer = trace.get_tracer(__name__)
    
    # Example: User registration flow
    with tracer.start_as_current_span("user_registration") as span:
        span.set_attribute("user.email", "user@example.com")
        span.set_attribute("user.signup_method", "email")
        
        logger.info("User registration started", 
                   email="user@example.com",
                   method="email_signup")
        
        # Simulate validation
        with tracer.start_as_current_span("validate_user_data") as validation_span:
            validation_span.set_attribute("validation.fields", ["email", "password"])
            
            time.sleep(0.1)  # Simulate processing time
            logger.info("User data validation completed",
                       fields_validated=["email", "password"],
                       validation_result="success")
        
        # Simulate database save
        with tracer.start_as_current_span("save_user_to_db") as db_span:
            db_span.set_attribute("db.operation", "insert")
            db_span.set_attribute("db.table", "users")
            
            time.sleep(0.05)  # Simulate DB time
            logger.info("User saved to database",
                       user_id=12345,
                       table="users")
        
        logger.info("User registration completed successfully",
                   user_id=12345,
                   total_time_ms=150)
    
    print("✓ All log messages in the span will have the same trace_id")
    print("✓ Child spans will have different span_ids but same trace_id")


def microservice_example():
    """Example for microservice architecture with OTLP export."""
    
    print("\n=== Microservice Architecture Example ===")
    
    # Create microservice-optimized logger
    logger = MohflowLogger.microservice(
        service_name="user-service",
        service_version="2.1.0",
        otlp_endpoint="http://localhost:4317",  # OTLP collector endpoint
        console_logging=True
    )
    
    if not HAS_OTEL:
        print("OpenTelemetry not available - traces won't be exported")
    
    # Simulate HTTP request processing
    logger.info("Processing user API request",
               method="GET",
               path="/users/12345",
               request_id="req_abc123")
    
    # The logger automatically includes:
    # - trace_id: Links logs to distributed trace
    # - span_id: Identifies current operation
    # - service info: Service name and version
    # - Environment context: From auto-configuration


def cloud_native_example():
    """Example for cloud-native deployments with environment-based config."""
    
    print("\n=== Cloud-Native Deployment Example ===")
    
    # Environment variables that configure OpenTelemetry:
    # OTEL_SERVICE_NAME=payment-service
    # OTEL_SERVICE_VERSION=3.2.1
    # OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://traces.example.com:4317
    # OTEL_EXPORTER_OTLP_TRACES_HEADERS=authorization=Bearer token123
    # OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production,k8s.namespace=payments
    
    # Create cloud-native logger (reads config from environment)
    logger = MohflowLogger.cloud_native(
        service_name="payment-service",
        service_version="3.2.1",
        console_logging=True
    )
    
    # Simulate payment processing
    logger.info("Payment processing initiated",
               payment_id="pay_xyz789",
               amount=99.99,
               currency="USD",
               customer_id="cust_123")
    
    logger.info("Payment validation completed",
               payment_id="pay_xyz789",
               validation_status="approved",
               fraud_score=0.15)
    
    logger.info("Payment processed successfully",
               payment_id="pay_xyz789",
               transaction_id="txn_456789",
               processing_time_ms=250)


def trace_correlation_example():
    """Example showing log correlation across service boundaries."""
    
    print("\n=== Trace Correlation Example ===")
    
    logger = MohflowLogger.with_tracing(
        service_name="api-gateway",
        console_logging=True
    )
    
    if not HAS_OTEL:
        print("OpenTelemetry not available - correlation demo skipped")
        return
    
    tracer = trace.get_tracer(__name__)
    
    # Simulate incoming request with trace context
    with tracer.start_as_current_span("api_request") as request_span:
        request_span.set_attribute("http.method", "POST")
        request_span.set_attribute("http.route", "/api/orders")
        
        logger.info("API request received",
                   method="POST",
                   path="/api/orders",
                   user_agent="mobile-app/1.2.3")
        
        # Simulate calling downstream service
        with tracer.start_as_current_span("call_inventory_service") as inventory_span:
            inventory_span.set_attribute("service.name", "inventory")
            inventory_span.set_attribute("http.url", "http://inventory:8080/check")
            
            logger.info("Calling inventory service",
                       service="inventory",
                       operation="check_availability",
                       product_ids=[1, 2, 3])
            
            # In real implementation, trace context would be propagated
            # via HTTP headers to the downstream service
            
            time.sleep(0.1)  # Simulate network call
            
            logger.info("Inventory service response received",
                       service="inventory",
                       available_items=2,
                       response_time_ms=95)
        
        # Simulate calling another service
        with tracer.start_as_current_span("call_payment_service") as payment_span:
            payment_span.set_attribute("service.name", "payment")
            payment_span.set_attribute("amount", 199.98)
            
            logger.info("Processing payment",
                       service="payment",
                       amount=199.98,
                       currency="USD")
            
            time.sleep(0.05)  # Simulate payment processing
            
            logger.info("Payment completed",
                       service="payment",
                       status="approved",
                       transaction_id="txn_999")
        
        logger.info("API request completed",
                   status=201,
                   order_id="order_777",
                   total_time_ms=155)
    
    print("✓ All logs share the same trace_id for end-to-end correlation")
    print("✓ Each service call has its own span_id for detailed tracing")


def performance_considerations():
    """Example showing performance optimizations with tracing."""
    
    print("\n=== Performance Considerations ===")
    
    # Fast logger with minimal overhead
    fast_logger = MohflowLogger(
        service_name="high-throughput-service",
        enable_otel=True,
        formatter_type="fast",           # Minimal JSON formatting
        async_handlers=True,             # Non-blocking handlers
        enable_context_enrichment=False, # Disable extra enrichment
        console_logging=False,           # Only file logging
        file_logging=True,
        log_file_path="/tmp/fast_logs.log"
    )
    
    # Measure performance
    message_count = 10_000
    start_time = time.perf_counter()
    
    for i in range(message_count):
        fast_logger.info(f"High-throughput message {i}",
                        batch_id=i // 1000,
                        sequence=i)
    
    end_time = time.perf_counter()
    duration = end_time - start_time
    throughput = message_count / duration
    
    print(f"✓ Logged {message_count:,} messages in {duration:.3f}s")
    print(f"✓ Throughput: {throughput:,.0f} messages/second")
    print(f"✓ Average latency: {(duration/message_count)*1000:.3f}ms per message")


def main():
    """Run all OpenTelemetry examples."""
    
    print("🚀 MohFlow OpenTelemetry Integration Examples")
    print("=" * 60)
    
    basic_tracing_example()
    microservice_example()
    cloud_native_example()
    trace_correlation_example()
    performance_considerations()
    
    print("\n" + "=" * 60)
    print("📚 Key Benefits of MohFlow + OpenTelemetry:")
    print("✓ Automatic trace correlation in logs")
    print("✓ Zero-code instrumentation for common frameworks")
    print("✓ High-performance async-safe logging")
    print("✓ Cloud-native configuration from environment")
    print("✓ Compatible with Jaeger, Zipkin, and OTLP collectors")
    print("✓ Graceful degradation when OpenTelemetry unavailable")
    
    print("\n🔧 Setup Instructions:")
    print("1. Install OpenTelemetry: pip install mohflow[otel]")
    print("2. Set environment variables for your tracing backend")
    print("3. Use factory methods for common deployment patterns")
    print("4. Logs will automatically include trace correlation")


if __name__ == "__main__":
    main()