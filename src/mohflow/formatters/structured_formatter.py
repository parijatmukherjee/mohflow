"""Structured formatter for enhanced logging with context awareness."""

import logging
from typing import Dict, Any, Optional, Callable
from .orjson_formatter import OrjsonFormatter


class StructuredFormatter(OrjsonFormatter):
    """
    Advanced structured formatter with context awareness and field processors.
    
    Provides enhanced structured logging with:
    - Field processors for data transformation
    - Context-aware field inclusion
    - Custom serializers for complex types
    - Performance-optimized field selection
    """
    
    def __init__(
        self,
        include_context: bool = True,
        include_system_info: bool = True,
        include_source_info: bool = True,
        field_processors: Optional[Dict[str, Callable]] = None,
        context_fields: Optional[list] = None,
        **kwargs
    ):
        """
        Initialize structured formatter.
        
        Args:
            include_context: Include request/correlation context
            include_system_info: Include system metadata
            include_source_info: Include source code information
            field_processors: Custom field processors {field_name: processor_func}
            context_fields: List of context fields to include
            **kwargs: Additional OrjsonFormatter arguments
        """
        self.include_context = include_context
        self.include_system_info = include_system_info
        self.include_source_info = include_source_info
        self.field_processors = field_processors or {}
        self.context_fields = set(context_fields or [
            'request_id', 'correlation_id', 'user_id', 'session_id',
            'trace_id', 'span_id', 'operation_name'
        ])
        
        # Set structured logging defaults
        kwargs.setdefault('timestamp_format', 'iso')
        kwargs.setdefault('sort_keys', True)
        
        super().__init__(**kwargs)
    
    def _create_log_data(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Create structured log data with enhanced context."""
        log_data = {}
        
        # Core log information
        log_data.update({
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
        })
        
        # System information
        if self.include_system_info:
            log_data.update({
                'process_id': record.process,
                'thread_id': record.thread,
                'thread_name': record.threadName,
            })
        
        # Source information
        if self.include_source_info:
            log_data.update({
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
                'pathname': record.pathname,
            })
        
        # Exception information
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': self.formatException(record.exc_info)
            }
        
        # Stack information
        if record.stack_info:
            log_data['stack_info'] = self.formatStack(record.stack_info)
        
        # Context fields
        if self.include_context:
            for field in self.context_fields:
                if hasattr(record, field) and getattr(record, field) is not None:
                    log_data[field] = getattr(record, field)
        
        # Extra fields from record
        for key, value in record.__dict__.items():
            if key not in self._get_reserved_fields() and not key.startswith('_'):
                # Apply field processor if available
                if key in self.field_processors:
                    try:
                        value = self.field_processors[key](value)
                    except Exception:
                        # If processor fails, use original value
                        pass
                
                log_data[key] = value
        
        return log_data
    
    def _get_reserved_fields(self) -> set:
        """Get set of reserved LogRecord fields to exclude from extras."""
        return {
            'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
            'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
            'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
            'thread', 'threadName', 'processName', 'process', 'message',
            'asctime', 'taskName'
        }
    
    def add_field_processor(self, field_name: str, processor: Callable[[Any], Any]):
        """Add a field processor for custom data transformation."""
        self.field_processors[field_name] = processor
    
    def remove_field_processor(self, field_name: str):
        """Remove a field processor."""
        self.field_processors.pop(field_name, None)


class ProductionFormatter(StructuredFormatter):
    """Production-optimized structured formatter with minimal overhead."""
    
    def __init__(self, **kwargs):
        # Production optimizations
        kwargs.setdefault('include_source_info', False)
        kwargs.setdefault('sort_keys', False)
        kwargs.setdefault('indent', None)
        kwargs.setdefault('timestamp_format', 'epoch_ms')
        kwargs.setdefault('exclude_fields', [
            'thread_name', 'pathname', 'processName'
        ])
        
        super().__init__(**kwargs)


class DevelopmentFormatter(StructuredFormatter):
    """Development-optimized formatter with full context and readable output."""
    
    def __init__(self, **kwargs):
        # Development optimizations
        kwargs.setdefault('include_source_info', True)
        kwargs.setdefault('include_system_info', True)
        kwargs.setdefault('sort_keys', True)
        kwargs.setdefault('indent', 2)
        kwargs.setdefault('timestamp_format', 'iso')
        
        super().__init__(**kwargs)