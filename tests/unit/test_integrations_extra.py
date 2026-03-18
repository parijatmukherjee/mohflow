"""Extra integration tests to cover uncovered lines."""

import sys
import pytest
from unittest.mock import MagicMock, patch
from contextlib import contextmanager


def _noop_cm():
    """No-op context manager for request_context mock."""

    @contextmanager
    def _cm(*a, **kw):
        yield

    return _cm


class TestCeleryHandlerMethods:
    """Direct calls to Celery signal handlers."""

    def _make_integration(self):
        # Mock celery imports
        mock_celery = MagicMock()
        mock_celery.signals = MagicMock()
        sys.modules["celery"] = mock_celery
        sys.modules["celery.signals"] = mock_celery.signals
        sys.modules["celery.app"] = MagicMock()
        sys.modules["celery.app.task"] = MagicMock()

        with patch.dict(
            "mohflow.integrations.celery.__dict__",
            {"HAS_CELERY": True},
        ):
            from mohflow.integrations.celery import (
                MohFlowCeleryIntegration,
            )

            logger = MagicMock()
            logger.request_context = _noop_cm()
            return MohFlowCeleryIntegration(logger=logger)

    def test_task_prerun(self):
        integ = self._make_integration()
        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        integ._task_prerun_handler(
            sender=sender,
            task_id="t1",
            task=task,
            args=(1, 2),
            kwargs={"k": "v"},
        )
        integ.logger.info.assert_called()

    def test_task_postrun_success(self):
        integ = self._make_integration()
        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {"task_start_time": 0}
        integ._task_postrun_handler(
            sender=sender,
            task_id="t1",
            task=task,
            retval="ok",
            state="SUCCESS",
        )
        integ.logger.info.assert_called()

    def test_task_postrun_non_success(self):
        integ = self._make_integration()
        sender = MagicMock()
        sender.name = "my_task"
        task = MagicMock()
        task.mohflow_context = {}
        integ._task_postrun_handler(
            sender=sender,
            task_id="t1",
            task=task,
            state="FAILURE",
        )
        integ.logger.warning.assert_called()

    def test_task_failure(self):
        integ = self._make_integration()
        sender = MagicMock()
        sender.name = "my_task"
        integ._task_failure_handler(
            sender=sender,
            task_id="t1",
            exception=ValueError("boom"),
            einfo="traceback...",
        )
        integ.logger.error.assert_called()

    def test_task_retry(self):
        integ = self._make_integration()
        sender = MagicMock()
        sender.name = "my_task"
        integ._task_retry_handler(
            sender=sender,
            task_id="t1",
            reason="rate limit",
            einfo="trace",
        )
        integ.logger.warning.assert_called()

    def test_worker_ready(self):
        integ = self._make_integration()
        sender = MagicMock()
        sender.hostname = "worker-1"
        sender.pid = 1234
        integ._worker_ready_handler(sender=sender)
        integ.logger.info.assert_called()

    def test_worker_shutdown(self):
        integ = self._make_integration()
        sender = MagicMock()
        sender.hostname = "worker-1"
        sender.pid = 1234
        integ._worker_shutdown_handler(sender=sender)
        integ.logger.info.assert_called()

    def test_safe_serialize_non_serializable(self):
        integ = self._make_integration()
        result = integ._safe_serialize(object())
        assert isinstance(result, str)

    def test_safe_serialize_none(self):
        integ = self._make_integration()
        result = integ._safe_serialize(None)
        assert result is None


class TestCeleryInit:
    """Test __init__.py coverage."""

    def test_init_exports(self):
        from mohflow.integrations import __init__  # noqa
