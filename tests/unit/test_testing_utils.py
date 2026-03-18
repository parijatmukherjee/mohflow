"""Tests for F11: Testing Utilities — capture_logs, assert_logged, LogCapture."""

import logging
import pytest
from mohflow.testing import (
    capture_logs,
    assert_logged,
    LogCapture,
    CapturedRecord,
)


class TestLogCapture:
    """Test the LogCapture data structure."""

    def test_empty_capture(self):
        cap = LogCapture()
        assert len(cap) == 0
        assert not cap
        assert cap.messages == []

    def test_append(self):
        cap = LogCapture()
        rec = CapturedRecord(level="INFO", message="hello", logger_name="test")
        cap.append(rec)
        assert len(cap) == 1
        assert cap
        assert cap.messages == ["hello"]

    def test_filter_by_level(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="info msg",
                logger_name="t",
            )
        )
        cap.append(
            CapturedRecord(
                level="ERROR",
                message="error msg",
                logger_name="t",
            )
        )
        results = cap.filter(level="ERROR")
        assert len(results) == 1
        assert results[0].message == "error msg"

    def test_filter_by_logger_name(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(level="INFO", message="a", logger_name="app")
        )
        cap.append(
            CapturedRecord(level="INFO", message="b", logger_name="lib")
        )
        results = cap.filter(logger_name="app")
        assert len(results) == 1

    def test_filter_by_message_contains(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="user signed up",
                logger_name="t",
            )
        )
        cap.append(
            CapturedRecord(
                level="INFO",
                message="order placed",
                logger_name="t",
            )
        )
        results = cap.filter(message_contains="signed")
        assert len(results) == 1

    def test_filter_combined(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="user login",
                logger_name="auth",
            )
        )
        cap.append(
            CapturedRecord(
                level="ERROR",
                message="user login failed",
                logger_name="auth",
            )
        )
        results = cap.filter(level="ERROR", message_contains="login")
        assert len(results) == 1
        assert "failed" in results[0].message

    def test_clear(self):
        cap = LogCapture()
        cap.append(CapturedRecord(level="INFO", message="x", logger_name="t"))
        cap.clear()
        assert len(cap) == 0

    def test_repr(self):
        cap = LogCapture()
        r = repr(cap)
        assert "0 records" in r

    def test_repr_with_records(self):
        cap = LogCapture()
        for i in range(5):
            cap.append(
                CapturedRecord(
                    level="INFO",
                    message=f"msg{i}",
                    logger_name="t",
                )
            )
        r = repr(cap)
        assert "5 records" in r
        assert "..." in r


class TestCapturedRecord:
    """Test CapturedRecord creation."""

    def test_from_log_record(self):
        record = logging.LogRecord(
            name="myapp",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        record.custom_field = "custom_value"
        captured = CapturedRecord.from_log_record(record)
        assert captured.level == "INFO"
        assert captured.message == "hello world"
        assert captured.logger_name == "myapp"
        assert captured.extra["custom_field"] == "custom_value"

    def test_extra_excludes_standard_keys(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=None,
            exc_info=None,
        )
        captured = CapturedRecord.from_log_record(record)
        # Standard keys should not be in extra
        assert "msg" not in captured.extra
        assert "levelname" not in captured.extra
        assert "name" not in captured.extra


class TestCaptureLogs:
    """Test the capture_logs context manager."""

    def test_captures_root_logger(self):
        with capture_logs() as cap:
            logging.getLogger().info("root msg")
        assert len(cap) >= 1
        msgs = [r.message for r in cap.records]
        assert any("root msg" in m for m in msgs)

    def test_captures_named_logger(self):
        with capture_logs("myapp.test") as cap:
            logging.getLogger("myapp.test").warning("warn!")
        assert len(cap) == 1
        assert cap.records[0].level == "WARNING"

    def test_captures_all_levels(self):
        with capture_logs() as cap:
            logger = logging.getLogger("all_levels_test")
            logger.debug("d")
            logger.info("i")
            logger.warning("w")
            logger.error("e")
        levels = {r.level for r in cap.records}
        assert "DEBUG" in levels
        assert "INFO" in levels
        assert "WARNING" in levels
        assert "ERROR" in levels

    def test_restores_logger_state(self):
        logger = logging.getLogger("restore_test")
        original_handlers = len(logger.handlers)
        with capture_logs("restore_test"):
            pass
        assert len(logger.handlers) == original_handlers

    def test_captures_extra_fields(self):
        with capture_logs("extra_test") as cap:
            logger = logging.getLogger("extra_test")
            logger.info(
                "with extras",
                extra={"user_id": "u123"},
            )
        assert cap.records[0].extra.get("user_id") == "u123"


class TestAssertLogged:
    """Test the assert_logged helper."""

    def test_passes_on_match(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="user signed up",
                logger_name="auth",
            )
        )
        # Should not raise
        assert_logged(
            cap,
            level="INFO",
            message_contains="signed up",
        )

    def test_fails_on_no_match(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="hello",
                logger_name="t",
            )
        )
        with pytest.raises(AssertionError, match="No matching"):
            assert_logged(cap, level="ERROR", message_contains="bye")

    def test_message_equals(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="exact match",
                logger_name="t",
            )
        )
        assert_logged(cap, message_equals="exact match")

    def test_message_equals_fails(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="not this",
                logger_name="t",
            )
        )
        with pytest.raises(AssertionError):
            assert_logged(cap, message_equals="exact match")

    def test_count_exact(self):
        cap = LogCapture()
        for _ in range(3):
            cap.append(
                CapturedRecord(
                    level="INFO",
                    message="repeated",
                    logger_name="t",
                )
            )
        assert_logged(
            cap,
            message_contains="repeated",
            count=3,
        )

    def test_count_mismatch(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="once",
                logger_name="t",
            )
        )
        with pytest.raises(AssertionError, match="Expected 2"):
            assert_logged(cap, message_contains="once", count=2)

    def test_extra_contains(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="msg",
                logger_name="t",
                extra={"user_id": "u123", "plan": "pro"},
            )
        )
        assert_logged(
            cap,
            extra_contains={"user_id": "u123"},
        )

    def test_extra_contains_mismatch(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="msg",
                logger_name="t",
                extra={"user_id": "u999"},
            )
        )
        with pytest.raises(AssertionError):
            assert_logged(
                cap,
                extra_contains={"user_id": "u123"},
            )

    def test_logger_name_filter(self):
        cap = LogCapture()
        cap.append(
            CapturedRecord(
                level="INFO",
                message="msg",
                logger_name="auth",
            )
        )
        assert_logged(cap, logger_name="auth")
        with pytest.raises(AssertionError):
            assert_logged(cap, logger_name="payments")
