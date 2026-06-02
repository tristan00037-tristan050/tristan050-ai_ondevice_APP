from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.company_policy.contracts import AccessRule, sha256_text, make_company_policy
from butler_pc_core.company_policy.middleware import add_policy_gate_middleware
from butler_pc_core.company_policy.storage import PolicyStore
from butler_pc_core.company_policy.contracts import AdminContext


def admin():
    return AdminContext(
        admin_id_digest=sha256_text("admin"),
        role="admin",
        admin_session_digest=sha256_text("session"),
        auth_method="test_only",
    )


def _client(tmp_path, with_policy=True, decision="allow"):
    store = PolicyStore(root=tmp_path / "policy")
    if with_policy:
        policy = make_company_policy(
            registered_by_digest=sha256_text("admin"),
            access_rules=[AccessRule(dept_digest=sha256_text("dept"), role="employee", doc_grade="internal", decision=decision, reason_code="RULE_MATCHED")],
        )
        store.save_policy(policy, admin())
    app = FastAPI()
    add_policy_gate_middleware(app, policy_store=store)
    calls = {"count": 0}

    @app.post("/v1/cards/3/draft")
    async def draft():
        calls["count"] += 1
        return {"ok": True}

    return TestClient(app), calls


def test_policy_gate_middleware_allow_calls_box(tmp_path):
    client, calls = _client(tmp_path, with_policy=True, decision="allow")
    response = client.post(
        "/v1/cards/3/draft",
        headers={
            "x-request-id": "req",
            "x-tenant-digest": sha256_text("tenant"),
            "x-dept-digest": sha256_text("dept"),
            "x-user-role": "employee",
            "x-doc-grade": "internal",
        },
    )
    assert response.status_code == 200
    assert calls["count"] == 1


def test_policy_gate_middleware_bootstrap_blocks_box_call_zero(tmp_path):
    client, calls = _client(tmp_path, with_policy=False)
    response = client.post(
        "/v1/cards/3/draft",
        headers={
            "x-request-id": "req",
            "x-tenant-digest": sha256_text("tenant"),
            "x-dept-digest": sha256_text("dept"),
            "x-user-role": "employee",
            "x-doc-grade": "internal",
        },
    )
    assert response.status_code == 403
    assert response.json()["block_reason"] == "POLICY_BOOTSTRAP_REQUIRED"
    assert calls["count"] == 0


def test_policy_gate_middleware_deny_calls_zero(tmp_path):
    client, calls = _client(tmp_path, with_policy=True, decision="block")
    response = client.post(
        "/v1/cards/3/draft",
        headers={
            "x-request-id": "req",
            "x-tenant-digest": sha256_text("tenant"),
            "x-dept-digest": sha256_text("dept"),
            "x-user-role": "employee",
            "x-doc-grade": "internal",
        },
    )
    assert response.status_code == 403
    assert calls["count"] == 0


def test_audit_raw_zero_after_format_and_policy(tmp_path):
    client, calls = _client(tmp_path, with_policy=True, decision="allow")
    response = client.post(
        "/v1/cards/3/draft",
        headers={
            "x-request-id": "req",
            "x-tenant-digest": sha256_text("tenant"),
            "x-dept-digest": sha256_text("dept"),
            "x-user-role": "employee",
            "x-doc-grade": "internal",
        },
    )
    encoded = json.dumps(response.json(), ensure_ascii=False)
    assert ("/" + "Users/") not in encoded
    assert ("/" + "home/") not in encoded
    assert ("sk-" + "proj-") not in encoded
    assert "token" not in encoded.lower()
