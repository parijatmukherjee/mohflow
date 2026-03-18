"""
Colored console renderer for development-friendly log output.

Uses ANSI escape codes for coloring (no external dependency required).
Falls back to plain text when output is not a TTY.
"""

import logging
import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ANSI color codes
_COLORS = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "DIM": "\033[2m",
    "RED": "\033[31m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
    "BLUE": "\033[34m",
    "MAGENTA": "\033[35m",
    "CYAN": "\033[36m",
    "WHITE": "\033[37m",
    "BRIGHT_RED": "\033[91m",
    "BRIGHT_GREEN": "\033[92m",
    "BRIGHT_YELLOW": "\033[93m",
    "BRIGHT_BLUE": "\033[94m",
    "BRIGHT_MAGENTA": "\033[95m",
    "BRIGHT_CYAN": "\033[96m",
    "GRAY": "\033[90m",
}

_LEVEL_COLORS = {
    "DEBUG": _COLORS["BLUE"],
    "INFO": _COLORS["GREEN"],
    "WARNING": _COLORS["YELLOW"],
    "ERROR": _COLORS["RED"],
    "CRITICAL": _COLORS["BRIGHT_RED"] + _COLORS["BOLD"],
}

_LEVEL_ICONS = {
    "DEBUG": "DBG",
    "INFO": "INF",
    "WARNING": "WRN",
    "ERROR": "ERR",
    "CRITICAL": "CRT",
}


def _is_tty() -> bool:
    """Detect whether stdout is a terminal."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


class ColoredConsoleFormatter(logging.Formatter):
    """Human-friendly colored console formatter.

    Produces output like::

        12:34:56 INF  user signed up  user_id=u123 plan=pro

    Colors are applied when stderr is a TTY, disabled otherwise.
    Respects ``NO_COLOR`` and ``FORCE_COLOR`` env vars.
    """

    def __init__(
        self,
        colorize: Optional[bool] = None,
        show_timestamp: bool = True,
        show_level: bool = True,
        show_logger_name: bool = False,
        static_fields: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ):
        super().__init__()
        self.colorize = colorize if colorize is not None else _is_tty()
        self.show_timestamp = show_timestamp
        self.show_level = show_level
        self.show_logger_name = show_logger_name
        self.static_fields = static_fields or {}

    def _c(self, code: str, text: str) -> str:
        """Apply color if colorization is enabled."""
        if self.colorize:
            return f"{code}{text}{_COLORS['RESET']}"
        return text

    def format(self, record: logging.LogRecord) -> str:
        parts = []

        # Timestamp
        if self.show_timestamp:
            ts = datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).strftime("%H:%M:%S")
            parts.append(self._c(_COLORS["GRAY"], ts))

        # Level
        if self.show_level:
            level = record.levelname
            icon = _LEVEL_ICONS.get(level, level[:3])
            color = _LEVEL_COLORS.get(level, "")
            parts.append(self._c(color, f"{icon:>3}"))

        # Logger name
        if self.show_logger_name:
            parts.append(self._c(_COLORS["CYAN"], record.name))

        # Message
        msg = record.getMessage()
        parts.append(self._c(_COLORS["BOLD"], msg))

        # Extra fields (key=value pairs)
        extra_keys = _extract_extra_keys(record)
        if extra_keys:
            kv_parts = []
            for key in sorted(extra_keys):
                val = getattr(record, key, None)
                colored_key = self._c(_COLORS["DIM"], f"{key}=")
                kv_parts.append(f"{colored_key}{val}")
            parts.append("  ".join(kv_parts))

        # Exception info
        if record.exc_info and record.exc_info[1]:
            exc_text = self.formatException(record.exc_info)
            parts.append("\n" + self._c(_COLORS["RED"], exc_text))

        return "  ".join(p for p in parts if p and not p.startswith("\n")) + (
            ""
            if not record.exc_info or not record.exc_info[1]
            else "\n" + self._c(_COLORS["RED"], exc_text)
        )


# Standard LogRecord attributes to exclude from extra fields
_STANDARD_ATTRS = {
    "args",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}


def _extract_extra_keys(record: logging.LogRecord) -> list:
    """Extract non-standard keys from a LogRecord."""
    return [
        key
        for key in record.__dict__
        if key not in _STANDARD_ATTRS and not key.startswith("_")
    ]
