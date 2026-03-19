"""Tests for mohflow.integrations.llm: LLM call tracking, cost estimation, budgets."""

import time
from unittest.mock import MagicMock, patch

import pytest

from mohflow.integrations.llm import (
    LLMCallContext,
    LLMCallRecord,
    LLMTracker,
    _DEFAULT_COST_TABLE,
)

# -----------------------------------------------------------
# LLMCallRecord
# -----------------------------------------------------------


class TestLLMCallRecordInit:
    """Record construction defaults."""

    def test_fields_set(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        assert rec.call_id == "c1"
        assert rec.provider == "openai"
        assert rec.model == "gpt-4"

    def test_session_id_optional(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        assert rec.session_id is None

    def test_session_id_set(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4", session_id="s1")
        assert rec.session_id == "s1"

    def test_initial_defaults(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        assert rec.input_tokens == 0
        assert rec.output_tokens == 0
        assert rec.total_tokens == 0
        assert rec.latency_ms == 0.0
        assert rec.estimated_cost_usd == 0.0
        assert rec.status == "pending"
        assert rec.error is None
        assert rec.prompt is None
        assert rec.output_text is None
        assert rec.temperature is None
        assert rec.max_tokens is None
        assert rec.metadata == {}


class TestLLMCallRecordRecordResponse:
    """record_response() captures output details."""

    def test_basic_response(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        rec.record_response(
            output_text="hello",
            input_tokens=100,
            output_tokens=50,
        )
        assert rec.output_text == "hello"
        assert rec.input_tokens == 100
        assert rec.output_tokens == 50
        assert rec.total_tokens == 150

    def test_explicit_total_tokens(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        rec.record_response(
            input_tokens=100,
            output_tokens=50,
            total_tokens=200,
        )
        assert rec.total_tokens == 200

    def test_metadata_kwargs(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        rec.record_response(
            input_tokens=10,
            output_tokens=5,
            finish_reason="stop",
        )
        assert rec.metadata["finish_reason"] == "stop"

    def test_metadata_merges(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        rec.metadata = {"existing": True}
        rec.record_response(input_tokens=1, output_tokens=1, new_key="val")
        assert rec.metadata["existing"] is True
        assert rec.metadata["new_key"] == "val"


class TestLLMCallRecordToDict:
    """Serialization."""

    def test_basic_fields(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        d = rec.to_dict()
        assert d["call_id"] == "c1"
        assert d["provider"] == "openai"
        assert d["model"] == "gpt-4"
        assert d["status"] == "pending"
        assert d["input_tokens"] == 0
        assert d["output_tokens"] == 0
        assert d["total_tokens"] == 0
        assert d["latency_ms"] == 0.0
        assert d["estimated_cost_usd"] == 0.0

    def test_session_id_included_when_set(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4", session_id="s1")
        d = rec.to_dict()
        assert d["session_id"] == "s1"

    def test_session_id_excluded_when_none(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        d = rec.to_dict()
        assert "session_id" not in d

    def test_temperature_included_when_set(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        rec.temperature = 0.7
        d = rec.to_dict()
        assert d["temperature"] == 0.7

    def test_temperature_excluded_when_none(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        d = rec.to_dict()
        assert "temperature" not in d

    def test_error_included_when_set(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        rec.error = "timeout"
        d = rec.to_dict()
        assert d["error"] == "timeout"

    def test_error_excluded_when_none(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        d = rec.to_dict()
        assert "error" not in d

    def test_metadata_merged_into_dict(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        rec.metadata = {"finish_reason": "stop"}
        d = rec.to_dict()
        assert d["finish_reason"] == "stop"

    def test_empty_metadata_no_extra_keys(self):
        rec = LLMCallRecord("c1", "openai", "gpt-4")
        d = rec.to_dict()
        expected_keys = {
            "call_id",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "latency_ms",
            "estimated_cost_usd",
            "status",
        }
        assert set(d.keys()) == expected_keys


# -----------------------------------------------------------
# LLMCallContext
# -----------------------------------------------------------


class TestLLMCallContext:
    """Context manager for a single LLM call."""

    def test_call_id_property(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hi")
        assert isinstance(ctx.call_id, str)
        assert len(ctx.call_id) == 12

    def test_enter_sets_in_progress(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hi")
        with ctx:
            assert ctx._record.status == "in_progress"

    def test_exit_sets_success(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hi")
        with ctx:
            ctx.record_response(input_tokens=10, output_tokens=5)
        assert ctx._record.status == "success"

    def test_exit_sets_error_on_exception(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hi")
        with pytest.raises(ValueError):
            with ctx:
                raise ValueError("boom")
        assert ctx._record.status == "error"
        assert ctx._record.error == "boom"

    def test_latency_measured(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hi")
        with ctx:
            time.sleep(0.02)
            ctx.record_response(input_tokens=10, output_tokens=5)
        assert ctx._record.latency_ms >= 15

    def test_record_response_delegates(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hi")
        with ctx:
            ctx.record_response(
                output_text="world",
                input_tokens=10,
                output_tokens=5,
            )
        assert ctx._record.output_text == "world"
        assert ctx._record.input_tokens == 10

    def test_exception_not_suppressed(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        with pytest.raises(RuntimeError, match="not caught"):
            with tracker.track_call(prompt="hi"):
                raise RuntimeError("not caught")


# -----------------------------------------------------------
# LLMTracker initialization
# -----------------------------------------------------------


class TestLLMTrackerInit:
    """Tracker construction and defaults."""

    def test_defaults(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        assert tracker.provider == "openai"
        assert tracker.model == "gpt-4o"
        assert tracker.token_budget is None
        assert tracker.cost_budget is None

    def test_custom_params(self):
        logger = MagicMock()
        tracker = LLMTracker(
            logger,
            provider="anthropic",
            model="claude-opus-4-6",
            token_budget=100_000,
            cost_budget=10.0,
        )
        assert tracker.provider == "anthropic"
        assert tracker.model == "claude-opus-4-6"
        assert tracker.token_budget == 100_000
        assert tracker.cost_budget == 10.0

    def test_session_id_generated(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        assert isinstance(tracker.session_id, str)
        assert len(tracker.session_id) == 12

    def test_custom_session_id(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, session_id="my-session")
        assert tracker.session_id == "my-session"

    def test_initial_aggregates(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        assert tracker.total_cost == 0.0
        assert tracker.total_tokens == 0
        assert tracker.call_count == 0

    def test_custom_cost_table(self):
        logger = MagicMock()
        custom = {"my-model": {"input": 1.0, "output": 2.0}}
        tracker = LLMTracker(logger, cost_table=custom)
        assert tracker._cost_table == custom


# -----------------------------------------------------------
# Cost estimation
# -----------------------------------------------------------


class TestCostEstimation:
    """estimate_cost() using the cost table."""

    def test_known_model(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        cost = tracker.estimate_cost("gpt-4o", 1_000_000, 1_000_000)
        # gpt-4o: input=2.50, output=10.0
        expected = 2.50 + 10.0
        assert abs(cost - expected) < 0.01

    def test_unknown_model_zero_cost(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        cost = tracker.estimate_cost("unknown-model", 1000, 1000)
        assert cost == 0.0

    def test_custom_cost_table(self):
        logger = MagicMock()
        custom = {"local-llm": {"input": 0.0, "output": 0.0}}
        tracker = LLMTracker(logger, cost_table=custom)
        cost = tracker.estimate_cost("local-llm", 1000, 1000)
        assert cost == 0.0

    def test_zero_tokens(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        cost = tracker.estimate_cost("gpt-4", 0, 0)
        assert cost == 0.0

    def test_cost_in_context(self):
        """Cost is computed on exit from context."""
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as call:
            call.record_response(input_tokens=1000, output_tokens=500)
        # gpt-4o: input=2.50/1M, output=10.0/1M
        expected = 1000 * 2.50 / 1_000_000 + 500 * 10.0 / 1_000_000
        assert abs(call._record.estimated_cost_usd - expected) < 1e-8

    def test_default_cost_table_has_known_models(self):
        assert "gpt-4" in _DEFAULT_COST_TABLE
        assert "claude-opus-4-6" in _DEFAULT_COST_TABLE
        assert "gpt-4o" in _DEFAULT_COST_TABLE


# -----------------------------------------------------------
# track_call() context manager
# -----------------------------------------------------------


class TestTrackCall:
    """track_call() produces a working context manager."""

    def test_returns_llm_call_context(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hello")
        assert isinstance(ctx, LLMCallContext)

    def test_prompt_stored(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(prompt="hello")
        assert ctx._record.prompt == "hello"

    def test_model_override(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        ctx = tracker.track_call(model="gpt-4")
        assert ctx._record.model == "gpt-4"

    def test_default_model_used(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        ctx = tracker.track_call()
        assert ctx._record.model == "gpt-4o"

    def test_temperature_stored(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(temperature=0.5)
        assert ctx._record.temperature == 0.5

    def test_max_tokens_stored(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(max_tokens=100)
        assert ctx._record.max_tokens == 100

    def test_metadata_kwargs(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        ctx = tracker.track_call(custom_field="val")
        assert ctx._record.metadata["custom_field"] == "val"

    def test_session_id_propagated(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, session_id="sess-1")
        ctx = tracker.track_call()
        assert ctx._record.session_id == "sess-1"


# -----------------------------------------------------------
# Successful call flow and logging
# -----------------------------------------------------------


class TestSuccessfulCallFlow:
    """Complete successful call lifecycle."""

    def test_success_logs_info(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call(prompt="hello") as call:
            call.record_response(
                output_text="hi",
                input_tokens=10,
                output_tokens=5,
            )
        logger.info.assert_called_once()
        msg = logger.info.call_args[0][0]
        assert "LLM call" in msg
        assert "gpt-4o" in msg

    def test_success_increments_aggregates(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as call:
            call.record_response(input_tokens=100, output_tokens=50)
        assert tracker.total_tokens == 150
        assert tracker.call_count == 1
        assert tracker.total_cost > 0

    def test_log_data_includes_record_dict(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as call:
            call.record_response(input_tokens=10, output_tokens=5)
        kwargs = logger.info.call_args[1]
        assert "call_id" in kwargs
        assert kwargs["status"] == "success"


# -----------------------------------------------------------
# Error call flow
# -----------------------------------------------------------


class TestErrorCallFlow:
    """Call that raises an exception."""

    def test_error_logs_error(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with pytest.raises(RuntimeError):
            with tracker.track_call() as call:
                raise RuntimeError("api timeout")
        logger.error.assert_called_once()
        msg = logger.error.call_args[0][0]
        assert "failed" in msg

    def test_error_record_status(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        with pytest.raises(RuntimeError):
            with tracker.track_call() as call:
                raise RuntimeError("api timeout")
        assert call._record.status == "error"
        assert call._record.error == "api timeout"

    def test_error_still_aggregated(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        with pytest.raises(RuntimeError):
            with tracker.track_call():
                raise RuntimeError("fail")
        assert tracker.call_count == 1

    def test_error_latency_measured(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        with pytest.raises(RuntimeError):
            with tracker.track_call() as call:
                time.sleep(0.02)
                raise RuntimeError("fail")
        assert call._record.latency_ms >= 15


# -----------------------------------------------------------
# Token budget warning
# -----------------------------------------------------------


class TestTokenBudget:
    """Warning when token budget exceeded."""

    def test_warning_logged_when_exceeded(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o", token_budget=100)
        with tracker.track_call() as call:
            call.record_response(input_tokens=80, output_tokens=30)
        # total_tokens=110 > budget=100
        logger.warning.assert_called()
        warning_msg = logger.warning.call_args[0][0]
        assert "token budget" in warning_msg.lower()

    def test_no_warning_within_budget(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o", token_budget=1000)
        with tracker.track_call() as call:
            call.record_response(input_tokens=10, output_tokens=5)
        logger.warning.assert_not_called()

    def test_warning_includes_budget_info(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o", token_budget=50)
        with tracker.track_call() as call:
            call.record_response(input_tokens=40, output_tokens=20)
        kwargs = logger.warning.call_args[1]
        assert kwargs["budget_type"] == "token"
        assert kwargs["budget_limit"] == 50
        assert kwargs["budget_used"] == 60


# -----------------------------------------------------------
# Cost budget warning
# -----------------------------------------------------------


class TestCostBudget:
    """Warning when cost budget exceeded."""

    def test_warning_logged_when_exceeded(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4", cost_budget=0.001)
        with tracker.track_call() as call:
            call.record_response(input_tokens=10000, output_tokens=5000)
        # gpt-4: input=30/1M, output=60/1M
        # cost = 10000*30/1M + 5000*60/1M = 0.3 + 0.3 = 0.6 >> 0.001
        logger.warning.assert_called()
        warning_msg = logger.warning.call_args[0][0]
        assert "cost budget" in warning_msg.lower()

    def test_no_warning_within_cost_budget(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o-mini", cost_budget=100.0)
        with tracker.track_call() as call:
            call.record_response(input_tokens=10, output_tokens=5)
        logger.warning.assert_not_called()

    def test_warning_includes_cost_info(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4", cost_budget=0.0001)
        with tracker.track_call() as call:
            call.record_response(input_tokens=10000, output_tokens=5000)
        kwargs = logger.warning.call_args[1]
        assert kwargs["budget_type"] == "cost"
        assert kwargs["budget_limit"] == 0.0001


# -----------------------------------------------------------
# Multiple calls aggregation
# -----------------------------------------------------------


class TestMultipleCallsAggregation:
    """Aggregate statistics across multiple calls."""

    def test_multiple_calls_summed(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        for _ in range(3):
            with tracker.track_call() as call:
                call.record_response(input_tokens=100, output_tokens=50)
        assert tracker.call_count == 3
        assert tracker.total_tokens == 450  # 3 * 150

    def test_total_cost_accumulated(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as call:
            call.record_response(input_tokens=100, output_tokens=50)
        cost1 = tracker.total_cost
        with tracker.track_call() as call:
            call.record_response(input_tokens=100, output_tokens=50)
        assert tracker.total_cost > cost1

    def test_total_latency_accumulated(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as call:
            call.record_response(input_tokens=10, output_tokens=5)
        with tracker.track_call() as call:
            call.record_response(input_tokens=10, output_tokens=5)
        summary = tracker.get_summary()
        assert summary["total_latency_ms"] >= 0


# -----------------------------------------------------------
# get_summary()
# -----------------------------------------------------------


class TestGetSummary:
    """Aggregate summary dict."""

    def test_empty_summary(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o", session_id="s1")
        s = tracker.get_summary()
        assert s["session_id"] == "s1"
        assert s["provider"] == "openai"
        assert s["model"] == "gpt-4o"
        assert s["total_calls"] == 0
        assert s["total_tokens"] == 0
        assert s["total_cost_usd"] == 0.0
        assert s["avg_latency_ms"] == 0.0

    def test_summary_after_calls(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as call:
            call.record_response(input_tokens=100, output_tokens=50)
        s = tracker.get_summary()
        assert s["total_calls"] == 1
        assert s["total_input_tokens"] == 100
        assert s["total_output_tokens"] == 50
        assert s["total_tokens"] == 150
        assert s["total_cost_usd"] > 0
        assert s["avg_latency_ms"] >= 0

    def test_avg_latency_computed(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as c:
            time.sleep(0.01)
            c.record_response(input_tokens=10, output_tokens=5)
        with tracker.track_call() as c:
            time.sleep(0.01)
            c.record_response(input_tokens=10, output_tokens=5)
        s = tracker.get_summary()
        assert s["avg_latency_ms"] > 0
        # avg should be approximately total / 2
        expected_avg = s["total_latency_ms"] / 2
        assert s["avg_latency_ms"] == pytest.approx(expected_avg, abs=0.2)


# -----------------------------------------------------------
# Properties
# -----------------------------------------------------------


class TestTrackerProperties:
    """total_cost, total_tokens, call_count."""

    def test_total_cost_starts_zero(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        assert tracker.total_cost == 0.0

    def test_total_tokens_starts_zero(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        assert tracker.total_tokens == 0

    def test_call_count_starts_zero(self):
        logger = MagicMock()
        tracker = LLMTracker(logger)
        assert tracker.call_count == 0

    def test_properties_reflect_calls(self):
        logger = MagicMock()
        tracker = LLMTracker(logger, model="gpt-4o")
        with tracker.track_call() as c:
            c.record_response(input_tokens=100, output_tokens=50)
        assert tracker.total_tokens == 150
        assert tracker.call_count == 1
        assert tracker.total_cost > 0
