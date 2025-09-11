"""
Auto-configuration module for MohFlow.
Detects environment and configures logging based on deployment context.
"""

import os
import socket
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

from mohflow.static_config import (
    CLOUD_PROVIDERS,
    CONTAINER_DETECTION,
    Environment,
    DEFAULT_PORTS,
)


@dataclass
class EnvironmentInfo:
    """Information about the detected environment"""

    environment_type: str
    cloud_provider: Optional[str] = None
    container_runtime: Optional[str] = None
    orchestrator: Optional[str] = None
    region: Optional[str] = None
    instance_id: Optional[str] = None
    runtime: Optional[str] = None
    project_id: Optional[str] = None
    namespace: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class AutoConfigurator:
    """
    Automatic configuration based on environment detection.
    Detects deployment context and applies appropriate logging configurations.
    """

    def __init__(self, env_prefix: str = "MOHFLOW_"):
        self._logger = logging.getLogger(__name__)
        self.env_prefix = env_prefix
        self._env_info: Optional[EnvironmentInfo] = None

    def detect_environment(self) -> EnvironmentInfo:
        """
        Detect deployment environment and return environment information.

        Returns:
            EnvironmentInfo with detected environment details
        """
        if self._env_info is not None:
            return self._env_info

        environment_type = self._detect_environment_type()
        cloud_provider = self._detect_cloud_provider()
        container_runtime = self._detect_container_runtime()
        orchestrator = self._detect_orchestrator()
        region = self._detect_region(cloud_provider)
        instance_id = self._detect_instance_id(cloud_provider)
        runtime = self._detect_runtime(cloud_provider)
        project_id = self._detect_project_id(cloud_provider)
        namespace = self._detect_namespace(orchestrator)
        metadata = self._collect_metadata(
            cloud_provider, container_runtime, orchestrator
        )

        self._env_info = EnvironmentInfo(
            environment_type=environment_type,
            cloud_provider=cloud_provider,
            container_runtime=container_runtime,
            orchestrator=orchestrator,
            region=region,
            instance_id=instance_id,
            runtime=runtime,
            project_id=project_id,
            namespace=namespace,
            metadata=metadata,
        )

        return self._env_info

    def get_auto_config(
        self,
        env_info: Optional[EnvironmentInfo] = None,
        service_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get automatic configuration based on environment detection"""
        if env_info is None:
            env_info = self.detect_environment()

        config = {
            "environment": env_info.environment_type,
            "cloud_provider": env_info.cloud_provider,
        }

        if service_name:
            config["service_name"] = service_name

        # Add cloud-specific configurations
        if env_info.cloud_provider == "aws":
            config["region"] = env_info.region
        elif env_info.cloud_provider == "gcp":
            config["project_id"] = env_info.project_id

        if env_info.orchestrator == "kubernetes":
            config["namespace"] = env_info.namespace

        return config

    def get_config(self) -> Dict[str, Any]:
        """Alias for get_auto_config for backward compatibility"""
        return self.get_auto_config()

    def get_environment_info(self) -> EnvironmentInfo:
        """Get environment information"""
        return self.detect_environment()

    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate configuration dictionary"""
        required_fields = ["service_name"]
        return all(field in config for field in required_fields)

    def apply_auto_configuration(
        self, base_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply auto-configuration to base configuration"""
        auto_config = self.get_auto_config()
        merged_config = base_config.copy()
        merged_config.update(auto_config)
        return merged_config

    def get_recommendations(
        self, env_info: Optional[EnvironmentInfo] = None
    ) -> Dict[str, Any]:
        """Get configuration recommendations based on environment"""
        if env_info is None:
            env_info = self.detect_environment()

        recommendations = {
            "log_level": (
                "INFO"
                if env_info.environment_type == "production"
                else "DEBUG"
            ),
            "console_logging": env_info.environment_type != "production",
            "file_logging": env_info.environment_type == "production",
        }

        if env_info.cloud_provider:
            recommendations["enable_cloud_logging"] = True

        return recommendations

    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        import platform
        import socket
        import os

        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "process_id": os.getpid(),
        }

    def _detect_environment_type(self) -> str:
        """Detect if running in development, staging, or production"""
        # Check environment variables first
        env_type = os.getenv("ENVIRONMENT", "").lower()
        if env_type in ["development", "staging", "production"]:
            return env_type

        # Check for common development indicators
        dev_indicators = [
            os.getenv("DEBUG") == "true",
            os.getenv("DEV") == "true",
            os.getenv("NODE_ENV") == "development",
            "localhost" in socket.gethostname().lower(),
            "dev" in socket.gethostname().lower(),
        ]

        if any(dev_indicators):
            return Environment.DEVELOPMENT.value

        # Check for production indicators
        prod_indicators = [
            os.getenv("PROD") == "true",
            os.getenv("NODE_ENV") == "production",
            "prod" in socket.gethostname().lower(),
            self._detect_cloud_provider() is not None,
        ]

        if any(prod_indicators):
            return Environment.PRODUCTION.value

        # Default to development
        return Environment.DEVELOPMENT.value

    def _detect_cloud_provider(self) -> Optional[str]:
        """Detect cloud provider based on environment variables and metadata"""
        # Check AWS
        if any(os.getenv(var) for var in CLOUD_PROVIDERS.AWS_ENV_VARS):
            return "aws"

        # Check GCP
        if any(os.getenv(var) for var in CLOUD_PROVIDERS.GCP_ENV_VARS):
            return "gcp"

        # Check Azure
        if any(os.getenv(var) for var in CLOUD_PROVIDERS.AZURE_ENV_VARS):
            return "azure"

        # Try to detect from metadata endpoints (with timeout)
        # In a real implementation, you'd make HTTP calls
        # to metadata endpoints with requests library
        # For now, just return None

        return None

    def _detect_container_runtime(self) -> Optional[str]:
        """Detect if running in a container"""
        # Check for Docker
        if Path(CONTAINER_DETECTION.DOCKER_ENV_FILE).exists():
            return "docker"

        # Check for Docker environment variables
        if any(os.getenv(var) for var in CONTAINER_DETECTION.DOCKER_ENV_VARS):
            return "docker"

        # Check for container-specific files
        try:
            with open("/proc/1/cgroup", "r") as f:
                content = f.read()
                if "docker" in content or "containerd" in content:
                    return "docker"
        except (FileNotFoundError, PermissionError):
            pass

        return None

    def _detect_orchestrator(self) -> Optional[str]:
        """Detect container orchestrator (Kubernetes, Docker Swarm, etc.)"""
        # Check for Kubernetes
        if os.getenv(CONTAINER_DETECTION.KUBERNETES_SERVICE_HOST):
            return "kubernetes"

        if Path(CONTAINER_DETECTION.KUBERNETES_NAMESPACE_FILE).exists():
            return "kubernetes"

        # Check for Kubernetes environment variables
        if any(os.getenv(var) for var in CONTAINER_DETECTION.K8S_ENV_VARS):
            return "kubernetes"

        # Check for Docker Swarm
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip() == "active":
                return "docker-swarm"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def _detect_region(self, cloud_provider: Optional[str]) -> Optional[str]:
        """Detect cloud region"""
        if cloud_provider == "aws":
            return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        elif cloud_provider == "gcp":
            return os.getenv("GCP_REGION") or os.getenv("GOOGLE_CLOUD_REGION")
        elif cloud_provider == "azure":
            return os.getenv("AZURE_REGION")

        return None

    def _detect_instance_id(
        self, cloud_provider: Optional[str]
    ) -> Optional[str]:
        """Detect cloud instance ID"""
        if cloud_provider == "aws":
            return os.getenv("AWS_INSTANCE_ID")
        elif cloud_provider == "gcp":
            return os.getenv("GCP_INSTANCE_ID")
        elif cloud_provider == "azure":
            return os.getenv("AZURE_INSTANCE_ID")

        return None

    def _detect_runtime(self, cloud_provider: Optional[str]) -> Optional[str]:
        """Detect runtime environment"""
        if cloud_provider == "aws":
            aws_execution_env = os.getenv("AWS_EXECUTION_ENV")
            if aws_execution_env:
                return aws_execution_env
        elif cloud_provider == "gcp":
            gcp_runtime = os.getenv("GAE_RUNTIME")
            if gcp_runtime:
                return gcp_runtime

        # Check for Python version
        import platform

        python_version = platform.python_version()
        if python_version:
            return f"python{python_version}"

        return None

    def _detect_project_id(
        self, cloud_provider: Optional[str]
    ) -> Optional[str]:
        """Detect cloud project ID"""
        if cloud_provider == "gcp":
            return (
                os.getenv("GCP_PROJECT")
                or os.getenv("GOOGLE_CLOUD_PROJECT")
                or os.getenv("GCLOUD_PROJECT")
            )
        elif cloud_provider == "aws":
            return os.getenv("AWS_PROJECT_ID")
        elif cloud_provider == "azure":
            return os.getenv("AZURE_PROJECT_ID")

        return None

    def _detect_namespace(self, orchestrator: Optional[str]) -> Optional[str]:
        """Detect orchestrator namespace"""
        if orchestrator == "kubernetes":
            # Try to read from service account
            try:
                namespace_file = (
                    "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
                )
                with open(namespace_file, "r") as f:
                    return f.read().strip()
            except (FileNotFoundError, PermissionError):
                pass

            # Try environment variables
            return os.getenv("POD_NAMESPACE") or os.getenv(
                "KUBERNETES_NAMESPACE"
            )

        return None

    def _collect_metadata(
        self,
        cloud_provider: Optional[str],
        container_runtime: Optional[str],
        orchestrator: Optional[str],
    ) -> Dict[str, Any]:
        """Collect additional metadata about the environment"""
        metadata = {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "process_id": os.getpid(),
        }

        # Add cloud metadata
        if cloud_provider:
            metadata["cloud_provider"] = cloud_provider
            if cloud_provider == "aws":
                metadata.update(
                    {
                        "availability_zone": os.getenv(
                            "AWS_AVAILABILITY_ZONE"
                        ),
                        "instance_type": os.getenv("AWS_INSTANCE_TYPE"),
                    }
                )

        # Add container metadata
        if container_runtime:
            metadata["container_runtime"] = container_runtime
            if container_runtime == "docker":
                metadata["container_id"] = os.getenv(
                    "HOSTNAME"
                )  # Docker sets hostname to container ID

        # Add orchestrator metadata
        if orchestrator:
            metadata["orchestrator"] = orchestrator
            if orchestrator == "kubernetes":
                metadata.update(
                    {
                        "pod_name": os.getenv("POD_NAME"),
                        "namespace": os.getenv("POD_NAMESPACE"),
                        "node_name": os.getenv("NODE_NAME"),
                    }
                )

        return metadata

    def auto_configure(self, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply auto-configuration based on detected environment.

        Args:
            base_config: Base configuration to enhance

        Returns:
            Enhanced configuration with auto-detected settings
        """
        env_info = self.detect_environment()
        config = base_config.copy()

        # Apply environment-specific configurations
        self._apply_environment_config(config, env_info)
        self._apply_cloud_config(config, env_info)
        self._apply_container_config(config, env_info)
        self._apply_performance_config(config, env_info)

        return config

    def _apply_environment_config(
        self, config: Dict[str, Any], env_info: EnvironmentInfo
    ):
        """Apply environment-specific configurations"""
        if env_info.environment_type == Environment.DEVELOPMENT.value:
            # Development defaults
            config.setdefault("log_level", "DEBUG")
            config.setdefault("console_logging", True)
            config.setdefault("file_logging", False)

        elif env_info.environment_type == Environment.STAGING.value:
            # Staging defaults
            config.setdefault("log_level", "INFO")
            config.setdefault("console_logging", True)
            config.setdefault("file_logging", True)
            config.setdefault("log_file_path", "logs/staging.log")

        elif env_info.environment_type == Environment.PRODUCTION.value:
            # Production defaults
            config.setdefault("log_level", "WARNING")
            config.setdefault(
                "console_logging", False
            )  # Reduce noise in production
            config.setdefault("file_logging", True)
            config.setdefault("log_file_path", "/var/log/app/production.log")

            # Enable structured logging for production
            if "context_enrichment" not in config:
                config["context_enrichment"] = {}
            config["context_enrichment"]["enabled"] = True

    def _apply_cloud_config(
        self, config: Dict[str, Any], env_info: EnvironmentInfo
    ):
        """Apply cloud-specific configurations"""
        if not env_info.cloud_provider:
            return

        # Add cloud metadata to context
        if "context_enrichment" not in config:
            config["context_enrichment"] = {}

        cloud_context = config["context_enrichment"].setdefault(
            "custom_fields", {}
        )
        cloud_context.update(
            {
                "cloud_provider": env_info.cloud_provider,
                "region": env_info.region,
                "instance_id": env_info.instance_id,
            }
        )

        # Cloud-specific optimizations
        if env_info.cloud_provider == "aws":
            self._apply_aws_config(config, env_info)
        elif env_info.cloud_provider == "gcp":
            self._apply_gcp_config(config, env_info)
        elif env_info.cloud_provider == "azure":
            self._apply_azure_config(config, env_info)

    def _apply_aws_config(
        self, config: Dict[str, Any], env_info: EnvironmentInfo
    ):
        """Apply AWS-specific configurations"""
        # Auto-detect CloudWatch logs if available
        if os.getenv("AWS_LOG_GROUP"):
            # Could configure CloudWatch handler here
            pass

        # Add AWS metadata
        aws_metadata = {
            "availability_zone": env_info.metadata.get("availability_zone"),
            "instance_type": env_info.metadata.get("instance_type"),
        }
        config.setdefault("context_enrichment", {}).setdefault(
            "custom_fields", {}
        ).update(aws_metadata)

    def _apply_gcp_config(
        self, config: Dict[str, Any], env_info: EnvironmentInfo
    ):
        """Apply GCP-specific configurations"""
        # Auto-detect Cloud Logging if available
        if os.getenv("GOOGLE_CLOUD_PROJECT"):
            # Could configure Cloud Logging handler here
            pass

    def _apply_azure_config(
        self, config: Dict[str, Any], env_info: EnvironmentInfo
    ):
        """Apply Azure-specific configurations"""
        # Auto-detect Azure Monitor if available
        if os.getenv("AZURE_SUBSCRIPTION_ID"):
            # Could configure Azure Monitor handler here
            pass

    def _apply_container_config(
        self, config: Dict[str, Any], env_info: EnvironmentInfo
    ):
        """Apply container-specific configurations"""
        if not env_info.container_runtime:
            return

        # Container-specific settings
        config.setdefault(
            "console_logging", True
        )  # Containers typically use stdout/stderr

        # Add container metadata to context
        if "context_enrichment" not in config:
            config["context_enrichment"] = {}

        container_context = config["context_enrichment"].setdefault(
            "custom_fields", {}
        )
        container_context.update(
            {
                "container_runtime": env_info.container_runtime,
                "container_id": env_info.metadata.get("container_id"),
            }
        )

        # Kubernetes-specific configurations
        if env_info.orchestrator == "kubernetes":
            k8s_metadata = {
                "pod_name": env_info.metadata.get("pod_name"),
                "namespace": env_info.metadata.get("namespace"),
                "node_name": env_info.metadata.get("node_name"),
            }
            container_context.update(k8s_metadata)

            # Enable request ID correlation in K8s
            config["context_enrichment"]["include_request_id"] = True

    def _apply_performance_config(
        self, config: Dict[str, Any], env_info: EnvironmentInfo
    ):
        """Apply performance optimizations based on environment"""
        # Production performance optimizations
        if env_info.environment_type == Environment.PRODUCTION.value:
            if "handlers" not in config:
                config["handlers"] = {}

            # Optimize Loki handler for production
            loki_config = config["handlers"].setdefault("loki", {})
            loki_config.setdefault(
                "batch_size", 500
            )  # Larger batches for production
            loki_config.setdefault("timeout", 30)

            # Optimize file handler for production
            file_config = config["handlers"].setdefault("file", {})
            file_config.setdefault("rotation", True)
            file_config.setdefault(
                "max_size_mb", 1000
            )  # Larger files in production
            file_config.setdefault("backup_count", 10)

        # Development performance settings
        elif env_info.environment_type == Environment.DEVELOPMENT.value:
            if "handlers" not in config:
                config["handlers"] = {}

            # Smaller batches and timeouts for development
            loki_config = config["handlers"].setdefault("loki", {})
            loki_config.setdefault("batch_size", 10)
            loki_config.setdefault("timeout", 5)

    def get_recommended_loki_url(self) -> Optional[str]:
        """Get recommended Loki URL based on environment"""
        env_info = self.detect_environment()

        if env_info.environment_type == Environment.DEVELOPMENT.value:
            return f"http://localhost:{DEFAULT_PORTS.LOKI}/loki/api/v1/push"

        # In production, you might want to use service discovery
        # or environment-specific URLs
        if env_info.orchestrator == "kubernetes":
            return "http://loki:3100/loki/api/v1/push"  # K8s service name

        return None

    def get_environment_summary(self) -> Dict[str, Any]:
        """Get a summary of the detected environment for logging/debugging"""
        env_info = self.detect_environment()
        return {
            "environment_type": env_info.environment_type,
            "cloud_provider": env_info.cloud_provider,
            "container_runtime": env_info.container_runtime,
            "orchestrator": env_info.orchestrator,
            "region": env_info.region,
            "hostname": env_info.metadata.get("hostname"),
            "platform": env_info.metadata.get("platform"),
        }


# Singleton instance for easy access
_auto_configurator = AutoConfigurator()


# Convenience functions
def detect_environment() -> EnvironmentInfo:
    """Convenience function to detect environment"""
    return _auto_configurator.detect_environment()


def auto_configure(base_config: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to apply auto-configuration"""
    return _auto_configurator.auto_configure(base_config)


def get_environment_summary() -> Dict[str, Any]:
    """Convenience function to get environment summary"""
    return _auto_configurator.get_environment_summary()
