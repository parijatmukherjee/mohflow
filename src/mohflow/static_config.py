"""
Static configuration data using dataclasses for immutable configuration.
These are compile-time constants and defaults that don't change during runtime.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum


class LogLevel(Enum):
    """Enumeration for log levels"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Environment(Enum):
    """Enumeration for deployment environments"""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class DefaultFormats:
    """Default formatting configurations"""

    JSON_FORMAT: str = "%(asctime)s %(level_name)s %(name)s %(message)s"
    TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"
    FIELD_MAPPINGS: Dict[str, str] = field(
        default_factory=lambda: {
            "asctime": "timestamp",
            "level_name": "level",
            "name": "service_name",
        }
    )


@dataclass(frozen=True)
class DefaultLimits:
    """Default limits and thresholds"""

    MAX_LOG_MESSAGE_SIZE: int = 32768  # 32KB
    MAX_BATCH_SIZE: int = 1000
    DEFAULT_TIMEOUT: int = 30  # seconds
    MAX_FILE_SIZE_MB: int = 100
    MAX_BACKUP_COUNT: int = 10
    RETRY_ATTEMPTS: int = 3
    RETRY_DELAY: float = 1.0  # seconds


@dataclass(frozen=True)
class DefaultPorts:
    """Default ports for various services"""

    LOKI: int = 3100
    ELASTICSEARCH: int = 9200
    LOGSTASH: int = 5044
    SYSLOG: int = 514


@dataclass(frozen=True)
class CloudProviders:
    """Cloud provider detection patterns"""

    AWS_METADATA_URL: str = "http://169.254.169.254/latest/meta-data/"
    GCP_METADATA_URL: str = (
        "http://metadata.google.internal/computeMetadata/v1/"
    )
    AZURE_METADATA_URL: str = "http://169.254.169.254/metadata/instance"

    AWS_ENV_VARS: Tuple[str, ...] = (
        "AWS_REGION",
        "AWS_AVAILABILITY_ZONE",
        "AWS_INSTANCE_ID",
    )
    GCP_ENV_VARS: Tuple[str, ...] = (
        "GCP_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "GCP_REGION",
    )
    AZURE_ENV_VARS: Tuple[str, ...] = (
        "AZURE_RESOURCE_GROUP",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_REGION",
    )


@dataclass(frozen=True)
class ContainerDetection:
    """Container and orchestrator detection patterns"""

    DOCKER_ENV_FILE: str = "/.dockerenv"
    KUBERNETES_SERVICE_HOST: str = "KUBERNETES_SERVICE_HOST"
    KUBERNETES_NAMESPACE_FILE: str = (
        "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    )

    DOCKER_ENV_VARS: Tuple[str, ...] = ("DOCKER_CONTAINER_ID", "HOSTNAME")
    K8S_ENV_VARS: Tuple[str, ...] = (
        "KUBERNETES_SERVICE_HOST",
        "KUBERNETES_SERVICE_PORT",
        "POD_NAME",
        "POD_NAMESPACE",
    )


@dataclass(frozen=True)
class ContextFields:
    """Standard context field names"""

    TIMESTAMP: str = "timestamp"
    LEVEL: str = "level"
    SERVICE_NAME: str = "service_name"
    ENVIRONMENT: str = "environment"
    REQUEST_ID: str = "request_id"
    CORRELATION_ID: str = "correlation_id"
    USER_ID: str = "user_id"
    SESSION_ID: str = "session_id"
    TRACE_ID: str = "trace_id"
    SPAN_ID: str = "span_id"

    # Infrastructure context
    HOST_NAME: str = "hostname"
    PROCESS_ID: str = "process_id"
    THREAD_ID: str = "thread_id"

    # Cloud context
    CLOUD_PROVIDER: str = "cloud_provider"
    CLOUD_REGION: str = "cloud_region"
    CLOUD_ZONE: str = "cloud_zone"
    INSTANCE_ID: str = "instance_id"

    # Container context
    CONTAINER_ID: str = "container_id"
    CONTAINER_NAME: str = "container_name"
    POD_NAME: str = "pod_name"
    NAMESPACE: str = "namespace"


@dataclass(frozen=True)
class ErrorCodes:
    """Standard error codes and messages"""

    CONFIGURATION_ERROR: str = "MOHFLOW_CONFIG_001"
    HANDLER_SETUP_ERROR: str = "MOHFLOW_HANDLER_002"
    NETWORK_ERROR: str = "MOHFLOW_NETWORK_003"
    FILE_PERMISSION_ERROR: str = "MOHFLOW_FILE_004"
    VALIDATION_ERROR: str = "MOHFLOW_VALIDATION_005"

    ERROR_MESSAGES: Dict[str, str] = field(
        default_factory=lambda: {
            "MOHFLOW_CONFIG_001": "Configuration validation failed",
            "MOHFLOW_HANDLER_002": "Handler setup failed",
            "MOHFLOW_NETWORK_003": "Network communication error",
            "MOHFLOW_FILE_004": "File system permission error",
            "MOHFLOW_VALIDATION_005": "Input validation error",
        }
    )


@dataclass(frozen=True)
class RegexPatterns:
    """Common regex patterns for validation and parsing"""

    LOG_LEVEL_PATTERN: str = r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"
    SERVICE_NAME_PATTERN: str = r"^[a-zA-Z][a-zA-Z0-9\-_]{0,62}$"
    URL_PATTERN: str = r"^https?://[^\s/$.?#].[^\s]*$"
    UUID_PATTERN: str = (
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    IPV4_PATTERN: str = (
        r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    )


@dataclass(frozen=True)
class DashboardTemplates:
    """Dashboard template configurations"""

    GRAFANA_DASHBOARD_VERSION: str = "1.0.0"
    GRAFANA_API_VERSION: str = "v1"

    # Common dashboard panels
    LOG_VOLUME_PANEL: str = "log_volume_over_time"
    ERROR_RATE_PANEL: str = "error_rate"
    SERVICE_HEALTH_PANEL: str = "service_health"
    TOP_ERRORS_PANEL: str = "top_errors"

    # Kibana dashboard settings
    KIBANA_VERSION: str = "8.0"
    INDEX_PATTERN: str = "mohflow-*"


@dataclass(frozen=True)
class SecurityConfig:
    """Security-related static configuration"""

    SENSITIVE_FIELDS: Tuple[str, ...] = (
        "password",
        "token",
        "key",
        "secret",
        "auth",
        "credential",
        "api_key",
        "access_token",
        "refresh_token",
        "jwt",
        "bearer",
        "authorization",
        "x-api-key",
        "private_key",
        "client_secret",
    )

    REDACTION_PLACEHOLDER: str = "[REDACTED]"
    MAX_FIELD_LENGTH: int = 1000  # Maximum length before truncation

    # Headers to sanitize
    SENSITIVE_HEADERS: Tuple[str, ...] = (
        "authorization",
        "x-api-key",
        "x-auth-token",
        "cookie",
        "x-csrf-token",
        "x-requested-with",
        "x-forwarded-for",
    )


# Singleton instances for easy access
DEFAULT_FORMATS = DefaultFormats()
DEFAULT_LIMITS = DefaultLimits()
DEFAULT_PORTS = DefaultPorts()
CLOUD_PROVIDERS = CloudProviders()
CONTAINER_DETECTION = ContainerDetection()
CONTEXT_FIELDS = ContextFields()
ERROR_CODES = ErrorCodes()
REGEX_PATTERNS = RegexPatterns()
DASHBOARD_TEMPLATES = DashboardTemplates()
SECURITY_CONFIG = SecurityConfig()


# Utility functions for common operations
def get_all_log_levels() -> List[str]:
    """Get list of all available log levels"""
    return [lvl.value for lvl in LogLevel]


def get_all_environments() -> List[str]:
    """Get list of all available environments"""
    return [env.value for env in Environment]


def is_valid_log_level(level: str) -> bool:
    """Check if log level is valid"""
    return level.upper() in [lvl.value for lvl in LogLevel]


def is_valid_environment(env: str) -> bool:
    """Check if environment is valid"""
    return env.lower() in [e.value for e in Environment]


def get_error_message(error_code: str) -> Optional[str]:
    """Get error message for given error code"""
    return ERROR_CODES.ERROR_MESSAGES.get(error_code)
