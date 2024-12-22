import logging
import logging_loki
from ..exceptions import ConfigurationError
from typing import Dict, Any

class LokiHandler:
    @staticmethod
    def setup(
        url: str,
        service_name: str,
        environment: str,
        formatter: logging.Formatter,
        extra_tags: Dict[str, Any] = None,
    ) -> logging.Handler:
        """Setup Loki handler with configuration"""
        try:
            tags = {
                "service": service_name,
                "environment": environment,
            }
            if extra_tags:
                tags.update(extra_tags)

            handler = logging_loki.LokiHandler(
                url=url,
                tags=tags,
                version="1",
            )
            handler.setFormatter(formatter)
            return handler
        except Exception as e:
            raise ConfigurationError(
                f"Failed to setup Loki logging: {str(e)}"
            )