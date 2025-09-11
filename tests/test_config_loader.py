"""Tests for JSON configuration loader module."""

import pytest
import os
import json
import tempfile
from unittest.mock import Mock, patch, mock_open
from mohflow.config_loader import ConfigLoader


class TestConfigLoader:
    """Test cases for ConfigLoader class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.loader = ConfigLoader()

    def test_init_default(self):
        """Test ConfigLoader initialization with defaults."""
        assert self.loader.config_file is None
        assert self.loader.env_prefix == "MOHFLOW_"

    def test_init_with_params(self):
        """Test ConfigLoader initialization with parameters."""
        loader = ConfigLoader(config_file="test.json", env_prefix="TEST_")
        assert loader.config_file == "test.json"
        assert loader.env_prefix == "TEST_"

    def test_load_file_config_success(self):
        """Test successful file configuration loading."""
        test_config = {
            "service_name": "test-service",
            "log_level": "DEBUG",
            "environment": "development"
        }
        
        with patch('builtins.open', mock_open(read_data=json.dumps(test_config))):
            with patch('os.path.exists', return_value=True):
                config = self.loader._load_file_config("test.json")
                
                assert config == test_config

    def test_load_file_config_file_not_found(self):
        """Test file configuration loading with missing file."""
        with patch('os.path.exists', return_value=False):
            config = self.loader._load_file_config("missing.json")
            assert config == {}

    def test_load_file_config_invalid_json(self):
        """Test file configuration loading with invalid JSON."""
        with patch('builtins.open', mock_open(read_data="invalid json")):
            with patch('os.path.exists', return_value=True):
                config = self.loader._load_file_config("invalid.json")
                assert config == {}

    @patch('os.environ.get')
    def test_load_env_config(self, mock_env_get):
        """Test environment configuration loading."""
        def env_side_effect(key, default=None):
            env_vars = {
                'MOHFLOW_SERVICE_NAME': 'env-service',
                'MOHFLOW_LOG_LEVEL': 'INFO',
                'MOHFLOW_LOKI_URL': 'http://localhost:3100'
            }
            return env_vars.get(key, default)
        
        mock_env_get.side_effect = env_side_effect
        
        config = self.loader._load_env_config()
        
        expected = {
            'service_name': 'env-service',
            'log_level': 'INFO',
            'loki_url': 'http://localhost:3100'
        }
        assert config == expected

    def test_merge_configs_basic(self):
        """Test basic configuration merging."""
        base = {"service_name": "base", "log_level": "INFO"}
        override = {"log_level": "DEBUG", "environment": "test"}
        
        result = self.loader._merge_configs(base, override)
        
        expected = {
            "service_name": "base",
            "log_level": "DEBUG",
            "environment": "test"
        }
        assert result == expected

    def test_merge_configs_nested(self):
        """Test nested configuration merging."""
        base = {
            "service_name": "test",
            "context_enrichment": {
                "include_timestamp": True,
                "include_system_info": False
            }
        }
        override = {
            "context_enrichment": {
                "include_system_info": True,
                "include_request_context": True
            }
        }
        
        result = self.loader._merge_configs(base, override)
        
        expected = {
            "service_name": "test",
            "context_enrichment": {
                "include_timestamp": True,
                "include_system_info": True,
                "include_request_context": True
            }
        }
        assert result == expected

    def test_merge_configs_empty_base(self):
        """Test merging with empty base configuration."""
        base = {}
        override = {"service_name": "test", "log_level": "INFO"}
        
        result = self.loader._merge_configs(base, override)
        
        assert result == override

    def test_merge_configs_empty_override(self):
        """Test merging with empty override configuration."""
        base = {"service_name": "test", "log_level": "INFO"}
        override = {}
        
        result = self.loader._merge_configs(base, override)
        
        assert result == base

    def test_validate_config_success(self):
        """Test successful configuration validation."""
        config = {
            "service_name": "test-service",
            "log_level": "INFO",
            "environment": "development"
        }
        
        # Should not raise an exception
        self.loader._validate_config(config)

    def test_validate_config_missing_service_name(self):
        """Test configuration validation with missing service_name."""
        config = {
            "log_level": "INFO",
            "environment": "development"
        }
        
        with pytest.raises(ValueError, match="service_name is required"):
            self.loader._validate_config(config)

    def test_validate_config_invalid_log_level(self):
        """Test configuration validation with invalid log level."""
        config = {
            "service_name": "test-service",
            "log_level": "INVALID",
            "environment": "development"
        }
        
        with pytest.raises(ValueError, match="Invalid log_level"):
            self.loader._validate_config(config)

    def test_load_config_with_runtime_params(self):
        """Test loading configuration with runtime parameters."""
        with patch.object(self.loader, '_load_file_config', return_value={}):
            with patch.object(self.loader, '_load_env_config', return_value={}):
                config = self.loader.load_config(
                    service_name="runtime-service",
                    log_level="DEBUG"
                )
                
                assert config["service_name"] == "runtime-service"
                assert config["log_level"] == "DEBUG"

    def test_load_config_precedence(self):
        """Test configuration loading precedence: runtime > env > file."""
        file_config = {
            "service_name": "file-service",
            "log_level": "INFO",
            "environment": "development"
        }
        
        env_config = {
            "log_level": "WARNING",
            "loki_url": "http://env-loki:3100"
        }
        
        with patch.object(self.loader, '_load_file_config', return_value=file_config):
            with patch.object(self.loader, '_load_env_config', return_value=env_config):
                config = self.loader.load_config(
                    log_level="ERROR",  # Runtime override
                    console_logging=False
                )
                
                # Runtime parameter should have highest precedence
                assert config["log_level"] == "ERROR"
                
                # Environment should override file
                assert config["loki_url"] == "http://env-loki:3100"
                
                # File config should be preserved if not overridden
                assert config["service_name"] == "file-service"
                assert config["environment"] == "development"
                
                # Runtime parameter should be included
                assert config["console_logging"] is False

    def test_load_config_with_config_file(self):
        """Test loading configuration with specified config file."""
        test_config = {
            "service_name": "config-service",
            "log_level": "DEBUG"
        }
        
        loader = ConfigLoader(config_file="test_config.json")
        
        with patch.object(loader, '_load_file_config', return_value=test_config):
            with patch.object(loader, '_load_env_config', return_value={}):
                config = loader.load_config()
                
                assert config["service_name"] == "config-service"
                assert config["log_level"] == "DEBUG"

    def test_normalize_key(self):
        """Test key normalization for environment variables."""
        assert self.loader._normalize_key("SERVICE_NAME") == "service_name"
        assert self.loader._normalize_key("LOG_LEVEL") == "log_level"
        assert self.loader._normalize_key("LOKI_URL") == "loki_url"

    def test_convert_value_boolean(self):
        """Test value conversion for boolean types."""
        assert self.loader._convert_value("true") is True
        assert self.loader._convert_value("True") is True
        assert self.loader._convert_value("false") is False
        assert self.loader._convert_value("False") is False

    def test_convert_value_integer(self):
        """Test value conversion for integer types."""
        assert self.loader._convert_value("123") == 123
        assert self.loader._convert_value("-456") == -456

    def test_convert_value_string(self):
        """Test value conversion for string types."""
        assert self.loader._convert_value("test") == "test"
        assert self.loader._convert_value("") == ""

    def test_load_config_with_nested_env_vars(self):
        """Test loading configuration with nested environment variables."""
        with patch('os.environ.get') as mock_env_get:
            def env_side_effect(key, default=None):
                env_vars = {
                    'MOHFLOW_SERVICE_NAME': 'nested-service',
                    'MOHFLOW_CONTEXT_ENRICHMENT_INCLUDE_TIMESTAMP': 'true',
                    'MOHFLOW_CONTEXT_ENRICHMENT_INCLUDE_SYSTEM_INFO': 'false'
                }
                return env_vars.get(key, default)
            
            mock_env_get.side_effect = env_side_effect
            
            config = self.loader._load_env_config()
            
            assert config['service_name'] == 'nested-service'
            assert config['context_enrichment']['include_timestamp'] is True
            assert config['context_enrichment']['include_system_info'] is False

    def test_get_config_schema(self):
        """Test configuration schema retrieval."""
        schema = self.loader.get_config_schema()
        
        assert 'type' in schema
        assert 'properties' in schema
        assert 'service_name' in schema['properties']
        assert 'log_level' in schema['properties']

    def test_validate_against_schema(self):
        """Test configuration validation against schema."""
        valid_config = {
            "service_name": "test-service",
            "log_level": "INFO",
            "console_logging": True
        }
        
        # Should not raise an exception
        result = self.loader.validate_against_schema(valid_config)
        assert result is True

    def test_validate_against_schema_invalid(self):
        """Test configuration validation against schema with invalid config."""
        invalid_config = {
            "service_name": 123,  # Should be string
            "log_level": "INVALID"  # Invalid enum value
        }
        
        result = self.loader.validate_against_schema(invalid_config)
        assert result is False