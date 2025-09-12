"""
Advanced PII detection using machine learning patterns and heuristics.

This module provides intelligent detection of Personally Identifiable
Information (PII) using both traditional regex patterns and ML-based
classification techniques.
"""

import math
import re
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


# PII Classification Levels
class PIILevel(Enum):
    """Classification levels for PII sensitivity."""

    NONE = "none"  # No PII detected
    LOW = "low"  # Low-risk PII (partial info)
    MEDIUM = "medium"  # Medium-risk PII (identifiable info)
    HIGH = "high"  # High-risk PII (sensitive personal data)
    CRITICAL = "critical"  # Critical PII (SSN, financial data)


@dataclass
class PIIDetectionResult:
    """Result of PII detection analysis."""

    level: PIILevel
    detected_types: List[str]
    confidence_score: float
    redacted_value: str
    original_length: int
    field_name: Optional[str] = None


class MLPIIDetector:
    """
    Machine Learning-based PII detector with pattern recognition.

    Uses ensemble methods combining:
    1. Regex pattern matching
    2. Entropy analysis
    3. Format recognition
    4. Context-aware classification
    5. Named entity recognition (lightweight)
    """

    def __init__(self, enable_ml: bool = True, aggressive_mode: bool = False):
        """
        Initialize the PII detector.

        Args:
            enable_ml: Enable ML-based detection (vs regex-only)
            aggressive_mode: More sensitive detection with higher false
                positives
        """
        self.enable_ml = enable_ml
        self.aggressive_mode = aggressive_mode
        self._setup_patterns()
        self._setup_ml_features()

    def _setup_patterns(self) -> None:
        """Setup regex patterns for known PII types."""

        # High-confidence patterns (Critical Level)
        self.critical_patterns = {
            "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b"),
            "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
            "phone": re.compile(
                r"\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?"
                r"[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b"
            ),
            "passport": re.compile(r"\b[A-Z]{1,2}[0-9]{6,9}\b"),
            "drivers_license": re.compile(r"\b[A-Z]{1,2}[0-9]{6,8}\b"),
        }

        # Medium-confidence patterns (High Level)
        self.high_patterns = {
            "email": re.compile(
                r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            ),
            "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
            "date_birth": re.compile(
                r"\b(?:0[1-9]|1[0-2])[-/](?:0[1-9]|[12][0-9]|3[01])"
                r"[-/](?:19|20)\d{2}\b"
            ),
            "bank_account": re.compile(r"\b[0-9]{8,17}\b"),
        }

        # Lower-confidence patterns (Medium Level)
        self.medium_patterns = {
            "name": re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b"),
            "address": re.compile(
                r"\b\d+\s+[A-Za-z0-9\s,.-]+(?:Street|St|Avenue|Ave|Road|Rd|"
                r"Boulevard|Blvd|Lane|Ln|Drive|Dr)\b",
                re.IGNORECASE,
            ),
            "zip_code": re.compile(r"\b\d{5}(?:-\d{4})?\b"),
            "medical_record": re.compile(r"\b[A-Z]{2,3}\d{6,10}\b"),
        }

        # Context-sensitive patterns (Low Level)
        self.low_patterns = {
            "username": re.compile(r"\b[a-zA-Z0-9._-]{3,20}\b"),
            "token": re.compile(
                r"\b[A-Za-z0-9+/]{20,}={0,2}\b"
            ),  # Base64-like tokens
            "uuid": re.compile(
                r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                r"[0-9a-f]{4}-[0-9a-f]{12}\b",
                re.IGNORECASE,
            ),
        }

        # Compile all patterns for efficient matching
        self.all_patterns = {
            PIILevel.CRITICAL: self.critical_patterns,
            PIILevel.HIGH: self.high_patterns,
            PIILevel.MEDIUM: self.medium_patterns,
            PIILevel.LOW: self.low_patterns,
        }

    def _setup_ml_features(self) -> None:
        """Setup ML-based feature extraction and classification."""

        # High-entropy indicators (potential secrets/tokens)
        self.entropy_threshold = 4.0  # bits per character

        # Common PII field names (context-aware detection)
        self.pii_field_names = {
            "critical": {
                "ssn",
                "social_security",
                "credit_card",
                "ccn",
                "passport",
                "tax_id",
            },
            "high": {
                "email",
                "phone",
                "mobile",
                "date_of_birth",
                "dob",
                "account_number",
            },
            "medium": {
                "name",
                "first_name",
                "last_name",
                "address",
                "street",
                "city",
                "zip",
            },
            "low": {
                "username",
                "user_id",
                "customer_id",
                "ip_address",
                "session_id",
            },
        }

        # ML-like heuristics for format recognition
        self.format_scores = {
            "numeric_sequence": lambda x: (
                len(re.findall(r"\d", x)) / len(x) if x else 0
            ),
            "mixed_case": lambda x: bool(
                re.search(r"[a-z]", x) and re.search(r"[A-Z]", x)
            ),
            "special_chars": lambda x: (
                len(re.findall(r"[^a-zA-Z0-9\s]", x)) / len(x) if x else 0
            ),
            "length_suspicious": lambda x: 8
            <= len(x)
            <= 20,  # Common PII length range
        }

    def calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of text (bits per character)."""
        if not text:
            return 0.0

        # Count character frequencies
        char_counts = {}
        for char in text:
            char_counts[char] = char_counts.get(char, 0) + 1

        # Calculate entropy
        entropy = 0.0
        text_len = len(text)

        for count in char_counts.values():
            probability = count / text_len
            if probability > 0:
                entropy -= probability * math.log2(probability)

        return entropy

    def _extract_ml_features(
        self, text: str, field_name: Optional[str] = None
    ) -> Dict[str, float]:
        """Extract ML features for classification."""
        features = {
            "length": len(text) / 100.0,  # Normalized length
            "entropy": self.calculate_entropy(text)
            / 8.0,  # Normalized entropy
            "digit_ratio": (
                len(re.findall(r"\d", text)) / len(text) if text else 0
            ),
            "alpha_ratio": (
                len(re.findall(r"[a-zA-Z]", text)) / len(text) if text else 0
            ),
            "special_ratio": (
                len(re.findall(r"[^a-zA-Z0-9\s]", text)) / len(text)
                if text
                else 0
            ),
            "whitespace_ratio": (
                len(re.findall(r"\s", text)) / len(text) if text else 0
            ),
        }

        # Format-specific features
        features.update(
            {
                name: (
                    1.0
                    if scorer(text)
                    else 0.0 if callable(scorer) else scorer(text)
                )
                for name, scorer in self.format_scores.items()
            }
        )

        # Field name context
        if field_name:
            field_lower = field_name.lower()
            for level, names in self.pii_field_names.items():
                if any(name in field_lower for name in names):
                    features[f"field_context_{level}"] = 1.0
                    break

        return features

    def _classify_ml(
        self, text: str, field_name: Optional[str] = None
    ) -> Tuple[PIILevel, float]:
        """ML-based classification using feature extraction."""
        features = self._extract_ml_features(text, field_name)

        # Simple ensemble classifier (can be replaced with trained ML model)
        confidence = 0.0
        level = PIILevel.NONE

        # High entropy suggests secrets/tokens
        if features["entropy"] > 0.6:
            confidence += 0.3
            level = PIILevel.MEDIUM

        # Field name context is strong indicator
        for lvl in ["critical", "high", "medium", "low"]:
            if features.get(f"field_context_{lvl}", 0) > 0:
                level = getattr(PIILevel, lvl.upper())
                confidence += 0.4
                break

        # Format patterns
        if (
            features["digit_ratio"] > 0.8 and features["length"] > 0.08
        ):  # Mostly digits, decent length
            confidence += 0.2
            if level == PIILevel.NONE:
                level = PIILevel.LOW

        # Mixed case with special chars (tokens, passwords)
        if features["mixed_case"] and features["special_ratio"] > 0.1:
            confidence += 0.2
            if level == PIILevel.NONE:
                level = PIILevel.LOW

        # Length suspicious for PII
        if features["length_suspicious"]:
            confidence += 0.1

        return level, min(confidence, 1.0)

    def detect_pii(
        self, value: Any, field_name: Optional[str] = None
    ) -> PIIDetectionResult:
        """
        Detect PII in a given value using ensemble methods.

        Args:
            value: The value to analyze for PII
            field_name: Optional field name for context-aware detection

        Returns:
            PIIDetectionResult with classification and confidence
        """
        if value is None:
            return PIIDetectionResult(
                level=PIILevel.NONE,
                detected_types=[],
                confidence_score=0.0,
                redacted_value="null",
                original_length=0,
            )

        text = str(value)
        if not text.strip():
            return PIIDetectionResult(
                level=PIILevel.NONE,
                detected_types=[],
                confidence_score=0.0,
                redacted_value="",
                original_length=0,
            )

        detected_types = []
        max_level = PIILevel.NONE
        max_confidence = 0.0

        # Pattern-based detection
        for level, patterns in self.all_patterns.items():
            for pii_type, pattern in patterns.items():
                if pattern.search(text):
                    detected_types.append(pii_type)
                    if level.value != "none":
                        confidence = self._get_pattern_confidence(
                            pii_type, text
                        )
                        if confidence > max_confidence:
                            max_level = level
                            max_confidence = confidence

        # ML-based enhancement
        if self.enable_ml:
            ml_level, ml_confidence = self._classify_ml(text, field_name)

            # Combine pattern and ML results
            if ml_confidence > max_confidence or (
                ml_confidence > 0.5 and max_level == PIILevel.NONE
            ):
                max_level = ml_level
                max_confidence = max(ml_confidence, max_confidence)

        # Generate redacted value
        redacted_value = self._redact_value(text, max_level, detected_types)

        return PIIDetectionResult(
            level=max_level,
            detected_types=detected_types,
            confidence_score=max_confidence,
            redacted_value=redacted_value,
            original_length=len(text),
            field_name=field_name,
        )

    def _get_pattern_confidence(self, pii_type: str, text: str) -> float:
        """Get confidence score for pattern-based detection."""
        confidence_map = {
            # Critical patterns - very high confidence
            "ssn": 0.95,
            "credit_card": 0.90,
            "passport": 0.85,
            "drivers_license": 0.80,
            # High patterns - high confidence
            "email": 0.85,
            "phone": 0.80,
            "date_birth": 0.75,
            "bank_account": 0.70,
            # Medium patterns - medium confidence
            "name": 0.60,
            "address": 0.65,
            "zip_code": 0.70,
            "medical_record": 0.65,
            # Low patterns - lower confidence
            "username": 0.40,
            "token": 0.50,
            "uuid": 0.60,
            "ip_address": 0.75,
        }

        base_confidence = confidence_map.get(pii_type, 0.5)

        # Adjust based on aggressive mode
        if self.aggressive_mode:
            base_confidence = min(base_confidence + 0.1, 1.0)

        return base_confidence

    def _redact_value(
        self, text: str, level: PIILevel, detected_types: List[str]
    ) -> str:
        """Generate appropriately redacted value based on PII level."""
        if level == PIILevel.NONE:
            return text

        text_len = len(text)

        if level == PIILevel.CRITICAL:
            # Show only first character for critical PII
            return f"{text[0]}{'*' * (text_len - 1)}" if text_len > 1 else "*"

        elif level == PIILevel.HIGH:
            # Show first and last character for high-risk PII
            if text_len <= 2:
                return "*" * text_len
            elif text_len <= 4:
                return f"{text[0]}{'*' * (text_len - 2)}{text[-1]}"
            else:
                return f"{text[:2]}{'*' * (text_len - 4)}{text[-2:]}"

        elif level == PIILevel.MEDIUM:
            # Show more context for medium-risk PII
            if text_len <= 4:
                return "*" * text_len
            else:
                visible_chars = min(text_len // 3, 3)
                return (
                    f"{text[:visible_chars]}"
                    f"{'*' * (text_len - visible_chars * 2)}"
                    f"{text[-visible_chars:]}"
                )

        elif level == PIILevel.LOW:
            # Hash-based redaction for low-risk PII (preserves some utility)
            hash_obj = hashlib.sha256(text.encode())
            hash_hex = hash_obj.hexdigest()[:8]  # Short hash
            return f"<redacted:{hash_hex}>"

        return text

    def scan_data_structure(
        self, data: Any, max_depth: int = 10
    ) -> Dict[str, PIIDetectionResult]:
        """
        Recursively scan a data structure for PII.

        Args:
            data: Data structure to scan (dict, list, or primitive)
            max_depth: Maximum recursion depth

        Returns:
            Dictionary mapping field paths to PII detection results
        """
        results = {}

        def _scan_recursive(obj: Any, path: str, depth: int) -> None:
            if depth > max_depth:
                return

            if isinstance(obj, dict):
                for key, value in obj.items():
                    field_path = f"{path}.{key}" if path else key

                    # Check the key itself for PII indicators
                    if isinstance(value, (str, int, float)):
                        result = self.detect_pii(value, field_name=key)
                        if result.level != PIILevel.NONE:
                            results[field_path] = result

                    # Recurse into nested structures
                    _scan_recursive(value, field_path, depth + 1)

            elif isinstance(obj, (list, tuple)):
                for i, item in enumerate(obj):
                    field_path = f"{path}[{i}]"
                    _scan_recursive(item, field_path, depth + 1)

            elif isinstance(obj, (str, int, float)) and obj is not None:
                result = self.detect_pii(obj)
                if result.level != PIILevel.NONE:
                    results[path or "root"] = result

        _scan_recursive(data, "", 0)
        return results

    def get_privacy_report(self, data: Any) -> Dict[str, Any]:
        """
        Generate a comprehensive privacy report for data.

        Returns:
            Dictionary with privacy analysis and recommendations
        """
        pii_results = self.scan_data_structure(data)

        # Aggregate statistics
        level_counts = {}
        for result in pii_results.values():
            level = result.level.value
            level_counts[level] = level_counts.get(level, 0) + 1

        # Calculate risk score
        risk_weights = {
            PIILevel.CRITICAL: 10,
            PIILevel.HIGH: 7,
            PIILevel.MEDIUM: 4,
            PIILevel.LOW: 1,
            PIILevel.NONE: 0,
        }

        total_risk = sum(
            risk_weights[PIILevel(level)] * count
            for level, count in level_counts.items()
            if level != "none"
        )

        max_possible_risk = len(pii_results) * risk_weights[PIILevel.CRITICAL]
        risk_score = (
            (total_risk / max_possible_risk) if max_possible_risk > 0 else 0
        )

        return {
            "total_fields_scanned": (
                len(pii_results) if pii_results else self._count_fields(data)
            ),
            "pii_fields_detected": len(pii_results),
            "pii_level_counts": level_counts,
            "risk_score": round(risk_score * 100, 2),  # 0-100 scale
            "highest_risk_level": max(
                (
                    PIILevel(level)
                    for level in level_counts.keys()
                    if level != "none"
                ),
                default=PIILevel.NONE,
                key=lambda x: risk_weights[x],
            ).value,
            "detected_pii_types": list(
                set(
                    pii_type
                    for result in pii_results.values()
                    for pii_type in result.detected_types
                )
            ),
            "recommendations": self._generate_recommendations(
                pii_results, risk_score
            ),
        }

    def _count_fields(self, data: Any, max_depth: int = 10) -> int:
        """Count total fields in data structure."""

        def _count_recursive(obj: Any, depth: int) -> int:
            if depth > max_depth:
                return 0

            if isinstance(obj, dict):
                return len(obj) + sum(
                    _count_recursive(v, depth + 1) for v in obj.values()
                )
            elif isinstance(obj, (list, tuple)):
                return sum(_count_recursive(item, depth + 1) for item in obj)
            else:
                return 1

        return _count_recursive(data, 0)

    def _generate_recommendations(
        self, pii_results: Dict[str, PIIDetectionResult], risk_score: float
    ) -> List[str]:
        """Generate privacy recommendations based on scan results."""
        recommendations = []

        if risk_score > 0.7:
            recommendations.append(
                "HIGH RISK: Consider implementing field-level encryption "
                "for sensitive data"
            )
            recommendations.append(
                "Enable aggressive PII filtering in production environments"
            )

        if risk_score > 0.4:
            recommendations.append(
                "MEDIUM RISK: Implement data masking for non-production "
                "environments"
            )
            recommendations.append(
                "Consider using structured logging to separate PII from "
                "operational data"
            )

        if any(
            result.level == PIILevel.CRITICAL
            for result in pii_results.values()
        ):
            recommendations.append(
                "CRITICAL: Remove or encrypt critical PII before logging"
            )

        if len(pii_results) > 10:
            recommendations.append(
                "Large amount of PII detected - consider data minimization"
            )

        if not recommendations:
            recommendations.append(
                "Privacy posture looks good - continue monitoring"
            )

        return recommendations


# Singleton instance for global use
_default_detector = None


def get_pii_detector(
    enable_ml: bool = True, aggressive_mode: bool = False
) -> MLPIIDetector:
    """Get default PII detector instance."""
    global _default_detector
    if _default_detector is None:
        _default_detector = MLPIIDetector(
            enable_ml=enable_ml, aggressive_mode=aggressive_mode
        )
    return _default_detector


# Convenience functions
def detect_pii(
    value: Any, field_name: Optional[str] = None
) -> PIIDetectionResult:
    """Convenience function to detect PII in a value."""
    detector = get_pii_detector()
    return detector.detect_pii(value, field_name)


def scan_for_pii(data: Any) -> Dict[str, PIIDetectionResult]:
    """Convenience function to scan data structure for PII."""
    detector = get_pii_detector()
    return detector.scan_data_structure(data)


def generate_privacy_report(data: Any) -> Dict[str, Any]:
    """Convenience function to generate privacy report."""
    detector = get_pii_detector()
    return detector.get_privacy_report(data)
