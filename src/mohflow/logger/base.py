import logging
from typing import Optional
from pythonjsonlogger import json as jsonlogger
from ..config import LogConfig
from ..exceptions import ConfigurationError
from ..handlers.loki import LokiHandler


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
        log_file_path: Optional[str] = None,
    ):
        # Check file logging configuration first
        if file_logging and not log_file_path:
            raise ConfigurationError(
                "LOG_FILE_PATH must be set when FILE_LOGGING is enabled"
            )

        # Validate log level before setting
        try:
            getattr(logging, log_level.upper())
        except AttributeError:
            raise ValueError(f"Invalid log level: {log_level}")

        self.config = LogConfig(
            SERVICE_NAME=service_name,
            ENVIRONMENT=environment,
            LOKI_URL=loki_url,
            LOG_LEVEL=log_level,
            CONSOLE_LOGGING=console_logging,
            FILE_LOGGING=file_logging,
            LOG_FILE_PATH=log_file_path,
        )

        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup and configure logger"""
        logger = logging.getLogger(self.config.SERVICE_NAME)
        logger.setLevel(getattr(logging, self.config.LOG_LEVEL.upper()))

        # Prevent duplicate logs
        logger.handlers = []

        # Create formatter
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(level_name)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "level_name": "level",
                "name": "service_name",
            },
            timestamp=True,
        )

        # Add console handler
        if self.config.CONSOLE_LOGGING:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # Add file handler
        if self.config.FILE_LOGGING and self.config.LOG_FILE_PATH:
            file_handler = logging.FileHandler(self.config.LOG_FILE_PATH)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            logger.addHandler(file_handler)

        # Add Loki handler
        if self.config.LOKI_URL:
            loki_handler = LokiHandler.setup(
                url=self.config.LOKI_URL,
                service_name=self.config.SERVICE_NAME,
                environment=self.config.ENVIRONMENT,
                formatter=formatter,
            )
            logger.addHandler(loki_handler)

        return logger

    def info(self, message: str, **kwargs):
        """Log info message"""
        extra = self._prepare_extra(kwargs)
        self.logger.info(message, extra=extra)

    def error(self, message: str, exc_info: bool = True, **kwargs):
        """Log error message"""
        self.logger.error(
            message, exc_info=exc_info, extra=self._prepare_extra(kwargs)
        )

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(message, extra=self._prepare_extra(kwargs))

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(message, extra=self._prepare_extra(kwargs))

    def _prepare_extra(self, extra: dict) -> dict:
        """Prepare extra fields for logging"""
        return extra
