"""Tests for context/filters.py — HTTPDataFilter and uncovered paths."""

import json
import pytest
from mohflow.context.filters import (
    SensitiveDataFilter,
    HTTPDataFilter,
)


class TestSensitiveDataFilterRedact:
    def test_redact_none(self):
        f = SensitiveDataFilter()
        assert f.redact_value(None) is None

    def test_redact_short_string(self):
        f = SensitiveDataFilter()
        result = f.redact_value("short")
        assert result == f.redaction_text

    def test_redact_partial_long_string(self):
        f = SensitiveDataFilter()
        result = f.redact_value(
            "a_long_enough_string", partial=True
        )
        assert result.startswith("a_")
        assert result.endswith("ng")
        assert "*" in result

    def test_redact_partial_short_string(self):
        f = SensitiveDataFilter()
        result = f.redact_value("tiny", partial=True)
        assert result == f.redaction_text

    def test_redact_truncates_long_value(self):
        f = SensitiveDataFilter(max_field_length=10)
        long_val = "x" * 50
        result = f.redact_value(long_val)
        assert result == f.redaction_text

    def test_redact_dict_value(self):
        f = SensitiveDataFilter()
        result = f.redact_value({"password": "secret"})
        assert isinstance(result, dict)

    def test_redact_list_value(self):
        f = SensitiveDataFilter()
        result = f.redact_value([1, 2, 3])
        assert isinstance(result, list)

    def test_redact_numeric_value(self):
        f = SensitiveDataFilter()
        result = f.redact_value(12345)
        assert result == f.redaction_text


class TestSensitiveDataFilterMethods:
    def test_add_sensitive_field(self):
        f = SensitiveDataFilter()
        f.add_sensitive_field("my_secret")
        assert "my_secret" in f.sensitive_fields

    def test_add_sensitive_field_none(self):
        f = SensitiveDataFilter()
        f.add_sensitive_field(None)

    def test_remove_sensitive_field(self):
        f = SensitiveDataFilter()
        f.add_sensitive_field("removeme")
        f.remove_sensitive_field("removeme")
        assert "removeme" not in f.sensitive_fields

    def test_remove_sensitive_field_none(self):
        f = SensitiveDataFilter()
        f.remove_sensitive_field(None)

    def test_add_sensitive_pattern_string(self):
        f = SensitiveDataFilter()
        f.add_sensitive_pattern(r"SSN-\d+")
        assert len(f.sensitive_patterns) > 0

    def test_clear_sensitive_patterns(self):
        f = SensitiveDataFilter()
        f.add_sensitive_pattern(r"test")
        f.clear_sensitive_patterns()
        assert len(f.sensitive_patterns) == 0

    def test_filter_log_record(self):
        f = SensitiveDataFilter()
        result = f.filter_log_record(
            {"message": "hi", "password": "secret"}
        )
        assert result["password"] == f.redaction_text

    def test_contains_sensitive_pattern_non_string(self):
        f = SensitiveDataFilter()
        assert f.contains_sensitive_pattern(12345) is False

    def test_filter_data_list(self):
        f = SensitiveDataFilter()
        result = f.filter_data(
            [{"password": "secret"}, "plain"]
        )
        assert isinstance(result, list)
        assert result[0]["password"] == f.redaction_text

    def test_filter_dict_with_sensitive_value(self):
        f = SensitiveDataFilter()
        f.add_sensitive_pattern(r"sk-[a-zA-Z0-9]+")
        result = f.filter_data(
            {"api_key": "sk-abc123xyz"}
        )
        assert result["api_key"] == f.redaction_text


class TestHTTPDataFilter:
    def test_init_creates_filter(self):
        f = HTTPDataFilter()
        assert f is not None

    def test_filter_headers(self):
        f = HTTPDataFilter()
        result = f.filter_headers(
            {"authorization": "Bearer token123"}
        )
        assert "authorization" in result
        assert result["authorization"] == f.redaction_text

    def test_filter_query_params(self):
        f = HTTPDataFilter()
        result = f.filter_query_params(
            {"token": "secret", "page": "1"}
        )
        assert result["token"] == f.redaction_text
        assert result["page"] == "1"

    def test_filter_request_body_json(self):
        f = HTTPDataFilter()
        body = json.dumps(
            {"password": "secret", "name": "John"}
        )
        result = f.filter_request_body(body)
        parsed = json.loads(result)
        assert parsed["password"] == f.redaction_text
        assert parsed["name"] == "John"

    def test_filter_request_body_non_json(self):
        f = HTTPDataFilter()
        body = "not json content"
        result = f.filter_request_body(body)
        assert isinstance(result, str)

    def test_filter_request_body_dict(self):
        f = HTTPDataFilter()
        body = {"password": "secret"}
        result = f.filter_request_body(body)
        assert result["password"] == f.redaction_text

    def test_filter_http_context(self):
        f = HTTPDataFilter()
        ctx = {
            "headers": {
                "authorization": "Bearer xyz"
            },
            "params": {"token": "abc"},
            "body": json.dumps(
                {"password": "secret"}
            ),
            "url": "/api/test",
        }
        result = f.filter_http_context(ctx)
        assert "headers" in result
        assert "params" in result
        assert "body" in result
        assert "url" in result

    def test_filter_http_context_query_params(self):
        f = HTTPDataFilter()
        ctx = {"query_params": {"api_key": "secret"}}
        result = f.filter_http_context(ctx)
        assert (
            result["query_params"]["api_key"]
            == f.redaction_text
        )

    def test_filter_http_context_response_body(self):
        f = HTTPDataFilter()
        ctx = {
            "response_body": {"data": "safe"},
            "request_body": {"password": "secret"},
        }
        result = f.filter_http_context(ctx)
        assert "response_body" in result
        assert "request_body" in result

    def test_init_with_custom_sensitive_fields(self):
        f = HTTPDataFilter(
            sensitive_fields={"my_field"}
        )
        assert "my_field" in f.sensitive_fields

    def test_init_with_custom_patterns(self):
        import re

        pat = re.compile(r"custom_\d+")
        f = HTTPDataFilter(sensitive_patterns=[pat])
        # Should include custom + HTTP patterns
        assert len(f.sensitive_patterns) > 1

    def test_filter_data_preserves_safe_data(self):
        f = HTTPDataFilter()
        result = f.filter_data(
            {"safe_key": "safe_value", "count": 42}
        )
        assert result["safe_key"] == "safe_value"
        assert result["count"] == 42
