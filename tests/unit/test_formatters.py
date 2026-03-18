"""Tests for formatters: OrjsonFormatter, FastJSONFormatter,
StructuredFormatter, ProductionFormatter, DevelopmentFormatter."""

import json
import logging
import pytest
from mohflow.formatters.orjson_formatter import (
    OrjsonFormatter,
    FastJSONFormatter,
    HAS_ORJSON,
)
from mohflow.formatters.structured_formatter import (
    StructuredFormatter,
    ProductionFormatter,
    DevelopmentFormatter,
)


def _make_record(
    level=logging.INFO,
    msg="test message",
    name="test.logger",
    **extra,
):
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=42,
        msg=msg,
        args=None,
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


class TestOrjsonFormatter:
    """Test the base OrjsonFormatter."""

    def test_basic_format(self):
        fmt = OrjsonFormatter()
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "test message"
        assert data["logger"] == "test.logger"

    def test_timestamp_iso(self):
        fmt = OrjsonFormatter(timestamp_format="iso")
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "T" in data["timestamp"]

    def test_timestamp_epoch(self):
        fmt = OrjsonFormatter(timestamp_format="epoch")
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert isinstance(data["timestamp"], int)

    def test_timestamp_epoch_ms(self):
        fmt = OrjsonFormatter(timestamp_format="epoch_ms")
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert isinstance(data["timestamp"], int)
        assert data["timestamp"] > 1000000000000

    def test_static_fields(self):
        fmt = OrjsonFormatter(static_fields={"env": "test", "ver": "1.0"})
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert data["env"] == "test"
        assert data["ver"] == "1.0"

    def test_exclude_fields(self):
        fmt = OrjsonFormatter(exclude_fields=["module", "function"])
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "module" not in data
        assert "function" not in data

    def test_rename_fields(self):
        fmt = OrjsonFormatter(rename_fields={"level": "severity"})
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "severity" in data
        assert "level" not in data

    def test_sort_keys(self):
        fmt = OrjsonFormatter(sort_keys=True)
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        keys = list(data.keys())
        assert keys == sorted(keys)

    def test_extra_fields_included(self):
        fmt = OrjsonFormatter()
        record = _make_record(user_id="u123", action="login")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["user_id"] == "u123"
        assert data["action"] == "login"

    def test_exception_info(self):
        fmt = OrjsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            record = _make_record()
            record.exc_info = sys.exc_info()
        output = fmt.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_stack_info(self):
        fmt = OrjsonFormatter()
        record = _make_record()
        record.stack_info = "Stack trace here"
        output = fmt.format(record)
        data = json.loads(output)
        assert "stack_info" in data

    def test_indent_option(self):
        fmt = OrjsonFormatter(indent=2)
        record = _make_record()
        output = fmt.format(record)
        # Indented output should have newlines
        assert "\n" in output or "  " in output

    def test_json_default_datetime(self):
        from datetime import datetime, timezone

        fmt = OrjsonFormatter()
        result = fmt._json_default(datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert "2024" in result

    def test_json_default_object(self):
        fmt = OrjsonFormatter()

        class Obj:
            x = 1

        result = fmt._json_default(Obj())
        assert isinstance(result, dict)

    def test_json_default_fallback(self):
        fmt = OrjsonFormatter()
        result = fmt._json_default(set([1, 2, 3]))
        assert isinstance(result, str)


class TestFastJSONFormatter:
    """Test FastJSONFormatter presets."""

    def test_defaults(self):
        fmt = FastJSONFormatter()
        assert fmt.indent is None
        assert fmt.sort_keys is False
        assert fmt.timestamp_format == "epoch_ms"

    def test_excludes_verbose_fields(self):
        fmt = FastJSONFormatter()
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "module" not in data
        assert "function" not in data

    def test_format_output(self):
        fmt = FastJSONFormatter(static_fields={"service": "test"})
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert data["service"] == "test"
        assert isinstance(data["timestamp"], int)

    def test_overrides(self):
        fmt = FastJSONFormatter(indent=2, sort_keys=True)
        assert fmt.indent == 2
        assert fmt.sort_keys is True


class TestStructuredFormatterAdvanced:
    """Test StructuredFormatter from structured_formatter.py."""

    def test_basic_format(self):
        fmt = StructuredFormatter()
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "test message"

    def test_include_system_info(self):
        fmt = StructuredFormatter(include_system_info=True)
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "process_id" in data
        assert "thread_id" in data

    def test_exclude_system_info(self):
        fmt = StructuredFormatter(include_system_info=False)
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "process_id" not in data

    def test_include_source_info(self):
        fmt = StructuredFormatter(include_source_info=True)
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "module" in data
        assert "function" in data
        assert data["line"] == 42

    def test_exclude_source_info(self):
        fmt = StructuredFormatter(include_source_info=False)
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "pathname" not in data

    def test_context_fields(self):
        fmt = StructuredFormatter(include_context=True)
        record = _make_record(
            request_id="req-123",
            correlation_id="corr-456",
        )
        output = fmt.format(record)
        data = json.loads(output)
        assert data["request_id"] == "req-123"
        assert data["correlation_id"] == "corr-456"

    def test_exclude_context(self):
        fmt = StructuredFormatter(include_context=False)
        record = _make_record(request_id="req-123")
        output = fmt.format(record)
        data = json.loads(output)
        # request_id still appears as extra field
        assert "request_id" in data

    def test_custom_context_fields(self):
        fmt = StructuredFormatter(context_fields=["custom_id"])
        record = _make_record(custom_id="c123")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["custom_id"] == "c123"

    def test_field_processor(self):
        fmt = StructuredFormatter(
            field_processors={"email": lambda v: v.split("@")[0] + "@***"}
        )
        record = _make_record(email="user@example.com")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["email"] == "user@***"

    def test_field_processor_error_uses_original(self):
        fmt = StructuredFormatter(field_processors={"val": lambda v: 1 / 0})
        record = _make_record(val="original")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["val"] == "original"

    def test_add_field_processor(self):
        fmt = StructuredFormatter()
        fmt.add_field_processor("x", lambda v: v.upper())
        assert "x" in fmt.field_processors

    def test_remove_field_processor(self):
        fmt = StructuredFormatter(field_processors={"x": lambda v: v})
        fmt.remove_field_processor("x")
        assert "x" not in fmt.field_processors

    def test_remove_nonexistent_processor(self):
        fmt = StructuredFormatter()
        fmt.remove_field_processor("nonexistent")

    def test_exception_info_structured(self):
        fmt = StructuredFormatter()
        try:
            raise TypeError("bad type")
        except TypeError:
            import sys

            record = _make_record()
            record.exc_info = sys.exc_info()
        output = fmt.format(record)
        data = json.loads(output)
        assert data["exception"]["type"] == "TypeError"
        assert "bad type" in data["exception"]["message"]

    def test_reserved_fields_excluded(self):
        fmt = StructuredFormatter()
        reserved = fmt._get_reserved_fields()
        assert "msg" in reserved
        assert "args" in reserved
        assert "levelname" in reserved


class TestProductionFormatter:
    """Test ProductionFormatter presets."""

    def test_defaults(self):
        fmt = ProductionFormatter()
        assert fmt.include_source_info is False
        assert fmt.sort_keys is False
        assert fmt.indent is None
        assert fmt.timestamp_format == "epoch_ms"

    def test_format_compact(self):
        fmt = ProductionFormatter()
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "pathname" not in data
        assert isinstance(data["timestamp"], int)


class TestDevelopmentFormatter:
    """Test DevelopmentFormatter presets."""

    def test_defaults(self):
        fmt = DevelopmentFormatter()
        assert fmt.include_source_info is True
        assert fmt.include_system_info is True
        assert fmt.sort_keys is True
        assert fmt.indent == 2
        assert fmt.timestamp_format == "iso"

    def test_format_readable(self):
        fmt = DevelopmentFormatter()
        record = _make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert "module" in data
        assert "T" in data["timestamp"]
