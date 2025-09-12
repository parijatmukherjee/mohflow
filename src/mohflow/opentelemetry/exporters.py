"""
OpenTelemetry exporters configuration for various backends.

This module provides convenient setup functions for popular tracing backends
like Jaeger, OTLP, and console output.
"""

from typing import Dict, Any, Optional
import os

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import (
        Resource,
        SERVICE_NAME,
        SERVICE_VERSION,
    )

    HAS_OPENTELEMETRY = True
except ImportError:
    HAS_OPENTELEMETRY = False


def setup_console_exporter(
    service_name: str,
    service_version: str = "1.0.0",
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Setup console exporter for debugging and development.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        resource_attributes: Additional resource attributes

    Returns:
        True if setup successful, False otherwise
    """
    if not HAS_OPENTELEMETRY:
        return False

    try:
        from opentelemetry.exporter.console import ConsoleSpanExporter

        # Create resource
        attributes = {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }
        if resource_attributes:
            attributes.update(resource_attributes)

        resource = Resource.create(attributes)

        # Setup tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Add console exporter
        console_exporter = ConsoleSpanExporter()
        span_processor = BatchSpanProcessor(console_exporter)
        tracer_provider.add_span_processor(span_processor)

        return True

    except ImportError:
        return False
    except Exception:
        return False


def setup_jaeger_exporter(
    service_name: str,
    service_version: str = "1.0.0",
    jaeger_endpoint: Optional[str] = None,
    agent_host: str = "localhost",
    agent_port: int = 6831,
    collector_endpoint: Optional[str] = None,
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Setup Jaeger exporter for distributed tracing.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        jaeger_endpoint: Jaeger collector endpoint URL
        agent_host: Jaeger agent host (for UDP transport)
        agent_port: Jaeger agent port (for UDP transport)
        collector_endpoint: Jaeger collector HTTP endpoint
        resource_attributes: Additional resource attributes

    Returns:
        True if setup successful, False otherwise
    """
    if not HAS_OPENTELEMETRY:
        return False

    try:
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter

        # Create resource
        attributes = {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }
        if resource_attributes:
            attributes.update(resource_attributes)

        resource = Resource.create(attributes)

        # Setup tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Configure Jaeger exporter
        if collector_endpoint or jaeger_endpoint:
            # Use HTTP collector
            endpoint = collector_endpoint or jaeger_endpoint
            jaeger_exporter = JaegerExporter(
                collector_endpoint=endpoint,
            )
        else:
            # Use UDP agent
            jaeger_exporter = JaegerExporter(
                agent_host_name=agent_host,
                agent_port=agent_port,
            )

        # Add Jaeger exporter
        span_processor = BatchSpanProcessor(jaeger_exporter)
        tracer_provider.add_span_processor(span_processor)

        return True

    except ImportError:
        return False
    except Exception:
        return False


def setup_otlp_exporter(
    service_name: str,
    service_version: str = "1.0.0",
    otlp_endpoint: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    insecure: bool = False,
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Setup OTLP (OpenTelemetry Protocol) exporter.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        otlp_endpoint: OTLP endpoint URL
        headers: Additional headers for authentication
        insecure: Use insecure connection
        resource_attributes: Additional resource attributes

    Returns:
        True if setup successful, False otherwise
    """
    if not HAS_OPENTELEMETRY:
        return False

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        # Create resource
        attributes = {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }
        if resource_attributes:
            attributes.update(resource_attributes)

        resource = Resource.create(attributes)

        # Setup tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Get endpoint from environment or parameter
        endpoint = otlp_endpoint or os.getenv(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
        )

        if not endpoint:
            # Default to localhost
            endpoint = (
                "http://localhost:4317"
                if not insecure
                else "http://localhost:4317"
            )

        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=headers,
            insecure=insecure,
        )

        # Add OTLP exporter
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)

        return True

    except ImportError:
        return False
    except Exception:
        return False


def setup_multi_exporter(
    service_name: str,
    service_version: str = "1.0.0",
    exporters: Optional[list] = None,
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Setup multiple exporters simultaneously.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        exporters: List of exporter configurations
        resource_attributes: Additional resource attributes

    Example:
        exporters = [
            {"type": "console"},
            {"type": "jaeger", "agent_host": "jaeger", "agent_port": 6831},
            {"type": "otlp", "endpoint": "http://otel-collector:4317"}
        ]

    Returns:
        True if at least one exporter was setup successfully, False otherwise
    """
    if not HAS_OPENTELEMETRY or not exporters:
        return False

    try:
        # Create resource
        attributes = {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }
        if resource_attributes:
            attributes.update(resource_attributes)

        resource = Resource.create(attributes)

        # Setup tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        success_count = 0

        for exporter_config in exporters:
            exporter_type = exporter_config.get("type")

            try:
                if exporter_type == "console":
                    from opentelemetry.exporter.console import (
                        ConsoleSpanExporter,
                    )

                    exporter = ConsoleSpanExporter()

                elif exporter_type == "jaeger":
                    from opentelemetry.exporter.jaeger.thrift import (
                        JaegerExporter,
                    )

                    agent_host = exporter_config.get("agent_host", "localhost")
                    agent_port = exporter_config.get("agent_port", 6831)
                    collector_endpoint = exporter_config.get(
                        "collector_endpoint"
                    )

                    if collector_endpoint:
                        exporter = JaegerExporter(
                            collector_endpoint=collector_endpoint
                        )
                    else:
                        exporter = JaegerExporter(
                            agent_host_name=agent_host,
                            agent_port=agent_port,
                        )

                elif exporter_type == "otlp":
                    from opentelemetry.exporter.otlp.proto.grpc import (
                        trace_exporter,
                    )

                    OTLPSpanExporter = trace_exporter.OTLPSpanExporter

                    endpoint = exporter_config.get(
                        "endpoint", "http://localhost:4317"
                    )
                    headers = exporter_config.get("headers")
                    insecure = exporter_config.get("insecure", False)

                    exporter = OTLPSpanExporter(
                        endpoint=endpoint,
                        headers=headers,
                        insecure=insecure,
                    )

                else:
                    continue  # Skip unknown exporter types

                # Add span processor for this exporter
                span_processor = BatchSpanProcessor(exporter)
                tracer_provider.add_span_processor(span_processor)
                success_count += 1

            except ImportError:
                continue  # Skip if exporter not available
            except Exception:
                continue  # Skip if exporter setup failed

        return success_count > 0

    except Exception:
        return False


def setup_exporter_from_env(
    service_name: str,
    service_version: str = "1.0.0",
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Setup exporter based on environment variables.

    Supports standard OpenTelemetry environment variables:
    - OTEL_TRACES_EXPORTER: Exporter type ("console", "jaeger", "otlp")
    - OTEL_EXPORTER_JAEGER_AGENT_HOST: Jaeger agent host
    - OTEL_EXPORTER_JAEGER_AGENT_PORT: Jaeger agent port
    - OTEL_EXPORTER_JAEGER_ENDPOINT: Jaeger collector endpoint
    - OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: OTLP endpoint
    - OTEL_EXPORTER_OTLP_TRACES_HEADERS: OTLP headers

    Args:
        service_name: Name of the service
        service_version: Version of the service
        resource_attributes: Additional resource attributes

    Returns:
        True if setup successful, False otherwise
    """
    exporter_type = os.getenv("OTEL_TRACES_EXPORTER", "console").lower()

    if exporter_type == "console":
        return setup_console_exporter(
            service_name, service_version, resource_attributes
        )

    elif exporter_type == "jaeger":
        jaeger_endpoint = os.getenv("OTEL_EXPORTER_JAEGER_ENDPOINT")
        agent_host = os.getenv("OTEL_EXPORTER_JAEGER_AGENT_HOST", "localhost")
        agent_port = int(os.getenv("OTEL_EXPORTER_JAEGER_AGENT_PORT", "6831"))

        return setup_jaeger_exporter(
            service_name=service_name,
            service_version=service_version,
            jaeger_endpoint=jaeger_endpoint,
            agent_host=agent_host,
            agent_port=agent_port,
            resource_attributes=resource_attributes,
        )

    elif exporter_type == "otlp":
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        headers_str = os.getenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS")

        headers = None
        if headers_str:
            # Parse headers string like "key1=value1,key2=value2"
            try:
                headers = {}
                for pair in headers_str.split(","):
                    key, value = pair.split("=", 1)
                    headers[key.strip()] = value.strip()
            except Exception:
                headers = None

        return setup_otlp_exporter(
            service_name=service_name,
            service_version=service_version,
            otlp_endpoint=otlp_endpoint,
            headers=headers,
            resource_attributes=resource_attributes,
        )

    else:
        # Unknown exporter type, fallback to console
        return setup_console_exporter(
            service_name, service_version, resource_attributes
        )
