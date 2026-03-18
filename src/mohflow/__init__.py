import warnings

from .logger.base import MohflowLogger
from .exceptions import MohflowError, ConfigurationError
from .config_loader import ConfigLoader
from .context.enrichment import RequestContext, with_request_context
from .context.correlation import CorrelationContext, with_correlation_id
from .auto_config import detect_environment, auto_configure
from .templates import TemplateManager
from .context_api import bind_context, unbind_context, clear_context

__version__ = "1.1.2"


class _LazyLog:
    """Lazy proxy for the zero-config log singleton.

    Defers MohflowLogger creation until first attribute access, so
    ``from mohflow import log`` is side-effect-free at import time.
    Smart defaults: auto-detect environment, INFO level, console output.
    """

    _instance = None

    def _get_logger(self):
        if _LazyLog._instance is None:
            _LazyLog._instance = MohflowLogger(
                service_name="app",
                log_level="INFO",
                console_logging=True,
                file_logging=False,
                enable_context_enrichment=True,
                enable_sensitive_data_filter=True,
                formatter_type="structured",
            )
        return _LazyLog._instance

    def __getattr__(self, name):
        return getattr(self._get_logger(), name)

    def __repr__(self):
        if _LazyLog._instance is None:
            return "<mohflow.log (not yet initialized)>"
        return repr(_LazyLog._instance)


log = _LazyLog()


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
            warnings.warn(
                "Mohnitor not available. Install with: "
                "pip install mohflow[mohnitor]",
                stacklevel=2,
            )
        except Exception as e:
            warnings.warn(
                f"Failed to enable Mohnitor: {e}",
                stacklevel=2,
            )

    return logger


__all__ = [
    "MohflowLogger",
    "get_logger",
    "log",
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
    "bind_context",
    "unbind_context",
    "clear_context",
]
