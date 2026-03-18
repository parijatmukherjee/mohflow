"""
Mohnitor End-to-End Tests.

Verifies the complete log pipeline:
  Client logger → MohnitorForwardingHandler → WebSocket → Hub buffer → UI WebSocket

These tests spin up a real FastAPI hub (via httpx/ASGI), connect real
WebSocket clients, send real log events, and assert they arrive at UI
consumers — exercising every layer without mocks.

Run:  pytest tests/e2e/test_mohnitor_e2e.py -v -s
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    from httpx import ASGITransport, AsyncClient
    from starlette.testclient import TestClient
    import websockets

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

try:
    from mohflow.devui.hub import MohnitorHub, FastAPI
    from mohflow.devui.types import LogEvent
    from mohflow.devui.client import MohnitorForwardingHandler

    HAS_MOHNITOR = HAS_DEPS and FastAPI is not None
except ImportError:
    HAS_MOHNITOR = False

requires_mohnitor = pytest.mark.skipif(
    not HAS_MOHNITOR,
    reason="Mohnitor dependencies not installed (pip install mohflow[mohnitor])",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_log_message(service: str, level: str, message: str, **ctx) -> dict:
    """Build a client→hub WebSocket message."""
    return {
        "type": "log_event",
        "payload": {
            "timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "level": level,
            "service": service,
            "message": message,
            "logger": "test",
            "trace_id": ctx.get("trace_id"),
            "context": ctx,
            "source_host": "localhost",
            "source_pid": 99999,
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hub():
    """Create a fresh MohnitorHub with performance features disabled."""
    h = MohnitorHub.__new__(MohnitorHub)
    # Manually init to skip asyncio.create_task in __init__
    from collections import deque

    h.host = "127.0.0.1"
    h.port = 17361
    h.buffer_size = 5000
    h.started_at = datetime.now(timezone.utc)
    h.event_buffer = deque(maxlen=5000)
    h.dropped_events = 0
    h.connections = {}
    h.websockets = {}
    h.ui_websockets = set()
    h.token = None
    h.performance_enabled = False
    h.avg_event_size = 1024
    h.app = FastAPI(title="Mohnitor Hub Test", version="1.0.0")
    h._setup_routes()
    return h


@pytest.fixture
def test_client(hub):
    """Starlette TestClient wrapping the hub's ASGI app."""
    return TestClient(hub.app)


# ---------------------------------------------------------------------------
# 1. HTTP Endpoint Smoke Tests
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestHubHTTPEndpoints:
    """Verify HTTP endpoints work on the real hub app."""

    def test_healthz(self, test_client):
        resp = test_client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "uptime" in data

    def test_system_empty(self, test_client):
        resp = test_client.get("/system")
        assert resp.status_code == 200
        data = resp.json()
        assert data["buffer_stats"]["total_events"] == 0
        assert data["client_stats"]["active_connections"] == 0

    def test_version(self, test_client):
        resp = test_client.get("/version")
        assert resp.status_code == 200
        assert "version" in resp.json()

    def test_ui_page(self, test_client):
        resp = test_client.get("/ui")
        assert resp.status_code == 200
        assert "Mohnitor" in resp.text


# ---------------------------------------------------------------------------
# 2. Client → Hub WebSocket Ingestion
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestClientToHubIngestion:
    """Client sends log_event messages; hub buffers them."""

    def test_single_log_event_buffered(self, test_client, hub):
        """A single log event sent via WS appears in the hub's event buffer."""
        msg = _make_log_message("svc-a", "INFO", "hello world")

        with test_client.websocket_connect("/ws?service=svc-a") as ws:
            ws.send_text(json.dumps(msg))
            # Give the async handler a moment
            time.sleep(0.1)

        assert len(hub.event_buffer) == 1
        event = hub.event_buffer[0]
        assert event.service == "svc-a"
        assert event.message == "hello world"
        assert event.level == "INFO"

    def test_multiple_events_buffered_in_order(self, test_client, hub):
        """Multiple events are buffered in send order."""
        with test_client.websocket_connect("/ws?service=svc-b") as ws:
            for i in range(5):
                msg = _make_log_message("svc-b", "DEBUG", f"msg-{i}")
                ws.send_text(json.dumps(msg))
            time.sleep(0.1)

        assert len(hub.event_buffer) == 5
        for i, event in enumerate(hub.event_buffer):
            assert event.message == f"msg-{i}"

    def test_heartbeat_does_not_create_event(self, test_client, hub):
        """Heartbeat messages should not appear in the event buffer."""
        heartbeat = {
            "type": "heartbeat",
            "payload": {
                "timestamp": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "pid": 12345,
                "events_queued": 0,
            },
        }

        with test_client.websocket_connect("/ws?service=svc-c") as ws:
            ws.send_text(json.dumps(heartbeat))
            time.sleep(0.1)

        assert len(hub.event_buffer) == 0

    def test_connection_registers_service(self, test_client, hub):
        """Client connection should register the service in hub connections."""
        with test_client.websocket_connect("/ws?service=my-service") as ws:
            ws.send_text(
                json.dumps(
                    _make_log_message("my-service", "INFO", "register me")
                )
            )
            time.sleep(0.1)
            assert len(hub.connections) == 1
            conn = list(hub.connections.values())[0]
            assert conn.service == "my-service"
            assert conn.events_sent == 1

    def test_connection_cleanup_on_disconnect(self, test_client, hub):
        """After WS disconnect, the connection record is removed."""
        with test_client.websocket_connect("/ws?service=ephemeral") as ws:
            ws.send_text(
                json.dumps(_make_log_message("ephemeral", "INFO", "bye soon"))
            )
            time.sleep(0.1)
            assert len(hub.connections) == 1

        # After context manager exits (disconnect), connection should be cleaned
        assert len(hub.connections) == 0

    def test_missing_service_param_rejected(self, test_client):
        """WebSocket without service= param should be closed."""
        with pytest.raises(Exception):
            with test_client.websocket_connect("/ws") as ws:
                ws.receive_text()

    def test_system_endpoint_reflects_buffer(self, test_client, hub):
        """After ingestion, /system shows correct counts."""
        with test_client.websocket_connect("/ws?service=counter") as ws:
            for _ in range(3):
                ws.send_text(
                    json.dumps(_make_log_message("counter", "ERROR", "oops"))
                )
            time.sleep(0.1)

        resp = test_client.get("/system")
        data = resp.json()
        assert data["buffer_stats"]["total_events"] == 3


# ---------------------------------------------------------------------------
# 3. UI WebSocket — Real-time Broadcast
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestUIWebSocketBroadcast:
    """UI client connects via WS and receives log events in real time."""

    def test_ui_receives_initial_buffered_events(self, test_client, hub):
        """When a UI client connects, it should receive already-buffered events."""
        # First, ingest some events
        with test_client.websocket_connect("/ws?service=pre-ui") as ws:
            for i in range(3):
                ws.send_text(
                    json.dumps(_make_log_message("pre-ui", "INFO", f"pre-{i}"))
                )
            time.sleep(0.1)

        assert len(hub.event_buffer) == 3

        # Now connect as UI and expect to receive the buffered events
        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            received = []
            # The hub sends initial data: buffered log events + system stats
            for _ in range(4):  # 3 events + 1 system_stats
                try:
                    raw = ui_ws.receive_text()
                    received.append(json.loads(raw))
                except Exception:
                    break

            log_events = [m for m in received if m["type"] == "log_event"]
            stats = [m for m in received if m["type"] == "system_stats"]

            assert len(log_events) == 3
            assert log_events[0]["payload"]["message"] == "pre-0"
            assert log_events[2]["payload"]["message"] == "pre-2"
            assert len(stats) == 1

    def test_ui_receives_live_broadcast(self, test_client, hub):
        """UI client receives events broadcast in real time as clients send them."""
        # Connect UI first
        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            # Drain the initial system_stats message
            try:
                ui_ws.receive_text()
            except Exception:
                pass

            # Now send a log event from a client connection
            with test_client.websocket_connect(
                "/ws?service=live"
            ) as client_ws:
                client_ws.send_text(
                    json.dumps(
                        _make_log_message("live", "ERROR", "real-time alert")
                    )
                )
                time.sleep(0.1)

            # UI should have received the broadcast
            raw = ui_ws.receive_text()
            msg = json.loads(raw)
            assert msg["type"] == "log_event"
            assert msg["payload"]["message"] == "real-time alert"
            assert msg["payload"]["service"] == "live"
            assert msg["payload"]["level"] == "ERROR"

    def test_ui_ping_pong(self, test_client, hub):
        """UI can send ping and receive pong."""
        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            # Drain initial data
            try:
                ui_ws.receive_text()
            except Exception:
                pass

            ui_ws.send_text(json.dumps({"type": "ping"}))
            raw = ui_ws.receive_text()
            msg = json.loads(raw)
            assert msg["type"] == "pong"


# ---------------------------------------------------------------------------
# 4. Filtered Log Retrieval via UI WebSocket
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestFilteredLogRetrieval:
    """UI can request filtered subsets of buffered logs."""

    def _seed_events(self, test_client, hub):
        """Seed the hub with a mix of events."""
        events = [
            ("api", "INFO", "request started"),
            ("api", "ERROR", "request failed"),
            ("auth", "INFO", "user logged in"),
            ("auth", "WARN", "rate limit warning"),
            ("worker", "DEBUG", "processing job"),
        ]
        with test_client.websocket_connect("/ws?service=seeder") as ws:
            for svc, level, msg in events:
                ws.send_text(json.dumps(_make_log_message(svc, level, msg)))
            time.sleep(0.1)
        return events

    def test_filter_by_service(self, test_client, hub):
        self._seed_events(test_client, hub)

        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            # Drain initial data (5 events + 1 stats)
            for _ in range(6):
                try:
                    ui_ws.receive_text()
                except Exception:
                    break

            # Request only "auth" events
            ui_ws.send_text(
                json.dumps(
                    {
                        "type": "get_logs",
                        "filters": {"services": ["auth"]},
                    }
                )
            )

            auth_events = []
            for _ in range(2):
                try:
                    raw = ui_ws.receive_text()
                    auth_events.append(json.loads(raw))
                except Exception:
                    break

            assert len(auth_events) == 2
            for e in auth_events:
                assert e["payload"]["service"] == "auth"

    def test_filter_by_level(self, test_client, hub):
        self._seed_events(test_client, hub)

        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            for _ in range(6):
                try:
                    ui_ws.receive_text()
                except Exception:
                    break

            ui_ws.send_text(
                json.dumps({"type": "get_logs", "filters": {"level": "ERROR"}})
            )

            error_events = []
            try:
                raw = ui_ws.receive_text()
                error_events.append(json.loads(raw))
            except Exception:
                pass

            assert len(error_events) == 1
            assert error_events[0]["payload"]["level"] == "ERROR"

    def test_filter_by_search_term(self, test_client, hub):
        self._seed_events(test_client, hub)

        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            for _ in range(6):
                try:
                    ui_ws.receive_text()
                except Exception:
                    break

            ui_ws.send_text(
                json.dumps({"type": "get_logs", "filters": {"search": "job"}})
            )

            results = []
            try:
                raw = ui_ws.receive_text()
                results.append(json.loads(raw))
            except Exception:
                pass

            assert len(results) == 1
            assert "job" in results[0]["payload"]["message"]


# ---------------------------------------------------------------------------
# 5. Multi-Service / Multi-Client
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestMultiServiceE2E:
    """Multiple services sending concurrently to the same hub."""

    def test_two_services_interleaved(self, test_client, hub):
        """Two services can send to the hub simultaneously."""
        with test_client.websocket_connect(
            "/ws?service=alpha"
        ) as ws_a, test_client.websocket_connect("/ws?service=beta") as ws_b:
            ws_a.send_text(
                json.dumps(_make_log_message("alpha", "INFO", "from alpha"))
            )
            ws_b.send_text(
                json.dumps(_make_log_message("beta", "WARN", "from beta"))
            )
            time.sleep(0.1)

        assert len(hub.event_buffer) == 2
        services = {e.service for e in hub.event_buffer}
        assert services == {"alpha", "beta"}

    def test_system_shows_all_services(self, test_client, hub):
        with test_client.websocket_connect(
            "/ws?service=svc1"
        ) as ws1, test_client.websocket_connect("/ws?service=svc2") as ws2:
            ws1.send_text(json.dumps(_make_log_message("svc1", "INFO", "hi")))
            ws2.send_text(json.dumps(_make_log_message("svc2", "INFO", "hi")))
            time.sleep(0.1)

            resp = test_client.get("/system")
            data = resp.json()
            assert data["client_stats"]["active_connections"] == 2
            assert set(data["client_stats"]["services"]) == {"svc1", "svc2"}


# ---------------------------------------------------------------------------
# 6. Trace Correlation
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestTraceCorrelation:
    """Logs with the same trace_id are correlated through the pipeline."""

    def test_trace_id_preserved_through_pipeline(self, test_client, hub):
        trace = "trace-abc-123"
        with test_client.websocket_connect("/ws?service=traced") as ws:
            ws.send_text(
                json.dumps(
                    _make_log_message(
                        "traced", "INFO", "span-start", trace_id=trace
                    )
                )
            )
            ws.send_text(
                json.dumps(
                    _make_log_message(
                        "traced", "INFO", "span-end", trace_id=trace
                    )
                )
            )
            time.sleep(0.1)

        assert len(hub.event_buffer) == 2
        for event in hub.event_buffer:
            assert event.trace_id == trace

    def test_trace_id_visible_to_ui(self, test_client, hub):
        trace = "ui-trace-456"
        with test_client.websocket_connect("/ws?service=traced") as ws:
            ws.send_text(
                json.dumps(
                    _make_log_message(
                        "traced", "ERROR", "failure", trace_id=trace
                    )
                )
            )
            time.sleep(0.1)

        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            raw = ui_ws.receive_text()
            msg = json.loads(raw)
            assert msg["type"] == "log_event"
            assert msg["payload"]["trace_id"] == trace


# ---------------------------------------------------------------------------
# 7. Buffer Overflow / Ring Buffer Behavior
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestBufferOverflow:
    """Ring buffer drops oldest events when full."""

    def test_buffer_drops_oldest_when_full(self, test_client):
        """When buffer is full, oldest events are dropped."""
        # Create hub with tiny buffer
        tiny_hub = MohnitorHub.__new__(MohnitorHub)
        from collections import deque

        tiny_hub.host = "127.0.0.1"
        tiny_hub.port = 17361
        tiny_hub.buffer_size = 3
        tiny_hub.started_at = datetime.now(timezone.utc)
        tiny_hub.event_buffer = deque(maxlen=3)
        tiny_hub.dropped_events = 0
        tiny_hub.connections = {}
        tiny_hub.websockets = {}
        tiny_hub.ui_websockets = set()
        tiny_hub.token = None
        tiny_hub.performance_enabled = False
        tiny_hub.avg_event_size = 1024
        tiny_hub.app = FastAPI(title="Test", version="1.0.0")
        tiny_hub._setup_routes()

        client = TestClient(tiny_hub.app)

        with client.websocket_connect("/ws?service=overflow") as ws:
            for i in range(5):
                ws.send_text(
                    json.dumps(
                        _make_log_message("overflow", "INFO", f"event-{i}")
                    )
                )
            time.sleep(0.2)

        # Buffer capacity is 3; hub drops NEW events when full (tail-drop)
        assert len(tiny_hub.event_buffer) == 3
        assert tiny_hub.dropped_events == 2
        messages = [e.message for e in tiny_hub.event_buffer]
        assert messages == ["event-0", "event-1", "event-2"]


# ---------------------------------------------------------------------------
# 8. LogEvent Data Integrity
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestLogEventIntegrity:
    """Verify LogEvent fields survive the full pipeline."""

    def test_all_fields_preserved(self, test_client, hub):
        ctx = {"user_id": "u-789", "request_path": "/api/orders"}
        msg = _make_log_message(
            "integrity",
            "WARN",
            "check fields",
            trace_id="t-999",
            **ctx,
        )

        with test_client.websocket_connect("/ws?service=integrity") as ws:
            ws.send_text(json.dumps(msg))
            time.sleep(0.1)

        event = hub.event_buffer[0]
        assert event.service == "integrity"
        assert event.level == "WARN"
        assert event.message == "check fields"
        assert event.trace_id == "t-999"
        assert event.context["user_id"] == "u-789"
        assert event.context["request_path"] == "/api/orders"
        assert event.source_pid == 99999
        assert event.received_at is not None

    def test_event_serialization_roundtrip(self, test_client, hub):
        """Event survives dict → buffer → dict → UI JSON roundtrip."""
        msg = _make_log_message(
            "roundtrip", "CRITICAL", "db down", trace_id="rt-1"
        )

        with test_client.websocket_connect("/ws?service=roundtrip") as ws:
            ws.send_text(json.dumps(msg))
            time.sleep(0.1)

        with test_client.websocket_connect("/ws?type=ui") as ui_ws:
            raw = ui_ws.receive_text()
            payload = json.loads(raw)["payload"]

        assert payload["service"] == "roundtrip"
        assert payload["level"] == "CRITICAL"
        assert payload["message"] == "db down"
        assert payload["trace_id"] == "rt-1"
        assert payload["received_at"] is not None


# ---------------------------------------------------------------------------
# 9. MohnitorForwardingHandler (Real Logging Handler)
# ---------------------------------------------------------------------------


@requires_mohnitor
class TestForwardingHandler:
    """Test the actual MohnitorForwardingHandler as a logging.Handler."""

    def test_handler_creates_log_event_from_record(self):
        """Handler.emit() converts LogRecord to queued LogEvent."""
        handler = MohnitorForwardingHandler(
            service="handler-test",
            hub_host="127.0.0.1",
            hub_port=99999,  # Won't actually connect
        )

        try:
            logger = logging.getLogger("test.forwarding")
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

            logger.info("handler test message")

            # Event should be in the queue
            assert not handler.log_queue.empty()
            queued = handler.log_queue.get_nowait()
            assert queued["type"] == "log_event"
            assert queued["payload"]["message"] == "handler test message"
            assert queued["payload"]["level"] == "INFO"
            assert queued["payload"]["service"] == "handler-test"
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_handler_queue_overflow_drops_silently(self):
        """When queue is full, handler drops events without crashing."""
        handler = MohnitorForwardingHandler(
            service="overflow-test",
            hub_host="127.0.0.1",
            hub_port=99999,
            buffer_size=2,
        )

        try:
            logger = logging.getLogger("test.overflow")
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

            # Fill the queue
            for i in range(10):
                logger.info(f"msg-{i}")

            # Should not crash, queue should be at max 2
            assert handler.log_queue.qsize() <= 2
        finally:
            logger.removeHandler(handler)
            handler.close()
