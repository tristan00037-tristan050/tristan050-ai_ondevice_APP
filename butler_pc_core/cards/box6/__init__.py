"""Box6 form-fill service package."""

from .form_fill_service import (
    BOX6_JSON_SCHEMA,
    SCHEMA_VERSION,
    FormFillInput,
    FormFillResult,
    fill_form,
)

__all__ = [
    "BOX6_JSON_SCHEMA",
    "SCHEMA_VERSION",
    "FormFillInput",
    "FormFillResult",
    "fill_form",
]
