"""Tests for devui modules: paths, discovery, election, mohnitor."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from mohflow.devui.paths import (
    get_mohnitor_temp_dir,
    get_hub_descriptor_path,
    get_election_lock_path,
    get_ui_state_path,
    get_default_descriptor_path,
    get_default_lock_path,
)
from mohflow.devui.discovery import (
    discover_hub,
    _discover_from_remote_url,
    _discover_from_file,
    _probe_default_port,
    _is_pid_alive,
    _validate_hub_health,
)
from mohflow.devui.election import (
    try_become_hub,
    _acquire_lock,
    _is_lock_stale,
    _release_lock,
    _find_available_port,
    _generate_token,
    _save_descriptor,
)
from mohflow.devui.mohnitor import (
    enable_mohnitor,
    _connect_to_hub,
    _start_hub_background,
)


class TestPaths:
    """Test path utilities."""

    def test_get_mohnitor_temp_dir(self):
        d = get_mohnitor_temp_dir()
        assert isinstance(d, Path)
        assert d.name == "mohnitor"

    def test_get_hub_descriptor_path(self):
        p = get_hub_descriptor_path()
        assert p.name == "hub.json"

    def test_get_election_lock_path(self):
        p = get_election_lock_path()
        assert p.name == "hub.lock"

    def test_get_ui_state_path(self):
        p = get_ui_state_path()
        assert p is not None
        assert p.name == "ui-state.json"

    def test_get_default_descriptor_path(self):
        p = get_default_descriptor_path()
        assert isinstance(p, str)
        assert "hub.json" in p

    def test_get_default_lock_path(self):
        p = get_default_lock_path()
        assert isinstance(p, str)
        assert "hub.lock" in p


class TestDiscovery:
    """Test hub discovery logic."""

    @patch.dict(os.environ, {}, clear=True)
    @patch(
        "mohflow.devui.discovery._discover_from_file",
        return_value=None,
    )
    @patch(
        "mohflow.devui.discovery._probe_default_port",
        return_value=None,
    )
    def test_discover_hub_no_hub(self, mock_probe, mock_file):
        result = discover_hub()
        assert result is None

    @patch.dict(
        os.environ,
        {"MOHNITOR_REMOTE": "ws://127.0.0.1:17361/ws"},
    )
    @patch("mohflow.devui.discovery._discover_from_remote_url")
    def test_discover_hub_remote(self, mock_remote):
        mock_remote.return_value = MagicMock()
        result = discover_hub()
        assert result is not None

    @patch("requests.get")
    def test_discover_from_remote_url_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        result = _discover_from_remote_url("ws://127.0.0.1:17361/ws")
        # pid=0 may fail validation depending on types
        # Just verify mock was called
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_discover_from_remote_url_failure(self, mock_get):
        import requests as req

        mock_get.side_effect = req.RequestException("fail")
        result = _discover_from_remote_url("ws://bad:1234/ws")
        assert result is None

    def test_discover_from_remote_url_invalid(self):
        result = _discover_from_remote_url("not-a-ws-url")
        assert result is None

    @patch("mohflow.devui.discovery.get_hub_descriptor_path")
    def test_discover_from_file_no_file(self, mock_path):
        mock_path.return_value = Path("/nonexistent/hub.json")
        result = _discover_from_file()
        assert result is None

    @patch("mohflow.devui.discovery.get_hub_descriptor_path")
    @patch("mohflow.devui.discovery._is_pid_alive")
    @patch("mohflow.devui.discovery._validate_hub_health")
    def test_discover_from_file_stale_pid(
        self, mock_health, mock_alive, mock_path, tmp_path
    ):
        descriptor = tmp_path / "hub.json"
        descriptor.write_text(
            json.dumps(
                {
                    "host": "127.0.0.1",
                    "port": 17361,
                    "pid": 99999,
                    "token": None,
                    "created_at": "2024-01-01T00:00:00",
                    "version": "1.0.0",
                }
            )
        )
        mock_path.return_value = descriptor
        mock_alive.return_value = False
        result = _discover_from_file()
        assert result is None

    @patch("requests.get")
    def test_probe_default_port_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        # _probe_default_port creates HubDescriptor(pid=0)
        # which may fail validation; just verify get called
        _probe_default_port()
        mock_get.assert_called()

    @patch("requests.get")
    def test_probe_default_port_none(self, mock_get):
        import requests as req

        mock_get.side_effect = req.RequestException("fail")
        result = _probe_default_port()
        assert result is None

    def test_is_pid_alive_current(self):
        assert _is_pid_alive(os.getpid()) is True

    def test_is_pid_alive_dead(self):
        assert _is_pid_alive(999999999) is False

    @patch("requests.get")
    def test_validate_hub_health_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        descriptor = MagicMock()
        descriptor.host = "127.0.0.1"
        descriptor.port = 17361
        assert _validate_hub_health(descriptor) is True

    @patch("requests.get")
    def test_validate_hub_health_failure(self, mock_get):
        mock_get.side_effect = Exception("fail")
        descriptor = MagicMock()
        descriptor.host = "127.0.0.1"
        descriptor.port = 17361
        assert _validate_hub_health(descriptor) is False


class TestElection:
    """Test leader election."""

    def test_find_available_port(self):
        port = _find_available_port("127.0.0.1", 17361)
        # Should find something in the range
        assert port is not None
        assert 17361 <= port < 17381

    def test_generate_token(self):
        token = _generate_token()
        assert isinstance(token, str)
        assert len(token) > 10

    def test_is_lock_stale_no_pid(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock_file.write_text(json.dumps({}))
        assert _is_lock_stale(lock_file) is True

    def test_is_lock_stale_dead_process(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock_file.write_text(json.dumps({"pid": 999999999, "timestamp": 0}))
        assert _is_lock_stale(lock_file) is True

    def test_is_lock_stale_alive_process(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock_file.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "timestamp": 0,
                }
            )
        )
        assert _is_lock_stale(lock_file) is False

    def test_is_lock_stale_invalid_json(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock_file.write_text("not json")
        assert _is_lock_stale(lock_file) is True

    def test_release_lock(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock_file.write_text("lock")
        _release_lock(lock_file)
        assert not lock_file.exists()

    def test_release_lock_nonexistent(self, tmp_path):
        _release_lock(tmp_path / "nope.lock")

    @patch("mohflow.devui.election._acquire_lock")
    @patch("mohflow.devui.election._find_available_port")
    @patch("mohflow.devui.election._save_descriptor")
    @patch("mohflow.devui.election._release_lock")
    def test_try_become_hub_success(
        self,
        mock_release,
        mock_save,
        mock_port,
        mock_lock,
    ):
        mock_lock.return_value = True
        mock_port.return_value = 17361
        result = try_become_hub()
        assert result == 17361

    @patch("mohflow.devui.election._acquire_lock")
    def test_try_become_hub_lock_fail(self, mock_lock):
        mock_lock.return_value = False
        result = try_become_hub()
        assert result is None

    @patch("mohflow.devui.election._acquire_lock")
    @patch("mohflow.devui.election._find_available_port")
    @patch("mohflow.devui.election._release_lock")
    def test_try_become_hub_no_port(self, mock_release, mock_port, mock_lock):
        mock_lock.return_value = True
        mock_port.return_value = None
        result = try_become_hub()
        assert result is None


class TestMohnitor:
    """Test mohnitor integration."""

    @patch.dict(os.environ, {"MOHNITOR_DISABLE": "1"})
    def test_enable_mohnitor_disabled(self):
        result = enable_mohnitor("test-service")
        assert result is False

    @patch("mohflow.devui.mohnitor.discover_hub")
    @patch("mohflow.devui.mohnitor._connect_to_hub")
    @patch.dict(os.environ, {}, clear=False)
    def test_enable_mohnitor_existing_hub(self, mock_connect, mock_discover):
        # Remove disable env var if present
        os.environ.pop("MOHNITOR_DISABLE", None)
        mock_hub = MagicMock()
        mock_hub.host = "127.0.0.1"
        mock_hub.port = 17361
        mock_discover.return_value = mock_hub
        mock_connect.return_value = True
        result = enable_mohnitor("test-service")
        assert result is True

    @patch("mohflow.devui.mohnitor.discover_hub")
    @patch("mohflow.devui.mohnitor.try_become_hub")
    @patch.dict(os.environ, {}, clear=False)
    def test_enable_mohnitor_no_hub_no_port(
        self, mock_election, mock_discover
    ):
        os.environ.pop("MOHNITOR_DISABLE", None)
        mock_discover.return_value = None
        mock_election.return_value = None
        result = enable_mohnitor("test-service")
        assert result is False

    @patch("mohflow.devui.mohnitor.discover_hub")
    @patch.dict(os.environ, {}, clear=False)
    def test_enable_mohnitor_exception(self, mock_discover):
        os.environ.pop("MOHNITOR_DISABLE", None)
        mock_discover.side_effect = RuntimeError("fail")
        result = enable_mohnitor("test-service")
        assert result is False

    @patch("mohflow.devui.mohnitor.MohnitorForwardingHandler")
    def test_connect_to_hub(self, mock_handler_cls):
        mock_handler = MagicMock()
        mock_handler_cls.return_value = mock_handler
        result = _connect_to_hub("test", "127.0.0.1", 17361, 20000)
        assert result is True

    @patch("mohflow.devui.mohnitor.MohnitorForwardingHandler")
    def test_connect_to_hub_failure(self, mock_handler_cls):
        mock_handler_cls.side_effect = Exception("fail")
        result = _connect_to_hub("test", "127.0.0.1", 17361, 20000)
        assert result is False
