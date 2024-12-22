from typing import Dict, Any, Optional
from pydantic import BaseSettings, validator


class LogConfig(BaseSettings):
    """Logging configuration"""
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