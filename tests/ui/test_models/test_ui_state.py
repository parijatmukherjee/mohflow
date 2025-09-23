"""
Unit tests for UIState persistence.

These tests MUST FAIL initially until the types.py implementation is complete.
"""

import pytest
import json
from datetime import datetime, timezone
from mohflow.devui.types import UIState, FilterConfiguration


class TestUIState:
    """Test UIState persistence and validation."""

    def test_ui_state_creation(self):
        """Test basic UIState creation."""
        ui_state = UIState()

        assert ui_state.theme == "auto"
        assert ui_state.auto_scroll is True
        assert isinstance(ui_state.columns, list)
        assert len(ui_state.columns) > 0

    def test_ui_state_with_filters(self):
        """Test UIState with saved filters."""
        filter1 = FilterConfiguration(name="Errors", levels=["ERROR"])
        filter2 = FilterConfiguration(name="Service", services=["api"])

        ui_state = UIState(filters=[filter1, filter2])

        assert len(ui_state.filters) == 2
        assert ui_state.filters[0].name == "Errors"

    def test_ui_state_serialization(self):
        """Test UIState JSON serialization."""
        ui_state = UIState(
            theme="dark", columns=["timestamp", "level", "service", "message"]
        )

        # Should serialize to dict
        data = ui_state.to_dict()
        assert isinstance(data, dict)
        assert data["theme"] == "dark"

        # Should be JSON serializable
        json_str = json.dumps(data, default=str)
        assert isinstance(json_str, str)

    def test_ui_state_persistence(self):
        """Test UIState file persistence."""
        ui_state = UIState(theme="light")

        # Should save to file
        ui_state.save_to_file()

        # Should load from file
        loaded_state = UIState.load_from_file()
        assert loaded_state.theme == "light"
