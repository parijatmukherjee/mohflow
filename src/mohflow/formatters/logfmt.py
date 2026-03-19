"""
logfmt formatter for MohFlow logging.

Renders log records in logfmt format, the de-facto standard for
Prometheus/Grafana Loki ecosystems.

Output example::

    ts=2026-03-18T12:00:00Z level=info msg="user signed up" user_id=u123

References:
    - https://brandur.org/logfmt
    - https://pkg.go.dev/github.com/kr/logfmt
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

# Characters that require quoting in logfmt values
_NEEDS_QUOTE_RE = re.compile(r'[\s"=\\]')


def _logfmt_value(val: Any) -> str:
    """Serialize a single value for logfmt output.

    Rules:
    - ``None`` → empty string (omitted by caller)
    - ``bool`` → ``true`` / ``false``
    - ``int`` / ``float`` → unquoted numeric literal
    - ``str`` → quoted if it contains whitespace, ``=``, ``"``, or ``\\``
    - Everything else → ``str(val)`` then same quoting rules
    """
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val)
    if s == "":
        return '""'
    if _NEEDS_QUOTE_RE.search(s):
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _logfmt_pair(key: str, val: Any) -> str:
    """Return ``key=value`` logfmt pair."""
    return f"{key}={_logfmt_value(val)}"


# Standard LogRecord fields that should not leak into logfmt output
_STANDARD_RECORD_ATTRS = frozenset(
    {
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
        "taskName",
    }
)


class LogfmtFormatter(logging.Formatter):
    """Render log records as logfmt key=value pairs.

    Parameters
    ----------
    keys : sequence of str, optional
        Ordered list of keys to emit. When given, only these keys
        appear in the output (in this exact order).  Extra fields
        from the log record are appended afterwards unless
        *strict_keys* is ``True``.
    strict_keys : bool
        When ``True`` (and *keys* is given), extra fields not in
        *keys* are silently dropped.
    timestamp_key : str
        Key name used for the timestamp field (default ``"ts"``).
    level_key : str
        Key name used for the log level (default ``"level"``).
    message_key : str
        Key name used for the message (default ``"msg"``).
    timestamp_format : str
        ``"iso"`` (default), ``"epoch"``, or ``"epoch_ms"``.
    include_logger_name : bool
        Include the logger name as ``logger=...``.
    sort_extra_keys : bool
        Sort extra keys alphabetically (default ``False``).
    """

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        style: str = "%",
        validate: bool = True,
        *,
        keys: Optional[Sequence[str]] = None,
        strict_keys: bool = False,
        timestamp_key: str = "ts",
        level_key: str = "level",
        message_key: str = "msg",
        timestamp_format: str = "iso",
        include_logger_name: bool = False,
        sort_extra_keys: bool = False,
    ):
        super().__init__(fmt, datefmt, style, validate)
        self.keys = list(keys) if keys else None
        self.strict_keys = strict_keys
        self.timestamp_key = timestamp_key
        self.level_key = level_key
        self.message_key = message_key
        self.timestamp_format = timestamp_format
        self.include_logger_name = include_logger_name
        self.sort_extra_keys = sort_extra_keys

    # ── public API ───────────────────────────────────────────

    def format(self, record: logging.LogRecord) -> str:
        """Format *record* as a single logfmt line."""
        pairs = self._build_pairs(record)
        return " ".join(pairs)

    # ── internals ────────────────────────────────────────────

    def _build_pairs(self, record: logging.LogRecord) -> List[str]:
        """Build the ordered list of ``key=value`` strings."""
        data = self._record_to_dict(record)

        if self.keys:
            pairs = [
                _logfmt_pair(k, data.pop(k)) for k in self.keys if k in data
            ]
            if not self.strict_keys:
                extra = sorted(data) if self.sort_extra_keys else data
                pairs.extend(_logfmt_pair(k, data[k]) for k in extra)
        else:
            # Default order: ts, level, msg, logger, …rest
            ordered: List[str] = []
            for k in (
                self.timestamp_key,
                self.level_key,
                self.message_key,
            ):
                if k in data:
                    ordered.append(_logfmt_pair(k, data.pop(k)))

            if self.include_logger_name and "logger" in data:
                ordered.append(_logfmt_pair("logger", data.pop("logger")))

            rest_keys = sorted(data) if self.sort_extra_keys else list(data)
            ordered.extend(_logfmt_pair(k, data[k]) for k in rest_keys)
            pairs = ordered

        return pairs

    def _record_to_dict(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Convert a ``LogRecord`` into a flat dict for logfmt."""
        data: Dict[str, Any] = {}

        # Timestamp
        data[self.timestamp_key] = self._format_timestamp(record)

        # Level
        data[self.level_key] = record.levelname.lower()

        # Message
        data[self.message_key] = record.getMessage()

        # Logger name
        if self.include_logger_name:
            data["logger"] = record.name

        # Exception
        if record.exc_info and record.exc_info[1] is not None:
            data["error"] = str(record.exc_info[1])
            data["error_type"] = type(record.exc_info[1]).__name__

        # Extra fields from the record (user-supplied kwargs)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS:
                data[key] = value

        return data

    def _format_timestamp(
        self, record: logging.LogRecord
    ) -> Union[str, int, float]:
        if self.timestamp_format == "epoch":
            return int(record.created)
        elif self.timestamp_format == "epoch_ms":
            return int(record.created * 1000)
        else:
            dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
            return dt.isoformat()
