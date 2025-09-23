"""
Hub discovery logic for Mohnitor.

Implements the discovery order: env → file → probe → election.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from .types import HubDescriptor
from .paths import get_hub_descriptor_path


def discover_hub() -> Optional[HubDescriptor]:
    """
    Discover existing Mohnitor hub using discovery order.

    Returns HubDescriptor if found, None if no valid hub exists.
    """

    # 1. Check environment override
    remote_url = os.getenv("MOHNITOR_REMOTE")
    if remote_url:
        return _discover_from_remote_url(remote_url)

    # 2. Check descriptor file
    descriptor = _discover_from_file()
    if descriptor:
        return descriptor

    # 3. Probe default port
    descriptor = _probe_default_port()
    if descriptor:
        return descriptor

    # No hub found
    return None


def _discover_from_remote_url(remote_url: str) -> Optional[HubDescriptor]:
    """Discover hub from MOHNITOR_REMOTE environment variable."""
    try:
        # Extract host and port from WebSocket URL
        # ws://127.0.0.1:17361/ws -> host=127.0.0.1, port=17361
        if remote_url.startswith("ws://"):
            url_part = remote_url[5:]  # Remove "ws://"
            if "/" in url_part:
                host_port = url_part.split("/")[0]
            else:
                host_port = url_part

            if ":" in host_port:
                host, port_str = host_port.rsplit(":", 1)
                port = int(port_str)
            else:
                host = host_port
                port = 17361

            # Validate hub is running
            health_url = f"http://{host}:{port}/healthz"
            response = requests.get(health_url, timeout=2)

            if response.status_code == 200:
                # Create descriptor from discovered hub
                return HubDescriptor(
                    host=host,
                    port=port,
                    pid=0,  # Unknown PID for remote
                    token=os.getenv("MOHNITOR_TOKEN"),
                    created_at=time.time(),
                    version="1.0.0",
                )

    except (requests.RequestException, ValueError, Exception):
        pass

    return None


def _discover_from_file() -> Optional[HubDescriptor]:
    """Discover hub from descriptor file."""
    descriptor_path = get_hub_descriptor_path()

    if not descriptor_path.exists():
        return None

    try:
        with open(descriptor_path) as f:
            data = json.load(f)

        descriptor = HubDescriptor.from_dict(data)

        # Validate PID is still alive
        if not _is_pid_alive(descriptor.pid):
            # Stale descriptor - remove it
            descriptor_path.unlink(missing_ok=True)
            return None

        # Validate hub is responsive
        if not _validate_hub_health(descriptor):
            # Hub not responsive - remove stale descriptor
            descriptor_path.unlink(missing_ok=True)
            return None

        return descriptor

    except (json.JSONDecodeError, Exception):
        # Invalid descriptor file - remove it
        descriptor_path.unlink(missing_ok=True)
        return None


def _probe_default_port() -> Optional[HubDescriptor]:
    """Probe default port range for running hub."""
    for port in range(17361, 17381):  # 17361-17380
        try:
            health_url = f"http://127.0.0.1:{port}/healthz"
            response = requests.get(health_url, timeout=1)

            if response.status_code == 200:
                # Found running hub
                return HubDescriptor(
                    host="127.0.0.1",
                    port=port,
                    pid=0,  # Unknown PID
                    token=None,  # Localhost
                    created_at=time.time(),
                    version="1.0.0",
                )

        except requests.RequestException:
            continue

    return None


def _is_pid_alive(pid: int) -> bool:
    """Check if process ID is still alive."""
    if HAS_PSUTIL:
        try:
            return psutil.pid_exists(pid)
        except Exception:
            pass

    # Fallback to basic OS check
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _validate_hub_health(descriptor: HubDescriptor) -> bool:
    """Validate hub is responsive via health check."""
    if not HAS_REQUESTS:
        return True  # Assume healthy if can't check

    try:
        health_url = f"http://{descriptor.host}:{descriptor.port}/healthz"
        response = requests.get(health_url, timeout=2)
        return response.status_code == 200
    except Exception:
        return False
