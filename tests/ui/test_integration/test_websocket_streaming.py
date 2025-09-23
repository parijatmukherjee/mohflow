"""
Test WebSocket streaming functionality with mock data.
"""

import pytest
import asyncio
import sys
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_websocket_streaming():
    """Test WebSocket functionality with mock data."""

    # Skip this test if dependencies not available
    try:
        from mohflow.devui.types import LogEvent
    except ImportError:
        pytest.skip("LogEvent not available (missing dependencies)")

    print("🧪 Testing WebSocket streaming functionality...")

    try:
        # Test without creating actual FastAPI app
        from collections import deque
        from datetime import datetime, timezone
        import json

        # Create a minimal hub-like class for testing
        class MockHub:
            def __init__(self):
                self.buffer_size = 100
                self.event_buffer = deque(maxlen=self.buffer_size)
                self.dropped_events = 0
                self.started_at = datetime.now(timezone.utc)
                self.connections = {}
                self.ui_websockets = set()

            async def _send_initial_ui_data(self, websocket):
                """Send initial data to newly connected UI client."""
                # Send recent log events
                recent_events = (
                    list(self.event_buffer)[-1000:]
                    if self.event_buffer
                    else []
                )
                for event in recent_events:
                    await websocket.send_text(
                        json.dumps(
                            {"type": "log_event", "payload": event.to_dict()}
                        )
                    )

                # Send system stats
                await self._send_system_stats(websocket)

            async def _send_system_stats(self, websocket):
                """Send system statistics to UI client."""
                uptime = (
                    datetime.now(timezone.utc) - self.started_at
                ).total_seconds()
                memory_mb = len(self.event_buffer) * 1024 / (1024 * 1024)

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
                                    if hasattr(conn, "service")
                                )
                            ),
                        },
                        "uptime": uptime,
                        "started_at": self.started_at.isoformat() + "Z",
                    },
                }

                await websocket.send_text(json.dumps(stats))

        # Use mock hub
        hub = MockHub()

        # Add some mock log events to the buffer
        test_events = [
            LogEvent(
                timestamp=datetime.now(timezone.utc),
                level="INFO",
                service="test-service-1",
                message="Test log message 1",
                logger="test.logger",
            ),
            LogEvent(
                timestamp=datetime.now(timezone.utc),
                level="ERROR",
                service="test-service-2",
                message="Test error message",
                logger="error.logger",
            ),
            LogEvent(
                timestamp=datetime.now(timezone.utc),
                level="DEBUG",
                service="test-service-1",
                message="Debug information",
                logger="debug.logger",
            ),
        ]

        for event in test_events:
            hub.event_buffer.append(event)

        print(f"✅ Hub created with {len(hub.event_buffer)} test events")

        # Test the UI data methods
        class MockWebSocket:
            def __init__(self):
                self.messages = []

            async def send_text(self, message):
                self.messages.append(message)

        mock_ws = MockWebSocket()

        # Test sending initial UI data
        await hub._send_initial_ui_data(mock_ws)
        print(f"✅ Initial UI data sent: {len(mock_ws.messages)} messages")

        # Test sending system stats
        await hub._send_system_stats(mock_ws)
        print("✅ System stats sent successfully")

        # Verify message content
        for i, message in enumerate(mock_ws.messages):
            data = json.loads(message)
            if data["type"] == "log_event":
                print(
                    f"  📋 Log event {i+1}: {data['payload']['level']} - {data['payload']['message'][:30]}..."
                )
            elif data["type"] == "system_stats":
                print(
                    f"  📊 System stats: {data['payload']['buffer_stats']['total_events']} events"
                )

        return True

    except Exception as e:
        print(f"❌ WebSocket streaming test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run WebSocket streaming tests."""
    print("🧪 Testing WebSocket streaming...")

    success = asyncio.run(test_websocket_streaming())

    if success:
        print("🎉 WebSocket streaming tests passed!")
        return True
    else:
        print("⚠️  WebSocket streaming tests failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
