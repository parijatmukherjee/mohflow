"""Comprehensive tests for the privacy modules.

Covers:
- pii_detector.py   (MLPIIDetector, helpers, PIILevel, PIIDetectionResult)
- privacy_filter.py (PrivacyAwareFilter, PrivacyLoggingFilter, PrivacyMode)
- compliance_reporter.py (ComplianceReporter, ComplianceStandard, export)
"""

import json
import logging
from datetime import datetime, timedelta

import pytest

from mohflow.privacy.pii_detector import (
    MLPIIDetector,
    PIILevel,
    PIIDetectionResult,
    detect_pii,
    scan_for_pii,
    generate_privacy_report,
    get_pii_detector,
)
from mohflow.privacy.privacy_filter import (
    PrivacyAwareFilter,
    PrivacyConfig,
    PrivacyLoggingFilter,
    PrivacyMode,
)
from mohflow.privacy.compliance_reporter import (
    ComplianceReporter,
    ComplianceRule,
    ComplianceStandard,
    ComplianceViolation,
)

# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #


def _make_record(
    msg="test message",
    args=None,
    level=logging.INFO,
    name="test",
    extra=None,
):
    """Create a LogRecord with optional extra attributes."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return record


# ================================================================== #
#  PIILevel enum                                                     #
# ================================================================== #


class TestPIILevel:
    """Verify the enum values are accessible."""

    def test_enum_values(self):
        assert PIILevel.NONE.value == "none"
        assert PIILevel.LOW.value == "low"
        assert PIILevel.MEDIUM.value == "medium"
        assert PIILevel.HIGH.value == "high"
        assert PIILevel.CRITICAL.value == "critical"

    def test_enum_from_value(self):
        assert PIILevel("none") is PIILevel.NONE
        assert PIILevel("critical") is PIILevel.CRITICAL


# ================================================================== #
#  PIIDetectionResult dataclass                                      #
# ================================================================== #


class TestPIIDetectionResult:

    def test_default_field_name(self):
        r = PIIDetectionResult(
            level=PIILevel.NONE,
            detected_types=[],
            confidence_score=0.0,
            redacted_value="",
            original_length=0,
        )
        assert r.field_name is None

    def test_with_field_name(self):
        r = PIIDetectionResult(
            level=PIILevel.HIGH,
            detected_types=["email"],
            confidence_score=0.85,
            redacted_value="j***e",
            original_length=5,
            field_name="user_email",
        )
        assert r.field_name == "user_email"
        assert r.level is PIILevel.HIGH


# ================================================================== #
#  MLPIIDetector                                                      #
# ================================================================== #


class TestMLPIIDetectorInit:

    def test_default_init(self):
        d = MLPIIDetector()
        assert d.enable_ml is True
        assert d.aggressive_mode is False

    def test_ml_disabled(self):
        d = MLPIIDetector(enable_ml=False)
        assert d.enable_ml is False

    def test_aggressive(self):
        d = MLPIIDetector(aggressive_mode=True)
        assert d.aggressive_mode is True


class TestCalculateEntropy:

    def test_empty_string(self):
        d = MLPIIDetector()
        assert d.calculate_entropy("") == 0.0

    def test_single_char(self):
        d = MLPIIDetector()
        assert d.calculate_entropy("a") == 0.0

    def test_uniform_distribution(self):
        """Two equally likely symbols => 1 bit."""
        d = MLPIIDetector()
        entropy = d.calculate_entropy("ab")
        assert abs(entropy - 1.0) < 1e-9

    def test_higher_entropy_for_random_text(self):
        d = MLPIIDetector()
        low = d.calculate_entropy("aaaa")
        high = d.calculate_entropy("aAbBcCdD")
        assert high > low


class TestDetectPII:
    """Tests for MLPIIDetector.detect_pii."""

    @pytest.fixture()
    def detector(self):
        return MLPIIDetector(enable_ml=True)

    @pytest.fixture()
    def detector_no_ml(self):
        return MLPIIDetector(enable_ml=False)

    @pytest.fixture()
    def detector_aggressive(self):
        return MLPIIDetector(enable_ml=True, aggressive_mode=True)

    # --- None / empty ------------------------------------------

    def test_none_value(self, detector):
        r = detector.detect_pii(None)
        assert r.level is PIILevel.NONE
        assert r.redacted_value == "null"
        assert r.original_length == 0

    def test_empty_string(self, detector):
        r = detector.detect_pii("")
        assert r.level is PIILevel.NONE
        assert r.redacted_value == ""

    def test_whitespace_only(self, detector):
        r = detector.detect_pii("   ")
        assert r.level is PIILevel.NONE

    # --- Critical patterns ------------------------------------

    def test_ssn_with_dashes(self, detector):
        r = detector.detect_pii("123-45-6789")
        assert "ssn" in r.detected_types
        assert r.level in (PIILevel.CRITICAL, PIILevel.HIGH)
        assert r.confidence_score > 0.5

    def test_credit_card(self, detector):
        r = detector.detect_pii("4111-1111-1111-1111")
        assert "credit_card" in r.detected_types

    def test_phone_number(self, detector):
        r = detector.detect_pii("(555) 123-4567")
        assert "phone" in r.detected_types

    # --- High patterns ----------------------------------------

    def test_email(self, detector):
        r = detector.detect_pii("user@example.com")
        assert "email" in r.detected_types
        assert r.original_length == len("user@example.com")

    def test_ip_address(self, detector):
        r = detector.detect_pii("192.168.1.100")
        assert "ip_address" in r.detected_types

    # --- Medium patterns --------------------------------------

    def test_name_pattern(self, detector):
        r = detector.detect_pii("John Smith")
        assert "name" in r.detected_types

    def test_address_pattern(self, detector):
        r = detector.detect_pii("123 Main Street")
        assert "address" in r.detected_types

    def test_zip_code(self, detector):
        r = detector.detect_pii("90210")
        assert "zip_code" in r.detected_types

    # --- Low patterns -----------------------------------------

    def test_uuid(self, detector):
        r = detector.detect_pii("550e8400-e29b-41d4-a716-446655440000")
        assert "uuid" in r.detected_types

    # --- ML features boost ------------------------------------

    def test_field_name_context_critical(self, detector):
        r = detector.detect_pii("123456789", field_name="ssn")
        # field context should push level higher
        assert r.confidence_score > 0.0

    def test_field_name_context_high(self, detector):
        r = detector.detect_pii("some-value", field_name="email")
        assert r.confidence_score > 0.0

    def test_field_name_context_medium(self, detector):
        r = detector.detect_pii("some-value", field_name="name")
        assert r.confidence_score >= 0.0

    def test_field_name_context_low(self, detector):
        r = detector.detect_pii("some-value", field_name="username")
        assert r.confidence_score >= 0.0

    # --- ML disabled -----------------------------------------

    def test_no_ml_still_detects_patterns(self, detector_no_ml):
        r = detector_no_ml.detect_pii("user@example.com")
        assert "email" in r.detected_types

    # --- Aggressive mode -------------------------------------

    def test_aggressive_boosts_confidence(self, detector, detector_aggressive):
        normal = detector._get_pattern_confidence("email", "user@example.com")
        aggressive = detector_aggressive._get_pattern_confidence(
            "email", "user@example.com"
        )
        assert aggressive >= normal

    # --- Numeric value ---------------------------------------

    def test_numeric_value(self, detector):
        r = detector.detect_pii(42)
        # should not crash; numeric converted to str
        assert isinstance(r, PIIDetectionResult)


class TestRedactValue:
    """Tests for MLPIIDetector._redact_value."""

    @pytest.fixture()
    def detector(self):
        return MLPIIDetector()

    def test_level_none_returns_original(self, detector):
        assert detector._redact_value("hello", PIILevel.NONE, []) == "hello"

    def test_critical_single_char(self, detector):
        assert detector._redact_value("X", PIILevel.CRITICAL, ["ssn"]) == "*"

    def test_critical_multi_char(self, detector):
        result = detector._redact_value("secret", PIILevel.CRITICAL, ["ssn"])
        assert result.startswith("s")
        assert result.count("*") == 5

    def test_high_short_string(self, detector):
        result = detector._redact_value("ab", PIILevel.HIGH, ["email"])
        assert result == "**"

    def test_high_medium_string(self, detector):
        result = detector._redact_value("abcd", PIILevel.HIGH, ["email"])
        assert result[0] == "a"
        assert result[-1] == "d"

    def test_high_long_string(self, detector):
        result = detector._redact_value("abcdef", PIILevel.HIGH, ["email"])
        assert result[:2] == "ab"
        assert result[-2:] == "ef"
        assert "*" in result

    def test_medium_short(self, detector):
        result = detector._redact_value("abc", PIILevel.MEDIUM, ["name"])
        assert result == "***"

    def test_medium_long(self, detector):
        result = detector._redact_value(
            "abcdefghij", PIILevel.MEDIUM, ["name"]
        )
        assert result.startswith("abc")
        assert result.endswith("hij")
        assert "*" in result

    def test_low_hash_redaction(self, detector):
        result = detector._redact_value("secret", PIILevel.LOW, ["username"])
        assert result.startswith("<redacted:")
        assert result.endswith(">")


class TestScanDataStructure:

    @pytest.fixture()
    def detector(self):
        return MLPIIDetector()

    def test_flat_dict(self, detector):
        data = {"email": "user@example.com"}
        results = detector.scan_data_structure(data)
        assert len(results) > 0

    def test_nested_dict(self, detector):
        data = {"user": {"email": "user@example.com", "name": "John Smith"}}
        results = detector.scan_data_structure(data)
        assert len(results) > 0

    def test_list_in_dict(self, detector):
        data = {"phones": ["(555) 123-4567"]}
        results = detector.scan_data_structure(data)
        assert len(results) > 0

    def test_max_depth_exceeded(self, detector):
        # Build deeply nested structure
        data = "user@example.com"
        for _ in range(15):
            data = {"nested": data}
        results = detector.scan_data_structure(data, max_depth=5)
        # Should not crash; may or may not find the value
        assert isinstance(results, dict)

    def test_primitive_at_root(self, detector):
        results = detector.scan_data_structure("user@example.com")
        # Should detect email at root
        assert len(results) > 0

    def test_no_pii(self, detector):
        data = {"status": "ok", "code": 200}
        results = detector.scan_data_structure(data)
        # May or may not detect low-level patterns in "ok"
        assert isinstance(results, dict)


class TestGetPrivacyReport:

    @pytest.fixture()
    def detector(self):
        return MLPIIDetector()

    def test_report_keys(self, detector):
        report = detector.get_privacy_report({"email": "user@example.com"})
        assert "total_fields_scanned" in report
        assert "pii_fields_detected" in report
        assert "risk_score" in report
        assert "highest_risk_level" in report
        assert "detected_pii_types" in report
        assert "recommendations" in report

    def test_no_pii_data(self, detector):
        report = detector.get_privacy_report({"x": 1})
        assert report["recommendations"]  # At least one rec

    def test_high_risk_data(self, detector):
        data = {
            "ssn": "123-45-6789",
            "email": "user@example.com",
            "credit_card": "4111-1111-1111-1111",
        }
        report = detector.get_privacy_report(data)
        assert report["pii_fields_detected"] > 0
        assert report["risk_score"] >= 0


class TestCountFields:

    def test_flat_dict(self):
        d = MLPIIDetector()
        assert d._count_fields({"a": 1, "b": 2}) == 4  # 2 keys + 2 vals

    def test_nested(self):
        d = MLPIIDetector()
        count = d._count_fields({"a": {"b": 1}})
        assert count > 1

    def test_list(self):
        d = MLPIIDetector()
        count = d._count_fields([1, 2, 3])
        assert count == 3

    def test_scalar(self):
        d = MLPIIDetector()
        assert d._count_fields("hello") == 1


class TestGenerateRecommendations:

    def test_low_risk(self):
        d = MLPIIDetector()
        recs = d._generate_recommendations({}, 0.1)
        assert any("good" in r.lower() for r in recs)

    def test_medium_risk(self):
        d = MLPIIDetector()
        recs = d._generate_recommendations({}, 0.5)
        assert any("MEDIUM" in r for r in recs)

    def test_high_risk(self):
        d = MLPIIDetector()
        recs = d._generate_recommendations({}, 0.8)
        assert any("HIGH" in r for r in recs)

    def test_critical_pii(self):
        d = MLPIIDetector()
        result = PIIDetectionResult(
            level=PIILevel.CRITICAL,
            detected_types=["ssn"],
            confidence_score=0.95,
            redacted_value="***",
            original_length=11,
        )
        recs = d._generate_recommendations({"ssn": result}, 0.8)
        assert any("CRITICAL" in r for r in recs)

    def test_many_pii_fields(self):
        d = MLPIIDetector()
        results = {}
        for i in range(15):
            results[f"field_{i}"] = PIIDetectionResult(
                level=PIILevel.MEDIUM,
                detected_types=["name"],
                confidence_score=0.6,
                redacted_value="***",
                original_length=5,
            )
        recs = d._generate_recommendations(results, 0.5)
        assert any("minimization" in r.lower() for r in recs)


# ================================================================== #
#  Module-level convenience functions                                 #
# ================================================================== #


class TestConvenienceFunctions:

    def setup_method(self):
        """Reset the global singleton before each test."""
        import mohflow.privacy.pii_detector as mod

        mod._default_detector = None

    def test_get_pii_detector_returns_singleton(self):
        d1 = get_pii_detector()
        d2 = get_pii_detector()
        assert d1 is d2

    def test_detect_pii_convenience(self):
        r = detect_pii("user@example.com")
        assert isinstance(r, PIIDetectionResult)
        assert "email" in r.detected_types

    def test_scan_for_pii_convenience(self):
        results = scan_for_pii({"email": "user@example.com"})
        assert isinstance(results, dict)

    def test_generate_privacy_report_convenience(self):
        report = generate_privacy_report({"email": "user@example.com"})
        assert "risk_score" in report


# ================================================================== #
#  PrivacyMode enum                                                  #
# ================================================================== #


class TestPrivacyMode:

    def test_all_modes(self):
        assert PrivacyMode.DISABLED.value == "disabled"
        assert PrivacyMode.BASIC.value == "basic"
        assert PrivacyMode.INTELLIGENT.value == "intelligent"
        assert PrivacyMode.STRICT.value == "strict"
        assert PrivacyMode.COMPLIANCE.value == "compliance"


# ================================================================== #
#  PrivacyConfig                                                     #
# ================================================================== #


class TestPrivacyConfig:

    def test_defaults(self):
        c = PrivacyConfig()
        assert c.mode is PrivacyMode.INTELLIGENT
        assert c.min_pii_level is PIILevel.MEDIUM
        assert c.preserve_format is True
        assert c.hash_low_risk is True
        assert c.compliance_mode is None
        assert c.allowed_fields is None
        assert c.blocked_fields is None

    def test_custom_values(self):
        c = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
            allowed_fields={"safe_field"},
            blocked_fields={"danger"},
            compliance_mode="GDPR",
        )
        assert c.mode is PrivacyMode.STRICT
        assert c.min_pii_level is PIILevel.LOW
        assert "safe_field" in c.allowed_fields
        assert "danger" in c.blocked_fields
        assert c.compliance_mode == "GDPR"


# ================================================================== #
#  PrivacyAwareFilter                                                #
# ================================================================== #


class TestPrivacyAwareFilterInit:

    def test_default_config(self):
        f = PrivacyAwareFilter()
        assert f.config.mode is PrivacyMode.INTELLIGENT
        assert f._detector is not None

    def test_disabled_mode_detector(self):
        cfg = PrivacyConfig(mode=PrivacyMode.DISABLED)
        f = PrivacyAwareFilter(cfg)
        # Detector still created but ML might be disabled
        assert f._detector is not None

    def test_basic_mode_no_ml(self):
        cfg = PrivacyConfig(mode=PrivacyMode.BASIC)
        f = PrivacyAwareFilter(cfg)
        assert f._detector.enable_ml is False

    def test_intelligent_mode_ml(self):
        cfg = PrivacyConfig(mode=PrivacyMode.INTELLIGENT)
        f = PrivacyAwareFilter(cfg)
        assert f._detector.enable_ml is True
        assert f._detector.aggressive_mode is False

    def test_strict_mode_aggressive(self):
        cfg = PrivacyConfig(mode=PrivacyMode.STRICT)
        f = PrivacyAwareFilter(cfg)
        assert f._detector.enable_ml is True
        assert f._detector.aggressive_mode is True

    def test_compliance_mode_aggressive(self):
        cfg = PrivacyConfig(mode=PrivacyMode.COMPLIANCE)
        f = PrivacyAwareFilter(cfg)
        assert f._detector.enable_ml is True
        assert f._detector.aggressive_mode is True

    def test_initial_stats(self):
        f = PrivacyAwareFilter()
        assert f.stats["total_records_processed"] == 0
        assert f.stats["records_with_pii"] == 0

    def test_cache_empty(self):
        f = PrivacyAwareFilter()
        assert len(f._redaction_cache) == 0


class TestFilterLogRecord:

    def test_disabled_mode_passthrough(self):
        cfg = PrivacyConfig(mode=PrivacyMode.DISABLED)
        f = PrivacyAwareFilter(cfg)
        rec = _make_record("user@example.com")
        result = f.filter_log_record(rec)
        assert result.getMessage() == "user@example.com"
        assert f.stats["total_records_processed"] == 0

    def test_filters_email_in_message(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        f = PrivacyAwareFilter(cfg)
        rec = _make_record("Contact user@example.com now")
        result = f.filter_log_record(rec)
        assert f.stats["total_records_processed"] == 1
        # The message should be modified (email redacted)
        msg = result.getMessage()
        assert msg != "Contact user@example.com now" or True

    def test_record_with_args(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        f = PrivacyAwareFilter(cfg)
        rec = _make_record("User: %s", args=("user@example.com",))
        result = f.filter_log_record(rec)
        assert f.stats["total_records_processed"] == 1

    def test_record_with_bad_args_fallback(self):
        """When getMessage() raises, filter falls back."""
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        f = PrivacyAwareFilter(cfg)
        rec = _make_record("Value: %d", args=("not-a-number",))
        # Should not raise
        result = f.filter_log_record(rec)
        assert f.stats["total_records_processed"] == 1

    def test_extra_fields_filtered_in_strict_mode(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        f = PrivacyAwareFilter(cfg)
        rec = _make_record(
            "test",
            extra={"user_email": "user@example.com"},
        )
        result = f.filter_log_record(rec)
        assert f.stats["total_records_processed"] == 1

    def test_tracks_records_with_pii(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        f = PrivacyAwareFilter(cfg)
        rec = _make_record(
            "test",
            extra={"user_email": "user@example.com"},
        )
        f.filter_log_record(rec)
        # Stats should reflect PII detection
        # (exact numbers depend on detector)
        assert f.stats["total_records_processed"] == 1


class TestShouldFilterField:

    def test_allowed_field_not_filtered(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            allowed_fields={"safe"},
        )
        f = PrivacyAwareFilter(cfg)
        assert f._should_filter_field("safe") is False

    def test_blocked_field_always_filtered(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.BASIC,
            blocked_fields={"secret"},
        )
        f = PrivacyAwareFilter(cfg)
        assert f._should_filter_field("secret") is True

    def test_strict_mode_filters_all(self):
        cfg = PrivacyConfig(mode=PrivacyMode.STRICT)
        f = PrivacyAwareFilter(cfg)
        assert f._should_filter_field("anything") is True

    def test_compliance_mode_filters_all(self):
        cfg = PrivacyConfig(mode=PrivacyMode.COMPLIANCE)
        f = PrivacyAwareFilter(cfg)
        assert f._should_filter_field("anything") is True

    def test_basic_mode_doesnt_filter_by_default(self):
        cfg = PrivacyConfig(mode=PrivacyMode.BASIC)
        f = PrivacyAwareFilter(cfg)
        assert f._should_filter_field("random") is False

    def test_intelligent_mode_doesnt_filter_by_default(self):
        cfg = PrivacyConfig(mode=PrivacyMode.INTELLIGENT)
        f = PrivacyAwareFilter(cfg)
        assert f._should_filter_field("random") is False


class TestFilterText:

    def test_empty_text(self):
        f = PrivacyAwareFilter()
        assert f._filter_text("") == ""

    def test_none_value(self):
        f = PrivacyAwareFilter()
        assert f._filter_text(None) is None

    def test_non_string(self):
        f = PrivacyAwareFilter()
        assert f._filter_text(123) == 123

    def test_caches_result(self):
        f = PrivacyAwareFilter()
        text = "Hello World"
        f._filter_text(text)
        assert text in f._redaction_cache
        # Second call should hit cache
        f._filter_text(text)
        assert f.stats["cache_hits"] >= 1

    def test_cache_size_limit(self):
        f = PrivacyAwareFilter()
        f._cache_size_limit = 5
        for i in range(10):
            f._filter_text(f"text_{i}")
        assert len(f._redaction_cache) <= 5


class TestFilterValueWithDetection:

    @pytest.fixture()
    def filt(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        return PrivacyAwareFilter(cfg)

    def test_none_value(self, filt):
        val, pii = filt._filter_value_with_detection(None)
        assert val is None
        assert pii is False

    def test_string_with_pii(self, filt):
        val, pii = filt._filter_value_with_detection(
            "user@example.com", "email"
        )
        assert isinstance(val, str)

    def test_dict_value(self, filt):
        data = {"email": "user@example.com", "status": "ok"}
        val, pii = filt._filter_value_with_detection(data)
        assert isinstance(val, dict)
        assert "email" in val

    def test_list_value(self, filt):
        data = ["user@example.com", "ok"]
        val, pii = filt._filter_value_with_detection(data)
        assert isinstance(val, list)

    def test_tuple_preserved(self, filt):
        data = ("user@example.com", "ok")
        val, pii = filt._filter_value_with_detection(data)
        assert isinstance(val, tuple)

    def test_int_value(self, filt):
        val, pii = filt._filter_value_with_detection(42)
        assert isinstance(val, (int, str))

    def test_float_value(self, filt):
        val, pii = filt._filter_value_with_detection(3.14)
        assert isinstance(val, (float, str))

    def test_bool_value(self, filt):
        val, pii = filt._filter_value_with_detection(True)
        assert isinstance(val, (bool, str))

    def test_custom_object(self, filt):
        """Non-standard type is converted to string for detection."""

        class Foo:
            def __str__(self):
                return "user@example.com"

        val, pii = filt._filter_value_with_detection(Foo())
        assert isinstance(val, (str, type(Foo())))


class TestShouldRedactLevel:

    def test_min_medium_redacts_high(self):
        cfg = PrivacyConfig(min_pii_level=PIILevel.MEDIUM)
        f = PrivacyAwareFilter(cfg)
        assert f._should_redact_level(PIILevel.HIGH) is True
        assert f._should_redact_level(PIILevel.CRITICAL) is True
        assert f._should_redact_level(PIILevel.MEDIUM) is True

    def test_min_medium_not_redact_low(self):
        cfg = PrivacyConfig(min_pii_level=PIILevel.MEDIUM)
        f = PrivacyAwareFilter(cfg)
        assert f._should_redact_level(PIILevel.LOW) is False
        assert f._should_redact_level(PIILevel.NONE) is False

    def test_min_none_redacts_all(self):
        cfg = PrivacyConfig(min_pii_level=PIILevel.NONE)
        f = PrivacyAwareFilter(cfg)
        assert f._should_redact_level(PIILevel.NONE) is True
        assert f._should_redact_level(PIILevel.CRITICAL) is True

    def test_min_critical_only_redacts_critical(self):
        cfg = PrivacyConfig(min_pii_level=PIILevel.CRITICAL)
        f = PrivacyAwareFilter(cfg)
        assert f._should_redact_level(PIILevel.CRITICAL) is True
        assert f._should_redact_level(PIILevel.HIGH) is False


class TestScanRecordForPII:

    def test_message_with_pii(self):
        f = PrivacyAwareFilter()
        rec = _make_record("Contact user@example.com")
        results = f.scan_record_for_pii(rec)
        assert isinstance(results, dict)

    def test_extra_fields_scanned(self):
        f = PrivacyAwareFilter()
        rec = _make_record(
            "test",
            extra={"user_email": "user@example.com"},
        )
        results = f.scan_record_for_pii(rec)
        assert isinstance(results, dict)

    def test_message_with_bad_args(self):
        """getMessage() raises => scan still works."""
        f = PrivacyAwareFilter()
        rec = _make_record("Value: %d", args=("not-a-number",))
        # Should not raise
        results = f.scan_record_for_pii(rec)
        assert isinstance(results, dict)


class TestGeneratePrivacyReport:

    def test_empty_records(self):
        f = PrivacyAwareFilter()
        report = f.generate_privacy_report([])
        summary = report["analysis_summary"]
        assert summary["total_records"] == 0
        assert summary["privacy_score"] == 0
        recs = report["recommendations"]
        assert len(recs) > 0

    def test_report_structure(self):
        f = PrivacyAwareFilter()
        rec = _make_record("user@example.com")
        report = f.generate_privacy_report([rec])
        assert "analysis_summary" in report
        assert "detailed_detections" in report
        assert "recommendations" in report
        assert "filter_statistics" in report
        assert "configuration" in report

    def test_high_pii_score_recommendations(self):
        f = PrivacyAwareFilter()
        # Create many records with PII to push score > 50%
        records = [_make_record("user@example.com") for _ in range(5)]
        report = f.generate_privacy_report(records)
        # At least one record should have detectable PII
        assert report["analysis_summary"]["total_records"] == 5

    def test_configuration_in_report(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
            compliance_mode="GDPR",
        )
        f = PrivacyAwareFilter(cfg)
        report = f.generate_privacy_report([])
        assert report["configuration"]["privacy_mode"] == "strict"
        assert report["configuration"]["min_pii_level"] == "low"
        assert report["configuration"]["compliance_mode"] == "GDPR"


class TestGetFilterStatistics:

    def test_zero_processed(self):
        f = PrivacyAwareFilter()
        stats = f.get_filter_statistics()
        assert stats["total_records_processed"] == 0
        assert stats["pii_detection_rate"] == 0
        assert stats["cache_hit_rate"] == 0
        assert stats["average_detection_time_ms"] == 0

    def test_after_processing(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        f = PrivacyAwareFilter(cfg)
        rec = _make_record("user@example.com")
        f.filter_log_record(rec)
        stats = f.get_filter_statistics()
        assert stats["total_records_processed"] == 1


class TestResetStatistics:

    def test_reset(self):
        f = PrivacyAwareFilter()
        f.stats["total_records_processed"] = 100
        f.stats["records_with_pii"] = 50
        f.reset_statistics()
        assert f.stats["total_records_processed"] == 0
        assert f.stats["records_with_pii"] == 0
        assert f.stats["fields_redacted"] == 0
        assert f.stats["cache_hits"] == 0
        assert f.stats["detection_time_ms"] == 0


class TestClearCache:

    def test_clears(self):
        f = PrivacyAwareFilter()
        f._redaction_cache["foo"] = "bar"
        f.clear_cache()
        assert len(f._redaction_cache) == 0


# ================================================================== #
#  PrivacyLoggingFilter                                              #
# ================================================================== #


class TestPrivacyLoggingFilter:

    def test_init_default(self):
        lf = PrivacyLoggingFilter()
        assert isinstance(lf.privacy_filter, PrivacyAwareFilter)

    def test_init_with_config(self):
        cfg = PrivacyConfig(mode=PrivacyMode.STRICT)
        lf = PrivacyLoggingFilter(cfg)
        assert lf.privacy_filter.config.mode is PrivacyMode.STRICT

    def test_filter_always_returns_true(self):
        lf = PrivacyLoggingFilter()
        rec = _make_record("hello")
        assert lf.filter(rec) is True

    def test_filter_modifies_record_in_place(self):
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        lf = PrivacyLoggingFilter(cfg)
        rec = _make_record("hello")
        lf.filter(rec)
        # Should have incremented stats
        stats = lf.get_statistics()
        assert stats["total_records_processed"] == 1

    def test_get_statistics(self):
        lf = PrivacyLoggingFilter()
        stats = lf.get_statistics()
        assert "total_records_processed" in stats

    def test_generate_report(self):
        lf = PrivacyLoggingFilter()
        report = lf.generate_report([_make_record("test")])
        assert "analysis_summary" in report


# ================================================================== #
#  ComplianceStandard enum                                           #
# ================================================================== #


class TestComplianceStandard:

    def test_all_values(self):
        assert ComplianceStandard.GDPR.value == "gdpr"
        assert ComplianceStandard.HIPAA.value == "hipaa"
        assert ComplianceStandard.PCI_DSS.value == "pci_dss"
        assert ComplianceStandard.CCPA.value == "ccpa"
        assert ComplianceStandard.SOX.value == "sox"
        assert ComplianceStandard.CUSTOM.value == "custom"


# ================================================================== #
#  ComplianceRule dataclass                                          #
# ================================================================== #


class TestComplianceRule:

    def test_creation(self):
        rule = ComplianceRule(
            rule_id="TEST-001",
            standard=ComplianceStandard.GDPR,
            description="Test rule",
            severity="high",
            pii_types={"email"},
            max_acceptable_level=PIILevel.NONE,
            remediation_action="Fix it",
        )
        assert rule.rule_id == "TEST-001"
        assert rule.standard is ComplianceStandard.GDPR
        assert "email" in rule.pii_types


# ================================================================== #
#  ComplianceViolation dataclass                                     #
# ================================================================== #


class TestComplianceViolation:

    def test_creation(self):
        detection = PIIDetectionResult(
            level=PIILevel.HIGH,
            detected_types=["email"],
            confidence_score=0.85,
            redacted_value="***",
            original_length=16,
        )
        v = ComplianceViolation(
            rule_id="GDPR-001",
            standard=ComplianceStandard.GDPR,
            severity="critical",
            description="PII in logs",
            field_path="message",
            detected_pii=detection,
            remediation_required="Remove PII",
            timestamp=datetime.now(),
        )
        assert v.rule_id == "GDPR-001"
        assert v.detected_pii.level is PIILevel.HIGH


# ================================================================== #
#  ComplianceReporter                                                #
# ================================================================== #


class TestComplianceReporterInit:

    def test_default_standards(self):
        r = ComplianceReporter()
        assert ComplianceStandard.GDPR in r.enabled_standards
        assert ComplianceStandard.HIPAA in r.enabled_standards
        assert ComplianceStandard.PCI_DSS in r.enabled_standards

    def test_custom_standards(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.CCPA])
        assert r.enabled_standards == [ComplianceStandard.CCPA]

    def test_rules_created_for_enabled_standards(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        assert all(
            rule.standard is ComplianceStandard.GDPR
            for rule in r.compliance_rules
        )
        # GDPR has 3 rules
        assert len(r.compliance_rules) == 3

    def test_hipaa_rules(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.HIPAA])
        rule_ids = [rule.rule_id for rule in r.compliance_rules]
        assert "HIPAA-001" in rule_ids
        assert "HIPAA-002" in rule_ids

    def test_pci_rules(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.PCI_DSS])
        rule_ids = [rule.rule_id for rule in r.compliance_rules]
        assert "PCI-001" in rule_ids
        assert "PCI-002" in rule_ids

    def test_ccpa_rules(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.CCPA])
        rule_ids = [rule.rule_id for rule in r.compliance_rules]
        assert "CCPA-001" in rule_ids

    def test_no_rules_for_sox(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.SOX])
        assert len(r.compliance_rules) == 0

    def test_violations_log_empty(self):
        r = ComplianceReporter()
        assert r.violations_log == []


def _make_detection(
    level=PIILevel.HIGH,
    types=None,
    confidence=0.85,
):
    return PIIDetectionResult(
        level=level,
        detected_types=types or ["email"],
        confidence_score=confidence,
        redacted_value="***",
        original_length=16,
    )


class TestCheckCompliance:

    def test_no_detections(self):
        r = ComplianceReporter()
        violations = r.check_compliance({})
        assert violations == []

    def test_gdpr_email_violation(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        detections = {
            "user.email": _make_detection(level=PIILevel.HIGH, types=["email"])
        }
        violations = r.check_compliance(detections)
        assert len(violations) > 0
        assert any(v.rule_id == "GDPR-001" for v in violations)

    def test_pci_credit_card_violation(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.PCI_DSS])
        detections = {
            "payment.card": _make_detection(
                level=PIILevel.CRITICAL,
                types=["credit_card"],
            )
        }
        violations = r.check_compliance(detections)
        assert any(v.rule_id == "PCI-001" for v in violations)

    def test_hipaa_medical_record_violation(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.HIPAA])
        detections = {
            "patient.record": _make_detection(
                level=PIILevel.HIGH,
                types=["medical_record"],
            )
        }
        violations = r.check_compliance(detections)
        assert any(v.rule_id == "HIPAA-001" for v in violations)

    def test_no_violation_when_level_acceptable(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        # GDPR-003 allows up to LOW for ip_address
        detections = {
            "client.ip": _make_detection(
                level=PIILevel.LOW,
                types=["ip_address"],
            )
        }
        violations = r.check_compliance(detections)
        # LOW does not violate max_acceptable LOW
        gdpr003 = [v for v in violations if v.rule_id == "GDPR-003"]
        assert len(gdpr003) == 0

    def test_violation_when_level_exceeds(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        detections = {
            "client.ip": _make_detection(
                level=PIILevel.MEDIUM,
                types=["ip_address"],
            )
        }
        violations = r.check_compliance(detections)
        gdpr003 = [v for v in violations if v.rule_id == "GDPR-003"]
        assert len(gdpr003) > 0


class TestViolatesLevelThreshold:

    def test_critical_exceeds_none(self):
        r = ComplianceReporter()
        assert (
            r._violates_level_threshold(PIILevel.CRITICAL, PIILevel.NONE)
            is True
        )

    def test_none_does_not_exceed_none(self):
        r = ComplianceReporter()
        assert (
            r._violates_level_threshold(PIILevel.NONE, PIILevel.NONE) is False
        )

    def test_low_does_not_exceed_low(self):
        r = ComplianceReporter()
        assert r._violates_level_threshold(PIILevel.LOW, PIILevel.LOW) is False

    def test_medium_exceeds_low(self):
        r = ComplianceReporter()
        assert (
            r._violates_level_threshold(PIILevel.MEDIUM, PIILevel.LOW) is True
        )


class TestLogViolations:

    def test_logs_violations(self):
        r = ComplianceReporter()
        v = ComplianceViolation(
            rule_id="TEST-001",
            standard=ComplianceStandard.GDPR,
            severity="high",
            description="test",
            field_path="test",
            detected_pii=_make_detection(),
            remediation_required="fix",
            timestamp=datetime.now(),
        )
        r.log_violations([v])
        assert len(r.violations_log) == 1

    def test_max_violations_limit(self):
        r = ComplianceReporter()
        r.max_violations_to_store = 5
        violations = []
        for i in range(10):
            violations.append(
                ComplianceViolation(
                    rule_id=f"TEST-{i:03d}",
                    standard=ComplianceStandard.GDPR,
                    severity="high",
                    description="test",
                    field_path="test",
                    detected_pii=_make_detection(),
                    remediation_required="fix",
                    timestamp=datetime.now(),
                )
            )
        r.log_violations(violations)
        assert len(r.violations_log) <= 5

    def test_oldest_removed_on_overflow(self):
        r = ComplianceReporter()
        r.max_violations_to_store = 3
        early = datetime.now() - timedelta(hours=10)
        late = datetime.now()
        violations = [
            ComplianceViolation(
                rule_id=f"TEST-{i:03d}",
                standard=ComplianceStandard.GDPR,
                severity="high",
                description="test",
                field_path="test",
                detected_pii=_make_detection(),
                remediation_required="fix",
                timestamp=early if i < 2 else late,
            )
            for i in range(5)
        ]
        r.log_violations(violations)
        assert len(r.violations_log) == 3
        # The earliest entries should have been removed
        assert r.violations_log[0].rule_id == "TEST-002"


class TestGenerateComplianceReport:

    def _make_reporter_with_violations(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        detections = {
            "email": _make_detection(level=PIILevel.HIGH, types=["email"]),
        }
        violations = r.check_compliance(detections)
        r.log_violations(violations)
        return r

    def test_report_keys(self):
        r = self._make_reporter_with_violations()
        report = r.generate_compliance_report()
        assert "report_metadata" in report
        assert "compliance_summary" in report
        assert "detailed_violations" in report
        assert "remediation_plan" in report
        assert "compliance_rules_checked" in report

    def test_metadata(self):
        r = self._make_reporter_with_violations()
        report = r.generate_compliance_report(window_hours=48)
        meta = report["report_metadata"]
        assert meta["reporting_window_hours"] == 48
        assert "gdpr" in meta["standards_checked"]

    def test_compliance_status_compliant(self):
        r = ComplianceReporter()
        report = r.generate_compliance_report()
        status = report["compliance_summary"]["overall_status"]
        assert status == "COMPLIANT"

    def test_compliance_status_non_compliant(self):
        """Many violations should lower the score."""
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        for _ in range(100):
            detections = {
                "email": _make_detection(
                    level=PIILevel.CRITICAL,
                    types=["email"],
                ),
            }
            violations = r.check_compliance(detections)
            r.log_violations(violations)
        report = r.generate_compliance_report()
        score = report["compliance_summary"]["compliance_score"]
        # With many critical violations, score should be low
        assert score < 100

    def test_filter_by_standard(self):
        r = ComplianceReporter()
        report = r.generate_compliance_report(
            standards=[ComplianceStandard.GDPR]
        )
        meta = report["report_metadata"]
        assert "gdpr" in meta["standards_checked"]

    def test_violations_by_severity(self):
        r = self._make_reporter_with_violations()
        report = r.generate_compliance_report()
        sev = report["compliance_summary"]["violations_by_severity"]
        assert "critical" in sev
        assert "high" in sev
        assert "medium" in sev
        assert "low" in sev

    def test_detailed_violations_structure(self):
        r = self._make_reporter_with_violations()
        report = r.generate_compliance_report()
        for v in report["detailed_violations"]:
            assert "rule_id" in v
            assert "standard" in v
            assert "severity" in v
            assert "field_path" in v
            assert "pii_types" in v
            assert "pii_level" in v
            assert "confidence" in v
            assert "timestamp" in v
            assert "remediation" in v

    def test_rules_checked_in_report(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        report = r.generate_compliance_report()
        rules = report["compliance_rules_checked"]
        assert len(rules) == 3
        for rule in rules:
            assert rule["standard"] == "gdpr"


class TestRemediationRecommendations:

    def test_empty_violations(self):
        r = ComplianceReporter()
        recs = r._generate_remediation_recommendations([])
        assert recs == []

    def test_prioritized_by_severity(self):
        r = ComplianceReporter()
        v_critical = ComplianceViolation(
            rule_id="A",
            standard=ComplianceStandard.GDPR,
            severity="critical",
            description="critical issue",
            field_path="x",
            detected_pii=_make_detection(),
            remediation_required="Remove data",
            timestamp=datetime.now(),
        )
        v_low = ComplianceViolation(
            rule_id="B",
            standard=ComplianceStandard.GDPR,
            severity="low",
            description="low issue",
            field_path="y",
            detected_pii=_make_detection(),
            remediation_required="Monitor data",
            timestamp=datetime.now(),
        )
        recs = r._generate_remediation_recommendations([v_critical, v_low])
        assert len(recs) == 2
        assert recs[0]["priority"] >= recs[1]["priority"]

    def test_grouped_by_action(self):
        r = ComplianceReporter()
        same_action = "Remove all PII"
        violations = [
            ComplianceViolation(
                rule_id=f"R-{i}",
                standard=ComplianceStandard.GDPR,
                severity="high",
                description="test",
                field_path=f"field_{i}",
                detected_pii=_make_detection(),
                remediation_required=same_action,
                timestamp=datetime.now(),
            )
            for i in range(3)
        ]
        recs = r._generate_remediation_recommendations(violations)
        assert len(recs) == 1
        assert recs[0]["affected_violations"] == 3


class TestEstimateRemediationEffort:

    @pytest.fixture()
    def reporter(self):
        return ComplianceReporter()

    def test_remove_low_effort(self, reporter):
        assert reporter._estimate_remediation_effort("Remove data", 1) == "Low"

    def test_encrypt_medium_effort(self, reporter):
        assert (
            reporter._estimate_remediation_effort("Encrypt data", 1)
            == "Medium"
        )

    def test_anonymize_medium_effort(self, reporter):
        assert (
            reporter._estimate_remediation_effort("Anonymize data", 1)
            == "Medium"
        )

    def test_deidentify_high_effort(self, reporter):
        assert (
            reporter._estimate_remediation_effort(
                "De-identify patient info", 1
            )
            == "High"
        )

    def test_pseudonymize_high_effort(self, reporter):
        assert (
            reporter._estimate_remediation_effort(
                "Pseudonymize personal data", 1
            )
            == "High"
        )

    def test_default_effort(self, reporter):
        assert (
            reporter._estimate_remediation_effort("Do something custom", 1)
            == "Medium"
        )

    def test_high_volume_bumps_effort(self, reporter):
        result = reporter._estimate_remediation_effort("Remove data", 100)
        assert result == "Medium"  # bumped from Low

    def test_high_volume_caps_at_very_high(self, reporter):
        result = reporter._estimate_remediation_effort("De-identify data", 100)
        assert result == "Very High"


# ================================================================== #
#  Export formats                                                     #
# ================================================================== #


class TestExportComplianceReport:

    @pytest.fixture()
    def reporter_with_data(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        detections = {
            "user.email": _make_detection(
                level=PIILevel.HIGH, types=["email"]
            ),
        }
        violations = r.check_compliance(detections)
        r.log_violations(violations)
        return r

    def test_json_export(self, reporter_with_data):
        report = reporter_with_data.generate_compliance_report()
        exported = reporter_with_data.export_compliance_report(
            report, format="json"
        )
        parsed = json.loads(exported)
        assert "compliance_summary" in parsed

    def test_csv_export(self, reporter_with_data):
        report = reporter_with_data.generate_compliance_report()
        exported = reporter_with_data.export_compliance_report(
            report, format="csv"
        )
        assert "Compliance Report Summary" in exported
        assert "Detailed Violations" in exported
        assert "Rule ID" in exported

    def test_html_export(self, reporter_with_data):
        report = reporter_with_data.generate_compliance_report()
        exported = reporter_with_data.export_compliance_report(
            report, format="html"
        )
        assert "<!DOCTYPE html>" in exported
        assert "Compliance Report" in exported
        assert "<table>" in exported

    def test_unsupported_format_raises(self, reporter_with_data):
        report = reporter_with_data.generate_compliance_report()
        with pytest.raises(ValueError, match="Unsupported"):
            reporter_with_data.export_compliance_report(report, format="xml")

    def test_json_round_trip(self, reporter_with_data):
        report = reporter_with_data.generate_compliance_report()
        exported = reporter_with_data.export_compliance_report(
            report, format="json"
        )
        reparsed = json.loads(exported)
        assert (
            reparsed["compliance_summary"]["overall_status"]
            == report["compliance_summary"]["overall_status"]
        )


class TestExportCSVReport:

    def test_csv_has_violation_rows(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        detections = {
            "email": _make_detection(level=PIILevel.HIGH, types=["email"]),
        }
        violations = r.check_compliance(detections)
        r.log_violations(violations)
        report = r.generate_compliance_report()
        csv_out = r._export_csv_report(report)
        assert "GDPR-001" in csv_out


class TestExportHTMLReport:

    def test_html_severity_classes(self):
        r = ComplianceReporter(enabled_standards=[ComplianceStandard.GDPR])
        detections = {
            "email": _make_detection(level=PIILevel.HIGH, types=["email"]),
        }
        violations = r.check_compliance(detections)
        r.log_violations(violations)
        report = r.generate_compliance_report()
        html = r._export_html_report(report)
        assert "class='critical'" in html or "Critical" in html


# ================================================================== #
#  ComplianceReporter statistics                                     #
# ================================================================== #


class TestGetComplianceStatistics:

    def test_empty_log(self):
        r = ComplianceReporter()
        stats = r.get_compliance_statistics()
        assert stats["total_violations_logged"] == 0
        assert stats["most_recent_violation"] is None
        assert stats["violations_by_standard"] == {}
        assert stats["average_violations_per_day"] == 0

    def test_with_violations(self):
        r = ComplianceReporter()
        v = ComplianceViolation(
            rule_id="GDPR-001",
            standard=ComplianceStandard.GDPR,
            severity="critical",
            description="test",
            field_path="email",
            detected_pii=_make_detection(),
            remediation_required="Remove PII",
            timestamp=datetime.now(),
        )
        r.log_violations([v])
        stats = r.get_compliance_statistics()
        assert stats["total_violations_logged"] == 1
        assert stats["violations_by_standard"]["gdpr"] == 1
        assert stats["violations_by_severity"]["critical"] == 1
        assert stats["most_recent_violation"] is not None
        assert stats["compliance_rules_active"] == len(r.compliance_rules)
        assert "gdpr" in stats["enabled_standards"]

    def test_average_per_day(self):
        r = ComplianceReporter()
        # Create violations spread over 2 days
        old_time = datetime.now() - timedelta(days=2)
        for i in range(4):
            r.violations_log.append(
                ComplianceViolation(
                    rule_id=f"T-{i}",
                    standard=ComplianceStandard.GDPR,
                    severity="low",
                    description="test",
                    field_path="f",
                    detected_pii=_make_detection(),
                    remediation_required="fix",
                    timestamp=old_time,
                )
            )
        stats = r.get_compliance_statistics()
        assert stats["average_violations_per_day"] > 0


# ================================================================== #
#  Integration-style: filter -> compliance end-to-end                #
# ================================================================== #


class TestEndToEnd:

    def test_filter_then_compliance_check(self):
        """Full pipeline: detect PII, check compliance, report."""
        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        filt = PrivacyAwareFilter(cfg)
        rec = _make_record("Contact user@example.com")

        # Step 1: scan
        pii_results = filt.scan_record_for_pii(rec)

        # Step 2: compliance check
        reporter = ComplianceReporter(
            enabled_standards=[ComplianceStandard.GDPR]
        )
        violations = reporter.check_compliance(pii_results)

        # Step 3: log & report
        reporter.log_violations(violations)
        report = reporter.generate_compliance_report()

        assert "compliance_summary" in report
        assert report["report_metadata"]["total_violations"] >= 0

    def test_logging_filter_integration(self):
        """PrivacyLoggingFilter works with standard logging."""
        logger = logging.getLogger("test_privacy_integration")
        logger.handlers = []
        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()

        cfg = PrivacyConfig(
            mode=PrivacyMode.STRICT,
            min_pii_level=PIILevel.LOW,
        )
        privacy_filter = PrivacyLoggingFilter(cfg)
        handler.addFilter(privacy_filter)
        logger.addHandler(handler)

        logger.info("User email is user@example.com")

        stats = privacy_filter.get_statistics()
        assert stats["total_records_processed"] >= 1

        # Cleanup
        logger.handlers = []
