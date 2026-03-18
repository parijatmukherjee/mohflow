"""
Processor pipeline architecture for composable log transformations.

Inspired by structlog's processor chain pattern. Processors are plain
callables that accept and return a dict of event data, enabling
composable, testable log transformation chains.

Usage::

    from mohflow.processors import (
        ProcessorPipeline,
        add_timestamp,
        add_log_level,
        drop_keys,
        rename_keys,
        filter_by_level,
    )

    pipeline = ProcessorPipeline([
        add_timestamp(),
        add_log_level(),
        rename_keys({"service_name": "svc"}),
        drop_keys(["internal_debug"]),
        filter_by_level("INFO"),
    ])

    event = pipeline.process({"message": "hello", "level": "INFO"})
"""

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Union,
)
from datetime import datetime, timezone

# A Processor is any callable Dict -> Dict | None
# Returning None means "drop this event".
Processor = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


class DropEvent(Exception):
    """Raise inside a processor to drop the current event."""


class ProcessorPipeline:
    """Ordered chain of processors applied to every log event.

    Each processor receives the event dict and must return the
    (possibly modified) dict, or ``None`` / raise ``DropEvent``
    to discard the event.
    """

    def __init__(
        self,
        processors: Optional[Sequence[Processor]] = None,
    ):
        self._processors: List[Processor] = list(processors or [])

    def add(self, processor: Processor) -> "ProcessorPipeline":
        """Append a processor and return self for chaining."""
        self._processors.append(processor)
        return self

    def remove(self, processor: Processor) -> None:
        """Remove a processor from the chain."""
        self._processors.remove(processor)

    def clear(self) -> None:
        """Remove all processors."""
        self._processors.clear()

    @property
    def processors(self) -> List[Processor]:
        """Return a copy of the current processor list."""
        return list(self._processors)

    def process(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run *event* through every processor in order.

        Returns the final event dict, or ``None`` if any
        processor dropped the event.
        """
        for proc in self._processors:
            try:
                result = proc(event)
            except DropEvent:
                return None
            if result is None:
                return None
            event = result
        return event

    def __len__(self) -> int:
        return len(self._processors)

    def __repr__(self) -> str:
        names = [
            getattr(p, "__name__", type(p).__name__) for p in self._processors
        ]
        return f"ProcessorPipeline({names})"


# ── Built-in processors ──────────────────────────────────────


def add_timestamp(
    key: str = "timestamp",
    fmt: Optional[str] = None,
) -> Processor:
    """Add an ISO-8601 UTC timestamp to the event."""

    def _add_timestamp(
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        ts = datetime.now(timezone.utc)
        event[key] = ts.strftime(fmt) if fmt else ts.isoformat()
        return event

    _add_timestamp.__name__ = "add_timestamp"
    return _add_timestamp


def add_log_level(key: str = "level") -> Processor:
    """Ensure a ``level`` key exists (default INFO)."""

    def _add_log_level(
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        event.setdefault(key, "INFO")
        return event

    _add_log_level.__name__ = "add_log_level"
    return _add_log_level


def rename_keys(
    mapping: Dict[str, str],
) -> Processor:
    """Rename event keys according to *mapping*."""

    def _rename_keys(
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        for old, new in mapping.items():
            if old in event:
                event[new] = event.pop(old)
        return event

    _rename_keys.__name__ = "rename_keys"
    return _rename_keys


def drop_keys(keys: Sequence[str]) -> Processor:
    """Remove specified keys from the event."""
    keys_set = set(keys)

    def _drop_keys(
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        for k in keys_set:
            event.pop(k, None)
        return event

    _drop_keys.__name__ = "drop_keys"
    return _drop_keys


def add_static_fields(
    fields: Dict[str, Any],
) -> Processor:
    """Merge static fields into every event."""

    def _add_static(
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        for k, v in fields.items():
            event.setdefault(k, v)
        return event

    _add_static.__name__ = "add_static_fields"
    return _add_static


_LEVEL_ORDER = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3,
    "CRITICAL": 4,
}


def filter_by_level(
    min_level: str = "INFO",
) -> Processor:
    """Drop events below *min_level*."""
    min_val = _LEVEL_ORDER.get(min_level.upper(), 1)

    def _filter_level(
        event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        level = event.get("level", "INFO")
        if _LEVEL_ORDER.get(str(level).upper(), 1) < min_val:
            return None
        return event

    _filter_level.__name__ = "filter_by_level"
    return _filter_level


def filter_by_key(
    key: str,
    predicate: Callable[[Any], bool],
) -> Processor:
    """Drop events where ``predicate(event[key])`` is False."""

    def _filter_key(
        event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        value = event.get(key)
        if value is not None and not predicate(value):
            return None
        return event

    _filter_key.__name__ = f"filter_by_{key}"
    return _filter_key


def censor_keys(
    keys: Sequence[str],
    replacement: str = "***",
) -> Processor:
    """Replace values of sensitive keys with *replacement*."""
    keys_set = set(keys)

    def _censor(
        event: Dict[str, Any],
    ) -> Dict[str, Any]:
        for k in keys_set:
            if k in event:
                event[k] = replacement
        return event

    _censor.__name__ = "censor_keys"
    return _censor
