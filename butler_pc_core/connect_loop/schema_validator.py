"""Schema loading and validation for Connect Loop router contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas" / "connect_loop"


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / schema_name
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def validator_for(schema_name: str) -> Draft7Validator:
    return Draft7Validator(load_schema(schema_name))


def validate_chat_request(chat_request: dict[str, Any]) -> dict[str, Any]:
    validator_for("chat_request.schema.json").validate(chat_request)
    return chat_request


def validate_router_decision(router_decision: dict[str, Any]) -> dict[str, Any]:
    validator_for("router_decision.schema.json").validate(router_decision)
    return router_decision
