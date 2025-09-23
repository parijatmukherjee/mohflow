# Mohnitor Quickstart Guide

**Goal**: Get Mohnitor auto-spun log viewer running in under 5 minutes

## Prerequisites
- Python 3.11+
- MohFlow library installed
- Browser for viewing logs

## Installation

```bash
# Install with Mohnitor support
pip install mohflow[mohnitor]
```

## Basic Usage

### Single Application

```python
from mohflow import get_logger

# Enable Mohnitor in your application
logger = get_logger(
    service="my-app",
    enable_mohnitor=True  # This is the magic line
)

# Start logging as usual
logger.info("Application starting")
logger.debug("Debug information", user_id="123")
logger.error("Something went wrong", error_code="E001")

# Your app automatically becomes the hub or connects to existing one
# Check terminal output for: "Mohnitor UI available at: http://127.0.0.1:17361/ui"
```

### Multiple Applications (Shared Hub)

**Terminal 1 - First App (becomes hub)**:
```python
from mohflow import get_logger

logger = get_logger(service="auth-service", enable_mohnitor=True)
logger.info("Auth service starting")
# Output: "Mohnitor hub started at: http://127.0.0.1:17361/ui"
```

**Terminal 2 - Second App (connects to hub)**:
```python
from mohflow import get_logger

logger = get_logger(service="checkout-service", enable_mohnitor=True)
logger.info("Checkout service starting")
# Output: "Connected to Mohnitor hub at: 127.0.0.1:17361"
```

**Result**: Both services appear in the same UI at `http://127.0.0.1:17361/ui`

## UI Features Tour

### 1. Log Table
- **Columns**: Timestamp, Level, Service, Message, Trace ID
- **Sorting**: Click column headers
- **Auto-scroll**: Toggle to follow new logs
- **JSON expansion**: Click message to see full structured data

### 2. Filtering
- **Quick filters**: Buttons for log levels (DEBUG, INFO, WARN, ERROR)
- **Service filter**: Dropdown to show specific services
- **Time range**: Last 5m/15m/1h/24h buttons
- **Text search**: Search in message field
- **Advanced**: Field-specific queries like `user_id:123`

### 3. Trace Correlation
- **Click trace_id**: Automatically filter all logs with same trace
- **Cross-service**: Follow traces across multiple connected applications
- **Clear filter**: Click X to return to full log view

### 4. Export
- **Download button**: Export filtered logs as NDJSON
- **Date range**: Specify time bounds for export
- **Service selection**: Export specific services only

## Configuration Options

### Environment Variables
```bash
# Force connect to specific hub
export MOHNITOR_REMOTE="ws://192.168.1.100:17361/ws"

# Provide auth token for remote hubs
export MOHNITOR_TOKEN="abc123def456"

# Disable Mohnitor entirely
export MOHNITOR_DISABLE=1
```

### Programmatic Configuration
```python
logger = get_logger(
    service="my-app",
    enable_mohnitor=True,

    # Hub configuration
    mohnitor_host="127.0.0.1",          # Bind address
    mohnitor_base_port=17361,           # Starting port
    mohnitor_buffer_size=50000,         # Events to keep in memory

    # Client configuration
    mohnitor_descriptor="/tmp/mohnitor/hub.json",  # Discovery file
    mohnitor_election_lock="/tmp/mohnitor/hub.lock" # Leader election
)
```

## Common Scenarios

### Development Team Setup
```python
# Each developer runs their own services locally
# All connect to shared hub automatically

# Developer A - API service
logger = get_logger(service="api", enable_mohnitor=True)

# Developer B - Frontend service
logger = get_logger(service="frontend", enable_mohnitor=True)

# Developer C - Background worker
logger = get_logger(service="worker", enable_mohnitor=True)

# Result: One shared UI shows all three services
```

### Debugging with Trace IDs
```python
import uuid
from mohflow import get_logger

logger = get_logger(service="order-processor", enable_mohnitor=True)

def process_order(order_id):
    trace_id = str(uuid.uuid4())

    logger.info("Processing order", order_id=order_id, trace_id=trace_id)

    # Call other services with same trace_id
    payment_result = process_payment(order_id, trace_id)
    inventory_result = reserve_inventory(order_id, trace_id)

    logger.info("Order completed",
                order_id=order_id,
                trace_id=trace_id,
                payment=payment_result,
                inventory=inventory_result)

# In UI: Click any trace_id to see complete flow
```

### Production-Like Staging
```python
# Staging environment with remote access
logger = get_logger(
    service="staging-api",
    enable_mohnitor=True,
    mohnitor_host="0.0.0.0"  # Allow remote connections
)

# SSH tunnel from local machine:
# ssh -L 17361:staging-server:17361 user@staging-server
# Then access: http://127.0.0.1:17361/ui
```

## Performance Monitoring

### Built-in Metrics
- Access: `http://127.0.0.1:17361/system`
- **Buffer usage**: Current/max events, memory usage
- **Throughput**: Events per second, latency percentiles
- **Connections**: Active clients, services connected
- **Health**: Drop rate, error conditions

### Performance Tuning
```python
# High-throughput configuration
logger = get_logger(
    service="high-volume-service",
    enable_mohnitor=True,
    mohnitor_buffer_size=100000,  # Larger buffer
)

# Check /system endpoint for drop rate
# If >5% drops, increase buffer size or reduce log volume
```

## Troubleshooting

### Hub Won't Start
```bash
# Check port availability
netstat -ln | grep 17361

# Check permissions for /tmp/mohnitor/
ls -la /tmp/mohnitor/

# Check process conflicts
ps aux | grep mohnitor
```

### Logs Not Appearing
1. **Check service names**: Must match exactly between logger and UI
2. **Verify connection**: Look for "Connected to hub" message
3. **Check filters**: Clear all filters in UI
4. **Network issues**: Try `curl http://127.0.0.1:17361/healthz`

### High Memory Usage
1. **Reduce buffer size**: Lower `mohnitor_buffer_size`
2. **Check log volume**: Monitor events/second in `/system`
3. **Implement sampling**: Log only subset of high-volume events

## Next Steps

1. **Add to your applications**: Enable in existing projects
2. **Configure team sharing**: Set up shared development environment
3. **Create saved filters**: Build common debugging queries
4. **Integrate with CI**: Use for integration test log analysis
5. **Performance testing**: Monitor with load testing tools

## Success Validation

✅ **Single app**: Logs appear in browser UI
✅ **Multi-app**: Multiple services in same UI
✅ **Filtering**: Can filter by level, service, time
✅ **Trace correlation**: Click trace_id filters correctly
✅ **Export**: Can download logs as NDJSON
✅ **Performance**: <150ms latency for new logs

**Time to complete**: Should be under 5 minutes for basic setup