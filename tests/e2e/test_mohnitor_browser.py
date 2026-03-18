"""
Mohnitor Headless Browser E2E Tests.

Uses Playwright to verify the Mohnitor UI renders correctly in a real
browser and that log events sent via WebSocket appear in the rendered page.

Run:  pytest tests/e2e/test_mohnitor_browser.py -v
"""

import asyncio
import json
import multiprocessing
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from mohflow.devui.hub import MohnitorHub, FastAPI
    import uvicorn

    HAS_MOHNITOR = FastAPI is not None and uvicorn is not None
except ImportError:
    HAS_MOHNITOR = False

requires_browser = pytest.mark.skipif(
    not (HAS_PLAYWRIGHT and HAS_MOHNITOR),
    reason="Playwright and/or Mohnitor dependencies not installed",
)


def _find_free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_hub(port: int, ready_event):
    """Run MohnitorHub in a subprocess. Sets ready_event once listening."""
    import uvicorn
    from mohflow.devui.hub import MohnitorHub, FastAPI
    from collections import deque

    hub = MohnitorHub.__new__(MohnitorHub)
    hub.host = "127.0.0.1"
    hub.port = port
    hub.buffer_size = 5000
    hub.started_at = datetime.now(timezone.utc)
    hub.event_buffer = deque(maxlen=5000)
    hub.dropped_events = 0
    hub.connections = {}
    hub.websockets = {}
    hub.ui_websockets = set()
    hub.token = None
    hub.performance_enabled = False
    hub.avg_event_size = 1024
    hub.app = FastAPI(title="Mohnitor Hub Browser Test", version="1.0.0")
    hub._setup_routes()

    config = uvicorn.Config(
        hub.app, host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)

    # Signal readiness after server starts
    original_startup = server.startup

    async def startup_with_signal(*args, **kwargs):
        await original_startup(*args, **kwargs)
        ready_event.set()

    server.startup = startup_with_signal
    server.run()


@pytest.fixture(scope="module")
def hub_server():
    """Start a real MohnitorHub in a subprocess, yield (host, port), then tear down."""
    port = _find_free_port()
    ready = multiprocessing.Event()

    proc = multiprocessing.Process(
        target=_run_hub, args=(port, ready), daemon=True
    )
    proc.start()

    # Wait up to 10s for hub to be ready
    if not ready.wait(timeout=10):
        proc.terminate()
        pytest.fail("Hub server failed to start within 10 seconds")

    # Double-check with HTTP probe
    import urllib.request

    for _ in range(20):
        try:
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/healthz", timeout=1
            )
            if resp.status == 200:
                break
        except Exception:
            time.sleep(0.25)
    else:
        proc.terminate()
        pytest.fail("Hub /healthz never became reachable")

    yield "127.0.0.1", port

    proc.terminate()
    proc.join(timeout=5)


@pytest.fixture(scope="module")
def browser_context():
    """Launch Playwright Chromium and yield a browser context."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context()

    yield context

    context.close()
    browser.close()
    pw.stop()


def _send_log_via_ws(
    host: str, port: int, service: str, level: str, message: str
):
    """Send a single log event to the hub via a quick WebSocket connection."""
    import websocket as ws_client

    url = f"ws://{host}:{port}/ws?service={service}"
    payload = {
        "type": "log_event",
        "payload": {
            "timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "level": level,
            "service": service,
            "message": message,
            "logger": "browser-test",
            "trace_id": None,
            "context": {},
            "source_host": "localhost",
            "source_pid": 12345,
        },
    }

    conn = ws_client.create_connection(url, timeout=5)
    conn.send(json.dumps(payload))
    time.sleep(0.1)
    conn.close()


def _send_log_via_http_ws(
    host: str, port: int, service: str, level: str, message: str
):
    """Send a log event using websocket-client library."""
    try:
        _send_log_via_ws(host, port, service, level, message)
    except ImportError:
        # Fallback: use Playwright's built-in WebSocket via a page evaluation
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@requires_browser
class TestMohnitorUIRendering:
    """Verify the Mohnitor UI loads and renders in a real browser."""

    def test_ui_page_loads(self, hub_server, browser_context):
        """The /ui page should load and contain 'Mohnitor' text."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )
            assert "Mohnitor" in page.title() or "Mohnitor" in page.content()
        finally:
            page.close()

    def test_ui_shows_hub_port(self, hub_server, browser_context):
        """The UI page should display the hub port number."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )
            content = page.content()
            assert str(port) in content
        finally:
            page.close()

    def test_ui_has_log_viewer_heading(self, hub_server, browser_context):
        """The UI page should have the 'Log Viewer Active' heading."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )
            heading = page.locator("h1")
            assert heading.count() > 0
            assert "Log Viewer" in heading.first.text_content()
        finally:
            page.close()


@requires_browser
class TestMohnitorHealthEndpoints:
    """Verify API endpoints respond correctly when hit from a browser."""

    def test_healthz_returns_json(self, hub_server, browser_context):
        """GET /healthz should return valid JSON with status healthy."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            resp = page.goto(f"http://{host}:{port}/healthz")
            assert resp.status == 200
            body = json.loads(
                page.content().split("<pre>")[-1].split("</pre>")[0]
                if "<pre>" in page.content()
                else page.locator("body").text_content()
            )
            assert body["status"] == "healthy"
        finally:
            page.close()

    def test_version_returns_json(self, hub_server, browser_context):
        """GET /version should return version info."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            resp = page.goto(f"http://{host}:{port}/version")
            assert resp.status == 200
            text = page.locator("body").text_content()
            body = json.loads(text)
            assert "version" in body
        finally:
            page.close()

    def test_system_returns_buffer_stats(self, hub_server, browser_context):
        """GET /system should return buffer_stats."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            resp = page.goto(f"http://{host}:{port}/system")
            assert resp.status == 200
            text = page.locator("body").text_content()
            body = json.loads(text)
            assert "buffer_stats" in body
            assert "client_stats" in body
        finally:
            page.close()


@requires_browser
class TestMohnitorWebSocketInBrowser:
    """Test WebSocket interactions from within the browser using page.evaluate."""

    def test_websocket_connection_from_browser(
        self, hub_server, browser_context
    ):
        """Browser-side JS can open a WebSocket to the hub."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )

            # Open a WebSocket from JS and verify it connects
            result = page.evaluate(
                """async () => {
                    return new Promise((resolve, reject) => {
                        const ws = new WebSocket(`ws://127.0.0.1:"""
                + str(port)
                + """/ws?type=ui`);
                        ws.onopen = () => {
                            ws.close();
                            resolve('connected');
                        };
                        ws.onerror = (e) => reject('error');
                        setTimeout(() => reject('timeout'), 5000);
                    });
                }"""
            )
            assert result == "connected"
        finally:
            page.close()

    def test_websocket_receives_initial_data(
        self, hub_server, browser_context
    ):
        """Browser-side WebSocket should receive initial system_stats message."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )

            # Connect via WebSocket and capture the first message
            result = page.evaluate(
                """async () => {
                    return new Promise((resolve, reject) => {
                        const ws = new WebSocket(`ws://127.0.0.1:"""
                + str(port)
                + """/ws?type=ui`);
                        const messages = [];
                        ws.onmessage = (event) => {
                            messages.push(JSON.parse(event.data));
                            // After receiving at least one message, wait a bit and resolve
                            setTimeout(() => {
                                ws.close();
                                resolve(messages);
                            }, 500);
                        };
                        ws.onerror = (e) => reject('error');
                        setTimeout(() => {
                            ws.close();
                            resolve(messages);
                        }, 3000);
                    });
                }"""
            )

            assert len(result) > 0
            # Should have at least system_stats
            types = [m["type"] for m in result]
            assert "system_stats" in types
        finally:
            page.close()

    def test_websocket_ping_pong_from_browser(
        self, hub_server, browser_context
    ):
        """Browser sends ping, hub replies with pong."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )

            result = page.evaluate(
                """async () => {
                    return new Promise((resolve, reject) => {
                        const ws = new WebSocket(`ws://127.0.0.1:"""
                + str(port)
                + """/ws?type=ui`);
                        let gotPong = false;
                        ws.onopen = () => {
                            // Wait a moment for initial data, then send ping
                            setTimeout(() => {
                                ws.send(JSON.stringify({type: 'ping'}));
                            }, 500);
                        };
                        ws.onmessage = (event) => {
                            const msg = JSON.parse(event.data);
                            if (msg.type === 'pong') {
                                gotPong = true;
                                ws.close();
                                resolve('pong_received');
                            }
                        };
                        ws.onerror = (e) => reject('error');
                        setTimeout(() => {
                            ws.close();
                            resolve(gotPong ? 'pong_received' : 'no_pong');
                        }, 5000);
                    });
                }"""
            )
            assert result == "pong_received"
        finally:
            page.close()


@requires_browser
class TestMohnitorLiveLogDisplay:
    """Test that logs sent to the hub appear when queried from the browser."""

    def test_logs_visible_via_system_endpoint(
        self, hub_server, browser_context
    ):
        """After sending logs, /system shows them in total_events count."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            # Send a log event via WebSocket from browser JS
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )

            page.evaluate(
                """async () => {
                    return new Promise((resolve, reject) => {
                        const ws = new WebSocket(`ws://127.0.0.1:"""
                + str(port)
                + """/ws?service=browser-svc`);
                        ws.onopen = () => {
                            const msg = {
                                type: 'log_event',
                                payload: {
                                    timestamp: new Date().toISOString(),
                                    level: 'INFO',
                                    service: 'browser-svc',
                                    message: 'hello from browser',
                                    logger: 'browser-test',
                                    trace_id: null,
                                    context: {},
                                    source_host: 'localhost',
                                    source_pid: 1
                                }
                            };
                            ws.send(JSON.stringify(msg));
                            setTimeout(() => { ws.close(); resolve('sent'); }, 200);
                        };
                        ws.onerror = () => reject('error');
                        setTimeout(() => reject('timeout'), 5000);
                    });
                }"""
            )

            time.sleep(0.5)

            # Check /system endpoint
            resp = page.goto(f"http://{host}:{port}/system")
            text = page.locator("body").text_content()
            data = json.loads(text)
            assert data["buffer_stats"]["total_events"] > 0
        finally:
            page.close()

    def test_log_event_received_by_ui_websocket(
        self, hub_server, browser_context
    ):
        """UI WebSocket in the browser receives a log event sent by a client."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )

            # 1) Open UI WebSocket
            # 2) Open client WebSocket, send a log
            # 3) Verify UI WebSocket received the log event
            result = page.evaluate(
                """async () => {
                    return new Promise((resolve, reject) => {
                        const received = [];

                        // UI connection
                        const uiWs = new WebSocket(`ws://127.0.0.1:"""
                + str(port)
                + """/ws?type=ui`);

                        uiWs.onmessage = (event) => {
                            const msg = JSON.parse(event.data);
                            received.push(msg);
                        };

                        uiWs.onopen = () => {
                            // Wait for initial data, then send a log from a "client"
                            setTimeout(() => {
                                const clientWs = new WebSocket(`ws://127.0.0.1:"""
                + str(port)
                + """/ws?service=js-client`);
                                clientWs.onopen = () => {
                                    const logMsg = {
                                        type: 'log_event',
                                        payload: {
                                            timestamp: new Date().toISOString(),
                                            level: 'ERROR',
                                            service: 'js-client',
                                            message: 'browser-injected-error',
                                            logger: 'browser',
                                            trace_id: 'browser-trace-1',
                                            context: {browser: true},
                                            source_host: 'localhost',
                                            source_pid: 2
                                        }
                                    };
                                    clientWs.send(JSON.stringify(logMsg));
                                    setTimeout(() => clientWs.close(), 200);
                                };
                            }, 1000);

                            // Collect for 3 seconds then resolve
                            setTimeout(() => {
                                uiWs.close();
                                resolve(received);
                            }, 3000);
                        };

                        uiWs.onerror = () => reject('ui_ws_error');
                        setTimeout(() => { uiWs.close(); resolve(received); }, 5000);
                    });
                }"""
            )

            # Find the log event we sent
            log_events = [
                m
                for m in result
                if m.get("type") == "log_event"
                and m.get("payload", {}).get("message")
                == "browser-injected-error"
            ]
            assert len(log_events) >= 1
            payload = log_events[0]["payload"]
            assert payload["service"] == "js-client"
            assert payload["level"] == "ERROR"
            assert payload["trace_id"] == "browser-trace-1"
        finally:
            page.close()


@requires_browser
class TestMohnitorUIAccessibility:
    """Basic accessibility and structure checks on the rendered UI."""

    def test_page_has_valid_html(self, hub_server, browser_context):
        """The UI page should have a proper HTML structure."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )

            # Should have html, head, body
            assert page.locator("html").count() == 1
            assert page.locator("head").count() == 1
            assert page.locator("body").count() == 1
            assert page.locator("title").count() == 1
        finally:
            page.close()

    def test_page_title_contains_mohnitor(self, hub_server, browser_context):
        """Page title should reference Mohnitor."""
        host, port = hub_server
        page = browser_context.new_page()

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )
            assert "Mohnitor" in page.title()
        finally:
            page.close()

    def test_no_console_errors_on_load(self, hub_server, browser_context):
        """The UI page should load without JavaScript console errors."""
        host, port = hub_server
        page = browser_context.new_page()

        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        try:
            page.goto(
                f"http://{host}:{port}/ui", wait_until="domcontentloaded"
            )
            time.sleep(1)  # Let any async JS settle
            assert len(errors) == 0, f"Console errors found: {errors}"
        finally:
            page.close()
