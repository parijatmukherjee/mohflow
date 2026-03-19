"""
Multiprocess-safe log handler for MohFlow.

Provides a ``multiprocessing.Queue``-based handler that safely
aggregates log records from multiple worker processes into a
single output stream.  Solves the classic "interleaved log lines"
problem when using ``fork()`` or ``spawn()`` process pools.

Usage::

    from mohflow.handlers.multiprocess import (
        MultiProcessHandler,
        MultiProcessListener,
    )

    # In the main process — start a listener that drains the queue
    listener = MultiProcessListener(
        target_handler=logging.StreamHandler(),
        max_queue_size=10_000,
    )
    listener.start()

    # In worker processes — send records through the queue
    handler = MultiProcessHandler(listener.queue)
    logger = logging.getLogger("worker")
    logger.addHandler(handler)
    logger.info("safe from any process")

    # On shutdown
    listener.stop()

Features:
- Bounded queue with configurable backpressure (drop / block / drop-oldest)
- Works with both ``fork`` and ``spawn`` start methods
- Graceful shutdown with drain timeout
"""

from __future__ import annotations

import atexit
import logging
import multiprocessing
import queue
import threading
from typing import Any, Optional


class BackpressurePolicy:
    """Constants for backpressure behaviour when the queue is full."""

    BLOCK = "block"
    DROP_NEWEST = "drop_newest"
    DROP_OLDEST = "drop_oldest"


class MultiProcessHandler(logging.Handler):
    """A handler that enqueues records into a multiprocessing.Queue.

    Intended to be used in **worker processes**.  Records are
    serialised via the queue and consumed by a
    :class:`MultiProcessListener` in the main process.

    Parameters
    ----------
    queue : multiprocessing.Queue
        Shared queue (normally obtained from the listener).
    backpressure : str
        ``"block"`` (default), ``"drop_newest"``, or
        ``"drop_oldest"``.
    """

    def __init__(
        self,
        mp_queue: multiprocessing.Queue,
        backpressure: str = BackpressurePolicy.BLOCK,
    ):
        super().__init__()
        self.mp_queue = mp_queue
        self.backpressure = backpressure
        self._dropped = 0

    def emit(self, record: logging.LogRecord) -> None:
        """Enqueue the log record."""
        try:
            # Prepare the record (format exception info now,
            # since it can't be pickled)
            self.format(record)
            record.exc_info = None
            record.exc_text = None

            if self.backpressure == BackpressurePolicy.BLOCK:
                self.mp_queue.put(record)
            elif self.backpressure == BackpressurePolicy.DROP_NEWEST:
                try:
                    self.mp_queue.put_nowait(record)
                except queue.Full:
                    self._dropped += 1
            elif self.backpressure == BackpressurePolicy.DROP_OLDEST:
                try:
                    self.mp_queue.put_nowait(record)
                except queue.Full:
                    try:
                        self.mp_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.mp_queue.put_nowait(record)
                    except queue.Full:
                        self._dropped += 1
        except Exception:
            self.handleError(record)

    @property
    def dropped_count(self) -> int:
        """Number of records dropped due to backpressure."""
        return self._dropped

    def close(self) -> None:
        super().close()


class MultiProcessListener:
    """Consumes log records from a shared queue in a background thread.

    Runs in the **main process** and forwards every record from the
    queue to a conventional :class:`logging.Handler`.

    Parameters
    ----------
    target_handler : logging.Handler
        The real handler that writes output (e.g. ``StreamHandler``,
        ``FileHandler``).
    max_queue_size : int
        Maximum queue depth.  ``0`` means unbounded (not recommended).
    drain_timeout : float
        Seconds to wait for the queue to drain on ``stop()``.
    """

    _SENTINEL = None  # poison pill to signal shutdown

    def __init__(
        self,
        target_handler: logging.Handler,
        max_queue_size: int = 10_000,
        drain_timeout: float = 5.0,
    ):
        self.target_handler = target_handler
        self.max_queue_size = max_queue_size
        self.drain_timeout = drain_timeout
        self._queue: multiprocessing.Queue = multiprocessing.Queue(
            maxsize=max_queue_size
        )
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._records_processed = 0

    @property
    def queue(self) -> multiprocessing.Queue:
        """The shared queue — pass this to worker process handlers."""
        return self._queue

    @property
    def records_processed(self) -> int:
        return self._records_processed

    def start(self) -> None:
        """Start the background listener thread."""
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._listen,
            name="mohflow-mp-listener",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.stop)

    def stop(self) -> None:
        """Send the poison pill and wait for the thread to finish."""
        if not self._started:
            return
        self._started = False
        try:
            self._queue.put_nowait(self._SENTINEL)
        except queue.Full:
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=self.drain_timeout)
        self._thread = None

    def _listen(self) -> None:
        """Drain the queue until the sentinel is received."""
        while True:
            try:
                record = self._queue.get(timeout=1.0)
            except queue.Empty:
                if not self._started:
                    break
                continue

            if record is self._SENTINEL:
                break

            try:
                self.target_handler.emit(record)
                self._records_processed += 1
            except Exception:
                pass  # swallow handler errors

        # Drain remaining items
        while True:
            try:
                record = self._queue.get_nowait()
                if record is self._SENTINEL:
                    continue
                self.target_handler.emit(record)
                self._records_processed += 1
            except queue.Empty:
                break
            except Exception:
                break


def create_multiprocess_handler(
    target_handler: logging.Handler,
    max_queue_size: int = 10_000,
    backpressure: str = BackpressurePolicy.BLOCK,
    drain_timeout: float = 5.0,
) -> tuple:
    """Convenience factory that creates a matched listener + handler pair.

    Returns
    -------
    (handler, listener) : tuple
        *handler* goes into worker processes; *listener* stays
        in the main process and must be ``.start()``-ed.
    """
    listener = MultiProcessListener(
        target_handler=target_handler,
        max_queue_size=max_queue_size,
        drain_timeout=drain_timeout,
    )
    handler = MultiProcessHandler(
        mp_queue=listener.queue,
        backpressure=backpressure,
    )
    return handler, listener
