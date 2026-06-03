from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import sha256_text, stable_json_digest, now_utc

FORBIDDEN_AUDIT_SUBSTRINGS = [
    "sk-" + "proj-",
    "BEGIN " + "PRIVATE KEY",
    "Authori" + "zation:",
    "Bear" + "er ",
    "/" + "Users/",
    "/" + "home/",
    "/" + "Volumes/",
    "@",
]


@dataclass
class DigestAuditStore:
    records: list[dict[str, Any]]

    def __init__(self) -> None:
        self.records = []

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        assert_audit_record_digest_only(record)
        self.records.append(record)
        return record

    def clear(self) -> None:
        self.records.clear()


def build_admin_audit_record(
    *,
    action: str,
    admin_id_digest: str,
    object_digest: str,
    reason_code: str,
    extra_digest: str | None = None,
) -> dict[str, Any]:
    record = {
        "schema_version": "admin_policy_format_audit.v1",
        "audit_id": stable_json_digest({"action": action, "object_digest": object_digest, "at": now_utc()}),
        "created_at": now_utc(),
        "action": action,
        "admin_id_digest": admin_id_digest,
        "object_digest": object_digest,
        "extra_digest": extra_digest,
        "reason_code": reason_code,
        "raw_saved_zero": True,
        "raw_text_logged": False,
    }
    assert_audit_record_digest_only(record)
    return record


def assert_audit_record_digest_only(record: dict[str, Any]) -> None:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True)
    lowered = encoded.lower()
    forbidden_keys = ["raw_policy", "raw_template", "template_text", "token", "password", "secret", "email"]
    for key in forbidden_keys:
        if key in lowered:
            raise AssertionError(f"AUDIT_RAW_FIELD_FORBIDDEN:{key}")
    for needle in FORBIDDEN_AUDIT_SUBSTRINGS:
        if needle.lower() in lowered:
            raise AssertionError(f"AUDIT_FORBIDDEN_VALUE:{needle}")
    if record.get("raw_saved_zero") is not True:
        raise AssertionError("AUDIT_RAW_SAVED_ZERO_REQUIRED")
    if record.get("raw_text_logged") is not False:
        raise AssertionError("AUDIT_RAW_TEXT_LOGGED_FALSE_REQUIRED")


GLOBAL_ADMIN_AUDIT_STORE = DigestAuditStore()
