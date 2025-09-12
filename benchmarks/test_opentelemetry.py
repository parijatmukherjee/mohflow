"""
Test OpenTelemetry integration in MohFlow logging.
"""

import tempfile
import time
import json
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from mohflow.logger.base import MohflowLogger
    from mohflow.opentelemetry import (
        TraceContext,
        OpenTelemetryEnricher,
        setup_otel_logging,
        get_current_trace_context
    )
    
    # Test if OpenTelemetry is available
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import SERVICE_NAME
    
    HAS_OTEL = True
except ImportError as e:
    print(f"⚠ OpenTelemetry not available: {e}")
    HAS_OTEL = False


def test_basic_otel_integration():
    """Test basic OpenTelemetry integration without external dependencies."""
    
    if not HAS_OTEL:
        print("⚠ Skipping OpenTelemetry tests (dependencies not available)")
        return False
    
    print("🔍 Testing basic OpenTelemetry integration...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "otel_test.log"
        
        # Create logger with OpenTelemetry enabled
        logger = MohflowLogger.with_tracing(
            service_name="test_service",
            service_version="1.0.0",
            exporter_type="console",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True,
            formatter_type="structured"
        )
        
        # Test basic logging
        logger.info("Test message without trace context", user_id=123)
        
        # Test with trace span
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("test_operation") as span:
            span.set_attribute("operation.type", "test")
            span.set_attribute("user.id", "test_user")
            
            logger.info("Test message with trace context", 
                       operation="test_operation",
                       component="test_suite")
            
            logger.error("Test error with trace", 
                        error_type="test_error",
                        exc_info=False)
        
        # Verify log file was created and contains trace information
        assert log_file.exists(), "Log file should exist"
        
        log_entries = []
        with open(log_file) as f:
            for line in f:
                if line.strip():
                    try:
                        log_entry = json.loads(line.strip())
                        log_entries.append(log_entry)
                    except json.JSONDecodeError:
                        pass
        
        assert len(log_entries) >= 2, f"Should have at least 2 log entries, got {len(log_entries)}"
        
        # Check for trace context in traced logs
        traced_entries = [entry for entry in log_entries if 'trace_id' in entry]
        assert len(traced_entries) >= 2, f"Should have at least 2 traced entries, got {len(traced_entries)}"
        
        # Verify trace context fields
        traced_entry = traced_entries[0]
        assert 'trace_id' in traced_entry, "Should contain trace_id"
        assert 'span_id' in traced_entry, "Should contain span_id"
        assert len(traced_entry['trace_id']) == 32, "Trace ID should be 32 hex chars"
        assert len(traced_entry['span_id']) == 16, "Span ID should be 16 hex chars"
        
        print("✓ Basic OpenTelemetry integration working")
        return True


def test_trace_context_extraction():
    """Test OpenTelemetry trace context extraction."""
    
    if not HAS_OTEL:
        print("⚠ Skipping trace context test")
        return False
    
    print("🔍 Testing trace context extraction...")
    
    # Setup tracing
    setup_otel_logging(
        service_name="test_context_service",
        service_version="1.0.0",
        exporter_type="console"
    )
    
    tracer = trace.get_tracer(__name__)
    
    # Test without active span
    context_empty = get_current_trace_context()
    assert context_empty.trace_id is None, "Should have no trace context without span"
    
    # Test with active span  
    with tracer.start_as_current_span("context_test") as span:
        span.set_attribute("test.attribute", "test_value")
        
        context_with_span = get_current_trace_context()
        assert context_with_span.trace_id is not None, "Should have trace ID with active span"
        assert context_with_span.span_id is not None, "Should have span ID with active span"
        
        # Test TraceContext to dict conversion
        context_dict = context_with_span.to_dict()
        assert 'trace_id' in context_dict, "Dict should contain trace_id"
        assert 'span_id' in context_dict, "Dict should contain span_id"
        
        print(f"✓ Extracted trace context: {context_dict['trace_id'][:8]}...")
    
    print("✓ Trace context extraction working")
    return True


def test_otel_enricher():
    """Test OpenTelemetry enricher functionality."""
    
    if not HAS_OTEL:
        print("⚠ Skipping enricher test")
        return False
    
    print("🔍 Testing OpenTelemetry enricher...")
    
    # Setup tracing
    setup_otel_logging("test_enricher_service")
    
    enricher = OpenTelemetryEnricher(
        include_trace_id=True,
        include_span_id=True,
        include_baggage=True
    )
    
    # Test enrichment without span
    test_data = {"message": "test", "user_id": 123}
    enriched_empty = enricher.enrich_dict(test_data)
    
    # Should not add trace fields without active span
    assert 'trace_id' not in enriched_empty, "Should not add trace_id without span"
    
    # Test enrichment with span
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("enricher_test"):
        enriched_with_span = enricher.enrich_dict(test_data)
        
        # Should add trace fields with active span
        assert 'trace_id' in enriched_with_span, "Should add trace_id with span"
        assert 'span_id' in enriched_with_span, "Should add span_id with span"
        assert enriched_with_span['message'] == "test", "Should preserve original fields"
        assert enriched_with_span['user_id'] == 123, "Should preserve original fields"
    
    print("✓ OpenTelemetry enricher working")
    return True


def test_logger_factory_methods():
    """Test OpenTelemetry-enabled logger factory methods."""
    
    if not HAS_OTEL:
        print("⚠ Skipping factory method tests")
        return False
    
    print("🔍 Testing OpenTelemetry factory methods...")
    
    # Test with_tracing factory
    logger_tracing = MohflowLogger.with_tracing(
        service_name="test_tracing",
        service_version="2.0.0",
        console_logging=False
    )
    
    assert logger_tracing.enable_otel, "with_tracing should enable OpenTelemetry"
    assert logger_tracing.otel_service_version == "2.0.0", "Should set service version"
    
    # Test microservice factory
    logger_micro = MohflowLogger.microservice(
        service_name="test_microservice",
        console_logging=False
    )
    
    assert logger_micro.enable_otel, "microservice should enable OpenTelemetry"
    assert logger_micro.formatter_type == "production", "Should use production formatter"
    assert logger_micro.otel_exporter_type == "otlp", "Should use OTLP exporter"
    
    # Test cloud_native factory
    logger_cloud = MohflowLogger.cloud_native(
        service_name="test_cloud",
        console_logging=False
    )
    
    assert logger_cloud.enable_otel, "cloud_native should enable OpenTelemetry"
    assert logger_cloud.async_handlers, "Should use async handlers"
    
    print("✓ OpenTelemetry factory methods working")
    return True


def test_trace_correlation():
    """Test trace correlation across log messages."""
    
    if not HAS_OTEL:
        print("⚠ Skipping trace correlation test")
        return False
    
    print("🔍 Testing trace correlation...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "correlation_test.log"
        
        logger = MohflowLogger.with_tracing(
            service_name="correlation_test",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True
        )
        
        tracer = trace.get_tracer(__name__)
        
        # Create parent span
        with tracer.start_as_current_span("parent_operation") as parent_span:
            parent_span.set_attribute("operation.name", "parent")
            
            logger.info("Parent operation started", step=1)
            
            # Create child span
            with tracer.start_as_current_span("child_operation") as child_span:
                child_span.set_attribute("operation.name", "child")
                
                logger.info("Child operation in progress", step=2)
                logger.warning("Child operation warning", step=3)
            
            logger.info("Parent operation completed", step=4)
        
        # Read log file and verify trace correlation
        log_entries = []
        with open(log_file) as f:
            for line in f:
                if line.strip():
                    try:
                        log_entry = json.loads(line.strip())
                        log_entries.append(log_entry)
                    except json.JSONDecodeError:
                        pass
        
        assert len(log_entries) >= 4, f"Should have at least 4 log entries, got {len(log_entries)}"
        
        # All entries should have trace_id (same trace)
        trace_ids = [entry.get('trace_id') for entry in log_entries if 'trace_id' in entry]
        assert len(trace_ids) >= 4, "All entries should have trace_id"
        assert len(set(trace_ids)) == 1, "All entries should have same trace_id"
        
        # Parent and child spans should have different span_ids
        span_ids = [entry.get('span_id') for entry in log_entries if 'span_id' in entry]
        assert len(set(span_ids)) >= 2, "Should have at least 2 different span_ids"
        
        print(f"✓ Trace correlation working - {len(log_entries)} messages correlated")
        return True


def test_performance_with_tracing():
    """Test logging performance with OpenTelemetry enabled."""
    
    if not HAS_OTEL:
        print("⚠ Skipping performance test")
        return False
    
    print("🔍 Testing performance with OpenTelemetry...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "perf_test.log"
        
        # Test with tracing enabled
        logger_otel = MohflowLogger.with_tracing(
            service_name="perf_test",
            log_file_path=str(log_file),
            console_logging=False,
            file_logging=True,
            formatter_type="fast"
        )
        
        message_count = 5_000
        tracer = trace.get_tracer(__name__)
        
        # Measure performance with active span
        with tracer.start_as_current_span("performance_test"):
            start_time = time.perf_counter()
            
            for i in range(message_count):
                logger_otel.info(f"Performance test message {i}",
                               iteration=i, 
                               batch="performance_test")
            
            end_time = time.perf_counter()
        
        duration = end_time - start_time
        messages_per_second = message_count / duration
        
        print(f"✓ OpenTelemetry performance: {messages_per_second:,.0f} msg/sec")
        
        # Verify all messages have trace context
        log_entries = []
        with open(log_file) as f:
            for line in f:
                if line.strip():
                    try:
                        log_entry = json.loads(line.strip())
                        log_entries.append(log_entry)
                    except json.JSONDecodeError:
                        pass
        
        traced_entries = [entry for entry in log_entries if 'trace_id' in entry]
        trace_coverage = len(traced_entries) / len(log_entries) if log_entries else 0
        
        print(f"✓ Trace coverage: {trace_coverage*100:.1f}% ({len(traced_entries)}/{len(log_entries)})")
        
        return messages_per_second >= 1000  # Should maintain reasonable performance


def run_opentelemetry_tests():
    """Run all OpenTelemetry integration tests."""
    
    print("🚀 Running OpenTelemetry Integration Tests")
    print("=" * 50)
    
    if not HAS_OTEL:
        print("❌ OpenTelemetry dependencies not available")
        print("\nTo enable OpenTelemetry testing, install:")
        print("  pip install opentelemetry-api opentelemetry-sdk")
        return False
    
    results = {}
    
    try:
        results['basic'] = test_basic_otel_integration()
    except Exception as e:
        print(f"✗ Basic integration test failed: {e}")
        results['basic'] = False
    
    try:
        results['context'] = test_trace_context_extraction()
    except Exception as e:
        print(f"✗ Context extraction test failed: {e}")
        results['context'] = False
    
    try:
        results['enricher'] = test_otel_enricher()
    except Exception as e:
        print(f"✗ Enricher test failed: {e}")
        results['enricher'] = False
    
    try:
        results['factories'] = test_logger_factory_methods()
    except Exception as e:
        print(f"✗ Factory methods test failed: {e}")
        results['factories'] = False
    
    try:
        results['correlation'] = test_trace_correlation()
    except Exception as e:
        print(f"✗ Trace correlation test failed: {e}")
        results['correlation'] = False
    
    try:
        results['performance'] = test_performance_with_tracing()
    except Exception as e:
        print(f"✗ Performance test failed: {e}")
        results['performance'] = False
    
    print("\n" + "=" * 50)
    print("✅ OpenTelemetry Tests Complete")
    
    # Print summary
    print("\n📊 TEST SUMMARY")
    print("=" * 30)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name.capitalize()}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = run_opentelemetry_tests()
    
    if success:
        print("\n🎉 All OpenTelemetry integration tests passed!")
    else:
        print("\n⚠ Some OpenTelemetry tests failed")
    
    exit(0 if success else 1)