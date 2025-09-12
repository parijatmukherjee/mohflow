"""
Request-scoped and thread-local context management for MohFlow.

This module provides advanced context management capabilities including:
- Request-scoped context that persists across log calls within a request
- Thread-local context for multi-threaded applications
- Context chaining and temporary context overlays
- Automatic context cleanup and lifecycle management
"""

import threading
import contextvars
from typing import Dict, Any, Optional, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import uuid


# Context variables for async-safe storage
_request_context: contextvars.ContextVar[Dict[str, Any]] = (
    contextvars.ContextVar("request_context", default={})
)
_thread_context: contextvars.ContextVar[Dict[str, Any]] = (
    contextvars.ContextVar("thread_context", default={})
)
_temporary_context: contextvars.ContextVar[Dict[str, Any]] = (
    contextvars.ContextVar("temporary_context", default={})
)


@dataclass
class ContextScope:
    """Represents a context scope with metadata."""

    scope_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    scope_type: str = "unknown"
    created_at: datetime = field(default_factory=datetime.now)
    parent_scope_id: Optional[str] = None
    context_data: Dict[str, Any] = field(default_factory=dict)


class ScopedContextManager:
    """
    Advanced context management for MohFlow logging.

    Provides request-scoped, thread-local, and temporary context management
    with support for context chaining and automatic cleanup.
    """

    def __init__(self):
        """Initialize the context manager."""
        self._thread_local = threading.local()
        self._global_context: Dict[str, Any] = {}
        self._context_stack: Dict[str, ContextScope] = {}

    def set_global_context(self, **kwargs: Any) -> None:
        """
        Set global context that applies to all log messages.

        Args:
            **kwargs: Context key-value pairs to set globally
        """
        self._global_context.update(kwargs)

    def get_global_context(self) -> Dict[str, Any]:
        """Get the current global context."""
        return self._global_context.copy()

    def clear_global_context(self) -> None:
        """Clear all global context."""
        self._global_context.clear()

    @contextmanager
    def request_context(self, **kwargs: Any) -> Generator[str, None, None]:
        """
        Context manager for request-scoped logging context.

        Usage:
            with logger_context.request_context(
                request_id="123", user_id="user456"
            ):
                logger.info("Processing request")  # Includes request context

        Args:
            **kwargs: Context key-value pairs for this request

        Yields:
            str: Unique scope ID for this request context
        """
        scope = ContextScope(scope_type="request", context_data=kwargs)

        # Store current request context
        current_context = _request_context.get({})

        try:
            # Set new request context (merged with current)
            merged_context = {**current_context, **kwargs}
            _request_context.set(merged_context)
            self._context_stack[scope.scope_id] = scope

            yield scope.scope_id

        finally:
            # Restore previous request context
            _request_context.set(current_context)
            self._context_stack.pop(scope.scope_id, None)

    @contextmanager
    def thread_context(self, **kwargs: Any) -> Generator[str, None, None]:
        """
        Context manager for thread-local logging context.

        Usage:
            with logger_context.thread_context(worker_id="worker_1"):
                logger.info("Thread processing")  # Includes thread context

        Args:
            **kwargs: Context key-value pairs for this thread

        Yields:
            str: Unique scope ID for this thread context
        """
        scope = ContextScope(scope_type="thread", context_data=kwargs)

        # Store current thread context
        current_context = _thread_context.get({})

        try:
            # Set new thread context (merged with current)
            merged_context = {**current_context, **kwargs}
            _thread_context.set(merged_context)
            self._context_stack[scope.scope_id] = scope

            yield scope.scope_id

        finally:
            # Restore previous thread context
            _thread_context.set(current_context)
            self._context_stack.pop(scope.scope_id, None)

    @contextmanager
    def temporary_context(self, **kwargs: Any) -> Generator[str, None, None]:
        """
        Context manager for temporary logging context overlay.

        Usage:
            logger.with_context(component="auth").info("Login attempt")
            # OR
            with logger_context.temporary_context(operation="validate"):
                logger.info("Validating user")  # Includes temporary context

        Args:
            **kwargs: Context key-value pairs for temporary use

        Yields:
            str: Unique scope ID for this temporary context
        """
        scope = ContextScope(scope_type="temporary", context_data=kwargs)

        # Store current temporary context
        current_context = _temporary_context.get({})

        try:
            # Set new temporary context (merged with current)
            merged_context = {**current_context, **kwargs}
            _temporary_context.set(merged_context)
            self._context_stack[scope.scope_id] = scope

            yield scope.scope_id

        finally:
            # Restore previous temporary context
            _temporary_context.set(current_context)
            self._context_stack.pop(scope.scope_id, None)

    def get_current_context(self) -> Dict[str, Any]:
        """
        Get the complete current context from all scopes.

        Returns:
            Dict[str, Any]: Merged context from all active scopes
        """
        # Start with global context
        context = self._global_context.copy()

        # Add thread-local context
        context.update(_thread_context.get({}))

        # Add request-scoped context
        context.update(_request_context.get({}))

        # Add temporary context (highest priority)
        context.update(_temporary_context.get({}))

        return context

    def get_context_info(self) -> Dict[str, Any]:
        """
        Get information about active context scopes.

        Returns:
            Dict containing active scopes and their metadata
        """
        active_scopes = []

        for scope_id, scope in self._context_stack.items():
            active_scopes.append(
                {
                    "scope_id": scope_id,
                    "scope_type": scope.scope_type,
                    "created_at": scope.created_at.isoformat(),
                    "context_keys": list(scope.context_data.keys()),
                    "context_size": len(scope.context_data),
                }
            )

        return {
            "global_context_keys": list(self._global_context.keys()),
            "active_scopes": active_scopes,
            "total_context_keys": len(self.get_current_context()),
            "request_context_active": bool(_request_context.get({})),
            "thread_context_active": bool(_thread_context.get({})),
            "temporary_context_active": bool(_temporary_context.get({})),
        }

    def clear_all_context(self) -> None:
        """Clear all context from all scopes."""
        self._global_context.clear()
        _request_context.set({})
        _thread_context.set({})
        _temporary_context.set({})
        self._context_stack.clear()


class ContextualLogger:
    """
    Mixin class that adds contextual logging capabilities to MohflowLogger.

    This class provides methods for creating temporary context overlays
    and chaining context for more readable logging code.
    """

    def __init__(self):
        """Initialize contextual logging capabilities."""
        self.context_manager = ScopedContextManager()

    def with_context(self, **kwargs: Any) -> "ContextualLoggerProxy":
        """
        Create a temporary context overlay for the next log message.

        Usage:
            logger.with_context(
                component="auth", user_id="123"
            ).info("Login attempt")

        Args:
            **kwargs: Context key-value pairs to add temporarily

        Returns:
            ContextualLoggerProxy: Proxy object with temporary context
        """
        return ContextualLoggerProxy(self, kwargs)

    def request_context(self, **kwargs: Any):
        """
        Get request context manager.

        Usage:
            with logger.request_context(request_id="123"):
                logger.info("Processing request")
        """
        return self.context_manager.request_context(**kwargs)

    def thread_context(self, **kwargs: Any):
        """
        Get thread context manager.

        Usage:
            with logger.thread_context(worker_id="worker_1"):
                logger.info("Thread processing")
        """
        return self.context_manager.thread_context(**kwargs)

    def temporary_context(self, **kwargs: Any):
        """
        Get temporary context manager.

        Usage:
            with logger.temporary_context(operation="validate"):
                logger.info("Validating")
        """
        return self.context_manager.temporary_context(**kwargs)

    def get_current_context(self) -> Dict[str, Any]:
        """Get complete current context from all scopes."""
        return self.context_manager.get_current_context()

    def set_context(self, **kwargs: Any) -> None:
        """
        Set global context (backward compatibility).

        Args:
            **kwargs: Context key-value pairs to set globally
        """
        self.context_manager.set_global_context(**kwargs)


class ContextualLoggerProxy:
    """
    Proxy object that applies temporary context to a single log operation.

    This allows for method chaining like:
    logger.with_context(user_id="123").info("User logged in")
    """

    def __init__(self, logger, context: Dict[str, Any]):
        """
        Initialize the contextual logger proxy.

        Args:
            logger: The underlying logger instance
            context: Temporary context to apply
        """
        self._logger = logger
        self._context = context

    def _log_with_context(self, level: str, message: str, **kwargs: Any):
        """Log message with temporary context applied."""
        # Merge temporary context with provided kwargs
        merged_kwargs = {**self._context, **kwargs}

        # Call the appropriate logging method
        log_method = getattr(self._logger, level)
        log_method(message, **merged_kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message with temporary context."""
        self._log_with_context("debug", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message with temporary context."""
        self._log_with_context("info", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message with temporary context."""
        self._log_with_context("warning", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message with temporary context."""
        self._log_with_context("error", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message with temporary context."""
        self._log_with_context("critical", message, **kwargs)


# Global context manager instance
_global_context_manager = ScopedContextManager()


# Convenience functions for global context management
def set_global_context(**kwargs: Any) -> None:
    """Set global context that applies to all loggers."""
    _global_context_manager.set_global_context(**kwargs)


def get_global_context() -> Dict[str, Any]:
    """Get current global context."""
    return _global_context_manager.get_global_context()


def clear_global_context() -> None:
    """Clear all global context."""
    _global_context_manager.clear_global_context()


def request_context(**kwargs: Any):
    """Global request context manager."""
    return _global_context_manager.request_context(**kwargs)


def thread_context(**kwargs: Any):
    """Global thread context manager."""
    return _global_context_manager.thread_context(**kwargs)


def temporary_context(**kwargs: Any):
    """Global temporary context manager."""
    return _global_context_manager.temporary_context(**kwargs)
