"""
Advanced framework and application detection for intelligent auto-configuration.

This module detects popular Python frameworks and adjusts logging configuration
automatically for optimal integration and performance.
"""

import os
import importlib.util
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging


@dataclass
class FrameworkInfo:
    """Information about detected framework and its configuration needs."""

    name: str
    version: Optional[str] = None
    is_async: bool = False
    has_middleware_support: bool = False
    default_log_level: str = "INFO"
    recommended_formatter: str = "structured"
    supports_request_id: bool = False
    supports_correlation: bool = False
    integration_notes: Optional[str] = None
    custom_config: Optional[Dict[str, Any]] = None


@dataclass
class ApplicationInfo:
    """Information about the application architecture and deployment."""

    app_type: str = "unknown"  # web, api, worker, cli, library
    frameworks: List[FrameworkInfo] = None
    has_database: bool = False
    has_cache: bool = False
    has_message_queue: bool = False
    has_external_apis: bool = False
    uses_async: bool = False
    deployment_type: str = "unknown"  # monolith, microservice, serverless

    def __post_init__(self):
        if self.frameworks is None:
            self.frameworks = []


class FrameworkDetector:
    """
    Intelligent framework detection and configuration optimization.

    Detects popular Python frameworks and configures MohFlow for optimal
    integration with framework-specific logging patterns and middleware.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._framework_cache: Optional[List[FrameworkInfo]] = None
        self._app_info_cache: Optional[ApplicationInfo] = None

    def detect_frameworks(
        self, force_refresh: bool = False
    ) -> List[FrameworkInfo]:
        """
        Detect all frameworks in use by the application.

        Args:
            force_refresh: Force re-detection even if cached

        Returns:
            List of detected FrameworkInfo objects
        """
        if self._framework_cache is not None and not force_refresh:
            return self._framework_cache

        frameworks = []

        # Web Frameworks
        frameworks.extend(self._detect_web_frameworks())

        # Async Frameworks
        frameworks.extend(self._detect_async_frameworks())

        # API Frameworks
        frameworks.extend(self._detect_api_frameworks())

        # Background Task Frameworks
        frameworks.extend(self._detect_task_frameworks())

        # Database Frameworks
        frameworks.extend(self._detect_database_frameworks())

        # Testing Frameworks
        frameworks.extend(self._detect_testing_frameworks())

        # Deployment/Production Frameworks
        frameworks.extend(self._detect_production_frameworks())

        self._framework_cache = frameworks
        return frameworks

    def detect_application_type(self) -> ApplicationInfo:
        """
        Analyze the application to determine its type and architecture.

        Returns:
            ApplicationInfo with detected characteristics
        """
        if self._app_info_cache is not None:
            return self._app_info_cache

        frameworks = self.detect_frameworks()

        # Determine application type
        app_type = self._determine_app_type(frameworks)

        # Check for async usage
        uses_async = self._detect_async_usage(frameworks)

        # Check for external dependencies
        has_database = self._detect_database_usage()
        has_cache = self._detect_cache_usage()
        has_message_queue = self._detect_message_queue_usage()
        has_external_apis = self._detect_external_api_usage()

        # Determine deployment type
        deployment_type = self._determine_deployment_type(frameworks, app_type)

        app_info = ApplicationInfo(
            app_type=app_type,
            frameworks=frameworks,
            has_database=has_database,
            has_cache=has_cache,
            has_message_queue=has_message_queue,
            has_external_apis=has_external_apis,
            uses_async=uses_async,
            deployment_type=deployment_type,
        )

        self._app_info_cache = app_info
        return app_info

    def get_optimized_config(self) -> Dict[str, Any]:
        """
        Get optimized MohFlow configuration based on detected frameworks.

        Returns:
            Configuration dictionary optimized for detected frameworks
        """
        app_info = self.detect_application_type()
        config = {}

        # Base configuration based on app type
        config.update(self._get_app_type_config(app_info))

        # Framework-specific optimizations
        for framework in app_info.frameworks:
            if framework.custom_config:
                config.update(framework.custom_config)

        # Performance optimizations based on architecture
        config.update(self._get_performance_config(app_info))

        # Integration-specific settings
        config.update(self._get_integration_config(app_info))

        return config

    # Web Framework Detection
    def _detect_web_frameworks(self) -> List[FrameworkInfo]:
        """Detect web frameworks like Flask, Django, FastAPI."""
        frameworks = []

        # Flask
        if self._is_module_available("flask"):
            flask_info = FrameworkInfo(
                name="flask",
                version=self._get_module_version("flask"),
                has_middleware_support=True,
                supports_request_id=True,
                supports_correlation=True,
                recommended_formatter="structured",
                integration_notes="Use Flask request context for log correlation",
                custom_config={
                    "enable_context_enrichment": True,
                    "context_enrichment": {
                        "include_request_context": True,
                        "include_timestamp": True,
                    },
                },
            )
            frameworks.append(flask_info)

        # Django
        if self._is_module_available("django"):
            django_info = FrameworkInfo(
                name="django",
                version=self._get_module_version("django"),
                has_middleware_support=True,
                supports_request_id=True,
                supports_correlation=True,
                default_log_level="INFO",
                recommended_formatter="structured",
                integration_notes="Integrates with Django's logging configuration",
                custom_config={
                    "enable_context_enrichment": True,
                    "context_enrichment": {
                        "include_request_context": True,
                        "custom_fields": {
                            "django_version": self._get_module_version(
                                "django"
                            )
                        },
                    },
                },
            )
            frameworks.append(django_info)

        return frameworks

    def _detect_async_frameworks(self) -> List[FrameworkInfo]:
        """Detect async frameworks like FastAPI, aiohttp, Sanic."""
        frameworks = []

        # FastAPI
        if self._is_module_available("fastapi"):
            fastapi_info = FrameworkInfo(
                name="fastapi",
                version=self._get_module_version("fastapi"),
                is_async=True,
                has_middleware_support=True,
                supports_request_id=True,
                supports_correlation=True,
                recommended_formatter="fast",  # High performance for async
                integration_notes="Use async-safe handlers for best performance",
                custom_config={
                    "async_handlers": True,
                    "formatter_type": "fast",
                    "enable_context_enrichment": True,
                    "context_enrichment": {
                        "include_request_context": True,
                        "custom_fields": {"framework": "fastapi"},
                    },
                },
            )
            frameworks.append(fastapi_info)

        # aiohttp
        if self._is_module_available("aiohttp"):
            aiohttp_info = FrameworkInfo(
                name="aiohttp",
                version=self._get_module_version("aiohttp"),
                is_async=True,
                has_middleware_support=True,
                supports_request_id=True,
                recommended_formatter="fast",
                integration_notes="Use aiohttp middleware for request correlation",
                custom_config={
                    "async_handlers": True,
                    "formatter_type": "fast",
                    "enable_context_enrichment": True,
                },
            )
            frameworks.append(aiohttp_info)

        # Sanic
        if self._is_module_available("sanic"):
            sanic_info = FrameworkInfo(
                name="sanic",
                version=self._get_module_version("sanic"),
                is_async=True,
                has_middleware_support=True,
                supports_request_id=True,
                recommended_formatter="fast",
                integration_notes="High-performance async web framework",
                custom_config={
                    "async_handlers": True,
                    "formatter_type": "fast",
                },
            )
            frameworks.append(sanic_info)

        return frameworks

    def _detect_api_frameworks(self) -> List[FrameworkInfo]:
        """Detect API frameworks and REST libraries."""
        frameworks = []

        # Flask-RESTful
        if self._is_module_available("flask_restful"):
            frameworks.append(
                FrameworkInfo(
                    name="flask_restful",
                    version=self._get_module_version("flask_restful"),
                    supports_correlation=True,
                    recommended_formatter="structured",
                    custom_config={"formatter_type": "structured"},
                )
            )

        # Django REST Framework
        if self._is_module_available("rest_framework"):
            frameworks.append(
                FrameworkInfo(
                    name="django_rest_framework",
                    version=self._get_module_version("djangorestframework"),
                    supports_correlation=True,
                    recommended_formatter="structured",
                    custom_config={
                        "formatter_type": "structured",
                        "enable_context_enrichment": True,
                    },
                )
            )

        return frameworks

    def _detect_task_frameworks(self) -> List[FrameworkInfo]:
        """Detect background task and queue frameworks."""
        frameworks = []

        # Celery
        if self._is_module_available("celery"):
            celery_info = FrameworkInfo(
                name="celery",
                version=self._get_module_version("celery"),
                supports_correlation=True,
                recommended_formatter="structured",
                integration_notes="Configure task-level correlation IDs",
                custom_config={
                    "formatter_type": "structured",
                    "enable_context_enrichment": True,
                    "context_enrichment": {
                        "custom_fields": {
                            "worker_type": "celery",
                            "task_correlation": True,
                        }
                    },
                },
            )
            frameworks.append(celery_info)

        # RQ (Redis Queue)
        if self._is_module_available("rq"):
            frameworks.append(
                FrameworkInfo(
                    name="rq",
                    version=self._get_module_version("rq"),
                    supports_correlation=True,
                    recommended_formatter="structured",
                    custom_config={
                        "formatter_type": "structured",
                        "enable_context_enrichment": True,
                    },
                )
            )

        return frameworks

    def _detect_database_frameworks(self) -> List[FrameworkInfo]:
        """Detect database and ORM frameworks."""
        frameworks = []

        # SQLAlchemy
        if self._is_module_available("sqlalchemy"):
            frameworks.append(
                FrameworkInfo(
                    name="sqlalchemy",
                    version=self._get_module_version("sqlalchemy"),
                    integration_notes="Enable SQL query logging correlation",
                    custom_config={
                        "enable_context_enrichment": True,
                        "context_enrichment": {
                            "custom_fields": {
                                "has_database": True,
                                "orm": "sqlalchemy",
                            }
                        },
                    },
                )
            )

        return frameworks

    def _detect_testing_frameworks(self) -> List[FrameworkInfo]:
        """Detect testing frameworks."""
        frameworks = []

        # pytest
        if self._is_module_available("pytest"):
            frameworks.append(
                FrameworkInfo(
                    name="pytest",
                    version=self._get_module_version("pytest"),
                    default_log_level="DEBUG",
                    recommended_formatter="development",
                    custom_config={
                        "formatter_type": "development",
                        "log_level": "DEBUG",
                        "console_logging": True,
                    },
                )
            )

        return frameworks

    def _detect_production_frameworks(self) -> List[FrameworkInfo]:
        """Detect production/deployment frameworks."""
        frameworks = []

        # Gunicorn
        if self._is_module_available("gunicorn"):
            frameworks.append(
                FrameworkInfo(
                    name="gunicorn",
                    version=self._get_module_version("gunicorn"),
                    integration_notes="WSGI server - optimize for multi-process logging",
                    custom_config={
                        "async_handlers": False,  # Gunicorn is sync
                        "formatter_type": "production",
                        "file_logging": True,
                    },
                )
            )

        # Uvicorn (ASGI)
        if self._is_module_available("uvicorn"):
            frameworks.append(
                FrameworkInfo(
                    name="uvicorn",
                    version=self._get_module_version("uvicorn"),
                    is_async=True,
                    integration_notes="ASGI server - use async handlers",
                    custom_config={
                        "async_handlers": True,
                        "formatter_type": "production",
                    },
                )
            )

        return frameworks

    def _determine_app_type(self, frameworks: List[FrameworkInfo]) -> str:
        """Determine application type from detected frameworks."""
        framework_names = {f.name.lower() for f in frameworks}

        # Web application
        web_frameworks = {"flask", "django", "fastapi", "aiohttp", "sanic"}
        if framework_names & web_frameworks:
            return "web"

        # API service
        api_frameworks = {"flask_restful", "django_rest_framework"}
        if framework_names & api_frameworks:
            return "api"

        # Background worker
        worker_frameworks = {"celery", "rq"}
        if framework_names & worker_frameworks:
            return "worker"

        # Testing
        if "pytest" in framework_names:
            return "test"

        # CLI application (check for Click, argparse, etc.)
        if self._is_module_available("click") or self._detect_cli_patterns():
            return "cli"

        return "library"  # Default for libraries or unknown

    def _detect_async_usage(self, frameworks: List[FrameworkInfo]) -> bool:
        """Check if application uses async/await patterns."""
        # Check frameworks
        for framework in frameworks:
            if framework.is_async:
                return True

        # Check for asyncio in the main module
        if self._is_module_available("asyncio"):
            # Could do more sophisticated detection here
            return True

        return False

    def _determine_deployment_type(
        self, frameworks: List[FrameworkInfo], app_type: str
    ) -> str:
        """Determine deployment architecture type."""
        framework_names = {f.name.lower() for f in frameworks}

        # Serverless indicators
        if os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv(
            "FUNCTIONS_WORKER_RUNTIME"
        ):
            return "serverless"

        # Microservice indicators
        microservice_indicators = [
            self._is_module_available("kubernetes"),
            os.getenv("KUBERNETES_SERVICE_HOST"),
            "fastapi" in framework_names,
            app_type in ["api", "worker"],
        ]
        if any(microservice_indicators):
            return "microservice"

        # Default to monolith
        return "monolith"

    def _detect_database_usage(self) -> bool:
        """Check if application uses databases."""
        db_modules = ["sqlalchemy", "pymongo", "psycopg2", "mysql", "sqlite3"]
        return any(self._is_module_available(module) for module in db_modules)

    def _detect_cache_usage(self) -> bool:
        """Check if application uses caching."""
        cache_modules = ["redis", "memcache", "pymemcache"]
        return any(
            self._is_module_available(module) for module in cache_modules
        )

    def _detect_message_queue_usage(self) -> bool:
        """Check if application uses message queues."""
        mq_modules = ["celery", "rq", "pika", "kafka"]
        return any(self._is_module_available(module) for module in mq_modules)

    def _detect_external_api_usage(self) -> bool:
        """Check if application makes external API calls."""
        api_modules = ["requests", "httpx", "aiohttp", "urllib3"]
        return any(self._is_module_available(module) for module in api_modules)

    def _detect_cli_patterns(self) -> bool:
        """Detect CLI application patterns."""
        # Check if main module has CLI patterns
        try:
            import __main__

            if hasattr(__main__, "__file__") and __main__.__file__:
                # Simple heuristic: check for argparse usage
                with open(__main__.__file__, "r") as f:
                    content = f.read()
                    return "argparse" in content or "click" in content
        except Exception:
            pass
        return False

    def _get_app_type_config(
        self, app_info: ApplicationInfo
    ) -> Dict[str, Any]:
        """Get configuration based on application type."""
        config = {}

        if app_info.app_type == "web":
            config.update(
                {
                    "formatter_type": "structured",
                    "enable_context_enrichment": True,
                    "context_enrichment": {
                        "include_request_context": True,
                        "include_timestamp": True,
                    },
                }
            )

        elif app_info.app_type == "api":
            config.update(
                {
                    "formatter_type": "structured",
                    "enable_context_enrichment": True,
                    "log_level": "INFO",
                }
            )

        elif app_info.app_type == "worker":
            config.update(
                {
                    "formatter_type": "production",
                    "file_logging": True,
                    "console_logging": False,
                }
            )

        elif app_info.app_type == "cli":
            config.update(
                {
                    "formatter_type": "development",
                    "console_logging": True,
                    "file_logging": False,
                    "log_level": "INFO",
                }
            )

        elif app_info.app_type == "test":
            config.update(
                {
                    "formatter_type": "development",
                    "console_logging": True,
                    "log_level": "DEBUG",
                }
            )

        return config

    def _get_performance_config(
        self, app_info: ApplicationInfo
    ) -> Dict[str, Any]:
        """Get performance optimizations based on app characteristics."""
        config = {}

        # Async optimization
        if app_info.uses_async:
            config["async_handlers"] = True
            config["formatter_type"] = "fast"

        # High-load optimization
        if app_info.deployment_type == "microservice":
            config.update(
                {"formatter_type": "production", "async_handlers": True}
            )

        return config

    def _get_integration_config(
        self, app_info: ApplicationInfo
    ) -> Dict[str, Any]:
        """Get integration-specific configuration."""
        config = {}

        # Database integration
        if app_info.has_database:
            if "context_enrichment" not in config:
                config["context_enrichment"] = {}
            config["context_enrichment"]["custom_fields"] = config[
                "context_enrichment"
            ].get("custom_fields", {})
            config["context_enrichment"]["custom_fields"][
                "has_database"
            ] = True

        # External API integration
        if app_info.has_external_apis:
            config["enable_context_enrichment"] = True
            if "context_enrichment" not in config:
                config["context_enrichment"] = {}
            config["context_enrichment"]["include_request_id"] = True

        return config

    # Utility methods
    def _is_module_available(self, module_name: str) -> bool:
        """Check if a module is available in the current environment."""
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            return False

    def _get_module_version(self, module_name: str) -> Optional[str]:
        """Get version of an installed module."""
        try:
            module = importlib.import_module(module_name)
            return getattr(module, "__version__", None)
        except ImportError:
            return None

    def get_framework_summary(self) -> Dict[str, Any]:
        """Get a summary of detected frameworks for debugging."""
        app_info = self.detect_application_type()

        return {
            "app_type": app_info.app_type,
            "deployment_type": app_info.deployment_type,
            "uses_async": app_info.uses_async,
            "frameworks": [
                {
                    "name": f.name,
                    "version": f.version,
                    "is_async": f.is_async,
                    "formatter": f.recommended_formatter,
                }
                for f in app_info.frameworks
            ],
            "capabilities": {
                "database": app_info.has_database,
                "cache": app_info.has_cache,
                "message_queue": app_info.has_message_queue,
                "external_apis": app_info.has_external_apis,
            },
        }


# Singleton instance for easy access
_framework_detector = FrameworkDetector()


# Convenience functions
def detect_frameworks(force_refresh: bool = False) -> List[FrameworkInfo]:
    """Detect all frameworks in use by the application."""
    return _framework_detector.detect_frameworks(force_refresh)


def detect_application_type() -> ApplicationInfo:
    """Detect application type and characteristics."""
    return _framework_detector.detect_application_type()


def get_framework_optimized_config() -> Dict[str, Any]:
    """Get optimized configuration based on detected frameworks."""
    return _framework_detector.get_optimized_config()


def get_framework_summary() -> Dict[str, Any]:
    """Get summary of detected frameworks and capabilities."""
    return _framework_detector.get_framework_summary()
