from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from pathlib import Path
from mohflow.config_loader import ConfigLoader


class LogConfig(BaseSettings):
    """Logging configuration with JSON support"""

    SERVICE_NAME: str
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Loki settings
    LOKI_URL: Optional[str] = None

    # Console settings
    CONSOLE_LOGGING: bool = True

    # File settings
    FILE_LOGGING: bool = False
    LOG_FILE_PATH: Optional[str] = None

    class Config:
        env_prefix = "MOHFLOW_"

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "LogConfig":
        """Create LogConfig from dictionary (from JSON or other sources)"""
        # Map dictionary keys to expected field names
        pydantic_config = {
            "SERVICE_NAME": config_dict.get("service_name"),
            "ENVIRONMENT": config_dict.get("environment", "development"),
            "LOG_LEVEL": config_dict.get("log_level", "INFO"),
            "LOKI_URL": config_dict.get("loki_url"),
            "CONSOLE_LOGGING": config_dict.get("console_logging", True),
            "FILE_LOGGING": config_dict.get("file_logging", False),
            "LOG_FILE_PATH": config_dict.get("log_file_path"),
        }

        # Filter out None values
        pydantic_config = {
            k: v for k, v in pydantic_config.items() if v is not None
        }

        return cls(**pydantic_config)

    @classmethod
    def from_json_file(
        cls, config_file: Optional[Path] = None, **overrides
    ) -> "LogConfig":
        """Load configuration from JSON file with optional overrides"""
        loader = ConfigLoader(config_file)
        config_dict = loader.load_config(**overrides)
        return cls.from_dict(config_dict)
