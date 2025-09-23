import pytest
from mohflow import MohflowLogger
from mohflow.exceptions import ConfigurationError


def test_minimal_config():
    """Test logger creation with minimal config"""
    logger = MohflowLogger(service_name="test-service")
    assert logger.config.SERVICE_NAME == "test-service"
    assert logger.config.ENVIRONMENT == "development"
    assert logger.config.LOG_LEVEL == "INFO"


def test_file_logging_without_path():
    """Test that enabling file logging without path raises error"""
    with pytest.raises(ConfigurationError):
        MohflowLogger(
            service_name="test-service", file_logging=True, log_file_path=None
        )
