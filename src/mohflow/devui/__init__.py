"""
Mohnitor: Auto-spun, Kibana-lite viewer for JSON logs.

A self-contained log viewer that automatically spins up with MohFlow.
Provides a shared UI hub for multiple applications with real-time filtering.
"""

from .mohnitor import enable_mohnitor
from .types import (
    HubDescriptor,
    LogEvent,
    ClientConnection,
    FilterConfiguration,
    UIState,
)

__all__ = [
    "enable_mohnitor",
    "HubDescriptor",
    "LogEvent",
    "ClientConnection",
    "FilterConfiguration",
    "UIState",
]
