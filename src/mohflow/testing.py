"""
Testing utilities for applications that use MohFlow.

Provides helpers to capture, inspect, and assert on log output
in unit and integration tests.

Usage::

    from mohflow.testing import capture_logs, assert_logged, LogCapture

    # As a context manager
    with capture_logs() as cap:
        log.info("user signed up", user_id="u123")

    assert_logged(cap, level="INFO", message_contains="signed up")
    assert cap.records[0].extra["user_id"] == "u123"

    # As a pytest fixture (register in conftest.py)
    @pytest.fixture
    def log_capture():
        with capture_logs() as cap:
            yield cap
"""

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class CapturedRecord:
    """A single captured log record with easy attribute access."""

    level: str
    message: str
    logger_name: str
    extra: Dict[str, Any] = field(default_factory=dict)
    exc_info: Optional[Any] = None
    _raw: Optional[logging.LogRecord] = field(default=None, repr=False)

    @classmethod
    def from_log_record(cls, record: logging.LogRecord) -> "CapturedRecord":
        """Build from a stdlib LogRecord."""
        # Extract extra fields (anything not in the standard set)
        extra = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _STANDARD_KEYS and not k.startswith("_")
        }
        return cls(
            level=record.levelname,
            message=record.getMessage(),
            logger_name=record.name,
            extra=extra,
            exc_info=record.exc_info,
            _raw=record,
        )


class LogCapture:
    """Accumulates captured log records for later inspection."""

    def __init__(self) -> None:
        self.records: List[CapturedRecord] = []

    def append(self, record: CapturedRecord) -> None:
        self.records.append(record)

    @property
    def messages(self) -> List[str]:
        """Return just the message strings."""
        return [r.message for r in self.records]

    def filter(
        self,
        level: Optional[str] = None,
        logger_name: Optional[str] = None,
        message_contains: Optional[str] = None,
    ) -> List[CapturedRecord]:
        """Return records matching all supplied criteria."""
        results = list(self.records)
        if level:
            results = [r for r in results if r.level == level.upper()]
        if logger_name:
            results = [r for r in results if r.logger_name == logger_name]
        if message_contains:
            results = [r for r in results if message_contains in r.message]
        return results

    def clear(self) -> None:
        self.records.clear()

    def __len__(self) -> int:
        return len(self.records)

    def __bool__(self) -> bool:
        return bool(self.records)

    def __repr__(self) -> str:
        return (
            f"LogCapture({len(self.records)} records: "
            f"{self.messages[:3]}{'...' if len(self.records) > 3 else ''})"
        )


class _CaptureHandler(logging.Handler):
    """Internal handler that appends to a LogCapture."""

    def __init__(self, capture: LogCapture):
        super().__init__(level=logging.DEBUG)
        self.capture = capture

    def emit(self, record: logging.LogRecord) -> None:
        self.capture.append(CapturedRecord.from_log_record(record))


@contextmanager
def capture_logs(
    logger_name: Optional[str] = None,
    level: int = logging.DEBUG,
):
    """Context manager that captures all log output.

    Args:
        logger_name: Specific logger to capture (None = root).
        level: Minimum level to capture (default DEBUG).

    Yields:
        LogCapture instance containing captured records.

    Example::

        with capture_logs() as cap:
            logging.getLogger("myapp").info("hello")
        assert len(cap) == 1
    """
    capture = LogCapture()
    handler = _CaptureHandler(capture)
    handler.setLevel(level)

    logger = logging.getLogger(logger_name)
    original_level = logger.level
    logger.setLevel(level)
    logger.addHandler(handler)
    try:
        yield capture
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)


def assert_logged(
    capture: LogCapture,
    level: Optional[str] = None,
    message_contains: Optional[str] = None,
    message_equals: Optional[str] = None,
    logger_name: Optional[str] = None,
    extra_contains: Optional[Dict[str, Any]] = None,
    count: Optional[int] = None,
) -> None:
    """Assert that a matching log record was captured.

    Raises ``AssertionError`` with a helpful message on failure.

    Args:
        capture: The LogCapture to search.
        level: Required log level (e.g. "INFO").
        message_contains: Substring that must appear in message.
        message_equals: Exact message match.
        logger_name: Required logger name.
        extra_contains: Dict of key-value pairs that must be
            present in the record's extra fields.
        count: If set, assert exactly this many matches.
    """
    matches = list(capture.records)

    if level:
        matches = [r for r in matches if r.level == level.upper()]
    if logger_name:
        matches = [r for r in matches if r.logger_name == logger_name]
    if message_contains:
        matches = [r for r in matches if message_contains in r.message]
    if message_equals:
        matches = [r for r in matches if r.message == message_equals]
    if extra_contains:

        def _extra_match(rec: CapturedRecord) -> bool:
            for k, v in extra_contains.items():
                if rec.extra.get(k) != v:
                    return False
            return True

        matches = [r for r in matches if _extra_match(r)]

    if count is not None:
        assert len(matches) == count, (
            f"Expected {count} matching log record(s), "
            f"found {len(matches)}. "
            f"All captured: {capture.messages}"
        )
    else:
        assert len(matches) > 0, (
            f"No matching log record found. "
            f"Criteria: level={level}, "
            f"message_contains={message_contains!r}, "
            f"message_equals={message_equals!r}, "
            f"logger_name={logger_name}. "
            f"All captured: {capture.messages}"
        )


# Standard LogRecord attribute names (excluded from extra)
_STANDARD_KEYS = {
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
