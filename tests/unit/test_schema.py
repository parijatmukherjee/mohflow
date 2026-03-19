"""Comprehensive tests for mohflow.schema module.

Covers LogSchema, SchemaValidator, SchemaValidationError, field() helper,
type checking, type coercion, strict vs non-strict modes, inheritance,
JSON Schema export, and error accumulation.
"""

import warnings
from copy import deepcopy

import pytest

from mohflow.schema import (
    LogSchema,
    SchemaValidationError,
    SchemaValidator,
    _FieldSpec,
    _SchemaMetaclass,
    field,
)

# ── Schema definitions used across tests ──────────────────────────


class OrderLog(LogSchema):
    order_id: str
    amount: float
    currency: str = "USD"


class UserLog(LogSchema):
    user_id: str
    email: str
    active: bool = field(
        required=False, default=True, description="Is the user active?"
    )


class StrictLog(LogSchema):
    request_id: str
    status_code: int


class MinimalLog(LogSchema):
    message: str


# ── SchemaValidationError tests ───────────────────────────────────


class TestSchemaValidationError:
    """Tests for the SchemaValidationError exception."""

    def test_error_message(self):
        err = SchemaValidationError("something failed")
        assert str(err) == "something failed"

    def test_errors_attribute_default_empty(self):
        err = SchemaValidationError("fail")
        assert err.errors == []

    def test_errors_attribute_with_list(self):
        errors = [
            {
                "field": "x",
                "error": "missing_required_field",
                "message": "x missing",
            },
        ]
        err = SchemaValidationError("fail", errors=errors)
        assert err.errors == errors
        assert len(err.errors) == 1

    def test_inherits_from_exception(self):
        assert issubclass(SchemaValidationError, Exception)

    def test_errors_none_becomes_empty_list(self):
        err = SchemaValidationError("fail", errors=None)
        assert err.errors == []


# ── field() helper tests ──────────────────────────────────────────


class TestFieldHelper:
    """Tests for the field() helper function."""

    def test_field_returns_dict_with_marker(self):
        result = field()
        assert result["__mohflow_field__"] is True

    def test_field_required_default(self):
        result = field()
        assert result["required"] is True

    def test_field_with_default_sets_required_false(self):
        result = field(default="hello")
        assert result["required"] is False

    def test_field_explicit_required_false(self):
        result = field(required=False)
        assert result["required"] is False

    def test_field_with_description(self):
        result = field(description="A helpful field")
        assert result["description"] == "A helpful field"

    def test_field_default_value(self):
        result = field(default=42)
        assert result["default"] == 42

    def test_field_none_default_keeps_required(self):
        """When default is None, required is not changed to False."""
        result = field(required=True, default=None)
        assert result["required"] is True

    def test_field_default_not_none_overrides_required(self):
        """Non-None default forces required=False even if required=True passed."""
        result = field(required=True, default="val")
        assert result["required"] is False


# ── _FieldSpec tests ──────────────────────────────────────────────


class TestFieldSpec:
    """Tests for the internal _FieldSpec descriptor."""

    def test_creation(self):
        spec = _FieldSpec(name="foo", field_type=int, required=True)
        assert spec.name == "foo"
        assert spec.field_type is int
        assert spec.required is True
        assert spec.default is None
        assert spec.description == ""

    def test_creation_with_all_params(self):
        spec = _FieldSpec(
            name="bar",
            field_type=str,
            required=False,
            default="baz",
            description="A bar field",
        )
        assert spec.name == "bar"
        assert spec.default == "baz"
        assert spec.description == "A bar field"


# ── LogSchema subclassing ────────────────────────────────────────


class TestLogSchemaSubclassing:
    """Tests for LogSchema subclass definition and field collection."""

    def test_field_specs_collected(self):
        assert "order_id" in OrderLog._field_specs
        assert "amount" in OrderLog._field_specs
        assert "currency" in OrderLog._field_specs

    def test_required_field_detected(self):
        spec = OrderLog._field_specs["order_id"]
        assert spec.required is True

    def test_default_value_field_not_required(self):
        spec = OrderLog._field_specs["currency"]
        assert spec.required is False
        assert spec.default == "USD"

    def test_field_type_detected(self):
        assert OrderLog._field_specs["order_id"].field_type is str
        assert OrderLog._field_specs["amount"].field_type is float

    def test_field_helper_in_schema(self):
        spec = UserLog._field_specs["active"]
        assert spec.required is False
        assert spec.default is True
        assert spec.description == "Is the user active?"

    def test_private_fields_ignored(self):
        class InternalLog(LogSchema):
            _internal: str
            public_field: str

        assert "_internal" not in InternalLog._field_specs
        assert "public_field" in InternalLog._field_specs


# ── SchemaValidator properties ────────────────────────────────────


class TestSchemaValidatorProperties:
    """Tests for SchemaValidator property accessors."""

    def test_schema_name(self):
        v = OrderLog.as_validator()
        assert v.schema_name == "OrderLog"

    def test_strict_default_true(self):
        v = OrderLog.as_validator()
        assert v.strict is True

    def test_strict_false(self):
        v = OrderLog.as_validator(strict=False)
        assert v.strict is False

    def test_required_fields(self):
        v = OrderLog.as_validator()
        assert v.required_fields == {"order_id", "amount"}

    def test_all_fields(self):
        v = OrderLog.as_validator()
        assert v.all_fields == {"order_id", "amount", "currency"}

    def test_repr(self):
        v = OrderLog.as_validator()
        r = repr(v)
        assert "SchemaValidator" in r
        assert "OrderLog" in r
        assert "strict=True" in r

    def test_repr_non_strict(self):
        v = OrderLog.as_validator(strict=False)
        r = repr(v)
        assert "strict=False" in r


# ── Required fields validation ────────────────────────────────────


class TestRequiredFieldsValidation:
    """Tests for required field validation."""

    def test_missing_required_field_raises(self):
        v = OrderLog.as_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            v.validate_event({"amount": 9.99})
        assert "order_id" in str(exc_info.value)

    def test_all_required_fields_present_passes(self):
        v = OrderLog.as_validator()
        result = v.validate_event({"order_id": "O1", "amount": 9.99})
        assert result["order_id"] == "O1"

    def test_missing_multiple_required_fields(self):
        v = OrderLog.as_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            v.validate_event({})
        err = exc_info.value
        assert len(err.errors) == 2  # order_id and amount
        field_names = {e["field"] for e in err.errors}
        assert field_names == {"order_id", "amount"}


# ── Optional fields with defaults ────────────────────────────────


class TestOptionalFieldsDefaults:
    """Tests for optional fields and default injection."""

    def test_default_injected_when_absent(self):
        v = OrderLog.as_validator()
        result = v.validate_event({"order_id": "O1", "amount": 5.0})
        assert result["currency"] == "USD"

    def test_default_overridden_when_provided(self):
        v = OrderLog.as_validator()
        result = v.validate_event(
            {"order_id": "O1", "amount": 5.0, "currency": "EUR"}
        )
        assert result["currency"] == "EUR"

    def test_field_helper_default_injected(self):
        v = UserLog.as_validator()
        result = v.validate_event({"user_id": "u1", "email": "a@b.com"})
        assert result["active"] is True

    def test_default_is_deepcopied(self):
        """Mutable defaults should be deep-copied to avoid shared state."""

        class ListLog(LogSchema):
            tags: list = field(default=["default"], required=False)

        v = ListLog.as_validator()
        r1 = v.validate_event({})
        r2 = v.validate_event({})
        r1["tags"].append("extra")
        assert r2["tags"] == ["default"]  # Not mutated


# ── Type checking ─────────────────────────────────────────────────


class TestTypeChecking:
    """Tests for type validation."""

    def test_wrong_type_raises_in_strict_mode(self):
        v = OrderLog.as_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            v.validate_event({"order_id": "O1", "amount": "not_a_float"})
        assert "type_error" in exc_info.value.errors[0]["error"]

    def test_correct_types_pass(self):
        v = OrderLog.as_validator()
        result = v.validate_event({"order_id": "O1", "amount": 9.99})
        assert result["amount"] == 9.99

    def test_int_type_check(self):
        v = StrictLog.as_validator()
        with pytest.raises(SchemaValidationError):
            v.validate_event({"request_id": "r1", "status_code": "200"})

    def test_bool_type_check(self):
        v = UserLog.as_validator()
        with pytest.raises(SchemaValidationError):
            v.validate_event(
                {"user_id": "u1", "email": "a@b.com", "active": "yes"}
            )


# ── Type coercion mode ───────────────────────────────────────────


class TestTypeCoercion:
    """Tests for coerce_types=True mode."""

    def test_string_to_float_coercion(self):
        v = OrderLog.as_validator(coerce_types=True)
        result = v.validate_event({"order_id": "O1", "amount": "9.99"})
        assert result["amount"] == 9.99
        assert isinstance(result["amount"], float)

    def test_string_to_int_coercion(self):
        v = StrictLog.as_validator(coerce_types=True)
        result = v.validate_event({"request_id": "r1", "status_code": "200"})
        assert result["status_code"] == 200
        assert isinstance(result["status_code"], int)

    def test_coercion_failure_raises(self):
        v = StrictLog.as_validator(coerce_types=True)
        with pytest.raises(SchemaValidationError) as exc_info:
            v.validate_event(
                {"request_id": "r1", "status_code": "not_a_number"}
            )
        err = exc_info.value.errors[0]
        assert "coercion failed" in err["message"]

    def test_coercion_disabled_by_default(self):
        v = StrictLog.as_validator()
        with pytest.raises(SchemaValidationError):
            v.validate_event({"request_id": "r1", "status_code": "200"})


# ── Strict vs non-strict mode ────────────────────────────────────


class TestStrictVsNonStrict:
    """Tests for strict=True (raise) vs strict=False (warning)."""

    def test_strict_raises_on_error(self):
        v = OrderLog.as_validator(strict=True)
        with pytest.raises(SchemaValidationError):
            v.validate_event({"amount": 9.99})

    def test_non_strict_warns_on_error(self):
        v = OrderLog.as_validator(strict=False)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = v.validate_event({"amount": 9.99})
            assert len(w) == 1
            assert "order_id" in str(w[0].message)

    def test_non_strict_returns_event_despite_error(self):
        v = OrderLog.as_validator(strict=False)
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = v.validate_event({"amount": 9.99})
        assert result["amount"] == 9.99

    def test_non_strict_type_error_warns(self):
        v = StrictLog.as_validator(strict=False)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            v.validate_event({"request_id": "r1", "status_code": "bad"})
            assert len(w) == 1
            assert "type_error" in str(w[0].message) or "expected" in str(
                w[0].message
            )


# ── json_schema() export ─────────────────────────────────────────


class TestJsonSchemaExport:
    """Tests for the json_schema() class method."""

    def test_returns_dict(self):
        schema = OrderLog.json_schema()
        assert isinstance(schema, dict)

    def test_has_json_schema_key(self):
        schema = OrderLog.json_schema()
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"

    def test_title_is_class_name(self):
        schema = OrderLog.json_schema()
        assert schema["title"] == "OrderLog"

    def test_type_is_object(self):
        schema = OrderLog.json_schema()
        assert schema["type"] == "object"

    def test_properties_contains_all_fields(self):
        schema = OrderLog.json_schema()
        assert "order_id" in schema["properties"]
        assert "amount" in schema["properties"]
        assert "currency" in schema["properties"]

    def test_required_fields_listed(self):
        schema = OrderLog.json_schema()
        assert "order_id" in schema["required"]
        assert "amount" in schema["required"]
        assert "currency" not in schema["required"]

    def test_type_mapping_string(self):
        schema = OrderLog.json_schema()
        assert schema["properties"]["order_id"]["type"] == "string"

    def test_type_mapping_float_to_number(self):
        schema = OrderLog.json_schema()
        assert schema["properties"]["amount"]["type"] == "number"

    def test_type_mapping_bool(self):
        schema = UserLog.json_schema()
        assert schema["properties"]["active"]["type"] == "boolean"

    def test_type_mapping_int(self):
        schema = StrictLog.json_schema()
        assert schema["properties"]["status_code"]["type"] == "integer"

    def test_description_included(self):
        schema = UserLog.json_schema()
        assert (
            schema["properties"]["active"]["description"]
            == "Is the user active?"
        )

    def test_default_included(self):
        schema = OrderLog.json_schema()
        assert schema["properties"]["currency"]["default"] == "USD"

    def test_additional_properties_true(self):
        schema = OrderLog.json_schema()
        assert schema["additionalProperties"] is True

    def test_list_and_dict_types(self):
        class ComplexLog(LogSchema):
            tags: list = field(default=[], required=False)
            metadata: dict = field(default={}, required=False)

        schema = ComplexLog.json_schema()
        assert schema["properties"]["tags"]["type"] == "array"
        assert schema["properties"]["metadata"]["type"] == "object"


# ── Schema inheritance ────────────────────────────────────────────


class TestSchemaInheritance:
    """Tests for schemas inheriting from other schemas."""

    def test_child_inherits_parent_fields(self):
        class BaseLog(LogSchema):
            request_id: str
            timestamp: str

        class ExtendedLog(BaseLog):
            user_id: str
            action: str

        assert "request_id" in ExtendedLog._field_specs
        assert "timestamp" in ExtendedLog._field_specs
        assert "user_id" in ExtendedLog._field_specs
        assert "action" in ExtendedLog._field_specs

    def test_child_can_override_parent_field(self):
        class BaseLog(LogSchema):
            level: str

        class ChildLog(BaseLog):
            level: str = "INFO"

        spec = ChildLog._field_specs["level"]
        assert spec.required is False
        assert spec.default == "INFO"

    def test_inherited_validator_works(self):
        class BaseLog(LogSchema):
            request_id: str

        class ChildLog(BaseLog):
            user_id: str

        v = ChildLog.as_validator()
        result = v.validate_event({"request_id": "r1", "user_id": "u1"})
        assert result["request_id"] == "r1"
        assert result["user_id"] == "u1"

    def test_inherited_missing_parent_field_raises(self):
        class BaseLog(LogSchema):
            request_id: str

        class ChildLog(BaseLog):
            user_id: str

        v = ChildLog.as_validator()
        with pytest.raises(SchemaValidationError):
            v.validate_event({"user_id": "u1"})  # missing request_id


# ── Extra fields pass through ─────────────────────────────────────


class TestExtraFieldsPassThrough:
    """Tests that extra fields not defined in schema pass through."""

    def test_extra_fields_in_result(self):
        v = MinimalLog.as_validator()
        result = v.validate_event(
            {"message": "hi", "extra_field": "extra_value"}
        )
        assert result["extra_field"] == "extra_value"

    def test_extra_fields_do_not_cause_error(self):
        v = MinimalLog.as_validator()
        # Should not raise
        result = v.validate_event({"message": "hi", "foo": 1, "bar": "baz"})
        assert result["foo"] == 1
        assert result["bar"] == "baz"


# ── Multiple errors accumulated ──────────────────────────────────


class TestMultipleErrors:
    """Tests that multiple errors are accumulated in a single raise."""

    def test_multiple_missing_fields(self):
        v = OrderLog.as_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            v.validate_event({})
        assert len(exc_info.value.errors) >= 2

    def test_missing_and_type_error_combined(self):
        v = StrictLog.as_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            # missing request_id AND wrong type for status_code
            v.validate_event({"status_code": "not_int"})
        errors = exc_info.value.errors
        error_types = {e["error"] for e in errors}
        assert "missing_required_field" in error_types
        assert "type_error" in error_types

    def test_error_message_contains_all_issues(self):
        v = OrderLog.as_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            v.validate_event({})
        msg = str(exc_info.value)
        assert "order_id" in msg
        assert "amount" in msg


# ── validate_event returns copy ───────────────────────────────────


class TestValidateEventCopy:
    """Tests that validate_event returns a copy, not the original dict."""

    def test_returns_shallow_copy(self):
        v = MinimalLog.as_validator()
        original = {"message": "test"}
        result = v.validate_event(original)
        result["message"] = "modified"
        assert original["message"] == "test"

    def test_defaults_do_not_mutate_original(self):
        v = OrderLog.as_validator()
        original = {"order_id": "O1", "amount": 5.0}
        result = v.validate_event(original)
        assert "currency" in result
        assert "currency" not in original


# ── as_validator factory ──────────────────────────────────────────


class TestAsValidator:
    """Tests for the as_validator() class method."""

    def test_returns_schema_validator(self):
        v = OrderLog.as_validator()
        assert isinstance(v, SchemaValidator)

    def test_strict_param_passed(self):
        v = OrderLog.as_validator(strict=False)
        assert v.strict is False

    def test_coerce_types_param_passed(self):
        v = OrderLog.as_validator(coerce_types=True)
        assert v._coerce_types is True

    def test_default_coerce_types_false(self):
        v = OrderLog.as_validator()
        assert v._coerce_types is False
