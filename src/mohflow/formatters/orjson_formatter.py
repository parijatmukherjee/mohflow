"""High-performance JSON formatter using orjson for faster serialization."""

import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone

try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    import json

    HAS_ORJSON = False


class OrjsonFormatter(logging.Formatter):
    """
    High-performance JSON formatter using orjson.

    Provides 4-10x faster JSON serialization compared to standard json library.
    Falls back to standard json if orjson is not available.
    """

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        style: str = "%",
        validate: bool = True,
        *,
        ensure_ascii: bool = False,
        indent: Optional[int] = None,
        sort_keys: bool = False,
        static_fields: Optional[Dict[str, Any]] = None,
        exclude_fields: Optional[list] = None,
        rename_fields: Optional[Dict[str, str]] = None,
        timestamp_field: str = "timestamp",
        timestamp_format: str = "iso",
    ):
        """
        Initialize the high-performance JSON formatter.

        Args:
            fmt: Format string (ignored for JSON output)
            datefmt: Date format string
            style: Format style (ignored for JSON output)
            validate: Validate format string (ignored for JSON output)
            ensure_ascii: Escape non-ASCII characters
            indent: JSON indentation (None for compact output)
            sort_keys: Sort JSON keys alphabetically
            static_fields: Fields to include in every log record
            exclude_fields: Fields to exclude from log records
            rename_fields: Mapping to rename log record fields
            timestamp_field: Name of timestamp field
            timestamp_format: Timestamp format ('iso', 'epoch', 'epoch_ms')
        """
        super().__init__(fmt, datefmt, style, validate)

        self.ensure_ascii = ensure_ascii
        self.indent = indent
        self.sort_keys = sort_keys
        self.static_fields = static_fields or {}
        self.exclude_fields = set(exclude_fields or [])
        self.rename_fields = rename_fields or {}
        self.timestamp_field = timestamp_field
        self.timestamp_format = timestamp_format

        # orjson options
        self._orjson_options = orjson.OPT_APPEND_NEWLINE if HAS_ORJSON else 0
        if not ensure_ascii and HAS_ORJSON:
            self._orjson_options |= orjson.OPT_NON_STR_KEYS
        if sort_keys and HAS_ORJSON:
            self._orjson_options |= orjson.OPT_SORT_KEYS
        if indent and HAS_ORJSON:
            self._orjson_options |= orjson.OPT_INDENT_2

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        # Create log data dictionary
        log_data = self._create_log_data(record)

        # Add timestamp
        log_data[self.timestamp_field] = self._format_timestamp(record)

        # Add static fields
        log_data.update(self.static_fields)

        # Apply field renaming
        if self.rename_fields:
            for old_name, new_name in self.rename_fields.items():
                if old_name in log_data:
                    log_data[new_name] = log_data.pop(old_name)

        # Remove excluded fields
        for field in self.exclude_fields:
            log_data.pop(field, None)

        # Serialize to JSON
        if HAS_ORJSON:
            return orjson.dumps(log_data, option=self._orjson_options).decode(
                "utf-8"
            )
        else:
            return (
                json.dumps(
                    log_data,
                    ensure_ascii=self.ensure_ascii,
                    indent=self.indent,
                    sort_keys=self.sort_keys,
                    default=self._json_default,
                )
                + "\n"
            )

    def _create_log_data(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Create base log data dictionary from record."""
        # Basic log fields
        log_data = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process_id": record.process,
            "thread_id": record.thread,
            "thread_name": record.threadName,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_data["stack_info"] = self.formatStack(record.stack_info)

        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "asctime",
            }:
                log_data[key] = value

        return log_data

    def _format_timestamp(
        self, record: logging.LogRecord
    ) -> Union[str, int, float]:
        """Format timestamp based on configured format."""
        if self.timestamp_format == "epoch":
            return int(record.created)
        elif self.timestamp_format == "epoch_ms":
            return int(record.created * 1000)
        else:  # iso format (default)
            dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
            return dt.isoformat()

    def _json_default(self, obj: Any) -> Any:
        """Default JSON serializer for non-standard types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        else:
            return str(obj)


class FastJSONFormatter(OrjsonFormatter):
    """
    Optimized JSON formatter with preset configurations for maximum
    performance.

    Uses orjson with optimized settings:
    - Compact output (no indentation)
    - No field sorting
    - Epoch timestamp (faster than ISO)
    - Minimal field set
    """

    def __init__(self, **kwargs):
        # Override with performance-optimized defaults
        kwargs.setdefault("indent", None)
        kwargs.setdefault("sort_keys", False)
        kwargs.setdefault("timestamp_format", "epoch_ms")
        kwargs.setdefault(
            "exclude_fields",
            ["module", "function", "line", "thread_name", "processName"],
        )

        super().__init__(**kwargs)


class StructuredFormatter(OrjsonFormatter):
    """
    Formatter optimized for structured logging with rich context.

    Includes comprehensive field set and human-readable formatting
    suitable for development and debugging.
    """

    def __init__(self, **kwargs):
        # Override with structured logging defaults
        kwargs.setdefault("indent", 2)
        kwargs.setdefault("sort_keys", True)
        kwargs.setdefault("timestamp_format", "iso")
        kwargs.setdefault(
            "static_fields", {"service": "mohflow-app", "version": "1.0.0"}
        )

        super().__init__(**kwargs)
