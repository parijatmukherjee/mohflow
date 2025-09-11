"""Tests for dashboard template manager module."""

import pytest
import json
from unittest.mock import Mock, patch, mock_open
from mohflow.templates.template_manager import (
    TemplateManager,
    deploy_grafana_dashboard,
    deploy_kibana_dashboard,
    list_available_templates,
)


class TestTemplateManager:
    """Test cases for TemplateManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = TemplateManager()

    def test_manager_initialization(self):
        """Test TemplateManager initialization."""
        assert self.manager is not None
        assert hasattr(self.manager, "get_available_templates")
        assert hasattr(self.manager, "load_template")

    @patch("os.path.exists")
    @patch("os.listdir")
    def test_get_available_templates(self, mock_listdir, mock_exists):
        """Test getting available templates."""
        mock_exists.return_value = True
        mock_listdir.return_value = [
            "application_logs.json",
            "error_tracking.json",
            "performance_metrics.json",
            "readme.txt",  # Should be filtered out
        ]

        templates = self.manager.get_available_templates()

        expected = [
            "application_logs",
            "error_tracking",
            "performance_metrics",
        ]
        assert templates == expected

    @patch("os.path.exists")
    def test_get_available_templates_no_directory(self, mock_exists):
        """Test getting templates when directory doesn't exist."""
        mock_exists.return_value = False

        templates = self.manager.get_available_templates()

        assert templates == []

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.path.exists")
    def test_load_template_success(self, mock_exists, mock_file):
        """Test successful template loading."""
        template_data = {
            "dashboard": {"title": "Application Logs", "panels": []}
        }

        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps(template_data)

        result = self.manager.load_template("application_logs")

        assert result == template_data

    @patch("os.path.exists")
    def test_load_template_not_found(self, mock_exists):
        """Test loading template that doesn't exist."""
        mock_exists.return_value = False

        with pytest.raises(FileNotFoundError):
            self.manager.load_template("nonexistent_template")

    @patch("builtins.open", new_callable=mock_open)
    @patch("os.path.exists")
    def test_load_template_invalid_json(self, mock_exists, mock_file):
        """Test loading template with invalid JSON."""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = "invalid json"

        with pytest.raises(json.JSONDecodeError):
            self.manager.load_template("invalid_template")

    @patch("requests.post")
    @patch.object(TemplateManager, "load_template")
    def test_deploy_grafana_dashboard_success(
        self, mock_load_template, mock_post
    ):
        """Test successful Grafana dashboard deployment."""
        template_data = {
            "dashboard": {"title": "Test Dashboard", "panels": []}
        }

        mock_load_template.return_value = template_data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "status": "success"}
        mock_post.return_value = mock_response

        result = self.manager.deploy_grafana_dashboard(
            template_name="application_logs",
            grafana_url="http://localhost:3000",
            api_key="test-api-key",
        )

        assert result["status"] == "success"
        mock_post.assert_called_once()

    @patch("requests.post")
    @patch.object(TemplateManager, "load_template")
    def test_deploy_grafana_dashboard_with_datasource(
        self, mock_load_template, mock_post
    ):
        """Test Grafana dashboard deployment with custom datasource."""
        template_data = {
            "dashboard": {
                "title": "Test Dashboard",
                "panels": [{"datasource": "${DS_LOKI}"}],
            }
        }

        mock_load_template.return_value = template_data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "status": "success"}
        mock_post.return_value = mock_response

        self.manager.deploy_grafana_dashboard(
            template_name="application_logs",
            grafana_url="http://localhost:3000",
            api_key="test-api-key",
            datasource_name="Custom-Loki",
        )

        # Check that datasource was replaced
        call_args = mock_post.call_args
        posted_data = json.loads(call_args[1]["data"])
        assert (
            posted_data["dashboard"]["panels"][0]["datasource"]
            == "Custom-Loki"
        )

    @patch("requests.post")
    @patch.object(TemplateManager, "load_template")
    def test_deploy_grafana_dashboard_failure(
        self, mock_load_template, mock_post
    ):
        """Test Grafana dashboard deployment failure."""
        template_data = {"dashboard": {"title": "Test Dashboard"}}

        mock_load_template.return_value = template_data
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        with pytest.raises(Exception, match="Failed to deploy dashboard"):
            self.manager.deploy_grafana_dashboard(
                template_name="application_logs",
                grafana_url="http://localhost:3000",
                api_key="test-api-key",
            )

    @patch("requests.post")
    @patch.object(TemplateManager, "load_template")
    def test_deploy_kibana_dashboard_success(
        self, mock_load_template, mock_post
    ):
        """Test successful Kibana dashboard deployment."""
        template_data = {
            "objects": [
                {
                    "type": "dashboard",
                    "attributes": {"title": "Test Dashboard"},
                }
            ]
        }

        mock_load_template.return_value = template_data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response

        result = self.manager.deploy_kibana_dashboard(
            template_name="error_tracking", kibana_url="http://localhost:5601"
        )

        assert result["success"] is True
        mock_post.assert_called_once()

    @patch("requests.post")
    @patch.object(TemplateManager, "load_template")
    def test_deploy_kibana_dashboard_with_index_pattern(
        self, mock_load_template, mock_post
    ):
        """Test Kibana dashboard deployment with custom index pattern."""
        template_data = {
            "objects": [
                {"type": "index-pattern", "attributes": {"title": "logs-*"}}
            ]
        }

        mock_load_template.return_value = template_data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response

        self.manager.deploy_kibana_dashboard(
            template_name="error_tracking",
            kibana_url="http://localhost:5601",
            index_pattern="custom-logs-*",
        )

        # Check that index pattern was replaced
        call_args = mock_post.call_args
        posted_data = json.loads(call_args[1]["data"])
        index_pattern_obj = next(
            obj
            for obj in posted_data["objects"]
            if obj["type"] == "index-pattern"
        )
        assert index_pattern_obj["attributes"]["title"] == "custom-logs-*"

    @patch("requests.post")
    @patch.object(TemplateManager, "load_template")
    def test_deploy_kibana_dashboard_failure(
        self, mock_load_template, mock_post
    ):
        """Test Kibana dashboard deployment failure."""
        template_data = {"objects": []}

        mock_load_template.return_value = template_data
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(Exception, match="Failed to deploy dashboard"):
            self.manager.deploy_kibana_dashboard(
                template_name="error_tracking",
                kibana_url="http://localhost:5601",
            )

    def test_validate_template_structure_grafana(self):
        """Test Grafana template structure validation."""
        valid_template = {
            "dashboard": {"title": "Test Dashboard", "panels": []}
        }

        # Should not raise an exception
        self.manager._validate_grafana_template(valid_template)

    def test_validate_template_structure_grafana_invalid(self):
        """Test Grafana template structure validation with invalid template."""
        invalid_template = {
            "dashboard": {
                # Missing required 'title' field
                "panels": []
            }
        }

        with pytest.raises(ValueError, match="Invalid Grafana template"):
            self.manager._validate_grafana_template(invalid_template)

    def test_validate_template_structure_kibana(self):
        """Test Kibana template structure validation."""
        valid_template = {
            "objects": [
                {
                    "type": "dashboard",
                    "attributes": {"title": "Test Dashboard"},
                }
            ]
        }

        # Should not raise an exception
        self.manager._validate_kibana_template(valid_template)

    def test_validate_template_structure_kibana_invalid(self):
        """Test Kibana template structure validation with invalid template."""
        invalid_template = {
            "objects": [
                {
                    "type": "dashboard",
                    # Missing required 'attributes' field
                }
            ]
        }

        with pytest.raises(ValueError, match="Invalid Kibana template"):
            self.manager._validate_kibana_template(invalid_template)

    def test_replace_template_variables(self):
        """Test template variable replacement."""
        template = {
            "title": "${SERVICE_NAME} Dashboard",
            "panels": [
                {
                    "datasource": "${DS_LOKI}",
                    "query": 'service="${SERVICE_NAME}"',
                }
            ],
        }

        variables = {
            "${SERVICE_NAME}": "my-service",
            "${DS_LOKI}": "Loki-Prod",
        }

        result = self.manager._replace_variables(template, variables)

        assert result["title"] == "my-service Dashboard"
        assert result["panels"][0]["datasource"] == "Loki-Prod"
        assert result["panels"][0]["query"] == 'service="my-service"'

    @patch("requests.get")
    def test_check_grafana_connectivity(self, mock_get):
        """Test Grafana connectivity check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.manager._check_grafana_connectivity(
            "http://localhost:3000", "test-api-key"
        )

        assert result is True

    @patch("requests.get")
    def test_check_grafana_connectivity_failure(self, mock_get):
        """Test Grafana connectivity check failure."""
        mock_get.side_effect = Exception("Connection failed")

        result = self.manager._check_grafana_connectivity(
            "http://localhost:3000", "test-api-key"
        )

        assert result is False

    @patch("requests.get")
    def test_check_kibana_connectivity(self, mock_get):
        """Test Kibana connectivity check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = self.manager._check_kibana_connectivity(
            "http://localhost:5601"
        )

        assert result is True


class TestModuleFunctions:
    """Test cases for module-level functions."""

    @patch.object(TemplateManager, "get_available_templates")
    def test_list_available_templates(self, mock_get_templates):
        """Test list_available_templates function."""
        mock_get_templates.return_value = ["template1", "template2"]

        result = list_available_templates()

        assert result == ["template1", "template2"]

    @patch.object(TemplateManager, "deploy_grafana_dashboard")
    def test_deploy_grafana_dashboard_function(self, mock_deploy):
        """Test deploy_grafana_dashboard function."""
        mock_deploy.return_value = {"status": "success"}

        result = deploy_grafana_dashboard(
            template_name="test",
            grafana_url="http://localhost:3000",
            api_key="test-key",
        )

        assert result["status"] == "success"
        mock_deploy.assert_called_once_with(
            template_name="test",
            grafana_url="http://localhost:3000",
            api_key="test-key",
            datasource_name=None,
        )

    @patch.object(TemplateManager, "deploy_kibana_dashboard")
    def test_deploy_kibana_dashboard_function(self, mock_deploy):
        """Test deploy_kibana_dashboard function."""
        mock_deploy.return_value = {"success": True}

        result = deploy_kibana_dashboard(
            template_name="test", kibana_url="http://localhost:5601"
        )

        assert result["success"] is True
        mock_deploy.assert_called_once_with(
            template_name="test",
            kibana_url="http://localhost:5601",
            index_pattern=None,
        )
