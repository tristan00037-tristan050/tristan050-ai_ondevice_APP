from __future__ import annotations

import hashlib
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
import butler_pc_core.accounting.assignment.router as route_module


@pytest.fixture()
def api(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(route_module, "CompanyProfileStore", ProfileStore)
    monkeypatch.setattr(route_module, "_TOKEN_MANAGER", token_manager)
    set_accounting_review_runtime_for_tests(runtime)
    runtime.ingest_dataframe(
        "batch_api_product_001",
        pd.DataFrame([{"거래일": "2026-07-16", "거래내용": "API 검증 거래", "금액": "-5000", "분류과목": "미분류"}]),
        profile,
    )
    app = fastapi.FastAPI()
    app.include_router(route_module.router)
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    try:
        yield client, runtime
    finally:
        set_accounting_review_runtime_for_tests(None)


def test_http_product_route_review_assign_and_refresh(api):
    client, runtime = api
    summary = client.get("/v1/accounting/batches/batch_api_product_001/review-summary")
    assert summary.status_code == 200
    assert summary.json()["counts"]["review_required"] == 1

    page = client.get("/v1/accounting/batches/batch_api_product_001/unaccounted")
    assert page.status_code == 200
    txn = page.json()["items"][0]
    registry = client.get("/v1/accounting/chart-of-accounts")
    assert registry.status_code == 200
    assert [entry["account_id"] for entry in registry.json()["entries"] if entry["assignable"]] == ["POSTING.API"]

    assigned = client.post(
        f"/v1/accounting/unaccounted/{txn['txn_id']}/assign",
        headers={"Idempotency-Key": "api-idempotency-0001", "If-Match": '"1"'},
        json={
            "schema_version": "2.0",
            "account_id": "POSTING.API",
            "scope": "THIS_ONLY",
            "registry_digest": runtime.registry.registry_digest,
            "expected_transaction_version": 1,
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["state"] == "USER_ASSIGNED"
    assert client.get("/v1/accounting/batches/batch_api_product_001/unaccounted").json()["items"] == []


def test_http_product_route_rejects_auth_and_forged_evidence(api):
    client, runtime = api
    assert client.get(
        "/v1/accounting/batches/batch_api_product_001/review-summary",
        headers={"Authorization": ""},
    ).status_code == 401
    txn_id = client.get("/v1/accounting/batches/batch_api_product_001/unaccounted").json()["items"][0]["txn_id"]
    forged = client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={"Idempotency-Key": "api-idempotency-0002", "If-Match": '"1"'},
        json={
            "schema_version": "2.0",
            "account_id": "POSTING.API",
            "scope": "THIS_ONLY",
            "registry_digest": runtime.registry.registry_digest,
            "expected_transaction_version": 1,
            "descriptor_digest": "f" * 64,
        },
    )
    assert forged.status_code == 422


def test_upload_projection_registration_exposes_review_count(api):
    _, runtime = api
    import butler_sidecar

    profile = route_module.CompanyProfileStore().load_active_profile()
    projection = butler_sidecar._register_accounting_review_projection(
        "batch_upload_projection_001",
        pd.DataFrame([
            {"거래일": "2026-07-17", "거래내용": "업로드 검토 거래", "금액": "-7000", "분류과목": "미분류"}
        ]),
        profile,
        None,
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
