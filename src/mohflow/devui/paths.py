"""
File paths and descriptor management for Mohnitor.

Handles hub descriptor files, lockfiles, and UI state persistence.
"""

import os
from pathlib import Path
from typing import Optional


def get_mohnitor_temp_dir() -> Path:
    """Get the temporary directory for Mohnitor files."""
    temp_dir = Path("/tmp/mohnitor")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir


def get_hub_descriptor_path() -> Path:
    """Get path to hub descriptor JSON file."""
    return get_mohnitor_temp_dir() / "hub.json"


def get_election_lock_path() -> Path:
    """Get path to leader election lockfile."""
    return get_mohnitor_temp_dir() / "hub.lock"


def get_ui_state_path() -> Optional[Path]:
    """Get path to UI state configuration file."""
    config_dir = Path.home() / ".config" / "mohnitor"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "ui-state.json"


def get_default_descriptor_path() -> str:
    """Get default descriptor path as string for configuration."""
    return str(get_hub_descriptor_path())


def get_default_lock_path() -> str:
    """Get default lock path as string for configuration."""
    return str(get_election_lock_path())
