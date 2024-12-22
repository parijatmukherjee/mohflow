import logging
import sys
from datetime import datetime
from typing import Optional, Dict, Any
import logging_loki
from pythonjsonlogger import json as jsonlogger
from ..config import LogConfig
from ..exceptions import ConfigurationError


class MohflowLogger:
    """Main logger class for Mohflow"""

    def __init__(
            self,
            service_name: str,
            environment: str = "development",
            loki_url: Optional[str] = None,
            log_level: str = "INFO",
            console_logging: bool = True,
            file_logging: bool = False,
            log_file_path: Optional[str] = None
    ):
        self.config = LogConfig(
            SERVICE_NAME=service_name,
            ENVIRONMENT=environment,
            LOKI_URL=loki_url,
            LOG_LEVEL=log_level,
            CONSOLE_LOGGING=console_logging,
            FILE_LOGGING=file_logging,
            LOG_FILE_PATH=log_file_path
        )

        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup and configure logger"""
        logger = logging.getLogger(self.config.SERVICE_NAME)
        logger.setLevel(getattr(logging, self.config.LOG_LEVEL.upper()))

        # Prevent duplicate logs
        logger.handlers = []

        # Create formatter
        formatter = self._create_json_formatter()

        # Add console handler
        if self.config.CONSOLE_LOGGING:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # Add Loki handler
        if self.config.LOKI_URL:
            try:
                loki_handler = logging_loki.LokiHandler(
                    url=self.config.LOKI_URL,
                    tags={
                        "service": self.config.SERVICE_NAME,
                        "environment": self.config.ENVIRONMENT
                    },
                    version="1"
                )
                loki_handler.setFormatter(formatter)
                logger.addHandler(loki_handler)
            except Exception as e:
                raise ConfigurationError(f"Failed to setup Loki logging: {str(e)}")

        # Add file handler
        if self.config.FILE_LOGGING:
            if not self.config.LOG_FILE_PATH:
                raise ConfigurationError("LOG_FILE_PATH must be set when FILE_LOGGING is enabled")
            file_handler = logging.FileHandler(self.config.LOG_FILE_PATH)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        return logger

    def _create_json_formatter(self) -> jsonlogger.JsonFormatter:
        """Create JSON formatter for structured logging"""
        return jsonlogger.JsonFormatter(
            fmt="%(timestamp)s %(level)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    def info(self, message: str, **kwargs):
        """Log info message"""
        self.logger.info(message, extra=self._prepare_extra(kwargs))

    def error(self, message: str, exc_info: bool = True, **kwargs):
        """Log error message"""
        self.logger.error(message, exc_info=exc_info, extra=self._prepare_extra(kwargs))

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(message, extra=self._prepare_extra(kwargs))

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(message, extra=self._prepare_extra(kwargs))

    def _prepare_extra(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare extra fields for logging"""
        return {
            **extra,
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.config.SERVICE_NAME,
            "environment": self.config.ENVIRONMENT
        }