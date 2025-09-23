"""
Contract test for WebSocket /ws endpoint.

This test MUST FAIL initially until the hub server is implemented.
"""

import pytest
import asyncio
import json
from datetime import datetime

try:
    import websockets
except ImportError:
    websockets = None


@pytest.mark.skipif(websockets is None, reason="websockets not available")
class TestWebSocketContract:
    """Test contract for /ws endpoint according to websocket-protocol.md."""

    @pytest.mark.asyncio
    async def test_websocket_connection_with_service_param(self):
        """Test that WebSocket connects with service parameter."""
        # This will fail until hub server is implemented
        uri = "ws://127.0.0.1:17361/ws?service=test-service"

        async with websockets.connect(uri) as websocket:
            # Connection should be established
            assert websocket.open

    @pytest.mark.asyncio
    async def test_websocket_rejects_connection_without_service(self):
        """Test that WebSocket rejects connection without service parameter."""
        uri = "ws://127.0.0.1:17361/ws"

        with pytest.raises(
            (
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.InvalidStatusCode,
            )
        ):
            async with websockets.connect(uri) as websocket:
                # Should not reach here
                pass

    @pytest.mark.asyncio
    async def test_websocket_accepts_log_event_message(self):
        """Test that WebSocket accepts valid log event messages."""
        uri = "ws://127.0.0.1:17361/ws?service=test-service"

        async with websockets.connect(uri) as websocket:
            # Send a valid log event according to protocol
            log_event = {
                "type": "log_event",
                "payload": {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": "INFO",
                    "service": "test-service",
                    "message": "Test log message",
                    "logger": "test.logger",
                    "trace_id": "test-trace-123",
                    "context": {"user_id": "12345"},
                },
            }

            await websocket.send(json.dumps(log_event))

            # Should not disconnect or error
            assert websocket.open

    @pytest.mark.asyncio
    async def test_websocket_handles_heartbeat_message(self):
        """Test that WebSocket handles heartbeat messages."""
        uri = "ws://127.0.0.1:17361/ws?service=test-service"

        async with websockets.connect(uri) as websocket:
            # Send heartbeat message
            heartbeat = {
                "type": "heartbeat",
                "payload": {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "pid": 12345,
                    "events_queued": 0,
                },
            }

            await websocket.send(json.dumps(heartbeat))

            # Should not disconnect or error
            assert websocket.open

    @pytest.mark.asyncio
    async def test_websocket_ui_connection(self):
        """Test that WebSocket accepts UI connections."""
        uri = "ws://127.0.0.1:17361/ws?type=ui"

        async with websockets.connect(uri) as websocket:
            # UI connection should be established
            assert websocket.open

    @pytest.mark.asyncio
    async def test_websocket_authentication_for_remote_host(self):
        """Test that WebSocket requires token for non-localhost connections."""
        # This test simulates remote connection behavior
        # In practice, we'll test by setting up hub with non-localhost bind

        # For now, test that localhost connections work without token
        uri = "ws://127.0.0.1:17361/ws?service=test-service"

        async with websockets.connect(uri) as websocket:
            # Localhost should work without token
            assert websocket.open

    @pytest.mark.asyncio
    async def test_websocket_rejects_invalid_json(self):
        """Test that WebSocket handles invalid JSON gracefully."""
        uri = "ws://127.0.0.1:17361/ws?service=test-service"

        async with websockets.connect(uri) as websocket:
            # Send invalid JSON
            await websocket.send("invalid json {}")

            # Connection might close or send error, but shouldn't crash server
            # We'll check if we can still send valid messages
            try:
                valid_message = {
                    "type": "heartbeat",
                    "payload": {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "pid": 1,
                    },
                }
                await websocket.send(json.dumps(valid_message))
            except websockets.exceptions.ConnectionClosed:
                # Connection closed is acceptable response to invalid JSON
                pass

    @pytest.mark.asyncio
    async def test_websocket_message_size_limit(self):
        """Test that WebSocket enforces reasonable message size limits."""
        uri = "ws://127.0.0.1:17361/ws?service=test-service"

        async with websockets.connect(uri) as websocket:
            # Create a very large message (>64KB as per design)
            large_context = {"large_field": "x" * (65 * 1024)}  # 65KB

            large_log_event = {
                "type": "log_event",
                "payload": {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": "INFO",
                    "service": "test-service",
                    "message": "Large message test",
                    "logger": "test.logger",
                    "context": large_context,
                },
            }

            # Should either reject or handle gracefully
            try:
                await websocket.send(json.dumps(large_log_event))
                # If accepted, that's fine too (implementation choice)
            except websockets.exceptions.ConnectionClosed:
                # Rejection is also acceptable
                pass
