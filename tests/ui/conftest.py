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


requires_hub_server = pytest.mark.skipif(
    not hub_server_available(), reason="Mohnitor hub server not available"
)


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
