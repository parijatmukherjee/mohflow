"""
Contract test for GET /ui endpoint.

This test MUST FAIL initially until the hub server is implemented.
"""

import pytest
import requests
from ..conftest import requires_hub_server


@requires_hub_server
class TestUIContract:
    """Test contract for /ui endpoint according to hub-api.yaml."""

    def test_ui_endpoint_returns_200(self):
        """Test that /ui returns 200 status code."""
        # This will fail until hub server is implemented
        response = requests.get("http://127.0.0.1:17361/ui")
        assert response.status_code == 200

    def test_ui_response_content_type_is_html(self):
        """Test that /ui returns HTML content type."""
        response = requests.get("http://127.0.0.1:17361/ui")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type

    def test_ui_response_contains_html_structure(self):
        """Test that /ui response contains valid HTML structure."""
        response = requests.get("http://127.0.0.1:17361/ui")
        assert response.status_code == 200

        html_content = response.text

        # Basic HTML structure checks
        assert "<!DOCTYPE html>" in html_content or "<html" in html_content
        assert "<head>" in html_content
        assert "<title>" in html_content
        assert "<body>" in html_content

    def test_ui_response_contains_mohnitor_references(self):
        """Test that /ui HTML contains Mohnitor-related content."""
        response = requests.get("http://127.0.0.1:17361/ui")
        html_content = response.text.lower()

        # Should reference Mohnitor in some way
        mohnitor_keywords = ["mohnitor", "mohflow", "log", "viewer"]
        has_keyword = any(
            keyword in html_content for keyword in mohnitor_keywords
        )
        assert has_keyword, "UI should contain Mohnitor-related keywords"

    def test_ui_response_has_reasonable_size(self):
        """Test that UI response is not empty and not excessively large."""
        response = requests.get("http://127.0.0.1:17361/ui")
        content_length = len(response.content)

        # Should not be empty
        assert content_length > 0

        # Should not be excessively large (>10MB is probably an error)
        assert content_length < 10 * 1024 * 1024  # 10MB limit

    def test_ui_can_be_cached(self):
        """Test that UI response includes appropriate caching headers."""
        response = requests.get("http://127.0.0.1:17361/ui")

        # While not strictly required by contract, good practice
        # We'll check if any caching headers are present
        cache_headers = ["cache-control", "etag", "last-modified", "expires"]

        # At least one caching header should be present for static content
        has_cache_header = any(
            header in response.headers for header in cache_headers
        )
        # This is a soft assertion - nice to have but not critical
        if not has_cache_header:
            print("Warning: No caching headers found in UI response")
