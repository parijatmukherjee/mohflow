"""
Filters for sensitive data redaction and log sanitization.
Automatically detects and redacts sensitive information from log records.
"""

import re
import json
from typing import Any, Dict, List, Pattern, Set, Union, Optional
from mohflow.static_config import SECURITY_CONFIG, REGEX_PATTERNS


class SensitiveDataFilter:
    """
    Filter for detecting and redacting sensitive information from log data.
    Supports field name matching, regex patterns, and custom filters.
    """

    def __init__(
        self,
        enabled: bool = True,
        sensitive_fields: Optional[Set[str]] = None,
        sensitive_patterns: Optional[List[str]] = None,
        additional_patterns: Optional[List[str]] = None,
        redaction_text: str = SECURITY_CONFIG.REDACTION_PLACEHOLDER,
        max_field_length: int = SECURITY_CONFIG.MAX_FIELD_LENGTH,
        case_sensitive: bool = False,
    ):
        """
        Initialize sensitive data filter.

        Args:
            enabled: Whether the filter is enabled
            sensitive_fields: Set of field names to redact
            sensitive_patterns: List of regex pattern strings
            additional_patterns: Additional patterns to add
            redaction_text: Text to replace sensitive data with
            max_field_length: Maximum length for field values before truncation
            case_sensitive: Whether field name matching is case-sensitive
        """
        self.enabled = enabled
        self.redaction_text = redaction_text
        self.max_field_length = max_field_length
        self.case_sensitive = case_sensitive

        # Build sensitive fields set
        base_fields = set(SECURITY_CONFIG.SENSITIVE_FIELDS)
        if sensitive_fields:
            base_fields.update(sensitive_fields)
        self.sensitive_fields = base_fields

        # Build sensitive patterns list (as strings for tests)
        base_patterns = [
            "password",
            "secret",
            "token",
            "api_key",
            "credit_card",
            "ssn",
            r"\d{4}-\d{4}-\d{4}-\d{4}",  # Credit card
            r"\d{3}-\d{2}-\d{4}",  # SSN
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
        ]
        if sensitive_patterns:
            base_patterns.extend(sensitive_patterns)
        if additional_patterns:
            base_patterns.extend(additional_patterns)
        self.sensitive_patterns = base_patterns

        # Prepare field lookup set
        if not case_sensitive:
            self.sensitive_fields_lower = {
                field.lower()
                for field in self.sensitive_fields
                if field is not None
            }
        else:
            self.sensitive_fields_lower = self.sensitive_fields

    def _get_default_patterns(self) -> List[Pattern]:
        """Get default regex patterns for sensitive data detection"""
        patterns = [
            # Credit card numbers (basic pattern)
            re.compile(
                r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", re.IGNORECASE
            ),
            # Social Security Numbers (US format)
            re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
            # Email addresses (basic pattern)
            re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            # Phone numbers (various formats)
            re.compile(
                r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}"
                r"[-.\s]?[0-9]{4}\b"
            ),
            # IP addresses (IPv4)
            re.compile(REGEX_PATTERNS.IPV4_PATTERN),
            # UUIDs
            re.compile(REGEX_PATTERNS.UUID_PATTERN, re.IGNORECASE),
            # API keys and tokens (common patterns)
            re.compile(
                r"\b[A-Za-z0-9]{32,}\b"
            ),  # 32+ character alphanumeric strings
            re.compile(r"sk-[A-Za-z0-9]{32,}"),  # OpenAI-style keys
            re.compile(r"pk_[A-Za-z0-9]{32,}"),  # Stripe-style public keys
            re.compile(r"sk_[A-Za-z0-9]{32,}"),  # Stripe-style secret keys
            # JWT tokens (basic pattern)
            re.compile(
                r"eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*"
            ),
            # AWS access keys
            re.compile(r"AKIA[0-9A-Z]{16}"),
            # Generic secrets (common naming patterns)
            re.compile(
                r'(?:secret|key|token|password)["\']?\s*[:=]\s*'
                r'["\']?[A-Za-z0-9+/]{20,}["\']?',
                re.IGNORECASE,
            ),
        ]

        return patterns

    def _is_sensitive_field(self, field_name: str) -> bool:
        """
        Check if a field name indicates sensitive data.

        Args:
            field_name: Name of the field to check

        Returns:
            True if field is considered sensitive
        """
        if field_name is None:
            return False
        check_name = (
            field_name.lower() if not self.case_sensitive else field_name
        )

        # Check if any pattern matches the field name
        for pattern in self.sensitive_patterns:
            if isinstance(pattern, str):
                if pattern.lower() in check_name:
                    return True

        return check_name in self.sensitive_fields_lower

    def _is_sensitive_value(self, value: str) -> bool:
        """Check if a value contains sensitive patterns"""
        if not isinstance(value, str):
            return False

        import re

        # Define comprehensive regex patterns for sensitive data
        patterns = [
            # Credit card numbers - with and without dashes/spaces
            r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
            r"\b\d{16}\b",
            # SSN patterns - with and without dashes
            r"\b\d{3}-\d{2}-\d{4}\b",
            r"\b\d{9}\b",
            # Email addresses
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            # Phone numbers
            r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b",  # noqa: E501
            # API keys and tokens (common patterns)
            r"\b[A-Za-z0-9]{32,}\b",
            r"sk-[A-Za-z0-9]{32,}",
            r"pk_[A-Za-z0-9]{32,}",
            # UUIDs
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",  # noqa: E501
        ]

        for pattern in patterns:
            if re.search(pattern, value):
                return True

        return False

    def _redact_sensitive_data(self, data: Any) -> Any:
        """Redact sensitive data from any data structure"""
        if not self.enabled:
            return data
        return self.filter_data(data)

    def filter(self, record):
        """Filter a log record"""
        if not self.enabled:
            return record

        # Get all attributes and filter them
        for attr_name in dir(record):
            if not attr_name.startswith("_") and hasattr(record, attr_name):
                try:
                    value = getattr(record, attr_name)
                    if self._is_sensitive_field(attr_name):
                        setattr(record, attr_name, self.redaction_text)
                    elif isinstance(value, str) and self._is_sensitive_value(
                        value
                    ):
                        setattr(record, attr_name, self.redaction_text)
                    elif isinstance(value, (dict, list)):
                        setattr(
                            record,
                            attr_name,
                            self._redact_sensitive_data(value),
                        )
                except (TypeError, AttributeError):
                    # Skip built-in attributes that can't be modified
                    pass

        return record

    def contains_sensitive_pattern(self, value: str) -> bool:
        """
        Check if a string contains sensitive patterns.

        Args:
            value: String value to check

        Returns:
            True if value contains sensitive patterns
        """
        if not isinstance(value, str):
            return False

        # Use the same logic as _is_sensitive_value
        return self._is_sensitive_value(value)

    def redact_value(self, value: Any, partial: bool = False) -> Any:
        """
        Redact a sensitive value.

        Args:
            value: Value to redact
            partial: If True, show partial value
                (e.g., first/last few characters)

        Returns:
            Redacted value
        """
        if value is None:
            return None

        if isinstance(value, str):
            if len(value) > self.max_field_length:
                # Truncate long values
                value = value[: self.max_field_length] + "..."

            if partial and len(value) > 8:
                # Show first 2 and last 2 characters
                return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
            else:
                return self.redaction_text

        elif isinstance(value, (dict, list)):
            # For complex types, recursively filter
            return self.filter_data(value)

        else:
            # For other types, convert to string and redact
            return self.redaction_text

    def filter_data(self, data: Any) -> Any:
        """
        Filter sensitive data from a data structure.

        Args:
            data: Data structure to filter (dict, list, or primitive)

        Returns:
            Filtered data structure with sensitive data redacted
        """
        if isinstance(data, dict):
            return self._filter_dict(data)
        elif isinstance(data, list):
            return self._filter_list(data)
        elif isinstance(data, str):
            # Check string content for sensitive patterns
            if self.contains_sensitive_pattern(data):
                return self.redact_value(data)
            elif len(data) > self.max_field_length:
                return data[: self.max_field_length] + "..."
            else:
                return data
        else:
            return data

    def _filter_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter sensitive data from dictionary"""
        filtered = {}

        for key, value in data.items():
            if self._is_sensitive_field(key):
                # Redact sensitive field
                filtered[key] = self.redact_value(value, partial=False)
            elif isinstance(value, str) and self.contains_sensitive_pattern(
                value
            ):
                # Redact value containing sensitive patterns
                filtered[key] = self.redact_value(value)
            else:
                # Recursively filter nested structures
                filtered[key] = self.filter_data(value)

        return filtered

    def _filter_list(self, data: List[Any]) -> List[Any]:
        """Filter sensitive data from list"""
        return [self.filter_data(item) for item in data]

    def filter_log_record(self, record_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter sensitive data from a log record.

        Args:
            record_data: Log record data dictionary

        Returns:
            Filtered log record data
        """
        return self.filter_data(record_data)

    def add_sensitive_field(self, field_name: str):
        """Add a field name to the sensitive fields set"""
        if field_name is None:
            return
        self.sensitive_fields.add(field_name)
        if not self.case_sensitive:
            self.sensitive_fields_lower.add(field_name.lower())

    def remove_sensitive_field(self, field_name: str):
        """Remove a field name from the sensitive fields set"""
        if field_name is None:
            return
        self.sensitive_fields.discard(field_name)
        if not self.case_sensitive:
            self.sensitive_fields_lower.discard(field_name.lower())

    def add_sensitive_pattern(self, pattern: Union[str, Pattern]):
        """Add a regex pattern for sensitive data detection"""
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        self.sensitive_patterns.append(pattern)

    def clear_sensitive_patterns(self):
        """Clear all sensitive patterns"""
        self.sensitive_patterns.clear()


class HTTPDataFilter(SensitiveDataFilter):
    """
    Specialized filter for HTTP request/response data.
    Handles headers, query parameters, and body data.
    """

    def __init__(self, **kwargs):
        # Add HTTP-specific sensitive fields
        sensitive_fields = kwargs.get("sensitive_fields", set())
        if isinstance(sensitive_fields, set):
            sensitive_fields.update(SECURITY_CONFIG.SENSITIVE_HEADERS)

        # Add HTTP-specific patterns
        sensitive_patterns = kwargs.get("sensitive_patterns", [])
        if not sensitive_patterns:
            sensitive_patterns = self._get_default_patterns()

        # Add HTTP-specific patterns
        http_patterns = [
            # Bearer tokens
            re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
            # Basic auth
            re.compile(r"Basic\s+[A-Za-z0-9+/]+=*", re.IGNORECASE),
            # Session cookies
            re.compile(r"sessionid=[A-Za-z0-9]+", re.IGNORECASE),
            re.compile(r"csrf_token=[A-Za-z0-9]+", re.IGNORECASE),
        ]

        sensitive_patterns.extend(http_patterns)
        kwargs["sensitive_patterns"] = sensitive_patterns

        super().__init__(**kwargs)

    def filter_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Filter sensitive data from HTTP headers"""
        return self.filter_data(headers)

    def filter_query_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Filter sensitive data from query parameters"""
        return self.filter_data(params)

    def filter_request_body(self, body: Any) -> Any:
        """Filter sensitive data from request body"""
        if isinstance(body, str):
            try:
                # Try to parse as JSON
                parsed = json.loads(body)
                filtered = self.filter_data(parsed)
                return json.dumps(filtered)
            except (json.JSONDecodeError, TypeError):
                # Not JSON, filter as string
                return self.filter_data(body)
        else:
            return self.filter_data(body)

    def filter_http_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter complete HTTP context including headers, params, body.

        Args:
            context: HTTP context with 'headers', 'params', 'body', etc.

        Returns:
            Filtered HTTP context
        """
        filtered = {}

        for key, value in context.items():
            if key == "headers" and isinstance(value, dict):
                filtered[key] = self.filter_headers(value)
            elif key in ("params", "query_params") and isinstance(value, dict):
                filtered[key] = self.filter_query_params(value)
            elif key in ("body", "request_body", "response_body"):
                filtered[key] = self.filter_request_body(value)
            else:
                filtered[key] = self.filter_data(value)

        return filtered


# Singleton instances for common use cases
default_filter = SensitiveDataFilter()
http_filter = HTTPDataFilter()


# Utility functions for common filtering operations
def filter_sensitive_data(data: Any, use_http_filter: bool = False) -> Any:
    """
    Convenience function to filter sensitive data.

    Args:
        data: Data to filter
        use_http_filter: Use HTTP-specific filter

    Returns:
        Filtered data
    """
    filter_instance = http_filter if use_http_filter else default_filter
    return filter_instance.filter_data(data)


def create_custom_filter(
    sensitive_fields: Set[str] = None,
    sensitive_patterns: List[Union[str, Pattern]] = None,
    **kwargs,
) -> SensitiveDataFilter:
    """
    Create a custom sensitive data filter.

    Args:
        sensitive_fields: Custom sensitive field names
        sensitive_patterns: Custom regex patterns
        **kwargs: Additional filter configuration

    Returns:
        Configured SensitiveDataFilter instance
    """
    return SensitiveDataFilter(
        sensitive_fields=sensitive_fields,
        sensitive_patterns=[
            re.compile(p) if isinstance(p, str) else p
            for p in (sensitive_patterns or [])
        ],
        **kwargs,
    )
