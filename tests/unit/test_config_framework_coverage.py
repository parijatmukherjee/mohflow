"""
Comprehensive unit tests for auto_config, config_loader, and
framework_detection modules.

Targets near-100% line coverage for all uncovered lines in:
- src/mohflow/auto_config.py
- src/mohflow/config_loader.py
- src/mohflow/framework_detection.py
"""

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict
from unittest.mock import (
    MagicMock,
    mock_open,
    patch,
)

import pytest

from mohflow.auto_config import (
    AutoConfigurator,
    EnvironmentInfo,
    auto_configure,
    detect_environment,
    get_environment_summary,
    get_framework_recommendations,
    get_intelligent_config,
)
from mohflow.config_loader import (
    ConfigLoader,
    load_config,
)
from mohflow.exceptions import ConfigurationError
from mohflow.framework_detection import (
    ApplicationInfo,
    FrameworkDetector,
    FrameworkInfo,
    detect_application_type,
    detect_frameworks,
    get_framework_optimized_config,
    get_framework_summary,
)


# ---------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove cloud / container env vars between tests so that
    detection methods start from a clean slate."""
    cloud_vars = [
        "AWS_REGION",
        "AWS_AVAILABILITY_ZONE",
        "AWS_INSTANCE_ID",
        "AWS_DEFAULT_REGION",
        "AWS_EXECUTION_ENV",
        "AWS_LOG_GROUP",
        "AWS_INSTANCE_TYPE",
        "AWS_PROJECT_ID",
        "AWS_LAMBDA_FUNCTION_NAME",
        "GCP_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "GCLOUD_PROJECT",
        "GCP_REGION",
        "GOOGLE_CLOUD_REGION",
        "GCP_INSTANCE_ID",
        "GAE_RUNTIME",
        "K_SERVICE",
        "AZURE_RESOURCE_GROUP",
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_REGION",
        "AZURE_CLIENT_ID",
        "AZURE_INSTANCE_ID",
        "AZURE_PROJECT_ID",
        "WEBSITE_SITE_NAME",
        "KUBERNETES_SERVICE_HOST",
        "KUBERNETES_SERVICE_PORT",
        "KUBERNETES_NAMESPACE",
        "POD_NAME",
        "POD_NAMESPACE",
        "NODE_NAME",
        "DOCKER_CONTAINER_ID",
        "HOSTNAME",
        "ENVIRONMENT",
        "DEBUG",
        "DEV",
        "NODE_ENV",
        "PROD",
        "FUNCTIONS_WORKER_RUNTIME",
        # MOHFLOW_ prefixed vars
        "MOHFLOW_SERVICE_NAME",
        "MOHFLOW_ENVIRONMENT",
        "MOHFLOW_LOG_LEVEL",
        "MOHFLOW_CONSOLE_LOGGING",
        "MOHFLOW_FILE_LOGGING",
        "MOHFLOW_LOG_FILE_PATH",
        "MOHFLOW_LOKI_URL",
    ]
    for var in cloud_vars:
        monkeypatch.delenv(var, raising=False)


# ===============================================================
# AUTO_CONFIG TESTS
# ===============================================================


class TestEnvironmentInfo:
    """Tests for the EnvironmentInfo dataclass."""

    def test_defaults(self):
        env = EnvironmentInfo()
        assert env.environment_type == "development"
        assert env.cloud_provider is None
        assert env.metadata == {}

    def test_post_init_sets_metadata(self):
        env = EnvironmentInfo(metadata=None)
        assert env.metadata == {}

    def test_metadata_preserved_when_set(self):
        env = EnvironmentInfo(metadata={"key": "val"})
        assert env.metadata == {"key": "val"}


class TestAutoConfiguratorDetection:
    """Tests for AutoConfigurator environment detection methods."""

    def _make(self, **kw):
        ac = AutoConfigurator(**kw)
        return ac

    # -- _detect_environment_type --

    @patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False)
    def test_detect_env_type_from_env_var_production(self):
        ac = self._make()
        assert ac._detect_environment_type() == "production"

    @patch.dict(os.environ, {"ENVIRONMENT": "staging"}, clear=False)
    def test_detect_env_type_from_env_var_staging(self):
        ac = self._make()
        assert ac._detect_environment_type() == "staging"

    @patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False)
    def test_detect_env_type_from_env_var_development(self):
        ac = self._make()
        assert ac._detect_environment_type() == "development"

    @patch.dict(os.environ, {"DEBUG": "true"}, clear=False)
    def test_detect_env_type_debug_indicator(self):
        ac = self._make()
        assert ac._detect_environment_type() == "development"

    @patch.dict(os.environ, {"DEV": "true"}, clear=False)
    def test_detect_env_type_dev_indicator(self):
        ac = self._make()
        assert ac._detect_environment_type() == "development"

    @patch.dict(
        os.environ, {"NODE_ENV": "development"}, clear=False
    )
    def test_detect_env_type_node_env_development(self):
        ac = self._make()
        assert ac._detect_environment_type() == "development"

    @patch("socket.gethostname", return_value="my-localhost-box")
    def test_detect_env_type_localhost_hostname(self, _):
        ac = self._make()
        assert ac._detect_environment_type() == "development"

    @patch("socket.gethostname", return_value="my-dev-server")
    def test_detect_env_type_dev_in_hostname(self, _):
        ac = self._make()
        assert ac._detect_environment_type() == "development"

    @patch.dict(os.environ, {"PROD": "true"}, clear=False)
    def test_detect_env_type_prod_indicator(self):
        ac = self._make()
        assert ac._detect_environment_type() == "production"

    @patch.dict(
        os.environ, {"NODE_ENV": "production"}, clear=False
    )
    def test_detect_env_type_node_env_production(self):
        ac = self._make()
        assert ac._detect_environment_type() == "production"

    @patch("socket.gethostname", return_value="web-prod-01")
    def test_detect_env_type_prod_in_hostname(self, _):
        ac = self._make()
        assert ac._detect_environment_type() == "production"

    @patch.dict(
        os.environ, {"AWS_REGION": "us-east-1"}, clear=False
    )
    def test_detect_env_type_cloud_means_production(self):
        ac = self._make()
        assert ac._detect_environment_type() == "production"

    # -- _detect_cloud_provider --

    @patch.dict(
        os.environ, {"AWS_REGION": "us-east-1"}, clear=False
    )
    def test_detect_cloud_aws(self):
        ac = self._make()
        assert ac._detect_cloud_provider() == "aws"

    @patch.dict(
        os.environ, {"GCP_PROJECT": "my-proj"}, clear=False
    )
    def test_detect_cloud_gcp(self):
        ac = self._make()
        assert ac._detect_cloud_provider() == "gcp"

    @patch.dict(
        os.environ,
        {"AZURE_SUBSCRIPTION_ID": "sub-123"},
        clear=False,
    )
    def test_detect_cloud_azure(self):
        ac = self._make()
        assert ac._detect_cloud_provider() == "azure"

    def test_detect_cloud_local(self):
        ac = self._make()
        assert ac._detect_cloud_provider() == "local"

    # -- _detect_container_runtime --

    @patch("os.path.exists", return_value=True)
    def test_detect_docker_via_dockerenv(self, _):
        ac = self._make()
        assert ac._detect_container_runtime() == "docker"

    @patch("os.path.exists", return_value=False)
    @patch.dict(
        os.environ,
        {"DOCKER_CONTAINER_ID": "abc123"},
        clear=False,
    )
    def test_detect_docker_via_env_var(self, _):
        ac = self._make()
        assert ac._detect_container_runtime() == "docker"

    @patch("os.path.exists", return_value=False)
    def test_detect_docker_via_cgroup(self, mock_exists):
        ac = self._make()
        cgroup_content = "12:memory:/docker/abc123\n"
        with patch(
            "builtins.open",
            mock_open(read_data=cgroup_content),
        ):
            assert ac._detect_container_runtime() == "docker"

    @patch("os.path.exists", return_value=False)
    def test_detect_containerd_via_cgroup(self, mock_exists):
        ac = self._make()
        cgroup_content = "12:memory:/containerd/abc\n"
        with patch(
            "builtins.open",
            mock_open(read_data=cgroup_content),
        ):
            assert ac._detect_container_runtime() == "docker"

    @patch("os.path.exists", return_value=False)
    def test_detect_no_container_cgroup_not_found(self, _):
        ac = self._make()
        with patch(
            "builtins.open", side_effect=FileNotFoundError
        ):
            assert ac._detect_container_runtime() is None

    @patch("os.path.exists", return_value=False)
    def test_detect_no_container_cgroup_permission(self, _):
        ac = self._make()
        with patch(
            "builtins.open", side_effect=PermissionError
        ):
            assert ac._detect_container_runtime() is None

    # -- _detect_orchestrator --

    @patch.dict(
        os.environ,
        {"KUBERNETES_SERVICE_HOST": "10.0.0.1"},
        clear=False,
    )
    @patch("os.path.exists", return_value=False)
    def test_detect_k8s_via_env(self, _):
        ac = self._make()
        assert ac._detect_orchestrator() == "kubernetes"

    @patch("os.path.exists")
    def test_detect_k8s_via_namespace_file(self, mock_exists):
        mock_exists.side_effect = (
            lambda p: p
            == "/var/run/secrets/kubernetes.io/"
            "serviceaccount/namespace"
        )
        ac = self._make()
        assert ac._detect_orchestrator() == "kubernetes"

    @patch.dict(
        os.environ, {"POD_NAME": "my-pod"}, clear=False
    )
    @patch("os.path.exists", return_value=False)
    def test_detect_k8s_via_k8s_env_vars(self, _):
        ac = self._make()
        assert ac._detect_orchestrator() == "kubernetes"

    @patch("os.path.exists", return_value=False)
    @patch("subprocess.run")
    def test_detect_docker_swarm(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="active\n"
        )
        ac = self._make()
        assert ac._detect_orchestrator() == "docker-swarm"

    @patch("os.path.exists", return_value=False)
    @patch("subprocess.run")
    def test_detect_swarm_inactive(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="inactive\n"
        )
        ac = self._make()
        assert ac._detect_orchestrator() is None

    @patch("os.path.exists", return_value=False)
    @patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired("cmd", 5),
    )
    def test_detect_orchestrator_timeout(self, *_):
        ac = self._make()
        assert ac._detect_orchestrator() is None

    @patch("os.path.exists", return_value=False)
    @patch(
        "subprocess.run", side_effect=FileNotFoundError
    )
    def test_detect_orchestrator_no_docker(self, *_):
        ac = self._make()
        assert ac._detect_orchestrator() is None

    # -- _detect_region --

    def test_detect_region_aws(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AWS_REGION": "us-west-2"},
            clear=False,
        ):
            assert ac._detect_region("aws") == "us-west-2"

    def test_detect_region_aws_default(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AWS_DEFAULT_REGION": "eu-west-1"},
            clear=False,
        ):
            assert ac._detect_region("aws") == "eu-west-1"

    def test_detect_region_gcp(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"GCP_REGION": "us-central1"},
            clear=False,
        ):
            assert ac._detect_region("gcp") == "us-central1"

    def test_detect_region_gcp_google(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"GOOGLE_CLOUD_REGION": "asia-east1"},
            clear=False,
        ):
            assert ac._detect_region("gcp") == "asia-east1"

    def test_detect_region_azure(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AZURE_REGION": "westeurope"},
            clear=False,
        ):
            assert ac._detect_region("azure") == "westeurope"

    def test_detect_region_none(self):
        ac = self._make()
        assert ac._detect_region(None) is None
        assert ac._detect_region("local") is None

    # -- _detect_instance_id --

    def test_detect_instance_aws(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AWS_INSTANCE_ID": "i-123"},
            clear=False,
        ):
            assert ac._detect_instance_id("aws") == "i-123"

    def test_detect_instance_gcp(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"GCP_INSTANCE_ID": "gcp-i-1"},
            clear=False,
        ):
            assert ac._detect_instance_id("gcp") == "gcp-i-1"

    def test_detect_instance_azure(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AZURE_INSTANCE_ID": "az-i-1"},
            clear=False,
        ):
            assert (
                ac._detect_instance_id("azure") == "az-i-1"
            )

    def test_detect_instance_none(self):
        ac = self._make()
        assert ac._detect_instance_id(None) is None

    # -- _detect_runtime --

    def test_detect_runtime_aws_lambda(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AWS_EXECUTION_ENV": "AWS_Lambda_python3.9"},
            clear=False,
        ):
            assert (
                ac._detect_runtime("aws")
                == "AWS_Lambda_python3.9"
            )

    def test_detect_runtime_aws_no_exec_env(self):
        ac = self._make()
        result = ac._detect_runtime("aws")
        assert result.startswith("python")

    def test_detect_runtime_gcp_gae(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"GAE_RUNTIME": "python39"},
            clear=False,
        ):
            assert ac._detect_runtime("gcp") == "python39"

    def test_detect_runtime_gcp_no_gae(self):
        ac = self._make()
        result = ac._detect_runtime("gcp")
        assert result.startswith("python")

    def test_detect_runtime_default_python(self):
        ac = self._make()
        result = ac._detect_runtime(None)
        expected = f"python{platform.python_version()}"
        assert result == expected

    # -- _detect_project_id --

    def test_detect_project_gcp_primary(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"GCP_PROJECT": "my-proj"},
            clear=False,
        ):
            assert ac._detect_project_id("gcp") == "my-proj"

    def test_detect_project_gcp_google(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"GOOGLE_CLOUD_PROJECT": "gc-proj"},
            clear=False,
        ):
            assert ac._detect_project_id("gcp") == "gc-proj"

    def test_detect_project_gcp_gcloud(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"GCLOUD_PROJECT": "gl-proj"},
            clear=False,
        ):
            assert ac._detect_project_id("gcp") == "gl-proj"

    def test_detect_project_aws(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AWS_PROJECT_ID": "aws-p"},
            clear=False,
        ):
            assert ac._detect_project_id("aws") == "aws-p"

    def test_detect_project_azure(self):
        ac = self._make()
        with patch.dict(
            os.environ,
            {"AZURE_PROJECT_ID": "az-p"},
            clear=False,
        ):
            assert ac._detect_project_id("azure") == "az-p"

    def test_detect_project_none(self):
        ac = self._make()
        assert ac._detect_project_id(None) is None

    # -- _detect_namespace --

    def test_detect_namespace_k8s_file(self):
        ac = self._make()
        with patch(
            "builtins.open",
            mock_open(read_data="prod-ns\n"),
        ):
            assert (
                ac._detect_namespace("kubernetes") == "prod-ns"
            )

    def test_detect_namespace_k8s_file_not_found(self):
        ac = self._make()
        with patch(
            "builtins.open", side_effect=FileNotFoundError
        ):
            with patch.dict(
                os.environ,
                {"POD_NAMESPACE": "fallback-ns"},
                clear=False,
            ):
                assert (
                    ac._detect_namespace("kubernetes")
                    == "fallback-ns"
                )

    def test_detect_namespace_k8s_permission_error(self):
        ac = self._make()
        with patch(
            "builtins.open", side_effect=PermissionError
        ):
            with patch.dict(
                os.environ,
                {"KUBERNETES_NAMESPACE": "env-ns"},
                clear=False,
            ):
                assert (
                    ac._detect_namespace("kubernetes")
                    == "env-ns"
                )

    def test_detect_namespace_not_k8s(self):
        ac = self._make()
        assert ac._detect_namespace(None) is None
        assert ac._detect_namespace("docker-swarm") is None

    # -- _collect_metadata --

    def test_collect_metadata_basic(self):
        ac = self._make()
        md = ac._collect_metadata(None, None, None)
        assert "hostname" in md
        assert "platform" in md
        assert "python_version" in md
        assert "process_id" in md

    @patch.dict(
        os.environ,
        {
            "AWS_AVAILABILITY_ZONE": "us-east-1a",
            "AWS_INSTANCE_TYPE": "t3.micro",
        },
        clear=False,
    )
    def test_collect_metadata_aws(self):
        ac = self._make()
        md = ac._collect_metadata("aws", None, None)
        assert md["cloud_provider"] == "aws"
        assert md["availability_zone"] == "us-east-1a"
        assert md["instance_type"] == "t3.micro"

    @patch.dict(
        os.environ, {"HOSTNAME": "container-id"}, clear=False
    )
    def test_collect_metadata_docker(self):
        ac = self._make()
        md = ac._collect_metadata(None, "docker", None)
        assert md["container_runtime"] == "docker"
        assert md["container_id"] == "container-id"

    @patch.dict(
        os.environ,
        {
            "POD_NAME": "my-pod",
            "POD_NAMESPACE": "default",
            "NODE_NAME": "node-1",
        },
        clear=False,
    )
    def test_collect_metadata_k8s(self):
        ac = self._make()
        md = ac._collect_metadata(
            None, None, "kubernetes"
        )
        assert md["orchestrator"] == "kubernetes"
        assert md["pod_name"] == "my-pod"
        assert md["namespace"] == "default"
        assert md["node_name"] == "node-1"

    def test_collect_metadata_non_aws_cloud(self):
        ac = self._make()
        md = ac._collect_metadata("gcp", None, None)
        assert md["cloud_provider"] == "gcp"
        assert "availability_zone" not in md


class TestAutoConfiguratorDetectEnvironmentCaching:
    """Test that detect_environment caches results."""

    def test_caches_result(self):
        ac = AutoConfigurator()
        with patch.object(
            ac, "_detect_environment_type", return_value="development"
        ), patch.object(
            ac, "_detect_cloud_provider", return_value="local"
        ), patch.object(
            ac, "_detect_container_runtime", return_value=None
        ), patch.object(
            ac, "_detect_orchestrator", return_value=None
        ):
            first = ac.detect_environment()
            second = ac.detect_environment()
            assert first is second


class TestAutoConfiguratorConfigMethods:
    """Tests for get_auto_config and related methods."""

    def test_get_auto_config_no_env_info(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
        )
        ac._env_info = env
        config = ac.get_auto_config()
        assert config["environment"] == "development"

    def test_get_auto_config_gcp(self):
        env = EnvironmentInfo(
            environment_type="production",
            cloud_provider="gcp",
            project_id="p-123",
        )
        ac = AutoConfigurator()
        config = ac.get_auto_config(env, "svc")
        assert config["project_id"] == "p-123"
        assert config["service_name"] == "svc"

    def test_get_auto_config_no_runtime_no_orchestrator(self):
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
        )
        ac = AutoConfigurator()
        config = ac.get_auto_config(env)
        assert "runtime" not in config
        assert "orchestrator" not in config

    def test_get_config_alias(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
        )
        ac._env_info = env
        config = ac.get_config()
        assert config["environment"] == "development"

    def test_get_environment_info(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="staging",
            cloud_provider="local",
        )
        ac._env_info = env
        result = ac.get_environment_info()
        assert result.environment_type == "staging"

    def test_validate_configuration_true(self):
        ac = AutoConfigurator()
        assert ac.validate_configuration(
            {"service_name": "svc"}
        )

    def test_validate_configuration_false(self):
        ac = AutoConfigurator()
        assert not ac.validate_configuration({"foo": "bar"})

    def test_apply_auto_configuration(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
        )
        ac._env_info = env
        result = ac.apply_auto_configuration(
            {"service_name": "svc"}
        )
        assert result["environment"] == "development"
        assert result["service_name"] == "svc"


class TestAutoConfiguratorRecommendations:
    """Tests for get_recommendations."""

    def test_production_recommendations(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="production",
            cloud_provider="aws",
        )
        recs = ac.get_recommendations(env)
        assert recs["log_level"] == "INFO"
        assert recs["console_logging"] is False
        assert recs["file_logging"] is True
        assert recs["enable_cloud_logging"] is True

    def test_development_recommendations(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider=None,
        )
        recs = ac.get_recommendations(env)
        assert recs["log_level"] == "DEBUG"
        assert recs["console_logging"] is True
        assert recs["file_logging"] is False
        assert "enable_cloud_logging" not in recs

    def test_recommendations_uses_detect(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
        )
        ac._env_info = env
        recs = ac.get_recommendations()
        assert recs["log_level"] == "DEBUG"


class TestAutoConfiguratorApplyMethods:
    """Tests for _apply_* configuration methods."""

    def _env(self, **kw) -> EnvironmentInfo:
        defaults: Dict[str, Any] = {
            "environment_type": "development",
            "cloud_provider": None,
            "container_runtime": None,
            "orchestrator": None,
            "metadata": {},
        }
        defaults.update(kw)
        return EnvironmentInfo(**defaults)

    def test_apply_environment_config_development(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_environment_config(
            config, self._env(environment_type="development")
        )
        assert config["log_level"] == "DEBUG"
        assert config["console_logging"] is True
        assert config["file_logging"] is False

    def test_apply_environment_config_staging(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_environment_config(
            config, self._env(environment_type="staging")
        )
        assert config["log_level"] == "INFO"
        assert config["console_logging"] is True
        assert config["file_logging"] is True
        assert config["log_file_path"] == "logs/staging.log"

    def test_apply_environment_config_production(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_environment_config(
            config, self._env(environment_type="production")
        )
        assert config["log_level"] == "WARNING"
        assert config["console_logging"] is False
        assert config["file_logging"] is True
        assert config["context_enrichment"]["enabled"] is True

    def test_apply_environment_config_production_existing(
        self,
    ):
        """Production with existing context_enrichment."""
        ac = AutoConfigurator()
        config: Dict[str, Any] = {
            "context_enrichment": {"foo": "bar"}
        }
        ac._apply_environment_config(
            config, self._env(environment_type="production")
        )
        assert config["context_enrichment"]["enabled"] is True
        assert config["context_enrichment"]["foo"] == "bar"

    def test_apply_cloud_config_none(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_cloud_config(
            config, self._env(cloud_provider=None)
        )
        assert "context_enrichment" not in config

    def test_apply_cloud_config_aws(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        env = self._env(
            cloud_provider="aws",
            region="us-east-1",
            instance_id="i-1",
            metadata={
                "availability_zone": "us-east-1a",
                "instance_type": "t3.micro",
            },
        )
        ac._apply_cloud_config(config, env)
        ce = config["context_enrichment"]["custom_fields"]
        assert ce["cloud_provider"] == "aws"
        assert ce["region"] == "us-east-1"
        assert ce["availability_zone"] == "us-east-1a"

    def test_apply_cloud_config_gcp(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        env = self._env(
            cloud_provider="gcp",
            region="us-central1",
            metadata={},
        )
        with patch.dict(
            os.environ,
            {"GOOGLE_CLOUD_PROJECT": "proj"},
            clear=False,
        ):
            ac._apply_cloud_config(config, env)
        assert (
            config["context_enrichment"]["custom_fields"][
                "cloud_provider"
            ]
            == "gcp"
        )

    def test_apply_cloud_config_azure(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        env = self._env(
            cloud_provider="azure",
            metadata={},
        )
        with patch.dict(
            os.environ,
            {"AZURE_SUBSCRIPTION_ID": "sub-1"},
            clear=False,
        ):
            ac._apply_cloud_config(config, env)
        assert (
            config["context_enrichment"]["custom_fields"][
                "cloud_provider"
            ]
            == "azure"
        )

    def test_apply_container_config_none(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_container_config(
            config, self._env(container_runtime=None)
        )
        assert "context_enrichment" not in config

    def test_apply_container_config_docker(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        env = self._env(
            container_runtime="docker",
            metadata={"container_id": "abc123"},
        )
        ac._apply_container_config(config, env)
        ce = config["context_enrichment"]["custom_fields"]
        assert ce["container_runtime"] == "docker"
        assert ce["container_id"] == "abc123"

    def test_apply_container_config_k8s(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        env = self._env(
            container_runtime="docker",
            orchestrator="kubernetes",
            metadata={
                "container_id": "abc",
                "pod_name": "my-pod",
                "namespace": "default",
                "node_name": "node-1",
            },
        )
        ac._apply_container_config(config, env)
        ce = config["context_enrichment"]
        assert ce["include_request_id"] is True
        cf = ce["custom_fields"]
        assert cf["pod_name"] == "my-pod"
        assert cf["namespace"] == "default"

    def test_apply_performance_config_production(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_performance_config(
            config, self._env(environment_type="production")
        )
        assert config["handlers"]["loki"]["batch_size"] == 500
        assert config["handlers"]["loki"]["timeout"] == 30
        assert config["handlers"]["file"]["rotation"] is True

    def test_apply_performance_config_development(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_performance_config(
            config, self._env(environment_type="development")
        )
        assert config["handlers"]["loki"]["batch_size"] == 10
        assert config["handlers"]["loki"]["timeout"] == 5

    def test_apply_performance_config_staging_noop(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        ac._apply_performance_config(
            config, self._env(environment_type="staging")
        )
        assert "handlers" not in config


class TestAutoConfiguratorLokiUrl:
    """Tests for get_recommended_loki_url."""

    def test_loki_url_development(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
        )
        ac._env_info = env
        url = ac.get_recommended_loki_url()
        assert "localhost" in url
        assert "3100" in url

    def test_loki_url_k8s(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="production",
            cloud_provider="aws",
            orchestrator="kubernetes",
            metadata={},
        )
        ac._env_info = env
        url = ac.get_recommended_loki_url()
        assert url == "http://loki:3100/loki/api/v1/push"

    def test_loki_url_production_no_k8s(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="production",
            cloud_provider="aws",
            metadata={},
        )
        ac._env_info = env
        assert ac.get_recommended_loki_url() is None


class TestAutoConfiguratorAutoConfigure:
    """Tests for auto_configure and intelligent config."""

    def test_auto_configure_basic(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
            metadata={},
        )
        ac._env_info = env
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            return_value={},
        ):
            result = ac.auto_configure(
                {"service_name": "svc"}
            )
        assert result["environment"] == "development"

    def test_apply_framework_config_success(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
            metadata={},
        )
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            return_value={
                "formatter_type": "fast",
                "context_enrichment": {
                    "custom_fields": {"fw": "test"},
                    "include_request_id": True,
                },
                "new_key": "new_val",
            },
        ):
            ac._apply_framework_config(config, env)
        assert config["formatter_type"] == "fast"
        ce = config["context_enrichment"]
        assert ce["custom_fields"]["fw"] == "test"
        assert ce["include_request_id"] is True
        assert config["new_key"] == "new_val"

    def test_apply_framework_config_existing_ce(self):
        """Merge into existing context_enrichment."""
        ac = AutoConfigurator()
        config: Dict[str, Any] = {
            "context_enrichment": {
                "custom_fields": {"existing": "yes"}
            }
        }
        env = EnvironmentInfo(
            environment_type="development",
            metadata={},
        )
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            return_value={
                "context_enrichment": {
                    "custom_fields": {"fw": "new"},
                }
            },
        ):
            ac._apply_framework_config(config, env)
        cf = config["context_enrichment"]["custom_fields"]
        assert cf["existing"] == "yes"
        assert cf["fw"] == "new"

    def test_apply_framework_config_error_handled(self):
        ac = AutoConfigurator()
        config: Dict[str, Any] = {}
        env = EnvironmentInfo(metadata={})
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            side_effect=RuntimeError("boom"),
        ):
            ac._apply_framework_config(config, env)
        # Should not raise; config unchanged
        assert config == {}

    def test_apply_framework_config_setdefault(self):
        """Existing key not overwritten by setdefault."""
        ac = AutoConfigurator()
        config: Dict[str, Any] = {"formatter_type": "prod"}
        env = EnvironmentInfo(metadata={})
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            return_value={"formatter_type": "fast"},
        ):
            ac._apply_framework_config(config, env)
        assert config["formatter_type"] == "prod"


class TestAutoConfiguratorMergeIntelligently:
    """Tests for _merge_configs_intelligently."""

    def test_new_keys_added(self):
        ac = AutoConfigurator()
        base = {"a": 1}
        fw = {"b": 2}
        result = ac._merge_configs_intelligently(base, fw)
        assert result == {"a": 1, "b": 2}

    def test_env_settings_kept(self):
        ac = AutoConfigurator()
        base = {"log_level": "WARNING"}
        fw = {"log_level": "DEBUG"}
        result = ac._merge_configs_intelligently(base, fw)
        assert result["log_level"] == "WARNING"

    def test_formatter_type_overridden(self):
        ac = AutoConfigurator()
        base = {"formatter_type": "structured"}
        fw = {"formatter_type": "fast"}
        result = ac._merge_configs_intelligently(base, fw)
        assert result["formatter_type"] == "fast"

    def test_async_handlers_overridden(self):
        ac = AutoConfigurator()
        base = {"async_handlers": False}
        fw = {"async_handlers": True}
        result = ac._merge_configs_intelligently(base, fw)
        assert result["async_handlers"] is True

    def test_context_enrichment_deep_merge(self):
        ac = AutoConfigurator()
        base = {
            "context_enrichment": {
                "custom_fields": {"base": True},
                "env_setting": "keep",
            }
        }
        fw = {
            "context_enrichment": {
                "custom_fields": {"fw": True},
                "fw_setting": "new",
            }
        }
        result = ac._merge_configs_intelligently(base, fw)
        ce = result["context_enrichment"]
        assert ce["custom_fields"]["base"] is True
        assert ce["custom_fields"]["fw"] is True
        assert ce["fw_setting"] == "new"

    def test_context_enrichment_no_existing_cf(self):
        ac = AutoConfigurator()
        base = {"context_enrichment": {}}
        fw = {
            "context_enrichment": {
                "custom_fields": {"new": True}
            }
        }
        result = ac._merge_configs_intelligently(base, fw)
        assert (
            result["context_enrichment"]["custom_fields"][
                "new"
            ]
            is True
        )


class TestAutoConfiguratorIntelligentConfig:
    """Tests for get_intelligent_config."""

    def test_intelligent_config_basic(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
            metadata={},
        )
        ac._env_info = env

        mock_app_info = ApplicationInfo(
            app_type="web",
            deployment_type="monolith",
            frameworks=[],
        )
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            return_value={},
        ), patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=mock_app_info,
        ):
            result = ac.get_intelligent_config(
                {"service_name": "svc"}, service_name="svc"
            )
        assert result["service_name"] == "svc"
        ce = result["context_enrichment"]["custom_fields"]
        assert ce["app_type"] == "web"
        assert ce["framework_count"] == 0

    def test_intelligent_config_no_service_name(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
            metadata={},
        )
        ac._env_info = env

        mock_app_info = ApplicationInfo(
            app_type="cli",
            deployment_type="monolith",
            frameworks=[],
        )
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            return_value={},
        ), patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=mock_app_info,
        ):
            result = ac.get_intelligent_config({})
        assert "service_name" not in result

    def test_intelligent_config_existing_ce_custom_fields(
        self,
    ):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="development",
            cloud_provider="local",
            metadata={},
        )
        ac._env_info = env

        mock_app_info = ApplicationInfo(
            app_type="api",
            deployment_type="microservice",
            frameworks=[],
        )
        with patch.object(
            ac._framework_detector,
            "get_optimized_config",
            return_value={
                "context_enrichment": {
                    "custom_fields": {"existing": True}
                }
            },
        ), patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=mock_app_info,
        ):
            result = ac.get_intelligent_config({})
        cf = result["context_enrichment"]["custom_fields"]
        assert cf["app_type"] == "api"
        assert cf["existing"] is True


class TestAutoConfiguratorFrameworkRecommendations:
    """Tests for get_framework_recommendations."""

    def _make_fw(self, **kw):
        defaults = {
            "name": "flask",
            "version": "2.0",
            "is_async": False,
            "recommended_formatter": "structured",
            "integration_notes": "Use request context",
        }
        defaults.update(kw)
        return FrameworkInfo(**defaults)

    def test_web_recommendations(self):
        ac = AutoConfigurator()
        fw = self._make_fw()
        app = ApplicationInfo(
            app_type="web",
            deployment_type="monolith",
            uses_async=False,
            frameworks=[fw],
        )
        with patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=app,
        ):
            recs = ac.get_framework_recommendations()
        assert recs["detected_app_type"] == "web"
        assert len(recs["frameworks"]) == 1
        assert (
            recs["recommendations"]["formatter"]
            == "structured"
        )
        assert len(recs["integration_tips"]) == 1
        assert len(recs["performance_notes"]) == 1

    def test_api_recommendations(self):
        ac = AutoConfigurator()
        fw = self._make_fw(
            name="fastapi",
            is_async=True,
            integration_notes=None,
        )
        app = ApplicationInfo(
            app_type="api",
            deployment_type="microservice",
            uses_async=True,
            frameworks=[fw],
        )
        with patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=app,
        ):
            recs = ac.get_framework_recommendations()
        assert recs["recommendations"]["formatter"] == "fast"
        assert (
            recs["recommendations"]["async_handlers"] is True
        )
        # No integration_notes, so no tip added
        assert len(recs["integration_tips"]) == 0

    def test_async_recommendations(self):
        ac = AutoConfigurator()
        fw = self._make_fw(
            name="aiohttp",
            is_async=True,
            integration_notes="async stuff",
        )
        app = ApplicationInfo(
            app_type="worker",
            deployment_type="monolith",
            uses_async=True,
            frameworks=[fw],
        )
        with patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=app,
        ):
            recs = ac.get_framework_recommendations()
        assert (
            recs["recommendations"]["async_handlers"] is True
        )

    def test_no_special_type_recommendations(self):
        ac = AutoConfigurator()
        app = ApplicationInfo(
            app_type="library",
            deployment_type="monolith",
            uses_async=False,
            frameworks=[],
        )
        with patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=app,
        ):
            recs = ac.get_framework_recommendations()
        assert recs["recommendations"] == {}


class TestAutoConfiguratorEnvironmentSummary:
    """Tests for get_environment_summary."""

    def test_summary(self):
        ac = AutoConfigurator()
        env = EnvironmentInfo(
            environment_type="production",
            cloud_provider="aws",
            container_runtime="docker",
            orchestrator="kubernetes",
            region="us-east-1",
            metadata={
                "hostname": "pod-1",
                "platform": "Linux",
            },
        )
        ac._env_info = env
        app = ApplicationInfo(
            app_type="web",
            deployment_type="microservice",
            uses_async=True,
            has_database=True,
            has_cache=True,
            has_message_queue=False,
            has_external_apis=True,
            frameworks=[
                FrameworkInfo(name="fastapi"),
                FrameworkInfo(name="sqlalchemy"),
            ],
        )
        with patch.object(
            ac._framework_detector,
            "detect_application_type",
            return_value=app,
        ):
            summary = ac.get_environment_summary()
        assert summary["environment_type"] == "production"
        assert summary["cloud_provider"] == "aws"
        assert summary["hostname"] == "pod-1"
        assert summary["app_type"] == "web"
        assert summary["uses_async"] is True
        assert "fastapi" in summary["frameworks"]
        assert summary["capabilities"]["database"] is True
        assert (
            summary["capabilities"]["message_queue"] is False
        )


class TestAutoConfigConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_detect_environment_func(self):
        with patch(
            "mohflow.auto_config._auto_configurator"
        ) as mock_ac:
            mock_ac.detect_environment.return_value = (
                EnvironmentInfo()
            )
            result = detect_environment()
            assert result.environment_type == "development"

    def test_auto_configure_func(self):
        with patch(
            "mohflow.auto_config._auto_configurator"
        ) as mock_ac:
            mock_ac.auto_configure.return_value = {
                "env": "dev"
            }
            result = auto_configure({"base": True})
            assert result == {"env": "dev"}

    def test_get_intelligent_config_func(self):
        with patch(
            "mohflow.auto_config._auto_configurator"
        ) as mock_ac:
            mock_ac.get_intelligent_config.return_value = {
                "smart": True
            }
            result = get_intelligent_config(
                {"base": True}, service_name="svc"
            )
            assert result == {"smart": True}

    def test_get_framework_recommendations_func(self):
        with patch(
            "mohflow.auto_config._auto_configurator"
        ) as mock_ac:
            mock_ac.get_framework_recommendations.return_value = (
                {"recs": True}
            )
            result = get_framework_recommendations()
            assert result == {"recs": True}

    def test_get_environment_summary_func(self):
        with patch(
            "mohflow.auto_config._auto_configurator"
        ) as mock_ac:
            mock_ac.get_environment_summary.return_value = {
                "summary": True
            }
            result = get_environment_summary()
            assert result == {"summary": True}


# ===============================================================
# CONFIG_LOADER TESTS
# ===============================================================


class TestConfigLoaderLoadSchema:
    """Tests for _load_schema."""

    def test_load_schema_success(self):
        loader = ConfigLoader()
        schema = loader._load_schema()
        assert "properties" in schema
        assert schema["title"] == "MohFlow Configuration Schema"

    def test_load_schema_cached(self):
        loader = ConfigLoader()
        first = loader._load_schema()
        second = loader._load_schema()
        assert first is second

    def test_load_schema_file_not_found(self):
        loader = ConfigLoader()
        loader.schema_path = Path("/nonexistent/schema.json")
        with pytest.raises(
            ConfigurationError, match="schema not found"
        ):
            loader._load_schema()

    def test_load_schema_invalid_json(self):
        loader = ConfigLoader()
        with patch(
            "builtins.open",
            mock_open(read_data="not json{{{"),
        ):
            loader._schema = None
            with pytest.raises(
                ConfigurationError, match="Invalid JSON schema"
            ):
                loader._load_schema()


class TestConfigLoaderLoadJsonConfig:
    """Tests for _load_json_config."""

    def test_no_config_file(self):
        loader = ConfigLoader()
        assert loader._load_json_config() == {}

    def test_file_not_found(self, tmp_path):
        loader = ConfigLoader(
            config_file=str(tmp_path / "missing.json")
        )
        with pytest.raises(
            ConfigurationError,
            match="Configuration file not found",
        ):
            loader._load_json_config()

    def test_valid_json(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(
            json.dumps({"service_name": "test"})
        )
        loader = ConfigLoader(config_file=str(cfg_file))
        result = loader._load_json_config()
        assert result == {"service_name": "test"}

    def test_valid_json_path_object(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(
            json.dumps({"service_name": "test"})
        )
        loader = ConfigLoader(config_file=cfg_file)
        result = loader._load_json_config()
        assert result == {"service_name": "test"}

    def test_invalid_json(self, tmp_path):
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text("not valid json{{{")
        loader = ConfigLoader(config_file=str(cfg_file))
        with pytest.raises(
            ConfigurationError,
            match="Invalid JSON in configuration",
        ):
            loader._load_json_config()

    def test_non_dict_json(self, tmp_path):
        cfg_file = tmp_path / "list.json"
        cfg_file.write_text(json.dumps([1, 2, 3]))
        loader = ConfigLoader(config_file=str(cfg_file))
        result = loader._load_json_config()
        assert result == {}

    def test_generic_read_error(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("{}")
        loader = ConfigLoader(config_file=str(cfg_file))
        with patch(
            "builtins.open",
            side_effect=IOError("disk error"),
        ):
            with pytest.raises(
                ConfigurationError,
                match="Error reading configuration",
            ):
                loader._load_json_config()


class TestConfigLoaderLoadFileConfig:
    """Tests for _load_file_config."""

    def test_file_not_exists(self):
        loader = ConfigLoader()
        with patch("os.path.exists", return_value=False):
            assert loader._load_file_config("x.json") == {}

    def test_file_exists_valid(self):
        loader = ConfigLoader()
        data = json.dumps({"key": "val"})
        with patch("os.path.exists", return_value=True):
            with patch(
                "builtins.open", mock_open(read_data=data)
            ):
                result = loader._load_file_config("x.json")
        assert result == {"key": "val"}

    def test_file_exists_non_dict(self):
        loader = ConfigLoader()
        data = json.dumps([1, 2])
        with patch("os.path.exists", return_value=True):
            with patch(
                "builtins.open", mock_open(read_data=data)
            ):
                result = loader._load_file_config("x.json")
        assert result == {}

    def test_file_not_found_during_read(self):
        loader = ConfigLoader()
        with patch("os.path.exists", return_value=True):
            with patch(
                "builtins.open",
                side_effect=FileNotFoundError,
            ):
                assert (
                    loader._load_file_config("x.json") == {}
                )

    def test_invalid_json_in_file(self):
        loader = ConfigLoader()
        with patch("os.path.exists", return_value=True):
            with patch(
                "builtins.open",
                mock_open(read_data="bad json"),
            ):
                assert (
                    loader._load_file_config("x.json") == {}
                )


class TestConfigLoaderLoadEnvConfig:
    """Tests for _load_env_config."""

    def test_basic_env_vars(self):
        env = {
            "MOHFLOW_SERVICE_NAME": "svc",
            "MOHFLOW_LOG_LEVEL": "DEBUG",
            "MOHFLOW_LOKI_URL": "http://loki:3100",
        }
        with patch.dict(os.environ, env, clear=True):
            loader = ConfigLoader()
            config = loader._load_env_config()
        assert config["service_name"] == "svc"
        assert config["log_level"] == "DEBUG"
        assert config["loki_url"] == "http://loki:3100"

    def test_boolean_env_vars(self):
        env = {
            "MOHFLOW_CONSOLE_LOGGING": "true",
            "MOHFLOW_FILE_LOGGING": "0",
        }
        with patch.dict(os.environ, env, clear=True):
            loader = ConfigLoader()
            config = loader._load_env_config()
        assert config["console_logging"] is True
        assert config["file_logging"] is False

    def test_boolean_yes_on(self):
        env = {
            "MOHFLOW_CONSOLE_LOGGING": "yes",
            "MOHFLOW_FILE_LOGGING": "on",
        }
        with patch.dict(os.environ, env, clear=True):
            loader = ConfigLoader()
            config = loader._load_env_config()
        assert config["console_logging"] is True
        assert config["file_logging"] is True

    def test_nested_env_vars_true_false(self):
        env = {
            "MOHFLOW_CUSTOM_NESTED_ENABLED": "true",
            "MOHFLOW_CUSTOM_NESTED_DISABLED": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            loader = ConfigLoader()
            config = loader._load_env_config()
        assert config["custom"]["nested"]["enabled"] is True
        assert (
            config["custom"]["nested"]["disabled"] is False
        )

    def test_nested_env_vars_integer(self):
        env = {"MOHFLOW_HANDLER_BATCH_SIZE": "500"}
        with patch.dict(os.environ, env, clear=True):
            loader = ConfigLoader()
            config = loader._load_env_config()
        assert config["handler"]["batch"]["size"] == 500

    def test_nested_env_vars_string(self):
        env = {"MOHFLOW_HANDLER_NAME_VALUE": "my-handler"}
        with patch.dict(os.environ, env, clear=True):
            loader = ConfigLoader()
            config = loader._load_env_config()
        assert (
            config["handler"]["name"]["value"]
            == "my-handler"
        )

    def test_nested_env_vars_non_dict_collision(self):
        """When a nested path hits a non-dict value,
        that key is skipped."""
        env = {
            "MOHFLOW_SERVICE_NAME": "svc",
            "MOHFLOW_SERVICE_NAME_EXTRA": "ignored",
        }
        with patch.dict(os.environ, env, clear=True):
            loader = ConfigLoader()
            config = loader._load_env_config()
        # The first one sets service_name as string,
        # the second tries to nest under it but hits break.
        assert config["service_name"] == "svc"


class TestConfigLoaderValidateConfig:
    """Tests for _validate_config."""

    def test_valid(self):
        loader = ConfigLoader()
        assert loader._validate_config(
            {
                "service_name": "svc",
                "log_level": "INFO",
                "environment": "development",
            }
        )

    def test_missing_service_name(self):
        loader = ConfigLoader()
        with pytest.raises(ValueError):
            loader._validate_config({"log_level": "INFO"})

    def test_empty_service_name(self):
        loader = ConfigLoader()
        with pytest.raises(ValueError):
            loader._validate_config({"service_name": ""})

    def test_invalid_log_level(self):
        loader = ConfigLoader()
        with pytest.raises(ValueError):
            loader._validate_config(
                {
                    "service_name": "svc",
                    "log_level": "TRACE",
                }
            )

    def test_invalid_environment(self):
        loader = ConfigLoader()
        with pytest.raises(ConfigurationError):
            loader._validate_config(
                {
                    "service_name": "svc",
                    "environment": "invalid_env",
                }
            )

    def test_file_logging_no_path(self):
        loader = ConfigLoader()
        with pytest.raises(ConfigurationError):
            loader._validate_config(
                {
                    "service_name": "svc",
                    "file_logging": True,
                }
            )

    def test_file_logging_with_path(self):
        loader = ConfigLoader()
        assert loader._validate_config(
            {
                "service_name": "svc",
                "file_logging": True,
                "log_file_path": "/var/log/app.log",
            }
        )

    def test_generic_exception_wrapped(self):
        loader = ConfigLoader()
        # Trigger an unexpected exception inside validation
        with patch.object(
            loader,
            "_validate_config",
            side_effect=ConfigurationError("wrapped"),
        ):
            with pytest.raises(ConfigurationError):
                loader._validate_config(
                    {"service_name": "svc"}
                )


class TestConfigLoaderConvertValue:
    """Tests for _convert_value."""

    def test_true_variants(self):
        loader = ConfigLoader()
        for val in ["true", "1", "yes", "on"]:
            assert loader._convert_value(val) is True

    def test_false_variants(self):
        loader = ConfigLoader()
        for val in ["false", "0", "no", "off"]:
            assert loader._convert_value(val) is False

    def test_integer(self):
        loader = ConfigLoader()
        assert loader._convert_value("42") == 42

    def test_string_fallback(self):
        loader = ConfigLoader()
        assert loader._convert_value("hello") == "hello"


class TestConfigLoaderNormalizeKey:
    """Tests for _normalize_key."""

    def test_normalize(self):
        loader = ConfigLoader()
        assert (
            loader._normalize_key("SOME_KEY") == "some_key"
        )


class TestConfigLoaderValidateAgainstSchema:
    """Tests for validate_against_schema."""

    def test_valid(self):
        loader = ConfigLoader()
        assert loader.validate_against_schema(
            {
                "service_name": "svc",
                "log_level": "INFO",
                "console_logging": True,
                "environment": "development",
            }
        )

    def test_missing_required(self):
        loader = ConfigLoader()
        assert not loader.validate_against_schema(
            {"log_level": "INFO"}
        )

    def test_wrong_type_string(self):
        loader = ConfigLoader()
        assert not loader.validate_against_schema(
            {"service_name": 123}
        )

    def test_wrong_type_boolean(self):
        loader = ConfigLoader()
        assert not loader.validate_against_schema(
            {
                "service_name": "svc",
                "console_logging": "yes",
            }
        )

    def test_wrong_type_integer(self):
        loader = ConfigLoader()
        schema = loader.get_config_schema()
        # Add an integer property for testing
        schema["properties"]["count"] = {"type": "integer"}
        with patch.object(
            loader,
            "get_config_schema",
            return_value=schema,
        ):
            assert not loader.validate_against_schema(
                {"service_name": "svc", "count": "not_int"}
            )

    def test_invalid_enum(self):
        loader = ConfigLoader()
        assert not loader.validate_against_schema(
            {
                "service_name": "svc",
                "log_level": "TRACE",
            }
        )

    def test_exception_returns_false(self):
        loader = ConfigLoader()
        with patch.object(
            loader,
            "get_config_schema",
            side_effect=RuntimeError,
        ):
            assert not loader.validate_against_schema(
                {"service_name": "svc"}
            )


class TestConfigLoaderHelpers:
    """Tests for helper methods."""

    def test_load_config_from_dict(self):
        loader = ConfigLoader()
        with patch.dict(os.environ, {}, clear=True):
            result = loader.load_config_from_dict(
                {"service_name": "svc", "log_level": "INFO"}
            )
        assert result["service_name"] == "svc"

    def test_get_config_value(self):
        loader = ConfigLoader()
        with patch.object(
            loader,
            "load_config",
            return_value={"key": "val"},
        ):
            assert loader.get_config_value("key") == "val"
            assert (
                loader.get_config_value("missing", "def")
                == "def"
            )

    def test_has_config_file_true(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        loader = ConfigLoader(config_file=str(cfg))
        assert loader.has_config_file() is True

    def test_has_config_file_false_missing(self):
        loader = ConfigLoader(
            config_file="/nonexistent/file.json"
        )
        assert loader.has_config_file() is False

    def test_has_config_file_false_none(self):
        loader = ConfigLoader()
        assert loader.has_config_file() is False

    def test_get_env_config(self):
        loader = ConfigLoader()
        env = {"MOHFLOW_SERVICE_NAME": "env-svc"}
        with patch.dict(os.environ, env, clear=True):
            result = loader.get_env_config()
        assert result["service_name"] == "env-svc"

    def test_get_default_config(self):
        loader = ConfigLoader()
        defaults = loader._get_default_config()
        assert defaults["environment"] == "development"
        assert defaults["log_level"] == "INFO"
        assert defaults["console_logging"] is True
        assert defaults["file_logging"] is False
        assert "handlers" in defaults
        assert "context_enrichment" in defaults


class TestConfigLoaderMergeConfigs:
    """Tests for _merge_configs."""

    def test_empty_config_skipped(self):
        loader = ConfigLoader()
        result = loader._merge_configs(
            {"a": 1}, {}, {"b": 2}
        )
        assert result == {"a": 1, "b": 2}

    def test_none_config_skipped(self):
        loader = ConfigLoader()
        result = loader._merge_configs(
            {"a": 1}, None, {"b": 2}
        )
        assert result == {"a": 1, "b": 2}

    def test_recursive_merge(self):
        loader = ConfigLoader()
        result = loader._merge_configs(
            {"nested": {"a": 1, "b": 2}},
            {"nested": {"b": 3, "c": 4}},
        )
        assert result == {"nested": {"a": 1, "b": 3, "c": 4}}


class TestConfigLoaderLoadConfig:
    """Tests for load_config (full integration)."""

    def test_load_config_full(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(
            json.dumps(
                {
                    "service_name": "file-svc",
                    "environment": "development",
                }
            )
        )
        loader = ConfigLoader(config_file=str(cfg))
        with patch.dict(os.environ, {}, clear=True):
            config = loader.load_config()
        assert config["service_name"] == "file-svc"

    def test_load_config_runtime_overrides(self):
        loader = ConfigLoader()
        with patch.dict(os.environ, {}, clear=True):
            config = loader.load_config(
                service_name="runtime-svc",
                log_level="ERROR",
            )
        assert config["service_name"] == "runtime-svc"
        assert config["log_level"] == "ERROR"

    def test_load_config_none_params_filtered(self):
        loader = ConfigLoader()
        with patch.dict(os.environ, {}, clear=True):
            config = loader.load_config(
                service_name="svc", extra=None
            )
        assert "extra" not in config


class TestConfigLoaderCreateSampleConfig:
    """Tests for create_sample_config."""

    def test_create_sample(self, tmp_path):
        loader = ConfigLoader()
        output = tmp_path / "sample.json"
        loader.create_sample_config(output)
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["service_name"] == "my-service"
        assert data["environment"] == "development"

    def test_create_sample_error(self):
        loader = ConfigLoader()
        with patch(
            "builtins.open", side_effect=OSError("no perms")
        ):
            with pytest.raises(
                ConfigurationError,
                match="Failed to create",
            ):
                loader.create_sample_config(
                    "/bad/path/sample.json"
                )


class TestConfigLoaderConvenienceFunction:
    """Tests for the module-level load_config function."""

    def test_load_config_convenience(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(
                service_name="conv-svc",
                log_level="WARNING",
            )
        assert config["service_name"] == "conv-svc"


# ===============================================================
# FRAMEWORK_DETECTION TESTS
# ===============================================================


def _mock_module_available(names):
    """Return a side_effect for _is_module_available
    that returns True only for listed names."""

    def side_effect(module_name):
        return module_name in names

    return side_effect


class TestFrameworkInfo:
    """Tests for FrameworkInfo dataclass."""

    def test_defaults(self):
        fi = FrameworkInfo(name="test")
        assert fi.version is None
        assert fi.is_async is False
        assert fi.default_log_level == "INFO"
        assert fi.recommended_formatter == "structured"
        assert fi.custom_config is None


class TestApplicationInfo:
    """Tests for ApplicationInfo dataclass."""

    def test_defaults(self):
        ai = ApplicationInfo()
        assert ai.app_type == "unknown"
        assert ai.frameworks == []
        assert ai.uses_async is False

    def test_post_init_none_frameworks(self):
        ai = ApplicationInfo(frameworks=None)
        assert ai.frameworks == []


class TestFrameworkDetectorDetection:
    """Tests for individual framework detection methods."""

    def _detector(self):
        return FrameworkDetector()

    def test_detect_flask(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"flask"}),
        ), patch.object(
            fd, "_get_module_version", return_value="2.3.0"
        ):
            result = fd._detect_web_frameworks()
        assert len(result) == 1
        assert result[0].name == "flask"
        assert result[0].version == "2.3.0"
        assert result[0].has_middleware_support is True

    def test_detect_django(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"django"}),
        ), patch.object(
            fd, "_get_module_version", return_value="4.2"
        ):
            result = fd._detect_web_frameworks()
        assert len(result) == 1
        assert result[0].name == "django"

    def test_detect_no_web_frameworks(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            result = fd._detect_web_frameworks()
        assert result == []

    def test_detect_fastapi(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"fastapi"}),
        ), patch.object(
            fd, "_get_module_version", return_value="0.100"
        ):
            result = fd._detect_async_frameworks()
        assert len(result) == 1
        assert result[0].name == "fastapi"
        assert result[0].is_async is True

    def test_detect_aiohttp(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"aiohttp"}),
        ), patch.object(
            fd, "_get_module_version", return_value="3.8"
        ):
            result = fd._detect_async_frameworks()
        assert len(result) == 1
        assert result[0].name == "aiohttp"

    def test_detect_sanic(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"sanic"}),
        ), patch.object(
            fd, "_get_module_version", return_value="23.0"
        ):
            result = fd._detect_async_frameworks()
        assert len(result) == 1
        assert result[0].name == "sanic"

    def test_detect_flask_restful(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available(
                {"flask_restful"}
            ),
        ), patch.object(
            fd, "_get_module_version", return_value="0.3"
        ):
            result = fd._detect_api_frameworks()
        assert len(result) == 1
        assert result[0].name == "flask_restful"

    def test_detect_drf(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available(
                {"rest_framework"}
            ),
        ), patch.object(
            fd, "_get_module_version", return_value="3.14"
        ):
            result = fd._detect_api_frameworks()
        assert len(result) == 1
        assert result[0].name == "django_rest_framework"

    def test_detect_celery(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"celery"}),
        ), patch.object(
            fd, "_get_module_version", return_value="5.3"
        ):
            result = fd._detect_task_frameworks()
        assert len(result) == 1
        assert result[0].name == "celery"

    def test_detect_rq(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"rq"}),
        ), patch.object(
            fd, "_get_module_version", return_value="1.0"
        ):
            result = fd._detect_task_frameworks()
        assert len(result) == 1
        assert result[0].name == "rq"

    def test_detect_sqlalchemy(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available(
                {"sqlalchemy"}
            ),
        ), patch.object(
            fd, "_get_module_version", return_value="2.0"
        ):
            result = fd._detect_database_frameworks()
        assert len(result) == 1
        assert result[0].name == "sqlalchemy"

    def test_detect_no_db_frameworks(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            result = fd._detect_database_frameworks()
        assert result == []

    def test_detect_pytest(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"pytest"}),
        ), patch.object(
            fd, "_get_module_version", return_value="7.0"
        ):
            result = fd._detect_testing_frameworks()
        assert len(result) == 1
        assert result[0].name == "pytest"
        assert result[0].default_log_level == "DEBUG"

    def test_detect_gunicorn(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"gunicorn"}),
        ), patch.object(
            fd, "_get_module_version", return_value="21.0"
        ):
            result = fd._detect_production_frameworks()
        assert any(f.name == "gunicorn" for f in result)

    def test_detect_uvicorn(self):
        fd = self._detector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"uvicorn"}),
        ), patch.object(
            fd, "_get_module_version", return_value="0.20"
        ):
            result = fd._detect_production_frameworks()
        assert any(f.name == "uvicorn" for f in result)
        uvi = [
            f for f in result if f.name == "uvicorn"
        ][0]
        assert uvi.is_async is True


class TestFrameworkDetectorDetectFrameworks:
    """Tests for detect_frameworks and caching."""

    def test_detect_all_cached(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            first = fd.detect_frameworks()
            second = fd.detect_frameworks()
        assert first is second

    def test_detect_force_refresh(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            first = fd.detect_frameworks()
            second = fd.detect_frameworks(force_refresh=True)
        assert first is not second


class TestFrameworkDetectorAppType:
    """Tests for _determine_app_type."""

    def test_web_type(self):
        fd = FrameworkDetector()
        fws = [FrameworkInfo(name="flask")]
        assert fd._determine_app_type(fws) == "web"

    def test_api_type(self):
        fd = FrameworkDetector()
        fws = [FrameworkInfo(name="flask_restful")]
        assert fd._determine_app_type(fws) == "api"

    def test_worker_type(self):
        fd = FrameworkDetector()
        fws = [FrameworkInfo(name="celery")]
        assert fd._determine_app_type(fws) == "worker"

    def test_test_type(self):
        fd = FrameworkDetector()
        fws = [FrameworkInfo(name="pytest")]
        assert fd._determine_app_type(fws) == "test"

    def test_cli_type_click(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"click"}),
        ):
            assert fd._determine_app_type([]) == "cli"

    def test_cli_type_argparse(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ), patch.object(
            fd,
            "_detect_cli_patterns",
            return_value=True,
        ):
            assert fd._determine_app_type([]) == "cli"

    def test_library_type(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ), patch.object(
            fd,
            "_detect_cli_patterns",
            return_value=False,
        ):
            assert fd._determine_app_type([]) == "library"


class TestFrameworkDetectorAsyncUsage:
    """Tests for _detect_async_usage."""

    def test_async_from_framework(self):
        fd = FrameworkDetector()
        fws = [FrameworkInfo(name="fastapi", is_async=True)]
        assert fd._detect_async_usage(fws) is True

    def test_async_from_asyncio(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"asyncio"}),
        ):
            assert fd._detect_async_usage([]) is True

    def test_no_async(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert fd._detect_async_usage([]) is False


class TestFrameworkDetectorDeploymentType:
    """Tests for _determine_deployment_type."""

    @patch.dict(
        os.environ,
        {"AWS_LAMBDA_FUNCTION_NAME": "my-func"},
        clear=False,
    )
    def test_serverless_lambda(self):
        fd = FrameworkDetector()
        assert (
            fd._determine_deployment_type([], "api")
            == "serverless"
        )

    @patch.dict(
        os.environ,
        {"FUNCTIONS_WORKER_RUNTIME": "python"},
        clear=False,
    )
    def test_serverless_azure_functions(self):
        fd = FrameworkDetector()
        assert (
            fd._determine_deployment_type([], "web")
            == "serverless"
        )

    @patch.dict(
        os.environ,
        {"KUBERNETES_SERVICE_HOST": "10.0.0.1"},
        clear=False,
    )
    def test_microservice_k8s_env(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert (
                fd._determine_deployment_type([], "web")
                == "microservice"
            )

    def test_microservice_fastapi(self):
        fd = FrameworkDetector()
        fws = [FrameworkInfo(name="fastapi")]
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert (
                fd._determine_deployment_type(fws, "web")
                == "microservice"
            )

    def test_microservice_api_type(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert (
                fd._determine_deployment_type([], "api")
                == "microservice"
            )

    def test_microservice_worker_type(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert (
                fd._determine_deployment_type([], "worker")
                == "microservice"
            )

    def test_monolith_default(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert (
                fd._determine_deployment_type([], "web")
                == "monolith"
            )


class TestFrameworkDetectorDependencyDetection:
    """Tests for _detect_database_usage, _detect_cache_usage, etc."""

    def test_database_usage(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available(
                {"sqlalchemy"}
            ),
        ):
            assert fd._detect_database_usage() is True

    def test_no_database(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert fd._detect_database_usage() is False

    def test_cache_usage(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"redis"}),
        ):
            assert fd._detect_cache_usage() is True

    def test_no_cache(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert fd._detect_cache_usage() is False

    def test_message_queue_usage(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"pika"}),
        ):
            assert fd._detect_message_queue_usage() is True

    def test_no_message_queue(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert fd._detect_message_queue_usage() is False

    def test_external_api_usage(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            side_effect=_mock_module_available({"requests"}),
        ):
            assert fd._detect_external_api_usage() is True

    def test_no_external_apis(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ):
            assert fd._detect_external_api_usage() is False


class TestFrameworkDetectorCliPatterns:
    """Tests for _detect_cli_patterns."""

    def test_argparse_detected(self):
        fd = FrameworkDetector()
        with patch(
            "builtins.open",
            mock_open(read_data="import argparse\n"),
        ):
            mock_main = MagicMock()
            mock_main.__file__ = "/app/main.py"
            with patch.dict(
                "sys.modules", {"__main__": mock_main}
            ):
                assert fd._detect_cli_patterns() is True

    def test_click_detected(self):
        fd = FrameworkDetector()
        with patch(
            "builtins.open",
            mock_open(read_data="import click\n"),
        ):
            mock_main = MagicMock()
            mock_main.__file__ = "/app/main.py"
            with patch.dict(
                "sys.modules", {"__main__": mock_main}
            ):
                assert fd._detect_cli_patterns() is True

    def test_no_cli_patterns(self):
        fd = FrameworkDetector()
        with patch(
            "builtins.open",
            mock_open(read_data="import os\n"),
        ):
            mock_main = MagicMock()
            mock_main.__file__ = "/app/main.py"
            with patch.dict(
                "sys.modules", {"__main__": mock_main}
            ):
                assert fd._detect_cli_patterns() is False

    def test_no_main_file(self):
        fd = FrameworkDetector()
        mock_main = MagicMock(spec=[])
        with patch.dict(
            "sys.modules", {"__main__": mock_main}
        ):
            assert fd._detect_cli_patterns() is False

    def test_exception_handling(self):
        fd = FrameworkDetector()
        with patch(
            "builtins.open",
            side_effect=IOError("cannot read"),
        ):
            mock_main = MagicMock()
            mock_main.__file__ = "/app/main.py"
            with patch.dict(
                "sys.modules", {"__main__": mock_main}
            ):
                assert fd._detect_cli_patterns() is False


class TestFrameworkDetectorAppTypeConfig:
    """Tests for _get_app_type_config."""

    def test_web_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(app_type="web")
        config = fd._get_app_type_config(ai)
        assert config["formatter_type"] == "structured"
        assert config["enable_context_enrichment"] is True

    def test_api_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(app_type="api")
        config = fd._get_app_type_config(ai)
        assert config["formatter_type"] == "structured"
        assert config["log_level"] == "INFO"

    def test_worker_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(app_type="worker")
        config = fd._get_app_type_config(ai)
        assert config["file_logging"] is True
        assert config["console_logging"] is False

    def test_cli_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(app_type="cli")
        config = fd._get_app_type_config(ai)
        assert config["formatter_type"] == "development"
        assert config["console_logging"] is True

    def test_test_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(app_type="test")
        config = fd._get_app_type_config(ai)
        assert config["log_level"] == "DEBUG"

    def test_unknown_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(app_type="unknown")
        config = fd._get_app_type_config(ai)
        assert config == {}


class TestFrameworkDetectorPerformanceConfig:
    """Tests for _get_performance_config."""

    def test_async_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(uses_async=True)
        config = fd._get_performance_config(ai)
        assert config["async_handlers"] is True
        assert config["formatter_type"] == "fast"

    def test_microservice_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(
            deployment_type="microservice"
        )
        config = fd._get_performance_config(ai)
        assert config["formatter_type"] == "production"
        assert config["async_handlers"] is True

    def test_no_special_config(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(
            uses_async=False, deployment_type="monolith"
        )
        config = fd._get_performance_config(ai)
        assert config == {}


class TestFrameworkDetectorIntegrationConfig:
    """Tests for _get_integration_config."""

    def test_database_integration(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(has_database=True)
        config = fd._get_integration_config(ai)
        ce = config["context_enrichment"]
        assert ce["custom_fields"]["has_database"] is True

    def test_external_api_integration(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(has_external_apis=True)
        config = fd._get_integration_config(ai)
        assert config["enable_context_enrichment"] is True
        assert (
            config["context_enrichment"][
                "include_request_id"
            ]
            is True
        )

    def test_both_db_and_api(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo(
            has_database=True, has_external_apis=True
        )
        config = fd._get_integration_config(ai)
        ce = config["context_enrichment"]
        assert ce["custom_fields"]["has_database"] is True
        assert ce["include_request_id"] is True

    def test_no_integration(self):
        fd = FrameworkDetector()
        ai = ApplicationInfo()
        config = fd._get_integration_config(ai)
        assert config == {}


class TestFrameworkDetectorModuleUtils:
    """Tests for _is_module_available and
    _get_module_version."""

    def test_is_module_available_true(self):
        fd = FrameworkDetector()
        assert fd._is_module_available("os") is True

    def test_is_module_available_false(self):
        fd = FrameworkDetector()
        assert (
            fd._is_module_available(
                "nonexistent_module_xyz"
            )
            is False
        )

    def test_get_module_version_with_version(self):
        fd = FrameworkDetector()
        mock_mod = MagicMock()
        mock_mod.__version__ = "1.2.3"
        with patch(
            "importlib.import_module",
            return_value=mock_mod,
        ):
            assert fd._get_module_version("fake") == "1.2.3"

    def test_get_module_version_no_version_attr(self):
        fd = FrameworkDetector()
        mock_mod = MagicMock(spec=[])
        with patch(
            "importlib.import_module",
            return_value=mock_mod,
        ):
            assert fd._get_module_version("fake") is None

    def test_get_module_version_import_error(self):
        fd = FrameworkDetector()
        with patch(
            "importlib.import_module",
            side_effect=ImportError,
        ):
            assert fd._get_module_version("bad") is None


class TestFrameworkDetectorDetectAppType:
    """Tests for detect_application_type (full)."""

    def test_cached(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ), patch.object(
            fd,
            "_detect_cli_patterns",
            return_value=False,
        ):
            first = fd.detect_application_type()
            second = fd.detect_application_type()
        assert first is second

    def test_full_detection(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ), patch.object(
            fd,
            "_detect_cli_patterns",
            return_value=False,
        ):
            app = fd.detect_application_type()
        assert app.app_type == "library"


class TestFrameworkDetectorGetOptimizedConfig:
    """Tests for get_optimized_config."""

    def test_basic(self):
        fd = FrameworkDetector()
        with patch.object(
            fd,
            "_is_module_available",
            return_value=False,
        ), patch.object(
            fd,
            "_detect_cli_patterns",
            return_value=False,
        ):
            config = fd.get_optimized_config()
        assert isinstance(config, dict)

    def test_with_custom_config(self):
        fd = FrameworkDetector()
        fw = FrameworkInfo(
            name="flask",
            custom_config={"extra": "value"},
        )
        app = ApplicationInfo(
            app_type="web",
            deployment_type="monolith",
            frameworks=[fw],
        )
        with patch.object(
            fd,
            "detect_application_type",
            return_value=app,
        ):
            config = fd.get_optimized_config()
        assert config.get("extra") == "value"


class TestFrameworkDetectorGetFrameworkSummary:
    """Tests for get_framework_summary."""

    def test_summary(self):
        fd = FrameworkDetector()
        fw = FrameworkInfo(
            name="fastapi",
            version="0.100",
            is_async=True,
            recommended_formatter="fast",
        )
        app = ApplicationInfo(
            app_type="web",
            deployment_type="microservice",
            uses_async=True,
            has_database=True,
            has_cache=False,
            has_message_queue=False,
            has_external_apis=True,
            frameworks=[fw],
        )
        with patch.object(
            fd,
            "detect_application_type",
            return_value=app,
        ):
            summary = fd.get_framework_summary()
        assert summary["app_type"] == "web"
        assert summary["uses_async"] is True
        assert len(summary["frameworks"]) == 1
        assert (
            summary["capabilities"]["database"] is True
        )
        assert summary["capabilities"]["cache"] is False


class TestFrameworkDetectionConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_detect_frameworks_func(self):
        with patch(
            "mohflow.framework_detection._framework_detector"
        ) as mock_fd:
            mock_fd.detect_frameworks.return_value = []
            result = detect_frameworks(force_refresh=True)
            assert result == []
            mock_fd.detect_frameworks.assert_called_once_with(
                True
            )

    def test_detect_application_type_func(self):
        with patch(
            "mohflow.framework_detection._framework_detector"
        ) as mock_fd:
            mock_fd.detect_application_type.return_value = (
                ApplicationInfo()
            )
            result = detect_application_type()
            assert result.app_type == "unknown"

    def test_get_framework_optimized_config_func(self):
        with patch(
            "mohflow.framework_detection._framework_detector"
        ) as mock_fd:
            mock_fd.get_optimized_config.return_value = {
                "key": "val"
            }
            result = get_framework_optimized_config()
            assert result == {"key": "val"}

    def test_get_framework_summary_func(self):
        with patch(
            "mohflow.framework_detection._framework_detector"
        ) as mock_fd:
            mock_fd.get_framework_summary.return_value = {
                "summary": True
            }
            result = get_framework_summary()
            assert result == {"summary": True}
