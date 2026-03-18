"""Tests for F2: Processor Pipeline Architecture."""

import pytest
from mohflow.processors import (
    ProcessorPipeline,
    DropEvent,
    add_timestamp,
    add_log_level,
    rename_keys,
    drop_keys,
    add_static_fields,
    filter_by_level,
    filter_by_key,
    censor_keys,
)


class TestProcessorPipeline:
    """Test the processor pipeline core."""

    def test_empty_pipeline(self):
        pipeline = ProcessorPipeline()
        event = {"message": "hello"}
        result = pipeline.process(event)
        assert result == {"message": "hello"}

    def test_single_processor(self):
        def uppercase_msg(event):
            event["message"] = event["message"].upper()
            return event

        pipeline = ProcessorPipeline([uppercase_msg])
        result = pipeline.process({"message": "hello"})
        assert result["message"] == "HELLO"

    def test_chained_processors(self):
        def add_a(event):
            event["a"] = 1
            return event

        def add_b(event):
            event["b"] = 2
            return event

        pipeline = ProcessorPipeline([add_a, add_b])
        result = pipeline.process({"message": "test"})
        assert result["a"] == 1
        assert result["b"] == 2

    def test_processor_returning_none_drops_event(self):
        def drop_all(event):
            return None

        pipeline = ProcessorPipeline([drop_all])
        result = pipeline.process({"message": "hello"})
        assert result is None

    def test_drop_event_exception(self):
        def dropper(event):
            raise DropEvent()

        pipeline = ProcessorPipeline([dropper])
        result = pipeline.process({"message": "hello"})
        assert result is None

    def test_drop_stops_chain(self):
        call_count = 0

        def counter(event):
            nonlocal call_count
            call_count += 1
            return event

        def dropper(event):
            return None

        pipeline = ProcessorPipeline([counter, dropper, counter])
        result = pipeline.process({"message": "test"})
        assert result is None
        assert call_count == 1  # Second counter never called

    def test_add_method(self):
        pipeline = ProcessorPipeline()

        def add_field(event):
            event["added"] = True
            return event

        pipeline.add(add_field)
        result = pipeline.process({"message": "test"})
        assert result["added"] is True

    def test_add_returns_self(self):
        pipeline = ProcessorPipeline()
        result = pipeline.add(lambda e: e)
        assert result is pipeline

    def test_remove_processor(self):
        def proc(event):
            event["x"] = 1
            return event

        pipeline = ProcessorPipeline([proc])
        pipeline.remove(proc)
        assert len(pipeline) == 0

    def test_clear(self):
        pipeline = ProcessorPipeline([lambda e: e, lambda e: e])
        pipeline.clear()
        assert len(pipeline) == 0

    def test_processors_property(self):
        def p1(event):
            return event

        def p2(event):
            return event

        pipeline = ProcessorPipeline([p1, p2])
        procs = pipeline.processors
        assert len(procs) == 2
        # Should be a copy
        procs.append(lambda e: e)
        assert len(pipeline) == 2

    def test_len(self):
        pipeline = ProcessorPipeline([lambda e: e, lambda e: e, lambda e: e])
        assert len(pipeline) == 3

    def test_repr(self):
        pipeline = ProcessorPipeline([add_timestamp()])
        r = repr(pipeline)
        assert "ProcessorPipeline" in r
        assert "add_timestamp" in r

    def test_chaining_with_add(self):
        pipeline = (
            ProcessorPipeline().add(add_timestamp()).add(add_log_level())
        )
        assert len(pipeline) == 2


class TestAddTimestamp:
    """Test add_timestamp processor."""

    def test_adds_timestamp(self):
        proc = add_timestamp()
        result = proc({"message": "test"})
        assert "timestamp" in result
        assert "T" in result["timestamp"]  # ISO format

    def test_custom_key(self):
        proc = add_timestamp(key="ts")
        result = proc({"message": "test"})
        assert "ts" in result
        assert "timestamp" not in result

    def test_custom_format(self):
        proc = add_timestamp(fmt="%Y-%m-%d")
        result = proc({"message": "test"})
        assert len(result["timestamp"]) == 10  # YYYY-MM-DD


class TestAddLogLevel:
    """Test add_log_level processor."""

    def test_adds_default_level(self):
        proc = add_log_level()
        result = proc({"message": "test"})
        assert result["level"] == "INFO"

    def test_preserves_existing_level(self):
        proc = add_log_level()
        result = proc({"message": "test", "level": "ERROR"})
        assert result["level"] == "ERROR"

    def test_custom_key(self):
        proc = add_log_level(key="severity")
        result = proc({"message": "test"})
        assert result["severity"] == "INFO"


class TestRenameKeys:
    """Test rename_keys processor."""

    def test_renames_key(self):
        proc = rename_keys({"old_name": "new_name"})
        result = proc({"old_name": "value", "other": "keep"})
        assert "new_name" in result
        assert "old_name" not in result
        assert result["other"] == "keep"

    def test_missing_key_no_error(self):
        proc = rename_keys({"missing": "new"})
        result = proc({"existing": "value"})
        assert result == {"existing": "value"}

    def test_multiple_renames(self):
        proc = rename_keys({"a": "x", "b": "y"})
        result = proc({"a": 1, "b": 2, "c": 3})
        assert result == {"x": 1, "y": 2, "c": 3}


class TestDropKeys:
    """Test drop_keys processor."""

    def test_drops_keys(self):
        proc = drop_keys(["secret", "password"])
        result = proc(
            {
                "message": "test",
                "secret": "hidden",
                "password": "hunter2",
            }
        )
        assert "secret" not in result
        assert "password" not in result
        assert result["message"] == "test"

    def test_missing_key_no_error(self):
        proc = drop_keys(["nonexistent"])
        result = proc({"message": "test"})
        assert result == {"message": "test"}


class TestAddStaticFields:
    """Test add_static_fields processor."""

    def test_adds_fields(self):
        proc = add_static_fields({"service": "myapp", "env": "prod"})
        result = proc({"message": "test"})
        assert result["service"] == "myapp"
        assert result["env"] == "prod"

    def test_does_not_overwrite(self):
        proc = add_static_fields({"service": "default"})
        result = proc({"message": "test", "service": "custom"})
        assert result["service"] == "custom"


class TestFilterByLevel:
    """Test filter_by_level processor."""

    def test_passes_above_level(self):
        proc = filter_by_level("INFO")
        result = proc({"message": "test", "level": "ERROR"})
        assert result is not None

    def test_passes_at_level(self):
        proc = filter_by_level("INFO")
        result = proc({"message": "test", "level": "INFO"})
        assert result is not None

    def test_drops_below_level(self):
        proc = filter_by_level("INFO")
        result = proc({"message": "test", "level": "DEBUG"})
        assert result is None

    def test_case_insensitive(self):
        proc = filter_by_level("warning")
        result = proc({"message": "test", "level": "WARNING"})
        assert result is not None

    def test_all_levels(self):
        proc = filter_by_level("WARNING")
        assert proc({"level": "DEBUG"}) is None
        assert proc({"level": "INFO"}) is None
        assert proc({"level": "WARNING"}) is not None
        assert proc({"level": "ERROR"}) is not None
        assert proc({"level": "CRITICAL"}) is not None


class TestFilterByKey:
    """Test filter_by_key processor."""

    def test_passes_matching(self):
        proc = filter_by_key("status", lambda v: v == 200)
        result = proc({"message": "test", "status": 200})
        assert result is not None

    def test_drops_non_matching(self):
        proc = filter_by_key("status", lambda v: v < 400)
        result = proc({"message": "test", "status": 500})
        assert result is None

    def test_missing_key_passes(self):
        proc = filter_by_key("status", lambda v: v == 200)
        result = proc({"message": "test"})
        assert result is not None


class TestCensorKeys:
    """Test censor_keys processor."""

    def test_censors_keys(self):
        proc = censor_keys(["password", "token"])
        result = proc(
            {
                "message": "test",
                "password": "secret",
                "token": "abc123",
            }
        )
        assert result["password"] == "***"
        assert result["token"] == "***"
        assert result["message"] == "test"

    def test_custom_replacement(self):
        proc = censor_keys(["ssn"], replacement="[REDACTED]")
        result = proc({"ssn": "123-45-6789"})
        assert result["ssn"] == "[REDACTED]"

    def test_missing_key_no_error(self):
        proc = censor_keys(["secret"])
        result = proc({"message": "test"})
        assert result == {"message": "test"}


class TestProcessorPipelineIntegration:
    """Integration tests for full pipeline scenarios."""

    def test_full_pipeline(self):
        pipeline = ProcessorPipeline(
            [
                add_timestamp(),
                add_log_level(),
                add_static_fields({"service": "myapp"}),
                rename_keys({"service": "svc"}),
                drop_keys(["internal"]),
                censor_keys(["password"]),
            ]
        )
        event = {
            "message": "login",
            "internal": "debug-data",
            "password": "secret",
        }
        result = pipeline.process(event)
        assert "timestamp" in result
        assert result["level"] == "INFO"
        assert result["svc"] == "myapp"
        assert "internal" not in result
        assert result["password"] == "***"

    def test_pipeline_with_filter_drop(self):
        pipeline = ProcessorPipeline(
            [
                filter_by_level("WARNING"),
                add_timestamp(),
            ]
        )
        # DEBUG should be dropped before timestamp
        result = pipeline.process({"message": "test", "level": "DEBUG"})
        assert result is None

    def test_pipeline_preserves_order(self):
        order = []

        def make_tracker(name):
            def tracker(event):
                order.append(name)
                return event

            return tracker

        pipeline = ProcessorPipeline(
            [
                make_tracker("first"),
                make_tracker("second"),
                make_tracker("third"),
            ]
        )
        pipeline.process({"message": "test"})
        assert order == ["first", "second", "third"]
