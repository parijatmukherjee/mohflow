from .logger.base import MohflowLogger
from .exceptions import MohflowError, ConfigurationError
from .config_loader import ConfigLoader
from .context.enrichment import RequestContext, with_request_context
from .context.correlation import CorrelationContext, with_correlation_id
from .auto_config import detect_environment, auto_configure
from .templates import TemplateManager

__version__ = "0.1.3"

__all__ = [
    "MohflowLogger",
    "MohflowError",
    "ConfigurationError",
    "ConfigLoader",
    "RequestContext",
    "with_request_context",
    "CorrelationContext",
    "with_correlation_id",
    "detect_environment",
    "auto_configure",
    "TemplateManager",
]
