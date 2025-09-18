"""
T019: Test existing sensitive data filtering behavior unchanged
These tests MUST FAIL initially (TDD approach)
"""

from mohflow.context.filters import SensitiveDataFilter


class TestRegressionSensitiveFiltering:
    """Test existing sensitive data filtering behavior is preserved"""

    def test_existing_sensitive_fields_still_redacted(self):
        """Test all existing sensitive fields are still redacted"""
        filter_obj = SensitiveDataFilter()

        # Known sensitive fields from existing implementation
        existing_sensitive_fields = [
            "password",
            "token",
            "key",
            "secret",
            "auth",
            "credential",
            "api_key",
            "access_token",
            "refresh_token",
            "jwt",
            "bearer",
            "authorization",
            "x-api-key",
            "private_key",
            "client_secret",
        ]

        test_data = {
            field: f"secret_value_{field}"
            for field in existing_sensitive_fields
        }

        filtered_data = filter_obj.filter_data(test_data)

        # All should be redacted
        for field in existing_sensitive_fields:
            assert filtered_data[field] == "[REDACTED]"

    def test_existing_sensitive_patterns_still_work(self):
        """Test existing sensitive data patterns still work"""
        filter_obj = SensitiveDataFilter()

        test_data = {
            "credit_card_1": "1234-5678-9012-3456",  # Credit card pattern
            "credit_card_2": "1234567890123456",  # Credit card without dashes
            "ssn": "123-45-6789",  # SSN pattern
            "email": "user@example.com",  # Email pattern
            "phone": "555-123-4567",  # Phone pattern
            "uuid": "550e8400-e29b-41d4-a716-446655440000",  # UUID pattern
        }

        filtered_data = filter_obj.filter_data(test_data)

        # All pattern-based sensitive data should be redacted
        for field in test_data.keys():
            assert filtered_data[field] == "[REDACTED]"

    def test_existing_configuration_options_preserved(self):
        """Test existing configuration options still work"""
        # Test with existing parameters
        filter_obj = SensitiveDataFilter(
            enabled=True,
            sensitive_fields={"custom_secret"},
            additional_patterns=["custom_pattern_.*"],
            redaction_text="[HIDDEN]",
            max_field_length=500,
            case_sensitive=True,
        )

        test_data = {
            "custom_secret": "should_be_redacted",
            "custom_pattern_test": "should_match_pattern",
            "normal_field": "should_be_preserved",
        }

        filtered_data = filter_obj.filter_data(test_data)

        # Custom configuration should work
        assert filtered_data["custom_secret"] == "[HIDDEN]"
        assert filtered_data["custom_pattern_test"] == "[HIDDEN]"
        assert filtered_data["normal_field"] == "should_be_preserved"

    def test_disabled_filter_unchanged(self):
        """Test disabled filter behavior is unchanged"""
        filter_obj = SensitiveDataFilter(enabled=False)

        test_data = {
            "password": "secret123",
            "api_key": "key123",
            "normal_field": "value",
        }

        filtered_data = filter_obj.filter_data(test_data)

        # When disabled, nothing should be redacted
        assert filtered_data == test_data

    def test_existing_http_filter_unchanged(self):
        """Test existing HTTPDataFilter behavior is unchanged"""
        from mohflow.context.filters import HTTPDataFilter

        http_filter = HTTPDataFilter()

        headers = {
            "authorization": "Bearer token123",
            "x-api-key": "secret-key",
            "content-type": "application/json",
        }

        filtered_headers = http_filter.filter_headers(headers)

        # Sensitive headers should be redacted
        assert filtered_headers["authorization"] == "[REDACTED]"
        assert filtered_headers["x-api-key"] == "[REDACTED]"
        assert filtered_headers["content-type"] == "application/json"

    def test_existing_utility_functions_unchanged(self):
        """Test existing utility functions still work"""
        from mohflow.context.filters import filter_sensitive_data

        test_data = {"password": "secret", "user_id": "user123"}

        # Regular filter
        filtered_regular = filter_sensitive_data(
            test_data, use_http_filter=False
        )
        assert filtered_regular["password"] == "[REDACTED]"
        assert filtered_regular["user_id"] == "user123"

        # HTTP filter
        filtered_http = filter_sensitive_data(test_data, use_http_filter=True)
        assert filtered_http["password"] == "[REDACTED]"
        assert filtered_http["user_id"] == "user123"
