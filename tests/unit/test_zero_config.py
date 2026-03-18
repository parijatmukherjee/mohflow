"""Tests for F1: Zero-Config Quickstart — `from mohflow import log`."""

import logging
import pytest


class TestLazyLogSingleton:
    """Test the lazy-initialized log singleton."""

    def test_import_log_does_not_crash(self):
        """Importing log should be side-effect-free."""
        from mohflow import log

        assert log is not None

    def test_log_repr_before_init(self):
        """repr should be safe before first use."""
        from mohflow import _LazyLog

        fresh = _LazyLog()
        # Save and clear the class-level instance
        old = _LazyLog._instance
        _LazyLog._instance = None
        try:
            r = repr(fresh)
            assert "not yet initialized" in r
        finally:
            _LazyLog._instance = old

    def test_log_info(self, caplog):
        """log.info should work with zero config."""
        from mohflow import log

        with caplog.at_level(logging.INFO):
            log.info("hello from zero-config")
        records = [
            r for r in caplog.records if "hello from zero-config" in r.message
        ]
        assert len(records) == 1
        assert records[0].levelname == "INFO"

    def test_log_warning(self, caplog):
        from mohflow import log

        with caplog.at_level(logging.WARNING):
            log.warning("warn msg")
        records = [r for r in caplog.records if "warn msg" in r.message]
        assert len(records) == 1

    def test_log_error(self, caplog):
        from mohflow import log

        with caplog.at_level(logging.ERROR):
            log.error("error msg", exc_info=False)
        records = [r for r in caplog.records if "error msg" in r.message]
        assert len(records) == 1

    def test_log_debug(self, caplog):
        """Debug is below default INFO level, so it should
        be filtered unless we set the logger level."""
        from mohflow import log

        # Force the underlying logger to DEBUG level
        log._get_logger().logger.setLevel(logging.DEBUG)
        try:
            with caplog.at_level(logging.DEBUG):
                log.debug("debug msg")
            records = [r for r in caplog.records if "debug msg" in r.message]
            assert len(records) == 1
        finally:
            log._get_logger().logger.setLevel(logging.INFO)

    def test_log_critical(self, caplog):
        from mohflow import log

        with caplog.at_level(logging.CRITICAL):
            log.critical("critical msg")
        records = [r for r in caplog.records if "critical msg" in r.message]
        assert len(records) == 1

    def test_log_with_kwargs(self, caplog):
        """Extra kwargs should be passed through."""
        from mohflow import log

        with caplog.at_level(logging.INFO):
            log.info("user signup", user_id="u123", plan="pro")
        records = [r for r in caplog.records if "user signup" in r.message]
        assert len(records) == 1
        assert records[0].user_id == "u123"
        assert records[0].plan == "pro"

    def test_log_is_singleton(self):
        """Multiple imports should return the same object."""
        from mohflow import log as log1
        from mohflow import log as log2

        assert log1 is log2

    def test_log_in_all(self):
        """log should be in __all__."""
        import mohflow

        assert "log" in mohflow.__all__

    def test_log_has_standard_methods(self):
        """Singleton should expose all standard log methods."""
        from mohflow import log

        for method in [
            "info",
            "warning",
            "error",
            "debug",
            "critical",
        ]:
            assert callable(getattr(log, method))
