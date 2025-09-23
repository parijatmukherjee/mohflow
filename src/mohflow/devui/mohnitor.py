"""
Main Mohnitor integration module.

Provides the enable_mohnitor() function for MohFlow integration.
"""

import os
import threading
import time
from typing import Optional

from .discovery import discover_hub
from .election import try_become_hub
from .hub import MohnitorHub
from .client import MohnitorForwardingHandler


def enable_mohnitor(
    service: str,
    mohnitor_host: str = "127.0.0.1",
    mohnitor_base_port: int = 17361,
    mohnitor_descriptor: Optional[str] = None,
    mohnitor_election_lock: Optional[str] = None,
    mohnitor_buffer_size: int = 20000,
) -> bool:
    """
    Enable Mohnitor log forwarding for this service.

    Args:
        service: Service identifier
        mohnitor_host: Host to bind hub (default: localhost)
        mohnitor_base_port: Starting port for hub (default: 17361)
        mohnitor_descriptor: Path to hub descriptor file
        mohnitor_election_lock: Path to election lockfile
        mohnitor_buffer_size: Client-side buffer size

    Returns:
        True if Mohnitor was enabled successfully, False otherwise
    """
    # Check if disabled via environment
    if os.getenv("MOHNITOR_DISABLE") == "1":
        return False

    try:
        # Try to discover existing hub
        existing_hub = discover_hub()

        if existing_hub:
            # Connect to existing hub
            return _connect_to_hub(
                service,
                existing_hub.host,
                existing_hub.port,
                mohnitor_buffer_size,
            )
        else:
            # Try to become hub
            hub_port = try_become_hub(mohnitor_host, mohnitor_base_port)
            if hub_port:
                # Start hub in background thread
                _start_hub_background(
                    mohnitor_host, hub_port, mohnitor_buffer_size
                )
                time.sleep(1)  # Give hub time to start

                # Connect to our own hub
                return _connect_to_hub(
                    service, mohnitor_host, hub_port, mohnitor_buffer_size
                )

        return False

    except Exception as e:
        print(f"Failed to enable Mohnitor: {e}")
        return False


def _connect_to_hub(
    service: str, host: str, port: int, buffer_size: int
) -> bool:
    """Connect to existing hub as client."""
    try:
        # Create forwarding handler
        handler = MohnitorForwardingHandler(
            service=service,
            hub_host=host,
            hub_port=port,
            buffer_size=buffer_size,
        )

        # Add to root logger (simplified integration)
        import logging

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        print(f"📡 Connected to Mohnitor hub at: http://{host}:{port}/ui")
        return True

    except Exception as e:
        print(f"Failed to connect to Mohnitor hub: {e}")
        return False


def _start_hub_background(host: str, port: int, buffer_size: int) -> None:
    """Start hub server in background thread."""

    def run_hub():
        try:
            hub = MohnitorHub(host=host, port=port, buffer_size=buffer_size)
            hub.run()
        except Exception as e:
            print(f"Hub failed to start: {e}")

    hub_thread = threading.Thread(target=run_hub, daemon=True)
    hub_thread.start()
