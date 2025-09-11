"""
Context enrichment for automatic metadata injection into log records.
Provides request correlation, user context, and system metadata.
"""

import os
import time
import uuid
import threading
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, field
from contextvars import ContextVar

from mohflow.static_config import CONTEXT_FIELDS


# Context variables for thread-safe context management
_request_context: ContextVar[Optional["RequestContext"]] = ContextVar(
    "request_context", default=None
)
_global_context: ContextVar[Dict[str, Any]] = ContextVar(
    "global_context", default={}
)


@dataclass
class RequestContext:
    """
    Request-scoped context information that gets included in all logs
    within the same request/operation boundary.
    """

    request_id: str
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    operation_name: Optional[str] = None
    start_time: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for log inclusion"""
        result = {
            CONTEXT_FIELDS.REQUEST_ID: self.request_id,
            CONTEXT_FIELDS.CORRELATION_ID: self.correlation_id,
            CONTEXT_FIELDS.USER_ID: self.user_id,
            CONTEXT_FIELDS.SESSION_ID: self.session_id,
            CONTEXT_FIELDS.TRACE_ID: self.trace_id,
            CONTEXT_FIELDS.SPAN_ID: self.span_id,
        }

        # Add operation name if present
        if self.operation_name:
            result["operation_name"] = self.operation_name

        # Add custom fields
        result.update(self.custom_fields)

        # Filter out None values
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class GlobalContext:
    """
    Global context information that persists across all requests.
    Includes system-level metadata and configuration.
    """

    service_name: str
    environment: str
    version: Optional[str] = None
    hostname: str = field(default_factory=lambda: os.uname().nodename)
    process_id: int = field(default_factory=os.getpid)
    thread_id: int = field(default_factory=lambda: threading.get_ident())

    # Infrastructure context
    cloud_provider: Optional[str] = None
    cloud_region: Optional[str] = None
    cloud_zone: Optional[str] = None
    instance_id: Optional[str] = None

    # Container context
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    pod_name: Optional[str] = None
    namespace: Optional[str] = None

    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for log inclusion"""
        result = {
            CONTEXT_FIELDS.SERVICE_NAME: self.service_name,
            CONTEXT_FIELDS.ENVIRONMENT: self.environment,
            CONTEXT_FIELDS.HOST_NAME: self.hostname,
            CONTEXT_FIELDS.PROCESS_ID: self.process_id,
            CONTEXT_FIELDS.THREAD_ID: self.thread_id,
        }

        # Add optional fields
        if self.version:
            result["version"] = self.version
        if self.cloud_provider:
            result[CONTEXT_FIELDS.CLOUD_PROVIDER] = self.cloud_provider
        if self.cloud_region:
            result[CONTEXT_FIELDS.CLOUD_REGION] = self.cloud_region
        if self.cloud_zone:
            result[CONTEXT_FIELDS.CLOUD_ZONE] = self.cloud_zone
        if self.instance_id:
            result[CONTEXT_FIELDS.INSTANCE_ID] = self.instance_id
        if self.container_id:
            result[CONTEXT_FIELDS.CONTAINER_ID] = self.container_id
        if self.container_name:
            result[CONTEXT_FIELDS.CONTAINER_NAME] = self.container_name
        if self.pod_name:
            result[CONTEXT_FIELDS.POD_NAME] = self.pod_name
        if self.namespace:
            result[CONTEXT_FIELDS.NAMESPACE] = self.namespace

        # Add custom fields
        result.update(self.custom_fields)

        return result


class ContextEnricher:
    """
    Automatic context enrichment for log records.
    Injects metadata from request, global context, and system info.
    """

    def __init__(
        self,
        include_timestamp: bool = True,
        include_system_info: bool = True,
        include_request_context: bool = True,
        include_global_context: bool = True,
        custom_enrichers: Optional[Dict[str, Callable[[], Any]]] = None,
    ):
        """
        Initialize context enricher.

        Args:
            include_timestamp: Include standardized timestamp
            include_system_info: Include system-level information
            include_request_context: Include request-scoped context
            include_global_context: Include global context
            custom_enrichers: Custom field enrichers (field_name -> callable)
        """
        self.include_timestamp = include_timestamp
        self.include_system_info = include_system_info
        self.include_request_context = include_request_context
        self.include_global_context = include_global_context
        self.custom_enrichers = custom_enrichers or {}

        # Cache system info to avoid repeated calls
        self._system_info_cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 300  # 5 minutes cache TTL

    def enrich_log_record(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich log record with context information.

        Args:
            extra: Existing extra fields from log call

        Returns:
            Enriched extra fields dictionary
        """
        enriched = extra.copy()

        self._add_timestamp_if_enabled(enriched)
        self._add_system_info_if_enabled(enriched)
        self._add_global_context_if_enabled(enriched)
        self._add_request_context_if_enabled(enriched)
        self._add_custom_enrichers(enriched)

        return enriched

    def _add_timestamp_if_enabled(self, enriched: Dict[str, Any]):
        """Add timestamp if enabled"""
        if self.include_timestamp:
            enriched[CONTEXT_FIELDS.TIMESTAMP] = self._get_timestamp()

    def _add_system_info_if_enabled(self, enriched: Dict[str, Any]):
        """Add system info if enabled"""
        if self.include_system_info:
            enriched.update(self._get_system_info())

    def _add_global_context_if_enabled(self, enriched: Dict[str, Any]):
        """Add global context if enabled"""
        if self.include_global_context:
            global_ctx = _global_context.get()
            if global_ctx:
                enriched.update(global_ctx)

    def _add_request_context_if_enabled(self, enriched: Dict[str, Any]):
        """Add request context if enabled"""
        if self.include_request_context:
            request_ctx = _request_context.get()
            if request_ctx:
                enriched.update(request_ctx.to_dict())

    def _add_custom_enrichers(self, enriched: Dict[str, Any]):
        """Add custom enrichers"""
        for field_name, enricher_func in self.custom_enrichers.items():
            try:
                value = enricher_func()
                if value is not None:
                    enriched[field_name] = value
            except Exception as e:
                # Log enricher errors but don't fail the logging operation
                enriched[f"{field_name}_error"] = str(e)

    def _get_timestamp(self) -> str:
        """Get ISO formatted timestamp"""
        return datetime.now(timezone.utc).isoformat()

    def _get_system_info(self) -> Dict[str, Any]:
        """Get cached system information"""
        current_time = time.time()

        # Return cached info if still valid
        if (
            self._system_info_cache is not None
            and current_time - self._cache_time < self._cache_ttl
        ):
            return self._system_info_cache

        # Refresh system info cache
        self._system_info_cache = {
            CONTEXT_FIELDS.PROCESS_ID: os.getpid(),
            CONTEXT_FIELDS.THREAD_ID: threading.get_ident(),
            CONTEXT_FIELDS.HOST_NAME: os.uname().nodename,
        }
        self._cache_time = current_time

        return self._system_info_cache

    def add_custom_enricher(
        self, field_name: str, enricher_func: Callable[[], Any]
    ):
        """Add a custom enricher function"""
        self.custom_enrichers[field_name] = enricher_func

    def remove_custom_enricher(self, field_name: str):
        """Remove a custom enricher function"""
        self.custom_enrichers.pop(field_name, None)


# Context management functions
def set_request_context(context: RequestContext):
    """Set the current request context"""
    _request_context.set(context)


def get_request_context() -> Optional[RequestContext]:
    """Get the current request context"""
    return _request_context.get()


def clear_request_context():
    """Clear the current request context"""
    _request_context.set(None)


def set_global_context(**fields):
    """Set global context fields"""
    current = _global_context.get({})
    updated = current.copy()
    updated.update(fields)
    _global_context.set(updated)


def get_global_context() -> Dict[str, Any]:
    """Get the current global context"""
    return _global_context.get({})


def clear_global_context():
    """Clear the global context"""
    _global_context.set({})


def update_request_context(**fields):
    """Update fields in the current request context"""
    current_ctx = _request_context.get()
    if current_ctx:
        current_ctx.custom_fields.update(fields)


# Context managers for automatic context management
class RequestContextManager:
    """Context manager for request-scoped context"""

    def __init__(
        self,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        operation_name: Optional[str] = None,
        **custom_fields,
    ):
        """
        Initialize request context manager.

        Args:
            request_id: Request identifier (auto-generated if None)
            correlation_id: Correlation identifier
            user_id: User identifier
            session_id: Session identifier
            operation_name: Name of the operation being performed
            **custom_fields: Additional custom fields
        """
        self.request_id = request_id or str(uuid.uuid4())
        self.correlation_id = correlation_id
        self.user_id = user_id
        self.session_id = session_id
        self.operation_name = operation_name
        self.custom_fields = custom_fields
        self._previous_context: Optional[RequestContext] = None

    def __enter__(self) -> RequestContext:
        """Enter request context"""
        # Save previous context
        self._previous_context = _request_context.get()

        # Set new context
        context = RequestContext(
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            user_id=self.user_id,
            session_id=self.session_id,
            operation_name=self.operation_name,
            custom_fields=self.custom_fields,
        )

        _request_context.set(context)
        return context

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit request context"""
        # Restore previous context
        _request_context.set(self._previous_context)


class GlobalContextManager:
    """Context manager for global context fields"""

    def __init__(self, **fields):
        """
        Initialize global context manager.

        Args:
            **fields: Global context fields to set
        """
        self.fields = fields
        self._previous_context: Dict[str, Any] = {}

    def __enter__(self):
        """Enter global context"""
        # Save current context
        self._previous_context = _global_context.get({})

        # Merge with new fields
        updated = self._previous_context.copy()
        updated.update(self.fields)
        _global_context.set(updated)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit global context"""
        # Restore previous context
        _global_context.set(self._previous_context)


# Decorators for automatic context management
def with_request_context(
    request_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    operation_name: Optional[str] = None,
    **custom_fields,
):
    """
    Decorator to automatically set request context for a function.

    Args:
        request_id: Request identifier (auto-generated if None)
        correlation_id: Correlation identifier
        user_id: User identifier
        session_id: Session identifier
        operation_name: Operation name (defaults to function name)
        **custom_fields: Additional custom fields
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            with RequestContextManager(
                request_id=request_id,
                correlation_id=correlation_id,
                user_id=user_id,
                session_id=session_id,
                operation_name=op_name,
                **custom_fields,
            ):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def with_global_context(**fields):
    """
    Decorator to temporarily set global context fields for a function.

    Args:
        **fields: Global context fields to set
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            with GlobalContextManager(**fields):
                return func(*args, **kwargs)

        return wrapper

    return decorator
