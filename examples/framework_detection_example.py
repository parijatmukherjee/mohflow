"""
Example: Advanced Framework Detection and Auto-Configuration

This example demonstrates MohFlow's intelligent framework detection
and automatic optimization for different Python frameworks and deployment contexts.
"""

import sys
from pathlib import Path
import json

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mohflow.logger.base import MohflowLogger
from mohflow.framework_detection import get_framework_summary, detect_frameworks
from mohflow.auto_config import get_framework_recommendations, get_environment_summary


def demo_basic_framework_detection():
    """Demonstrate basic framework detection capabilities."""
    
    print("=== Framework Detection Demo ===")
    
    # Get framework summary
    summary = get_framework_summary()
    print(f"📱 Application Type: {summary['app_type']}")
    print(f"🚀 Deployment Type: {summary['deployment_type']}")
    print(f"⚡ Uses Async: {summary['uses_async']}")
    
    if summary['frameworks']:
        print(f"\n🛠 Detected Frameworks:")
        for framework in summary['frameworks']:
            print(f"  • {framework['name']} {framework.get('version', 'unknown')}")
            print(f"    - Async: {framework['is_async']}")
            print(f"    - Recommended Formatter: {framework['formatter']}")
    else:
        print("\n🛠 No specific frameworks detected (library/CLI application)")
    
    print(f"\n🔧 Capabilities:")
    caps = summary['capabilities']
    print(f"  • Database: {caps['database']}")
    print(f"  • Cache: {caps['cache']}")
    print(f"  • Message Queue: {caps['message_queue']}")
    print(f"  • External APIs: {caps['external_apis']}")


def demo_intelligent_configuration():
    """Demonstrate intelligent configuration based on framework detection."""
    
    print("\n=== Intelligent Auto-Configuration ===")
    
    # Get framework recommendations
    recommendations = get_framework_recommendations()
    
    print(f"📊 Application Analysis:")
    print(f"  • Type: {recommendations['detected_app_type']}")
    print(f"  • Deployment: {recommendations['deployment_type']}")
    
    if recommendations['frameworks']:
        print(f"\n🎯 Framework Recommendations:")
        for framework in recommendations['frameworks']:
            print(f"  • {framework['name']}")
            print(f"    - Formatter: {framework['recommended_formatter']}")
            print(f"    - Async Support: {framework['supports_async']}")
            if framework.get('integration_notes'):
                print(f"    - Note: {framework['integration_notes']}")
    
    if recommendations['integration_tips']:
        print(f"\n💡 Integration Tips:")
        for tip in recommendations['integration_tips']:
            print(f"  • {tip}")
    
    if recommendations['performance_notes']:
        print(f"\n⚡ Performance Notes:")
        for note in recommendations['performance_notes']:
            print(f"  • {note}")


def demo_smart_logger_factory():
    """Demonstrate smart logger factory methods."""
    
    print("\n=== Smart Logger Factory Methods ===")
    
    # Create a smart logger that auto-detects and optimizes
    print("Creating smart logger with auto-detection...")
    
    smart_logger = MohflowLogger.smart(
        service_name="demo-app",
        console_logging=True
    )
    
    print("✓ Smart logger created")
    
    # Get optimization report
    report = smart_logger.get_optimization_report()
    
    print(f"\n📈 Optimization Report:")
    config = report['current_config']
    print(f"  • Formatter: {config['formatter_type']}")
    print(f"  • Async Handlers: {config['async_handlers']}")
    print(f"  • OpenTelemetry: {config['enable_otel']}")
    print(f"  • Environment: {config['environment']}")
    
    # Show detected environment
    env = report['environment']
    print(f"\n🌍 Environment Details:")
    print(f"  • Type: {env['environment_type']}")
    print(f"  • Cloud: {env['cloud_provider']}")
    print(f"  • Container: {env.get('container_runtime', 'none')}")
    print(f"  • Platform: {env['platform']}")
    
    # Show optimization tips
    if report['optimization_tips']:
        print(f"\n💡 Optimization Tips:")
        for tip in report['optimization_tips']:
            print(f"  • {tip}")
    else:
        print(f"\n✅ Configuration is already optimized!")
    
    return smart_logger


def demo_framework_specific_configs():
    """Demonstrate framework-specific optimizations."""
    
    print("\n=== Framework-Specific Configurations ===")
    
    # Simulate different framework scenarios
    scenarios = [
        {
            "name": "High-throughput API",
            "config": {"formatter_type": "fast", "async_handlers": True},
            "description": "Optimized for FastAPI/aiohttp-style APIs"
        },
        {
            "name": "Web Application",
            "config": {"formatter_type": "structured", "enable_context_enrichment": True},
            "description": "Optimized for Flask/Django web apps"
        },
        {
            "name": "Background Worker", 
            "config": {"formatter_type": "production", "file_logging": True, "log_file_path": "/tmp/worker.log"},
            "description": "Optimized for Celery/RQ workers"
        },
        {
            "name": "Microservice",
            "config": {"formatter_type": "production", "enable_otel": True, "async_handlers": True},
            "description": "Optimized for cloud-native microservices"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📋 {scenario['name']} Configuration:")
        print(f"   {scenario['description']}")
        
        # Prepare config without conflicts
        config = scenario['config'].copy()
        config['console_logging'] = True  # Override for demo
        config['service_name'] = f"demo-{scenario['name'].lower().replace(' ', '-')}"
        
        logger = MohflowLogger(**config)
        
        # Log a sample message to show the configuration in action
        logger.info("Sample log message", 
                   scenario=scenario['name'], 
                   optimization="framework_specific")
        
        print(f"   ✓ Configured with {scenario['config']}")


def demo_auto_optimized_logger():
    """Demonstrate the most intelligent auto-optimized logger."""
    
    print("\n=== Auto-Optimized Logger Demo ===")
    
    # Create the most intelligent logger
    logger = MohflowLogger.auto_optimized(
        service_name="intelligent-app",
        enable_tracing=False,  # Disable for demo to avoid OpenTelemetry requirement
        console_logging=True
    )
    
    print("🧠 Created auto-optimized logger with:")
    print(f"  • Framework detection: enabled")
    print(f"  • Environment detection: enabled") 
    print(f"  • Performance optimization: enabled")
    print(f"  • Context enrichment: auto-configured")
    
    # Test the logger with various scenarios
    logger.info("Application started", 
               component="main",
               auto_optimized=True)
    
    logger.info("Processing request",
               request_id="req_12345",
               user_id="user_67890",
               endpoint="/api/users")
    
    logger.warning("Performance threshold exceeded",
                  response_time_ms=1500,
                  threshold_ms=1000,
                  alert=True)
    
    # Show configuration details
    optimization_report = logger.get_optimization_report()
    framework_info = logger.get_framework_info()
    
    print(f"\n📊 Final Configuration Summary:")
    print(f"  • Detected app type: {framework_info.get('detected_app_type', 'unknown')}")
    print(f"  • Active formatter: {logger.formatter_type}")
    print(f"  • Async handlers: {logger.async_handlers}")
    print(f"  • Context enrichment: {logger.context_enricher is not None}")
    
    return logger


def demo_environment_adaptivity():
    """Demonstrate how configuration adapts to different environments."""
    
    print("\n=== Environment Adaptivity Demo ===")
    
    # Get current environment summary
    env_summary = get_environment_summary()
    
    print(f"🌍 Current Environment Analysis:")
    print(f"  • Environment Type: {env_summary['environment_type']}")
    print(f"  • Cloud Provider: {env_summary['cloud_provider']}")
    print(f"  • Container Runtime: {env_summary.get('container_runtime', 'none')}")
    print(f"  • Orchestrator: {env_summary.get('orchestrator', 'none')}")
    print(f"  • Platform: {env_summary['platform']}")
    
    # Show how configuration would change in different environments
    environments = ["development", "staging", "production"]
    
    for env in environments:
        print(f"\n⚙️  Configuration for {env.title()} Environment:")
        
        # Simulate environment detection results
        if env == "development":
            recommendations = {
                "log_level": "DEBUG",
                "console_logging": True,
                "file_logging": False,
                "formatter": "development"
            }
        elif env == "staging":
            recommendations = {
                "log_level": "INFO",
                "console_logging": True,
                "file_logging": True,
                "formatter": "structured"
            }
        else:  # production
            recommendations = {
                "log_level": "WARNING",
                "console_logging": False,
                "file_logging": True,
                "formatter": "production"
            }
        
        for key, value in recommendations.items():
            print(f"    • {key}: {value}")


def main():
    """Run all framework detection and auto-configuration demos."""
    
    print("🚀 MohFlow Framework Detection & Auto-Configuration Demo")
    print("=" * 65)
    
    # Run all demonstrations
    demo_basic_framework_detection()
    demo_intelligent_configuration()
    smart_logger = demo_smart_logger_factory()
    demo_framework_specific_configs()
    auto_logger = demo_auto_optimized_logger()
    demo_environment_adaptivity()
    
    print("\n" + "=" * 65)
    print("🎯 Key Benefits of Intelligent Auto-Configuration:")
    print("✓ Automatic framework detection (Flask, Django, FastAPI, etc.)")
    print("✓ Performance optimization based on app type")
    print("✓ Environment-aware configuration")
    print("✓ Zero-code setup for optimal logging")
    print("✓ Framework-specific integration tips")
    print("✓ Real-time optimization recommendations")
    
    print("\n🔧 Usage Patterns:")
    print("• MohflowLogger.smart() - Automatic detection and optimization")
    print("• MohflowLogger.auto_optimized() - Maximum intelligence with tracing")
    print("• logger.get_optimization_report() - Get configuration analysis")
    print("• logger.get_framework_info() - Get detected framework details")


if __name__ == "__main__":
    main()