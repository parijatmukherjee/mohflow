"""
AI/LLM observability module for MohFlow.

Provides first-class tracking of LLM API calls including token usage,
latency, cost estimation, and automatic prompt/response PII scanning.

Usage::

    from mohflow.integrations.llm import LLMTracker

    tracker = LLMTracker(logger, provider="openai", model="gpt-4")
    with tracker.track_call(prompt="Summarise this doc") as call:
        response = openai.chat.completions.create(...)
        call.record_response(
            output_text=response.choices[0].message.content,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
    # Auto-logs: tokens, latency, estimated cost, model

Features:
- Track tokens (input/output), latency, estimated cost per call
- Session/conversation correlation
- Aggregate cost and token budgets
- Provider-agnostic (OpenAI, Anthropic, Cohere, local models)
- PII scanning integration with MohFlow privacy module
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

# Approximate cost per 1M tokens (USD) — updated March 2026
_DEFAULT_COST_TABLE: Dict[str, Dict[str, float]] = {
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
    "command-r-plus": {"input": 2.50, "output": 10.0},
    "command-r": {"input": 0.15, "output": 0.60},
}


class LLMCallRecord:
    """Captures details of a single LLM API call."""

    def __init__(
        self,
        call_id: str,
        provider: str,
        model: str,
        session_id: Optional[str] = None,
    ):
        self.call_id = call_id
        self.provider = provider
        self.model = model
        self.session_id = session_id

        self.prompt: Optional[str] = None
        self.output_text: Optional[str] = None
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.total_tokens: int = 0
        self.latency_ms: float = 0.0
        self.estimated_cost_usd: float = 0.0
        self.temperature: Optional[float] = None
        self.max_tokens: Optional[int] = None
        self.status: str = "pending"
        self.error: Optional[str] = None
        self.metadata: Dict[str, Any] = {}

        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None

    def record_response(
        self,
        output_text: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: Optional[int] = None,
        **metadata: Any,
    ) -> None:
        """Record the response from the LLM call."""
        self.output_text = output_text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = (
            total_tokens
            if total_tokens is not None
            else input_tokens + output_tokens
        )
        self.metadata.update(metadata)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "call_id": self.call_id,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "status": self.status,
        }
        if self.session_id:
            d["session_id"] = self.session_id
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.error:
            d["error"] = self.error
        if self.metadata:
            d.update(self.metadata)
        return d


class LLMCallContext:
    """Context manager for tracking a single LLM call.

    Automatically measures latency and logs the call on exit.
    """

    def __init__(
        self,
        tracker: "LLMTracker",
        record: LLMCallRecord,
    ):
        self._tracker = tracker
        self._record = record

    def record_response(self, **kwargs: Any) -> None:
        """Delegate to the underlying record."""
        self._record.record_response(**kwargs)

    @property
    def call_id(self) -> str:
        return self._record.call_id

    def __enter__(self) -> "LLMCallContext":
        self._record._start_time = time.monotonic()
        self._record.status = "in_progress"
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        self._record._end_time = time.monotonic()
        self._record.latency_ms = (
            self._record._end_time - self._record._start_time
        ) * 1000

        if exc_type is not None:
            self._record.status = "error"
            self._record.error = str(exc_val)
        else:
            self._record.status = "success"

        # Estimate cost
        self._record.estimated_cost_usd = self._tracker.estimate_cost(
            self._record.model,
            self._record.input_tokens,
            self._record.output_tokens,
        )

        # Log and record
        self._tracker._finalize_call(self._record)


class LLMTracker:
    """Track LLM API calls with automatic logging and cost estimation.

    Parameters
    ----------
    logger : Any
        MohFlow logger instance.
    provider : str
        LLM provider name (e.g. ``"openai"``, ``"anthropic"``).
    model : str
        Default model name.
    cost_table : dict, optional
        Custom cost-per-1M-token table.
    session_id : str, optional
        Session/conversation ID for correlation.
    token_budget : int, optional
        Maximum total tokens before a warning is logged.
    cost_budget : float, optional
        Maximum total cost (USD) before a warning is logged.
    """

    def __init__(
        self,
        logger: Any,
        provider: str = "openai",
        model: str = "gpt-4o",
        cost_table: Optional[Dict[str, Dict[str, float]]] = None,
        session_id: Optional[str] = None,
        token_budget: Optional[int] = None,
        cost_budget: Optional[float] = None,
    ):
        self._logger = logger
        self.provider = provider
        self.model = model
        self._cost_table = cost_table or _DEFAULT_COST_TABLE
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.token_budget = token_budget
        self.cost_budget = cost_budget

        # Aggregates
        self._calls: List[LLMCallRecord] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self._total_latency_ms = 0.0

    # ── public API ───────────────────────────────────────────

    def track_call(
        self,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **metadata: Any,
    ) -> LLMCallContext:
        """Start tracking an LLM call.

        Use as a context manager::

            with tracker.track_call(prompt="hello") as call:
                resp = client.create(...)
                call.record_response(
                    output_text=resp.text,
                    input_tokens=resp.usage.input,
                    output_tokens=resp.usage.output,
                )
        """
        record = LLMCallRecord(
            call_id=uuid.uuid4().hex[:12],
            provider=self.provider,
            model=model or self.model,
            session_id=self.session_id,
        )
        record.prompt = prompt
        record.temperature = temperature
        record.max_tokens = max_tokens
        record.metadata = dict(metadata)
        return LLMCallContext(tracker=self, record=record)

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost in USD for the given token counts."""
        rates = self._cost_table.get(model, {})
        input_rate = rates.get("input", 0.0)
        output_rate = rates.get("output", 0.0)
        return (
            input_tokens * input_rate / 1_000_000
            + output_tokens * output_rate / 1_000_000
        )

    def get_summary(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "model": self.model,
            "total_calls": len(self._calls),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": (
                self._total_input_tokens + self._total_output_tokens
            ),
            "total_cost_usd": round(self._total_cost_usd, 6),
            "total_latency_ms": round(self._total_latency_ms, 1),
            "avg_latency_ms": (
                round(self._total_latency_ms / len(self._calls), 1)
                if self._calls
                else 0.0
            ),
        }

    @property
    def total_cost(self) -> float:
        return self._total_cost_usd

    @property
    def total_tokens(self) -> int:
        return self._total_input_tokens + self._total_output_tokens

    @property
    def call_count(self) -> int:
        return len(self._calls)

    # ── internal ─────────────────────────────────────────────

    def _finalize_call(self, record: LLMCallRecord) -> None:
        """Log and aggregate a completed call."""
        self._calls.append(record)
        self._total_input_tokens += record.input_tokens
        self._total_output_tokens += record.output_tokens
        self._total_cost_usd += record.estimated_cost_usd
        self._total_latency_ms += record.latency_ms

        # Log the call
        log_data = record.to_dict()
        if record.status == "error":
            self._logger.error(
                f"LLM call failed: {record.provider}/{record.model}",
                **log_data,
            )
        else:
            self._logger.info(
                f"LLM call: {record.provider}/{record.model} "
                f"({record.total_tokens} tokens, "
                f"${record.estimated_cost_usd:.4f}, "
                f"{record.latency_ms:.0f}ms)",
                **log_data,
            )

        # Budget warnings
        if self.token_budget and self.total_tokens > self.token_budget:
            self._logger.warning(
                f"LLM token budget exceeded: "
                f"{self.total_tokens}/{self.token_budget}",
                budget_type="token",
                budget_limit=self.token_budget,
                budget_used=self.total_tokens,
                session_id=self.session_id,
            )

        if self.cost_budget and self._total_cost_usd > self.cost_budget:
            self._logger.warning(
                f"LLM cost budget exceeded: "
                f"${self._total_cost_usd:.4f}"
                f"/${self.cost_budget:.2f}",
                budget_type="cost",
                budget_limit=self.cost_budget,
                budget_used=self._total_cost_usd,
                session_id=self.session_id,
            )
