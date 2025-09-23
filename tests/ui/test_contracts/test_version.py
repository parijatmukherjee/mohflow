"""
Contract test for GET /version endpoint.

This test MUST FAIL initially until the hub server is implemented.
"""

import pytest
import requests
import json
import re
from datetime import datetime
from ..conftest import requires_hub_server


@requires_hub_server
class TestVersionContract:
    """Test contract for /version endpoint according to hub-api.yaml."""

    def test_version_endpoint_returns_200(self):
        """Test that /version returns 200 status code."""
        # This will fail until hub server is implemented
        response = requests.get("http://127.0.0.1:17361/version")
        assert response.status_code == 200

    def test_version_response_has_required_fields(self):
        """Test that /version response contains all required fields."""
        response = requests.get("http://127.0.0.1:17361/version")
        assert response.status_code == 200

        data = response.json()

        # Check required fields
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_version_response_optional_fields(self):
        """Test optional fields in /version response."""
        response = requests.get("http://127.0.0.1:17361/version")
        data = response.json()

        # Optional build_date field
        if "build_date" in data:
            build_date = data["build_date"]
            assert isinstance(build_date, str)
            # Should be valid ISO 8601 datetime
            datetime.fromisoformat(build_date.replace("Z", "+00:00"))

        # Optional commit_hash field
        if "commit_hash" in data:
            commit_hash = data["commit_hash"]
            assert isinstance(commit_hash, str)
            # Should look like a git hash (hex string)
            assert re.match(r"^[a-f0-9]+$", commit_hash.lower())

    def test_version_format_is_semantic(self):
        """Test that version follows semantic versioning."""
        response = requests.get("http://127.0.0.1:17361/version")
        data = response.json()

        version = data["version"]

        # Should match semantic versioning pattern (major.minor.patch)
        semver_pattern = (
            r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?$"
        )
        assert re.match(
            semver_pattern, version
        ), f"Version '{version}' does not follow semantic versioning"

    def test_version_matches_mohflow_version(self):
        """Test that version matches MohFlow package version."""
        response = requests.get("http://127.0.0.1:17361/version")
        data = response.json()

        # Should start with or match MohFlow version
        version = data["version"]

        # Try to import MohFlow version for comparison
        try:
            import mohflow

            mohflow_version = getattr(mohflow, "__version__", None)
            if mohflow_version:
                # Version should be related to MohFlow version
                assert (
                    version.startswith(mohflow_version)
                    or mohflow_version in version
                )
        except ImportError:
            # If MohFlow not available, just check format
            pass
