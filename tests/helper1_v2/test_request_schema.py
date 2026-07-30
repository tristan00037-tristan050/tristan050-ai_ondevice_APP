from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def _validator() -> Draft202012Validator:
    value = json.loads(
        (
            ROOT / "contracts" / "helper1" / "ask-request-v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(value)
    return Draft202012Validator(value)


def _request() -> dict[str, object]:
    return {
        "schema_version": "butler.helper1.ask-request.v2",
        "request_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "query": "회사 규정",
        "top_k": 5,
        "requested_generation_id": None,
        "effect_intent": "display_only",
    }


def test_request_schema_accepts_exact_envelope():
    _validator().validate(_request())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("top_k", True),
        ("query", ""),
        ("request_id", "not-a-uuid"),
        ("effect_intent", "network"),
    ],
)
def test_request_schema_rejects_invalid_values(field, value):
    request = _request()
    request[field] = value
    assert list(_validator().iter_errors(request))


def test_request_schema_rejects_unknown_field():
    request = _request()
    request["path"] = "/private/user/document"
    assert list(_validator().iter_errors(request))
