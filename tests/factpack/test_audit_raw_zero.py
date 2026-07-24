from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.factpack.schema import FactPackAuditEntry


try:
    from fastapi.testclient import TestClient

    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False


pytestmark = pytest.mark.skipif(not _FASTAPI_OK, reason="fastapi 미설치")


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


# Audit-path-scoped scan. The original `"query=params.query" not in sidecar_text`
# whole-file scan false-flagged the required prompt/stream flow
# (render_card_user_prompt(query=params.query), AnalyzeStreamRequest(query=...)).
# The audit contract is only: the FactPackAuditEntry record must carry
# query_digest, never a raw `query=` field. Scope the scan to those records.
def _factpack_audit_record_bodies(text: str) -> list[str]:
    marker = "FactPackAuditEntry("
    bodies: list[str] = []
    idx = 0
    while True:
        i = text.find(marker, idx)
        if i == -1:
            break
        start = i + len(marker)
        depth, j = 1, start
        while j < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        bodies.append(text[start : j - 1])
        idx = j
    return bodies


def _audit_records_with_raw_query(text: str) -> list[str]:
    """FactPackAuditEntry(...) records that assign a raw `query=` field
    (query_digest= is the correct, allowed form)."""
    offenders = []
    for body in _factpack_audit_record_bodies(text):
        if any(m.group(1) == "query" for m in re.finditer(r"\b(query\w*)\s*=", body)):
            offenders.append(body)
    return offenders


def test_factpack_audit_code_path_has_no_raw_query_assignment():
    sidecar_text = Path("butler_sidecar.py").read_text(encoding="utf-8")
    schema_text = Path("butler_pc_core/factpack/schema.py").read_text(encoding="utf-8")

    # audit-path-scoped: only the FactPackAuditEntry record construction, not the
    # required prompt/stream `query=params.query` runtime flow.
    assert _audit_records_with_raw_query(sidecar_text) == []
    assert "query: str" not in schema_text


def test_factpack_audit_raw_query_regression_still_detected():
    """★ Plant a genuine raw-query leak in an audit record: still detected."""
    leak = 'FactPackAuditEntry(query=params.query, source="factpack")'
    assert _audit_records_with_raw_query(leak) == [leak[len("FactPackAuditEntry("):-1]]
    # the correct digest-only form is not flagged
    ok = 'FactPackAuditEntry(query_digest=sha256_text(params.query), source="factpack")'
    assert _audit_records_with_raw_query(ok) == []
