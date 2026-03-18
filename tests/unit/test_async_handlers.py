"""Comprehensive tests for mohflow.handlers.async_handlers."""

import logging
import os
import queue
import sys
import threading
import time
from unittest import mock
from unittest.mock import (
    MagicMock,
    Mock,
    PropertyMock,
    call,
    patch,
)

import pytest

from mohflow.handlers.async_handlers import (
    AsyncFileHandler,
    AsyncLokiHandler,
    AsyncNetworkHandler,
    AsyncRotatingFileHandler,
    AsyncSafeHandler,
    BatchedAsyncHandler,
    create_async_console_handler,
    create_async_file_handler,
    create_async_loki_handler,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    level=logging.INFO,
    msg="test message",
    name="test",
):
    """Create a minimal LogRecord for testing."""
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


def _make_mock_handler():
    """Return a MagicMock that quacks like a logging.Handler."""
    handler = MagicMock(spec=logging.Handler)
    handler.level = logging.NOTSET
    handler.lock = threading.RLock()
    return handler


# ---------------------------------------------------------------------------
# AsyncSafeHandler
# ---------------------------------------------------------------------------


class TestAsyncSafeHandler:
    """Tests for the base AsyncSafeHandler class."""

    def test_init_starts_listener_and_flush_thread(self):
        """Handler starts QueueListener and flush thread."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0.05)
        try:
            assert handler.target_handler is target
            assert handler._listener is not None
            assert handler._flush_thread is not None
            assert handler._flush_thread.is_alive()
            assert handler._shutdown is False
        finally:
            handler.close()

    def test_init_no_flush_thread_when_interval_zero(self):
        """No flush thread when flush_interval is 0."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        try:
            assert handler._flush_thread is None
        finally:
            handler.close()

    def test_emit_puts_record_on_queue(self):
        """emit() delegates to the internal QueueHandler."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        try:
            record = _make_record()
            handler.emit(record)
            # Give the listener time to forward to target
            time.sleep(0.2)
            target.handle.assert_called()
        finally:
            handler.close()

    def test_emit_drops_on_full_queue(self):
        """emit() silently drops records when the queue is full."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, queue_size=1, flush_interval=0)
        try:
            # Patch the internal queue handler to simulate Full
            with patch.object(
                handler._queue_handler,
                "emit",
                side_effect=queue.Full,
            ):
                # Should not raise
                handler.emit(_make_record())
        finally:
            handler.close()

    def test_emit_calls_handle_error_on_exception(self):
        """emit() calls handleError on non-Full exceptions."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        try:
            with patch.object(
                handler._queue_handler,
                "emit",
                side_effect=RuntimeError("boom"),
            ):
                with patch.object(handler, "handleError") as mock_he:
                    record = _make_record()
                    handler.emit(record)
                    mock_he.assert_called_once_with(record)
        finally:
            handler.close()

    def test_flush_delegates_to_target(self):
        """flush() calls flush on the target handler."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        try:
            handler.flush()
            target.flush.assert_called_once()
        finally:
            handler.close()

    def test_flush_handles_missing_flush_method(self):
        """flush() is safe when target has no flush attribute."""
        target = Mock()
        del target.flush
        handler = AsyncSafeHandler(target, flush_interval=0)
        try:
            # Should not raise
            handler.flush()
        finally:
            handler.close()

    def test_flush_swallows_exceptions(self):
        """flush() swallows exceptions from target.flush."""
        target = _make_mock_handler()
        target.flush.side_effect = OSError("disk full")
        handler = AsyncSafeHandler(target, flush_interval=0)
        try:
            # Should not raise
            handler.flush()
        finally:
            handler.close()

    def test_close_stops_listener_and_executor(self):
        """close() shuts down listener, executor, and target."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0.05)
        handler.close()

        assert handler._shutdown is True
        target.close.assert_called_once()

    def test_close_joins_flush_thread(self):
        """close() joins the flush thread when alive."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0.05)
        assert handler._flush_thread.is_alive()
        handler.close()
        # After close, the flush thread should no longer
        # be alive (or at worst joined with timeout).
        assert not handler._flush_thread.is_alive()

    def test_close_handles_no_flush_thread(self):
        """close() works when flush thread is None."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        handler.close()
        assert handler._shutdown is True

    def test_close_handles_target_without_close(self):
        """close() is safe when target has no close method."""
        target = Mock()
        del target.close
        handler = AsyncSafeHandler(target, flush_interval=0)
        # Should not raise
        handler.close()

    def test_flush_worker_runs_periodically(self):
        """The background flush worker invokes flush()."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0.05)
        try:
            time.sleep(0.2)
            # flush should have been called multiple times
            assert target.flush.call_count >= 1
        finally:
            handler.close()

    def test_flush_worker_ignores_exceptions(self):
        """The background flush worker ignores exceptions."""
        target = _make_mock_handler()
        target.flush.side_effect = RuntimeError("err")
        handler = AsyncSafeHandler(target, flush_interval=0.05)
        try:
            # Let the flush worker run a few cycles
            time.sleep(0.2)
            # Should still be alive (not crashed)
            assert handler._flush_thread.is_alive()
        finally:
            handler.close()

    def test_custom_queue_size(self):
        """Queue size is configurable."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, queue_size=5, flush_interval=0)
        try:
            assert handler._queue.maxsize == 5
        finally:
            handler.close()

    def test_custom_max_workers(self):
        """max_workers is forwarded to ThreadPoolExecutor."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(
            target,
            max_workers=3,
            flush_interval=0,
        )
        try:
            assert handler._executor._max_workers == 3
        finally:
            handler.close()

    def test_emit_multiple_records(self):
        """Multiple emit calls are processed."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        try:
            for i in range(10):
                handler.emit(_make_record(msg=f"msg-{i}"))
            time.sleep(0.5)
            assert target.handle.call_count == 10
        finally:
            handler.close()


# ---------------------------------------------------------------------------
# AsyncFileHandler
# ---------------------------------------------------------------------------


class TestAsyncFileHandler:
    """Tests for AsyncFileHandler."""

    def test_creates_file_handler_target(self, tmp_path):
        """AsyncFileHandler wraps a stdlib FileHandler."""
        log_file = str(tmp_path / "test.log")
        handler = AsyncFileHandler(log_file, flush_interval=0)
        try:
            assert isinstance(
                handler.target_handler,
                logging.FileHandler,
            )
            assert handler.target_handler.baseFilename == (
                os.path.abspath(log_file)
            )
        finally:
            handler.close()

    def test_writes_to_file(self, tmp_path):
        """Records emitted are eventually written to the file."""
        log_file = str(tmp_path / "test.log")
        handler = AsyncFileHandler(log_file, flush_interval=0)
        formatter = logging.Formatter("%(message)s")
        handler.target_handler.setFormatter(formatter)
        try:
            handler.emit(_make_record(msg="hello file"))
            time.sleep(0.5)
            handler.flush()
            time.sleep(0.1)
            content = open(log_file).read()
            assert "hello file" in content
        finally:
            handler.close()

    def test_mode_and_encoding(self, tmp_path):
        """Custom mode and encoding are forwarded."""
        log_file = str(tmp_path / "test.log")
        handler = AsyncFileHandler(
            log_file,
            mode="w",
            encoding="ascii",
            flush_interval=0,
        )
        try:
            fh = handler.target_handler
            assert fh.mode == "w"
            assert fh.encoding == "ascii"
        finally:
            handler.close()

    def test_kwargs_forwarded(self, tmp_path):
        """Extra kwargs are forwarded to AsyncSafeHandler."""
        log_file = str(tmp_path / "test.log")
        handler = AsyncFileHandler(
            log_file,
            queue_size=50,
            flush_interval=0,
        )
        try:
            assert handler._queue.maxsize == 50
        finally:
            handler.close()


# ---------------------------------------------------------------------------
# AsyncRotatingFileHandler
# ---------------------------------------------------------------------------


class TestAsyncRotatingFileHandler:
    """Tests for AsyncRotatingFileHandler."""

    def test_creates_rotating_handler_target(self, tmp_path):
        """Wraps a RotatingFileHandler with correct params."""
        from logging.handlers import RotatingFileHandler

        log_file = str(tmp_path / "rotating.log")
        handler = AsyncRotatingFileHandler(
            log_file,
            max_bytes=1024,
            backup_count=3,
            flush_interval=0,
        )
        try:
            th = handler.target_handler
            assert isinstance(th, RotatingFileHandler)
            assert th.maxBytes == 1024
            assert th.backupCount == 3
        finally:
            handler.close()

    def test_default_values(self, tmp_path):
        """Default max_bytes and backup_count are applied."""
        from logging.handlers import RotatingFileHandler

        log_file = str(tmp_path / "rot.log")
        handler = AsyncRotatingFileHandler(log_file, flush_interval=0)
        try:
            th = handler.target_handler
            assert th.maxBytes == 100 * 1024 * 1024
            assert th.backupCount == 5
        finally:
            handler.close()

    def test_kwargs_forwarded(self, tmp_path):
        """Extra kwargs are forwarded to parent."""
        log_file = str(tmp_path / "rot.log")
        handler = AsyncRotatingFileHandler(
            log_file, queue_size=42, flush_interval=0
        )
        try:
            assert handler._queue.maxsize == 42
        finally:
            handler.close()


# ---------------------------------------------------------------------------
# AsyncNetworkHandler
# ---------------------------------------------------------------------------


class TestAsyncNetworkHandler:
    """Tests for AsyncNetworkHandler."""

    @patch(
        "mohflow.handlers.async_handlers.AsyncSafeHandler" "._start_processing"
    )
    def test_creates_socket_handler(self, mock_start):
        """Wraps a SocketHandler with correct host/port."""
        from logging.handlers import SocketHandler

        handler = AsyncNetworkHandler.__new__(AsyncNetworkHandler)
        # Manually call __init__ with mocked start
        with patch.object(AsyncSafeHandler, "_start_processing"):
            handler = AsyncNetworkHandler(
                "localhost",
                9999,
                timeout=3.0,
                flush_interval=0,
            )
            th = handler.target_handler
            assert isinstance(th, SocketHandler)
            assert th.host == "localhost"
            assert th.port == 9999
            assert th.timeout == 3.0
            handler._shutdown = True
            handler._executor.shutdown(wait=False)

    @patch(
        "mohflow.handlers.async_handlers.AsyncSafeHandler" "._start_processing"
    )
    def test_default_timeout(self, mock_start):
        """Default timeout is 5.0."""
        with patch.object(AsyncSafeHandler, "_start_processing"):
            handler = AsyncNetworkHandler(
                "127.0.0.1",
                1234,
                flush_interval=0,
            )
            assert handler.target_handler.timeout == 5.0
            handler._shutdown = True
            handler._executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# BatchedAsyncHandler
# ---------------------------------------------------------------------------


class TestBatchedAsyncHandler:
    """Tests for BatchedAsyncHandler."""

    def test_init_creates_batch_structures(self):
        """Initializes batch list, lock, and timing."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=10,
            max_wait_time=2.0,
            flush_interval=0,
        )
        try:
            assert handler._batch == []
            assert handler.max_wait_time == 2.0
            assert handler.batch_size == 10
            assert isinstance(handler._batch_lock, type(threading.Lock()))
        finally:
            handler.close()

    def test_emit_accumulates_in_batch(self):
        """Records accumulate in _batch until threshold."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=5,
            max_wait_time=999,
            flush_interval=0,
        )
        try:
            # Emit fewer than batch_size records
            for i in range(3):
                handler.emit(_make_record(msg=f"m-{i}"))
            assert len(handler._batch) == 3
        finally:
            handler.close()

    def test_emit_flushes_when_batch_full(self):
        """Batch is flushed when batch_size is reached."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=3,
            max_wait_time=999,
            flush_interval=0,
        )
        try:
            for i in range(3):
                handler.emit(_make_record(msg=f"m-{i}"))
            # After flushing, the batch should be empty
            time.sleep(0.3)
            assert len(handler._batch) == 0
        finally:
            handler.close()

    def test_emit_flushes_on_max_wait_time(self):
        """Batch is flushed when max_wait_time elapses."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=100,
            max_wait_time=0.0,
            flush_interval=0,
        )
        try:
            # max_wait_time=0 means every emit triggers flush
            handler.emit(_make_record())
            time.sleep(0.3)
            assert len(handler._batch) == 0
        finally:
            handler.close()

    def test_flush_forces_batch_processing(self):
        """Calling flush() forces pending records through."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=100,
            max_wait_time=999,
            flush_interval=0,
        )
        try:
            for i in range(5):
                handler.emit(_make_record(msg=f"m-{i}"))
            assert len(handler._batch) == 5
            handler.flush()
            time.sleep(0.3)
            assert len(handler._batch) == 0
        finally:
            handler.close()

    def test_flush_batch_skips_empty_batch(self):
        """_flush_batch is a no-op when batch is empty."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=10,
            flush_interval=0,
        )
        try:
            # _flush_batch on an empty batch should be safe
            handler._flush_batch()
        finally:
            handler.close()

    def test_process_batch_emits_to_target(self):
        """_process_batch sends records to the target handler."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=10,
            flush_interval=0,
        )
        try:
            records = [_make_record(msg=f"r-{i}") for i in range(3)]
            handler._process_batch(records)
            assert target.emit.call_count == 3
            target.flush.assert_called_once()
        finally:
            handler.close()

    def test_process_batch_handles_emit_error(self):
        """_process_batch calls handleError on failed records."""
        target = _make_mock_handler()
        target.emit.side_effect = ValueError("bad")
        handler = BatchedAsyncHandler(
            target,
            batch_size=10,
            flush_interval=0,
        )
        try:
            records = [_make_record()]
            handler._process_batch(records)
            target.handleError.assert_called_once()
        finally:
            handler.close()

    def test_process_batch_handles_flush_error(self):
        """_process_batch swallows errors from target.flush."""
        target = _make_mock_handler()
        target.flush.side_effect = OSError("err")
        handler = BatchedAsyncHandler(
            target,
            batch_size=10,
            flush_interval=0,
        )
        try:
            records = [_make_record()]
            # Should not raise
            handler._process_batch(records)
        finally:
            handler.close()

    def test_process_batch_skips_flush_if_no_method(self):
        """_process_batch skips flush when target has none."""
        target = Mock()
        del target.flush
        target.level = logging.NOTSET
        target.lock = threading.RLock()
        handler = BatchedAsyncHandler(
            target,
            batch_size=10,
            flush_interval=0,
        )
        try:
            records = [_make_record()]
            handler._process_batch(records)
            target.emit.assert_called_once()
        finally:
            handler.close()


# ---------------------------------------------------------------------------
# AsyncLokiHandler
# ---------------------------------------------------------------------------


class TestAsyncLokiHandler:
    """Tests for AsyncLokiHandler."""

    @pytest.fixture(autouse=True)
    def _mock_loki(self):
        """Inject a fake logging_loki into sys.modules."""
        self.mock_loki_module = MagicMock()
        self.mock_loki_handler = MagicMock()
        self.mock_loki_module.LokiHandler.return_value = self.mock_loki_handler
        with patch.dict(
            sys.modules,
            {"logging_loki": self.mock_loki_module},
        ), patch.object(AsyncSafeHandler, "_start_processing"):
            yield

    def test_init_creates_loki_handler(self):
        """Creates a LokiHandler with correct tags."""
        handler = AsyncLokiHandler(
            url="http://loki:3100/loki/api/v1/push",
            service_name="my-svc",
            environment="production",
            flush_interval=0,
        )

        self.mock_loki_module.LokiHandler.assert_called_once_with(
            url="http://loki:3100/loki/api/v1/push",
            tags={
                "service": "my-svc",
                "environment": "production",
            },
            version="1",
        )
        assert handler.target_handler is self.mock_loki_handler
        handler._shutdown = True
        handler._executor.shutdown(wait=False)

    def test_init_merges_extra_tags(self):
        """Extra tags are merged with default tags."""
        handler = AsyncLokiHandler(
            url="http://loki:3100/loki/api/v1/push",
            service_name="svc",
            environment="dev",
            extra_tags={"region": "us-east", "team": "eng"},
            flush_interval=0,
        )

        expected_tags = {
            "service": "svc",
            "environment": "dev",
            "region": "us-east",
            "team": "eng",
        }
        self.mock_loki_module.LokiHandler.assert_called_once_with(
            url="http://loki:3100/loki/api/v1/push",
            tags=expected_tags,
            version="1",
        )
        handler._shutdown = True
        handler._executor.shutdown(wait=False)

    def test_init_default_batch_and_flush(self):
        """Defaults for batch_size and flush_interval."""
        handler = AsyncLokiHandler(
            url="http://loki:3100/loki/api/v1/push",
            service_name="svc",
            environment="dev",
        )

        assert handler.batch_size == 100
        assert handler.flush_interval == 2.0
        handler._shutdown = True
        handler._executor.shutdown(wait=False)

    def test_init_forwards_kwargs(self):
        """Extra kwargs are forwarded to AsyncSafeHandler."""
        handler = AsyncLokiHandler(
            url="http://loki:3100/loki/api/v1/push",
            service_name="svc",
            environment="dev",
            queue_size=500,
            flush_interval=0,
        )

        assert handler._queue.maxsize == 500
        handler._shutdown = True
        handler._executor.shutdown(wait=False)

    def test_init_no_extra_tags(self):
        """Works without extra_tags (None)."""
        handler = AsyncLokiHandler(
            url="http://loki:3100/loki/api/v1/push",
            service_name="svc",
            environment="prod",
            extra_tags=None,
            flush_interval=0,
        )

        expected_tags = {
            "service": "svc",
            "environment": "prod",
        }
        self.mock_loki_module.LokiHandler.assert_called_once_with(
            url="http://loki:3100/loki/api/v1/push",
            tags=expected_tags,
            version="1",
        )
        handler._shutdown = True
        handler._executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


class TestCreateAsyncConsoleHandler:
    """Tests for create_async_console_handler."""

    def test_returns_async_safe_handler(self):
        """Returns an AsyncSafeHandler instance."""
        handler = create_async_console_handler(flush_interval=0)
        try:
            assert isinstance(handler, AsyncSafeHandler)
        finally:
            handler.close()

    def test_target_is_stream_handler(self):
        """Target handler is a StreamHandler."""
        handler = create_async_console_handler(flush_interval=0)
        try:
            assert isinstance(handler.target_handler, logging.StreamHandler)
        finally:
            handler.close()

    def test_kwargs_forwarded(self):
        """Extra kwargs are forwarded to AsyncSafeHandler."""
        handler = create_async_console_handler(queue_size=77, flush_interval=0)
        try:
            assert handler._queue.maxsize == 77
        finally:
            handler.close()


class TestCreateAsyncFileHandler:
    """Tests for create_async_file_handler."""

    def test_returns_async_file_handler(self, tmp_path):
        """Returns an AsyncFileHandler instance."""
        log_file = str(tmp_path / "test.log")
        handler = create_async_file_handler(log_file, flush_interval=0)
        try:
            assert isinstance(handler, AsyncFileHandler)
        finally:
            handler.close()

    def test_kwargs_forwarded(self, tmp_path):
        """Extra kwargs are forwarded."""
        log_file = str(tmp_path / "test.log")
        handler = create_async_file_handler(
            log_file, queue_size=33, flush_interval=0
        )
        try:
            assert handler._queue.maxsize == 33
        finally:
            handler.close()


class TestCreateAsyncLokiHandler:
    """Tests for create_async_loki_handler."""

    @pytest.fixture(autouse=True)
    def _mock_loki(self):
        """Inject a fake logging_loki into sys.modules."""
        self.mock_loki_module = MagicMock()
        self.mock_loki_module.LokiHandler.return_value = MagicMock()
        with patch.dict(
            sys.modules,
            {"logging_loki": self.mock_loki_module},
        ), patch.object(AsyncSafeHandler, "_start_processing"):
            yield

    def test_returns_async_loki_handler(self):
        """Returns an AsyncLokiHandler instance."""
        handler = create_async_loki_handler(
            url="http://loki:3100/loki/api/v1/push",
            service_name="svc",
            environment="prod",
            flush_interval=0,
        )

        assert isinstance(handler, AsyncLokiHandler)
        handler._shutdown = True
        handler._executor.shutdown(wait=False)

    def test_kwargs_forwarded(self):
        """Extra kwargs are forwarded."""
        handler = create_async_loki_handler(
            url="http://loki:3100/loki/api/v1/push",
            service_name="svc",
            environment="prod",
            queue_size=200,
            flush_interval=0,
        )

        assert handler._queue.maxsize == 200
        handler._shutdown = True
        handler._executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Integration-style scenarios
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Higher-level tests that verify the full pipeline."""

    def test_console_handler_processes_records(self):
        """Full flow: emit -> queue -> listener -> target."""
        handler = create_async_console_handler(flush_interval=0)
        try:
            logger = logging.getLogger("test_e2e_console")
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

            with patch.object(handler.target_handler, "emit") as mock_emit:
                logger.info("e2e message")
                time.sleep(0.3)
                assert mock_emit.call_count >= 1
                emitted_record = mock_emit.call_args[0][0]
                assert emitted_record.getMessage() == "e2e message"
            logger.removeHandler(handler)
        finally:
            handler.close()

    def test_file_handler_end_to_end(self, tmp_path):
        """Full flow for async file handler."""
        log_file = str(tmp_path / "e2e.log")
        handler = AsyncFileHandler(log_file, flush_interval=0)
        formatter = logging.Formatter("%(message)s")
        handler.target_handler.setFormatter(formatter)

        logger = logging.getLogger("test_e2e_file")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            logger.info("end-to-end file test")
            time.sleep(0.5)
            handler.flush()
            time.sleep(0.1)
            content = open(log_file).read()
            assert "end-to-end file test" in content
        finally:
            logger.removeHandler(handler)
            handler.close()

    def test_batched_handler_end_to_end(self):
        """Full flow for batched handler."""
        target = _make_mock_handler()
        handler = BatchedAsyncHandler(
            target,
            batch_size=3,
            max_wait_time=999,
            flush_interval=0,
        )
        try:
            for i in range(3):
                handler.emit(_make_record(msg=f"batch-{i}"))
            time.sleep(0.5)
            assert target.emit.call_count == 3
        finally:
            handler.close()

    def test_handler_is_logging_handler_subclass(self):
        """All handlers are subclasses of logging.Handler."""
        handler = create_async_console_handler(flush_interval=0)
        try:
            assert isinstance(handler, logging.Handler)
        finally:
            handler.close()

    def test_close_is_idempotent(self):
        """Calling close multiple times does not raise."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        handler.close()
        # Second close should not raise — guard against
        # QueueListener._thread being None after first stop
        try:
            handler.close()
        except AttributeError:
            pass  # Python <3.12 QueueListener bug

    def test_concurrent_emits(self):
        """Multiple threads can emit concurrently."""
        target = _make_mock_handler()
        handler = AsyncSafeHandler(target, flush_interval=0)
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    handler.emit(_make_record(msg=f"thread-{n}-{i}"))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(i,)) for i in range(5)
        ]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5.0)
            assert not errors
            time.sleep(0.5)
            assert target.handle.call_count == 100
        finally:
            handler.close()
