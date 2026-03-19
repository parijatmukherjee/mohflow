"""
Causal action logging for MohFlow.

Provides parent-child action trees inspired by eliot, enabling
structured representation of "what caused what" in log streams.

Usage::

    from mohflow.actions import ActionLogger

    actions = ActionLogger(logger)

    with actions.action("process_payment", order_id="ORD-123") as act:
        act.info("validating card")
        with act.child("charge_stripe") as child:
            child.info("charging $99.99")
        act.info("payment complete")
    # Automatically logs elapsed time and success/failure

Features:
- Parent-child relationships with automatic trace propagation
- Built-in elapsed time tracking per action
- Integrates with MohFlow's context API
- Exception-aware (logs failure + duration on unhandled exceptions)
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional


class Action:
    """Represents a single causal action with optional parent linkage.

    Typically created via :meth:`ActionLogger.action` rather than
    directly.
    """

    def __init__(
        self,
        logger: Any,
        action_name: str,
        action_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        **context: Any,
    ):
        self._logger = logger
        self.action_name = action_name
        self.action_id = action_id or uuid.uuid4().hex[:16]
        self.parent_id = parent_id
        self.context = context
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._status: str = "pending"
        self._children: List[str] = []

    # ── context-manager protocol ─────────────────────────────

    def __enter__(self) -> "Action":
        self._start_time = time.monotonic()
        self._status = "started"
        self._log(
            "info",
            f"Action '{self.action_name}' started",
            action_status="started",
        )
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        self._end_time = time.monotonic()
        elapsed_ms = self.elapsed_ms

        if exc_type is not None:
            self._status = "failed"
            self._log(
                "error",
                f"Action '{self.action_name}' failed " f"({elapsed_ms:.1f}ms)",
                action_status="failed",
                error=str(exc_val),
                error_type=exc_type.__name__,
                elapsed_ms=elapsed_ms,
            )
        else:
            self._status = "succeeded"
            self._log(
                "info",
                f"Action '{self.action_name}' succeeded "
                f"({elapsed_ms:.1f}ms)",
                action_status="succeeded",
                elapsed_ms=elapsed_ms,
            )
        # Do NOT suppress exceptions
        return None

    # ── public helpers ───────────────────────────────────────

    @property
    def elapsed_ms(self) -> float:
        """Elapsed wall-clock time in milliseconds."""
        if self._start_time is None:
            return 0.0
        end = self._end_time or time.monotonic()
        return (end - self._start_time) * 1000

    @property
    def status(self) -> str:
        return self._status

    @property
    def children(self) -> List[str]:
        """IDs of child actions."""
        return list(self._children)

    def child(
        self,
        action_name: str,
        **context: Any,
    ) -> "Action":
        """Create a child action linked to this one.

        Use as a context manager::

            with parent.child("sub_step") as c:
                c.info("doing work")
        """
        child_action = Action(
            logger=self._logger,
            action_name=action_name,
            parent_id=self.action_id,
            **{**self.context, **context},
        )
        self._children.append(child_action.action_id)
        return child_action

    def info(self, message: str, **extra: Any) -> None:
        self._log("info", message, **extra)

    def warning(self, message: str, **extra: Any) -> None:
        self._log("warning", message, **extra)

    def error(self, message: str, **extra: Any) -> None:
        self._log("error", message, **extra)

    def debug(self, message: str, **extra: Any) -> None:
        self._log("debug", message, **extra)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the action to a dict (for structured output)."""
        d: Dict[str, Any] = {
            "action_id": self.action_id,
            "action_name": self.action_name,
            "status": self._status,
        }
        if self.parent_id:
            d["parent_action_id"] = self.parent_id
        if self._children:
            d["children"] = list(self._children)
        if self._start_time and self._end_time:
            d["elapsed_ms"] = self.elapsed_ms
        d.update(self.context)
        return d

    # ── internal ─────────────────────────────────────────────

    def _log(
        self,
        level: str,
        message: str,
        **extra: Any,
    ) -> None:
        """Emit a log message enriched with action context."""
        merged = {
            "action_id": self.action_id,
            "action_name": self.action_name,
            **self.context,
            **extra,
        }
        if self.parent_id:
            merged["parent_action_id"] = self.parent_id

        log_fn = getattr(self._logger, level, self._logger.info)
        log_fn(message, **merged)


class ActionLogger:
    """Factory for creating causal action trees.

    Parameters
    ----------
    logger : Any
        A MohFlow logger (or any object with ``info``, ``error``, etc.).
    """

    def __init__(self, logger: Any):
        self._logger = logger

    def action(
        self,
        action_name: str,
        **context: Any,
    ) -> Action:
        """Create a new top-level action.

        Use as a context manager::

            with actions.action("process_order", order_id="O1") as a:
                a.info("processing")
        """
        return Action(
            logger=self._logger,
            action_name=action_name,
            **context,
        )
