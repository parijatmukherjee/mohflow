"""Tests for sensitive data filter module."""

import logging
from mohflow.context.filters import SensitiveDataFilter


class TestSensitiveDataFilter:
    """Test cases for SensitiveDataFilter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = SensitiveDataFilter()

    def test_filter_initialization_defaults(self):
        """Test SensitiveDataFilter initialization with defaults."""
        assert self.filter.enabled is True
        assert self.filter.redaction_text == "[REDACTED]"
        assert len(self.filter.sensitive_patterns) > 0

    def test_filter_initialization_custom(self):
        """Test SensitiveDataFilter initialization with custom settings."""
        custom_patterns = ["custom_secret", "api_token"]
        filter_obj = SensitiveDataFilter(
            enabled=False,
            redaction_text="***",
            additional_patterns=custom_patterns,
        )

        assert filter_obj.enabled is False
        assert filter_obj.redaction_text == "***"
        assert "custom_secret" in filter_obj.sensitive_patterns
        assert "api_token" in filter_obj.sensitive_patterns

    def test_is_sensitive_field_default_patterns(self):
        """Test detection of sensitive fields using default patterns."""
        # Test common sensitive field names
        assert self.filter._is_sensitive_field("password") is True
        assert self.filter._is_sensitive_field("secret") is True
        assert self.filter._is_sensitive_field("token") is True
        assert self.filter._is_sensitive_field("api_key") is True
        assert self.filter._is_sensitive_field("credit_card") is True
        assert self.filter._is_sensitive_field("ssn") is True

        # Test non-sensitive field names
        assert self.filter._is_sensitive_field("username") is False
        assert self.filter._is_sensitive_field("email") is False
        assert self.filter._is_sensitive_field("name") is False

    def test_is_sensitive_field_case_insensitive(self):
        """Test that sensitive field detection is case insensitive."""
        assert self.filter._is_sensitive_field("PASSWORD") is True
        assert self.filter._is_sensitive_field("Password") is True
        assert self.filter._is_sensitive_field("SECRET") is True
        assert self.filter._is_sensitive_field("API_KEY") is True

    def test_is_sensitive_field_partial_match(self):
        """Test partial matching of sensitive patterns."""
        assert self.filter._is_sensitive_field("user_password") is True
        assert self.filter._is_sensitive_field("access_token") is True
        assert self.filter._is_sensitive_field("client_secret") is True
        assert self.filter._is_sensitive_field("database_password") is True

    def test_is_sensitive_value_patterns(self):
        """Test detection of sensitive values using patterns."""
        # Test credit card numbers
        assert self.filter._is_sensitive_value("4111-1111-1111-1111") is True
        assert self.filter._is_sensitive_value("4111111111111111") is True

        # Test SSN patterns
        assert self.filter._is_sensitive_value("123-45-6789") is True
        assert self.filter._is_sensitive_value("123456789") is True

        # Test email patterns
        assert self.filter._is_sensitive_value("user@example.com") is True

        # Test non-sensitive values
        assert self.filter._is_sensitive_value("regular_text") is False
        assert self.filter._is_sensitive_value("123") is False

    def test_redact_sensitive_data_dict(self):
        """Test redacting sensitive data from dictionary."""
        data = {
            "username": "john_doe",
            "password": "secret123",
            "email": "john@example.com",
            "api_key": "sk-abc123xyz",
            "user_id": "12345",
        }

        redacted = self.filter._redact_sensitive_data(data)

        assert redacted["username"] == "john_doe"  # Not sensitive
        assert redacted["password"] == "[REDACTED]"  # Sensitive field
        assert redacted["email"] == "[REDACTED]"  # Sensitive value pattern
        assert redacted["api_key"] == "[REDACTED]"  # Sensitive field
        assert redacted["user_id"] == "12345"  # Not sensitive

    def test_redact_sensitive_data_nested_dict(self):
        """Test redacting sensitive data from nested dictionary."""
        data = {
            "user": {
                "username": "john_doe",
                "password": "secret123",
                "profile": {"email": "john@example.com", "age": 30},
            },
            "auth": {"token": "bearer_token_123"},
        }

        redacted = self.filter._redact_sensitive_data(data)

        assert redacted["user"]["username"] == "john_doe"
        assert redacted["user"]["password"] == "[REDACTED]"
        assert redacted["user"]["profile"]["email"] == "[REDACTED]"
        assert redacted["user"]["profile"]["age"] == 30
        assert redacted["auth"]["token"] == "[REDACTED]"

    def test_redact_sensitive_data_list(self):
        """Test redacting sensitive data from list."""
        data = [
            {"username": "user1", "password": "pass1"},
            {"username": "user2", "password": "pass2"},
        ]

        redacted = self.filter._redact_sensitive_data(data)

        assert redacted[0]["username"] == "user1"
        assert redacted[0]["password"] == "[REDACTED]"
        assert redacted[1]["username"] == "user2"
        assert redacted[1]["password"] == "[REDACTED]"

    def test_redact_sensitive_data_string(self):
        """Test redacting sensitive data from string."""
        sensitive_string = "user@example.com"
        redacted = self.filter._redact_sensitive_data(sensitive_string)
        assert redacted == "[REDACTED]"

        normal_string = "regular text"
        redacted = self.filter._redact_sensitive_data(normal_string)
        assert redacted == "regular text"

    def test_filter_log_record_enabled(self):
        """Test filtering log record when filter is enabled."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User login attempt",
            args=(),
            exc_info=None,
        )

        # Add sensitive attributes
        record.username = "john_doe"
        record.password = "secret123"
        record.email = "john@example.com"

        filtered = self.filter.filter(record)

        assert filtered.username == "john_doe"  # Not sensitive
        assert filtered.password == "[REDACTED]"  # Sensitive
        assert filtered.email == "[REDACTED]"  # Sensitive

    def test_filter_log_record_disabled(self):
        """Test filtering log record when filter is disabled."""
        disabled_filter = SensitiveDataFilter(enabled=False)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User login attempt",
            args=(),
            exc_info=None,
        )

        # Add sensitive attributes
        record.password = "secret123"

        filtered = disabled_filter.filter(record)

        # Should not redact when disabled
        assert filtered.password == "secret123"

    def test_filter_preserves_non_sensitive_data(self):
        """Test that filter preserves non-sensitive data."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User operation",
            args=(),
            exc_info=None,
        )

        # Add various attributes
        record.user_id = "12345"
        record.operation = "create_user"
        record.timestamp = "2023-01-01T00:00:00Z"
        record.status = "success"

        filtered = self.filter.filter(record)

        # All should be preserved as they're not sensitive
        assert filtered.user_id == "12345"
        assert filtered.operation == "create_user"
        assert filtered.timestamp == "2023-01-01T00:00:00Z"
        assert filtered.status == "success"

    def test_custom_redaction_text(self):
        """Test custom redaction text."""
        custom_filter = SensitiveDataFilter(redaction_text="***HIDDEN***")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        record.password = "secret123"

        filtered = custom_filter.filter(record)

        assert filtered.password == "***HIDDEN***"

    def test_additional_patterns(self):
        """Test additional custom patterns."""
        custom_patterns = ["internal_id", "session_key"]
        custom_filter = SensitiveDataFilter(
            additional_patterns=custom_patterns
        )

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        record.internal_id = "internal_12345"
        record.session_key = "sess_abcdef"
        record.normal_field = "normal_value"

        filtered = custom_filter.filter(record)

        assert filtered.internal_id == "[REDACTED]"
        assert filtered.session_key == "[REDACTED]"
        assert filtered.normal_field == "normal_value"

    def test_filter_complex_nested_structures(self):
        """Test filtering complex nested data structures."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Complex data",
            args=(),
            exc_info=None,
        )

        record.request_data = {
            "user": {
                "username": "john",
                "credentials": {
                    "password": "secret",
                    "api_keys": ["key1", "key2"],
                },
            },
            "metadata": {"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"},
        }

        filtered = self.filter.filter(record)

        # Check nested redaction
        assert filtered.request_data["user"]["username"] == "john"
        assert (
            filtered.request_data["user"]["credentials"]["password"]
            == "[REDACTED]"
        )
        assert filtered.request_data["metadata"]["ip"] == "192.168.1.1"

    def test_filter_performance(self):
        """Test that filtering doesn't significantly impact performance."""
        import time

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Performance test",
            args=(),
            exc_info=None,
        )

        # Add multiple attributes
        for i in range(100):
            setattr(record, f"field_{i}", f"value_{i}")

        record.password = "secret"  # One sensitive field

        start_time = time.time()
        for _ in range(1000):
            self.filter.filter(record)
        end_time = time.time()

        # Should complete 1000 filters in under 1 second
        assert (end_time - start_time) < 1.0
