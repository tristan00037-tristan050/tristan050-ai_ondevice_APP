from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

SCHEMA_VERSION_CHAT_REQUEST = "chat_request.v1"
SCHEMA_VERSION_ROUTER_DECISION = "router_decision.v1"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def load_connect_loop_schema(name: str) -> dict[str, Any]:
    path = repo_root() / "schemas" / "connect_loop" / name
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def _validator(name: str) -> Draft7Validator:
    schema = load_connect_loop_schema(name)
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


def validate_chat_request(payload: dict[str, Any]) -> None:
    _validator("chat_request.schema.json").validate(payload)


def validate_router_decision(payload: dict[str, Any]) -> None:
    _validator("router_decision.schema.json").validate(payload)


def router_decision_schema() -> dict[str, Any]:
    return load_connect_loop_schema("router_decision.schema.json")
