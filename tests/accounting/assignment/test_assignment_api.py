from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from butler_pc_core.accounting.assignment.registry import RegistryEntry, RegistrySnapshot
from butler_pc_core.accounting.assignment.runtime import (
    AccountingReviewRuntime,
    set_accounting_review_runtime_for_tests,
)
from butler_pc_core.accounting.assignment.security import MemoryKeyStore
from butler_pc_core.auth.capability_token import CapabilityTokenManager
from tests.accounting.assignment.authorization_testkit import (
    issue_test_assertion,
    make_authorized_test_app,
    make_test_authority,
)


@pytest.fixture()
def api(tmp_path: Path):
    registry = RegistrySnapshot(
        registry_digest="3" * 64,
        overlay_digest="4" * 64,
        entries=(
            RegistryEntry("GROUP.API", None, "API 그룹", ("API 그룹",), "GROUP", False, "ACCOUNT_NODE_GROUP_NOT_ASSIGNABLE", 10),
            RegistryEntry("POSTING.API", "2001", "지급수수료", ("API 그룹", "지급수수료"), "POSTING", True, None, 20),
        ),
    )
    runtime = AccountingReviewRuntime(
        db_path=tmp_path / "api.sqlite3",
        key_store=MemoryKeyStore(key=b"e" * 32),
        registry=registry,
    )
    profile_id = "api-tenant"
    profile = SimpleNamespace(
        status="ACTIVE",
        profile_id=profile_id,
        profile_digest=hashlib.sha256(profile_id.encode()).hexdigest(),
    )

    class ProfileStore:
        def load_active_profile(self):
            return profile

    token_manager = CapabilityTokenManager(tmp_path / "sidecar-token")
    token = token_manager.generate()
    authorization_service, private_key, trust = make_test_authority(
        tmp_path, token_manager, runtime.authorization_replay_store
    )
    app = make_authorized_test_app(
        token_manager=token_manager,
        authorization_service=authorization_service,
        profile_store_factory=ProfileStore,
        runtime=runtime,
    )
    # The projection helper is an older non-route product seam and still uses
    # the canonical runtime singleton.  Route authorization itself is composed
    # exclusively through the isolated app above.
    set_accounting_review_runtime_for_tests(runtime)
    runtime.ingest_dataframe(
        "batch_api_product_001",
        pd.DataFrame([{"거래일시": "2026-07-16", "상대계좌예금주명": "API 검증 거래", "금액": "-5000", "분류과목": "미분류"}]),
        profile,
        source_file_sha256=hashlib.sha256(b"api-product-fixture").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    local_session = token_manager.verify_authorization_header(f"Bearer {token}")

    def authorized_headers(action: str, resource_type: str, resource_id: str):
        return {
            "Butler-User-Authorization": issue_test_assertion(
                private_key,
                trust,
                local_session=local_session,
                profile=profile,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        }
    try:
        yield client, runtime, authorized_headers
    finally:
        set_accounting_review_runtime_for_tests(None)


def test_http_product_route_review_assign_and_refresh(api):
    client, runtime, authorized_headers = api
    summary = client.get(
        "/v1/accounting/batches/batch_api_product_001/review-summary",
        headers=authorized_headers("ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_api_product_001"),
    )
    assert summary.status_code == 200
    assert summary.json()["counts"]["review_required"] == 1

    page = client.get(
        "/v1/accounting/batches/batch_api_product_001/unaccounted",
        headers=authorized_headers("ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_api_product_001"),
    )
    assert page.status_code == 200
    txn = page.json()["items"][0]
    registry = client.get(
        "/v1/accounting/chart-of-accounts",
        headers=authorized_headers("ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "active-registry"),
    )
    assert registry.status_code == 200
    assert [entry["account_id"] for entry in registry.json()["entries"] if entry["assignable"]] == ["POSTING.API"]
    nonce = client.post(
        f"/v1/accounting/unaccounted/{txn['txn_id']}/action-nonce?scope=THIS_ONLY",
        headers=authorized_headers("ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn["txn_id"]),
    )
    assert nonce.status_code == 200

    assigned = client.post(
        f"/v1/accounting/unaccounted/{txn['txn_id']}/assign",
        headers={
            **authorized_headers("ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn["txn_id"]),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "account_id": "POSTING.API",
            "scope": "THIS_ONLY",
            "client_action_id": str(uuid.uuid4()),
            "user_action_nonce": nonce.json()["user_action_nonce"],
            "expected_transaction_version": 1,
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["state"] == "USER_ASSIGNED"
    assert client.get(
        "/v1/accounting/batches/batch_api_product_001/unaccounted",
        headers=authorized_headers("ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_api_product_001"),
    ).json()["items"] == []


def test_http_product_route_rejects_auth_and_forged_evidence(api):
    client, runtime, authorized_headers = api
    assert client.get(
        "/v1/accounting/batches/batch_api_product_001/review-summary",
        headers={"Authorization": ""},
    ).status_code == 401
    txn_id = client.get(
        "/v1/accounting/batches/batch_api_product_001/unaccounted",
        headers=authorized_headers("ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_api_product_001"),
    ).json()["items"][0]["txn_id"]
    nonce = client.post(
        f"/v1/accounting/unaccounted/{txn_id}/action-nonce?scope=THIS_ONLY",
        headers=authorized_headers("ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id),
    ).json()["user_action_nonce"]
    forged = client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={
            **authorized_headers("ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "account_id": "POSTING.API",
            "scope": "THIS_ONLY",
            "client_action_id": str(uuid.uuid4()),
            "user_action_nonce": nonce,
            "expected_transaction_version": 1,
            "descriptor_digest": "f" * 64,
        },
    )
    assert forged.status_code == 422
    denied = client.post(
        "/v1/accounting/learned-rules/00000000-0000-4000-8000-000000000001/deactivate",
        headers={
            **authorized_headers(
                "ASSIGNMENT_CREATE",
                "LEARNED_RULE",
                "00000000-0000-4000-8000-000000000001",
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
    )
    assert denied.status_code == 403
    assert denied.json()["reason_code"] == "AUTHORIZATION_RESOURCE_MISMATCH"


def test_upload_projection_registration_exposes_review_count(api):
    client, runtime, _ = api
    import butler_sidecar

    profile = (
        client.app.state.box5_accounting_dependencies
        .profile_store_factory()
        .load_active_profile()
    )
    projection = butler_sidecar._register_accounting_review_projection(
        "batch_upload_projection_001",
        pd.DataFrame([
            {"거래일시": "2026-07-17", "상대계좌예금주명": "업로드 검토 거래", "금액": "-7000", "분류과목": "미분류"}
        ]),
        profile,
        None,
        hashlib.sha256(b"upload-projection-fixture").hexdigest(),
    )
    assert projection == {
        "available": True,
        "batch_id": "batch_upload_projection_001",
        "review_required_count": 1,
        "reason_code": None,
    }
    context = runtime.context_from_profile(profile)
    assert runtime.unaccounted_page(
        context, "batch_upload_projection_001", cursor=None, page_size=50
    )["total_count"] == 1
