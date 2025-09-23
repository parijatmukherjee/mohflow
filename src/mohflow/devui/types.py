"""
Data types and models for Mohnitor.

Defines core entities: HubDescriptor, LogEvent, ClientConnection,
FilterConfiguration, and UIState.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import json
import os
import ipaddress
import re


def utcnow() -> datetime:
    """Get current UTC time with timezone awareness."""
    return datetime.now(timezone.utc)


@dataclass
class HubDescriptor:
    """Discovery and connection metadata for active Mohnitor hub."""

    host: str  # "127.0.0.1" or bind address
    port: int  # Selected port (17361-17380)
    pid: int  # Hub process ID for validation
    token: Optional[str]  # Auth token (None for localhost)
    created_at: datetime  # Timestamp for staleness checks
    version: str  # Mohnitor version for compatibility

    def __post_init__(self):
        """Validate HubDescriptor fields after creation."""
        self._validate_host()
        self._validate_port()
        self._validate_pid()
        self._validate_token_for_remote()

    def _validate_host(self):
        """Validate host is valid IP or hostname."""
        if not self.host or not isinstance(self.host, str):
            raise ValueError("Host must be non-empty string")

        # Try to parse as IP address
        try:
            ipaddress.ip_address(self.host)
            return
        except ValueError:
            pass

        # Validate as hostname
        if not re.match(r"^[a-zA-Z0-9.-]+$", self.host) or ".." in self.host:
            raise ValueError(f"Invalid host: {self.host}")

    def _validate_port(self):
        """Validate port is in valid range."""
        if (
            not isinstance(self.port, int)
            or self.port < 1024
            or self.port > 65535
        ):
            raise ValueError(
                f"Port must be between 1024-65535, got: {self.port}"
            )

    def _validate_pid(self):
        """Validate PID is positive integer."""
        if not isinstance(self.pid, int) or self.pid <= 0:
            raise ValueError(f"PID must be positive integer, got: {self.pid}")

    def _validate_token_for_remote(self):
        """Validate token is required for non-localhost hosts."""
        if self.host not in ("127.0.0.1", "localhost") and self.token is None:
            raise ValueError("Token required for non-localhost hosts")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "pid": self.pid,
            "token": self.token,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HubDescriptor":
        """Deserialize from dictionary."""
        return cls(
            host=data["host"],
            port=data["port"],
            pid=data["pid"],
            token=data.get("token"),
            created_at=datetime.fromisoformat(
                data["created_at"].replace("Z", "+00:00")
            ),
            version=data["version"],
        )

    def age_seconds(self) -> float:
        """Calculate age in seconds since creation."""
        return (utcnow() - self.created_at).total_seconds()


@dataclass
class LogEvent:
    """Structured log entry for transmission and display."""

    timestamp: datetime  # ISO 8601 UTC timestamp
    level: str  # DEBUG, INFO, WARN, ERROR, CRITICAL
    service: str  # Service identifier
    message: str  # Primary log message
    logger: str  # Logger name/module
    trace_id: Optional[str] = None  # Correlation identifier
    context: Dict[str, Any] = field(
        default_factory=dict
    )  # Additional structured fields

    # Mohnitor metadata
    source_host: str = ""  # Client host identifier
    source_pid: int = 0  # Client process ID
    received_at: Optional[datetime] = None  # Hub receipt timestamp

    def __post_init__(self):
        """Validate LogEvent fields after creation."""
        self._validate_level()
        self._validate_service()

    def _validate_level(self):
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}
        if self.level not in valid_levels:
            raise ValueError(
                f"Invalid log level: {self.level}. Must be one of {valid_levels}"
            )

    def _validate_service(self):
        """Validate service name is non-empty."""
        if not self.service or not isinstance(self.service, str):
            raise ValueError("Service name must be non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "service": self.service,
            "message": self.message,
            "logger": self.logger,
            "trace_id": self.trace_id,
            "context": self.context,
            "source_host": self.source_host,
            "source_pid": self.source_pid,
            "received_at": (
                self.received_at.isoformat() if self.received_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEvent":
        """Deserialize from dictionary."""
        # Parse timestamp
        timestamp_str = data["timestamp"]
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        timestamp = datetime.fromisoformat(timestamp_str)

        # Parse received_at if present
        received_at = None
        if data.get("received_at"):
            received_str = data["received_at"]
            if received_str.endswith("Z"):
                received_str = received_str[:-1] + "+00:00"
            received_at = datetime.fromisoformat(received_str)

        return cls(
            timestamp=timestamp,
            level=data["level"],
            service=data["service"],
            message=data["message"],
            logger=data["logger"],
            trace_id=data.get("trace_id"),
            context=data.get("context", {}),
            source_host=data.get("source_host", ""),
            source_pid=data.get("source_pid", 0),
            received_at=received_at,
        )

    def serialized_size(self) -> int:
        """Calculate serialized size in bytes."""
        return len(json.dumps(self.to_dict(), default=str).encode("utf-8"))

    def validate_size(self, max_size: int = 64 * 1024) -> None:
        """Validate event size is under limit."""
        size = self.serialized_size()
        if size > max_size:
            raise ValueError(
                f"LogEvent size {size} bytes exceeds limit {max_size} bytes"
            )

    def set_received_at(self) -> None:
        """Set received_at timestamp to current time."""
        self.received_at = utcnow()


@dataclass
class ClientConnection:
    """Active WebSocket connection from application to hub."""

    connection_id: str  # Unique connection identifier
    service: str  # Client service name
    host: str  # Client host/IP
    pid: int  # Client process ID
    connected_at: datetime  # Connection establishment time
    last_seen: datetime  # Last activity timestamp
    events_sent: int = 0  # Message counter
    is_authenticated: bool = False  # Auth status for remote connections

    def update_heartbeat(self) -> None:
        """Update last_seen timestamp to current time."""
        self.last_seen = utcnow()

    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if connection is stale based on last_seen."""
        age = (utcnow() - self.last_seen).total_seconds()
        return age > timeout_seconds


@dataclass
class FilterConfiguration:
    """User-defined criteria for log event filtering."""

    name: str  # User-assigned filter name
    time_range: Optional[str] = None  # "5m", "15m", "1h", "24h"
    levels: List[str] = field(default_factory=list)  # Selected log levels
    services: List[str] = field(default_factory=list)  # Selected service names
    text_search: Optional[str] = None  # Free-text search term
    field_filters: Dict[str, Any] = field(
        default_factory=dict
    )  # Key-value field constraints
    query_expression: Optional[str] = None  # MQL query string
    exclude_patterns: List[str] = field(
        default_factory=list
    )  # Negation patterns

    # UI state
    is_active: bool = False  # Currently applied
    is_saved: bool = False  # Persisted to storage
    created_at: Optional[datetime] = None  # Creation timestamp

    def __post_init__(self):
        """Validate FilterConfiguration after creation."""
        if self.time_range:
            self._validate_time_range()

    def _validate_time_range(self):
        """Validate time range format."""
        valid_ranges = {"5m", "15m", "1h", "24h"}
        if self.time_range not in valid_ranges:
            raise ValueError(
                f"Invalid time range: {self.time_range}. Must be one of {valid_ranges}"
            )

    def parse_mql(self) -> Dict[str, Any]:
        """Parse MQL query expression into structured filter."""
        if not self.query_expression:
            return {}

        # Simple MQL parser - basic implementation
        # Full implementation would be in query/mql.py
        parsed = {}
        if "level:" in self.query_expression:
            # Extract level filter
            import re

            level_match = re.search(r"level:(\w+)", self.query_expression)
            if level_match:
                parsed["level"] = level_match.group(1)

        return parsed

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "time_range": self.time_range,
            "levels": self.levels,
            "services": self.services,
            "text_search": self.text_search,
            "field_filters": self.field_filters,
            "query_expression": self.query_expression,
            "exclude_patterns": self.exclude_patterns,
            "is_active": self.is_active,
            "is_saved": self.is_saved,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilterConfiguration":
        """Deserialize from dictionary."""
        # Parse created_at if present
        created_at = None
        if data.get("created_at"):
            created_at_str = data["created_at"]
            if created_at_str.endswith("Z"):
                created_at_str = created_at_str[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_at_str)

        return cls(
            name=data["name"],
            time_range=data.get("time_range"),
            levels=data.get("levels", []),
            services=data.get("services", []),
            text_search=data.get("text_search"),
            field_filters=data.get("field_filters", {}),
            query_expression=data.get("query_expression"),
            exclude_patterns=data.get("exclude_patterns", []),
            is_active=data.get("is_active", False),
            is_saved=data.get("is_saved", False),
            created_at=created_at,
        )


@dataclass
class UIState:
    """Persistent user interface configuration."""

    theme: str = "auto"  # "light", "dark", "auto"
    columns: List[str] = field(
        default_factory=lambda: ["timestamp", "level", "service", "message"]
    )  # Visible column order
    column_widths: Dict[str, int] = field(
        default_factory=dict
    )  # Column width preferences
    auto_scroll: bool = True  # Follow new logs
    json_expanded: bool = False  # Default JSON view state
    filters: List[FilterConfiguration] = field(
        default_factory=list
    )  # Saved filters
    pinned_fields: List[str] = field(
        default_factory=list
    )  # Always-visible fields

    # Persistence
    last_updated: Optional[datetime] = None  # State modification time
    version: int = 1  # State schema version

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "theme": self.theme,
            "columns": self.columns,
            "column_widths": self.column_widths,
            "auto_scroll": self.auto_scroll,
            "json_expanded": self.json_expanded,
            "filters": [
                {"name": f.name, "levels": f.levels, "services": f.services}
                for f in self.filters
            ],
            "pinned_fields": self.pinned_fields,
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
            "version": self.version,
        }

    @classmethod
    def load_from_file(cls) -> "UIState":
        """Load UI state from file."""
        from .paths import get_ui_state_path

        state_path = get_ui_state_path()
        if not state_path or not state_path.exists():
            return cls()  # Return default state

        try:
            with open(state_path) as f:
                data = json.load(f)
            return cls(
                theme=data.get("theme", "auto"),
                columns=data.get(
                    "columns", ["timestamp", "level", "service", "message"]
                ),
                auto_scroll=data.get("auto_scroll", True),
                version=data.get("version", 1),
            )
        except (json.JSONDecodeError, IOError):
            return cls()  # Return default on error

    def save_to_file(self) -> None:
        """Save UI state to file."""
        from .paths import get_ui_state_path

        state_path = get_ui_state_path()
        if not state_path:
            return

        self.last_updated = utcnow()

        try:
            with open(state_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
        except IOError:
            pass  # Ignore save errors
