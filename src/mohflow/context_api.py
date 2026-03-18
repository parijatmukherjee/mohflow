"""
Top-level contextvars-first context propagation API.

Provides simple bind/unbind/clear functions for attaching structured
context that flows automatically into every log call in the current
async task or thread.

Usage::

    from mohflow import bind_context, unbind_context, clear_context

    bind_context(user_id="u123", tenant="acme")
    log.info("request started")       # includes user_id + tenant
    unbind_context("tenant")
    log.info("tenant removed")         # includes user_id only
    clear_context()
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional, Sequence

_bound_context: ContextVar[Dict[str, Any]] = ContextVar(
    "mohflow_bound_context", default={}
)


def bind_context(**kwargs: Any) -> None:
    """Bind key-value pairs to the current context.

    Bound values are automatically included in every subsequent log
    call within the same async task / thread.
    """
    current = _bound_context.get({})
    updated = {**current, **kwargs}
    _bound_context.set(updated)


def unbind_context(*keys: str) -> None:
    """Remove specific keys from the current context."""
    current = _bound_context.get({})
    if not keys:
        return
    updated = {k: v for k, v in current.items() if k not in keys}
    _bound_context.set(updated)


def clear_context() -> None:
    """Remove all bound context."""
    _bound_context.set({})


def get_bound_context() -> Dict[str, Any]:
    """Return a copy of the currently bound context."""
    return dict(_bound_context.get({}))
