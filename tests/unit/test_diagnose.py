"""Comprehensive tests for mohflow.diagnose module.

Covers DiagnosticFormatter, FrameInfo, _safe_repr, _is_sensitive_name,
variable masking, max_depth limiting, production auto-disable,
exclude_modules, nested exceptions, and _SKIP_VARS filtering.
"""

import os
import sys
import traceback
from types import TracebackType
from unittest.mock import MagicMock, patch

import pytest

from mohflow.diagnose import (
    DiagnosticFormatter,
    FrameInfo,
    _is_sensitive_name,
    _safe_repr,
    _SENSITIVE_PATTERNS,
    _SKIP_VARS,
)

# ── _is_sensitive_name tests ─────────────────────────────────────


class TestIsSensitiveName:
    """Tests for the _is_sensitive_name helper."""

    def test_password_is_sensitive(self):
        assert _is_sensitive_name("password") is True

    def test_user_password_is_sensitive(self):
        assert _is_sensitive_name("user_password") is True

    def test_secret_is_sensitive(self):
        assert _is_sensitive_name("secret") is True

    def test_db_secret_is_sensitive(self):
        assert _is_sensitive_name("db_secret") is True

    def test_token_is_sensitive(self):
        assert _is_sensitive_name("token") is True

    def test_auth_token_is_sensitive(self):
        assert _is_sensitive_name("auth_token") is True

    def test_api_key_is_sensitive(self):
        assert _is_sensitive_name("api_key") is True

    def test_apikey_is_sensitive(self):
        assert _is_sensitive_name("apikey") is True

    def test_api_hyphen_key_is_sensitive(self):
        assert _is_sensitive_name("api-key") is True

    def test_auth_is_sensitive(self):
        assert _is_sensitive_name("auth") is True

    def test_credential_is_sensitive(self):
        assert _is_sensitive_name("credential") is True

    def test_private_key_is_sensitive(self):
        assert _is_sensitive_name("private_key") is True

    def test_private_hyphen_key_is_sensitive(self):
        assert _is_sensitive_name("private-key") is True

    def test_session_id_is_sensitive(self):
        assert _is_sensitive_name("session_id") is True

    def test_session_hyphen_id_is_sensitive(self):
        assert _is_sensitive_name("session-id") is True

    def test_access_key_is_sensitive(self):
        assert _is_sensitive_name("access_key") is True

    def test_normal_name_not_sensitive(self):
        assert _is_sensitive_name("user_id") is False

    def test_count_not_sensitive(self):
        assert _is_sensitive_name("count") is False

    def test_name_not_sensitive(self):
        assert _is_sensitive_name("name") is False

    def test_case_insensitive(self):
        assert _is_sensitive_name("PASSWORD") is True
        assert _is_sensitive_name("Api_Key") is True
        assert _is_sensitive_name("SECRET") is True


# ── _safe_repr tests ─────────────────────────────────────────────


class TestSafeRepr:
    """Tests for the _safe_repr helper."""

    def test_string_repr(self):
        assert _safe_repr("hello") == "'hello'"

    def test_int_repr(self):
        assert _safe_repr(42) == "42"

    def test_float_repr(self):
        assert _safe_repr(3.14) == "3.14"

    def test_none_repr(self):
        assert _safe_repr(None) == "None"

    def test_bool_repr(self):
        assert _safe_repr(True) == "True"

    def test_list_repr(self):
        assert _safe_repr([1, 2, 3]) == "[1, 2, 3]"

    def test_dict_repr(self):
        result = _safe_repr({"a": 1})
        assert "a" in result
        assert "1" in result

    def test_truncation(self):
        long_str = "x" * 300
        result = _safe_repr(long_str, max_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_truncation_at_exact_limit(self):
        """Value exactly at max_length should not be truncated."""
        val = "a" * 10  # repr is 'aaaaaaaaaa' = 12 chars
        result = _safe_repr(val, max_length=12)
        assert result == repr(val)
        assert "..." not in result

    def test_truncation_over_limit(self):
        val = "a" * 20  # repr is 'aaaa...' = 22 chars
        result = _safe_repr(val, max_length=15)
        assert len(result) == 15
        assert result.endswith("...")

    def test_repr_failure_returns_safe_string(self):
        """If repr() raises, _safe_repr returns '<repr failed>'."""

        class BadRepr:
            def __repr__(self):
                raise RuntimeError("repr exploded")

        result = _safe_repr(BadRepr())
        assert result == "<repr failed>"

    def test_default_max_length(self):
        """Default max_length is 200."""
        long_val = "z" * 250
        result = _safe_repr(long_val)
        assert len(result) == 200
        assert result.endswith("...")

    def test_empty_string(self):
        assert _safe_repr("") == "''"

    def test_tuple_repr(self):
        assert _safe_repr((1, 2)) == "(1, 2)"

    def test_set_repr(self):
        result = _safe_repr({1})
        assert "1" in result


# ── FrameInfo tests ──────────────────────────────────────────────


class TestFrameInfo:
    """Tests for the FrameInfo data class."""

    def test_attributes(self):
        fi = FrameInfo(
            filename="test.py",
            lineno=42,
            function="my_func",
            code_context="x = 1 + 2",
            local_vars={"x": "3"},
        )
        assert fi.filename == "test.py"
        assert fi.lineno == 42
        assert fi.function == "my_func"
        assert fi.code_context == "x = 1 + 2"
        assert fi.local_vars == {"x": "3"}

    def test_to_dict_basic(self):
        fi = FrameInfo(
            filename="test.py",
            lineno=10,
            function="func",
            code_context="pass",
            local_vars={"a": "1"},
        )
        d = fi.to_dict()
        assert d["filename"] == "test.py"
        assert d["lineno"] == 10
        assert d["function"] == "func"
        assert d["code"] == "pass"
        assert d["locals"] == {"a": "1"}

    def test_to_dict_no_code_context(self):
        fi = FrameInfo(
            filename="test.py",
            lineno=10,
            function="func",
            code_context=None,
            local_vars={"a": "1"},
        )
        d = fi.to_dict()
        assert "code" not in d
        assert "locals" in d

    def test_to_dict_no_local_vars(self):
        fi = FrameInfo(
            filename="test.py",
            lineno=10,
            function="func",
            code_context="x = 1",
            local_vars={},
        )
        d = fi.to_dict()
        assert "code" in d
        assert "locals" not in d

    def test_to_dict_neither_code_nor_vars(self):
        fi = FrameInfo(
            filename="f.py",
            lineno=1,
            function="fn",
            code_context=None,
            local_vars={},
        )
        d = fi.to_dict()
        assert d == {"filename": "f.py", "lineno": 1, "function": "fn"}

    def test_slots_defined(self):
        assert hasattr(FrameInfo, "__slots__")
        assert "filename" in FrameInfo.__slots__
        assert "local_vars" in FrameInfo.__slots__


# ── DiagnosticFormatter init and properties ──────────────────────


class TestDiagnosticFormatterInit:
    """Tests for DiagnosticFormatter initialization."""

    def test_default_parameters(self):
        fmt = DiagnosticFormatter()
        assert fmt.max_depth == 5
        assert fmt.max_value_length == 200
        assert fmt.max_vars_per_frame == 20
        assert fmt.mask_sensitive is True
        assert fmt.auto_disable_production is True
        assert fmt.exclude_modules == []

    def test_custom_parameters(self):
        fmt = DiagnosticFormatter(
            max_depth=3,
            max_value_length=100,
            max_vars_per_frame=10,
            mask_sensitive=False,
            auto_disable_production=False,
            exclude_modules=["site-packages"],
        )
        assert fmt.max_depth == 3
        assert fmt.max_value_length == 100
        assert fmt.max_vars_per_frame == 10
        assert fmt.mask_sensitive is False
        assert fmt.auto_disable_production is False
        assert fmt.exclude_modules == ["site-packages"]


# ── enabled property ─────────────────────────────────────────────


class TestDiagnosticFormatterEnabled:
    """Tests for the enabled property and production auto-disable."""

    def test_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is True

    def test_disabled_in_production_mohflow_env(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "production"}, clear=True
        ):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is False

    def test_disabled_in_prod_mohflow_env(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "prod"}, clear=True
        ):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is False

    def test_disabled_in_production_environment_var(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is False

    def test_disabled_in_prod_environment_var(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "prod"}, clear=True):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is False

    def test_mohflow_env_takes_precedence(self):
        with patch.dict(
            os.environ,
            {"MOHFLOW_ENVIRONMENT": "staging", "ENVIRONMENT": "production"},
            clear=True,
        ):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is True

    def test_auto_disable_false_ignores_production(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "production"}, clear=True
        ):
            fmt = DiagnosticFormatter(auto_disable_production=False)
            assert fmt.enabled is True

    def test_case_insensitive_production_check(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "PRODUCTION"}, clear=True
        ):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is False

    def test_enabled_in_staging(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "staging"}, clear=True
        ):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is True

    def test_enabled_in_development(self):
        with patch.dict(
            os.environ, {"ENVIRONMENT": "development"}, clear=True
        ):
            fmt = DiagnosticFormatter()
            assert fmt.enabled is True


# ── format_exception basic tests ─────────────────────────────────


class TestFormatExceptionBasic:
    """Tests for basic exception formatting."""

    def _get_exc_info(self):
        """Helper to generate real exc_info."""
        try:
            raise ValueError("test error")
        except ValueError:
            return sys.exc_info()

    def test_returns_string(self):
        fmt = DiagnosticFormatter()
        exc_type, exc_value, exc_tb = self._get_exc_info()
        result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert isinstance(result, str)

    def test_contains_exception_type_and_message(self):
        fmt = DiagnosticFormatter()
        exc_type, exc_value, exc_tb = self._get_exc_info()
        result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "ValueError" in result
        assert "test error" in result

    def test_contains_traceback_header(self):
        fmt = DiagnosticFormatter()
        exc_type, exc_value, exc_tb = self._get_exc_info()
        result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "Traceback (with locals):" in result

    def test_contains_file_and_line_info(self):
        fmt = DiagnosticFormatter()
        exc_type, exc_value, exc_tb = self._get_exc_info()
        result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "File " in result
        assert "line " in result

    def test_no_exception_returns_empty_string(self):
        fmt = DiagnosticFormatter()
        result = fmt.format_exception(None, None, None)
        # When called outside exception context with None args
        # and sys.exc_info() returns (None, None, None), should return ""
        assert result == "" or "Traceback" in result

    def test_format_exception_with_no_args_outside_handler(self):
        """When called with no args and no active exception, returns ''."""
        fmt = DiagnosticFormatter()
        # Ensure we're not inside an exception handler
        result = fmt.format_exception()
        assert result == ""


# ── Local variable extraction ─────────────────────────────────────


class TestLocalVariableExtraction:
    """Tests for extracting local variables from frames."""

    def test_local_vars_captured(self):
        fmt = DiagnosticFormatter()
        local_x = 42
        local_s = "hello"
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "local_x" in result
        assert "42" in result
        assert "local_s" in result
        assert "hello" in result

    def test_local_vars_in_frame_info(self):
        fmt = DiagnosticFormatter()
        my_var = "test_value"
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        assert len(frames) > 0
        last_frame = frames[-1]
        assert "my_var" in last_frame.local_vars


# ── Sensitive variable masking ────────────────────────────────────


class TestSensitiveMasking:
    """Tests for sensitive variable name masking."""

    def test_password_masked(self):
        fmt = DiagnosticFormatter(mask_sensitive=True)
        password = "super_secret_123"  # noqa: S105
        try:
            raise RuntimeError("auth failed")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "super_secret_123" not in result
        assert "***" in result

    def test_api_key_masked(self):
        fmt = DiagnosticFormatter(mask_sensitive=True)
        api_key = "sk-1234567890"
        try:
            raise RuntimeError("bad key")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "sk-1234567890" not in result
        assert "***" in result

    def test_token_masked(self):
        fmt = DiagnosticFormatter(mask_sensitive=True)
        auth_token = "bearer-xyz-789"  # noqa: S105
        try:
            raise RuntimeError("expired")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "bearer-xyz-789" not in result

    def test_secret_masked(self):
        fmt = DiagnosticFormatter(mask_sensitive=True)
        db_secret = "my-db-secret-value"  # noqa: S105
        try:
            raise RuntimeError("connection failed")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "my-db-secret-value" not in result

    def test_masking_disabled(self):
        fmt = DiagnosticFormatter(mask_sensitive=False)
        password = "visible_password"  # noqa: S105
        try:
            raise RuntimeError("auth")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "visible_password" in result

    def test_non_sensitive_not_masked(self):
        fmt = DiagnosticFormatter(mask_sensitive=True)
        user_name = "alice"
        try:
            raise RuntimeError("error")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "alice" in result


# ── max_depth limiting ────────────────────────────────────────────


class TestMaxDepth:
    """Tests for max_depth frame limiting."""

    def _create_deep_exception(self, depth):
        """Create an exception with a traceback of a given depth."""

        def recurse(n):
            if n <= 0:
                raise RuntimeError(f"depth={depth}")
            return recurse(n - 1)

        try:
            recurse(depth)
        except RuntimeError:
            return sys.exc_info()

    def test_max_depth_limits_frames(self):
        fmt = DiagnosticFormatter(max_depth=2)
        exc_type, exc_value, exc_tb = self._create_deep_exception(10)
        frames = fmt.extract_frame_info(exc_tb)
        assert len(frames) <= 2

    def test_max_depth_keeps_innermost(self):
        """max_depth should keep the innermost (most recent) frames."""
        fmt = DiagnosticFormatter(max_depth=1)
        exc_type, exc_value, exc_tb = self._create_deep_exception(5)
        frames = fmt.extract_frame_info(exc_tb)
        assert len(frames) == 1
        # The innermost frame is the one where the exception was raised
        assert frames[0].function == "recurse"

    def test_max_depth_larger_than_actual(self):
        """When max_depth > actual frames, all frames are returned."""
        fmt = DiagnosticFormatter(max_depth=100)
        exc_type, exc_value, exc_tb = self._create_deep_exception(3)
        frames = fmt.extract_frame_info(exc_tb)
        # Should have all frames (at least the recurse calls + test frame)
        assert len(frames) >= 3


# ── max_value_length truncation ──────────────────────────────────


class TestMaxValueLength:
    """Tests for max_value_length truncation of variable reprs."""

    def test_long_value_truncated(self):
        fmt = DiagnosticFormatter(max_value_length=30)
        long_string = "a" * 100
        try:
            raise RuntimeError("check truncation")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        # The repr of long_string would be 'aaa...' truncated
        assert "..." in result

    def test_short_value_not_truncated(self):
        fmt = DiagnosticFormatter(max_value_length=200)
        short_val = "hi"
        try:
            raise RuntimeError("check")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "'hi'" in result


# ── max_vars_per_frame limiting ──────────────────────────────────


class TestMaxVarsPerFrame:
    """Tests for max_vars_per_frame limiting."""

    def test_limits_variable_count(self):
        fmt = DiagnosticFormatter(max_vars_per_frame=2)
        # Create many local variables
        var_a = 1
        var_b = 2
        var_c = 3
        var_d = 4
        var_e = 5
        try:
            raise RuntimeError("many vars")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        last_frame = frames[-1]
        # Should have at most 2 variables (+ self, fmt, etc. from SKIP_VARS filtering)
        assert len(last_frame.local_vars) <= 2

    def test_default_limit_is_20(self):
        fmt = DiagnosticFormatter()
        assert fmt.max_vars_per_frame == 20


# ── Production auto-disable in format_exception ─────────────────


class TestProductionAutoDisable:
    """Tests that production mode falls back to standard traceback."""

    def test_production_returns_standard_traceback(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "production"}, clear=True
        ):
            fmt = DiagnosticFormatter()
            try:
                raise ValueError("prod error")
            except ValueError:
                exc_type, exc_value, exc_tb = sys.exc_info()
                result = fmt.format_exception(exc_type, exc_value, exc_tb)
        # Standard traceback, not the enhanced one
        assert "Traceback (with locals):" not in result
        assert "Traceback (most recent call last):" in result
        assert "ValueError: prod error" in result

    def test_non_production_returns_enhanced_traceback(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "staging"}, clear=True
        ):
            fmt = DiagnosticFormatter()
            try:
                raise ValueError("staging error")
            except ValueError:
                exc_type, exc_value, exc_tb = sys.exc_info()
                result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "Traceback (with locals):" in result


# ── exclude_modules filtering ────────────────────────────────────


class TestExcludeModules:
    """Tests for exclude_modules frame filtering."""

    def test_excluded_module_has_no_locals(self):
        fmt = DiagnosticFormatter(exclude_modules=["test_diagnose"])
        try:
            raise RuntimeError("excluded")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        # Frames from this test file should have empty locals
        for frame in frames:
            if "test_diagnose" in frame.filename:
                assert frame.local_vars == {}

    def test_non_excluded_module_has_locals(self):
        fmt = DiagnosticFormatter(exclude_modules=["some_other_module"])
        local_var = "present"
        try:
            raise RuntimeError("not excluded")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        last_frame = frames[-1]
        assert len(last_frame.local_vars) > 0

    def test_multiple_excluded_modules(self):
        fmt = DiagnosticFormatter(
            exclude_modules=["test_diagnose", "another_module"]
        )
        try:
            raise RuntimeError("multi exclude")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        for frame in frames:
            if "test_diagnose" in frame.filename:
                assert frame.local_vars == {}


# ── _SKIP_VARS filtering ─────────────────────────────────────────


class TestSkipVars:
    """Tests for _SKIP_VARS filtering of built-in variables."""

    def test_skip_vars_contents(self):
        assert "__builtins__" in _SKIP_VARS
        assert "__name__" in _SKIP_VARS
        assert "__doc__" in _SKIP_VARS
        assert "__package__" in _SKIP_VARS
        assert "__loader__" in _SKIP_VARS
        assert "__spec__" in _SKIP_VARS
        assert "__file__" in _SKIP_VARS
        assert "__cached__" in _SKIP_VARS

    def test_skip_vars_is_frozenset(self):
        assert isinstance(_SKIP_VARS, frozenset)

    def test_builtins_not_in_output(self):
        fmt = DiagnosticFormatter()
        try:
            raise RuntimeError("skip test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        for frame in frames:
            for skip_var in _SKIP_VARS:
                assert skip_var not in frame.local_vars


# ── extract_frame_info method ────────────────────────────────────


class TestExtractFrameInfo:
    """Tests for the extract_frame_info public method."""

    def test_returns_list_of_frame_info(self):
        fmt = DiagnosticFormatter()
        try:
            raise RuntimeError("test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        assert isinstance(frames, list)
        assert all(isinstance(f, FrameInfo) for f in frames)

    def test_returns_empty_list_for_none(self):
        fmt = DiagnosticFormatter()
        frames = fmt.extract_frame_info(None)
        assert frames == []

    def test_frame_has_filename(self):
        fmt = DiagnosticFormatter()
        try:
            raise RuntimeError("test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        assert all(f.filename for f in frames)

    def test_frame_has_function_name(self):
        fmt = DiagnosticFormatter()
        try:
            raise RuntimeError("test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        last = frames[-1]
        assert last.function == "test_frame_has_function_name"

    def test_frame_has_lineno(self):
        fmt = DiagnosticFormatter()
        try:
            raise RuntimeError("test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        assert all(f.lineno > 0 for f in frames)


# ── Nested exception handling ─────────────────────────────────────


class TestNestedExceptions:
    """Tests for handling of chained/nested exceptions."""

    def test_chained_exception_formatted(self):
        fmt = DiagnosticFormatter()
        try:
            try:
                raise ValueError("original")
            except ValueError:
                raise RuntimeError("wrapper") from ValueError("original")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "RuntimeError" in result
        assert "wrapper" in result

    def test_implicit_chained_exception(self):
        fmt = DiagnosticFormatter()
        try:
            try:
                raise ValueError("first")
            except ValueError:
                raise RuntimeError("second")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            result = fmt.format_exception(exc_type, exc_value, exc_tb)
        assert "RuntimeError" in result
        assert "second" in result


# ── _extract_locals method ────────────────────────────────────────


class TestExtractLocals:
    """Tests for the _extract_locals internal method."""

    def test_extracts_frame_locals(self):
        fmt = DiagnosticFormatter()
        # We need a real frame, so use an exception
        my_local = "test_val"
        try:
            raise RuntimeError("test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frame = exc_tb.tb_frame
            local_vars = fmt._extract_locals(frame)
        assert "my_local" in local_vars
        assert "'test_val'" in local_vars["my_local"]

    def test_sensitive_vars_masked_in_extract_locals(self):
        fmt = DiagnosticFormatter(mask_sensitive=True)
        secret_key = "should_be_hidden"  # noqa: S105
        try:
            raise RuntimeError("test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frame = exc_tb.tb_frame
            local_vars = fmt._extract_locals(frame)
        assert local_vars.get("secret_key") == '"***"'

    def test_skip_vars_excluded_from_extract_locals(self):
        fmt = DiagnosticFormatter()
        try:
            raise RuntimeError("test")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frame = exc_tb.tb_frame
            local_vars = fmt._extract_locals(frame)
        for var in _SKIP_VARS:
            assert var not in local_vars


# ── _get_source_line method ──────────────────────────────────────


class TestGetSourceLine:
    """Tests for the _get_source_line internal method."""

    def test_returns_source_line(self):
        fmt = DiagnosticFormatter()
        # This file is readable, so it should return a line
        line = fmt._get_source_line(__file__, 1)
        assert line is not None

    def test_returns_none_for_invalid_file(self):
        fmt = DiagnosticFormatter()
        line = fmt._get_source_line("/nonexistent/file.py", 1)
        assert line is None or line == ""

    def test_line_is_stripped_right(self):
        fmt = DiagnosticFormatter()
        line = fmt._get_source_line(__file__, 1)
        if line:
            assert not line.endswith("\n")


# ── _SENSITIVE_PATTERNS regex tests ──────────────────────────────


class TestSensitivePatterns:
    """Tests for the _SENSITIVE_PATTERNS compiled regex."""

    def test_pattern_is_compiled(self):
        import re

        assert isinstance(_SENSITIVE_PATTERNS, type(re.compile("")))

    def test_pattern_matches_password(self):
        assert _SENSITIVE_PATTERNS.search("password")

    def test_pattern_matches_secret(self):
        assert _SENSITIVE_PATTERNS.search("client_secret")

    def test_pattern_matches_api_key(self):
        assert _SENSITIVE_PATTERNS.search("api_key")

    def test_pattern_matches_apikey(self):
        assert _SENSITIVE_PATTERNS.search("apikey")

    def test_pattern_matches_access_key(self):
        assert _SENSITIVE_PATTERNS.search("access_key")

    def test_pattern_case_insensitive(self):
        assert _SENSITIVE_PATTERNS.search("PASSWORD")
        assert _SENSITIVE_PATTERNS.search("Secret")
        assert _SENSITIVE_PATTERNS.search("API_KEY")


# ── Integration-style tests ──────────────────────────────────────


class TestDiagnosticFormatterIntegration:
    """Integration-style tests combining multiple features."""

    def test_full_flow_with_all_options(self):
        with patch.dict(
            os.environ, {"MOHFLOW_ENVIRONMENT": "development"}, clear=True
        ):
            fmt = DiagnosticFormatter(
                max_depth=3,
                max_value_length=50,
                max_vars_per_frame=5,
                mask_sensitive=True,
                exclude_modules=["some_lib"],
            )
            user_id = "u123"
            api_key = "secret-key-value"
            try:
                raise ValueError("integration test")
            except ValueError:
                exc_type, exc_value, exc_tb = sys.exc_info()
                result = fmt.format_exception(exc_type, exc_value, exc_tb)

        assert "ValueError: integration test" in result
        assert "u123" in result
        assert "secret-key-value" not in result  # masked
        assert "***" in result

    def test_format_exception_and_extract_frame_info_consistent(self):
        """format_exception and extract_frame_info should process the same frames."""
        fmt = DiagnosticFormatter(max_depth=2)
        try:
            raise RuntimeError("consistent")
        except RuntimeError:
            _, _, exc_tb = sys.exc_info()
            frames = fmt.extract_frame_info(exc_tb)
        assert len(frames) <= 2
        for frame in frames:
            d = frame.to_dict()
            assert "filename" in d
            assert "lineno" in d
            assert "function" in d
