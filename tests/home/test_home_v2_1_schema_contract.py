from __future__ import annotations

import json
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from butler_pc_core.home.store import HomeStore


SCHEMAS = Path(__file__).resolve().parents[2] / "contracts" / "home_v2_1"
UTC = "2026-07-20T00:00:00Z"


def validator(name: str) -> Draft202012Validator:
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in SCHEMAS.glob("*.schema.json")]
    registry = Registry().with_resources(
        (document["$id"], Resource.from_contents(document)) for document in documents
    )
    selected = next(document for document in documents if document["$id"].endswith(f"/{name}"))
    Draft202012Validator.check_schema(selected)
    return Draft202012Validator(selected, registry=registry, format_checker=FormatChecker())


def assert_valid(name: str, instance: object) -> None:
    errors = sorted(validator(name).iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, [error.message for error in errors]


def test_runtime_and_startup_match_owned_v2_1_schemas(tmp_path: Path) -> None:
    with HomeStore(tmp_path / "home.sqlite3") as store:
        assert_valid("startup_status.schema.json", store.startup_status())
        assert_valid("runtime_status.schema.json", store.runtime_status())


def test_durable_turn_receipts_match_owned_v2_1_schemas(tmp_path: Path) -> None:
    conversation_id = str(uuid.uuid4())
    with HomeStore(tmp_path / "home.sqlite3") as store:
        accepted = store.accept_user_turn(
            {
                "id": conversation_id,
                "folder_id": None,
                "title": "제품 요청",
                "title_is_custom": False,
                "created_at": UTC,
                "updated_at": UTC,
            },
            {"id": "user-1", "role": "user", "content": "분석해 주세요", "timestamp": UTC},
            business_profile_id=None,
            expected_version=None,
            request_id=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            actor="local-user",
        )
        assert_valid("turn_acceptance_receipt.schema.json", accepted)
        completed = store.append_assistant_turn(
            conversation_id,
            {"id": "assistant-1", "role": "butler", "content": "완료했습니다", "timestamp": UTC},
            accepted["conversation_version"],
            turn_id=accepted["turn_id"],
            model_request_id=accepted["model_request_id"],
            request_id=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            actor="local-user",
        )
        assert_valid("terminal_receipt.schema.json", completed)


def test_all_owned_schemas_are_draft_2020_12_valid() -> None:
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))
