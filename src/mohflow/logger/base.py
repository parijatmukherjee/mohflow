import logging
import time
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from pathlib import Path
from mohflow.config import LogConfig
from mohflow.formatters import OrjsonFormatter, FastJSONFormatter, StructuredFormatter
from mohflow.config_loader import ConfigLoader
from mohflow.handlers.loki import LokiHandler
from mohflow.context.enrichment import ContextEnricher, set_global_context
from mohflow.context.filters import SensitiveDataFilter
from mohflow.context.scoped_context import ContextualLogger
from mohflow.auto_config import auto_configure, get_intelligent_config
from mohflow.sampling import AdaptiveSampler, SamplingConfig, SamplingStrategy
from mohflow.metrics import AutoMetricsGenerator, create_web_service_metrics, create_database_metrics
from mohflow.types import (
    LogLevel, FormatterType, ExporterType, LogData, 
    OptimizationReport, FrameworkDetectionResult,
    LogFormatter, ContextEnricher as ContextEnricherProtocol,
    DataFilter, LogFilePath
)

# Privacy and PII detection (optional)
try:
    from mohflow.privacy import (
        PrivacyAwareFilter, PrivacyMode, PrivacyConfig,
        ComplianceReporter, ComplianceStandard,
        detect_pii, generate_privacy_report
    )
    HAS_PRIVACY = True
except ImportError:
    HAS_PRIVACY = False

# OpenTelemetry integration (optional)
try:
    from mohflow.opentelemetry import OpenTelemetryEnricher, setup_otel_logging
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

if TYPE_CHECKING:
    from mohflow.context.enrichment import ContextEnricher
    from mohflow.context.filters import SensitiveDataFilter


class MohflowLogger(ContextualLogger):
    """Enhanced MohFlow logger with auto-configuration and context awareness"""

    def __init__(
        self,
        service_name: Optional[str] = None,
        environment: Optional[str] = None,
        loki_url: Optional[str] = None,
        log_level: Optional[Union[LogLevel, str]] = None,
        console_logging: Optional[bool] = None,
        file_logging: Optional[bool] = None,
        log_file_path: Optional[LogFilePath] = None,
        config_file: Optional[LogFilePath] = None,
        enable_auto_config: bool = False,
        enable_context_enrichment: bool = True,
        enable_sensitive_data_filter: bool = True,
        formatter_type: FormatterType = "structured",
        async_handlers: bool = False,
        # Privacy and PII protection parameters
        enable_pii_detection: bool = False,
        privacy_mode: str = "intelligent",
        compliance_standards: Optional[List[str]] = None,
        # OpenTelemetry parameters
        enable_otel: bool = False,
        otel_service_version: Optional[str] = None,
        otel_exporter_type: ExporterType = "console",
        otel_endpoint: Optional[str] = None,
        otel_propagators: Optional[List[str]] = None,
        # Log sampling parameters
        enable_sampling: bool = False,
        sample_rate: float = 1.0,
        sampling_strategy: str = "random", 
        max_logs_per_second: Optional[int] = None,
        burst_limit: Optional[int] = None,
        adaptive_sampling: bool = False,
        level_sample_rates: Optional[Dict[str, float]] = None,
        # Auto-metrics parameters
        enable_auto_metrics: bool = False,
        metrics_config: str = "default",  # "default", "web_service", "database", "custom"
        export_prometheus: bool = False,
        **kwargs: Any,
    ) -> None:
        # Initialize ContextualLogger capabilities first
        super().__init__()
        
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
        self.formatter_type = formatter_type
        self.async_handlers = async_handlers

        # OpenTelemetry configuration
        self.enable_otel = enable_otel and HAS_OTEL
        self.otel_service_version = otel_service_version or "1.0.0"
        self.otel_exporter_type = otel_exporter_type
        self.otel_endpoint = otel_endpoint
        self.otel_propagators = otel_propagators

        # Initialize components with proper typing
        self.context_enricher: Optional['ContextEnricher'] = None
        self.sensitive_filter: Optional['SensitiveDataFilter'] = None
        self.otel_enricher: Optional[OpenTelemetryEnricher] = None

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

        # Initialize OpenTelemetry enricher
        if self.enable_otel:
            self.otel_enricher = OpenTelemetryEnricher(
                include_trace_id=True,
                include_span_id=True,
                include_baggage=True,
                include_service_info=True
            )
            
            # Setup OpenTelemetry tracing
            self._setup_otel_tracing()

        # Initialize privacy and PII detection
        self.privacy_filter = None
        self.compliance_reporter = None
        
        if enable_pii_detection and HAS_PRIVACY:
            # Parse privacy mode
            privacy_mode_enum = getattr(PrivacyMode, privacy_mode.upper(), PrivacyMode.INTELLIGENT)
            
            # Parse compliance standards
            compliance_standards_enum = []
            if compliance_standards:
                for standard in compliance_standards:
                    try:
                        standard_enum = getattr(ComplianceStandard, standard.upper())
                        compliance_standards_enum.append(standard_enum)
                    except AttributeError:
                        continue
            
            # Setup privacy configuration
            privacy_config = PrivacyConfig(
                mode=privacy_mode_enum,
                compliance_mode=compliance_standards[0] if compliance_standards else None
            )
            
            self.privacy_filter = PrivacyAwareFilter(privacy_config)
            
            # Setup compliance reporting if standards specified
            if compliance_standards_enum:
                self.compliance_reporter = ComplianceReporter(compliance_standards_enum)

        # Initialize log sampling
        self.sampler = None
        if enable_sampling:
            # Map string strategy to enum
            strategy_map = {
                'random': SamplingStrategy.RANDOM,
                'deterministic': SamplingStrategy.DETERMINISTIC,
                'adaptive': SamplingStrategy.ADAPTIVE,
                'rate_limited': SamplingStrategy.RATE_LIMITED,
                'burst_allowed': SamplingStrategy.BURST_ALLOWED
            }
            
            sampling_config = SamplingConfig(
                sample_rate=sample_rate,
                strategy=strategy_map.get(sampling_strategy, SamplingStrategy.RANDOM),
                max_logs_per_second=max_logs_per_second,
                burst_limit=burst_limit,
                enable_adaptive=adaptive_sampling,
                level_sample_rates=level_sample_rates or {}
            )
            self.sampler = AdaptiveSampler(sampling_config)

        # Initialize auto-metrics generation
        self.metrics_generator = None
        self.export_prometheus = export_prometheus
        if enable_auto_metrics:
            if metrics_config == "web_service":
                self.metrics_generator = create_web_service_metrics()
            elif metrics_config == "database":
                self.metrics_generator = create_database_metrics()
            else:  # "default" or "custom"
                self.metrics_generator = AutoMetricsGenerator(enable_default_metrics=True)

        # Setup logger
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Setup and configure logger"""
        logger = logging.getLogger(self.config.SERVICE_NAME)
        logger.setLevel(getattr(logging, self.config.LOG_LEVEL.upper()))

        # Prevent duplicate logs
        logger.handlers = []

        # Create formatter based on type
        formatter = self._create_formatter()

        # Add console handler
        if self.config.CONSOLE_LOGGING:
            if self.async_handlers:
                from mohflow.handlers.async_handlers import create_async_console_handler
                console_handler = create_async_console_handler()
            else:
                console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # Add file handler
        if self.config.FILE_LOGGING and self.config.LOG_FILE_PATH:
            if self.async_handlers:
                from mohflow.handlers.async_handlers import create_async_file_handler
                file_handler = create_async_file_handler(self.config.LOG_FILE_PATH)
            else:
                file_handler = logging.FileHandler(self.config.LOG_FILE_PATH)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            logger.addHandler(file_handler)

        # Add Loki handler
        if self.config.LOKI_URL:
            if self.async_handlers:
                from mohflow.handlers.async_handlers import create_async_loki_handler
                loki_handler = create_async_loki_handler(
                    url=self.config.LOKI_URL,
                    service_name=self.config.SERVICE_NAME,
                    environment=self.config.ENVIRONMENT,
                )
                loki_handler.setFormatter(formatter)
            else:
                loki_handler = LokiHandler.setup(
                    url=self.config.LOKI_URL,
                    service_name=self.config.SERVICE_NAME,
                    environment=self.config.ENVIRONMENT,
                    formatter=formatter,
                )
            logger.addHandler(loki_handler)

        return logger

    def _setup_otel_tracing(self) -> None:
        """Setup OpenTelemetry tracing configuration."""
        if not self.enable_otel or not HAS_OTEL:
            return
        
        try:
            success = setup_otel_logging(
                service_name=self.config.SERVICE_NAME,
                service_version=self.otel_service_version,
                endpoint=self.otel_endpoint,
                exporter_type=self.otel_exporter_type,
                resource_attributes={
                    "environment": self.config.ENVIRONMENT,
                }
            )
            
            if success:
                # Setup trace propagation if propagators specified
                if self.otel_propagators:
                    from mohflow.opentelemetry.propagators import setup_trace_propagation
                    setup_trace_propagation(self.otel_propagators)
                
        except Exception:
            # Silently fail if OpenTelemetry setup fails
            self.enable_otel = False
            self.otel_enricher = None

    def _create_formatter(self) -> logging.Formatter:
        """Create formatter based on configuration."""
        # Base formatter configuration
        formatter_config = {
            'static_fields': {
                'service': self.config.SERVICE_NAME,
                'environment': self.config.ENVIRONMENT,
            },
            'rename_fields': {
                'level': 'level',
                'logger': 'service_name',
            }
        }
        
        # Select formatter type
        if self.formatter_type == "fast":
            return FastJSONFormatter(**formatter_config)
        elif self.formatter_type == "production":
            from mohflow.formatters.structured_formatter import ProductionFormatter
            return ProductionFormatter(**formatter_config)
        elif self.formatter_type == "development":
            from mohflow.formatters.structured_formatter import DevelopmentFormatter
            return DevelopmentFormatter(**formatter_config)
        else:  # "structured" (default)
            return StructuredFormatter(**formatter_config)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message"""
        if self.sampler:
            result = self.sampler.should_sample(
                level="INFO",
                component=kwargs.get('component'),
                message=message
            )
            if not result.should_log:
                return
        
        # Process metrics before logging
        self._process_metrics(message, "INFO", **kwargs)
                
        extra = self._prepare_extra(kwargs)
        extra["level"] = "INFO"
        self.logger.info(message, extra=extra)

    def error(self, message: str, exc_info: bool = True, **kwargs: Any) -> None:
        """Log error message"""
        if self.sampler:
            result = self.sampler.should_sample(
                level="ERROR",
                component=kwargs.get('component'),
                message=message
            )
            if not result.should_log:
                return
        
        # Process metrics before logging
        self._process_metrics(message, "ERROR", **kwargs)
                
        extra = self._prepare_extra(kwargs)
        extra["level"] = "ERROR"
        self.logger.error(message, exc_info=exc_info, extra=extra)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message"""
        if self.sampler:
            result = self.sampler.should_sample(
                level="WARNING",
                component=kwargs.get('component'),
                message=message
            )
            if not result.should_log:
                return
        
        # Process metrics before logging
        self._process_metrics(message, "WARNING", **kwargs)
                
        extra = self._prepare_extra(kwargs)
        extra["level"] = "WARNING"
        self.logger.warning(message, extra=extra)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message"""
        if self.sampler:
            result = self.sampler.should_sample(
                level="DEBUG",
                component=kwargs.get('component'),
                message=message
            )
            if not result.should_log:
                return
        
        # Process metrics before logging
        self._process_metrics(message, "DEBUG", **kwargs)
                
        extra = self._prepare_extra(kwargs)
        extra["level"] = "DEBUG"
        self.logger.debug(message, extra=extra)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message"""
        if self.sampler:
            result = self.sampler.should_sample(
                level="CRITICAL",
                component=kwargs.get('component'),
                message=message
            )
            if not result.should_log:
                return
        
        # Process metrics before logging
        self._process_metrics(message, "CRITICAL", **kwargs)
                
        extra = self._prepare_extra(kwargs)
        extra["level"] = "CRITICAL"
        self.logger.critical(message, extra=extra)

    def _load_configuration(
        self,
        config_file: Optional[LogFilePath] = None,
        enable_auto_config: bool = False,
        **params: Any,
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
            # Use intelligent config that includes framework detection
            # Extract service_name from params or config_dict
            svc_name = params.get('service_name') or config_dict.get('service_name')
            config_dict = get_intelligent_config(config_dict, svc_name)
        
        return config_dict

    def _prepare_extra(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare extra fields for logging with enrichment and filtering"""
        enriched_extra = extra.copy()

        # Apply context enrichment
        if self.context_enricher:
            enriched_extra = self.context_enricher.enrich_dict(enriched_extra)

        # Apply OpenTelemetry trace enrichment
        if self.otel_enricher:
            enriched_extra = self.otel_enricher.enrich_dict(enriched_extra)

        # Apply sensitive data filtering
        if self.sensitive_filter:
            enriched_extra = self.sensitive_filter.filter_log_record(
                enriched_extra
            )

        return enriched_extra
    
    def _process_metrics(self, message: str, level: str, **kwargs: Any) -> None:
        """Process log record for auto-metrics generation."""
        if not self.metrics_generator:
            return
            
        # Create log record for metrics processing
        log_record = {
            'message': message,
            'level': level,
            'timestamp': time.time(),
            'service_name': self.config.SERVICE_NAME,
            **kwargs
        }
        
        try:
            # Extract and process metrics
            metrics = self.metrics_generator.process_log_record(log_record)
            
            # Optional: Log metrics extraction results (debug mode)
            if len(metrics) > 0 and kwargs.get('debug_metrics', False):
                metric_names = [m.name for m in metrics]
                self.debug(f"Extracted metrics: {metric_names}", extracted_metrics=metric_names)
        except Exception as e:
            # Don't let metrics processing break logging
            pass

    def set_context(self, **context_fields: Any) -> None:
        """Set global context fields for all future log messages"""
        set_global_context(**context_fields)

    def add_custom_enricher(self, field_name: str, enricher_func: Any) -> None:
        """Add a custom field enricher"""
        if self.context_enricher:
            self.context_enricher.add_custom_enricher(
                field_name, enricher_func
            )

    def add_sensitive_field(self, field_name: str) -> None:
        """Add a field name to the sensitive data filter"""
        if self.sensitive_filter:
            self.sensitive_filter.add_sensitive_field(field_name)

    def get_environment_info(self) -> Dict[str, Any]:
        """Get information about the detected environment"""
        from mohflow.auto_config import get_environment_summary

        return get_environment_summary()

    def get_trace_context(self) -> Dict[str, Any]:
        """Get current OpenTelemetry trace context information."""
        if not self.enable_otel or not self.otel_enricher:
            return {}
        
        from mohflow.opentelemetry import get_current_trace_context
        trace_context = get_current_trace_context()
        return trace_context.to_dict()

    def start_trace(self, operation_name: str = "log_operation") -> Optional[Any]:
        """Start a new trace span for log correlation."""
        if not self.enable_otel:
            return None
        
        from mohflow.opentelemetry import trace_correlation_middleware
        return trace_correlation_middleware(operation_name)

    def log_with_trace(
        self, 
        level: str, 
        message: str, 
        operation_name: Optional[str] = None, 
        **kwargs: Any
    ) -> None:
        """Log a message within a trace span context."""
        if not self.enable_otel:
            # Fall back to regular logging
            getattr(self, level.lower(), self.info)(message, **kwargs)
            return
        
        operation_name = operation_name or f"{level.lower()}_operation"
        
        with self.start_trace(operation_name):
            getattr(self, level.lower(), self.info)(message, **kwargs)

    def get_sampling_stats(self) -> Optional[Dict[str, Any]]:
        """Get current sampling statistics."""
        if not self.sampler:
            return None
        return self.sampler.get_stats()
    
    def update_sampling_config(self, **config_updates: Any) -> None:
        """Update sampling configuration at runtime."""
        if not self.sampler:
            return
            
        # Update the sampler's config
        config = self.sampler.config
        for key, value in config_updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    def reset_sampling_stats(self) -> None:
        """Reset sampling statistics."""
        if self.sampler:
            self.sampler.reset()
    
    def get_metrics_summary(self) -> Optional[Dict[str, Any]]:
        """Get summary of auto-generated metrics."""
        if not self.metrics_generator:
            return None
        return self.metrics_generator.get_metrics_summary()
    
    def get_error_rates(self, time_window_seconds: int = 300) -> Dict[str, float]:
        """Get error rates from auto-generated metrics."""
        if not self.metrics_generator:
            return {}
        return self.metrics_generator.get_error_rate(time_window_seconds)
    
    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Get latency statistics from auto-generated metrics."""
        if not self.metrics_generator:
            return {}
        return self.metrics_generator.get_latency_stats()
    
    def export_prometheus_metrics(self) -> Optional[str]:
        """Export metrics in Prometheus format."""
        if not self.metrics_generator:
            return None
        return self.metrics_generator.export_prometheus_metrics()
    
    def reset_metrics(self) -> None:
        """Reset all auto-generated metrics."""
        if self.metrics_generator:
            self.metrics_generator.reset_metrics()

    @classmethod
    def from_config_file(
        cls, config_file: LogFilePath, **overrides: Any
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
        cls, service_name: str, **overrides: Any
    ) -> "MohflowLogger":
        """Create logger instance with automatic environment configuration"""
        return cls(
            service_name=service_name, enable_auto_config=True, **overrides
        )

    @classmethod
    def fast(cls, service_name: str, **overrides: Any) -> "MohflowLogger":
        """Create high-performance logger optimized for throughput."""
        return cls(
            service_name=service_name,
            formatter_type="fast",
            enable_context_enrichment=False,
            enable_sensitive_data_filter=False,
            **overrides
        )

    @classmethod
    def production(cls, service_name: str, **overrides: Any) -> "MohflowLogger":
        """Create production-optimized logger with essential features."""
        return cls(
            service_name=service_name,
            formatter_type="production",
            enable_auto_config=True,
            **overrides
        )

    @classmethod
    def development(cls, service_name: str, **overrides: Any) -> "MohflowLogger":
        """Create development logger with full context and readable output."""
        return cls(
            service_name=service_name,
            formatter_type="development",
            log_level="DEBUG",
            **overrides
        )

    @classmethod
    def with_tracing(
        cls,
        service_name: str,
        service_version: str = "1.0.0",
        exporter_type: ExporterType = "console",
        endpoint: Optional[str] = None,
        **overrides: Any
    ) -> "MohflowLogger":
        """Create logger with OpenTelemetry distributed tracing enabled."""
        return cls(
            service_name=service_name,
            enable_otel=True,
            otel_service_version=service_version,
            otel_exporter_type=exporter_type,
            otel_endpoint=endpoint,
            otel_propagators=["tracecontext", "baggage"],
            **overrides
        )

    @classmethod
    def microservice(
        cls,
        service_name: str,
        service_version: str = "1.0.0",
        otlp_endpoint: Optional[str] = None,
        **overrides: Any
    ) -> "MohflowLogger":
        """Create microservice-optimized logger with tracing and production settings."""
        return cls(
            service_name=service_name,
            formatter_type="production",
            enable_otel=True,
            otel_service_version=service_version,
            otel_exporter_type="otlp",
            otel_endpoint=otlp_endpoint,
            otel_propagators=["tracecontext", "baggage", "b3"],
            enable_auto_config=True,
            **overrides
        )

    @classmethod
    def cloud_native(
        cls,
        service_name: str,
        service_version: str = "1.0.0",
        **overrides
    ) -> "MohflowLogger":
        """Create cloud-native logger with environment-based configuration."""
        return cls(
            service_name=service_name,
            formatter_type="production",
            enable_otel=True,
            otel_service_version=service_version,
            otel_exporter_type="otlp",  # Will use env vars for configuration
            otel_propagators=["tracecontext", "baggage"],
            enable_auto_config=True,
            async_handlers=True,
            **overrides
        )

    @classmethod
    def smart(cls, service_name: str, **overrides: Any) -> "MohflowLogger":
        """
        Create smart logger with automatic framework detection and optimization.
        
        This factory method automatically detects your application's frameworks
        and configures the logger for optimal performance and integration.
        """
        return cls(
            service_name=service_name,
            enable_auto_config=True,  # This now uses intelligent config
            **overrides
        )

    @classmethod
    def auto_optimized(
        cls,
        service_name: str,
        enable_tracing: bool = True,
        **overrides: Any
    ) -> "MohflowLogger":
        """
        Create automatically optimized logger based on detected environment and frameworks.
        
        This is the most intelligent factory method that:
        - Detects your frameworks (Flask, FastAPI, Django, etc.)
        - Optimizes formatter and handlers for your app type
        - Configures tracing if requested
        - Sets up environment-specific defaults
        """
        config = dict(overrides)
        config["enable_auto_config"] = True
        config["enable_otel"] = enable_tracing
        
        if enable_tracing:
            config["otel_exporter_type"] = "console"
            config["otel_propagators"] = ["tracecontext", "baggage"]
        
        return cls(
            service_name=service_name,
            **config
        )
    
    # Missing factory methods from improvement plan
    @classmethod
    def get_logger(cls, name: str, **kwargs: Any) -> "MohflowLogger":
        """
        Get logger instance following standard logging pattern.
        
        This method follows the familiar logging.getLogger(name) pattern
        that developers expect from Python's standard logging library.
        
        Args:
            name: Logger name (used as service_name)
            **kwargs: Additional configuration options
            
        Returns:
            MohflowLogger instance configured for the given name
        """
        return cls.smart(service_name=name, **kwargs)
    
    @classmethod
    def create(cls, service_name: str, **kwargs: Any) -> "MohflowLogger":
        """
        Create logger with simplified, clear API.
        
        This is a straightforward factory method that emphasizes
        clarity and simplicity in logger creation.
        
        Args:
            service_name: Name of the service/application
            **kwargs: Configuration options
            
        Returns:
            MohflowLogger instance with intelligent defaults
        """
        return cls.smart(service_name=service_name, **kwargs)
    
    @classmethod
    def for_service(cls, service_name: str, **kwargs: Any) -> "MohflowLogger":
        """
        Create logger specifically for a service with clear intent.
        
        This factory method makes the intent explicit - creating a logger
        that's optimized for service-level logging with appropriate defaults.
        
        Args:
            service_name: Name of the service
            **kwargs: Additional configuration
            
        Returns:
            Service-optimized MohflowLogger instance
        """
        # For services, we want production-ready defaults
        service_config = {
            'enable_auto_config': True,
            'enable_context_enrichment': True,
            'formatter_type': 'production'
        }
        service_config.update(kwargs)
        
        return cls(service_name=service_name, **service_config)

    def get_framework_info(self) -> Dict[str, Any]:
        """Get information about detected frameworks and recommendations."""
        from mohflow.auto_config import get_framework_recommendations
        return get_framework_recommendations()

    def get_optimization_report(self) -> OptimizationReport:
        """Get a report on current configuration optimizations."""
        from mohflow.auto_config import get_environment_summary
        
        env_summary = get_environment_summary()
        framework_info = self.get_framework_info()
        
        return {
            "current_config": {
                "formatter_type": self.formatter_type,
                "async_handlers": self.async_handlers,
                "enable_otel": self.enable_otel,
                "service_name": self.config.SERVICE_NAME,
                "environment": self.config.ENVIRONMENT
            },
            "environment": env_summary,
            "framework_recommendations": dict(framework_info),
            "optimization_tips": self._generate_optimization_tips(framework_info)
        }

    def _generate_optimization_tips(self, framework_info: Dict[str, Any]) -> List[str]:
        """Generate optimization tips based on current config and detected frameworks."""
        tips = []
        
        # Framework-specific tips
        if framework_info.get("uses_async", False) and not self.async_handlers:
            tips.append("Consider enabling async_handlers=True for better async performance")
        
        if framework_info.get("app_type") == "api" and self.formatter_type != "fast":
            tips.append("Consider using formatter_type='fast' for high-throughput API services")
        
        if framework_info.get("app_type") == "web" and not self.enable_otel:
            tips.append("Consider enabling tracing for better request correlation in web apps")
        
        # Environment-specific tips
        if self.config.ENVIRONMENT == "production" and self.config.LOG_LEVEL == "DEBUG":
            tips.append("Consider using log_level='INFO' or higher in production")
        
        if self.config.ENVIRONMENT == "development" and not self.config.CONSOLE_LOGGING:
            tips.append("Consider enabling console_logging=True for development")
        
        return tips
