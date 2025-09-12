"""
Privacy-aware filter that integrates with the logging system.

Provides intelligent PII filtering with multiple privacy modes and
automatic redaction based on ML-based PII detection.
"""

import logging
from typing import Dict, Any, Optional, Set, List, Tuple
from enum import Enum
from dataclasses import dataclass

from .pii_detector import MLPIIDetector, PIILevel, PIIDetectionResult


class PrivacyMode(Enum):
    """Privacy protection modes."""

    DISABLED = "disabled"  # No privacy filtering
    BASIC = "basic"  # Regex-based filtering only
    INTELLIGENT = "intelligent"  # ML-enhanced filtering
    STRICT = "strict"  # Aggressive filtering with low false negative tolerance
    COMPLIANCE = "compliance"  # Maximum protection for regulatory compliance


@dataclass
class PrivacyConfig:
    """Configuration for privacy-aware filtering."""

    mode: PrivacyMode = PrivacyMode.INTELLIGENT
    min_pii_level: PIILevel = PIILevel.MEDIUM
    preserve_format: bool = True
    hash_low_risk: bool = True
    compliance_mode: Optional[str] = None  # GDPR, HIPAA, PCI-DSS
    allowed_fields: Optional[Set[str]] = None
    blocked_fields: Optional[Set[str]] = None


class PrivacyAwareFilter:
    """
    Advanced privacy filter for logging records.

    Integrates with MohFlow's logging system to provide intelligent
    PII detection and redaction with minimal performance impact.
    """

    def __init__(self, config: Optional[PrivacyConfig] = None):
        """
        Initialize privacy-aware filter.

        Args:
            config: Privacy configuration settings
        """
        self.config = config or PrivacyConfig()
        self._detector = None
        self._initialize_detector()

        # Performance optimization - cache common results
        self._redaction_cache = {}
        self._cache_size_limit = 1000

        # Statistics for monitoring
        self.stats = {
            "total_records_processed": 0,
            "records_with_pii": 0,
            "fields_redacted": 0,
            "cache_hits": 0,
            "detection_time_ms": 0,
        }

    def _initialize_detector(self) -> None:
        """Initialize the PII detector based on privacy mode."""
        enable_ml = self.config.mode in [
            PrivacyMode.INTELLIGENT,
            PrivacyMode.STRICT,
            PrivacyMode.COMPLIANCE,
        ]

        aggressive_mode = self.config.mode in [
            PrivacyMode.STRICT,
            PrivacyMode.COMPLIANCE,
        ]

        self._detector = MLPIIDetector(
            enable_ml=enable_ml, aggressive_mode=aggressive_mode
        )

    def filter_log_record(
        self, record: logging.LogRecord
    ) -> logging.LogRecord:
        """
        Filter a log record for PII, redacting sensitive information.

        Args:
            record: Original log record

        Returns:
            Filtered log record with PII redacted
        """
        if self.config.mode == PrivacyMode.DISABLED:
            return record

        self.stats["total_records_processed"] += 1

        # Create a copy of the record to avoid modifying the original
        filtered_record = logging.LogRecord(
            record.name,
            record.levelno,
            record.pathname,
            record.lineno,
            record.msg,
            record.args,
            record.exc_info,
            record.funcName,
            record.stack_info,
        )

        # Copy all attributes
        for attr_name in dir(record):
            if not attr_name.startswith("_") and not callable(
                getattr(record, attr_name)
            ):
                try:
                    setattr(
                        filtered_record, attr_name, getattr(record, attr_name)
                    )
                except (AttributeError, TypeError):
                    pass

        # Filter the main message
        if hasattr(record, "args") and record.args:
            # Handle parameterized messages
            try:
                formatted_msg = record.getMessage()
                filtered_msg = self._filter_text(formatted_msg)
                filtered_record.msg = filtered_msg
                # Clear args since we've formatted the message
                filtered_record.args = ()
            except (TypeError, ValueError):
                # Fallback: filter the message template and args separately
                filtered_record.msg = self._filter_text(str(record.msg))
                if isinstance(record.args, (list, tuple)):
                    filtered_record.args = tuple(
                        self._filter_value(arg) for arg in record.args
                    )
        else:
            filtered_record.msg = self._filter_text(str(record.msg))

        # Filter additional attributes/fields
        record_dict = record.__dict__.copy()
        had_pii = False

        for attr_name, attr_value in record_dict.items():
            if attr_name.startswith("_") or attr_name in [
                "name",
                "levelno",
                "pathname",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "module",
                "filename",
                "stack_info",
                "exc_info",
                "exc_text",
            ]:
                continue

            # Check if this field should be filtered
            if self._should_filter_field(attr_name):
                filtered_value, has_pii = self._filter_value_with_detection(
                    attr_value, attr_name
                )
                setattr(filtered_record, attr_name, filtered_value)
                if has_pii:
                    had_pii = True
                    self.stats["fields_redacted"] += 1

        if had_pii:
            self.stats["records_with_pii"] += 1

        return filtered_record

    def _should_filter_field(self, field_name: str) -> bool:
        """Determine if a field should be filtered based on configuration."""
        if (
            self.config.allowed_fields
            and field_name in self.config.allowed_fields
        ):
            return False

        if (
            self.config.blocked_fields
            and field_name in self.config.blocked_fields
        ):
            return True

        # Default: filter all fields in strict/compliance modes
        return self.config.mode in [PrivacyMode.STRICT, PrivacyMode.COMPLIANCE]

    def _filter_text(self, text: str) -> str:
        """Filter text content for PII."""
        if not text or not isinstance(text, str):
            return text

        # Check cache first
        if text in self._redaction_cache:
            self.stats["cache_hits"] += 1
            return self._redaction_cache[text]

        result = self._detector.detect_pii(text)

        if result.level.value == "none" or not self._should_redact_level(
            result.level
        ):
            filtered_text = text
        else:
            filtered_text = result.redacted_value

        # Cache the result (with size limit)
        if len(self._redaction_cache) < self._cache_size_limit:
            self._redaction_cache[text] = filtered_text

        return filtered_text

    def _filter_value(
        self, value: Any, field_name: Optional[str] = None
    ) -> Any:
        """Filter a single value for PII."""
        filtered_value, _ = self._filter_value_with_detection(
            value, field_name
        )
        return filtered_value

    def _filter_value_with_detection(
        self, value: Any, field_name: Optional[str] = None
    ) -> Tuple[Any, bool]:
        """Filter a value and return whether PII was detected."""
        if value is None:
            return value, False

        if isinstance(value, str):
            result = self._detector.detect_pii(value, field_name)
            if result.level.value != "none" and self._should_redact_level(
                result.level
            ):
                return result.redacted_value, True
            return value, False

        elif isinstance(value, dict):
            filtered_dict = {}
            has_pii = False
            for k, v in value.items():
                filtered_v, v_has_pii = self._filter_value_with_detection(v, k)
                filtered_dict[k] = filtered_v
                if v_has_pii:
                    has_pii = True
            return filtered_dict, has_pii

        elif isinstance(value, (list, tuple)):
            filtered_items = []
            has_pii = False
            for item in value:
                filtered_item, item_has_pii = (
                    self._filter_value_with_detection(item)
                )
                filtered_items.append(filtered_item)
                if item_has_pii:
                    has_pii = True
            return (
                tuple(filtered_items)
                if isinstance(value, tuple)
                else filtered_items
            ), has_pii

        elif isinstance(value, (int, float, bool)):
            # Numeric values - check if they might be PII
            # (like SSNs stored as numbers)
            result = self._detector.detect_pii(str(value), field_name)
            if result.level.value != "none" and self._should_redact_level(
                result.level
            ):
                return result.redacted_value, True
            return value, False

        else:
            # Other types - convert to string and check
            str_value = str(value)
            result = self._detector.detect_pii(str_value, field_name)
            if result.level.value != "none" and self._should_redact_level(
                result.level
            ):
                return result.redacted_value, True
            return value, False

    def _should_redact_level(self, pii_level: PIILevel) -> bool:
        """
        Determine if a PII level should be redacted based on configuration.
        """
        level_hierarchy = {
            PIILevel.NONE: 0,
            PIILevel.LOW: 1,
            PIILevel.MEDIUM: 2,
            PIILevel.HIGH: 3,
            PIILevel.CRITICAL: 4,
        }

        return (
            level_hierarchy[pii_level]
            >= level_hierarchy[self.config.min_pii_level]
        )

    def scan_record_for_pii(
        self, record: logging.LogRecord
    ) -> Dict[str, PIIDetectionResult]:
        """
        Scan a log record for PII without filtering.

        Useful for auditing and compliance reporting.
        """
        results = {}

        # Scan the main message
        if hasattr(record, "getMessage"):
            try:
                message = record.getMessage()
                result = self._detector.detect_pii(message)
                if result.level != PIILevel.NONE:
                    results["message"] = result
            except (TypeError, ValueError):
                pass

        # Scan additional attributes
        for attr_name, attr_value in record.__dict__.items():
            if attr_name.startswith("_") or attr_name in [
                "name",
                "levelno",
                "pathname",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "module",
                "filename",
                "stack_info",
                "exc_info",
                "exc_text",
            ]:
                continue

            pii_results = self._detector.scan_data_structure(
                {attr_name: attr_value}
            )
            results.update(pii_results)

        return results

    def generate_privacy_report(
        self, records: List[logging.LogRecord]
    ) -> Dict[str, Any]:
        """
        Generate a privacy report for a batch of log records.

        Args:
            records: List of log records to analyze

        Returns:
            Comprehensive privacy analysis report
        """
        total_records = len(records)
        records_with_pii = 0
        all_pii_detections = {}
        pii_types_found = set()
        risk_levels = {
            "none": 0,
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
        }

        for i, record in enumerate(records):
            pii_results = self.scan_record_for_pii(record)

            if pii_results:
                records_with_pii += 1
                all_pii_detections[f"record_{i}"] = pii_results

                for result in pii_results.values():
                    risk_levels[result.level.value] += 1
                    pii_types_found.update(result.detected_types)

        # Calculate privacy score (0-100, lower is better for privacy)
        privacy_score = (
            (records_with_pii / total_records * 100)
            if total_records > 0
            else 0
        )

        # Generate recommendations
        recommendations = []
        if privacy_score > 50:
            recommendations.append(
                "HIGH PRIVACY RISK: Over 50% of log records contain PII"
            )
            recommendations.append(
                "Consider implementing more aggressive filtering"
            )

        if risk_levels["critical"] > 0:
            recommendations.append(
                "CRITICAL: Critical PII detected in logs - immediate action "
                "required"
            )

        if risk_levels["high"] > 0:
            recommendations.append(
                "HIGH RISK: High-risk PII detected - consider data "
                "minimization"
            )

        if not recommendations:
            recommendations.append(
                "Privacy posture acceptable - continue monitoring"
            )

        return {
            "analysis_summary": {
                "total_records": total_records,
                "records_with_pii": records_with_pii,
                "privacy_score": round(privacy_score, 2),
                "pii_types_detected": list(pii_types_found),
                "risk_level_distribution": risk_levels,
            },
            "detailed_detections": all_pii_detections,
            "recommendations": recommendations,
            "filter_statistics": self.stats.copy(),
            "configuration": {
                "privacy_mode": self.config.mode.value,
                "min_pii_level": self.config.min_pii_level.value,
                "compliance_mode": self.config.compliance_mode,
            },
        }

    def get_filter_statistics(self) -> Dict[str, Any]:
        """Get performance and usage statistics for the filter."""
        total_processed = self.stats["total_records_processed"]

        return {
            "total_records_processed": total_processed,
            "records_with_pii": self.stats["records_with_pii"],
            "fields_redacted": self.stats["fields_redacted"],
            "pii_detection_rate": (
                self.stats["records_with_pii"] / total_processed * 100
                if total_processed > 0
                else 0
            ),
            "cache_hit_rate": (
                self.stats["cache_hits"] / total_processed * 100
                if total_processed > 0
                else 0
            ),
            "average_detection_time_ms": (
                self.stats["detection_time_ms"] / total_processed
                if total_processed > 0
                else 0
            ),
        }

    def reset_statistics(self) -> None:
        """Reset filter statistics."""
        self.stats = {
            "total_records_processed": 0,
            "records_with_pii": 0,
            "fields_redacted": 0,
            "cache_hits": 0,
            "detection_time_ms": 0,
        }

    def clear_cache(self) -> None:
        """Clear the redaction cache."""
        self._redaction_cache.clear()


class PrivacyLoggingFilter(logging.Filter):
    """
    Standard Python logging Filter that integrates PrivacyAwareFilter.

    This allows easy integration with existing logging configurations.
    """

    def __init__(self, privacy_config: Optional[PrivacyConfig] = None):
        """Initialize with privacy configuration."""
        super().__init__()
        self.privacy_filter = PrivacyAwareFilter(privacy_config)

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter a log record for PII.

        Returns:
            Always True (doesn't block records, just modifies them)
        """
        # Apply privacy filtering to the record
        filtered_record = self.privacy_filter.filter_log_record(record)

        # Update the original record with filtered content
        for attr_name in dir(filtered_record):
            if not attr_name.startswith("_") and not callable(
                getattr(filtered_record, attr_name)
            ):
                try:
                    setattr(
                        record, attr_name, getattr(filtered_record, attr_name)
                    )
                except (AttributeError, TypeError):
                    pass

        return True  # Never block records, just filter them

    def get_statistics(self) -> Dict[str, Any]:
        """Get privacy filter statistics."""
        return self.privacy_filter.get_filter_statistics()

    def generate_report(
        self, records: List[logging.LogRecord]
    ) -> Dict[str, Any]:
        """Generate privacy report for records."""
        return self.privacy_filter.generate_privacy_report(records)
