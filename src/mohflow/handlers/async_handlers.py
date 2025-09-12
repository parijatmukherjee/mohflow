"""Async-safe handlers for high-performance logging in async applications."""

import logging
import queue
import threading
import time
from typing import Optional, Dict, Any, List
from logging.handlers import QueueHandler, QueueListener
from concurrent.futures import ThreadPoolExecutor


class AsyncSafeHandler(logging.Handler):
    """
    Async-safe logging handler that prevents blocking the event loop.

    Uses a queue-based approach with a background thread to handle
    potentially blocking operations like network I/O and file writes.
    """

    def __init__(
        self,
        target_handler: logging.Handler,
        queue_size: int = 10000,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        max_workers: int = 1,
    ):
        """
        Initialize async-safe handler.

        Args:
            target_handler: The actual handler to delegate to
            queue_size: Maximum queue size before blocking
            batch_size: Number of records to batch process
            flush_interval: Time interval to flush pending records
            max_workers: Number of worker threads
        """
        super().__init__()

        self.target_handler = target_handler
        self.batch_size = batch_size
        self.flush_interval = flush_interval

        # Create queue and listener
        self._queue = queue.Queue(maxsize=queue_size)
        self._queue_handler = QueueHandler(self._queue)
        self._listener = QueueListener(
            self._queue, target_handler, respect_handler_level=True
        )

        # Threading components
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._shutdown = False
        self._flush_thread = None

        # Start background processing
        self._start_processing()

    def _start_processing(self):
        """Start background processing threads."""
        self._listener.start()

        # Start flush thread for batching
        if self.flush_interval > 0:
            self._flush_thread = threading.Thread(
                target=self._flush_worker, daemon=True
            )
            self._flush_thread.start()

    def _flush_worker(self):
        """Background worker for periodic flushing."""
        while not self._shutdown:
            time.sleep(self.flush_interval)
            try:
                self.flush()
            except Exception:
                # Ignore flush errors to prevent blocking
                pass

    def emit(self, record: logging.LogRecord):
        """Emit a log record asynchronously."""
        try:
            # Use the queue handler to avoid blocking
            self._queue_handler.emit(record)
        except queue.Full:
            # Queue is full, drop the record to avoid blocking
            # In production, you might want to implement backpressure
            pass
        except Exception:
            self.handleError(record)

    def flush(self):
        """Flush pending log records."""
        try:
            # Flush the target handler
            if hasattr(self.target_handler, "flush"):
                self.target_handler.flush()
        except Exception:
            pass

    def close(self):
        """Close the handler and clean up resources."""
        self._shutdown = True

        # Wait for flush thread to stop
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5.0)

        # Stop the listener
        self._listener.stop()

        # Close target handler
        if hasattr(self.target_handler, "close"):
            self.target_handler.close()

        # Shutdown executor
        self._executor.shutdown(wait=True)

        super().close()


class AsyncFileHandler(AsyncSafeHandler):
    """Async-safe file handler for high-performance file logging."""

    def __init__(
        self, filename: str, mode: str = "a", encoding: str = "utf-8", **kwargs
    ):
        """Initialize async file handler."""
        file_handler = logging.FileHandler(
            filename=filename, mode=mode, encoding=encoding
        )
        super().__init__(target_handler=file_handler, **kwargs)


class AsyncRotatingFileHandler(AsyncSafeHandler):
    """Async-safe rotating file handler."""

    def __init__(
        self,
        filename: str,
        max_bytes: int = 100 * 1024 * 1024,  # 100MB
        backup_count: int = 5,
        encoding: str = "utf-8",
        **kwargs,
    ):
        """Initialize async rotating file handler."""
        from logging.handlers import RotatingFileHandler

        rotating_handler = RotatingFileHandler(
            filename=filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding,
        )
        super().__init__(target_handler=rotating_handler, **kwargs)


class AsyncNetworkHandler(AsyncSafeHandler):
    """Async-safe network handler for remote logging."""

    def __init__(self, host: str, port: int, timeout: float = 5.0, **kwargs):
        """Initialize async network handler."""
        from logging.handlers import SocketHandler

        socket_handler = SocketHandler(host, port)
        socket_handler.timeout = timeout
        super().__init__(target_handler=socket_handler, **kwargs)


class BatchedAsyncHandler(AsyncSafeHandler):
    """
    Batched async handler that accumulates records and processes them in
    batches.

    Optimized for high-throughput scenarios where batching improves
    performance.
    """

    def __init__(
        self,
        target_handler: logging.Handler,
        batch_size: int = 100,
        max_wait_time: float = 5.0,
        **kwargs,
    ):
        """
        Initialize batched async handler.

        Args:
            target_handler: Handler to batch records to
            batch_size: Number of records per batch
            max_wait_time: Maximum time to wait before flushing partial batch
        """
        self.max_wait_time = max_wait_time
        self._batch = []
        self._last_flush = time.time()
        self._batch_lock = threading.Lock()

        super().__init__(
            target_handler=target_handler, batch_size=batch_size, **kwargs
        )

    def emit(self, record: logging.LogRecord):
        """Emit record to batch."""
        current_time = time.time()

        with self._batch_lock:
            self._batch.append(record)

            # Check if we should flush the batch
            should_flush = (
                len(self._batch) >= self.batch_size
                or current_time - self._last_flush >= self.max_wait_time
            )

            if should_flush:
                self._flush_batch()

    def _flush_batch(self):
        """Flush the current batch of records."""
        if not self._batch:
            return

        # Process batch in executor to avoid blocking
        batch_to_process = self._batch.copy()
        self._batch.clear()
        self._last_flush = time.time()

        # Submit batch processing to thread pool
        self._executor.submit(self._process_batch, batch_to_process)

    def _process_batch(self, records: List[logging.LogRecord]):
        """Process a batch of log records."""
        for record in records:
            try:
                self.target_handler.emit(record)
            except Exception:
                # Handle individual record errors
                self.target_handler.handleError(record)

        # Flush the target handler
        if hasattr(self.target_handler, "flush"):
            try:
                self.target_handler.flush()
            except Exception:
                pass

    def flush(self):
        """Force flush any pending records."""
        with self._batch_lock:
            self._flush_batch()
        super().flush()


class AsyncLokiHandler(AsyncSafeHandler):
    """Async-safe Loki handler optimized for high-throughput logging."""

    def __init__(
        self,
        url: str,
        service_name: str,
        environment: str,
        extra_tags: Optional[Dict[str, Any]] = None,
        batch_size: int = 100,
        flush_interval: float = 2.0,
        **kwargs,
    ):
        """Initialize async Loki handler."""
        import logging_loki

        tags = {
            "service": service_name,
            "environment": environment,
        }
        if extra_tags:
            tags.update(extra_tags)

        loki_handler = logging_loki.LokiHandler(
            url=url,
            tags=tags,
            version="1",
        )

        super().__init__(
            target_handler=loki_handler,
            batch_size=batch_size,
            flush_interval=flush_interval,
            **kwargs,
        )


# Convenience factory functions
def create_async_console_handler(**kwargs) -> AsyncSafeHandler:
    """Create async-safe console handler."""
    console_handler = logging.StreamHandler()
    return AsyncSafeHandler(console_handler, **kwargs)


def create_async_file_handler(filename: str, **kwargs) -> AsyncFileHandler:
    """Create async-safe file handler."""
    return AsyncFileHandler(filename, **kwargs)


def create_async_loki_handler(
    url: str, service_name: str, environment: str, **kwargs
) -> AsyncLokiHandler:
    """Create async-safe Loki handler."""
    return AsyncLokiHandler(url, service_name, environment, **kwargs)
