"""Tests for mohflow.actions: causal action logging with parent-child trees."""

import time
from unittest.mock import MagicMock, call

import pytest

from mohflow.actions import Action, ActionLogger

# -----------------------------------------------------------
# Action basics
# -----------------------------------------------------------


class TestActionInit:
    """Verify Action construction defaults and overrides."""

    def test_default_action_id_generated(self):
        logger = MagicMock()
        act = Action(logger, "deploy")
        assert isinstance(act.action_id, str)
        assert len(act.action_id) == 16

    def test_custom_action_id(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="custom-123")
        assert act.action_id == "custom-123"

    def test_parent_id_default_none(self):
        logger = MagicMock()
        act = Action(logger, "deploy")
        assert act.parent_id is None

    def test_parent_id_set(self):
        logger = MagicMock()
        act = Action(logger, "deploy", parent_id="parent-abc")
        assert act.parent_id == "parent-abc"

    def test_context_kwargs_stored(self):
        logger = MagicMock()
        act = Action(logger, "deploy", region="us-east", env="prod")
        assert act.context == {"region": "us-east", "env": "prod"}

    def test_initial_status_is_pending(self):
        logger = MagicMock()
        act = Action(logger, "deploy")
        assert act.status == "pending"

    def test_initial_children_empty(self):
        logger = MagicMock()
        act = Action(logger, "deploy")
        assert act.children == []

    def test_elapsed_ms_zero_before_start(self):
        logger = MagicMock()
        act = Action(logger, "deploy")
        assert act.elapsed_ms == 0.0


# -----------------------------------------------------------
# Context manager protocol
# -----------------------------------------------------------


class TestActionContextManager:
    """Action used as a context manager: start/succeed/fail."""

    def test_enter_sets_started_status(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with act:
            assert act.status == "started"

    def test_enter_logs_started(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with act:
            pass
        # First call is the "started" log
        started_call = logger.info.call_args_list[0]
        assert "started" in started_call[0][0]

    def test_successful_exit_sets_succeeded(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with act:
            pass
        assert act.status == "succeeded"

    def test_successful_exit_logs_succeeded_with_elapsed(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with act:
            pass
        # Second info call is the "succeeded" log
        succeeded_call = logger.info.call_args_list[1]
        assert "succeeded" in succeeded_call[0][0]
        assert "elapsed_ms" in succeeded_call[1]

    def test_failure_sets_failed_status(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with pytest.raises(ValueError):
            with act:
                raise ValueError("boom")
        assert act.status == "failed"

    def test_failure_logs_error_with_details(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with pytest.raises(ValueError):
            with act:
                raise ValueError("boom")
        logger.error.assert_called_once()
        kwargs = logger.error.call_args[1]
        assert kwargs["action_status"] == "failed"
        assert kwargs["error"] == "boom"
        assert kwargs["error_type"] == "ValueError"
        assert "elapsed_ms" in kwargs

    def test_exception_not_suppressed(self):
        """Action.__exit__ must NOT suppress exceptions."""
        logger = MagicMock()
        act = Action(logger, "deploy")
        with pytest.raises(RuntimeError, match="not suppressed"):
            with act:
                raise RuntimeError("not suppressed")

    def test_exit_returns_none(self):
        logger = MagicMock()
        act = Action(logger, "deploy")
        result = act.__exit__(None, None, None)
        assert result is None


# -----------------------------------------------------------
# Elapsed time tracking
# -----------------------------------------------------------


class TestElapsedTime:
    """Verify elapsed_ms tracking behaviour."""

    def test_elapsed_during_execution(self):
        logger = MagicMock()
        act = Action(logger, "slow")
        with act:
            time.sleep(0.02)
            assert act.elapsed_ms >= 15  # at least ~15ms

    def test_elapsed_frozen_after_exit(self):
        logger = MagicMock()
        act = Action(logger, "fast")
        with act:
            pass
        t1 = act.elapsed_ms
        time.sleep(0.01)
        t2 = act.elapsed_ms
        assert t1 == t2  # frozen once _end_time is set

    def test_elapsed_zero_when_never_started(self):
        logger = MagicMock()
        act = Action(logger, "never")
        assert act.elapsed_ms == 0.0


# -----------------------------------------------------------
# Parent-child relationships
# -----------------------------------------------------------


class TestChildActions:
    """Verify child() creates linked actions."""

    def test_child_has_parent_id(self):
        logger = MagicMock()
        parent = Action(logger, "parent", action_id="p1")
        child = parent.child("child_step")
        assert child.parent_id == "p1"

    def test_child_appears_in_parent_children(self):
        logger = MagicMock()
        parent = Action(logger, "parent", action_id="p1")
        child = parent.child("child_step")
        assert child.action_id in parent.children

    def test_child_inherits_parent_context(self):
        logger = MagicMock()
        parent = Action(logger, "parent", region="us-east")
        child = parent.child("child_step")
        assert child.context["region"] == "us-east"

    def test_child_override_context(self):
        logger = MagicMock()
        parent = Action(logger, "parent", region="us-east")
        child = parent.child("child_step", region="eu-west")
        assert child.context["region"] == "eu-west"

    def test_child_adds_extra_context(self):
        logger = MagicMock()
        parent = Action(logger, "parent", region="us-east")
        child = parent.child("child_step", shard=3)
        assert child.context["region"] == "us-east"
        assert child.context["shard"] == 3

    def test_children_list_is_copy(self):
        """Modifying the returned list must not affect internal state."""
        logger = MagicMock()
        parent = Action(logger, "parent")
        parent.child("c1")
        children = parent.children
        children.append("hacked")
        assert "hacked" not in parent.children

    def test_child_usable_as_context_manager(self):
        logger = MagicMock()
        parent = Action(logger, "parent", action_id="p1")
        child = parent.child("child_step")
        with child:
            child.info("working")
        assert child.status == "succeeded"

    def test_multiple_children(self):
        logger = MagicMock()
        parent = Action(logger, "parent", action_id="p1")
        c1 = parent.child("step1")
        c2 = parent.child("step2")
        c3 = parent.child("step3")
        assert len(parent.children) == 3
        assert c1.action_id in parent.children
        assert c2.action_id in parent.children
        assert c3.action_id in parent.children


# -----------------------------------------------------------
# Nested action trees (3+ levels)
# -----------------------------------------------------------


class TestNestedActionTrees:
    """Three or more levels of nesting."""

    def test_three_level_nesting(self):
        logger = MagicMock()
        root = Action(logger, "root", action_id="r")
        with root:
            child = root.child("level2")
            with child:
                grandchild = child.child("level3")
                with grandchild:
                    grandchild.info("leaf work")
                assert grandchild.status == "succeeded"
            assert child.status == "succeeded"
        assert root.status == "succeeded"
        assert grandchild.parent_id == child.action_id
        assert child.parent_id == "r"

    def test_deep_context_propagation(self):
        logger = MagicMock()
        root = Action(logger, "root", trace_id="T1")
        child = root.child("mid")
        grandchild = child.child("leaf")
        assert grandchild.context["trace_id"] == "T1"

    def test_failure_at_leaf_propagates(self):
        logger = MagicMock()
        root = Action(logger, "root")
        with pytest.raises(ValueError):
            with root:
                child = root.child("child")
                with child:
                    grandchild = child.child("grandchild")
                    with grandchild:
                        raise ValueError("deep error")
        assert grandchild.status == "failed"
        assert child.status == "failed"
        assert root.status == "failed"


# -----------------------------------------------------------
# Log levels
# -----------------------------------------------------------


class TestActionLogLevels:
    """All four log levels delegate correctly."""

    def test_info(self):
        logger = MagicMock()
        act = Action(logger, "op", action_id="a1")
        act.info("hello", extra_key="val")
        logger.info.assert_called_once()
        args, kwargs = logger.info.call_args
        assert args[0] == "hello"
        assert kwargs["action_id"] == "a1"
        assert kwargs["extra_key"] == "val"

    def test_warning(self):
        logger = MagicMock()
        act = Action(logger, "op", action_id="a1")
        act.warning("caution")
        logger.warning.assert_called_once()
        assert logger.warning.call_args[0][0] == "caution"

    def test_error(self):
        logger = MagicMock()
        act = Action(logger, "op", action_id="a1")
        act.error("bad")
        logger.error.assert_called_once()

    def test_debug(self):
        logger = MagicMock()
        act = Action(logger, "op", action_id="a1")
        act.debug("trace")
        logger.debug.assert_called_once()

    def test_log_includes_parent_id_when_set(self):
        logger = MagicMock()
        act = Action(logger, "op", action_id="a1", parent_id="p1")
        act.info("msg")
        kwargs = logger.info.call_args[1]
        assert kwargs["parent_action_id"] == "p1"

    def test_log_no_parent_id_when_none(self):
        logger = MagicMock()
        act = Action(logger, "op", action_id="a1")
        act.info("msg")
        kwargs = logger.info.call_args[1]
        assert "parent_action_id" not in kwargs

    def test_log_includes_context(self):
        logger = MagicMock()
        act = Action(logger, "op", action_id="a1", env="prod")
        act.info("msg")
        kwargs = logger.info.call_args[1]
        assert kwargs["env"] == "prod"


# -----------------------------------------------------------
# to_dict serialization
# -----------------------------------------------------------


class TestActionToDict:
    """Verify to_dict() serialization."""

    def test_basic_fields(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        d = act.to_dict()
        assert d["action_id"] == "a1"
        assert d["action_name"] == "deploy"
        assert d["status"] == "pending"

    def test_no_parent_id_when_none(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        d = act.to_dict()
        assert "parent_action_id" not in d

    def test_parent_id_included(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1", parent_id="p1")
        d = act.to_dict()
        assert d["parent_action_id"] == "p1"

    def test_children_included(self):
        logger = MagicMock()
        parent = Action(logger, "parent", action_id="p1")
        c = parent.child("child")
        d = parent.to_dict()
        assert d["children"] == [c.action_id]

    def test_no_children_key_when_empty(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        d = act.to_dict()
        assert "children" not in d

    def test_elapsed_ms_after_completion(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with act:
            pass
        d = act.to_dict()
        assert "elapsed_ms" in d
        assert d["elapsed_ms"] >= 0

    def test_no_elapsed_before_start(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        d = act.to_dict()
        assert "elapsed_ms" not in d

    def test_context_merged(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1", env="prod", region="us")
        d = act.to_dict()
        assert d["env"] == "prod"
        assert d["region"] == "us"

    def test_status_after_success(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with act:
            pass
        assert act.to_dict()["status"] == "succeeded"

    def test_status_after_failure(self):
        logger = MagicMock()
        act = Action(logger, "deploy", action_id="a1")
        with pytest.raises(RuntimeError):
            with act:
                raise RuntimeError("fail")
        assert act.to_dict()["status"] == "failed"


# -----------------------------------------------------------
# Status transitions
# -----------------------------------------------------------


class TestStatusTransitions:
    """Verify pending -> started -> succeeded/failed transitions."""

    def test_pending_to_started_to_succeeded(self):
        logger = MagicMock()
        act = Action(logger, "op")
        assert act.status == "pending"
        with act:
            assert act.status == "started"
        assert act.status == "succeeded"

    def test_pending_to_started_to_failed(self):
        logger = MagicMock()
        act = Action(logger, "op")
        assert act.status == "pending"
        with pytest.raises(Exception):
            with act:
                assert act.status == "started"
                raise Exception("oops")
        assert act.status == "failed"


# -----------------------------------------------------------
# ActionLogger factory
# -----------------------------------------------------------


class TestActionLogger:
    """Verify the factory creates actions correctly."""

    def test_creates_action(self):
        logger = MagicMock()
        factory = ActionLogger(logger)
        act = factory.action("deploy")
        assert isinstance(act, Action)
        assert act.action_name == "deploy"

    def test_passes_context(self):
        logger = MagicMock()
        factory = ActionLogger(logger)
        act = factory.action("deploy", env="staging")
        assert act.context["env"] == "staging"

    def test_action_uses_factory_logger(self):
        logger = MagicMock()
        factory = ActionLogger(logger)
        act = factory.action("deploy")
        with act:
            act.info("hello")
        assert logger.info.called

    def test_no_parent_id_for_top_level(self):
        logger = MagicMock()
        factory = ActionLogger(logger)
        act = factory.action("deploy")
        assert act.parent_id is None

    def test_multiple_actions_independent(self):
        logger = MagicMock()
        factory = ActionLogger(logger)
        a1 = factory.action("deploy")
        a2 = factory.action("rollback")
        assert a1.action_id != a2.action_id
        assert a1.action_name == "deploy"
        assert a2.action_name == "rollback"


# -----------------------------------------------------------
# Context propagation to children via _log
# -----------------------------------------------------------


class TestContextPropagation:
    """Ensure context flows through the _log calls to the logger."""

    def test_parent_context_in_child_log(self):
        logger = MagicMock()
        parent = Action(logger, "parent", action_id="p1", trace_id="T1")
        child = parent.child("child")
        child.info("msg")
        kwargs = logger.info.call_args[1]
        assert kwargs["trace_id"] == "T1"
        assert kwargs["parent_action_id"] == "p1"

    def test_child_context_overrides_parent_in_log(self):
        logger = MagicMock()
        parent = Action(logger, "parent", version="1")
        child = parent.child("child", version="2")
        child.info("msg")
        kwargs = logger.info.call_args[1]
        assert kwargs["version"] == "2"

    def test_extra_kwargs_in_log_override_context(self):
        logger = MagicMock()
        act = Action(logger, "op", env="prod")
        act.info("msg", env="staging")
        kwargs = logger.info.call_args[1]
        assert kwargs["env"] == "staging"
