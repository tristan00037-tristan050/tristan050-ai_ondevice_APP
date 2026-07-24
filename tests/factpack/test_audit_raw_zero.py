from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.factpack.schema import FactPackAuditEntry


REPO_ROOT = Path(__file__).resolve().parents[2]


try:
    from fastapi.testclient import TestClient

    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False


pytestmark = [
    pytest.mark.skipif(not _FASTAPI_OK, reason="fastapi 미설치"),
    pytest.mark.active_policy,
]


def _events(raw: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in raw.splitlines():
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif line == "" and current:
            parsed.append(current)
            current = {}
    if current:
        parsed.append(current)
    return parsed


def _client_and_sidecar():
    import butler_sidecar as sidecar

    sidecar._factpack_audit_log.clear()
    return TestClient(sidecar.app), sidecar


def _post_query(client: TestClient, query: str) -> list[dict[str, Any]]:
    response = client.post(
        "/api/analyze/stream",
        data={"query": query, "card_mode": "free", "total_chunks": "1", "output_dir": "/tmp"},
    )
    assert response.status_code == 200
    return _events(response.text)


def test_factpack_audit_entry_schema_has_query_digest_only():
    fields = set(FactPackAuditEntry.model_fields)

    assert "query_digest" in fields
    assert "query" not in fields


def test_factpack_audit_hit_stores_query_digest_not_raw_query():
    raw_query = "한국의 4대 보험은 무엇인가요?"
    client, sidecar = _client_and_sidecar()

    events = _post_query(client, raw_query)

    assert "complete" in [event["event"] for event in events]
    assert sidecar._factpack_audit_log
    entry = sidecar._factpack_audit_log[-1].model_dump()
    encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    assert entry["source"] == "factpack"
    assert entry["query_digest"] == sha256_text(raw_query)
    assert "query" not in entry
    assert raw_query not in encoded


def test_factpack_audit_miss_stores_query_digest_not_raw_query():
    raw_query = "이 문장은 factpack에 없는 독립 테스트 질문입니다"
    client, sidecar = _client_and_sidecar()

    _post_query(client, raw_query)

    assert sidecar._factpack_audit_log
    entry = sidecar._factpack_audit_log[-1].model_dump()
    encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    assert entry["source"] == "llm"
    assert entry["query_digest"] == sha256_text(raw_query)
    assert "query" not in entry
    assert raw_query not in encoded


def test_factpack_audit_code_path_has_no_raw_query_assignment():
    sidecar_text = (REPO_ROOT / "butler_sidecar.py").read_text(encoding="utf-8")
    schema_text = (REPO_ROOT / "butler_pc_core/factpack/schema.py").read_text(encoding="utf-8")

    tree = ast.parse(sidecar_text)
    audit_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "FactPackAuditEntry"
    ]
    assert audit_calls
    assert all("query" not in {keyword.arg for keyword in call.keywords} for call in audit_calls)
    assert "query: str" not in schema_text
