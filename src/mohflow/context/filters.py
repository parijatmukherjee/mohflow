"""
Filters for sensitive data redaction and log sanitization.
Automatically detects and redacts sensitive information from log records.
"""

import re
import json
import time
from enum import Enum
from typing import Any, Dict, List, Pattern, Set, Union, Optional
from mohflow.static_config import SECURITY_CONFIG, REGEX_PATTERNS


class FieldType(Enum):
    """Classification types for fields during filtering."""

    TRACING = "tracing"
    SENSITIVE = "sensitive"
    NEUTRAL = "neutral"


class FieldClassification:
    """Result of field classification analysis."""

    def __init__(
        self,
        field_name: str,
        classification: FieldType,
        matched_pattern: Optional[str] = None,
        exempted: bool = False,
    ):
        """Initialize field classification result."""
        # Allow empty strings for edge case handling
        # Only validate empty string if it's not None

        if not isinstance(classification, FieldType):
            raise ValueError("classification must be valid FieldType")

        if exempted and classification != FieldType.TRACING:
            raise ValueError("exempted=True only allowed for TRACING fields")

        if matched_pattern is not None:
            try:
                re.compile(matched_pattern)
            except re.error:
                raise ValueError(
                    "matched_pattern must be valid regex if provided"
                )

        self.field_name = field_name
        self.classification = classification
        self.matched_pattern = matched_pattern
        self.exempted = exempted

    def __str__(self):
        return (
            f"FieldClassification({self.field_name}, "
            f"{self.classification.name}, exempted={self.exempted})"
        )

    def __eq__(self, other):
        if not isinstance(other, FieldClassification):
            return False
        return (
            self.field_name == other.field_name
            and self.classification == other.classification
            and self.matched_pattern == other.matched_pattern
            and self.exempted == other.exempted
        )


class TracingFieldRegistry:
    """Registry for tracing field patterns and exemptions."""

    DEFAULT_TRACING_FIELDS = set(SECURITY_CONFIG.DEFAULT_TRACING_FIELDS)
    DEFAULT_TRACING_PATTERNS = list(SECURITY_CONFIG.DEFAULT_TRACING_PATTERNS)

    def __init__(self, case_sensitive: bool = False):
        """Initialize tracing field registry."""
        self.case_sensitive = case_sensitive
        self._default_fields = self.DEFAULT_TRACING_FIELDS.copy()
        self.default_patterns = self.DEFAULT_TRACING_PATTERNS.copy()
        self.custom_fields = set()
        self.custom_patterns = []

        # Compile patterns
        self._compiled_patterns = []
        self._all_patterns = []  # Track pattern strings for lookup
        self._compile_patterns()

    @property
    def default_fields(self) -> set:
        """Return immutable copy of default fields."""
        return self._default_fields.copy()

    def _compile_patterns(self):
        """Compile default patterns during initialization."""
        for pattern in self.default_patterns:
            try:
                self._compiled_patterns.append(re.compile(pattern))
                self._all_patterns.append(pattern)
            except re.error:
                pass  # Skip invalid patterns

    def is_tracing_field(self, field_name: str) -> bool:
        """Check if a field name indicates a tracing context."""
        return self.get_tracing_match(field_name) is not None

    def get_tracing_match(self, field_name: str) -> Optional[str]:
        """Get the pattern/field that matched for tracing, or None."""
        if field_name is None or field_name == "" or field_name.isspace():
            return None

        check_name = (
            field_name.lower() if not self.case_sensitive else field_name
        )

        # Check default fields
        default_fields_check = (
            {f.lower() for f in self._default_fields}
            if not self.case_sensitive
            else self._default_fields
        )
        if check_name in default_fields_check:
            return f"default_field:{field_name}"

        # Check custom fields
        custom_fields_check = (
            {f.lower() for f in self.custom_fields}
            if not self.case_sensitive
            else self.custom_fields
        )
        if check_name in custom_fields_check:
            return f"custom_field:{field_name}"

        # Check patterns
        test_name = (
            field_name.lower() if not self.case_sensitive else field_name
        )
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(test_name):
                # Return the original pattern string
                return self._all_patterns[i]

        return None

    def add_custom_field(self, field_name: str) -> None:
        """Add a custom field to the tracing exemption list."""
        if field_name is None:
            raise ValueError("field_name cannot be None")
        if field_name == "" or field_name.isspace():
            raise ValueError("field_name cannot be empty")
        if not re.match(r"^[a-zA-Z0-9_.-]+$", field_name):
            raise ValueError("invalid field name format")

        self.custom_fields.add(field_name)

    def remove_custom_field(self, field_name: str) -> None:
        """Remove a custom field from the tracing exemption list."""
        if field_name in self._default_fields:
            raise ValueError("cannot remove built-in field")
        self.custom_fields.discard(field_name)


class FilterResult:
    """Result of filtering operation with audit information."""

    def __init__(
        self,
        filtered_data: Any,
        redacted_fields: List[str],
        preserved_fields: List[str],
        processing_time: float,
    ):
        """Initialize filter result."""
        if processing_time < 0:
            raise ValueError("processing_time must be non-negative")

        # Check for overlap
        redacted_set = set(redacted_fields)
        preserved_set = set(preserved_fields)
        if redacted_set & preserved_set:
            raise ValueError(
                "redacted_fields and preserved_fields cannot overlap"
            )

        # Check field lists contain only strings
        for field in redacted_fields:
            if not isinstance(field, str):
                raise TypeError("redacted_fields must contain only strings")
        for field in preserved_fields:
            if not isinstance(field, str):
                raise TypeError("preserved_fields must contain only strings")

        self.filtered_data = filtered_data
        self.redacted_fields = redacted_fields
        self.preserved_fields = preserved_fields
        self.processing_time = processing_time

    def get_audit_summary(self) -> str:
        """Get audit summary string."""
        return (
            f"{len(self.redacted_fields)} redacted, "
            f"{len(self.preserved_fields)} preserved, "
            f"processing_time: {self.processing_time:.3f}s"
        )

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        total_fields = len(self.redacted_fields) + len(self.preserved_fields)
        redaction_rate = (
            len(self.redacted_fields) / total_fields if total_fields > 0 else 0
        )
        fields_per_second = (
            total_fields / self.processing_time
            if self.processing_time > 0
            else 0
        )

        return {
            "fields_processed": total_fields,
            "redaction_rate": redaction_rate,
            "processing_time": self.processing_time,
            "fields_per_second": fields_per_second,
        }

    def __eq__(self, other):
        if not isinstance(other, FilterResult):
            return False
        return (
            self.filtered_data == other.filtered_data
            and self.redacted_fields == other.redacted_fields
            and self.preserved_fields == other.preserved_fields
            and abs(self.processing_time - other.processing_time) < 0.001
        )

    def __str__(self):
        return (
            f"FilterResult({len(self.redacted_fields)} redacted, "
            f"{len(self.preserved_fields)} preserved, "
            f"{self.processing_time:.3f}s)"
        )


class FilterConfiguration:
    """Configuration for sensitive data filtering behavior."""

    def __init__(
        self,
        enabled: bool = True,
        exclude_tracing_fields: bool = True,
        custom_safe_fields: Optional[Set[str]] = None,
        tracing_field_patterns: Optional[List[str]] = None,
        sensitive_fields: Optional[Set[str]] = None,
        sensitive_patterns: Optional[List[str]] = None,
        case_sensitive: bool = False,
    ):
        """Initialize filter configuration."""
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be boolean")

        if custom_safe_fields and "" in custom_safe_fields:
            raise ValueError(
                "custom_safe_fields must not contain empty strings"
            )

        if tracing_field_patterns:
            for pattern in tracing_field_patterns:
                try:
                    re.compile(pattern)
                except re.error:
                    raise ValueError("invalid regex pattern")

        self.enabled = enabled
        self.exclude_tracing_fields = exclude_tracing_fields
        self.custom_safe_fields = custom_safe_fields or set()
        self.tracing_field_patterns = tracing_field_patterns or []
        self.sensitive_fields = sensitive_fields or set(
            SECURITY_CONFIG.SENSITIVE_FIELDS
        )
        self.sensitive_patterns = sensitive_patterns or []
        self.case_sensitive = case_sensitive

        # Compile patterns
        self._compiled_patterns = []
        for pattern in self.tracing_field_patterns:
            try:
                self._compiled_patterns.append(re.compile(pattern))
            except re.error:
                pass

        # Build lookup sets
        self._rebuild_lookup_sets()

    def _rebuild_lookup_sets(self):
        """Rebuild field lookup sets."""
        if not self.case_sensitive:
            self._safe_fields_lower = {
                f.lower() for f in self.custom_safe_fields
            }
        else:
            self._safe_fields_lower = self.custom_safe_fields

    def add_safe_field(self, field_name: str):
        """Add a field to safe exemption list."""
        if not field_name or field_name.isspace():
            raise ValueError("invalid field name")
        self.custom_safe_fields.add(field_name)
        self._rebuild_lookup_sets()

    def remove_safe_field(self, field_name: str):
        """Remove a field from safe exemption list."""
        self.custom_safe_fields.discard(field_name)
        self._rebuild_lookup_sets()

    def validate(self):
        """Validate configuration for conflicts."""
        if self.exclude_tracing_fields:
            tracing_fields = set(SECURITY_CONFIG.DEFAULT_TRACING_FIELDS)
            overlap = self.sensitive_fields & (
                tracing_fields | self.custom_safe_fields
            )
            if overlap:
                raise ValueError(
                    "overlap between tracing and sensitive fields"
                )


class SensitiveDataFilter:
    """
    Filter for detecting and redacting sensitive information from log data.
    Supports field name matching, regex patterns, and custom filters.
    """

    def __init__(
        self,
        enabled: bool = True,
        exclude_tracing_fields: bool = True,
        custom_safe_fields: Optional[Set[str]] = None,
        tracing_field_patterns: Optional[List[str]] = None,
        sensitive_fields: Optional[Set[str]] = None,
        sensitive_patterns: Optional[List[str]] = None,
        additional_patterns: Optional[List[str]] = None,
        redaction_text: str = SECURITY_CONFIG.REDACTION_PLACEHOLDER,
        max_field_length: int = SECURITY_CONFIG.MAX_FIELD_LENGTH,
        case_sensitive: bool = False,
    ):
        """
        Initialize enhanced sensitive data filter with tracing exemptions.

        This filter supports preserving distributed tracing fields while
        redacting sensitive authentication and PII data.

        Args:
            enabled: Whether the filter is enabled (default: True)
            exclude_tracing_fields: Whether to exempt tracing fields from
                redaction (default: True). When True, fields like
                'correlation_id', 'trace_id', 'span_id' are preserved.
            custom_safe_fields: Additional field names to exempt from
                redaction (e.g., {'order_id', 'session_id'})
            tracing_field_patterns: Custom regex patterns for tracing
                field detection
            sensitive_fields: Set of field names to always redact
            sensitive_patterns: List of regex patterns for sensitive data
            additional_patterns: Additional regex patterns to add
            redaction_text: Text to replace sensitive data with
                (default: '[REDACTED]')
            max_field_length: Maximum length for field values before truncation
            case_sensitive: Whether field name matching is case-sensitive
        """
        self.enabled = enabled
        self.exclude_tracing_fields = exclude_tracing_fields
        self.redaction_text = redaction_text
        self.max_field_length = max_field_length
        self.case_sensitive = case_sensitive

        # Initialize tracing field registry
        self.tracing_registry = TracingFieldRegistry(
            case_sensitive=case_sensitive
        )
        if custom_safe_fields:
            for field in custom_safe_fields:
                self.tracing_registry.add_custom_field(field)

        if tracing_field_patterns:
            for pattern in tracing_field_patterns:
                try:
                    self.add_tracing_pattern(pattern)
                except ValueError:
                    # Skip invalid patterns gracefully during initialization
                    pass

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

    def classify_field(self, field_name: str) -> FieldClassification:
        """
        Classify a field name to determine how it should be filtered.

        Classification priority:
        1. Tracing fields (if exclude_tracing_fields=True) → TRACING
           (preserved)
        2. Sensitive fields/patterns → SENSITIVE (redacted)
        3. All others → NEUTRAL (unchanged)

        Args:
            field_name: Name of the field to classify

        Returns:
            FieldClassification with field_name, type, and exemption status

        Example:
            >>> filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)
            >>> filter_obj.classify_field("correlation_id")
            FieldClassification(field_name="correlation_id",
                                type=FieldType.TRACING, exempted=True)
            >>> filter_obj.classify_field("api_key")
            FieldClassification(field_name="api_key",
                                type=FieldType.SENSITIVE, exempted=False)
            >>> filter_obj.classify_field("user_id")
            FieldClassification(field_name="user_id",
                                type=FieldType.NEUTRAL, exempted=False)
        """
        if field_name is None or field_name == "" or field_name.isspace():
            return FieldClassification(field_name, FieldType.NEUTRAL)

        # Check if sensitive first (security takes priority)
        if self._is_sensitive_field(field_name):
            return FieldClassification(field_name, FieldType.SENSITIVE)

        # Check tracing exemptions (only if not sensitive)
        if self.exclude_tracing_fields:
            tracing_match = self.tracing_registry.get_tracing_match(field_name)
            if tracing_match:
                return FieldClassification(
                    field_name,
                    FieldType.TRACING,
                    matched_pattern=tracing_match,
                    exempted=True,
                )

        # Default to neutral
        return FieldClassification(field_name, FieldType.NEUTRAL)

    def is_tracing_field(self, field_name: str) -> bool:
        """Check if a field should be exempted as a tracing field."""
        if not self.exclude_tracing_fields:
            return False

        if field_name is None or not isinstance(field_name, str):
            return False

        return self.tracing_registry.is_tracing_field(field_name)

    def add_safe_field(self, field_name: str) -> None:
        """Add a field to the safe exemption list."""
        # Comprehensive validation with consistent error messages
        if field_name is None:
            raise ValueError("invalid field name: cannot be None")
        if not isinstance(field_name, str):
            raise ValueError("invalid field name: must be string")
        if field_name == "" or field_name.isspace():
            raise ValueError("invalid field name: cannot be empty")
        if not re.match(r"^[a-zA-Z0-9_.-]+$", field_name):
            raise ValueError("invalid field name: contains invalid characters")

        # Check for conflicts with sensitive patterns
        field_name_lower = field_name.lower()

        # Check exact matches first
        if field_name_lower in {
            f.lower() for f in SECURITY_CONFIG.SENSITIVE_FIELDS
        }:
            raise ValueError("conflict with sensitive field")

        # Check if field contains sensitive patterns
        for sensitive_field in SECURITY_CONFIG.SENSITIVE_FIELDS:
            if sensitive_field.lower() in field_name_lower:
                raise ValueError("conflict with sensitive field")

        self.tracing_registry.add_custom_field(field_name)

    def remove_safe_field(self, field_name: str) -> None:
        """Remove a field from the safe exemption list."""
        if field_name in SECURITY_CONFIG.DEFAULT_TRACING_FIELDS:
            raise ValueError("cannot remove built-in field")

        self.tracing_registry.remove_custom_field(field_name)

    def add_tracing_pattern(self, pattern: str) -> None:
        """Add a regex pattern for tracing field detection."""
        try:
            re.compile(pattern)
        except re.error:
            raise ValueError("Invalid regex pattern")

        self.tracing_registry.custom_patterns.append(pattern)
        # Recompile patterns
        try:
            self.tracing_registry._compiled_patterns.append(
                re.compile(pattern)
            )
            self.tracing_registry._all_patterns.append(pattern)
        except re.error:
            pass

    def get_configuration(self) -> FilterConfiguration:
        """Get current filter configuration."""
        # Return a copy to prevent external modification
        config = FilterConfiguration(
            enabled=self.enabled,
            exclude_tracing_fields=self.exclude_tracing_fields,
            custom_safe_fields=self.tracing_registry.custom_fields.copy(),
            tracing_field_patterns=(
                self.tracing_registry.custom_patterns.copy()
            ),
            sensitive_fields=self.sensitive_fields.copy(),
            sensitive_patterns=self.sensitive_patterns.copy(),
            case_sensitive=self.case_sensitive,
        )
        return config

    def filter_data_with_audit(self, data: Any) -> FilterResult:
        """
        Filter sensitive data with comprehensive audit trail.

        This method provides enhanced filtering with tracing field exemptions
        and detailed audit information about preserved/redacted fields.

        Args:
            data: Data to filter (dict, list, or other types)

        Returns:
            FilterResult containing:
                - filtered_data: The filtered data structure
                - redacted_fields: List of field paths that were redacted
                - preserved_fields: List of tracing fields that were preserved
                - processing_time: Time taken for filtering in seconds

        Example:
            >>> filter_obj = SensitiveDataFilter(exclude_tracing_fields=True)
            >>> data = {
            ...     "correlation_id": "req-123",      # Preserved (tracing)
            ...     "api_key": "secret-key",          # Redacted (sensitive)
            ...     "user_id": "user-456"             # Untouched (neutral)
            ... }
            >>> result = filter_obj.filter_data_with_audit(data)
            >>> result.filtered_data
            {"correlation_id": "req-123", "api_key": "[REDACTED]",
             "user_id": "user-456"}
            >>> result.preserved_fields
            ["correlation_id"]
            >>> result.redacted_fields
            ["api_key"]
        """
        start_time = time.time()

        if not self.enabled:
            end_time = time.time()
            return FilterResult(data, [], [], end_time - start_time)

        if data is None:
            end_time = time.time()
            return FilterResult(None, [], [], end_time - start_time)

        redacted_fields = []
        preserved_fields = []

        # Track visited objects to prevent circular references
        visited = set()
        filtered_data = self._filter_data_recursive(
            data, redacted_fields, preserved_fields, "", visited
        )

        end_time = time.time()
        return FilterResult(
            filtered_data,
            redacted_fields,
            preserved_fields,
            end_time - start_time,
        )

    def _filter_data_recursive(
        self,
        data: Any,
        redacted_fields: List[str],
        preserved_fields: List[str],
        path: str,
        visited: set,
    ) -> Any:
        """Recursively filter data structure."""
        # Handle circular references
        if isinstance(data, (dict, list)) and id(data) in visited:
            return "[CIRCULAR_REFERENCE]"

        if isinstance(data, (dict, list)):
            visited.add(id(data))
            try:
                if isinstance(data, dict):
                    result = self._filter_dict_data(
                        data, redacted_fields, preserved_fields, path, visited
                    )
                else:
                    result = self._filter_list_data(
                        data, redacted_fields, preserved_fields, path, visited
                    )
                return result
            finally:
                visited.remove(id(data))
        else:
            return data

    def _filter_dict_data(
        self,
        data: Dict[str, Any],
        redacted_fields: List[str],
        preserved_fields: List[str],
        path: str,
        visited: set,
    ) -> Dict[str, Any]:
        """Filter dictionary data."""
        filtered = {}

        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            classification = self.classify_field(key)

            if classification.exempted:
                # Preserve tracing field
                preserved_fields.append(current_path)
                filtered[key] = self._filter_data_recursive(
                    value,
                    redacted_fields,
                    preserved_fields,
                    current_path,
                    visited,
                )
            elif classification.classification == FieldType.SENSITIVE:
                # Redact sensitive field
                redacted_fields.append(current_path)
                filtered[key] = self.redaction_text
            elif isinstance(value, str) and self._is_sensitive_value(value):
                # Redact value with sensitive pattern
                redacted_fields.append(current_path)
                filtered[key] = self.redaction_text
            else:
                # Recursively process
                filtered[key] = self._filter_data_recursive(
                    value,
                    redacted_fields,
                    preserved_fields,
                    current_path,
                    visited,
                )

        return filtered

    def _filter_list_data(
        self,
        data: List[Any],
        redacted_fields: List[str],
        preserved_fields: List[str],
        path: str,
        visited: set,
    ) -> List[Any]:
        """Filter list data."""
        filtered = []
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            filtered_item = self._filter_data_recursive(
                item, redacted_fields, preserved_fields, current_path, visited
            )
            filtered.append(filtered_item)
        return filtered

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
        import re

        for pattern in self.sensitive_patterns:
            if isinstance(pattern, str):
                try:
                    # Try regex match first
                    if re.search(
                        pattern,
                        check_name,
                        re.IGNORECASE if not self.case_sensitive else 0,
                    ):
                        return True
                except re.error:
                    # Fall back to substring match for non-regex patterns
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

        # Handle string values directly
        if isinstance(data, str):
            if self._is_sensitive_value(data):
                return self.redaction_text
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
        Filter sensitive data from a data structure
        (enhanced with tracing field support).

        Args:
            data: Data structure to filter (dict, list, or primitive)

        Returns:
            Filtered data structure with sensitive data redacted
        """
        # Use enhanced filtering with audit trail, but return only
        # the filtered data for backward compatibility
        result = self.filter_data_with_audit(data)
        return result.filtered_data

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
