"""
Mohnitor client forwarder implementation.

Handles log forwarding to hub via WebSocket.
"""

import asyncio
import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None

from .types import LogEvent


class MohnitorForwardingHandler(logging.Handler):
    """Python logging handler that forwards to Mohnitor hub."""

    def __init__(
        self,
        service: str,
        hub_host: str = "127.0.0.1",
        hub_port: int = 17361,
        buffer_size: int = 20000,
    ):
        super().__init__()
        self.service = service
        self.hub_host = hub_host
        self.hub_port = hub_port
        self.buffer_size = buffer_size

        # Non-blocking queue for log events
        self.log_queue = queue.Queue(maxsize=buffer_size)
        self.is_connected = False
        self.should_stop = False

        # Start background sender thread
        self.sender_thread = threading.Thread(
            target=self._sender_loop, daemon=True
        )
        self.sender_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        """Emit log record to Mohnitor."""
        try:
            # Convert LogRecord to LogEvent
            log_event = LogEvent(
                timestamp=datetime.fromtimestamp(record.created, timezone.utc),
                level=record.levelname,
                service=self.service,
                message=record.getMessage(),
                logger=record.name,
                trace_id=getattr(record, "trace_id", None),
                context=getattr(record, "context", {}),
                source_host="localhost",  # Simplified
                source_pid=record.process,
            )

            # Add to queue (non-blocking)
            try:
                self.log_queue.put_nowait(
                    {"type": "log_event", "payload": log_event.to_dict()}
                )
            except queue.Full:
                # Drop event if queue is full
                pass

        except Exception:
            # Never crash on logging
            pass

    def _sender_loop(self) -> None:
        """Background thread that sends queued events to hub."""
        if not websockets:
            return

        while not self.should_stop:
            try:
                asyncio.run(self._send_events())
            except Exception:
                # Retry after delay
                time.sleep(5)

    async def _send_events(self) -> None:
        """Send queued events via WebSocket."""
        uri = f"ws://{self.hub_host}:{self.hub_port}/ws?service={self.service}"

        try:
            async with websockets.connect(uri) as websocket:
                self.is_connected = True

                # Send heartbeat first
                heartbeat = {
                    "type": "heartbeat",
                    "payload": {
                        "timestamp": datetime.now(timezone.utc).isoformat()
                        + "Z",
                        "pid": threading.get_ident(),
                        "events_queued": self.log_queue.qsize(),
                    },
                }
                await websocket.send(json.dumps(heartbeat))

                # Process queued events
                while not self.should_stop:
                    try:
                        # Get event from queue (with timeout)
                        try:
                            event = self.log_queue.get(timeout=1.0)
                            await websocket.send(json.dumps(event))
                            self.log_queue.task_done()
                        except queue.Empty:
                            # Send periodic heartbeat
                            heartbeat["payload"]["timestamp"] = (
                                datetime.now(timezone.utc).isoformat() + "Z"
                            )
                            heartbeat["payload"][
                                "events_queued"
                            ] = self.log_queue.qsize()
                            await websocket.send(json.dumps(heartbeat))

                    except websockets.exceptions.ConnectionClosed:
                        break

        except Exception:
            self.is_connected = False
            # Will retry in _sender_loop

    def close(self) -> None:
        """Close the handler and stop background thread."""
        self.should_stop = True
        if self.sender_thread.is_alive():
            self.sender_thread.join(timeout=2)
        super().close()
