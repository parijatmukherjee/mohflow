"""
Leader election for Mohnitor hub.

Implements lockfile-based election to prevent race conditions.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .paths import get_election_lock_path, get_hub_descriptor_path
from .types import HubDescriptor


def try_become_hub(
    host: str = "127.0.0.1", base_port: int = 17361
) -> Optional[int]:
    """
    Try to become hub through leader election.

    Returns port number if successful, None if another process won.
    """
    lock_path = get_election_lock_path()

    # Try to acquire lock
    if not _acquire_lock(lock_path):
        return None

    try:
        # Find available port
        port = _find_available_port(host, base_port)
        if not port:
            return None

        # Create and save descriptor
        descriptor = HubDescriptor(
            host=host,
            port=port,
            pid=os.getpid(),
            token=None if host == "127.0.0.1" else _generate_token(),
            created_at=datetime.now(timezone.utc),
            version="1.0.0",
        )

        _save_descriptor(descriptor)

        return port

    finally:
        # Release lock
        _release_lock(lock_path)


def _acquire_lock(lock_path: Path) -> bool:
    """Acquire election lock file."""
    try:
        # Ensure directory exists
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Try to create lock file exclusively
        with open(lock_path, "x") as f:
            lock_data = {"pid": os.getpid(), "timestamp": time.time()}
            json.dump(lock_data, f)

        return True

    except FileExistsError:
        # Another process has the lock
        # Check if lock is stale
        if _is_lock_stale(lock_path):
            # Remove stale lock and try again
            lock_path.unlink(missing_ok=True)
            return _acquire_lock(lock_path)

        return False

    except Exception:
        return False


def _is_lock_stale(lock_path: Path) -> bool:
    """Check if lock file is stale (process died)."""
    try:
        with open(lock_path) as f:
            data = json.load(f)

        pid = data.get("pid")
        if not pid:
            return True

        # Check if process is still alive
        try:
            os.kill(pid, 0)
            return False  # Process alive
        except (OSError, ProcessLookupError):
            return True  # Process dead

    except (json.JSONDecodeError, Exception):
        return True  # Invalid lock file


def _release_lock(lock_path: Path) -> None:
    """Release election lock file."""
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _find_available_port(host: str, base_port: int) -> Optional[int]:
    """Find available port in range."""
    import socket

    for port in range(base_port, base_port + 20):  # Try 20 ports
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            continue

    return None


def _generate_token() -> str:
    """Generate authentication token for remote access."""
    import secrets

    return secrets.token_urlsafe(24)


def _save_descriptor(descriptor: HubDescriptor) -> None:
    """Save hub descriptor to file."""
    descriptor_path = get_hub_descriptor_path()
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)

    with open(descriptor_path, "w") as f:
        json.dump(descriptor.to_dict(), f, indent=2, default=str)
