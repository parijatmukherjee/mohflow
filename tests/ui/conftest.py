"""
Shared configuration for UI tests.
"""

import pytest
import requests


def hub_server_available():
    """Check if Mohnitor hub server is available."""
    try:
        response = requests.get("http://127.0.0.1:17361/healthz", timeout=1)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


_HUB_AVAILABLE = hub_server_available()

requires_hub_server = pytest.mark.skipif(
    not _HUB_AVAILABLE,
    reason="Mohnitor hub server not available",
)


def pytest_collection_modifyitems(config, items):
    """Auto-skip UI tests that need the hub server when it's not running."""
    if _HUB_AVAILABLE:
        return
    skip_marker = pytest.mark.skip(reason="Mohnitor hub server not available")
    for item in items:
        # Skip tests in test_contracts/, test_integration/, test_automation/
        # that hit the live hub
        rel = str(item.fspath)
        if (
            "test_contracts" in rel
            or "test_integration" in rel
            or "test_automation" in rel
        ):
            item.add_marker(skip_marker)


# Optional dependency markers
try:
    import selenium

    selenium_available = True
except ImportError:
    selenium_available = False

requires_selenium = pytest.mark.skipif(
    not selenium_available, reason="Selenium not available"
)


try:
    import fastapi

    fastapi_available = True
except ImportError:
    fastapi_available = False

requires_fastapi = pytest.mark.skipif(
    not fastapi_available, reason="FastAPI not available"
)
