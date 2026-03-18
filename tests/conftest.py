import logging
import pytest
import requests
from mohflow import MohflowLogger


@pytest.fixture(autouse=True)
def _clean_mohflow_state():
    """Reset MohFlow global state between every test."""
    yield
    # Clear bound context from contextvars API
    try:
        from mohflow.context_api import clear_context

        clear_context()
    except ImportError:
        pass

    # Reset the lazy log singleton so tests don't leak state
    try:
        from mohflow import _LazyLog

        _LazyLog._instance = None
    except (ImportError, AttributeError):
        pass

    # Clear correlation ID
    try:
        from mohflow.context.correlation import clear_correlation_id

        clear_correlation_id()
    except ImportError:
        pass

    # Reset root logger handlers to prevent handler accumulation
    root = logging.getLogger()
    for handler in root.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass
    root.handlers.clear()


@pytest.fixture
def basic_logger():
    """Returns a basic console-only logger"""
    return MohflowLogger(
        service_name="test-service", enable_sensitive_data_filter=False
    )


@pytest.fixture
def temp_log_file(tmp_path):
    """Creates a temporary log file"""
    log_file = tmp_path / "test.log"
    return str(log_file)


@pytest.fixture
def file_logger(temp_log_file):
    """Returns a logger with file output"""
    return MohflowLogger(
        service_name="test-service",
        file_logging=True,
        log_file_path=temp_log_file,
    )


# UI Test Configuration
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
