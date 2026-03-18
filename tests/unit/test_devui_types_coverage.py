"""Tests for devui/types.py uncovered paths."""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from mohflow.devui.types import (
    HubDescriptor,
    LogEvent,
    FilterConfiguration,
    UIState,
    utcnow,
    _normalize_iso_timestamp,
    parse_iso_datetime,
)


class TestUtcnow:
    def test_returns_aware_datetime(self):
        dt = utcnow()
        assert dt.tzinfo is not None
        assert dt.tzinfo == timezone.utc


class TestNormalizeIsoTimestamp:
    def test_z_suffix(self):
        result = _normalize_iso_timestamp(
            "2024-01-01T00:00:00Z"
        )
        assert result == "2024-01-01T00:00:00+00:00"

    def test_plus_utc_z_suffix(self):
        result = _normalize_iso_timestamp(
            "2024-01-01T00:00:00+00:00Z"
        )
        assert result == "2024-01-01T00:00:00+00:00"

    def test_already_correct(self):
        result = _normalize_iso_timestamp(
            "2024-01-01T00:00:00+00:00"
        )
        assert result == "2024-01-01T00:00:00+00:00"


class TestParseIsoDatetime:
    def test_parses_z_format(self):
        dt = parse_iso_datetime("2024-01-01T00:00:00Z")
        assert dt.year == 2024


class TestFilterConfiguration:
    def test_validate_time_range_invalid(self):
        with pytest.raises(ValueError):
            fc = FilterConfiguration(
                name="bad", time_range="99h"
            )
            fc._validate_time_range()

    def test_parse_mql_empty(self):
        fc = FilterConfiguration(name="f1")
        assert fc.parse_mql() == {}

    def test_parse_mql_level(self):
        fc = FilterConfiguration(
            name="f1", query_expression="level:ERROR"
        )
        result = fc.parse_mql()
        assert result["level"] == "ERROR"

    def test_to_dict(self):
        fc = FilterConfiguration(
            name="f1",
            levels=["INFO"],
            services=["svc1"],
        )
        d = fc.to_dict()
        assert d["name"] == "f1"
        assert d["levels"] == ["INFO"]

    def test_to_dict_with_created_at(self):
        fc = FilterConfiguration(
            name="f1",
            created_at=datetime(
                2024, 1, 1, tzinfo=timezone.utc
            ),
        )
        d = fc.to_dict()
        assert d["created_at"] is not None

    def test_from_dict(self):
        d = {
            "name": "f1",
            "levels": ["ERROR"],
            "services": [],
        }
        fc = FilterConfiguration.from_dict(d)
        assert fc.name == "f1"
        assert fc.levels == ["ERROR"]

    def test_from_dict_with_z_timestamp(self):
        d = {
            "name": "f1",
            "created_at": "2024-01-01T00:00:00Z",
        }
        fc = FilterConfiguration.from_dict(d)
        assert fc.created_at is not None

    def test_from_dict_with_utc_timestamp(self):
        d = {
            "name": "f1",
            "created_at": "2024-01-01T00:00:00+00:00",
        }
        fc = FilterConfiguration.from_dict(d)
        assert fc.created_at is not None


class TestUIState:
    def test_to_dict(self):
        state = UIState()
        d = state.to_dict()
        assert d["theme"] == "auto"
        assert d["auto_scroll"] is True
        assert d["version"] == 1

    def test_to_dict_with_filters(self):
        fc = FilterConfiguration(
            name="f1", levels=["INFO"]
        )
        state = UIState(filters=[fc])
        d = state.to_dict()
        assert len(d["filters"]) == 1

    def test_to_dict_with_last_updated(self):
        state = UIState(
            last_updated=datetime(
                2024, 1, 1, tzinfo=timezone.utc
            )
        )
        d = state.to_dict()
        assert d["last_updated"] is not None

    def test_load_from_file_no_file(self):
        with patch(
            "mohflow.devui.paths.get_ui_state_path"
        ) as mock_path:
            mock_path.return_value = None
            state = UIState.load_from_file()
            assert state.theme == "auto"

    def test_load_from_file_missing_file(self, tmp_path):
        with patch(
            "mohflow.devui.paths.get_ui_state_path"
        ) as mock_path:
            mock_path.return_value = (
                tmp_path / "nonexistent.json"
            )
            state = UIState.load_from_file()
            assert state.theme == "auto"

    def test_load_from_file_valid(self, tmp_path):
        p = tmp_path / "ui-state.json"
        p.write_text(
            json.dumps(
                {
                    "theme": "dark",
                    "auto_scroll": False,
                    "version": 2,
                }
            )
        )
        with patch(
            "mohflow.devui.paths.get_ui_state_path"
        ) as mock_path:
            mock_path.return_value = p
            state = UIState.load_from_file()
            assert state.theme == "dark"
            assert state.auto_scroll is False

    def test_load_from_file_invalid_json(self, tmp_path):
        p = tmp_path / "ui-state.json"
        p.write_text("not json")
        with patch(
            "mohflow.devui.paths.get_ui_state_path"
        ) as mock_path:
            mock_path.return_value = p
            state = UIState.load_from_file()
            assert state.theme == "auto"

    def test_save_to_file(self, tmp_path):
        p = tmp_path / "ui-state.json"
        with patch(
            "mohflow.devui.paths.get_ui_state_path"
        ) as mock_path:
            mock_path.return_value = p
            state = UIState(theme="dark")
            state.save_to_file()
            assert p.exists()
            data = json.loads(p.read_text())
            assert data["theme"] == "dark"

    def test_save_to_file_no_path(self):
        with patch(
            "mohflow.devui.paths.get_ui_state_path"
        ) as mock_path:
            mock_path.return_value = None
            state = UIState()
            state.save_to_file()  # Should not raise

    def test_save_to_file_io_error(self):
        with patch(
            "mohflow.devui.paths.get_ui_state_path"
        ) as mock_path:
            mock_path.return_value = MagicMock()
            with patch(
                "builtins.open", side_effect=IOError
            ):
                state = UIState()
                state.save_to_file()  # Should not raise


class TestLogEvent:
    def test_from_dict(self):
        d = {
            "timestamp": "2024-01-01T00:00:00Z",
            "level": "INFO",
            "message": "hello",
            "service": "svc1",
            "logger": "test-logger",
        }
        event = LogEvent.from_dict(d)
        assert event.level == "INFO"
        assert event.message == "hello"

    def test_to_dict(self):
        event = LogEvent(
            timestamp=datetime(
                2024, 1, 1, tzinfo=timezone.utc
            ),
            level="INFO",
            message="hello",
            service="svc1",
            logger="test-logger",
        )
        d = event.to_dict()
        assert d["level"] == "INFO"
        assert "timestamp" in d
