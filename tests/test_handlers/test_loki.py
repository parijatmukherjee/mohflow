import pytest
from mohflow.handlers.loki import LokiHandler
from mohflow.exceptions import ConfigurationError
import logging


def test_loki_handler_setup(mocker):
    """Test Loki handler setup"""
    mock_formatter = mocker.Mock(spec=logging.Formatter)

    handler = LokiHandler.setup(
        url="http://loki:3100",
        service_name="test-service",
        environment="test",
        formatter=mock_formatter,
    )

    assert handler is not None
    assert handler.formatter == mock_formatter


def test_loki_handler_with_extra_tags(mocker):
    """Test Loki handler with extra tags"""
    # Mock the LokiHandler class
    mock_loki_class = mocker.patch("logging_loki.LokiHandler")
    mock_formatter = mocker.Mock(spec=logging.Formatter)
    extra_tags = {"app_version": "1.0.0"}

    # Create handler
    LokiHandler.setup(
        url="http://loki:3100",
        service_name="test-service",
        environment="test",
        formatter=mock_formatter,
        extra_tags=extra_tags,
    )

    # Verify the tags passed to LokiHandler constructor
    mock_loki_class.assert_called_once()
    call_kwargs = mock_loki_class.call_args[1]
    assert "tags" in call_kwargs
    assert call_kwargs["tags"]["app_version"] == "1.0.0"


def test_loki_handler_error(mocker):
    """Test Loki handler error handling"""
    mocker.patch(
        "logging_loki.LokiHandler", side_effect=Exception("Connection failed")
    )

    with pytest.raises(ConfigurationError) as exc_info:
        LokiHandler.setup(
            url="http://invalid-url",
            service_name="test-service",
            environment="test",
            formatter=mocker.Mock(),
        )

    assert "Failed to setup Loki logging" in str(exc_info.value)
