"""
Template manager for deploying MohFlow dashboards to Grafana and Kibana.
Provides utilities for dashboard deployment and management.
"""

import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List
from mohflow.exceptions import ConfigurationError


class TemplateManager:
    """
    Manager for dashboard templates and deployment.
    Handles Grafana and Kibana dashboard operations.
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize template manager.

        Args:
            templates_dir: Path to templates directory
                (defaults to package templates)
        """
        if templates_dir:
            self.templates_dir = Path(templates_dir)
        else:
            self.templates_dir = Path(__file__).parent

        self.grafana_dir = self.templates_dir / "grafana"
        self.kibana_dir = self.templates_dir / "kibana"

    def list_templates(self, platform: str = "all") -> Dict[str, List[str]]:
        """
        List available dashboard templates.

        Args:
            platform: Platform to list templates for
                ("grafana", "kibana", or "all")

        Returns:
            Dictionary mapping platform to list of template names
        """
        templates = {}

        if platform in ("grafana", "all"):
            grafana_templates = []
            if self.grafana_dir.exists():
                for template_file in self.grafana_dir.glob("*.json"):
                    grafana_templates.append(template_file.stem)
            templates["grafana"] = grafana_templates

        if platform in ("kibana", "all"):
            kibana_templates = []
            if self.kibana_dir.exists():
                for template_file in self.kibana_dir.glob("*.json"):
                    kibana_templates.append(template_file.stem)
            templates["kibana"] = kibana_templates

        return templates

    def load_template(
        self, platform: str, template_name: str
    ) -> Dict[str, Any]:
        """
        Load a dashboard template.

        Args:
            platform: Platform ("grafana" or "kibana")
            template_name: Name of the template

        Returns:
            Template configuration dictionary

        Raises:
            ConfigurationError: If template not found or invalid
        """
        if platform == "grafana":
            template_dir = self.grafana_dir
        elif platform == "kibana":
            template_dir = self.kibana_dir
        else:
            raise ConfigurationError(f"Unsupported platform: {platform}")

        template_file = template_dir / f"{template_name}.json"

        if not template_file.exists():
            raise ConfigurationError(f"Template not found: {template_file}")

        try:
            with open(template_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in template {template_name}: {e}"
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load template {template_name}: {e}"
            )

    def deploy_grafana_dashboard(
        self,
        template_name: str,
        grafana_url: str,
        api_key: str,
        overwrite: bool = True,
        folder_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Deploy a Grafana dashboard template.

        Args:
            template_name: Name of the template to deploy
            grafana_url: Grafana instance URL
            api_key: Grafana API key
            overwrite: Whether to overwrite existing dashboard
            folder_id: Folder ID to deploy dashboard to

        Returns:
            Deployment result

        Raises:
            ConfigurationError: If deployment fails
        """
        template = self.load_template("grafana", template_name)

        # Prepare dashboard payload
        dashboard_data = {
            "dashboard": template.get("dashboard", template),
            "overwrite": overwrite,
        }

        if folder_id is not None:
            dashboard_data["folderId"] = folder_id

        # Deploy to Grafana
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{grafana_url.rstrip('/')}/api/dashboards/db",
                headers=headers,
                json=dashboard_data,
                timeout=30,
            )
            response.raise_for_status()

            result = response.json()
            return {
                "status": "success",
                "dashboard_id": result.get("id"),
                "dashboard_uid": result.get("uid"),
                "url": result.get("url"),
                "version": result.get("version"),
            }

        except requests.exceptions.RequestException as e:
            raise ConfigurationError(
                f"Failed to deploy Grafana dashboard: {e}"
            )
        except Exception as e:
            raise ConfigurationError(f"Grafana deployment error: {e}")

    def deploy_kibana_objects(
        self,
        template_name: str,
        kibana_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        space_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deploy Kibana objects (dashboards, visualizations, etc.).

        Args:
            template_name: Name of the template to deploy
            kibana_url: Kibana instance URL
            username: Kibana username (for basic auth)
            password: Kibana password (for basic auth)
            api_key: Kibana API key (alternative to username/password)
            space_id: Kibana space ID

        Returns:
            Deployment result

        Raises:
            ConfigurationError: If deployment fails
        """
        template = self.load_template("kibana", template_name)

        # Prepare headers
        headers = {"Content-Type": "application/json"}

        if api_key:
            headers["Authorization"] = f"ApiKey {api_key}"
        elif username and password:
            import base64

            credentials = base64.b64encode(
                f"{username}:{password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"
        else:
            raise ConfigurationError(
                "Either api_key or username/password must be provided"
            )

        # Prepare URL
        base_url = kibana_url.rstrip("/")
        if space_id:
            api_url = f"{base_url}/s/{space_id}/api/saved_objects/_import"
        else:
            api_url = f"{base_url}/api/saved_objects/_import"

        # Prepare objects for import
        objects = template.get("objects", [])
        if not objects:
            raise ConfigurationError(
                f"No objects found in template {template_name}"
            )

        # Create NDJSON format for Kibana import
        ndjson_data = "\n".join(json.dumps(obj) for obj in objects)

        try:
            response = requests.post(
                api_url,
                headers=headers,
                files={
                    "file": (
                        "export.ndjson",
                        ndjson_data,
                        "application/ndjson",
                    )
                },
                params={"overwrite": "true"},
                timeout=30,
            )
            response.raise_for_status()

            result = response.json()
            return {
                "status": "success",
                "imported_count": result.get("successCount", 0),
                "errors": result.get("errors", []),
                "success_results": result.get("successResults", []),
            }

        except requests.exceptions.RequestException as e:
            raise ConfigurationError(f"Failed to deploy Kibana objects: {e}")
        except Exception as e:
            raise ConfigurationError(f"Kibana deployment error: {e}")

    def deploy_kibana_dashboard(
        self,
        template_name: str,
        kibana_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        space_id: Optional[str] = None,
        index_pattern: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Deploy a Kibana dashboard template.

        This is an alias for deploy_kibana_objects for consistency with
        the convenience function naming.

        Args:
            template_name: Name of the template to deploy
            kibana_url: Kibana instance URL
            username: Kibana username (for basic auth)
            password: Kibana password (for basic auth)
            api_key: Kibana API key (alternative to username/password)
            space_id: Kibana space ID
            index_pattern: Index pattern (for backward compatibility)

        Returns:
            Deployment result
        """
        return self.deploy_kibana_objects(
            template_name=template_name,
            kibana_url=kibana_url,
            username=username,
            password=password,
            api_key=api_key,
            space_id=space_id,
            **kwargs,
        )

    def customize_template(
        self, platform: str, template_name: str, customizations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Customize a template with specific parameters.

        Args:
            platform: Platform ("grafana" or "kibana")
            template_name: Name of the template
            customizations: Dictionary of customizations to apply

        Returns:
            Customized template
        """
        template = self.load_template(platform, template_name)

        # Apply customizations based on platform
        if platform == "grafana":
            return self._customize_grafana_template(template, customizations)
        elif platform == "kibana":
            return self._customize_kibana_template(template, customizations)
        else:
            raise ConfigurationError(f"Unsupported platform: {platform}")

    def _customize_grafana_template(
        self, template: Dict[str, Any], customizations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Customize Grafana template"""
        customized = template.copy()
        dashboard = customized.get("dashboard", {})

        # Apply common customizations
        if "title" in customizations:
            dashboard["title"] = customizations["title"]

        if "refresh" in customizations:
            dashboard["refresh"] = customizations["refresh"]

        if "time_range" in customizations:
            time_range = customizations["time_range"]
            dashboard["time"] = {
                "from": time_range.get("from", "now-1h"),
                "to": time_range.get("to", "now"),
            }

        # Customize variables/templating
        if "variables" in customizations:
            templating = dashboard.setdefault("templating", {})
            var_list = templating.setdefault("list", [])

            for var_name, var_config in customizations["variables"].items():
                # Find and update existing variable or add new one
                existing_var = next(
                    (v for v in var_list if v.get("name") == var_name), None
                )
                if existing_var:
                    existing_var.update(var_config)
                else:
                    var_config["name"] = var_name
                    var_list.append(var_config)

        return customized

    def _customize_kibana_template(
        self, template: Dict[str, Any], customizations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Customize Kibana template"""
        customized = template.copy()

        # Apply customizations to objects
        if "index_pattern" in customizations:
            for obj in customized.get("objects", []):
                if obj.get("type") == "index-pattern":
                    obj["attributes"]["title"] = customizations[
                        "index_pattern"
                    ]

        if "title" in customizations:
            for obj in customized.get("objects", []):
                if obj.get("type") == "dashboard":
                    obj["attributes"]["title"] = customizations["title"]

        return customized

    def save_template(
        self,
        platform: str,
        template_name: str,
        template_data: Dict[str, Any],
        custom_dir: Optional[Path] = None,
    ):
        """
        Save a template to file.

        Args:
            platform: Platform ("grafana" or "kibana")
            template_name: Name of the template
            template_data: Template data to save
            custom_dir: Custom directory to save to (optional)
        """
        if custom_dir:
            output_dir = Path(custom_dir) / platform
        else:
            output_dir = self.templates_dir / platform

        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{template_name}.json"

        with open(output_file, "w") as f:
            json.dump(template_data, f, indent=2)


# Singleton instance for easy access
default_manager = TemplateManager()


# Convenience functions
def deploy_grafana_dashboard(
    template_name: str, grafana_url: str, api_key: str, **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to deploy Grafana dashboard.

    Args:
        template_name: Name of the template
        grafana_url: Grafana URL
        api_key: Grafana API key
        **kwargs: Additional deployment options

    Returns:
        Deployment result
    """
    return default_manager.deploy_grafana_dashboard(
        template_name, grafana_url, api_key, **kwargs
    )


def deploy_kibana_dashboard(
    template_name: str,
    kibana_url: str,
    index_pattern: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Convenience function to deploy Kibana dashboard.

    Args:
        template_name: Name of the template
        kibana_url: Kibana URL
        index_pattern: Index pattern (for backward compatibility)
        **kwargs: Authentication and deployment options

    Returns:
        Deployment result
    """
    return default_manager.deploy_kibana_dashboard(
        template_name=template_name,
        kibana_url=kibana_url,
        index_pattern=index_pattern,
        **kwargs,
    )


def list_available_templates() -> Dict[str, List[str]]:
    """List all available dashboard templates"""
    return default_manager.list_templates()


def create_custom_template(
    platform: str,
    base_template: str,
    customizations: Dict[str, Any],
    output_name: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Create a custom template based on existing template.

    Args:
        platform: Platform ("grafana" or "kibana")
        base_template: Base template name
        customizations: Customizations to apply
        output_name: Name for the custom template
        output_dir: Directory to save custom template

    Returns:
        Path to the created template file
    """
    customized = default_manager.customize_template(
        platform, base_template, customizations
    )
    default_manager.save_template(
        platform, output_name, customized, output_dir
    )

    if output_dir:
        return Path(output_dir) / platform / f"{output_name}.json"
    else:
        return default_manager.templates_dir / platform / f"{output_name}.json"
