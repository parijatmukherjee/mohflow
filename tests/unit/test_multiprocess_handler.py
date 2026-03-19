"""Tests for mohflow.handlers.multiprocess: queue-based multiprocess logging."""

import logging
import multiprocessing
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from mohflow.handlers.multiprocess import (
    BackpressurePolicy,
    MultiProcessHandler,
    MultiProcessListener,
    create_multiprocess_handler,
)

# -----------------------------------------------------------
# BackpressurePolicy constants
# -----------------------------------------------------------


class TestBackpressurePolicy:
    """Verify policy constant values."""

    def test_block_value(self):
        assert BackpressurePolicy.BLOCK == "block"

    def test_drop_newest_value(self):
        assert BackpressurePolicy.DROP_NEWEST == "drop_newest"

    def test_drop_oldest_value(self):
        assert BackpressurePolicy.DROP_OLDEST == "drop_oldest"


# -----------------------------------------------------------
# MultiProcessHandler
# -----------------------------------------------------------


def _make_record(msg="test"):
    """Create a minimal LogRecord."""
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


class TestMultiProcessHandlerInit:
    """Handler construction."""

    def test_default_backpressure_is_block(self):
        q = multiprocessing.Queue(maxsize=5)
        handler = MultiProcessHandler(q)
        assert handler.backpressure == BackpressurePolicy.BLOCK

    def test_custom_backpressure(self):
        q = multiprocessing.Queue(maxsize=5)
        handler = MultiProcessHandler(
            q, backpressure=BackpressurePolicy.DROP_NEWEST
        )
        assert handler.backpressure == BackpressurePolicy.DROP_NEWEST

    def test_initial_dropped_count_zero(self):
        q = multiprocessing.Queue(maxsize=5)
        handler = MultiProcessHandler(q)
        assert handler.dropped_count == 0


class TestMultiProcessHandlerEmitBlock:
    """emit() with BLOCK policy."""

    def test_record_enqueued(self):
        q = multiprocessing.Queue(maxsize=5)
        handler = MultiProcessHandler(q, backpressure=BackpressurePolicy.BLOCK)
        record = _make_record("hello")
        handler.emit(record)
        result = q.get(timeout=1)
        assert result.msg == "hello"

    def test_exc_info_cleared(self):
        q = multiprocessing.Queue(maxsize=5)
        handler = MultiProcessHandler(q, backpressure=BackpressurePolicy.BLOCK)
        record = _make_record("hello")
        record.exc_info = ("fake",)
        record.exc_text = "traceback"
        handler.emit(record)
        result = q.get(timeout=1)
        assert result.exc_info is None
        assert result.exc_text is None


class TestMultiProcessHandlerEmitDropNewest:
    """emit() with DROP_NEWEST policy."""

    def test_drops_when_full(self):
        q = multiprocessing.Queue(maxsize=2)
        handler = MultiProcessHandler(
            q, backpressure=BackpressurePolicy.DROP_NEWEST
        )
        handler.emit(_make_record("m1"))
        handler.emit(_make_record("m2"))
        # Queue is now full (maxsize=2)
        handler.emit(_make_record("m3"))
        assert handler.dropped_count == 1

    def test_first_records_preserved(self):
        q = multiprocessing.Queue(maxsize=2)
        handler = MultiProcessHandler(
            q, backpressure=BackpressurePolicy.DROP_NEWEST
        )
        handler.emit(_make_record("m1"))
        handler.emit(_make_record("m2"))
        handler.emit(_make_record("m3"))  # dropped
        assert q.get(timeout=1).msg == "m1"
        assert q.get(timeout=1).msg == "m2"

    def test_multiple_drops_counted(self):
        q = multiprocessing.Queue(maxsize=1)
        handler = MultiProcessHandler(
            q, backpressure=BackpressurePolicy.DROP_NEWEST
        )
        handler.emit(_make_record("m1"))
        handler.emit(_make_record("m2"))
        handler.emit(_make_record("m3"))
        assert handler.dropped_count == 2


class TestMultiProcessHandlerEmitDropOldest:
    """emit() with DROP_OLDEST policy."""

    def test_oldest_evicted_when_full(self):
        """Use a mock queue to precisely control full/empty behavior."""
        mock_q = MagicMock()
        call_count = [0]

        def put_nowait_side_effect(item):
            call_count[0] += 1
            if call_count[0] == 1:
                # First put_nowait succeeds (initial enqueue attempt)
                return
            if call_count[0] == 2:
                # Second call (first attempt for record when full) raises Full
                raise queue.Full
            # Third call (retry after eviction) succeeds
            return

        mock_q.put_nowait = MagicMock(side_effect=put_nowait_side_effect)
        mock_q.get_nowait = MagicMock(return_value=_make_record("old"))

        handler = MultiProcessHandler(
            mock_q, backpressure=BackpressurePolicy.DROP_OLDEST
        )
        # First emit succeeds (call_count=1)
        handler.emit(_make_record("m1"))
        # Second emit: first put_nowait raises Full (call_count=2),
        # get_nowait evicts old, retry put_nowait succeeds (call_count=3)
        handler.emit(_make_record("m2"))
        assert mock_q.get_nowait.call_count == 1  # old item evicted
        assert handler.dropped_count == 0  # retry succeeded

    def test_dropped_count_increments_on_retry_failure(self):
        """If the retry put also fails, dropped_count increments."""
        q = multiprocessing.Queue(maxsize=1)
        handler = MultiProcessHandler(
            q, backpressure=BackpressurePolicy.DROP_OLDEST
        )
        handler.emit(_make_record("m1"))  # fills queue
        # Now try to add with a mock that makes put_nowait always fail on retry
        # This tests the inner except queue.Full path
        original_put_nowait = q.put_nowait
        call_count = [0]

        def patched_put_nowait(item):
            call_count[0] += 1
            if call_count[0] >= 3:
                # On third call (the retry after eviction), raise Full
                raise queue.Full
            return original_put_nowait(item)

        q.put_nowait = patched_put_nowait
        handler.emit(_make_record("m2"))
        # The dropped_count should have been incremented
        assert handler.dropped_count >= 1


class TestMultiProcessHandlerClose:
    """Handler close lifecycle."""

    def test_close_does_not_raise(self):
        q = multiprocessing.Queue(maxsize=5)
        handler = MultiProcessHandler(q)
        handler.close()  # should not raise


class TestMultiProcessHandlerErrorHandling:
    """emit() error path calls handleError."""

    def test_handleError_on_exception(self):
        q = MagicMock()
        q.put = MagicMock(side_effect=RuntimeError("broken"))
        handler = MultiProcessHandler(q, backpressure=BackpressurePolicy.BLOCK)
        handler.handleError = MagicMock()
        handler.emit(_make_record("fail"))
        handler.handleError.assert_called_once()


# -----------------------------------------------------------
# MultiProcessListener
# -----------------------------------------------------------


class TestMultiProcessListenerInit:
    """Listener construction."""

    def test_default_max_queue_size(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target)
        assert listener.max_queue_size == 10_000

    def test_custom_queue_size(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=50)
        assert listener.max_queue_size == 50

    def test_queue_property(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target)
        assert listener.queue is not None

    def test_initial_records_processed_zero(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target)
        assert listener.records_processed == 0


class TestMultiProcessListenerLifecycle:
    """start/stop lifecycle."""

    def test_start_creates_thread(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.start()
        try:
            assert listener._thread is not None
            assert listener._thread.is_alive()
            assert listener._started is True
        finally:
            listener.stop()

    def test_idempotent_start(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.start()
        thread1 = listener._thread
        listener.start()  # second call should be no-op
        thread2 = listener._thread
        try:
            assert thread1 is thread2
        finally:
            listener.stop()

    def test_stop_without_start_is_noop(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.stop()  # should not raise

    def test_idempotent_stop(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.start()
        listener.stop()
        listener.stop()  # second stop is no-op, should not raise

    def test_stop_joins_thread(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.start()
        listener.stop()
        assert listener._thread is None


# -----------------------------------------------------------
# Records flowing through listener
# -----------------------------------------------------------


class TestMultiProcessListenerRecordFlow:
    """Records enqueued by handler arrive at target_handler via listener."""

    def test_single_record_forwarded(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.start()
        try:
            record = _make_record("hello")
            listener.queue.put(record)
            # Give the listener thread time to process
            time.sleep(0.2)
        finally:
            listener.stop()
        target.emit.assert_called()
        assert listener.records_processed >= 1

    def test_multiple_records_forwarded(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=10)
        listener.start()
        try:
            for i in range(5):
                listener.queue.put(_make_record(f"msg-{i}"))
            time.sleep(0.5)
        finally:
            listener.stop()
        assert target.emit.call_count >= 5
        assert listener.records_processed >= 5

    def test_handler_to_listener_integration(self):
        """End-to-end: handler.emit -> queue -> listener -> target."""
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=10)
        handler = MultiProcessHandler(listener.queue)
        listener.start()
        try:
            handler.emit(_make_record("integration"))
            time.sleep(0.3)
        finally:
            listener.stop()
        target.emit.assert_called()
        assert target.emit.call_args[0][0].msg == "integration"


# -----------------------------------------------------------
# Sentinel (poison pill) handling
# -----------------------------------------------------------


class TestSentinelHandling:
    """Verify the sentinel stops the listener."""

    def test_sentinel_stops_loop(self):
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.start()
        # Put some records, then stop (which puts sentinel)
        listener.queue.put(_make_record("before"))
        time.sleep(0.2)
        listener.stop()
        # Thread should have exited
        assert listener._thread is None

    def test_drain_on_stop(self):
        """Records remaining in queue should be drained on stop."""
        target = MagicMock(spec=logging.Handler)
        listener = MultiProcessListener(target, max_queue_size=100)
        listener.start()
        try:
            # Put several records quickly
            for i in range(5):
                listener.queue.put(_make_record(f"drain-{i}"))
            time.sleep(0.3)
        finally:
            listener.stop()
        # All records should have been processed
        assert listener.records_processed >= 5


# -----------------------------------------------------------
# Listener swallows handler errors
# -----------------------------------------------------------


class TestListenerErrorHandling:
    """Target handler errors should not crash the listener."""

    def test_target_error_swallowed(self):
        target = MagicMock(spec=logging.Handler)
        target.emit.side_effect = RuntimeError("target broken")
        listener = MultiProcessListener(target, max_queue_size=5)
        listener.start()
        try:
            listener.queue.put(_make_record("will fail"))
            time.sleep(0.3)
        finally:
            listener.stop()
        # Listener should have stopped cleanly despite error
        assert listener._thread is None


# -----------------------------------------------------------
# create_multiprocess_handler factory
# -----------------------------------------------------------


class TestCreateMultiprocessHandler:
    """Verify the convenience factory."""

    def test_returns_handler_and_listener(self):
        target = MagicMock(spec=logging.Handler)
        handler, listener = create_multiprocess_handler(target)
        assert isinstance(handler, MultiProcessHandler)
        assert isinstance(listener, MultiProcessListener)

    def test_handler_uses_listener_queue(self):
        target = MagicMock(spec=logging.Handler)
        handler, listener = create_multiprocess_handler(target)
        assert handler.mp_queue is listener.queue

    def test_custom_parameters(self):
        target = MagicMock(spec=logging.Handler)
        handler, listener = create_multiprocess_handler(
            target,
            max_queue_size=50,
            backpressure=BackpressurePolicy.DROP_NEWEST,
            drain_timeout=2.0,
        )
        assert listener.max_queue_size == 50
        assert handler.backpressure == BackpressurePolicy.DROP_NEWEST
        assert listener.drain_timeout == 2.0

    def test_default_parameters(self):
        target = MagicMock(spec=logging.Handler)
        handler, listener = create_multiprocess_handler(target)
        assert listener.max_queue_size == 10_000
        assert handler.backpressure == BackpressurePolicy.BLOCK
        assert listener.drain_timeout == 5.0

    def test_factory_integration(self):
        """Factory-produced handler+listener pass records end-to-end."""
        target = MagicMock(spec=logging.Handler)
        handler, listener = create_multiprocess_handler(
            target, max_queue_size=10
        )
        listener.start()
        try:
            handler.emit(_make_record("factory-test"))
            time.sleep(0.3)
        finally:
            listener.stop()
        target.emit.assert_called()
        assert target.emit.call_args[0][0].msg == "factory-test"


# -----------------------------------------------------------
# Bounded queue (max_queue_size)
# -----------------------------------------------------------


class TestBoundedQueue:
    """Verify queue respects max_queue_size."""

    def test_queue_size_respected_drop_newest(self):
        q = multiprocessing.Queue(maxsize=3)
        handler = MultiProcessHandler(
            q, backpressure=BackpressurePolicy.DROP_NEWEST
        )
        for i in range(10):
            handler.emit(_make_record(f"m{i}"))
        assert handler.dropped_count == 7
        # Queue should have exactly 3 items; drain with timeout
        count = 0
        while True:
            try:
                q.get(timeout=0.5)
                count += 1
            except queue.Empty:
                break
        assert count == 3
