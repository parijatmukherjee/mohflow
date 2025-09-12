import pytest
import logging
from unittest.mock import Mock, patch
from mohflow.handlers.loki import LokiHandler
from mohflow.exceptions import ConfigurationError


@patch("logging_loki.LokiHandler")
def test_loki_handler_setup(mock_loki_class):
    """Test Loki handler setup"""
    mock_formatter = Mock(spec=logging.Formatter)
    mock_handler_instance = Mock()
    mock_loki_class.return_value = mock_handler_instance

    handler = LokiHandler.setup(
        url="http://loki:3100",
        service_name="test-service",
        environment="test",
        formatter=mock_formatter,
    )

    assert handler is not None
    assert handler == mock_handler_instance
    mock_loki_class.assert_called_once_with(
        url="http://loki:3100",
        tags={
            "service": "test-service",
            "environment": "test",
        },
        version="1",
    )
    mock_handler_instance.setFormatter.assert_called_once_with(mock_formatter)


@patch("logging_loki.LokiHandler")
def test_loki_handler_with_extra_tags(mock_loki_class):
    """Test Loki handler with extra tags"""
    mock_formatter = Mock(spec=logging.Formatter)
    mock_handler_instance = Mock()
    mock_loki_class.return_value = mock_handler_instance
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
    expected_tags = {
        "service": "test-service",
        "environment": "test",
        "app_version": "1.0.0",
    }
    assert call_kwargs["tags"] == expected_tags


@patch("logging_loki.LokiHandler")
def test_loki_handler_error(mock_loki_class):
    """Test Loki handler error handling"""
    mock_formatter = Mock(spec=logging.Formatter)
    mock_loki_class.side_effect = Exception("Connection failed")

    with pytest.raises(ConfigurationError) as exc_info:
        LokiHandler.setup(
            url="http://invalid-url",
            service_name="test-service",
            environment="test",
            formatter=mock_formatter,
        )

    assert "Failed to setup Loki logging" in str(exc_info.value)
