"""
Mohnitor Hub Server Implementation.

FastAPI-based server that provides WebSocket endpoints and serves the UI.
"""

import asyncio
import json
import os
import socket
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
import secrets

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    # Will be installed when mohnitor extra is used
    FastAPI = None
    WebSocket = None
    uvicorn = None

from .types import HubDescriptor, LogEvent, ClientConnection
from .paths import get_hub_descriptor_path
from .performance import (
    event_cache,
    message_batcher,
    memory_optimizer,
    performance_monitor,
)


class MohnitorHub:
    """Mohnitor hub server managing log events and WebSocket connections."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 17361,
        buffer_size: int = 50000,
    ):
        if FastAPI is None:
            raise ImportError(
                "FastAPI not available. Install with: pip install mohflow[mohnitor]"
            )

        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.started_at = datetime.now(timezone.utc)

        # Ring buffer for log events
        self.event_buffer: deque = deque(maxlen=buffer_size)
        self.dropped_events = 0

        # Active connections
        self.connections: Dict[str, ClientConnection] = {}
        self.websockets: Dict[str, WebSocket] = {}
        self.ui_websockets: Set[WebSocket] = set()

        # Hub metadata
        self.token = None
        if host != "127.0.0.1":
            self.token = secrets.token_urlsafe(24)

        # Performance optimization
        self.performance_enabled = True
        self.avg_event_size = 1024  # Estimate
        self._optimize_buffer_size()

        # Start performance monitoring
        if self.performance_enabled:
            message_batcher.add_subscriber = self._add_batcher_subscriber
            asyncio.create_task(message_batcher.start_timer())

        # FastAPI app
        self.app = FastAPI(title="Mohnitor Hub", version="1.0.0")
        self._setup_routes()

    def _optimize_buffer_size(self):
        """Optimize buffer size based on memory constraints."""
        target_memory_mb = 50  # 50MB target
        optimal_size = memory_optimizer.optimize_buffer_size(
            target_memory_mb, self.avg_event_size
        )
        if optimal_size != self.buffer_size:
            print(
                f"🎯 Optimized buffer size: {optimal_size} events (target: {target_memory_mb}MB)"
            )
            self.buffer_size = optimal_size
            self.event_buffer = deque(maxlen=optimal_size)

    def _add_batcher_subscriber(self, websocket):
        """Add WebSocket to message batcher."""
        message_batcher.add_subscriber(websocket)

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/healthz")
        async def healthz():
            """Health check endpoint."""
            uptime = (
                datetime.now(timezone.utc) - self.started_at
            ).total_seconds()
            return {"status": "healthy", "uptime": uptime, "version": "1.0.0"}

        @self.app.get("/system")
        async def system():
            """System metrics endpoint."""
            uptime = (
                datetime.now(timezone.utc) - self.started_at
            ).total_seconds()

            # Calculate memory usage (improved estimate)
            memory_mb = (
                len(self.event_buffer) * self.avg_event_size / (1024 * 1024)
            )

            # Update performance monitoring
            if self.performance_enabled:
                performance_monitor.update_memory_usage(memory_mb)
                performance_monitor.update_connection_count(
                    len(self.ui_websockets)
                )
                perf_report = performance_monitor.get_performance_report()
            else:
                perf_report = {}

            return {
                "buffer_stats": {
                    "total_events": len(self.event_buffer),
                    "max_events": self.buffer_size,
                    "dropped_events": self.dropped_events,
                    "memory_usage_mb": round(memory_mb, 2),
                    "avg_event_size_bytes": round(self.avg_event_size),
                },
                "client_stats": {
                    "active_connections": len(self.connections),
                    "ui_connections": len(self.ui_websockets),
                    "services": list(
                        set(conn.service for conn in self.connections.values())
                    ),
                },
                "performance": perf_report,
                "uptime": uptime,
                "port": self.port,
                "started_at": self.started_at.isoformat() + "Z",
            }

        @self.app.get("/version")
        async def version():
            """Version information endpoint."""
            return {
                "version": "1.0.0",
                "build_date": datetime.now(timezone.utc).isoformat() + "Z",
            }

        @self.app.get("/ui")
        async def ui():
            """Serve UI application."""
            # Load placeholder HTML for now
            ui_dist_path = Path(__file__).parent / "ui_dist" / "index.html"

            if ui_dist_path.exists():
                with open(ui_dist_path) as f:
                    html_content = f.read()
                return HTMLResponse(content=html_content)
            else:
                # Fallback placeholder
                html_content = (
                    """<!DOCTYPE html>
<html>
<head>
    <title>Mohnitor - Log Viewer</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        .container { max-width: 600px; margin: 0 auto; }
        .logo { font-size: 2em; color: #333; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">📊 Mohnitor</div>
        <h1>Log Viewer Active</h1>
        <p>Hub is running on port """
                    + str(self.port)
                    + """</p>
        <p>Connected services: """
                    + str(len(self.connections))
                    + """</p>
        <p>Total events: """
                    + str(len(self.event_buffer))
                    + """</p>
    </div>
</body>
</html>"""
                )
                return HTMLResponse(content=html_content)

        @self.app.websocket("/ws")
        async def websocket_endpoint(
            websocket: WebSocket,
            service: Optional[str] = None,
            type: Optional[str] = None,
            token: Optional[str] = None,
        ):
            """WebSocket endpoint for log streaming."""
            await websocket.accept()

            try:
                if type == "ui":
                    # UI connection
                    self.ui_websockets.add(websocket)
                    try:
                        # Send initial data to new UI client
                        await self._send_initial_ui_data(websocket)

                        while True:
                            # Wait for UI messages with timeout for periodic updates
                            try:
                                message = await asyncio.wait_for(
                                    websocket.receive_text(), timeout=30.0
                                )
                                await self._handle_ui_message(
                                    websocket, message
                                )
                            except asyncio.TimeoutError:
                                # Send periodic system stats
                                await self._send_system_stats(websocket)
                    except WebSocketDisconnect:
                        pass
                    finally:
                        self.ui_websockets.discard(websocket)

                elif service:
                    # Client connection
                    if self.host != "127.0.0.1" and token != self.token:
                        await websocket.close(
                            code=1008, reason="Authentication required"
                        )
                        return

                    connection_id = f"{service}-{len(self.connections)}"
                    connection = ClientConnection(
                        connection_id=connection_id,
                        service=service,
                        host=(
                            websocket.client.host
                            if websocket.client
                            else "unknown"
                        ),
                        pid=os.getpid(),  # TODO: Should use client PID from WebSocket headers or client-provided metadata
                        connected_at=datetime.now(timezone.utc),
                        last_seen=datetime.now(timezone.utc),
                        is_authenticated=True,
                    )

                    self.connections[connection_id] = connection
                    self.websockets[connection_id] = websocket

                    try:
                        while True:
                            message = await websocket.receive_text()
                            await self._handle_client_message(
                                connection_id, message
                            )
                    except WebSocketDisconnect:
                        pass
                    finally:
                        self.connections.pop(connection_id, None)
                        self.websockets.pop(connection_id, None)

                else:
                    await websocket.close(
                        code=1008, reason="Service parameter required"
                    )

            except Exception as e:
                print(f"WebSocket error: {e}")
                try:
                    await websocket.close()
                except:
                    pass

    async def _handle_client_message(self, connection_id: str, message: str):
        """Handle message from client connection."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "log_event":
                # Performance monitoring
                start_time = time.time() * 1000  # ms

                # Add log event to buffer
                payload = data["payload"]
                log_event = LogEvent.from_dict(payload)
                log_event.set_received_at()

                # Update event size estimate for optimization
                if self.performance_enabled:
                    event_size = memory_optimizer.estimate_event_size(
                        log_event
                    )
                    self.avg_event_size = (self.avg_event_size * 0.9) + (
                        event_size * 0.1
                    )

                # Add to ring buffer
                if len(self.event_buffer) >= self.buffer_size:
                    self.dropped_events += 1
                    if self.performance_enabled:
                        performance_monitor.record_event_dropped()
                else:
                    self.event_buffer.append(log_event)
                    if self.performance_enabled:
                        performance_monitor.record_event_processed()

                # Update connection stats
                if connection_id in self.connections:
                    self.connections[connection_id].events_sent += 1
                    self.connections[connection_id].update_heartbeat()

                # Optimized broadcast to UI clients
                if self.performance_enabled and self.ui_websockets:
                    # Use caching and batching for better performance
                    event_key = f"{log_event.service}:{log_event.level}:{hash(log_event.message)}"
                    cached_payload = event_cache.get(event_key)

                    if not cached_payload:
                        cached_payload = json.dumps(log_event.to_dict())
                        event_cache.put(event_key, cached_payload)

                    # Add to batch for efficient sending
                    message_batcher.add_message(
                        {
                            "type": "log_event",
                            "payload": json.loads(cached_payload),
                        }
                    )
                else:
                    # Fallback to direct broadcast
                    await self._broadcast_to_ui(
                        {"type": "log_event", "payload": log_event.to_dict()}
                    )

                # Record latency
                if self.performance_enabled:
                    latency = (time.time() * 1000) - start_time
                    performance_monitor.record_broadcast_latency(latency)

            elif msg_type == "heartbeat":
                # Update connection heartbeat
                if connection_id in self.connections:
                    self.connections[connection_id].update_heartbeat()

        except (json.JSONDecodeError, Exception) as e:
            print(f"Error handling client message: {e}")

    async def _broadcast_to_ui(self, message: dict):
        """Broadcast message to all UI WebSocket connections."""
        if not self.ui_websockets:
            return

        message_str = json.dumps(message)
        disconnected = set()

        for ws in self.ui_websockets:
            try:
                await ws.send_text(message_str)
            except:
                disconnected.add(ws)

        # Remove disconnected websockets
        for ws in disconnected:
            self.ui_websockets.discard(ws)

    def create_descriptor(self) -> HubDescriptor:
        """Create hub descriptor for discovery."""
        return HubDescriptor(
            host=self.host,
            port=self.port,
            pid=os.getpid(),
            token=self.token,
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

    def save_descriptor(self):
        """Save hub descriptor to file for discovery."""
        descriptor = self.create_descriptor()
        descriptor_path = get_hub_descriptor_path()

        # Ensure directory exists
        descriptor_path.parent.mkdir(parents=True, exist_ok=True)

        with open(descriptor_path, "w") as f:
            json.dump(descriptor.to_dict(), f, indent=2, default=str)

    async def _send_initial_ui_data(self, websocket: WebSocket):
        """Send initial data to newly connected UI client."""
        try:
            # Send recent log events (last 1000)
            recent_events = (
                list(self.event_buffer)[-1000:] if self.event_buffer else []
            )
            for event in recent_events:
                await websocket.send_text(
                    json.dumps(
                        {"type": "log_event", "payload": event.to_dict()}
                    )
                )

            # Send system stats
            await self._send_system_stats(websocket)

        except Exception as e:
            print(f"Error sending initial UI data: {e}")

    async def _send_system_stats(self, websocket: WebSocket):
        """Send system statistics to UI client."""
        try:
            uptime = (
                datetime.now(timezone.utc) - self.started_at
            ).total_seconds()
            memory_mb = (
                len(self.event_buffer) * 1024 / (1024 * 1024)
            )  # Rough estimate

            stats = {
                "type": "system_stats",
                "payload": {
                    "buffer_stats": {
                        "total_events": len(self.event_buffer),
                        "max_events": self.buffer_size,
                        "dropped_events": self.dropped_events,
                        "memory_usage_mb": round(memory_mb, 2),
                    },
                    "client_stats": {
                        "active_connections": len(self.connections),
                        "services": list(
                            set(
                                conn.service
                                for conn in self.connections.values()
                            )
                        ),
                    },
                    "uptime": uptime,
                    "started_at": self.started_at.isoformat() + "Z",
                },
            }

            await websocket.send_text(json.dumps(stats))

        except Exception as e:
            print(f"Error sending system stats: {e}")

    async def _handle_ui_message(self, websocket: WebSocket, message: str):
        """Handle messages from UI clients."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "get_logs":
                # Send filtered logs based on request
                filters = data.get("filters", {})
                await self._send_filtered_logs(websocket, filters)

            elif msg_type == "ping":
                # Respond to ping with pong
                await websocket.send_text(json.dumps({"type": "pong"}))

        except (json.JSONDecodeError, Exception) as e:
            print(f"Error handling UI message: {e}")

    async def _send_filtered_logs(self, websocket: WebSocket, filters: dict):
        """Send filtered log events to UI client."""
        try:
            service_filter = filters.get("services", [])
            level_filter = filters.get("level")
            search_term = filters.get("search", "").lower()

            filtered_events = []
            for event in self.event_buffer:
                # Apply filters
                if service_filter and event.service not in service_filter:
                    continue
                if level_filter and event.level != level_filter:
                    continue
                if search_term and search_term not in event.message.lower():
                    continue

                filtered_events.append(event)

            # Send filtered events
            for event in filtered_events[-1000:]:  # Limit to last 1000
                await websocket.send_text(
                    json.dumps(
                        {"type": "log_event", "payload": event.to_dict()}
                    )
                )

        except Exception as e:
            print(f"Error sending filtered logs: {e}")

    def run(self):
        """Run the hub server."""
        # Save descriptor for discovery
        self.save_descriptor()

        print(f"🚀 Mohnitor hub started at: http://{self.host}:{self.port}/ui")

        if uvicorn:
            # Run with uvicorn
            uvicorn.run(
                self.app, host=self.host, port=self.port, log_level="warning"
            )
        else:
            print(
                "⚠️  uvicorn not available. Install with: pip install mohflow[mohnitor]"
            )
