import logging
from typing import Optional, Dict, Any
from pathlib import Path
from pythonjsonlogger import json as jsonlogger
from mohflow.config import LogConfig
from mohflow.config_loader import ConfigLoader
from mohflow.handlers.loki import LokiHandler
from mohflow.context.enrichment import ContextEnricher, set_global_context
from mohflow.context.filters import SensitiveDataFilter
from mohflow.auto_config import auto_configure


class MohflowLogger:
    """Enhanced MohFlow logger with auto-configuration and context awareness"""

    def __init__(
        self,
        service_name: str,
        environment: str = "development",
        loki_url: Optional[str] = None,
        log_level: str = "INFO",
        console_logging: bool = True,
        file_logging: bool = False,
        log_file_path: Optional[str] = None,
        config_file: Optional[str] = None,
        enable_auto_config: bool = False,
        enable_context_enrichment: bool = True,
        enable_sensitive_data_filter: bool = True,
        **kwargs,
    ):
        # Load configuration from multiple sources
        config_dict = self._load_configuration(
            service_name=service_name,
            environment=environment,
            loki_url=loki_url,
            log_level=log_level,
            console_logging=console_logging,
            file_logging=file_logging,
            log_file_path=log_file_path,
            config_file=config_file,
            enable_auto_config=enable_auto_config,
            **kwargs,
        )

        # Create LogConfig from merged configuration
        self.config = LogConfig.from_dict(config_dict)

        # Initialize components
        self.context_enricher = None
        self.sensitive_filter = None

        if enable_context_enrichment:
            self.context_enricher = ContextEnricher(
                include_timestamp=config_dict.get(
                    "context_enrichment", {}
                ).get("include_timestamp", True),
                include_system_info=True,
                include_request_context=config_dict.get(
                    "context_enrichment", {}
                ).get("include_request_id", False),
                include_global_context=True,
            )

            # Set global context
            set_global_context(
                service_name=self.config.SERVICE_NAME,
                environment=self.config.ENVIRONMENT,
                **config_dict.get("context_enrichment", {}).get(
                    "custom_fields", {}
                ),
            )

        if enable_sensitive_data_filter:
            self.sensitive_filter = SensitiveDataFilter()

        # Setup logger
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
        extra["level"] = "INFO"
        self.logger.info(message, extra=extra)

    def error(self, message: str, exc_info: bool = True, **kwargs):
        """Log error message"""
        extra = self._prepare_extra(kwargs)
        extra["level"] = "ERROR"
        self.logger.error(message, exc_info=exc_info, extra=extra)

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        extra = self._prepare_extra(kwargs)
        extra["level"] = "WARNING"
        self.logger.warning(message, extra=extra)

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        extra = self._prepare_extra(kwargs)
        extra["level"] = "DEBUG"
        self.logger.debug(message, extra=extra)

    def _load_configuration(
        self,
        config_file: Optional[str] = None,
        enable_auto_config: bool = False,
        **params,
    ) -> Dict[str, Any]:
        """Load configuration from multiple sources with proper precedence"""
        # Load base configuration
        if config_file:
            loader = ConfigLoader(Path(config_file))
        else:
            loader = ConfigLoader()

        config_dict = loader.load_config(**params)

        # Apply auto-configuration if enabled
        if enable_auto_config:
            config_dict = auto_configure(config_dict)

        return config_dict

    def _prepare_extra(self, extra: dict) -> dict:
        """Prepare extra fields for logging with context enrichment and filtering"""
        enriched_extra = extra.copy()

        # Apply context enrichment
        if self.context_enricher:
            enriched_extra = self.context_enricher.enrich_log_record(
                enriched_extra
            )

        # Apply sensitive data filtering
        if self.sensitive_filter:
            enriched_extra = self.sensitive_filter.filter_log_record(
                enriched_extra
            )

        return enriched_extra

    def set_context(self, **context_fields):
        """Set global context fields for all future log messages"""
        set_global_context(**context_fields)

    def add_custom_enricher(self, field_name: str, enricher_func):
        """Add a custom field enricher"""
        if self.context_enricher:
            self.context_enricher.add_custom_enricher(
                field_name, enricher_func
            )

    def add_sensitive_field(self, field_name: str):
        """Add a field name to the sensitive data filter"""
        if self.sensitive_filter:
            self.sensitive_filter.add_sensitive_field(field_name)

    def get_environment_info(self) -> Dict[str, Any]:
        """Get information about the detected environment"""
        from mohflow.auto_config import get_environment_summary

        return get_environment_summary()

    @classmethod
    def from_config_file(
        cls, config_file: str, **overrides
    ) -> "MohflowLogger":
        """Create logger instance from JSON configuration file"""
        # Load config to get service name (required parameter)
        loader = ConfigLoader(Path(config_file))
        config_dict = loader.load_config(**overrides)

        return cls(
            service_name=config_dict["service_name"],
            config_file=config_file,
            **overrides,
        )

    @classmethod
    def with_auto_config(
        cls, service_name: str, **overrides
    ) -> "MohflowLogger":
        """Create logger instance with automatic environment configuration"""
        return cls(
            service_name=service_name, enable_auto_config=True, **overrides
        )
