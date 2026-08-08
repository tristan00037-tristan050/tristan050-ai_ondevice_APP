"""Small fail-closed JSON Schema evaluator used by the AC-25 receipt gate.

The committed schema document is the sole shape authority.  This evaluator
implements only the draft-2020-12 keywords used by that document and rejects
unknown schema keywords instead of silently ignoring them.
"""
from __future__ import annotations

import re
from typing import Any

from . import strict_receipt as sr


_SUPPORTED = frozenset({
    "$schema", "$id", "$defs", "$ref", "type", "properties", "required",
    "additionalProperties", "items", "minItems", "uniqueItems", "const",
    "enum", "pattern", "minLength", "minimum", "description", "title",
})


def _fail() -> None:
    raise sr.StrictReceiptError("RECEIPT_SCHEMA_INVALID")


def _resolve(root: dict, reference: str) -> dict:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        _fail()
    current: Any = root
    for token in reference[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            _fail()
        current = current[token]
    if not isinstance(current, dict):
        _fail()
    return current


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    _fail()
    return False


def _validate_schema_shape(schema: dict) -> None:
    if not isinstance(schema, dict) or set(schema) - _SUPPORTED:
        _fail()
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        _fail()
    for child in definitions.values():
        _validate_schema_shape(child)
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        _fail()
    for child in properties.values():
        _validate_schema_shape(child)
    if "items" in schema:
        _validate_schema_shape(schema["items"])


def _validate(instance: Any, schema: dict, root: dict) -> None:
    if "$ref" in schema:
        if len(schema) != 1:
            _fail()
        _validate(instance, _resolve(root, schema["$ref"]), root)
        return
    expected_type = schema.get("type")
    if expected_type is not None and not _type_matches(instance, expected_type):
        _fail()
    if "const" in schema and instance != schema["const"]:
        _fail()
    if "enum" in schema:
        choices = schema["enum"]
        if not isinstance(choices, list) or instance not in choices:
            _fail()
    if isinstance(instance, str):
        minimum = schema.get("minLength")
        if minimum is not None and (
            not isinstance(minimum, int) or isinstance(minimum, bool)
            or minimum < 0 or len(instance) < minimum
        ):
            _fail()
        pattern = schema.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                _fail()
            try:
                matched = re.search(pattern, instance)
            except re.error:
                _fail()
            if matched is None:
                _fail()
    if isinstance(instance, int) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and (
            not isinstance(minimum, int) or isinstance(minimum, bool)
            or instance < minimum
        ):
            _fail()
    if isinstance(instance, list):
        minimum = schema.get("minItems")
        if minimum is not None and (
            not isinstance(minimum, int) or isinstance(minimum, bool)
            or minimum < 0 or len(instance) < minimum
        ):
            _fail()
        if schema.get("uniqueItems") is True:
            encoded = [sr.canonical_json_bytes(item) for item in instance]
            if len(encoded) != len(set(encoded)):
                _fail()
        item_schema = schema.get("items")
        if item_schema is not None:
            for item in instance:
                _validate(item, item_schema, root)
    if isinstance(instance, dict):
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            _fail()
        if set(required) - set(instance):
            _fail()
        if schema.get("additionalProperties") is False and set(instance) - set(properties):
            _fail()
        for key, value in instance.items():
            if key in properties:
                _validate(value, properties[key], root)


def validate(instance: Any, schema: dict) -> None:
    """Apply the exact committed schema or raise one stable error code."""
    _validate_schema_shape(schema)
    _validate(instance, schema, schema)


__all__ = ["validate"]
