"""Tests for devui/client.py to improve coverage."""

import logging
import queue
import pytest
from unittest.mock import patch, MagicMock
from mohflow.devui.client import MohnitorForwardingHandler


class TestMohnitorForwardingHandler:
    def test_init(self):
        with patch.object(
            MohnitorForwardingHandler,
            "_sender_loop",
        ):
            handler = MohnitorForwardingHandler(service="test")
            assert handler.service == "test"
            assert handler.hub_host == "127.0.0.1"
            assert handler.hub_port == 17361
            assert handler.is_connected is False
            handler.should_stop = True

    def test_emit_enqueues(self):
        with patch.object(
            MohnitorForwardingHandler,
            "_sender_loop",
        ):
            handler = MohnitorForwardingHandler(service="test")
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="hello",
                args=None,
                exc_info=None,
            )
            handler.emit(record)
            assert handler.log_queue.qsize() == 1
            handler.should_stop = True

    def test_emit_queue_full(self):
        with patch.object(
            MohnitorForwardingHandler,
            "_sender_loop",
        ):
            handler = MohnitorForwardingHandler(service="test", buffer_size=1)
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="hello",
                args=None,
                exc_info=None,
            )
            handler.emit(record)
            handler.emit(record)  # Queue full
            assert handler.log_queue.qsize() == 1
            handler.should_stop = True

    def test_emit_error_suppressed(self):
        with patch.object(
            MohnitorForwardingHandler,
            "_sender_loop",
        ):
            handler = MohnitorForwardingHandler(service="test")
            # Break LogEvent creation
            with patch(
                "mohflow.devui.client.LogEvent",
                side_effect=Exception("boom"),
            ):
                record = logging.LogRecord(
                    name="test",
                    level=logging.INFO,
                    pathname="test.py",
                    lineno=1,
                    msg="hello",
                    args=None,
                    exc_info=None,
                )
                handler.emit(record)  # Should not raise
            handler.should_stop = True

    def test_close(self):
        with patch.object(
            MohnitorForwardingHandler,
            "_sender_loop",
        ):
            handler = MohnitorForwardingHandler(service="test")
            handler.should_stop = True
            handler.close()
            assert handler.should_stop is True

    def test_sender_loop_no_websockets(self):
        with patch.object(
            MohnitorForwardingHandler,
            "_sender_loop",
        ):
            handler = MohnitorForwardingHandler(service="test")
        # Now test the actual _sender_loop
        with patch("mohflow.devui.client.websockets", None):
            handler._sender_loop()
        handler.should_stop = True
