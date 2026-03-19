"""
Log schema enforcement for MohFlow.

Provides Pydantic-based validation of structured log fields, ensuring
downstream consumers (Loki, Elasticsearch, BigQuery) always receive
consistent, well-typed log records.

Usage::

    from mohflow.schema import LogSchema, SchemaValidationError

    class OrderLog(LogSchema):
        order_id: str
        amount: float
        currency: str = "USD"

    schema = OrderLog.as_validator()
    validated = schema.validate_event({"order_id": "O1", "amount": 9.99})
    # → {"order_id": "O1", "amount": 9.99, "currency": "USD"}

    schema.validate_event({"amount": 9.99})
    # raises SchemaValidationError (missing order_id)
"""

from __future__ import annotations

import warnings
from copy import deepcopy
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Type,
)


class SchemaValidationError(Exception):
    """Raised when a log event fails schema validation."""

    def __init__(
        self,
        message: str,
        errors: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(message)
        self.errors = errors or []


class _FieldSpec:
    """Internal descriptor for a schema field."""

    __slots__ = (
        "name",
        "field_type",
        "required",
        "default",
        "description",
    )

    def __init__(
        self,
        name: str,
        field_type: type = str,
        required: bool = True,
        default: Any = None,
        description: str = "",
    ):
        self.name = name
        self.field_type = field_type
        self.required = required
        self.default = default
        self.description = description


def field(
    required: bool = True,
    default: Any = None,
    description: str = "",
) -> Any:
    """Declare a field inside a :class:`LogSchema` subclass.

    Parameters
    ----------
    required : bool
        Whether the field must be present in every log event.
    default : Any
        Default value injected when the field is absent
        (implies ``required=False``).
    description : str
        Human-readable description (used in JSON Schema export).
    """
    if default is not None:
        required = False
    return {
        "__mohflow_field__": True,
        "required": required,
        "default": default,
        "description": description,
    }


class _SchemaMetaclass(type):
    """Metaclass that collects field annotations at class-creation time."""

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
    ):
        cls = super().__new__(mcs, name, bases, namespace)
        if name == "LogSchema":
            return cls

        field_specs: Dict[str, _FieldSpec] = {}
        annotations = {}

        # Walk the MRO to collect inherited fields
        for base in reversed(cls.__mro__):
            annotations.update(getattr(base, "__annotations__", {}))

        for fname, ftype in annotations.items():
            if fname.startswith("_"):
                continue
            raw = namespace.get(fname)
            if isinstance(raw, dict) and raw.get("__mohflow_field__"):
                spec = _FieldSpec(
                    name=fname,
                    field_type=ftype,
                    required=raw["required"],
                    default=raw["default"],
                    description=raw.get("description", ""),
                )
            elif raw is not None:
                # Class-level default value (e.g. currency: str = "USD")
                spec = _FieldSpec(
                    name=fname,
                    field_type=ftype,
                    required=False,
                    default=raw,
                )
            else:
                # Annotation-only → required field
                spec = _FieldSpec(
                    name=fname,
                    field_type=ftype,
                    required=True,
                )
            field_specs[fname] = spec

        cls._field_specs = field_specs  # type: ignore[attr-defined]
        return cls


class LogSchema(metaclass=_SchemaMetaclass):
    """Base class for log schema definitions.

    Subclass this and add typed annotations to define the expected
    shape of a log event:

    .. code-block:: python

        class PaymentLog(LogSchema):
            order_id: str
            amount: float
            currency: str = "USD"

    Then obtain a reusable validator:

    .. code-block:: python

        validator = PaymentLog.as_validator()
        event = validator.validate_event({...})
    """

    _field_specs: Dict[str, _FieldSpec] = {}

    @classmethod
    def as_validator(
        cls,
        strict: bool = True,
        coerce_types: bool = False,
    ) -> "SchemaValidator":
        """Create a :class:`SchemaValidator` from this schema.

        Parameters
        ----------
        strict : bool
            If ``True``, raise on validation failure.
            If ``False``, emit a warning and pass through.
        coerce_types : bool
            If ``True``, attempt to coerce values to the declared type.
        """
        return SchemaValidator(
            schema_cls=cls,
            strict=strict,
            coerce_types=coerce_types,
        )

    @classmethod
    def json_schema(cls) -> Dict[str, Any]:
        """Export the schema as a JSON Schema document."""
        _TYPE_MAP = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for spec in cls._field_specs.values():
            prop: Dict[str, Any] = {
                "type": _TYPE_MAP.get(spec.field_type, "string"),
            }
            if spec.description:
                prop["description"] = spec.description
            if spec.default is not None:
                prop["default"] = spec.default
            properties[spec.name] = prop
            if spec.required:
                required.append(spec.name)

        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": cls.__name__,
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": True,
        }


class SchemaValidator:
    """Validates and normalises log events against a :class:`LogSchema`.

    Parameters
    ----------
    schema_cls : Type[LogSchema]
        The schema class to validate against.
    strict : bool
        Raise :class:`SchemaValidationError` on failure (default).
        When ``False``, emit a warning and return the event as-is.
    coerce_types : bool
        Attempt to coerce values to declared types (e.g. ``"42"`` → 42).
    """

    def __init__(
        self,
        schema_cls: Type[LogSchema],
        strict: bool = True,
        coerce_types: bool = False,
    ):
        self._schema_cls = schema_cls
        self._specs: Dict[str, _FieldSpec] = schema_cls._field_specs
        self._strict = strict
        self._coerce_types = coerce_types

    @property
    def schema_name(self) -> str:
        return self._schema_cls.__name__

    @property
    def strict(self) -> bool:
        return self._strict

    @property
    def required_fields(self) -> Set[str]:
        return {s.name for s in self._specs.values() if s.required}

    @property
    def all_fields(self) -> Set[str]:
        return set(self._specs.keys())

    def validate_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Validate *event* against the schema.

        Returns a (possibly enriched) copy of the event dict with
        defaults applied.  Raises :class:`SchemaValidationError` in
        strict mode if validation fails.
        """
        errors: List[Dict[str, Any]] = []
        result = dict(event)  # shallow copy

        for spec in self._specs.values():
            if spec.name not in result:
                if spec.required:
                    errors.append(
                        {
                            "field": spec.name,
                            "error": "missing_required_field",
                            "message": (
                                f"Required field '{spec.name}' " f"is missing"
                            ),
                        }
                    )
                elif spec.default is not None:
                    result[spec.name] = deepcopy(spec.default)
            else:
                # Type check
                value = result[spec.name]
                if not isinstance(value, spec.field_type):
                    if self._coerce_types:
                        try:
                            result[spec.name] = spec.field_type(value)
                        except (ValueError, TypeError):
                            errors.append(
                                {
                                    "field": spec.name,
                                    "error": "type_error",
                                    "message": (
                                        f"Field '{spec.name}' "
                                        f"expected "
                                        f"{spec.field_type.__name__}, "
                                        f"got "
                                        f"{type(value).__name__} "
                                        f"(coercion failed)"
                                    ),
                                }
                            )
                    else:
                        errors.append(
                            {
                                "field": spec.name,
                                "error": "type_error",
                                "message": (
                                    f"Field '{spec.name}' "
                                    f"expected "
                                    f"{spec.field_type.__name__}, "
                                    f"got {type(value).__name__}"
                                ),
                            }
                        )

        if errors:
            msg = (
                f"Schema validation failed for "
                f"{self.schema_name}: "
                + "; ".join(e["message"] for e in errors)
            )
            if self._strict:
                raise SchemaValidationError(msg, errors=errors)
            else:
                warnings.warn(msg, stacklevel=2)

        return result

    def __repr__(self) -> str:
        return (
            f"SchemaValidator("
            f"{self.schema_name}, "
            f"strict={self._strict})"
        )
