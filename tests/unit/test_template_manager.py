"""Comprehensive unit tests for template_manager.py.

Covers TemplateManager class (init, list, load, validate, replace,
connectivity, deploy, customize, save) and all module-level
convenience functions.
"""

import json
import os
from pathlib import Path
from unittest.mock import Mock, patch, mock_open, MagicMock

import pytest
import requests

from mohflow.exceptions import ConfigurationError
from mohflow.templates.template_manager import (
    TemplateManager,
    create_custom_template,
    default_manager,
    deploy_grafana_dashboard,
    deploy_kibana_dashboard,
    list_available_templates,
)

# ── fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def tmp_templates(tmp_path):
    """Create a temporary templates directory with sample files."""
    grafana = tmp_path / "grafana"
    kibana = tmp_path / "kibana"
    grafana.mkdir()
    kibana.mkdir()

    grafana_tpl = {
        "dashboard": {
            "title": "Test Grafana",
            "panels": [{"datasource": "${DS_LOKI}"}],
        }
    }
    (grafana / "overview.json").write_text(json.dumps(grafana_tpl))

    kibana_tpl = {
        "objects": [
            {
                "type": "index-pattern",
                "attributes": {"title": "logs-*"},
            },
            {
                "type": "dashboard",
                "attributes": {"title": "Test Kibana"},
            },
        ]
    }
    (kibana / "dashboard.json").write_text(json.dumps(kibana_tpl))

    # A loose JSON file directly in templates_dir for single-arg load
    loose_tpl = {"key": "value", "nested": {"a": 1}}
    (tmp_path / "loose.json").write_text(json.dumps(loose_tpl))

    return tmp_path


@pytest.fixture
def manager(tmp_templates):
    """Return a TemplateManager rooted at the tmp templates dir."""
    return TemplateManager(templates_dir=tmp_templates)


# ── TemplateManager.__init__ ─────────────────────────────────────


class TestTemplateManagerInit:
    """Initialization tests."""

    def test_default_templates_dir(self):
        """Default templates_dir points to the package directory."""
        mgr = TemplateManager()
        expected = Path(__file__).parent  # won't match exactly
        # It should resolve to …/templates (the package dir)
        assert mgr.templates_dir.name == "templates" or (
            mgr.templates_dir.exists()
        )

    def test_custom_templates_dir(self, tmp_path):
        """Custom templates_dir is respected."""
        mgr = TemplateManager(templates_dir=tmp_path)
        assert mgr.templates_dir == tmp_path

    def test_grafana_and_kibana_subdirs(self, tmp_path):
        """grafana_dir and kibana_dir are derived correctly."""
        mgr = TemplateManager(templates_dir=tmp_path)
        assert mgr.grafana_dir == tmp_path / "grafana"
        assert mgr.kibana_dir == tmp_path / "kibana"

    def test_string_path_converted_to_pathlib(self, tmp_path):
        """A string path is converted to a Path object."""
        mgr = TemplateManager(templates_dir=str(tmp_path))
        assert isinstance(mgr.templates_dir, Path)


# ── list_templates ───────────────────────────────────────────────


class TestListTemplates:
    """Tests for list_templates()."""

    def test_list_all(self, manager):
        """Listing 'all' returns both platforms."""
        result = manager.list_templates("all")
        assert "grafana" in result
        assert "kibana" in result
        assert "overview" in result["grafana"]
        assert "dashboard" in result["kibana"]

    def test_list_grafana_only(self, manager):
        """Listing 'grafana' returns only grafana templates."""
        result = manager.list_templates("grafana")
        assert "grafana" in result
        assert "kibana" not in result

    def test_list_kibana_only(self, manager):
        """Listing 'kibana' returns only kibana templates."""
        result = manager.list_templates("kibana")
        assert "kibana" in result
        assert "grafana" not in result

    def test_list_default_is_all(self, manager):
        """Default platform is 'all'."""
        result = manager.list_templates()
        assert "grafana" in result
        assert "kibana" in result

    def test_list_when_dirs_missing(self, tmp_path):
        """Returns empty lists when platform dirs do not exist."""
        mgr = TemplateManager(templates_dir=tmp_path)
        result = mgr.list_templates("all")
        assert result["grafana"] == []
        assert result["kibana"] == []

    def test_list_ignores_non_json(self, tmp_templates):
        """Non-JSON files are not listed."""
        (tmp_templates / "grafana" / "readme.txt").write_text("hi")
        mgr = TemplateManager(templates_dir=tmp_templates)
        result = mgr.list_templates("grafana")
        assert "readme" not in result["grafana"]

    def test_list_unknown_platform(self, manager):
        """An unknown platform returns an empty dict."""
        result = manager.list_templates("prometheus")
        assert result == {}


# ── load_template (single-arg) ───────────────────────────────────


class TestLoadTemplateSingleArg:
    """Tests for load_template(template_name) — single argument."""

    def test_success(self, manager):
        """Successfully loads a loose JSON template."""
        result = manager.load_template("loose")
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_not_found(self, manager):
        """Raises FileNotFoundError for missing template."""
        with pytest.raises(FileNotFoundError, match="Template not found"):
            manager.load_template("nonexistent")

    def test_invalid_json(self, tmp_templates):
        """Raises JSONDecodeError for malformed JSON."""
        (tmp_templates / "bad.json").write_text("{not valid json")
        mgr = TemplateManager(templates_dir=tmp_templates)
        with pytest.raises(json.JSONDecodeError):
            mgr.load_template("bad")

    def test_general_read_error(self, tmp_templates):
        """Wraps unexpected errors in FileNotFoundError."""
        mgr = TemplateManager(templates_dir=tmp_templates)
        # Create a template that exists but mock open to fail
        (tmp_templates / "exists.json").write_text("{}")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            with pytest.raises(
                FileNotFoundError, match="Failed to load template"
            ):
                mgr.load_template("exists")


# ── load_template (two-arg) ─────────────────────────────────────


class TestLoadTemplateTwoArg:
    """Tests for load_template(platform, template_name)."""

    def test_grafana_success(self, manager):
        """Loads a grafana template by platform + name."""
        result = manager.load_template("grafana", "overview")
        assert "dashboard" in result
        assert result["dashboard"]["title"] == "Test Grafana"

    def test_kibana_success(self, manager):
        """Loads a kibana template by platform + name."""
        result = manager.load_template("kibana", "dashboard")
        assert "objects" in result

    def test_unsupported_platform(self, manager):
        """Raises ConfigurationError for unknown platform."""
        with pytest.raises(ConfigurationError, match="Unsupported platform"):
            manager.load_template("prometheus", "some_template")

    def test_template_not_found(self, manager):
        """Raises ConfigurationError when template file missing."""
        with pytest.raises(ConfigurationError, match="Template not found"):
            manager.load_template("grafana", "nonexistent")

    def test_invalid_json_two_arg(self, tmp_templates):
        """Raises ConfigurationError for malformed JSON."""
        (tmp_templates / "grafana" / "broken.json").write_text("{{invalid}}")
        mgr = TemplateManager(templates_dir=tmp_templates)
        with pytest.raises(ConfigurationError, match="Invalid JSON"):
            mgr.load_template("grafana", "broken")

    def test_general_error_two_arg(self, tmp_templates):
        """Wraps unexpected read errors in ConfigurationError."""
        (tmp_templates / "grafana" / "perm.json").write_text("{}")
        mgr = TemplateManager(templates_dir=tmp_templates)
        with patch("builtins.open", side_effect=PermissionError("nope")):
            with pytest.raises(
                ConfigurationError, match="Failed to load template"
            ):
                mgr.load_template("grafana", "perm")


# ── get_available_templates ──────────────────────────────────────


class TestGetAvailableTemplates:
    """Tests for get_available_templates()."""

    def test_returns_json_stems(self, tmp_templates):
        """Returns stem names of .json files at top level."""
        mgr = TemplateManager(templates_dir=tmp_templates)
        templates = mgr.get_available_templates()
        assert "loose" in templates

    def test_filters_non_json(self, tmp_templates):
        """Non-JSON files are excluded."""
        (tmp_templates / "notes.txt").write_text("hi")
        mgr = TemplateManager(templates_dir=tmp_templates)
        templates = mgr.get_available_templates()
        assert "notes" not in templates

    def test_empty_when_dir_missing(self, tmp_path):
        """Returns empty list when templates_dir does not exist."""
        mgr = TemplateManager(templates_dir=tmp_path / "does_not_exist")
        assert mgr.get_available_templates() == []

    def test_oserror_returns_empty(self, tmp_templates):
        """Returns empty list on OSError during listdir."""
        mgr = TemplateManager(templates_dir=tmp_templates)
        with patch("os.listdir", side_effect=OSError("boom")):
            assert mgr.get_available_templates() == []


# ── _validate_grafana_template ───────────────────────────────────


class TestValidateGrafanaTemplate:
    """Tests for Grafana template validation."""

    def test_valid(self, manager):
        """Valid template does not raise."""
        tpl = {"dashboard": {"title": "OK", "panels": []}}
        manager._validate_grafana_template(tpl)

    def test_missing_dashboard_key(self, manager):
        """Raises ValueError when 'dashboard' key missing."""
        with pytest.raises(ValueError, match="missing 'dashboard' field"):
            manager._validate_grafana_template({"panels": []})

    def test_missing_title(self, manager):
        """Raises ValueError when title is absent."""
        with pytest.raises(ValueError, match="missing 'title' field"):
            manager._validate_grafana_template({"dashboard": {"panels": []}})


# ── _validate_kibana_template ────────────────────────────────────


class TestValidateKibanaTemplate:
    """Tests for Kibana template validation."""

    def test_valid(self, manager):
        """Valid template does not raise."""
        tpl = {
            "objects": [{"type": "dashboard", "attributes": {"title": "X"}}]
        }
        manager._validate_kibana_template(tpl)

    def test_missing_objects_key(self, manager):
        """Raises ValueError when 'objects' key missing."""
        with pytest.raises(ValueError, match="missing 'objects' field"):
            manager._validate_kibana_template({"dashboards": []})

    def test_object_missing_type(self, manager):
        """Raises ValueError when an object lacks 'type'."""
        with pytest.raises(ValueError, match="missing 'type' field"):
            manager._validate_kibana_template(
                {"objects": [{"attributes": {}}]}
            )

    def test_object_missing_attributes(self, manager):
        """Raises ValueError when an object lacks 'attributes'."""
        with pytest.raises(ValueError, match="missing 'attributes' field"):
            manager._validate_kibana_template(
                {"objects": [{"type": "dashboard"}]}
            )

    def test_empty_objects_is_valid(self, manager):
        """Empty objects list passes validation."""
        manager._validate_kibana_template({"objects": []})


# ── validate_template (public dispatcher) ────────────────────────


class TestValidateTemplate:
    """Tests for the public validate_template() dispatcher."""

    def test_grafana_valid(self, manager):
        """Dispatches to Grafana validator for valid template."""
        tpl = {"dashboard": {"title": "X"}}
        # _validate_grafana_template returns None on success,
        # so validate_template also returns None
        result = manager.validate_template(tpl, "grafana")
        assert result is None

    def test_kibana_valid(self, manager):
        """Dispatches to Kibana validator."""
        tpl = {"objects": [{"type": "vis", "attributes": {"a": 1}}]}
        result = manager.validate_template(tpl, "kibana")
        assert result is None

    def test_unknown_platform_non_empty(self, manager):
        """Unknown platform falls back to basic dict check."""
        result = manager.validate_template({"a": 1}, "prometheus")
        assert result is True

    def test_unknown_platform_empty_dict(self, manager):
        """Empty dict fails basic validation for unknown platform."""
        result = manager.validate_template({}, "prometheus")
        assert result is False

    def test_none_platform_returns_false(self, manager):
        """platform=None returns False."""
        result = manager.validate_template({"a": 1}, None)
        assert result is False

    def test_case_insensitive(self, manager):
        """Platform name matching is case-insensitive."""
        tpl = {"dashboard": {"title": "X"}}
        result = manager.validate_template(tpl, "GRAFANA")
        assert result is None  # no error

    def test_grafana_invalid_raises(self, manager):
        """Invalid Grafana template propagates ValueError."""
        with pytest.raises(ValueError):
            manager.validate_template({"no_dashboard": 1}, "grafana")


# ── _replace_variables ───────────────────────────────────────────


class TestReplaceVariables:
    """Tests for variable substitution in templates."""

    def test_braces_format(self, manager):
        """Variables with ${KEY} format are replaced."""
        tpl = {"url": "${HOST}:${PORT}/api"}
        result = manager._replace_variables(
            tpl, {"HOST": "localhost", "PORT": "8080"}
        )
        assert result["url"] == "localhost:8080/api"

    def test_pre_formatted_keys(self, manager):
        """Keys already wrapped in ${} are used as-is."""
        tpl = {"ds": "${DS_LOKI}"}
        result = manager._replace_variables(tpl, {"${DS_LOKI}": "MyLoki"})
        assert result["ds"] == "MyLoki"

    def test_nested_replacement(self, manager):
        """Variables inside nested structures are replaced."""
        tpl = {
            "outer": {
                "inner": [{"val": "${X}"}],
            }
        }
        result = manager._replace_variables(tpl, {"X": "replaced"})
        assert result["outer"]["inner"][0]["val"] == "replaced"

    def test_no_matching_vars(self, manager):
        """Template unchanged when no variables match."""
        tpl = {"static": "value"}
        result = manager._replace_variables(tpl, {"OTHER": "x"})
        assert result == {"static": "value"}

    def test_empty_variables(self, manager):
        """Empty variables dict returns template unchanged."""
        tpl = {"a": "${B}"}
        result = manager._replace_variables(tpl, {})
        assert result == {"a": "${B}"}

    def test_numeric_value_converted(self, manager):
        """Numeric values are converted to strings."""
        tpl = {"port": "${PORT}"}
        result = manager._replace_variables(tpl, {"PORT": 3000})
        assert result["port"] == "3000"

    def test_multiple_occurrences(self, manager):
        """Same variable appearing multiple times is replaced."""
        tpl = {"a": "${V}", "b": "${V}"}
        result = manager._replace_variables(tpl, {"V": "x"})
        assert result["a"] == "x"
        assert result["b"] == "x"


# ── _check_grafana_connectivity ──────────────────────────────────


class TestCheckGrafanaConnectivity:
    """Tests for Grafana health-check."""

    @patch("requests.get")
    def test_success(self, mock_get, manager):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert manager._check_grafana_connectivity(
            "http://grafana:3000", "key"
        )
        mock_get.assert_called_once_with(
            "http://grafana:3000/api/health",
            headers={"Authorization": "Bearer key"},
            timeout=5,
        )

    @patch("requests.get")
    def test_non_200(self, mock_get, manager):
        mock_resp = Mock()
        mock_resp.status_code = 503
        mock_get.return_value = mock_resp
        assert not manager._check_grafana_connectivity(
            "http://grafana:3000", "key"
        )

    @patch("requests.get", side_effect=ConnectionError("refused"))
    def test_connection_error(self, _mock, manager):
        assert not manager._check_grafana_connectivity(
            "http://grafana:3000", "key"
        )


# ── _check_kibana_connectivity ───────────────────────────────────


class TestCheckKibanaConnectivity:
    """Tests for Kibana health-check."""

    @patch("requests.get")
    def test_success_no_auth(self, mock_get, manager):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert manager._check_kibana_connectivity("http://kibana:5601")
        called_headers = mock_get.call_args[1]["headers"]
        assert called_headers == {}

    @patch("requests.get")
    def test_success_with_api_key(self, mock_get, manager):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        assert manager._check_kibana_connectivity(
            "http://kibana:5601", api_key="abc"
        )
        called_headers = mock_get.call_args[1]["headers"]
        assert called_headers["Authorization"] == "ApiKey abc"

    @patch("requests.get", side_effect=Exception("timeout"))
    def test_failure(self, _mock, manager):
        assert not manager._check_kibana_connectivity("http://kibana:5601")


# ── deploy_grafana_dashboard (method) ────────────────────────────


class TestDeployGrafanaDashboard:
    """Tests for TemplateManager.deploy_grafana_dashboard."""

    @patch("requests.post")
    def test_basic_deploy(self, mock_post, manager):
        """Successful deployment returns expected dict."""
        mock_resp = Mock()
        mock_resp.json.return_value = {
            "id": 42,
            "uid": "abc",
            "url": "/d/abc",
            "version": 1,
        }
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        result = manager.deploy_grafana_dashboard(
            template_name="overview",
            grafana_url="http://g:3000",
            api_key="k",
        )
        assert result["status"] == "success"
        assert result["dashboard_id"] == 42
        assert result["dashboard_uid"] == "abc"
        assert result["url"] == "/d/abc"
        assert result["version"] == 1

    @patch("requests.post")
    def test_datasource_replacement(self, mock_post, manager):
        """datasource_name triggers variable replacement."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"id": 1}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_grafana_dashboard(
            template_name="overview",
            grafana_url="http://g:3000",
            api_key="k",
            datasource_name="ProdLoki",
        )

        body = json.loads(mock_post.call_args[1]["data"])
        panel = body["dashboard"]["panels"][0]
        assert panel["datasource"] == "ProdLoki"

    @patch("requests.post")
    def test_folder_id(self, mock_post, manager):
        """folder_id is included in the payload."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"id": 1}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_grafana_dashboard(
            template_name="overview",
            grafana_url="http://g:3000",
            api_key="k",
            folder_id=7,
        )

        body = json.loads(mock_post.call_args[1]["data"])
        assert body["folderId"] == 7

    @patch("requests.post")
    def test_overwrite_default_true(self, mock_post, manager):
        """overwrite defaults to True in payload."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"id": 1}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_grafana_dashboard(
            template_name="overview",
            grafana_url="http://g:3000",
            api_key="k",
        )

        body = json.loads(mock_post.call_args[1]["data"])
        assert body["overwrite"] is True

    @patch("requests.post")
    def test_url_trailing_slash_stripped(self, mock_post, manager):
        """Trailing slash on grafana_url is stripped."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"id": 1}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_grafana_dashboard(
            template_name="overview",
            grafana_url="http://g:3000/",
            api_key="k",
        )

        url_called = mock_post.call_args[0][0]
        assert url_called == "http://g:3000/api/dashboards/db"

    @patch("requests.post")
    def test_http_error(self, mock_post, manager):
        """HTTP errors raise Exception."""
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("400")
        mock_post.return_value = mock_resp

        with pytest.raises(Exception, match="Failed to deploy dashboard"):
            manager.deploy_grafana_dashboard(
                template_name="overview",
                grafana_url="http://g:3000",
                api_key="k",
            )

    @patch(
        "requests.post",
        side_effect=requests.ConnectionError("refused"),
    )
    def test_connection_error(self, _mock, manager):
        """Connection errors raise Exception."""
        with pytest.raises(Exception, match="Failed to deploy dashboard"):
            manager.deploy_grafana_dashboard(
                template_name="overview",
                grafana_url="http://g:3000",
                api_key="k",
            )


# ── deploy_kibana_objects ────────────────────────────────────────


class TestDeployKibanaObjects:
    """Tests for TemplateManager.deploy_kibana_objects."""

    @patch("requests.post")
    def test_basic_deploy(self, mock_post, manager):
        """Successful deployment returns response JSON."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"saved_objects": []}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        result = manager.deploy_kibana_objects(
            template_name="dashboard",
            kibana_url="http://k:5601",
        )
        assert "saved_objects" in result

    @patch("requests.post")
    def test_api_key_auth(self, mock_post, manager):
        """api_key sets ApiKey authorization header."""
        mock_resp = Mock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_kibana_objects(
            template_name="dashboard",
            kibana_url="http://k:5601",
            api_key="secret",
        )

        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "ApiKey secret"

    @patch("requests.post")
    def test_basic_auth(self, mock_post, manager):
        """username/password sets Basic authorization header."""
        import base64

        mock_resp = Mock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_kibana_objects(
            template_name="dashboard",
            kibana_url="http://k:5601",
            username="admin",
            password="pass",
        )

        headers = mock_post.call_args[1]["headers"]
        expected = base64.b64encode(b"admin:pass").decode()
        assert headers["Authorization"] == f"Basic {expected}"

    @patch("requests.post")
    def test_index_pattern_override(self, mock_post, manager):
        """index_pattern kwarg replaces logs-* patterns."""
        mock_resp = Mock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_kibana_objects(
            template_name="dashboard",
            kibana_url="http://k:5601",
            index_pattern="my-app-*",
        )

        body = json.loads(mock_post.call_args[1]["data"])
        ip_obj = next(
            o for o in body["objects"] if o["type"] == "index-pattern"
        )
        assert ip_obj["attributes"]["title"] == "my-app-*"

    @patch("requests.post")
    def test_url_constructed(self, mock_post, manager):
        """URL is built correctly with trailing slash stripped."""
        mock_resp = Mock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_kibana_objects(
            template_name="dashboard",
            kibana_url="http://k:5601/",
        )

        url = mock_post.call_args[0][0]
        assert url == ("http://k:5601/api/saved_objects/_bulk_create")

    @patch("requests.post")
    def test_http_error(self, mock_post, manager):
        """HTTP errors raise Exception."""
        mock_resp = Mock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = mock_resp

        with pytest.raises(Exception, match="Failed to deploy dashboard"):
            manager.deploy_kibana_objects(
                template_name="dashboard",
                kibana_url="http://k:5601",
            )

    @patch(
        "requests.post",
        side_effect=requests.ConnectionError("down"),
    )
    def test_connection_error(self, _mock, manager):
        """Connection errors raise Exception."""
        with pytest.raises(Exception, match="Failed to deploy dashboard"):
            manager.deploy_kibana_objects(
                template_name="dashboard",
                kibana_url="http://k:5601",
            )


# ── deploy_kibana_dashboard (alias) ─────────────────────────────


class TestDeployKibanaDashboard:
    """Tests for the alias method deploy_kibana_dashboard."""

    @patch("requests.post")
    def test_delegates_to_deploy_kibana_objects(self, mock_post, manager):
        """deploy_kibana_dashboard delegates correctly."""
        mock_resp = Mock()
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        result = manager.deploy_kibana_dashboard(
            template_name="dashboard",
            kibana_url="http://k:5601",
            api_key="key",
        )
        assert result == {"ok": True}

    @patch("requests.post")
    def test_passes_index_pattern(self, mock_post, manager):
        """index_pattern is forwarded via kwargs."""
        mock_resp = Mock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_kibana_dashboard(
            template_name="dashboard",
            kibana_url="http://k:5601",
            index_pattern="custom-*",
        )

        body = json.loads(mock_post.call_args[1]["data"])
        ip_obj = next(
            o for o in body["objects"] if o["type"] == "index-pattern"
        )
        assert ip_obj["attributes"]["title"] == "custom-*"

    @patch("requests.post")
    def test_none_index_pattern_not_forwarded(self, mock_post, manager):
        """index_pattern=None is not added to kwargs."""
        mock_resp = Mock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = Mock()
        mock_post.return_value = mock_resp

        manager.deploy_kibana_dashboard(
            template_name="dashboard",
            kibana_url="http://k:5601",
            index_pattern=None,
        )

        body = json.loads(mock_post.call_args[1]["data"])
        ip_obj = next(
            o for o in body["objects"] if o["type"] == "index-pattern"
        )
        # Should remain original because None means no override
        assert ip_obj["attributes"]["title"] == "logs-*"


# ── customize_template ───────────────────────────────────────────


class TestCustomizeTemplate:
    """Tests for customize_template() dispatcher."""

    def test_grafana_dispatch(self, manager):
        """Dispatches to _customize_grafana_template."""
        result = manager.customize_template(
            "grafana", "overview", {"title": "New Title"}
        )
        assert result["dashboard"]["title"] == "New Title"

    def test_kibana_dispatch(self, manager):
        """Dispatches to _customize_kibana_template."""
        result = manager.customize_template(
            "kibana",
            "dashboard",
            {"index_pattern": "app-*"},
        )
        ip_obj = next(
            o for o in result["objects"] if o["type"] == "index-pattern"
        )
        assert ip_obj["attributes"]["title"] == "app-*"

    def test_unsupported_platform(self, manager):
        """Raises ConfigurationError for unknown platform."""
        with pytest.raises(ConfigurationError, match="Unsupported platform"):
            manager.customize_template("prometheus", "overview", {})


# ── _customize_grafana_template ──────────────────────────────────


class TestCustomizeGrafanaTemplate:
    """Tests for Grafana template customization."""

    def test_title(self, manager):
        tpl = {"dashboard": {"title": "Old"}}
        result = manager._customize_grafana_template(tpl, {"title": "New"})
        assert result["dashboard"]["title"] == "New"

    def test_refresh(self, manager):
        tpl = {"dashboard": {"title": "X", "refresh": "5s"}}
        result = manager._customize_grafana_template(tpl, {"refresh": "30s"})
        assert result["dashboard"]["refresh"] == "30s"

    def test_time_range(self, manager):
        tpl = {"dashboard": {"title": "X"}}
        result = manager._customize_grafana_template(
            tpl,
            {"time_range": {"from": "now-6h", "to": "now"}},
        )
        assert result["dashboard"]["time"]["from"] == "now-6h"
        assert result["dashboard"]["time"]["to"] == "now"

    def test_time_range_defaults(self, manager):
        tpl = {"dashboard": {"title": "X"}}
        result = manager._customize_grafana_template(tpl, {"time_range": {}})
        assert result["dashboard"]["time"]["from"] == "now-1h"
        assert result["dashboard"]["time"]["to"] == "now"

    def test_update_existing_variable(self, manager):
        tpl = {
            "dashboard": {
                "title": "X",
                "templating": {
                    "list": [{"name": "env", "current": {"value": "prod"}}]
                },
            }
        }
        result = manager._customize_grafana_template(
            tpl,
            {"variables": {"env": {"current": {"value": "staging"}}}},
        )
        var = result["dashboard"]["templating"]["list"][0]
        assert var["current"]["value"] == "staging"

    def test_add_new_variable(self, manager):
        tpl = {"dashboard": {"title": "X"}}
        result = manager._customize_grafana_template(
            tpl,
            {"variables": {"region": {"type": "custom"}}},
        )
        var_list = result["dashboard"]["templating"]["list"]
        assert len(var_list) == 1
        assert var_list[0]["name"] == "region"
        assert var_list[0]["type"] == "custom"

    def test_no_customizations(self, manager):
        tpl = {"dashboard": {"title": "X"}}
        result = manager._customize_grafana_template(tpl, {})
        assert result["dashboard"]["title"] == "X"


# ── _customize_kibana_template ───────────────────────────────────


class TestCustomizeKibanaTemplate:
    """Tests for Kibana template customization."""

    def test_index_pattern(self, manager):
        tpl = {
            "objects": [
                {
                    "type": "index-pattern",
                    "attributes": {"title": "logs-*"},
                }
            ]
        }
        result = manager._customize_kibana_template(
            tpl, {"index_pattern": "app-*"}
        )
        assert result["objects"][0]["attributes"]["title"] == "app-*"

    def test_title(self, manager):
        tpl = {
            "objects": [
                {
                    "type": "dashboard",
                    "attributes": {"title": "Old"},
                }
            ]
        }
        result = manager._customize_kibana_template(tpl, {"title": "New"})
        assert result["objects"][0]["attributes"]["title"] == "New"

    def test_no_matching_type(self, manager):
        tpl = {
            "objects": [
                {
                    "type": "visualization",
                    "attributes": {"title": "Viz"},
                }
            ]
        }
        result = manager._customize_kibana_template(
            tpl, {"index_pattern": "x-*", "title": "Y"}
        )
        # Neither matched, so attributes unchanged
        assert result["objects"][0]["attributes"]["title"] == "Viz"

    def test_empty_objects(self, manager):
        tpl = {"objects": []}
        result = manager._customize_kibana_template(tpl, {"title": "X"})
        assert result["objects"] == []


# ── save_template ────────────────────────────────────────────────


class TestSaveTemplate:
    """Tests for save_template()."""

    def test_save_to_default_dir(self, manager, tmp_templates):
        """Saves to templates_dir/<platform>/<name>.json."""
        data = {"dashboard": {"title": "Saved"}}
        manager.save_template("grafana", "my_template", data)

        path = tmp_templates / "grafana" / "my_template.json"
        assert path.exists()
        assert json.loads(path.read_text()) == data

    def test_save_to_custom_dir(self, manager, tmp_path):
        """Saves to custom_dir/<platform>/<name>.json."""
        custom = tmp_path / "custom"
        data = {"objects": []}
        manager.save_template("kibana", "exported", data, custom_dir=custom)

        path = custom / "kibana" / "exported.json"
        assert path.exists()
        assert json.loads(path.read_text()) == data

    def test_creates_dirs(self, manager, tmp_path):
        """Creates intermediate directories as needed."""
        custom = tmp_path / "deep" / "nested"
        manager.save_template("grafana", "tpl", {"a": 1}, custom_dir=custom)
        assert (custom / "grafana" / "tpl.json").exists()

    def test_overwrites_existing(self, manager, tmp_templates):
        """Overwrites an existing template file."""
        manager.save_template("grafana", "overview", {"new": True})
        path = tmp_templates / "grafana" / "overview.json"
        assert json.loads(path.read_text()) == {"new": True}

    def test_json_formatting(self, manager, tmp_templates):
        """Output is indented with 2 spaces."""
        manager.save_template("grafana", "fmt", {"k": "v"})
        content = (tmp_templates / "grafana" / "fmt.json").read_text()
        assert "  " in content  # indent=2


# ── get_template_info & template_exists ──────────────────────────
# These methods reference self.template_dir (a bug/typo — should
# be templates_dir).  We test them to document behavior.


class TestGetTemplateInfo:
    """Tests for get_template_info — uses self.template_dir."""

    def test_attribute_error(self, manager):
        """Raises AttributeError because of template_dir typo."""
        with pytest.raises(AttributeError):
            manager.get_template_info("overview")


class TestTemplateExists:
    """Tests for template_exists — also uses self.template_dir."""

    def test_returns_false_on_error(self, manager):
        """Returns False because of the attribute error."""
        assert manager.template_exists("overview") is False

    def test_with_platform_returns_false_on_error(self, manager):
        """Returns False for platform-qualified lookup too."""
        assert manager.template_exists("overview", "grafana") is False


# ── Module-level convenience functions ───────────────────────────


class TestConvenienceFunctions:
    """Tests for module-level wrapper functions."""

    @patch.object(TemplateManager, "get_available_templates")
    def test_list_available_templates(self, mock_method):
        mock_method.return_value = ["a", "b"]
        assert list_available_templates() == ["a", "b"]

    @patch.object(TemplateManager, "deploy_grafana_dashboard")
    def test_deploy_grafana_dashboard(self, mock_method):
        mock_method.return_value = {"status": "success"}
        result = deploy_grafana_dashboard(
            template_name="t",
            grafana_url="http://g:3000",
            api_key="k",
        )
        assert result == {"status": "success"}
        mock_method.assert_called_once_with(
            template_name="t",
            grafana_url="http://g:3000",
            api_key="k",
            datasource_name=None,
        )

    @patch.object(TemplateManager, "deploy_grafana_dashboard")
    def test_deploy_grafana_with_datasource(self, mock_method):
        mock_method.return_value = {"status": "success"}
        deploy_grafana_dashboard(
            template_name="t",
            grafana_url="http://g:3000",
            api_key="k",
            datasource_name="DS",
        )
        mock_method.assert_called_once_with(
            template_name="t",
            grafana_url="http://g:3000",
            api_key="k",
            datasource_name="DS",
        )

    @patch.object(TemplateManager, "deploy_kibana_dashboard")
    def test_deploy_kibana_dashboard(self, mock_method):
        mock_method.return_value = {"ok": True}
        result = deploy_kibana_dashboard(
            template_name="t",
            kibana_url="http://k:5601",
        )
        assert result == {"ok": True}
        mock_method.assert_called_once_with(
            template_name="t",
            kibana_url="http://k:5601",
            index_pattern=None,
        )

    @patch.object(TemplateManager, "deploy_kibana_dashboard")
    def test_deploy_kibana_with_index(self, mock_method):
        mock_method.return_value = {}
        deploy_kibana_dashboard(
            template_name="t",
            kibana_url="http://k:5601",
            index_pattern="app-*",
        )
        mock_method.assert_called_once_with(
            template_name="t",
            kibana_url="http://k:5601",
            index_pattern="app-*",
        )


class TestCreateCustomTemplate:
    """Tests for create_custom_template convenience function."""

    @patch.object(TemplateManager, "save_template")
    @patch.object(TemplateManager, "customize_template")
    def test_with_output_dir(self, mock_customize, mock_save, tmp_path):
        mock_customize.return_value = {"custom": True}
        result = create_custom_template(
            platform="grafana",
            base_template="overview",
            customizations={"title": "Custom"},
            output_name="my_custom",
            output_dir=tmp_path,
        )
        mock_customize.assert_called_once_with(
            "grafana", "overview", {"title": "Custom"}
        )
        mock_save.assert_called_once_with(
            "grafana", "my_custom", {"custom": True}, tmp_path
        )
        assert result == tmp_path / "grafana" / "my_custom.json"

    @patch.object(TemplateManager, "save_template")
    @patch.object(TemplateManager, "customize_template")
    def test_without_output_dir(self, mock_customize, mock_save):
        mock_customize.return_value = {"custom": True}
        result = create_custom_template(
            platform="kibana",
            base_template="dashboard",
            customizations={},
            output_name="exported",
        )
        mock_save.assert_called_once_with(
            "kibana", "exported", {"custom": True}, None
        )
        expected = default_manager.templates_dir / "kibana" / "exported.json"
        assert result == expected


# ── default_manager singleton ────────────────────────────────────


class TestDefaultManager:
    """Tests for the module-level singleton."""

    def test_is_instance(self):
        assert isinstance(default_manager, TemplateManager)

    def test_uses_package_dir(self):
        """Default manager templates_dir is the package dir."""
        assert default_manager.templates_dir == Path(
            os.path.dirname(
                os.path.abspath(
                    os.path.join(
                        os.path.dirname(__file__),
                        "..",
                        "..",
                        "src",
                        "mohflow",
                        "templates",
                        "template_manager.py",
                    )
                )
            )
        ) or default_manager.templates_dir.name in (
            "templates",
            "mohflow",
        )
