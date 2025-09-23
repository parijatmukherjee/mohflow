# WebSocket Protocol Specification

**Version**: 1.0.0
**Date**: 2025-09-23

## Connection Types

### Client Connection (App → Hub)
**Purpose**: Forward log events from application to hub
**URL**: `ws://127.0.0.1:17361/ws?service=<service_name>&token=<token>`

#### Authentication
- **Localhost**: No token required
- **Remote**: Token required in query parameter
- **Validation**: Service name must be non-empty

#### Message Types

##### 1. Log Event Forward
```json
{
  "type": "log_event",
  "payload": {
    "timestamp": "2025-09-23T10:30:00.123Z",
    "level": "INFO",
    "service": "checkout",
    "message": "User login successful",
    "logger": "auth.service",
    "trace_id": "abc123-def456",
    "context": {
      "user_id": "12345",
      "ip_address": "192.168.1.100"
    }
  }
}
```

##### 2. Client Heartbeat
```json
{
  "type": "heartbeat",
  "payload": {
    "timestamp": "2025-09-23T10:30:00.123Z",
    "pid": 12345,
    "events_queued": 0
  }
}
```

##### 3. Client Disconnect
```json
{
  "type": "disconnect",
  "payload": {
    "reason": "shutdown",
    "final_event_count": 1000
  }
}
```

### UI Connection (Browser → Hub)
**Purpose**: Receive real-time log updates and send filter commands
**URL**: `ws://127.0.0.1:17361/ws?type=ui`

#### Message Types (Hub → UI)

##### 1. Log Event Broadcast
```json
{
  "type": "log_event",
  "payload": {
    "timestamp": "2025-09-23T10:30:00.123Z",
    "level": "INFO",
    "service": "checkout",
    "message": "User login successful",
    "logger": "auth.service",
    "trace_id": "abc123-def456",
    "context": {
      "user_id": "12345",
      "ip_address": "192.168.1.100"
    },
    "source_host": "dev-machine",
    "source_pid": 12345,
    "received_at": "2025-09-23T10:30:00.125Z"
  }
}
```

##### 2. System Status Update
```json
{
  "type": "system_status",
  "payload": {
    "buffer_events": 15000,
    "active_clients": 3,
    "drop_rate": 0.1,
    "timestamp": "2025-09-23T10:30:00.123Z"
  }
}
```

##### 3. Client Connection Event
```json
{
  "type": "client_event",
  "payload": {
    "event": "connected|disconnected",
    "service": "checkout",
    "host": "dev-machine",
    "timestamp": "2025-09-23T10:30:00.123Z"
  }
}
```

#### Message Types (UI → Hub)

##### 1. Filter Application
```json
{
  "type": "apply_filter",
  "payload": {
    "filter_id": "temp_001",
    "time_range": "15m",
    "levels": ["INFO", "WARN", "ERROR"],
    "services": ["checkout", "auth"],
    "text_search": "login",
    "field_filters": {
      "user_id": "12345"
    },
    "query_expression": "level:ERROR AND service:checkout"
  }
}
```

##### 2. Historical Data Request
```json
{
  "type": "request_history",
  "payload": {
    "filter": { /* FilterRequest object */ },
    "limit": 1000,
    "offset": 0
  }
}
```

##### 3. Export Request
```json
{
  "type": "export_request",
  "payload": {
    "format": "ndjson",
    "filter": { /* FilterRequest object */ },
    "include_metadata": true
  }
}
```

## Connection Lifecycle

### Client (App) Lifecycle
1. **Connect**: WebSocket connection with service parameter
2. **Authenticate**: Token validation for remote connections
3. **Register**: Hub adds to client registry
4. **Stream**: Continuous log event forwarding
5. **Heartbeat**: Periodic keepalive messages
6. **Disconnect**: Graceful or unexpected disconnection
7. **Cleanup**: Hub removes from registry

### UI Lifecycle
1. **Connect**: WebSocket connection with UI type
2. **Sync**: Receive current buffer contents
3. **Subscribe**: Real-time event streaming
4. **Filter**: Apply/modify display filters
5. **Export**: Request log data downloads
6. **Disconnect**: Close browser or navigate away

## Error Handling

### Connection Errors
```json
{
  "type": "error",
  "payload": {
    "code": "AUTH_REQUIRED|INVALID_SERVICE|CONNECTION_LIMIT",
    "message": "Human-readable error description",
    "timestamp": "2025-09-23T10:30:00.123Z"
  }
}
```

### Message Errors
```json
{
  "type": "message_error",
  "payload": {
    "original_message_id": "uuid",
    "error": "INVALID_FORMAT|SIZE_LIMIT|RATE_LIMIT",
    "details": "Specific error information"
  }
}
```

## Rate Limiting

### Client Connections
- **Max events/second**: 1000 per client
- **Max message size**: 64KB per log event
- **Queue backpressure**: Drop oldest when queue full

### UI Connections
- **Max filter changes**: 10 per second
- **Max export requests**: 1 per minute
- **Concurrent exports**: 1 per UI connection

## Protocol Extensions

### Future Message Types
- `trace_follow`: Follow specific trace across services
- `saved_filter`: Manage persistent filter configurations
- `performance_alert`: Notify of system performance issues

### Backwards Compatibility
- Version field in all messages for protocol evolution
- Unknown message types ignored gracefully
- Optional payload fields for feature detection