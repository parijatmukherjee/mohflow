import json
import logging
import pytest
from mohflow import MohflowLogger


@pytest.fixture
def caplog(caplog):
    """Configure caplog for JSON logging"""
    caplog.set_level(logging.DEBUG)
    return caplog


def test_logger_info(basic_logger, caplog):
    """Test info level logging"""
    with caplog.at_level(logging.INFO):
        basic_logger.info("Test message", extra_field="value")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "INFO"
    assert "Test message" in record.message
    assert hasattr(record, "extra_field")
    assert record.extra_field == "value"


def test_logger_error(basic_logger, caplog):
    """Test error level logging"""
    with caplog.at_level(logging.ERROR):
        basic_logger.error("Error message", error_code=500, exc_info=False)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "ERROR"
    assert "Error message" in record.message
    assert hasattr(record, "error_code")
    assert record.error_code == 500


def test_file_logging(file_logger, temp_log_file):
    """Test logging to file"""
    test_message = "Test file logging"
    file_logger.info(test_message)

    # Add a small delay to ensure file is written
    import time

    time.sleep(0.1)

    with open(temp_log_file, "r") as f:
        content = f.readline().strip()
        assert content, "Log file is empty"
        print(f"Raw content: {content}")  # Debug line
        log_entry = json.loads(content)
        print(f"Parsed log entry: {log_entry}")  # Debug line

    # Use .get() with default value to avoid KeyError
    assert log_entry.get("message") == test_message


# tests/test_logger.py
def test_loki_logging(mocker):
    """Test Loki integration"""
    # Create a proper mock for LokiHandler
    mock_handler = mocker.Mock()
    mock_handler.level = logging.INFO  # Add this line to fix comparison

    # Mock the LokiHandler class
    mocker.patch("logging_loki.LokiHandler", return_value=mock_handler)

    logger = MohflowLogger(
        service_name="test-service", loki_url="http://loki:3100"
    )

    # Log a message
    test_message = "Test Loki"
    logger.info(test_message)

    # Verify that the handler was used
    assert hasattr(mock_handler, "handle")
    # Verify that at least one call was made to handle
    assert mock_handler.handle.call_count >= 1


@pytest.mark.parametrize(
    "log_level,method",
    [
        ("DEBUG", "debug"),
        ("INFO", "info"),
        ("WARNING", "warning"),
        ("ERROR", "error"),
    ],
)
def test_log_levels(caplog, log_level, method):
    """Test different log levels"""
    logger = MohflowLogger(service_name="test-service", log_level=log_level)

    numeric_level = getattr(logging, log_level)
    with caplog.at_level(numeric_level):
        getattr(logger, method)(f"Test {log_level}")

        records = [r for r in caplog.records if r.levelname == log_level]
        assert len(records) == 1
        assert f"Test {log_level}" in records[0].message


@pytest.mark.asyncio
async def test_async_logging(basic_logger, caplog):
    """Test logging in async context"""

    async def async_operation():
        basic_logger.info("Async operation")

    with caplog.at_level(logging.INFO):
        await async_operation()

    assert len(caplog.records) == 1
    assert "Async operation" in caplog.records[0].message


def test_context_preservation(basic_logger, caplog):
    """Test that context is preserved in logs"""
    context = {"request_id": "123", "user_id": "456", "ip": "127.0.0.1"}

    with caplog.at_level(logging.INFO):
        basic_logger.info("Request processed", **context)

    record = caplog.records[0]
    for key, value in context.items():
        assert hasattr(record, key)
        assert getattr(record, key) == value


def test_exception_logging(basic_logger, caplog):
    """Test exception logging"""
    try:
        raise ValueError("Test error")
    except Exception as e:
        with caplog.at_level(logging.ERROR):
            basic_logger.error("An error occurred", error=str(e))

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "ERROR"
    assert "Test error" in str(getattr(record, "error", ""))
