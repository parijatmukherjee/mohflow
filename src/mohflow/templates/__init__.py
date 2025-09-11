"""
Dashboard templates for MohFlow.
Pre-built Grafana and Kibana dashboards for log visualization and analysis.
"""

from .template_manager import (
    TemplateManager,
    deploy_grafana_dashboard,
    deploy_kibana_dashboard,
    list_available_templates,
)

__all__ = [
    "TemplateManager",
    "deploy_grafana_dashboard",
    "deploy_kibana_dashboard",
    "list_available_templates",
]
