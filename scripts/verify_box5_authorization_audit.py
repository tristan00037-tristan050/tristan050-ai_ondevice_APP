#!/usr/bin/env python3
"""Independently replay Box5 authority audit rows from SQLite."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sqlite3
from pathlib import Path


ACTIONS = frozenset(
    {
        "ASSIGNMENT_CREATE",
        "RULE_FUTURE_CREATE",
        "RULE_DEACTIVATE",
        "RULE_APPLICATION_REVERT",
        "QUARANTINE_ROW_RECOMPILE",
        "CONFLICT_RESOLVE",
    }
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ATTACK_KEY = re.compile(
    r"^ATTACK_(?P<number>0[1-9]|1[0-5])_"
    r"(?P<field>NAME|FIRST|SECOND|ROWS|FAIL_CLOSED)$"
)
_ATTACK_NAME = re.compile(r"^[a-z0-9_]{1,80}$")


def _digest(value: dict[str, object]) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify_ac11_schema_matrix(path: Path, expected_sha256: str) -> dict[str, object]:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not path.is_file()
        or metadata.st_size < 1
        or metadata.st_size > 256_000
        or not _DIGEST.fullmatch(expected_sha256)
        or not hmac.compare_digest(_file_sha256(path), expected_sha256)
    ):
        raise ValueError("AC11_SCHEMA_MATRIX_INVALID")
    try:
        text = path.read_text(encoding="ascii", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ValueError("AC11_SCHEMA_MATRIX_INVALID") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.count("=") != 1:
            raise ValueError("AC11_SCHEMA_MATRIX_INVALID")
        key, value = line.split("=", 1)
        if key in values or not key or not value:
            raise ValueError("AC11_SCHEMA_MATRIX_INVALID")
        values[key] = value
    fixed = {
        "NORMAL_FIRST",
        "NORMAL_SECOND",
        "NORMAL_ROWS",
        "ATTACK_COUNT",
        "ATTACK_PASS_COUNT",
        "AC11_SCHEMA_CONSTRAINT_MATRIX_PASS",
    }
    if any(key not in fixed and _ATTACK_KEY.fullmatch(key) is None for key in values):
        raise ValueError("AC11_SCHEMA_MATRIX_INVALID")
    if {
        "NORMAL_FIRST": values.get("NORMAL_FIRST"),
        "NORMAL_SECOND": values.get("NORMAL_SECOND"),
        "NORMAL_ROWS": values.get("NORMAL_ROWS"),
        "ATTACK_COUNT": values.get("ATTACK_COUNT"),
        "ATTACK_PASS_COUNT": values.get("ATTACK_PASS_COUNT"),
        "AC11_SCHEMA_CONSTRAINT_MATRIX_PASS": values.get(
            "AC11_SCHEMA_CONSTRAINT_MATRIX_PASS"
        ),
    } != {
        "NORMAL_FIRST": "ACCEPTED",
        "NORMAL_SECOND": "REPLAY_BLOCKED",
        "NORMAL_ROWS": "1",
        "ATTACK_COUNT": "15",
        "ATTACK_PASS_COUNT": "15",
        "AC11_SCHEMA_CONSTRAINT_MATRIX_PASS": "TRUE",
    }:
        raise ValueError("AC11_SCHEMA_MATRIX_INVALID")
    names: set[str] = set()
    expected_result = "STORE_BLOCKED:AUTHORIZATION_REPLAY_SCHEMA_MISMATCH"
    for number in range(1, 16):
        prefix = f"ATTACK_{number:02d}_"
        name = values.get(prefix + "NAME", "")
        if (
            not _ATTACK_NAME.fullmatch(name)
            or name in names
            or values.get(prefix + "FIRST") != expected_result
            or values.get(prefix + "SECOND") != expected_result
            or values.get(prefix + "ROWS") != "0"
            or values.get(prefix + "FAIL_CLOSED") != "TRUE"
        ):
            raise ValueError("AC11_SCHEMA_MATRIX_INVALID")
        names.add(name)
    if len(values) != len(fixed) + 15 * 5:
        raise ValueError("AC11_SCHEMA_MATRIX_INVALID")
    return {
        "attack_count": 15,
        "matrix_sha256": expected_sha256,
        "normal_rows": 1,
        "weakened_rows": 0,
    }


def verify_database(path: Path) -> dict[str, object]:
    metadata = path.lstat()
    if path.is_symlink() or not path.is_file() or metadata.st_size < 1:
        raise ValueError("AUDIT_DATABASE_INVALID")
    # mode=ro intentionally observes committed WAL pages. Evidence packaging
    # checkpoints and copies the database before invoking this verifier.
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT sequence,event_id,observed_at,actor_hash,tenant_id,company_id,"
            "action,resource_hash,decision,reason_code,policy_digest,"
            "assertion_jti_hash,request_id,trace_id,role_registry_version,"
            "before_hash,after_hash,prev_hash,event_hash "
            "FROM accounting_authorization_audit_v2 ORDER BY sequence"
        ).fetchall()
        sequence_row = connection.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='accounting_authorization_audit_v2'"
        ).fetchone()
    if not rows:
        raise ValueError("AUDIT_EVENT_MISSING")
    previous_by_tenant: dict[str, str] = {}
    coverage: set[tuple[str, str]] = set()
    last_sequence = 0
    for row in rows:
        item = dict(row)
        if int(item["sequence"]) != last_sequence + 1:
            raise ValueError("AUDIT_SEQUENCE_INVALID")
        last_sequence = int(item["sequence"])
        action = str(item["action"])
        decision = str(item["decision"])
        if action not in ACTIONS or decision not in {"ALLOW", "DENY"}:
            raise ValueError("AUDIT_DECISION_INVALID")
        for field in (
            "actor_hash",
            "resource_hash",
            "policy_digest",
            "assertion_jti_hash",
            "before_hash",
            "after_hash",
            "prev_hash",
            "event_hash",
        ):
            if not _DIGEST.fullmatch(str(item[field])):
                raise ValueError("AUDIT_DIGEST_INVALID")
        tenant = str(item["tenant_id"])
        expected_previous = previous_by_tenant.get(tenant, "0" * 64)
        if item["prev_hash"] != expected_previous:
            raise ValueError("AUDIT_CHAIN_PREVIOUS_MISMATCH")
        claimed = str(item.pop("event_hash"))
        item["schema_version"] = "2.0"
        if _digest(item) != claimed:
            raise ValueError("AUDIT_EVENT_HASH_MISMATCH")
        previous_by_tenant[tenant] = claimed
        coverage.add((action, decision))
    if sequence_row is None or int(sequence_row["seq"]) != len(rows):
        raise ValueError("AUDIT_SEQUENCE_CHECKPOINT_MISMATCH")
    return {
        "event_count": len(rows),
        "allow_actions": sorted(action for action, result in coverage if result == "ALLOW"),
        "deny_actions": sorted(action for action, result in coverage if result == "DENY"),
        "chain_heads_digest": _digest(previous_by_tenant),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--ac11-schema-matrix", required=True, type=Path)
    parser.add_argument("--expected-matrix-sha256", required=True)
    parser.add_argument("--require-allow-matrix", action="store_true")
    parser.add_argument("--require-deny-matrix", action="store_true")
    args = parser.parse_args()
    try:
        schema_matrix = verify_ac11_schema_matrix(
            args.ac11_schema_matrix, args.expected_matrix_sha256
        )
        result = verify_database(args.database)
        if args.require_allow_matrix and set(result["allow_actions"]) != ACTIONS:
            raise ValueError("AUDIT_ALLOW_COVERAGE_INCOMPLETE")
        if args.require_deny_matrix and set(result["deny_actions"]) != ACTIONS:
            raise ValueError("AUDIT_DENY_COVERAGE_INCOMPLETE")
    except (OSError, sqlite3.DatabaseError, ValueError) as exc:
        code = str(exc)
        if not code.isascii() or len(code) > 96:
            code = "AUDIT_VERIFICATION_FAILED"
        print("STATUS=BLOCK")
        print(f"ERROR_CODE={code}")
        return 1
    print("STATUS=PASS")
    print(f"EVENT_COUNT={result['event_count']}")
    print(f"CHAIN_HEADS_DIGEST={result['chain_heads_digest']}")
    print(f"AC11_ATTACK_COUNT={schema_matrix['attack_count']}")
    print(f"AC11_SCHEMA_MATRIX_SHA256={schema_matrix['matrix_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
