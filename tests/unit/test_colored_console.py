"""Tests for F4: Colored Console Renderer."""

import logging
import os
import pytest
from mohflow.formatters.colored_console import (
    ColoredConsoleFormatter,
    _is_tty,
    _COLORS,
    _LEVEL_ICONS,
    _extract_extra_keys,
)


@pytest.fixture
def formatter():
    return ColoredConsoleFormatter(colorize=False)


@pytest.fixture
def colored_formatter():
    return ColoredConsoleFormatter(colorize=True)


def _make_record(
    level=logging.INFO,
    msg="test message",
    name="test",
    **extra,
):
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return record


class TestColoredConsoleFormatter:
    """Test the colored console formatter."""

    def test_basic_format(self, formatter):
        record = _make_record()
        output = formatter.format(record)
        assert "test message" in output
        assert "INF" in output

    def test_debug_level_icon(self, formatter):
        record = _make_record(level=logging.DEBUG)
        output = formatter.format(record)
        assert "DBG" in output

    def test_warning_level_icon(self, formatter):
        record = _make_record(level=logging.WARNING)
        output = formatter.format(record)
        assert "WRN" in output

    def test_error_level_icon(self, formatter):
        record = _make_record(level=logging.ERROR)
        output = formatter.format(record)
        assert "ERR" in output

    def test_critical_level_icon(self, formatter):
        record = _make_record(level=logging.CRITICAL)
        output = formatter.format(record)
        assert "CRT" in output

    def test_extra_fields_included(self, formatter):
        record = _make_record(user_id="u123", plan="pro")
        output = formatter.format(record)
        assert "user_id=" in output
        assert "u123" in output
        assert "plan=" in output
        assert "pro" in output

    def test_timestamp_shown(self, formatter):
        record = _make_record()
        output = formatter.format(record)
        # Should have HH:MM:SS format
        assert ":" in output

    def test_no_timestamp(self):
        fmt = ColoredConsoleFormatter(colorize=False, show_timestamp=False)
        record = _make_record()
        output = fmt.format(record)
        # Message should still be present
        assert "test message" in output

    def test_no_level(self):
        fmt = ColoredConsoleFormatter(colorize=False, show_level=False)
        record = _make_record()
        output = fmt.format(record)
        assert "INF" not in output
        assert "test message" in output

    def test_show_logger_name(self):
        fmt = ColoredConsoleFormatter(colorize=False, show_logger_name=True)
        record = _make_record(name="myapp.auth")
        output = fmt.format(record)
        assert "myapp.auth" in output

    def test_colored_output_has_ansi_codes(self, colored_formatter):
        record = _make_record()
        output = colored_formatter.format(record)
        # Should contain ANSI escape sequences
        assert "\033[" in output

    def test_no_color_output_no_ansi(self, formatter):
        record = _make_record()
        output = formatter.format(record)
        assert "\033[" not in output

    def test_exception_info_formatted(self, formatter):
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = _make_record()
        record.exc_info = exc_info
        output = formatter.format(record)
        assert "ValueError" in output
        assert "test error" in output


class TestIsTTY:
    """Test TTY detection."""

    def test_no_color_env(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert not _is_tty()

    def test_force_color_env(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert _is_tty()


class TestExtractExtraKeys:
    """Test extra key extraction."""

    def test_excludes_standard_keys(self):
        record = _make_record()
        keys = _extract_extra_keys(record)
        assert "msg" not in keys
        assert "levelname" not in keys

    def test_includes_custom_keys(self):
        record = _make_record(custom_field="value")
        keys = _extract_extra_keys(record)
        assert "custom_field" in keys

    def test_excludes_private_keys(self):
        record = _make_record()
        record._private = "hidden"
        keys = _extract_extra_keys(record)
        assert "_private" not in keys


class TestColoredFormatterWithMohflow:
    """Integration test with MohflowLogger."""

    def test_logger_with_colored_formatter(self, caplog):
        from mohflow import MohflowLogger

        logger = MohflowLogger(
            service_name="colored-test",
            formatter_type="colored",
            enable_sensitive_data_filter=False,
            enable_context_enrichment=False,
        )
        with caplog.at_level(logging.INFO):
            logger.info("colored log", user_id="u123")
        records = [r for r in caplog.records if "colored log" in r.message]
        assert len(records) == 1
