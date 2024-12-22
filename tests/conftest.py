import pytest
import logging
from mohflow import MohflowLogger

@pytest.fixture
def basic_logger():
    """Returns a basic console-only logger"""
    return MohflowLogger(service_name="test-service")

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
        log_file_path=temp_log_file
    )