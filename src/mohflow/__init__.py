from .logger.base import MohflowLogger
from .exceptions import MohflowError, ConfigurationError
from .config_loader import ConfigLoader
from .context.enrichment import RequestContext, with_request_context
from .context.correlation import CorrelationContext, with_correlation_id
from .auto_config import detect_environment, auto_configure
from .templates import TemplateManager

__version__ = "0.1.3"


def get_logger(
    service: str, enable_mohnitor: bool = False, **kwargs
) -> MohflowLogger:
    """
    Get MohFlow logger instance with optional Mohnitor integration.

    Args:
        service: Service name for logging
        enable_mohnitor: Enable Mohnitor log viewer integration
        **kwargs: Additional MohFlow logger configuration

    Returns:
        Configured MohflowLogger instance
    """
    # Create logger
    logger = MohflowLogger.get_logger(service, **kwargs)

    # Enable Mohnitor if requested
    if enable_mohnitor:
        try:
            from .devui.mohnitor import enable_mohnitor as enable_mohnitor_func

            enable_mohnitor_func(
                service,
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k.startswith("mohnitor_")
                },
            )
        except ImportError:
            print(
                "⚠️  Mohnitor not available. Install with: pip install mohflow[mohnitor]"
            )
        except Exception as e:
            print(f"⚠️  Failed to enable Mohnitor: {e}")

    return logger


__all__ = [
    "MohflowLogger",
    "get_logger",
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
