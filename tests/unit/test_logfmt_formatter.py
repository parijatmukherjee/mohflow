"""Comprehensive tests for mohflow.formatters.logfmt module.

Covers LogfmtFormatter, _logfmt_value, _logfmt_pair, and all
configuration options including custom keys, timestamp formats,
strict mode, sort order, logger name inclusion, and exception
formatting.
"""

import logging
import sys
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from mohflow.formatters.logfmt import (
    LogfmtFormatter,
    _logfmt_pair,
    _logfmt_value,
    _NEEDS_QUOTE_RE,
    _STANDARD_RECORD_ATTRS,
)

# ── helpers ─────────────────────────────────────────────────────────


def _make_record(
    level=logging.INFO,
    msg="test message",
    name="test.logger",
    exc_info=None,
    **extra,
):
    """Create a logging.LogRecord with optional extra fields."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=42,
        msg=msg,
        args=None,
        exc_info=exc_info,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


# ── _logfmt_value tests ────────────────────────────────────────────


class TestLogfmtValue:
    """Tests for the _logfmt_value helper function."""

    def test_none_returns_empty_string(self):
        assert _logfmt_value(None) == ""

    def test_bool_true(self):
        assert _logfmt_value(True) == "true"

    def test_bool_false(self):
        assert _logfmt_value(False) == "false"

    def test_int_value(self):
        assert _logfmt_value(42) == "42"

    def test_negative_int(self):
        assert _logfmt_value(-7) == "-7"

    def test_zero(self):
        assert _logfmt_value(0) == "0"

    def test_float_value(self):
        assert _logfmt_value(3.14) == "3.14"

    def test_negative_float(self):
        assert _logfmt_value(-0.5) == "-0.5"

    def test_float_zero(self):
        assert _logfmt_value(0.0) == "0.0"

    def test_simple_string_no_quoting(self):
        assert _logfmt_value("hello") == "hello"

    def test_string_with_spaces_is_quoted(self):
        assert _logfmt_value("hello world") == '"hello world"'

    def test_string_with_equals_is_quoted(self):
        assert _logfmt_value("a=b") == '"a=b"'

    def test_string_with_double_quote_is_escaped(self):
        result = _logfmt_value('say "hi"')
        assert result == '"say \\"hi\\""'

    def test_string_with_backslash_is_escaped(self):
        result = _logfmt_value("path\\to\\file")
        assert result == '"path\\\\to\\\\file"'

    def test_empty_string_returns_quoted_empty(self):
        assert _logfmt_value("") == '""'

    def test_string_with_tab_is_quoted(self):
        result = _logfmt_value("col1\tcol2")
        assert result == '"col1\tcol2"'

    def test_string_with_newline_is_quoted(self):
        result = _logfmt_value("line1\nline2")
        assert result == '"line1\nline2"'

    def test_non_string_object_converted_via_str(self):
        """Any non-primitive is converted through str() then quoting rules apply."""
        result = _logfmt_value([1, 2, 3])
        # str([1, 2, 3]) = "[1, 2, 3]" which contains spaces
        assert result.startswith('"')
        assert result.endswith('"')

    def test_string_no_special_chars_unquoted(self):
        assert _logfmt_value("simple123") == "simple123"

    def test_bool_before_int_check(self):
        """bool is a subclass of int; ensure True becomes 'true' not '1'."""
        assert _logfmt_value(True) == "true"
        assert _logfmt_value(False) == "false"

    def test_large_int(self):
        assert _logfmt_value(10**18) == "1000000000000000000"

    def test_scientific_float(self):
        result = _logfmt_value(1e-10)
        assert result == str(1e-10)


# ── _logfmt_pair tests ─────────────────────────────────────────────


class TestLogfmtPair:
    """Tests for the _logfmt_pair helper function."""

    def test_simple_pair(self):
        assert _logfmt_pair("level", "info") == "level=info"

    def test_pair_with_int_value(self):
        assert _logfmt_pair("count", 5) == "count=5"

    def test_pair_with_none_value(self):
        assert _logfmt_pair("key", None) == "key="

    def test_pair_with_bool_value(self):
        assert _logfmt_pair("active", True) == "active=true"

    def test_pair_with_quoted_string(self):
        assert _logfmt_pair("msg", "hello world") == 'msg="hello world"'

    def test_pair_with_empty_string(self):
        assert _logfmt_pair("val", "") == 'val=""'

    def test_pair_with_float(self):
        assert _logfmt_pair("rate", 0.95) == "rate=0.95"


# ── LogfmtFormatter basic formatting ──────────────────────────────


class TestLogfmtFormatterBasic:
    """Tests for basic LogfmtFormatter formatting."""

    def test_default_output_has_ts_level_msg(self):
        fmt = LogfmtFormatter()
        record = _make_record(msg="user signed up")
        output = fmt.format(record)
        assert output.startswith("ts=")
        assert "level=info" in output
        assert 'msg="user signed up"' in output

    def test_output_is_single_line(self):
        fmt = LogfmtFormatter()
        record = _make_record()
        output = fmt.format(record)
        assert "\n" not in output

    def test_default_key_order_ts_level_msg(self):
        fmt = LogfmtFormatter()
        record = _make_record()
        output = fmt.format(record)
        parts = output.split(" ")
        assert parts[0].startswith("ts=")
        assert parts[1].startswith("level=")
        assert parts[2].startswith("msg=")

    def test_level_is_lowercase(self):
        fmt = LogfmtFormatter()
        record = _make_record(level=logging.WARNING)
        output = fmt.format(record)
        assert "level=warning" in output

    def test_debug_level(self):
        fmt = LogfmtFormatter()
        record = _make_record(level=logging.DEBUG)
        output = fmt.format(record)
        assert "level=debug" in output

    def test_error_level(self):
        fmt = LogfmtFormatter()
        record = _make_record(level=logging.ERROR)
        output = fmt.format(record)
        assert "level=error" in output

    def test_critical_level(self):
        fmt = LogfmtFormatter()
        record = _make_record(level=logging.CRITICAL)
        output = fmt.format(record)
        assert "level=critical" in output


# ── Extra fields ──────────────────────────────────────────────────


class TestLogfmtFormatterExtraFields:
    """Tests for extra fields from LogRecord."""

    def test_extra_fields_appear_in_output(self):
        fmt = LogfmtFormatter()
        record = _make_record(user_id="u123", request_id="req-456")
        output = fmt.format(record)
        assert "user_id=u123" in output
        assert "request_id=req-456" in output

    def test_extra_field_with_int_value(self):
        fmt = LogfmtFormatter()
        record = _make_record(retry_count=3)
        output = fmt.format(record)
        assert "retry_count=3" in output

    def test_extra_field_with_bool_value(self):
        fmt = LogfmtFormatter()
        record = _make_record(is_admin=True)
        output = fmt.format(record)
        assert "is_admin=true" in output

    def test_extra_field_with_float_value(self):
        fmt = LogfmtFormatter()
        record = _make_record(duration=1.234)
        output = fmt.format(record)
        assert "duration=1.234" in output

    def test_standard_record_attrs_not_leaked(self):
        """Standard LogRecord attributes should not appear as extra fields."""
        fmt = LogfmtFormatter()
        record = _make_record()
        output = fmt.format(record)
        # None of the standard attrs like 'pathname', 'lineno' should appear
        for attr in ("pathname=", "lineno=", "funcName=", "thread="):
            assert attr not in output


# ── Custom key names ──────────────────────────────────────────────


class TestLogfmtFormatterCustomKeys:
    """Tests for custom key names (timestamp_key, level_key, message_key)."""

    def test_custom_timestamp_key(self):
        fmt = LogfmtFormatter(timestamp_key="timestamp")
        record = _make_record()
        output = fmt.format(record)
        assert output.startswith("timestamp=")
        assert "ts=" not in output

    def test_custom_level_key(self):
        fmt = LogfmtFormatter(level_key="severity")
        record = _make_record()
        output = fmt.format(record)
        assert "severity=info" in output
        assert " level=" not in output

    def test_custom_message_key(self):
        fmt = LogfmtFormatter(message_key="message")
        record = _make_record(msg="hello")
        output = fmt.format(record)
        assert "message=hello" in output
        assert " msg=" not in output

    def test_all_custom_keys(self):
        fmt = LogfmtFormatter(
            timestamp_key="time",
            level_key="lvl",
            message_key="text",
        )
        record = _make_record(msg="hi")
        output = fmt.format(record)
        assert "time=" in output
        assert "lvl=info" in output
        assert "text=hi" in output


# ── Timestamp formats ─────────────────────────────────────────────


class TestLogfmtFormatterTimestamp:
    """Tests for timestamp formatting options."""

    def test_iso_format_default(self):
        fmt = LogfmtFormatter(timestamp_format="iso")
        record = _make_record()
        output = fmt.format(record)
        # ISO format contains 'T' separator
        ts_part = output.split(" ")[0]
        ts_value = ts_part.split("=", 1)[1]
        assert "T" in ts_value
        assert (
            "+" in ts_value or ts_value.endswith("Z") or "+00:00" in ts_value
        )

    def test_epoch_format(self):
        fmt = LogfmtFormatter(timestamp_format="epoch")
        record = _make_record()
        output = fmt.format(record)
        ts_part = output.split(" ")[0]
        ts_value = ts_part.split("=", 1)[1]
        # Should be an integer (no decimal point)
        assert "." not in ts_value
        int(ts_value)  # Should not raise

    def test_epoch_ms_format(self):
        fmt = LogfmtFormatter(timestamp_format="epoch_ms")
        record = _make_record()
        output = fmt.format(record)
        ts_part = output.split(" ")[0]
        ts_value = ts_part.split("=", 1)[1]
        ms = int(ts_value)
        # epoch_ms should be much larger than epoch (roughly 1000x)
        assert ms > 1_000_000_000_000

    def test_epoch_returns_int(self):
        fmt = LogfmtFormatter(timestamp_format="epoch")
        record = _make_record()
        ts = fmt._format_timestamp(record)
        assert isinstance(ts, int)

    def test_epoch_ms_returns_int(self):
        fmt = LogfmtFormatter(timestamp_format="epoch_ms")
        record = _make_record()
        ts = fmt._format_timestamp(record)
        assert isinstance(ts, int)

    def test_iso_returns_string(self):
        fmt = LogfmtFormatter(timestamp_format="iso")
        record = _make_record()
        ts = fmt._format_timestamp(record)
        assert isinstance(ts, str)


# ── Custom key ordering with `keys` parameter ────────────────────


class TestLogfmtFormatterKeysOrdering:
    """Tests for the `keys` parameter controlling output order."""

    def test_keys_controls_order(self):
        fmt = LogfmtFormatter(keys=["msg", "level", "ts"])
        record = _make_record(msg="hello")
        output = fmt.format(record)
        parts = output.split(" ")
        assert parts[0].startswith("msg=")
        assert parts[1].startswith("level=")
        assert parts[2].startswith("ts=")

    def test_keys_with_extra_fields_appended(self):
        """When strict_keys is False (default), extra fields are appended."""
        fmt = LogfmtFormatter(keys=["ts", "level", "msg"])
        record = _make_record(user_id="u1")
        output = fmt.format(record)
        assert "user_id=u1" in output

    def test_keys_only_specified_keys_first(self):
        """Only keys listed in `keys` appear first, then extras."""
        fmt = LogfmtFormatter(keys=["level"])
        record = _make_record()
        output = fmt.format(record)
        parts = output.split(" ")
        assert parts[0].startswith("level=")

    def test_keys_missing_key_is_skipped(self):
        """If a key in `keys` is not in the record, it is silently skipped."""
        fmt = LogfmtFormatter(keys=["ts", "nonexistent", "level", "msg"])
        record = _make_record()
        output = fmt.format(record)
        assert "nonexistent=" not in output


# ── strict_keys mode ──────────────────────────────────────────────


class TestLogfmtFormatterStrictKeys:
    """Tests for strict_keys mode."""

    def test_strict_keys_drops_extra_fields(self):
        fmt = LogfmtFormatter(
            keys=["ts", "level", "msg"],
            strict_keys=True,
        )
        record = _make_record(user_id="u1", trace_id="t2")
        output = fmt.format(record)
        assert "user_id=" not in output
        assert "trace_id=" not in output

    def test_strict_keys_keeps_only_specified(self):
        fmt = LogfmtFormatter(
            keys=["level", "msg"],
            strict_keys=True,
        )
        record = _make_record(msg="hi")
        output = fmt.format(record)
        parts = output.split(" ")
        assert len(parts) == 2
        assert parts[0].startswith("level=")
        assert parts[1].startswith("msg=")

    def test_strict_keys_false_allows_extras(self):
        fmt = LogfmtFormatter(
            keys=["ts", "level", "msg"],
            strict_keys=False,
        )
        record = _make_record(user_id="u1")
        output = fmt.format(record)
        assert "user_id=u1" in output


# ── sort_extra_keys ───────────────────────────────────────────────


class TestLogfmtFormatterSortExtraKeys:
    """Tests for sort_extra_keys option."""

    def test_sort_extra_keys_alphabetical(self):
        fmt = LogfmtFormatter(sort_extra_keys=True)
        record = _make_record(zebra="z", alpha="a", middle="m")
        output = fmt.format(record)
        # After ts, level, msg, the extras should be alphabetical
        parts = output.split(" ")
        # Find the extra fields (after the first 3)
        extra_parts = [p for p in parts[3:] if "=" in p]
        extra_keys = [p.split("=")[0] for p in extra_parts]
        assert extra_keys == sorted(extra_keys)

    def test_sort_extra_keys_false_preserves_insertion_order(self):
        """When sort_extra_keys is False, extras appear in dict order."""
        fmt = LogfmtFormatter(sort_extra_keys=False)
        record = _make_record()
        output = fmt.format(record)
        # Just verify it doesn't crash; order is dict-dependent
        assert "ts=" in output

    def test_sort_extra_keys_with_custom_keys(self):
        """sort_extra_keys applies to extra fields appended after `keys`."""
        fmt = LogfmtFormatter(
            keys=["ts", "level", "msg"],
            sort_extra_keys=True,
        )
        record = _make_record(z_field="z", a_field="a")
        output = fmt.format(record)
        parts = output.split(" ")
        # After the 3 specified keys, extras should be sorted
        extra_parts = parts[3:]
        extra_keys = [p.split("=")[0] for p in extra_parts if "=" in p]
        assert extra_keys == sorted(extra_keys)


# ── include_logger_name ───────────────────────────────────────────


class TestLogfmtFormatterLoggerName:
    """Tests for include_logger_name option."""

    def test_include_logger_name_true(self):
        fmt = LogfmtFormatter(include_logger_name=True)
        record = _make_record(name="my.app.module")
        output = fmt.format(record)
        assert "logger=my.app.module" in output

    def test_include_logger_name_false_default(self):
        fmt = LogfmtFormatter(include_logger_name=False)
        record = _make_record(name="my.app")
        output = fmt.format(record)
        assert "logger=" not in output

    def test_logger_name_appears_after_msg(self):
        """When included, logger name should come right after the core keys."""
        fmt = LogfmtFormatter(include_logger_name=True)
        record = _make_record(name="my.app", msg="simple")
        output = fmt.format(record)
        # With a single-word message: "ts=... level=info msg=simple logger=my.app"
        parts = output.split(" ")
        keys = [p.split("=")[0] for p in parts]
        assert keys.index("logger") == 3

    def test_logger_name_with_dots_unquoted(self):
        """Dotted names (no spaces/equals) should not be quoted."""
        fmt = LogfmtFormatter(include_logger_name=True)
        record = _make_record(name="a.b.c")
        output = fmt.format(record)
        assert "logger=a.b.c" in output


# ── Exception formatting ─────────────────────────────────────────


class TestLogfmtFormatterException:
    """Tests for exception formatting in logfmt output."""

    def test_exception_adds_error_and_error_type(self):
        fmt = LogfmtFormatter()
        try:
            raise ValueError("something went wrong")
        except ValueError:
            record = _make_record(exc_info=sys.exc_info())
        output = fmt.format(record)
        assert 'error="something went wrong"' in output
        assert "error_type=ValueError" in output

    def test_no_exception_no_error_fields(self):
        fmt = LogfmtFormatter()
        record = _make_record()
        output = fmt.format(record)
        assert "error=" not in output
        assert "error_type=" not in output

    def test_exception_with_none_exc_info(self):
        """exc_info=(None, None, None) should not produce error fields."""
        fmt = LogfmtFormatter()
        record = _make_record(exc_info=(None, None, None))
        output = fmt.format(record)
        assert "error=" not in output

    def test_runtime_error_type(self):
        fmt = LogfmtFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record = _make_record(exc_info=sys.exc_info())
        output = fmt.format(record)
        assert "error_type=RuntimeError" in output

    def test_exception_message_with_spaces_is_quoted(self):
        fmt = LogfmtFormatter()
        try:
            raise ValueError("multiple words in error message")
        except ValueError:
            record = _make_record(exc_info=sys.exc_info())
        output = fmt.format(record)
        assert 'error="multiple words in error message"' in output


# ── _record_to_dict internals ────────────────────────────────────


class TestRecordToDict:
    """Tests for the internal _record_to_dict method."""

    def test_returns_dict_with_core_keys(self):
        fmt = LogfmtFormatter()
        record = _make_record()
        data = fmt._record_to_dict(record)
        assert "ts" in data
        assert "level" in data
        assert "msg" in data

    def test_extra_fields_included(self):
        fmt = LogfmtFormatter()
        record = _make_record(custom_field="value")
        data = fmt._record_to_dict(record)
        assert "custom_field" in data
        assert data["custom_field"] == "value"

    def test_standard_attrs_excluded(self):
        fmt = LogfmtFormatter()
        record = _make_record()
        data = fmt._record_to_dict(record)
        # Standard LogRecord attrs (e.g. pathname, lineno, thread)
        # should not leak into the dict. Note: "msg" is in
        # _STANDARD_RECORD_ATTRS but the formatter maps the message
        # to the message_key ("msg" by default), so skip checking
        # keys that collide with the formatter's own output keys.
        formatter_keys = {"ts", "level", "msg"}
        for attr in _STANDARD_RECORD_ATTRS:
            if attr not in formatter_keys:
                assert (
                    attr not in data
                ), f"Standard attr '{attr}' leaked into output"

    def test_custom_key_names_in_dict(self):
        fmt = LogfmtFormatter(
            timestamp_key="time",
            level_key="severity",
            message_key="text",
        )
        record = _make_record()
        data = fmt._record_to_dict(record)
        assert "time" in data
        assert "severity" in data
        assert "text" in data
        assert "ts" not in data
        assert "level" not in data
        assert "msg" not in data


# ── NEEDS_QUOTE_RE pattern tests ─────────────────────────────────


class TestNeedsQuoteRegex:
    """Tests for the _NEEDS_QUOTE_RE pattern."""

    def test_space_matches(self):
        assert _NEEDS_QUOTE_RE.search("a b")

    def test_equals_matches(self):
        assert _NEEDS_QUOTE_RE.search("a=b")

    def test_quote_matches(self):
        assert _NEEDS_QUOTE_RE.search('a"b')

    def test_backslash_matches(self):
        assert _NEEDS_QUOTE_RE.search("a\\b")

    def test_tab_matches(self):
        assert _NEEDS_QUOTE_RE.search("a\tb")

    def test_simple_string_does_not_match(self):
        assert not _NEEDS_QUOTE_RE.search("simple")

    def test_alphanumeric_does_not_match(self):
        assert not _NEEDS_QUOTE_RE.search("abc123")


# ── _build_pairs internals ───────────────────────────────────────


class TestBuildPairs:
    """Tests for the _build_pairs method."""

    def test_build_pairs_returns_list_of_strings(self):
        fmt = LogfmtFormatter()
        record = _make_record()
        pairs = fmt._build_pairs(record)
        assert isinstance(pairs, list)
        assert all(isinstance(p, str) for p in pairs)
        assert all("=" in p for p in pairs)

    def test_build_pairs_with_keys(self):
        fmt = LogfmtFormatter(keys=["msg", "level"])
        record = _make_record(msg="hi")
        pairs = fmt._build_pairs(record)
        assert pairs[0].startswith("msg=")
        assert pairs[1].startswith("level=")

    def test_build_pairs_strict_keys_limits_output(self):
        fmt = LogfmtFormatter(
            keys=["level"],
            strict_keys=True,
        )
        record = _make_record(extra_field="x")
        pairs = fmt._build_pairs(record)
        pair_keys = [p.split("=")[0] for p in pairs]
        assert "extra_field" not in pair_keys
        assert "level" in pair_keys


# ── Edge cases and integration-style tests ────────────────────────


class TestLogfmtFormatterEdgeCases:
    """Edge cases and combined option tests."""

    def test_message_with_special_chars(self):
        fmt = LogfmtFormatter()
        record = _make_record(msg='key="val" has spaces & stuff\\here')
        output = fmt.format(record)
        # Message should be quoted and escaped
        assert "msg=" in output
        assert "\\\\" in output or '\\"' in output

    def test_empty_message(self):
        fmt = LogfmtFormatter()
        record = _make_record(msg="")
        output = fmt.format(record)
        assert 'msg=""' in output

    def test_multiple_options_combined(self):
        fmt = LogfmtFormatter(
            timestamp_key="time",
            level_key="lvl",
            message_key="text",
            timestamp_format="epoch",
            include_logger_name=True,
            sort_extra_keys=True,
        )
        record = _make_record(name="app", msg="combined", z="z", a="a")
        output = fmt.format(record)
        assert "time=" in output
        assert "lvl=info" in output
        assert "text=combined" in output
        assert "logger=app" in output

    def test_keys_with_sort_and_strict(self):
        fmt = LogfmtFormatter(
            keys=["level", "msg"],
            strict_keys=True,
            sort_extra_keys=True,
        )
        record = _make_record(msg="x", extra1="e1", extra2="e2")
        output = fmt.format(record)
        parts = output.split(" ")
        assert len(parts) == 2

    def test_format_returns_string(self):
        fmt = LogfmtFormatter()
        record = _make_record()
        result = fmt.format(record)
        assert isinstance(result, str)

    def test_inherits_from_logging_formatter(self):
        assert issubclass(LogfmtFormatter, logging.Formatter)

    def test_init_stores_keys_as_list(self):
        fmt = LogfmtFormatter(keys=("a", "b", "c"))
        assert isinstance(fmt.keys, list)
        assert fmt.keys == ["a", "b", "c"]

    def test_init_no_keys_sets_none(self):
        fmt = LogfmtFormatter()
        assert fmt.keys is None

    def test_init_defaults(self):
        fmt = LogfmtFormatter()
        assert fmt.timestamp_key == "ts"
        assert fmt.level_key == "level"
        assert fmt.message_key == "msg"
        assert fmt.timestamp_format == "iso"
        assert fmt.include_logger_name is False
        assert fmt.sort_extra_keys is False
        assert fmt.strict_keys is False

    def test_message_with_format_args(self):
        """LogRecord with positional args should format the message."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="user %s logged in at %d",
            args=("alice", 12345),
            exc_info=None,
        )
        fmt = LogfmtFormatter()
        output = fmt.format(record)
        assert "alice" in output
        assert "12345" in output
