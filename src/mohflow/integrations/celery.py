"""
Celery integration for MohFlow logging.

Provides automatic task logging, error handling, and performance monitoring
for Celery distributed tasks with context propagation.
"""

import time
import uuid
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import json

try:
    from celery import Celery
    from celery.signals import (
        task_prerun,
        task_postrun,
        task_failure,
        task_retry,
        worker_ready,
        worker_shutdown,
    )
    from celery.app.task import Task

    HAS_CELERY = True
except ImportError:
    HAS_CELERY = False
    Celery = object
    Task = object


class MohFlowCeleryIntegration:
    """
    Celery integration for MohFlow logging.

    Provides automatic task lifecycle logging, error handling,
    and performance monitoring for Celery tasks.
    """

    def __init__(self, logger: Any, app: Optional[Celery] = None):
        """
        Initialize Celery integration.

        Args:
            logger: MohFlow logger instance
            app: Celery application instance
        """
        self.logger = logger
        self.app = app

        if app is not None:
            self.setup_signals()

    def setup_signals(self):
        """Setup Celery signal handlers."""
        if not HAS_CELERY:
            raise ImportError(
                "Celery is not installed. Install with: pip install celery"
            )

        # Connect signal handlers
        task_prerun.connect(self._task_prerun_handler, weak=False)
        task_postrun.connect(self._task_postrun_handler, weak=False)
        task_failure.connect(self._task_failure_handler, weak=False)
        task_retry.connect(self._task_retry_handler, weak=False)
        worker_ready.connect(self._worker_ready_handler, weak=False)
        worker_shutdown.connect(self._worker_shutdown_handler, weak=False)

    def _task_prerun_handler(
        self,
        sender=None,
        task_id=None,
        task=None,
        args=None,
        kwargs=None,
        **kwds,
    ):
        """Handle task start."""
        start_time = time.time()

        # Extract task context
        task_context = {
            "task_id": task_id,
            "task_name": sender.name if sender else task.name,
            "task_args": self._safe_serialize(args),
            "task_kwargs": self._safe_serialize(kwargs),
            "worker_id": kwds.get("hostname"),
            "timestamp": datetime.utcnow().isoformat(),
            "task_start_time": start_time,
        }

        # Store context for later use
        if hasattr(task, "mohflow_context"):
            task.mohflow_context = task_context

        # Log task start
        with self.logger.request_context(task_id=task_id, **task_context):
            self.logger.info(
                f"Task {task_context['task_name']} started", **task_context
            )

    def _task_postrun_handler(
        self,
        sender=None,
        task_id=None,
        task=None,
        args=None,
        kwargs=None,
        retval=None,
        state=None,
        **kwds,
    ):
        """Handle task completion."""
        end_time = time.time()

        # Get start time from context
        start_time = getattr(task, "mohflow_context", {}).get(
            "task_start_time", end_time
        )
        duration_ms = (end_time - start_time) * 1000

        task_context = {
            "task_id": task_id,
            "task_name": sender.name if sender else task.name,
            "task_state": state,
            "duration": duration_ms,
            "worker_id": kwds.get("hostname"),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Add return value if it's serializable and not too large
        if retval is not None:
            serialized_retval = self._safe_serialize(retval)
            if serialized_retval and len(str(serialized_retval)) < 1000:
                task_context["return_value"] = serialized_retval

        # Log task completion
        with self.logger.request_context(task_id=task_id, **task_context):
            if state == "SUCCESS":
                self.logger.info(
                    f"Task {task_context['task_name']} completed successfully "
                    f"({duration_ms:.1f}ms)",
                    **task_context,
                )
            else:
                self.logger.warning(
                    f"Task {task_context['task_name']} completed with state {state} "
                    f"({duration_ms:.1f}ms)",
                    **task_context,
                )

    def _task_failure_handler(
        self, sender=None, task_id=None, exception=None, einfo=None, **kwds
    ):
        """Handle task failure."""
        task_context = {
            "task_id": task_id,
            "task_name": sender.name if sender else "unknown",
            "error": str(exception) if exception else "Unknown error",
            "error_type": (
                type(exception).__name__ if exception else "UnknownError"
            ),
            "traceback": str(einfo) if einfo else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Log task failure
        with self.logger.request_context(task_id=task_id, **task_context):
            self.logger.error(
                f"Task {task_context['task_name']} failed", **task_context
            )

    def _task_retry_handler(
        self, sender=None, task_id=None, reason=None, einfo=None, **kwds
    ):
        """Handle task retry."""
        task_context = {
            "task_id": task_id,
            "task_name": sender.name if sender else "unknown",
            "retry_reason": str(reason) if reason else "Unknown reason",
            "traceback": str(einfo) if einfo else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Log task retry
        with self.logger.request_context(task_id=task_id, **task_context):
            self.logger.warning(
                f"Task {task_context['task_name']} will be retried",
                **task_context,
            )

    def _worker_ready_handler(self, sender=None, **kwds):
        """Handle worker startup."""
        worker_context = {
            "worker_id": (
                sender.hostname if hasattr(sender, "hostname") else "unknown"
            ),
            "worker_pid": sender.pid if hasattr(sender, "pid") else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.logger.info("Celery worker ready", **worker_context)

    def _worker_shutdown_handler(self, sender=None, **kwds):
        """Handle worker shutdown."""
        worker_context = {
            "worker_id": (
                sender.hostname if hasattr(sender, "hostname") else "unknown"
            ),
            "worker_pid": sender.pid if hasattr(sender, "pid") else None,
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.logger.info("Celery worker shutting down", **worker_context)

    def _safe_serialize(self, obj) -> Any:
        """Safely serialize object for logging."""
        try:
            # Try JSON serialization to check if it's serializable
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            # Return string representation if not serializable
            return str(obj) if obj is not None else None


class MohFlowCeleryTask(Task):
    """
    Custom Celery task class with MohFlow logging integration.

    Usage:
        app = Celery('myapp')
        app.Task = MohFlowCeleryTask

        # Or for specific tasks
        @app.task(base=MohFlowCeleryTask)
        def my_task():
            ...
    """

    def __init__(self):
        super().__init__()
        self.mohflow_logger = None

    def set_logger(self, logger: Any):
        """Set MohFlow logger for this task."""
        self.mohflow_logger = logger

    def apply_async(self, args=None, kwargs=None, **options):
        """Override apply_async to add context propagation."""
        # Add correlation ID if not present
        if "headers" not in options:
            options["headers"] = {}

        if "correlation_id" not in options["headers"]:
            options["headers"]["correlation_id"] = str(uuid.uuid4())

        # Log task dispatch
        if self.mohflow_logger:
            dispatch_context = {
                "task_name": self.name,
                "correlation_id": options["headers"]["correlation_id"],
                "task_args": self._safe_serialize(args),
                "task_kwargs": self._safe_serialize(kwargs),
                "timestamp": datetime.utcnow().isoformat(),
            }

            self.mohflow_logger.info(
                f"Task {self.name} dispatched", **dispatch_context
            )

        return super().apply_async(args, kwargs, **options)

    def retry(
        self,
        args=None,
        kwargs=None,
        exc=None,
        throw=True,
        eta=None,
        countdown=None,
        max_retries=None,
        **options,
    ):
        """Override retry to add logging."""
        if self.mohflow_logger:
            retry_context = {
                "task_name": self.name,
                "task_id": self.request.id,
                "retry_count": self.request.retries,
                "max_retries": max_retries or self.max_retries,
                "countdown": countdown,
                "eta": eta.isoformat() if eta else None,
                "exception": str(exc) if exc else None,
                "timestamp": datetime.utcnow().isoformat(),
            }

            self.mohflow_logger.warning(
                f"Task {self.name} retry attempt {self.request.retries + 1}",
                **retry_context,
            )

        return super().retry(
            args, kwargs, exc, throw, eta, countdown, max_retries, **options
        )

    def _safe_serialize(self, obj) -> Any:
        """Safely serialize object for logging."""
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj) if obj is not None else None


# Decorator for task-specific logging
def log_task(logger: Any, **log_kwargs):
    """
    Decorator for Celery tasks to add specific logging context.

    Usage:
        @app.task
        @log_task(logger, component="data_processing", priority="high")
        def process_data(data_id):
            ...
    """

    def decorator(task_func):
        def wrapper(*args, **kwargs):
            task_id = getattr(wrapper, "request", {}).get("id", "unknown")
            start_time = time.time()

            task_context = {"task_name": task_func.__name__, **log_kwargs}

            try:
                # Log task start with context
                with logger.request_context(task_id=task_id, **task_context):
                    logger.info(
                        f"Task {task_func.__name__} starting execution",
                        **task_context,
                    )

                result = task_func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000

                # Log successful completion
                with logger.request_context(task_id=task_id, **task_context):
                    logger.info(
                        f"Task {task_func.__name__} completed successfully "
                        f"({duration:.1f}ms)",
                        duration=duration,
                        **task_context,
                    )

                return result

            except Exception as e:
                duration = (time.time() - start_time) * 1000

                # Log task failure
                with logger.request_context(task_id=task_id, **task_context):
                    logger.error(
                        f"Task {task_func.__name__} failed ({duration:.1f}ms)",
                        duration=duration,
                        error=str(e),
                        error_type=type(e).__name__,
                        **task_context,
                    )
                raise

        # Preserve task attributes
        wrapper.__name__ = task_func.__name__
        wrapper.__doc__ = task_func.__doc__

        return wrapper

    return decorator


def setup_celery_logging(logger: Any, app: Celery) -> MohFlowCeleryIntegration:
    """
    Setup MohFlow logging for Celery application.

    Args:
        logger: MohFlow logger instance
        app: Celery application

    Returns:
        MohFlowCeleryIntegration instance
    """
    integration = MohFlowCeleryIntegration(logger, app)
    return integration


def create_celery_logger(base_logger: Any, task_name: str) -> Any:
    """
    Create a task-specific logger with Celery context.

    Usage:
        @app.task
        def my_task():
            logger = create_celery_logger(base_logger, 'my_task')
            logger.info("Task processing")
    """
    # Create a copy of the base logger with task-specific context
    task_logger = type(base_logger)(
        service_name=base_logger.config.SERVICE_NAME,
        **{
            k: v
            for k, v in base_logger.__dict__.items()
            if not k.startswith("_")
        },
    )

    # Set task-specific context
    task_logger.set_context(
        component="celery_task",
        task_name=task_name,
        timestamp=datetime.utcnow().isoformat(),
    )

    return task_logger


# Progress tracking for long-running tasks
def log_task_progress(
    logger: Any, task_id: str, current: int, total: int, message: str = None
):
    """
    Log task progress for long-running tasks.

    Usage:
        @app.task(bind=True)
        def long_task(self):
            for i in range(100):
                # Do work
                log_task_progress(logger, self.request.id, i+1, 100, "Processing item")
    """
    progress_percent = (current / total * 100) if total > 0 else 0

    progress_context = {
        "progress_current": current,
        "progress_total": total,
        "progress_percent": progress_percent,
        "timestamp": datetime.utcnow().isoformat(),
    }

    log_message = (
        message
        or f"Task progress: {current}/{total} ({progress_percent:.1f}%)"
    )

    with logger.request_context(task_id=task_id, **progress_context):
        logger.info(log_message, **progress_context)


# Error aggregation for task monitoring
class TaskErrorAggregator:
    """
    Aggregates task errors for monitoring and alerting.

    Usage:
        aggregator = TaskErrorAggregator(logger)
        integration = MohFlowCeleryIntegration(logger, app)
        integration.error_aggregator = aggregator
    """

    def __init__(self, logger: Any, window_minutes: int = 15):
        self.logger = logger
        self.window_minutes = window_minutes
        self.error_counts = {}
        self.last_cleanup = time.time()

    def record_error(self, task_name: str, error_type: str):
        """Record a task error."""
        current_time = time.time()

        # Cleanup old entries
        if current_time - self.last_cleanup > 300:  # 5 minutes
            self._cleanup_old_entries(current_time)
            self.last_cleanup = current_time

        # Record error
        key = f"{task_name}:{error_type}"
        if key not in self.error_counts:
            self.error_counts[key] = []

        self.error_counts[key].append(current_time)

        # Check if error rate is high
        self._check_error_rate(task_name, error_type)

    def _cleanup_old_entries(self, current_time: float):
        """Remove old error entries outside the window."""
        cutoff_time = current_time - (self.window_minutes * 60)

        for key in list(self.error_counts.keys()):
            self.error_counts[key] = [
                timestamp
                for timestamp in self.error_counts[key]
                if timestamp > cutoff_time
            ]

            if not self.error_counts[key]:
                del self.error_counts[key]

    def _check_error_rate(self, task_name: str, error_type: str):
        """Check if error rate is above threshold."""
        key = f"{task_name}:{error_type}"
        error_count = len(self.error_counts.get(key, []))

        # Alert if more than 10 errors in the window
        if error_count >= 10:
            self.logger.error(
                f"High error rate detected for task {task_name}",
                task_name=task_name,
                error_type=error_type,
                error_count=error_count,
                window_minutes=self.window_minutes,
                alert_type="high_error_rate",
            )
