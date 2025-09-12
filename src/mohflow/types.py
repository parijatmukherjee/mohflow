"""
Type definitions and protocols for MohFlow.

This module provides comprehensive type hints and protocols to ensure
type safety across the MohFlow logging library.
"""

from typing import (
    Any, Dict, List, Optional, Union, Protocol, TypeVar, Generic,
    Callable, Awaitable, Mapping, Sequence, TYPE_CHECKING,
    runtime_checkable, Literal
)
from typing_extensions import TypedDict, NotRequired
import logging
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from mohflow.logger.base import MohflowLogger
    from mohflow.framework_detection import FrameworkInfo, ApplicationInfo
    from mohflow.auto_config import EnvironmentInfo

# Type Variables
T = TypeVar('T')
LogRecordT = TypeVar('LogRecordT', bound=logging.LogRecord)

# Literal Types for Configuration
LogLevel = Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
FormatterType = Literal['fast', 'structured', 'production', 'development']
ExporterType = Literal['console', 'jaeger', 'otlp']
EnvironmentType = Literal['development', 'staging', 'production']
CloudProvider = Literal['aws', 'gcp', 'azure', 'local']
ContainerRuntime = Literal['docker', 'containerd', 'podman']
Orchestrator = Literal['kubernetes', 'docker-swarm', 'nomad']


class LogLevelEnum(Enum):
    """Enum for log levels with proper typing."""
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'


# Configuration Types
class BaseConfig(TypedDict):
    """Base configuration dictionary type."""
    service_name: str
    environment: NotRequired[EnvironmentType]
    log_level: NotRequired[LogLevel]


class LogConfig(BaseConfig):
    """Complete logging configuration type."""
    console_logging: NotRequired[bool]
    file_logging: NotRequired[bool]
    log_file_path: NotRequired[Optional[str]]
    loki_url: NotRequired[Optional[str]]
    formatter_type: NotRequired[FormatterType]
    async_handlers: NotRequired[bool]
    enable_context_enrichment: NotRequired[bool]
    enable_sensitive_data_filter: NotRequired[bool]
    enable_auto_config: NotRequired[bool]


class OpenTelemetryConfig(TypedDict):
    """OpenTelemetry configuration type."""
    enable_otel: NotRequired[bool]
    otel_service_version: NotRequired[str]
    otel_exporter_type: NotRequired[ExporterType]
    otel_endpoint: NotRequired[Optional[str]]
    otel_propagators: NotRequired[Optional[List[str]]]


class ContextEnrichmentConfig(TypedDict):
    """Context enrichment configuration type."""
    enabled: NotRequired[bool]
    include_timestamp: NotRequired[bool]
    include_system_info: NotRequired[bool]
    include_request_context: NotRequired[bool]
    include_request_id: NotRequired[bool]
    custom_fields: NotRequired[Dict[str, Any]]


class HandlerConfig(TypedDict):
    """Handler configuration type."""
    batch_size: NotRequired[int]
    timeout: NotRequired[int]
    rotation: NotRequired[bool]
    max_size_mb: NotRequired[int]
    backup_count: NotRequired[int]


class CompleteConfig(LogConfig, OpenTelemetryConfig):
    """Complete MohFlow configuration combining all options."""
    context_enrichment: NotRequired[ContextEnrichmentConfig]
    handlers: NotRequired[Dict[str, HandlerConfig]]


# Framework Detection Types
class FrameworkDetectionResult(TypedDict):
    """Result of framework detection."""
    app_type: str
    deployment_type: str
    uses_async: bool
    frameworks: List[Dict[str, Any]]
    capabilities: Dict[str, bool]


class OptimizationReport(TypedDict):
    """Logger optimization report type."""
    current_config: Dict[str, Any]
    environment: Dict[str, Any]
    framework_recommendations: Dict[str, Any]
    optimization_tips: List[str]


# Protocol Definitions
@runtime_checkable
class LogFormatter(Protocol):
    """Protocol for log formatters."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record."""
        ...


@runtime_checkable
class LogHandler(Protocol):
    """Protocol for log handlers."""
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record."""
        ...
    
    def flush(self) -> None:
        """Flush pending log records."""
        ...
    
    def close(self) -> None:
        """Close the handler."""
        ...


@runtime_checkable
class AsyncLogHandler(Protocol):
    """Protocol for async-safe log handlers."""
    
    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record asynchronously."""
        ...
    
    def flush(self) -> None:
        """Flush pending log records."""
        ...
    
    def close(self) -> None:
        """Close the handler and cleanup."""
        ...


@runtime_checkable
class ContextEnricher(Protocol):
    """Protocol for context enrichers."""
    
    def enrich_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich dictionary with additional context."""
        ...
    
    def enrich_record(self, record: logging.LogRecord) -> logging.LogRecord:
        """Enrich log record with additional context."""
        ...


@runtime_checkable
class DataFilter(Protocol):
    """Protocol for data filters (e.g., sensitive data)."""
    
    def filter_log_record(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter log record data."""
        ...


@runtime_checkable
class ConfigLoader(Protocol):
    """Protocol for configuration loaders."""
    
    def load_config(self, **kwargs: Any) -> Dict[str, Any]:
        """Load configuration from various sources."""
        ...
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration."""
        ...


@runtime_checkable
class FrameworkDetector(Protocol):
    """Protocol for framework detection."""
    
    def detect_frameworks(self, force_refresh: bool = False) -> List[Any]:
        """Detect frameworks in use."""
        ...
    
    def detect_application_type(self) -> Any:
        """Detect application type and characteristics."""
        ...
    
    def get_optimized_config(self) -> Dict[str, Any]:
        """Get optimized configuration."""
        ...


@runtime_checkable
class AutoConfigurator(Protocol):
    """Protocol for auto-configuration."""
    
    def detect_environment(self) -> Any:
        """Detect deployment environment."""
        ...
    
    def auto_configure(self, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply auto-configuration."""
        ...
    
    def get_intelligent_config(
        self, 
        base_config: Dict[str, Any], 
        service_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get intelligent configuration with framework detection."""
        ...


# Generic Types for Extensibility
class Enricher(Protocol, Generic[T]):
    """Generic enricher protocol."""
    
    def enrich(self, data: T) -> T:
        """Enrich data of type T."""
        ...


class Filter(Protocol, Generic[T]):
    """Generic filter protocol."""
    
    def filter(self, data: T) -> T:
        """Filter data of type T."""
        ...


class Processor(Protocol, Generic[T]):
    """Generic processor protocol."""
    
    def process(self, data: T) -> T:
        """Process data of type T."""
        ...


# Function Type Aliases
LogEnricher = Callable[[Dict[str, Any]], Dict[str, Any]]
LogFilter = Callable[[Dict[str, Any]], Dict[str, Any]]
LogProcessor = Callable[[logging.LogRecord], logging.LogRecord]
AsyncLogProcessor = Callable[[logging.LogRecord], Awaitable[logging.LogRecord]]

# Configuration Builder Types
ConfigBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]
ConfigValidator = Callable[[Dict[str, Any]], bool]
ConfigTransformer = Callable[[Dict[str, Any]], Dict[str, Any]]

# Middleware Types
LoggingMiddleware = Callable[[logging.LogRecord], Optional[logging.LogRecord]]
AsyncLoggingMiddleware = Callable[[logging.LogRecord], Awaitable[Optional[logging.LogRecord]]]

# Factory Types
LoggerFactory = Callable[..., 'MohflowLogger']
FormatterFactory = Callable[..., LogFormatter]
HandlerFactory = Callable[..., LogHandler]

# Error Types
class MohFlowError(Exception):
    """Base exception for MohFlow errors."""
    
    def __init__(self, message: str, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class ConfigurationError(MohFlowError):
    """Configuration-related errors."""
    pass


class HandlerError(MohFlowError):
    """Handler-related errors."""
    pass


class FormatterError(MohFlowError):
    """Formatter-related errors."""
    pass


class DetectionError(MohFlowError):
    """Framework/environment detection errors."""
    pass


# Path Types
LogFilePath = Union[str, Path]
ConfigFilePath = Union[str, Path]

# Network Types
class NetworkConfig(TypedDict):
    """Network configuration for remote handlers."""
    host: str
    port: int
    timeout: NotRequired[float]
    ssl: NotRequired[bool]
    headers: NotRequired[Dict[str, str]]


# Validation Types
class ValidationResult(TypedDict):
    """Result of configuration validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    recommendations: NotRequired[List[str]]


# Performance Types
class PerformanceMetrics(TypedDict):
    """Performance metrics for logging operations."""
    messages_per_second: float
    avg_latency_ms: float
    p99_latency_ms: float
    memory_usage_mb: float
    error_rate: float


# Tracing Types
class TraceContext(TypedDict):
    """Trace context information."""
    trace_id: NotRequired[Optional[str]]
    span_id: NotRequired[Optional[str]]
    trace_flags: NotRequired[Optional[str]]
    trace_state: NotRequired[Optional[str]]
    baggage: NotRequired[Optional[Dict[str, Any]]]
    service_name: NotRequired[Optional[str]]
    service_version: NotRequired[Optional[str]]


# Serialization Types
SerializableValue = Union[str, int, float, bool, None, List['SerializableValue'], Dict[str, 'SerializableValue']]
LogData = Dict[str, SerializableValue]

# Callback Types
LogCallback = Callable[[logging.LogRecord], None]
AsyncLogCallback = Callable[[logging.LogRecord], Awaitable[None]]
ErrorCallback = Callable[[Exception, logging.LogRecord], None]

# Context Manager Types
@runtime_checkable
class LogContextManager(Protocol):
    """Protocol for logging context managers."""
    
    def __enter__(self) -> Any:
        """Enter the context."""
        ...
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[bool]:
        """Exit the context."""
        ...


@runtime_checkable
class AsyncLogContextManager(Protocol):
    """Protocol for async logging context managers."""
    
    async def __aenter__(self) -> Any:
        """Async enter the context."""
        ...
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[bool]:
        """Async exit the context."""
        ...


# Plugin Types
class PluginConfig(TypedDict):
    """Plugin configuration."""
    enabled: bool
    config: NotRequired[Dict[str, Any]]


@runtime_checkable
class LoggingPlugin(Protocol):
    """Protocol for MohFlow plugins."""
    
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize the plugin."""
        ...
    
    def process_record(self, record: logging.LogRecord) -> Optional[logging.LogRecord]:
        """Process a log record."""
        ...
    
    def cleanup(self) -> None:
        """Cleanup plugin resources."""
        ...


# Registry Types
PluginRegistry = Dict[str, LoggingPlugin]
FormatterRegistry = Dict[str, LogFormatter]
HandlerRegistry = Dict[str, LogHandler]

# Utility Types for Type Guards
def is_log_level(value: str) -> bool:
    """Type guard for log levels."""
    return value.upper() in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}


def is_formatter_type(value: str) -> bool:
    """Type guard for formatter types."""
    return value in {'fast', 'structured', 'production', 'development'}


def is_exporter_type(value: str) -> bool:
    """Type guard for exporter types."""
    return value in {'console', 'jaeger', 'otlp'}


# Advanced Type Definitions for Future Extensions
@dataclass
class TypeSafeLogRecord:
    """Type-safe wrapper for log records."""
    level: LogLevel
    message: str
    timestamp: float
    logger_name: str
    context: Dict[str, SerializableValue]
    trace_context: Optional[TraceContext] = None
    
    def to_dict(self) -> LogData:
        """Convert to dictionary."""
        return {
            'level': self.level,
            'message': self.message,
            'timestamp': self.timestamp,
            'logger_name': self.logger_name,
            'context': self.context,
            'trace_context': self.trace_context
        }


# Export all public types
__all__ = [
    # Basic types
    'LogLevel', 'FormatterType', 'ExporterType', 'EnvironmentType',
    'CloudProvider', 'ContainerRuntime', 'Orchestrator',
    
    # Configuration types
    'BaseConfig', 'LogConfig', 'OpenTelemetryConfig', 'ContextEnrichmentConfig',
    'HandlerConfig', 'CompleteConfig',
    
    # Result types
    'FrameworkDetectionResult', 'OptimizationReport', 'ValidationResult',
    'PerformanceMetrics', 'TraceContext',
    
    # Protocol types
    'LogFormatter', 'LogHandler', 'AsyncLogHandler', 'ContextEnricher',
    'DataFilter', 'ConfigLoader', 'FrameworkDetector', 'AutoConfigurator',
    'LogContextManager', 'AsyncLogContextManager', 'LoggingPlugin',
    
    # Generic types
    'Enricher', 'Filter', 'Processor',
    
    # Function types
    'LogEnricher', 'LogFilter', 'LogProcessor', 'AsyncLogProcessor',
    'ConfigBuilder', 'ConfigValidator', 'ConfigTransformer',
    'LoggingMiddleware', 'AsyncLoggingMiddleware',
    
    # Factory types
    'LoggerFactory', 'FormatterFactory', 'HandlerFactory',
    
    # Exception types
    'MohFlowError', 'ConfigurationError', 'HandlerError',
    'FormatterError', 'DetectionError',
    
    # Utility types
    'SerializableValue', 'LogData', 'LogFilePath', 'ConfigFilePath',
    'NetworkConfig', 'PluginConfig', 'TypeSafeLogRecord',
    
    # Type guards
    'is_log_level', 'is_formatter_type', 'is_exporter_type',
    
    # Registries
    'PluginRegistry', 'FormatterRegistry', 'HandlerRegistry',
]