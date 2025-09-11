"""
Configuration loader for MohFlow with JSON support and validation.
Provides configuration loading from multiple sources with precedence handling.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union
from mohflow.exceptions import ConfigurationError


class ConfigLoader:
    """
    Configuration loader with support for JSON files, environment variables,
    and runtime parameters with proper precedence handling.

    Precedence order (highest to lowest):
    1. Runtime parameters (direct function arguments)
    2. JSON configuration file
    3. Environment variables
    4. Default values
    """

    def __init__(self, config_file: Optional[Union[str, Path]] = None):
        """
        Initialize configuration loader.

        Args:
            config_file: Path to JSON configuration file (optional)
        """
        self.config_file = Path(config_file) if config_file else None
        self.schema_path = (
            Path(__file__).parent / "schemas" / "config_schema.json"
        )
        self._schema: Optional[Dict[str, Any]] = None
        self.env_prefix = "MOHFLOW_"

    def _load_schema(self) -> Dict[str, Any]:
        """Load and cache JSON schema for validation"""
        if self._schema is None:
            try:
                with open(self.schema_path, "r") as f:
                    self._schema = json.load(f)
            except FileNotFoundError:
                raise ConfigurationError(
                    f"Configuration schema not found: {self.schema_path}"
                )
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Invalid JSON schema: {e}")
        return self._schema

    def _load_json_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        if not self.config_file:
            return {}

        if not self.config_file.exists():
            raise ConfigurationError(
                f"Configuration file not found: {self.config_file}"
            )

        try:
            with open(self.config_file, "r") as f:
                config = json.load(f)
            return config if isinstance(config, dict) else {}
        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in configuration file: {e}"
            )
        except Exception as e:
            raise ConfigurationError(f"Error reading configuration file: {e}")

    def _load_file_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            raise ConfigurationError(
                f"Configuration file not found: {config_file}"
            )
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in config file: {e}")

    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables"""
        env_config = {}
        env_prefix = "MOHFLOW_"

        # Map environment variables to config keys
        env_mappings = {
            f"{env_prefix}SERVICE_NAME": "service_name",
            f"{env_prefix}ENVIRONMENT": "environment",
            f"{env_prefix}LOG_LEVEL": "log_level",
            f"{env_prefix}CONSOLE_LOGGING": "console_logging",
            f"{env_prefix}FILE_LOGGING": "file_logging",
            f"{env_prefix}LOG_FILE_PATH": "log_file_path",
            f"{env_prefix}LOKI_URL": "loki_url",
        }

        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert string values to appropriate types
                if config_key in ["console_logging", "file_logging"]:
                    env_config[config_key] = value.lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                    )
                else:
                    env_config[config_key] = value

        return env_config

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values"""
        return {
            "environment": "development",
            "log_level": "INFO",
            "console_logging": True,
            "file_logging": False,
            "auto_configuration": {
                "enabled": False,
                "detect_environment": True,
                "cloud_metadata": False,
            },
            "context_enrichment": {
                "enabled": True,
                "include_timestamp": True,
                "include_request_id": False,
                "include_user_context": False,
                "custom_fields": {},
            },
            "handlers": {
                "loki": {
                    "enabled": True,
                    "batch_size": 100,
                    "timeout": 10,
                    "extra_tags": {},
                },
                "file": {
                    "enabled": True,
                    "rotation": False,
                    "max_size_mb": 100,
                    "backup_count": 5,
                },
            },
        }

    def _merge_configs(self, *configs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge multiple configuration dictionaries.
        Later configs override earlier ones.
        """
        merged = {}

        for config in configs:
            if not config:
                continue

            for key, value in config.items():
                if (
                    isinstance(value, dict)
                    and key in merged
                    and isinstance(merged[key], dict)
                ):
                    # Recursively merge nested dictionaries
                    merged[key] = self._merge_configs(merged[key], value)
                else:
                    # Override with new value
                    merged[key] = value

        return merged

    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration against schema.
        Note: Basic validation without jsonschema dependency.
        """
        try:
            # Check required fields
            if "service_name" not in config or not config["service_name"]:
                raise ConfigurationError(
                    "Missing required field: service_name"
                )

            # Validate log level
            if "log_level" in config:
                valid_levels = [
                    "DEBUG",
                    "INFO",
                    "WARNING",
                    "ERROR",
                    "CRITICAL",
                ]
                if config["log_level"] not in valid_levels:
                    raise ConfigurationError(
                        f"Invalid log level: {config['log_level']}"
                    )

            # Validate environment
            if "environment" in config:
                valid_envs = ["development", "staging", "production"]
                if config["environment"] not in valid_envs:
                    raise ConfigurationError(
                        f"Invalid environment: {config['environment']}"
                    )

            # Validate file logging configuration
            if config.get("file_logging") and not config.get("log_file_path"):
                raise ConfigurationError(
                    "log_file_path is required when file_logging is enabled"
                )

            return True

        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"Configuration validation error: {e}")

    def load_config(self, **runtime_params) -> Dict[str, Any]:
        """
        Load and merge configuration from all sources.

        Args:
            **runtime_params: Runtime configuration parameters

        Returns:
            Merged configuration dictionary

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Load configurations in precedence order (lowest to highest)
        default_config = self._get_default_config()
        env_config = self._load_env_config()
        json_config = self._load_json_config()

        # Filter out None values from runtime parameters
        runtime_config = {
            k: v for k, v in runtime_params.items() if v is not None
        }

        # Merge configurations (later ones override earlier ones)
        final_config = self._merge_configs(
            default_config, env_config, json_config, runtime_config
        )

        # Validate final configuration
        self._validate_config(final_config)

        return final_config

    def create_sample_config(self, output_path: Union[str, Path]) -> None:
        """
        Create a sample configuration file with default values and comments.

        Args:
            output_path: Path where to create the sample configuration
        """
        sample_config = {
            "_comment": "MohFlow Configuration File",
            "_description": "Sample config file for MohFlow logging library",
            "service_name": "my-service",
            "environment": "development",
            "log_level": "INFO",
            "console_logging": True,
            "file_logging": False,
            "log_file_path": "logs/app.log",
            "loki_url": "http://localhost:3100/loki/api/v1/push",
            "auto_configuration": {
                "_comment": "Auto-configuration settings",
                "enabled": False,
                "detect_environment": True,
                "cloud_metadata": False,
            },
            "context_enrichment": {
                "_comment": "Automatic context enrichment settings",
                "enabled": True,
                "include_timestamp": True,
                "include_request_id": False,
                "include_user_context": False,
                "custom_fields": {"version": "1.0.0", "component": "api"},
            },
            "handlers": {
                "_comment": "Handler-specific configurations",
                "loki": {
                    "enabled": True,
                    "batch_size": 100,
                    "timeout": 10,
                    "extra_tags": {
                        "datacenter": "us-west-1",
                        "team": "backend",
                    },
                },
                "file": {
                    "enabled": True,
                    "rotation": False,
                    "max_size_mb": 100,
                    "backup_count": 5,
                },
            },
        }

        output_path = Path(output_path)
        try:
            with open(output_path, "w") as f:
                json.dump(sample_config, f, indent=2, sort_keys=True)
            print(f"✅ Sample configuration created: {output_path}")
        except Exception as e:
            raise ConfigurationError(
                f"Failed to create sample configuration: {e}"
            )


# Convenience function for quick configuration loading
def load_config(
    config_file: Optional[Union[str, Path]] = None, **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to load configuration.

    Args:
        config_file: Path to JSON configuration file
        **kwargs: Runtime configuration parameters

    Returns:
        Loaded and validated configuration dictionary
    """
    loader = ConfigLoader(config_file)
    return loader.load_config(**kwargs)
