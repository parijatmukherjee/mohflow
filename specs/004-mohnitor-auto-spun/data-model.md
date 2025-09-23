# Data Model: Mohnitor

**Date**: 2025-09-23
**Status**: Phase 1 Design
**Source**: Extracted from feature specification entities

## Core Entities

### Hub Descriptor
**Purpose**: Discovery and connection metadata for active Mohnitor hub
**Location**: `/tmp/mohnitor/hub.json`

```python
@dataclass
class HubDescriptor:
    host: str              # "127.0.0.1" or bind address
    port: int              # Selected port (17361-17380)
    pid: int               # Hub process ID for validation
    token: Optional[str]   # Auth token (None for localhost)
    created_at: datetime   # Timestamp for staleness checks
    version: str           # Mohnitor version for compatibility
```

**Validation Rules**:
- `host` must be valid IP address or hostname
- `port` must be in range 1024-65535
- `pid` must reference active process
- `token` required if `host != "127.0.0.1"`
- `created_at` used for descriptor age validation

**State Transitions**:
- Created atomically when hub starts
- Removed when hub shuts down gracefully
- Validated by health check before use

### Log Event
**Purpose**: Structured log entry for transmission and display
**Source**: MohFlow logger output

```python
@dataclass
class LogEvent:
    timestamp: datetime    # ISO 8601 UTC timestamp
    level: str            # DEBUG, INFO, WARN, ERROR, CRITICAL
    service: str          # Service identifier
    message: str          # Primary log message
    logger: str           # Logger name/module
    trace_id: Optional[str] # Correlation identifier
    context: Dict[str, Any] # Additional structured fields

    # Mohnitor metadata
    source_host: str      # Client host identifier
    source_pid: int       # Client process ID
    received_at: datetime # Hub receipt timestamp
```

**Validation Rules**:
- `timestamp` must be valid ISO 8601 datetime
- `level` must be standard logging level
- `service` required, non-empty string
- `context` must be JSON-serializable
- `trace_id` format validation (UUID or custom)
- Total serialized size limit (configurable, default 64KB)

**Indexing Strategy**:
- Primary access by timestamp (time-range queries)
- Secondary access by service + trace_id
- Field-specific filtering on level, logger

### Client Connection
**Purpose**: Active WebSocket connection from application to hub

```python
@dataclass
class ClientConnection:
    connection_id: str    # Unique connection identifier
    websocket: WebSocket  # Active WebSocket connection
    service: str          # Client service name
    host: str            # Client host/IP
    pid: int             # Client process ID
    connected_at: datetime # Connection establishment time
    last_seen: datetime   # Last activity timestamp
    events_sent: int      # Message counter
    is_authenticated: bool # Auth status for remote connections
```

**Validation Rules**:
- `connection_id` must be globally unique
- `websocket` must be active connection
- `service` must match log events from this client
- Heartbeat validation via `last_seen`

**State Transitions**:
- `CONNECTING` → `AUTHENTICATED` → `ACTIVE`
- `ACTIVE` → `DISCONNECTED` (on connection loss)
- Automatic cleanup of stale connections

### Filter Configuration
**Purpose**: User-defined criteria for log event filtering

```python
@dataclass
class FilterConfiguration:
    name: str                    # User-assigned filter name
    time_range: Optional[str]    # "5m", "15m", "1h", "24h"
    levels: List[str]           # Selected log levels
    services: List[str]         # Selected service names
    text_search: Optional[str]   # Free-text search term
    field_filters: Dict[str, Any] # Key-value field constraints
    query_expression: Optional[str] # MQL query string
    exclude_patterns: List[str]  # Negation patterns

    # UI state
    is_active: bool             # Currently applied
    is_saved: bool              # Persisted to storage
    created_at: datetime        # Creation timestamp
```

**Validation Rules**:
- `time_range` must match supported formats
- `levels` must be valid logging levels
- `field_filters` values must be JSON-serializable
- `query_expression` must parse successfully
- Filter complexity limits (prevent DoS)

### UI State
**Purpose**: Persistent user interface configuration

```python
@dataclass
class UIState:
    theme: str                   # "light", "dark", "auto"
    columns: List[str]          # Visible column order
    column_widths: Dict[str, int] # Column width preferences
    auto_scroll: bool           # Follow new logs
    json_expanded: bool         # Default JSON view state
    filters: List[FilterConfiguration] # Saved filters
    pinned_fields: List[str]    # Always-visible fields

    # Persistence
    last_updated: datetime      # State modification time
    version: int               # State schema version
```

**Validation Rules**:
- `theme` must be supported theme name
- `columns` must reference valid log fields
- `column_widths` must be positive integers
- `pinned_fields` limited to reasonable count (max 10)

**State Transitions**:
- Loaded on UI initialization
- Auto-saved on user configuration changes
- Reset to defaults if version mismatch

## Relationships

### Hub ← Client Connections
- **Type**: One-to-many
- **Constraint**: Hub manages multiple active client connections
- **Lifecycle**: Connections cleaned up when clients disconnect

### Client Connection → Log Events
- **Type**: One-to-many
- **Constraint**: Each log event tagged with source connection
- **Lifecycle**: Events persist in buffer after connection ends

### Log Events ← Filter Configuration
- **Type**: Many-to-many
- **Constraint**: Filters applied to event streams for display
- **Lifecycle**: Filters independent of event lifecycle

### UI State → Filter Configuration
- **Type**: One-to-many
- **Constraint**: UI state contains saved filter configurations
- **Lifecycle**: Filters can outlive UI sessions

## Storage Strategy

### In-Memory (Hub Process)
- **Log Events**: Ring buffer with configurable size (default 50k)
- **Client Connections**: Active connection registry
- **Filter State**: Current UI filter applications

### Filesystem (Persistent)
- **Hub Descriptor**: `/tmp/mohnitor/hub.json`
- **UI State**: `~/.config/mohnitor/ui-state.json` (optional)
- **Saved Filters**: Embedded in UI state JSON

### No External Dependencies
- No database server required
- No network storage dependencies
- Self-contained within Python process + filesystem

## Performance Considerations

### Memory Usage
- 50k events × ~1KB average = ~50MB buffer
- Connection overhead: ~1KB per client
- UI state: <100KB typical

### Access Patterns
- **Write-heavy**: Continuous log event streaming
- **Read-heavy**: Time-range queries, real-time filtering
- **Bounded**: Ring buffer prevents unbounded growth

### Concurrency
- **Thread-safe**: Ring buffer append operations
- **Lock-free**: Event streaming to WebSocket clients
- **Async**: WebSocket handling with FastAPI/Starlette