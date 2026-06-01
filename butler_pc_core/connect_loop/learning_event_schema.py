"""Schema helpers for PR-E learning candidate gate.

The PR-E implementation consumes the merged PR-A schemas as the single source
of truth. It does not copy or modify schema contracts.
"""
from __future__ import annotations

from typing import Any

from jsonschema.exceptions import ValidationError

from .schema_validator import validator_for


class SchemaValidationUnavailable(RuntimeError):
    pass


def _validator(schema_name: str):
    try:
        return validator_for(schema_name)
    except Exception as exc:  # pragma: no cover - defensive fail-closed guard
        raise SchemaValidationUnavailable(f"SCHEMA_VALIDATOR_UNAVAILABLE:{schema_name}") from exc


def validate_learning_event(event: dict[str, Any]) -> dict[str, Any]:
    try:
        _validator("learning_event_v1.schema.json").validate(event)
    except ValidationError:
        raise
    return event


def validate_usage_log(usage_log: dict[str, Any]) -> dict[str, Any]:
    try:
        _validator("usage_log_v1_1.schema.json").validate(usage_log)
    except ValidationError:
        raise
    return usage_log
