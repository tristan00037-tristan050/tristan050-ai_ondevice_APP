from __future__ import annotations

import base64
import hashlib
import inspect
import json
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

pd = pytest.importorskip("pandas")
fastapi = pytest.importorskip("fastapi")
jsonschema = pytest.importorskip("jsonschema")
from fastapi.testclient import TestClient

import butler_pc_core.accounting.assignment.authorization as authorization_module
from butler_pc_core.accounting.assignment.authorization import (
    Box5AuthorizationService,
    ExistingUserAuthorizationAuthority,
    build_product_authorization_service,
)
from butler_pc_core.accounting.assignment.domain import AssignmentError
from butler_pc_core.accounting.assignment.router import (
    assign_account,
    install_product_accounting_dependencies,
)
from butler_pc_core.accounting.assignment.registry import RegistryEntry, RegistrySnapshot
from butler_pc_core.accounting.assignment.runtime import AccountingReviewRuntime
from butler_pc_core.accounting.assignment.security import MemoryKeyStore
from butler_pc_core.auth.capability_token import CapabilityTokenManager, LocalIpcSession
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from tests.accounting.assignment.authorization_testkit import (
    TEST_SUBJECT,
    issue_test_assertion,
    make_authorized_test_app,
    make_test_authority,
)
from scripts.verify_box5_authorization_audit import verify_database
from scripts.audit.reproduce_box5_ac11_schema_constraints_v1 import mutation_corpus


@pytest.fixture()
def authorized_api(tmp_path: Path):
    registry = RegistrySnapshot(
        registry_digest="7" * 64,
        overlay_digest="8" * 64,
        entries=(
            RegistryEntry(
                "POSTING.AUTH",
                "2001",
                "지급수수료",
                ("비용", "지급수수료"),
                "POSTING",
                True,
                None,
                10,
            ),
            RegistryEntry(
                "POSTING.AUTH.OTHER",
                "2002",
                "통신비",
                ("비용", "통신비"),
                "POSTING",
                True,
                None,
                20,
            ),
        ),
    )
    runtime = AccountingReviewRuntime(
        db_path=tmp_path / "authorization.sqlite3",
        key_store=MemoryKeyStore(key=b"z" * 32),
        registry=registry,
    )
    profile = SimpleNamespace(
        status="ACTIVE",
        profile_id="tenant-authorization-test",
        profile_digest=hashlib.sha256(b"tenant-authorization-test").hexdigest(),
    )

    class ProfileStore:
        def load_active_profile(self):
            return profile

    token_manager = CapabilityTokenManager(tmp_path / "sidecar-token")
    token = token_manager.generate()
    local_session = token_manager.verify_authorization_header(f"Bearer {token}")
    service, private_key, trust = make_test_authority(
        tmp_path, token_manager, runtime.authorization_replay_store
    )
    runtime.ingest_dataframe(
        "batch_authorization_001",
        pd.DataFrame(
            [
                {
                    "거래일시": "2026-08-02",
                    "상대계좌예금주명": "합성 권한 거래처",
                    "금액": "-5000",
                    "분류과목": "미분류",
                }
            ]
        ),
        profile,
        source_file_sha256=hashlib.sha256(b"authorization-fixture").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    runtime.ingest_dataframe(
        "batch_authorization_quarantine",
        pd.DataFrame(
            [
                {
                    "거래일시": "2026-08-02",
                    "상대계좌예금주명": "합성 격리 거래처",
                    "금액": "invalid",
                }
            ]
        ),
        profile,
        source_file_sha256=hashlib.sha256(b"authorization-quarantine").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    app = make_authorized_test_app(
        token_manager=token_manager,
        authorization_service=service,
        profile_store_factory=ProfileStore,
        runtime=runtime,
    )
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

    def assertion(
        action: str,
        resource_type: str,
        resource_id: str,
        overrides: dict[str, object] | None = None,
    ) -> str:
        return issue_test_assertion(
            private_key,
            trust,
            local_session=local_session,
            profile=profile,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            overrides=overrides,
        )

    def headers(
        action: str,
        resource_type: str,
        resource_id: str,
        overrides: dict[str, object] | None = None,
    ) -> dict[str, str]:
        return {
            "Butler-User-Authorization": assertion(
                action, resource_type, resource_id, overrides
            )
        }

    yield SimpleNamespace(
        client=client,
        runtime=runtime,
        profile=profile,
        token=token,
        token_manager=token_manager,
        local_session=local_session,
        service=service,
        private_key=private_key,
        trust=trust,
        trust_path=tmp_path / "authorization-trust.test.json",
        assertion=assertion,
        headers=headers,
    )


def _transaction_id(api) -> str:
    response = api.client.get(
        "/v1/accounting/batches/batch_authorization_001/unaccounted",
        headers=api.headers(
            "ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_authorization_001"
        ),
    )
    assert response.status_code == 200
    return response.json()["items"][0]["txn_id"]


def _nonce(api, txn_id: str, action: str, scope: str) -> str:
    response = api.client.post(
        f"/v1/accounting/unaccounted/{txn_id}/action-nonce?scope={scope}",
        headers=api.headers(action, "ACCOUNTING_TRANSACTION", txn_id),
    )
    assert response.status_code == 200
    assert response.json()["action"] == action
    return response.json()["user_action_nonce"]


def _assignment_request(
    api,
    txn_id: str,
    *,
    scope: str,
    action: str,
    nonce: str,
    assertion_action: str | None = None,
    idempotency_key: str | None = None,
    client_action_id: str | None = None,
    user_assertion: str | None = None,
    account_id: str = "POSTING.AUTH",
):
    assertion = user_assertion or api.assertion(
        assertion_action or action, "ACCOUNTING_TRANSACTION", txn_id
    )
    return api.client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={
            "Butler-User-Authorization": assertion,
            "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "account_id": account_id,
            "scope": scope,
            "client_action_id": client_action_id or str(uuid.uuid4()),
            "user_action_nonce": nonce,
            "expected_transaction_version": 1,
        },
    )


def _side_effect_counts(runtime: AccountingReviewRuntime) -> tuple[int, int, int, int]:
    with sqlite3.connect(runtime.store.path) as conn:
        return tuple(
            conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "current_assignments",
                "learned_rules",
                "assignment_events",
                "idempotency_records",
            )
        )


def test_user_this_only_succeeds_and_future_without_action_is_zero_effect(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    before = _side_effect_counts(api.runtime)
    denied = _assignment_request(
        api,
        txn_id,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        assertion_action="ASSIGNMENT_CREATE",
        nonce="n" * 48,
    )
    assert denied.status_code == 403
    assert denied.json()["reason_code"] == "AUTHORIZATION_RESOURCE_MISMATCH"
    assert _side_effect_counts(api.runtime) == before

    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    allowed = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=nonce,
    )
    assert allowed.status_code == 200
    assert allowed.json()["rule_effect"] == "NONE"
    assert _side_effect_counts(api.runtime)[:2] == (1, 0)


def test_authorized_future_rule_and_quarantine_actions_are_reachable(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(
        api, txn_id, "RULE_FUTURE_CREATE", "SAME_VENDOR_FUTURE"
    )
    allowed = _assignment_request(
        api,
        txn_id,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        nonce=nonce,
    )
    assert allowed.status_code == 200
    assert allowed.json()["rule_effect"] == "ACTIVE_USER_RULE_CREATED"
    assert _side_effect_counts(api.runtime)[:2] == (1, 1)

    page = api.client.get(
        "/v1/accounting/review/batches/batch_authorization_quarantine/quarantine",
        headers=api.headers(
            "ACCOUNTING_REVIEW_VIEW",
            "REVIEW_BATCH",
            "batch_authorization_quarantine",
        ),
    )
    row = page.json()["items"][0]
    before_quarantine = _side_effect_counts(api.runtime)
    denied = api.client.post(
        "/v1/accounting/review/batches/batch_authorization_quarantine/"
        f"quarantine/{row['row_id']}/recompile",
        headers={
            **api.headers(
                "ASSIGNMENT_CREATE",
                "QUARANTINED_ROW",
                row["row_id"],
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={"amount_minor": -100, "booked_date": "2026-08-02", "currency": "KRW"},
    )
    assert denied.status_code == 403
    assert denied.json()["reason_code"] == "AUTHORIZATION_RESOURCE_MISMATCH"
    assert _side_effect_counts(api.runtime) == before_quarantine

    corrected = api.client.post(
        "/v1/accounting/review/batches/batch_authorization_quarantine/"
        f"quarantine/{row['row_id']}/recompile",
        headers={
            **api.headers(
                "QUARANTINE_ROW_RECOMPILE",
                "QUARANTINED_ROW",
                row["row_id"],
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={"amount_minor": -100, "booked_date": "2026-08-02", "currency": "KRW"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["state"] == "UNACCOUNTED"


def test_product_rule_application_revert_uses_its_own_authority_action(authorized_api):
    api = authorized_api
    first_txn = _transaction_id(api)
    nonce = _nonce(api, first_txn, "RULE_FUTURE_CREATE", "SAME_VENDOR_FUTURE")
    created = _assignment_request(
        api,
        first_txn,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        nonce=nonce,
    )
    assert created.status_code == 200
    api.runtime.ingest_dataframe(
        "batch_authorization_revert",
        pd.DataFrame([{
            "거래일시": "2026-08-05",
            "상대계좌예금주명": "합성 권한 거래처",
            "금액": "-7000",
            "분류과목": "미분류",
        }]),
        api.profile,
        source_file_sha256=hashlib.sha256(b"authorization-revert").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    page = api.client.get(
        "/v1/accounting/batches/batch_authorization_revert/unaccounted",
        headers=api.headers(
            "ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_authorization_revert"
        ),
    )
    draft = page.json()["items"][0]
    assert draft["review_state"] == "USER_RULE_APPLIED_DRAFT"
    reverted = api.client.post(
        f"/v1/accounting/review/transactions/{draft['txn_id']}/rule-application/revert",
        headers={
            **api.headers(
                "RULE_APPLICATION_REVERT", "ACCOUNTING_TRANSACTION", draft["txn_id"]
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
    )
    assert reverted.status_code == 200
    verified = verify_database(api.runtime.store.path)
    assert set(verified["allow_actions"]) == {
        "RULE_FUTURE_CREATE", "RULE_APPLICATION_REVERT"
    }


def test_all_six_missing_assertion_denials_are_audited_without_mutation(authorized_api):
    api = authorized_api
    mutation_headers = {
        "Idempotency-Key": str(uuid.uuid4()),
        "If-Match": 'W/"1"',
    }
    assignment_body = {
        "account_id": "POSTING.AUTH",
        "scope": "THIS_ONLY",
        "client_action_id": str(uuid.uuid4()),
        "user_action_nonce": "n" * 48,
        "expected_transaction_version": 1,
    }
    requests = (
        (
            "/v1/accounting/unaccounted/txn_deny_assignment_001/assign",
            assignment_body,
        ),
        (
            "/v1/accounting/unaccounted/txn_deny_rule_001/assign",
            {**assignment_body, "scope": "SAME_VENDOR_FUTURE"},
        ),
        ("/v1/accounting/learned-rules/rule_deny_001/deactivate", None),
        (
            "/v1/accounting/review/transactions/txn_deny_revert_001/"
            "rule-application/revert",
            None,
        ),
        (
            "/v1/accounting/review/batches/batch_deny_001/"
            "quarantine/row_deny_001/recompile",
            {"amount_minor": -100, "booked_date": "2026-08-03", "currency": "KRW"},
        ),
        (
            "/v1/accounting/rule-conflicts/conflict_deny_001/resolve",
            {
                "schema_version": "2.0",
                "decision": "KEEP_EXISTING",
                "expected_conflict_version": 1,
            },
        ),
    )
    before = _side_effect_counts(api.runtime)
    for path, body in requests:
        response = api.client.post(path, headers=mutation_headers, json=body)
        assert response.status_code == 401
        assert response.json()["reason_code"] == "USER_ASSERTION_MISSING"
    assert _side_effect_counts(api.runtime) == before
    verified = verify_database(api.runtime.store.path)
    assert set(verified["deny_actions"]) == {
        "ASSIGNMENT_CREATE",
        "RULE_FUTURE_CREATE",
        "RULE_DEACTIVATE",
        "RULE_APPLICATION_REVERT",
        "QUARANTINE_ROW_RECOMPILE",
        "CONFLICT_RESOLVE",
    }


def test_denial_audit_failure_remains_fail_closed(authorized_api):
    api = authorized_api
    with sqlite3.connect(api.runtime.store.path) as connection:
        connection.execute(
            """CREATE TRIGGER fail_denial_audit BEFORE INSERT
               ON accounting_authorization_audit_v2
               BEGIN SELECT RAISE(ABORT, 'forced denial audit failure'); END"""
        )
    before = _side_effect_counts(api.runtime)
    response = api.client.post(
        "/v1/accounting/learned-rules/rule_deny_failure/deactivate",
        headers={
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
    )
    assert response.status_code == 503
    assert response.json()["reason_code"] == "AUTHORIZATION_AUDIT_UNAVAILABLE"
    assert _side_effect_counts(api.runtime) == before


def test_independent_audit_verifier_observes_all_six_real_allow_paths(authorized_api):
    api = authorized_api
    initial_txn = _transaction_id(api)
    initial_nonce = _nonce(api, initial_txn, "ASSIGNMENT_CREATE", "THIS_ONLY")
    assert _assignment_request(
        api,
        initial_txn,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=initial_nonce,
    ).status_code == 200

    def ingest(batch_id: str, amount: str) -> dict[str, object]:
        api.runtime.ingest_dataframe(
            batch_id,
            pd.DataFrame([{
                "거래일시": "2026-08-03",
                "상대계좌예금주명": "권한 감사 통합 거래처",
                "금액": amount,
                "분류과목": "미분류",
            }]),
            api.profile,
            source_file_sha256=hashlib.sha256(batch_id.encode()).hexdigest(),
            adapter_id="kr.ibk.statement",
        )
        response = api.client.get(
            f"/v1/accounting/batches/{batch_id}/unaccounted",
            headers=api.headers("ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", batch_id),
        )
        assert response.status_code == 200
        return response.json()["items"][0]

    source = ingest("batch_audit_matrix_source", "-6000")
    source_txn = str(source["txn_id"])
    rule_nonce = _nonce(
        api, source_txn, "RULE_FUTURE_CREATE", "SAME_VENDOR_FUTURE"
    )
    rule_response = _assignment_request(
        api,
        source_txn,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        nonce=rule_nonce,
    )
    assert rule_response.status_code == 200
    rule_id = rule_response.json()["rule_id"]

    conflict_row = ingest("batch_audit_matrix_conflict", "-7000")
    conflict_txn = str(conflict_row["txn_id"])
    conflict_nonce = _nonce(
        api, conflict_txn, "RULE_FUTURE_CREATE", "SAME_VENDOR_FUTURE"
    )
    conflict_response = _assignment_request(
        api,
        conflict_txn,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        nonce=conflict_nonce,
        account_id="POSTING.AUTH.OTHER",
    )
    assert conflict_response.status_code == 409
    conflict_id = conflict_response.json()["conflict_id"]
    resolved = api.client.post(
        f"/v1/accounting/rule-conflicts/{conflict_id}/resolve",
        headers={
            **api.headers("CONFLICT_RESOLVE", "RULE_CONFLICT", conflict_id),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "schema_version": "2.0",
            "decision": "KEEP_EXISTING",
            "expected_conflict_version": 1,
        },
    )
    assert resolved.status_code == 200

    draft = ingest("batch_audit_matrix_revert", "-8000")
    assert draft["review_state"] == "USER_RULE_APPLIED_DRAFT"
    draft_txn = str(draft["txn_id"])
    reverted = api.client.post(
        f"/v1/accounting/review/transactions/{draft_txn}/rule-application/revert",
        headers={
            **api.headers(
                "RULE_APPLICATION_REVERT", "ACCOUNTING_TRANSACTION", draft_txn
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
    )
    assert reverted.status_code == 200

    deactivated = api.client.post(
        f"/v1/accounting/learned-rules/{rule_id}/deactivate",
        headers={
            **api.headers("RULE_DEACTIVATE", "LEARNED_RULE", rule_id),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
    )
    assert deactivated.status_code == 200

    quarantine = api.client.get(
        "/v1/accounting/review/batches/batch_authorization_quarantine/quarantine",
        headers=api.headers(
            "ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_authorization_quarantine"
        ),
    ).json()["items"][0]
    row_id = quarantine["row_id"]
    corrected = api.client.post(
        "/v1/accounting/review/batches/batch_authorization_quarantine/"
        f"quarantine/{row_id}/recompile",
        headers={
            **api.headers(
                "QUARANTINE_ROW_RECOMPILE", "QUARANTINED_ROW", row_id
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={"amount_minor": -100, "booked_date": "2026-08-03", "currency": "KRW"},
    )
    assert corrected.status_code == 200
    verified = verify_database(api.runtime.store.path)
    assert set(verified["allow_actions"]) == {
        "ASSIGNMENT_CREATE",
        "RULE_FUTURE_CREATE",
        "RULE_DEACTIVATE",
        "RULE_APPLICATION_REVERT",
        "QUARANTINE_ROW_RECOMPILE",
        "CONFLICT_RESOLVE",
    }


def test_rule_revoke_and_conflict_resolution_require_and_accept_exact_actions(
    authorized_api,
):
    api = authorized_api
    first_txn = _transaction_id(api)
    first_nonce = _nonce(
        api, first_txn, "RULE_FUTURE_CREATE", "SAME_VENDOR_FUTURE"
    )
    first = _assignment_request(
        api,
        first_txn,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        nonce=first_nonce,
    )
    rule_id = first.json()["rule_id"]
    denied = api.client.post(
        f"/v1/accounting/learned-rules/{rule_id}/deactivate",
        headers={
            **api.headers(
                "ASSIGNMENT_CREATE", "LEARNED_RULE", rule_id
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
    )
    assert denied.status_code == 403
    allowed = api.client.post(
        f"/v1/accounting/learned-rules/{rule_id}/deactivate",
        headers={
            **api.headers("RULE_DEACTIVATE", "LEARNED_RULE", rule_id),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["state"] == "INACTIVE_USER"

    # Build an independent active rule, then request a different account for
    # the same exact 9-dimensional vendor key to reach the conflict route.
    api.runtime.ingest_dataframe(
        "batch_authorization_conflict_a",
        pd.DataFrame([{
            "거래일시": "2026-08-03",
            "상대계좌예금주명": "합성 충돌 거래처",
            "금액": "-6000",
            "분류과목": "미분류",
        }]),
        api.profile,
        source_file_sha256=hashlib.sha256(b"authorization-conflict-a").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    conflict_a = api.client.get(
        "/v1/accounting/batches/batch_authorization_conflict_a/unaccounted",
        headers=api.headers(
            "ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_authorization_conflict_a"
        ),
    ).json()["items"][0]["txn_id"]
    conflict_a_nonce = _nonce(
        api, conflict_a, "RULE_FUTURE_CREATE", "SAME_VENDOR_FUTURE"
    )
    assert _assignment_request(
        api,
        conflict_a,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        nonce=conflict_a_nonce,
    ).status_code == 200

    api.runtime.ingest_dataframe(
        "batch_authorization_conflict_b",
        pd.DataFrame([{
            "거래일시": "2026-08-04",
            "상대계좌예금주명": "합성 충돌 거래처",
            "금액": "-7000",
            "분류과목": "미분류",
        }]),
        api.profile,
        source_file_sha256=hashlib.sha256(b"authorization-conflict-b").hexdigest(),
        adapter_id="kr.ibk.statement",
    )
    conflict_b = api.client.get(
        "/v1/accounting/batches/batch_authorization_conflict_b/unaccounted",
        headers=api.headers(
            "ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_authorization_conflict_b"
        ),
    ).json()["items"][0]["txn_id"]
    conflict_b_nonce = _nonce(
        api, conflict_b, "RULE_FUTURE_CREATE", "SAME_VENDOR_FUTURE"
    )
    detected = _assignment_request(
        api,
        conflict_b,
        scope="SAME_VENDOR_FUTURE",
        action="RULE_FUTURE_CREATE",
        nonce=conflict_b_nonce,
        account_id="POSTING.AUTH.OTHER",
    )
    assert detected.status_code == 409
    conflict = detected.json()
    conflict_id = conflict["conflict_id"]
    wrong = api.client.post(
        f"/v1/accounting/rule-conflicts/{conflict_id}/resolve",
        headers={
            **api.headers("RULE_DEACTIVATE", "RULE_CONFLICT", conflict_id),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "schema_version": "2.0",
            "decision": "KEEP_EXISTING",
            "expected_conflict_version": 1,
        },
    )
    assert wrong.status_code == 403
    resolved = api.client.post(
        f"/v1/accounting/rule-conflicts/{conflict_id}/resolve",
        headers={
            **api.headers(
                "CONFLICT_RESOLVE", "RULE_CONFLICT", conflict_id
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "schema_version": "2.0",
            "decision": "KEEP_EXISTING",
            "expected_conflict_version": 1,
        },
    )
    assert resolved.status_code == 200


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"aud": "another-resource"}, "USER_ASSERTION_WRONG_AUDIENCE"),
        ({"iss": "attacker.invalid"}, "USER_ASSERTION_WRONG_ISSUER"),
        ({"typ": "another-token-type"}, "USER_ASSERTION_WRONG_TYPE"),
        ({"kid": "attacker-selected-key"}, "USER_ASSERTION_INVALID"),
        ({"alg": "none"}, "USER_ASSERTION_INVALID"),
        ({"company_id": "f" * 64}, "TENANT_COMPANY_MISMATCH"),
        ({"device_id": "d" * 64}, "DEVICE_SESSION_BINDING_MISMATCH"),
        ({"session_id": "e" * 64}, "DEVICE_SESSION_BINDING_MISMATCH"),
        (
            {
                "iat": int(time.time()),
                "nbf": int(time.time()) + 600,
                "exp": int(time.time()) + 700,
            },
            "USER_ASSERTION_INVALID",
        ),
        (
            {
                "iat": int(time.time()) - 500,
                "nbf": int(time.time()) - 500,
                "exp": int(time.time()) - 300,
            },
            "USER_ASSERTION_EXPIRED",
        ),
    ],
)
def test_invalid_assertion_matrix_is_fail_closed(authorized_api, overrides, expected):
    api = authorized_api
    txn_id = _transaction_id(api)
    response = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce="n" * 48,
        user_assertion=api.assertion(
            "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id, overrides
        ),
    )
    assert response.status_code in {401, 403}
    assert response.json()["reason_code"] == expected
    assert _side_effect_counts(api.runtime) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "forged_action",
    ["*", "all", " ALL ", "ＡＬＬ", "", "ASSIGNMENT_CREATE "],
)
def test_wildcard_and_normalization_action_bypasses_are_rejected(
    authorized_api, forged_action
):
    api = authorized_api
    txn_id = _transaction_id(api)
    response = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce="n" * 48,
        user_assertion=api.assertion(
            forged_action, "ACCOUNTING_TRANSACTION", txn_id
        ),
    )
    assert response.status_code == 403
    assert response.json()["reason_code"] == "AUTHORIZATION_RESOURCE_MISMATCH"
    assert _side_effect_counts(api.runtime) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "forged_resource",
    ["*", "all", "txn", "txn/*", " txn_deny ", "ＴＸＮ"],
)
def test_wildcard_and_prefix_resource_bypasses_are_rejected(
    authorized_api, forged_resource
):
    api = authorized_api
    txn_id = _transaction_id(api)
    response = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce="n" * 48,
        user_assertion=api.assertion(
            "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", forged_resource
        ),
    )
    assert response.status_code == 403
    assert response.json()["reason_code"] == "AUTHORIZATION_RESOURCE_MISMATCH"
    assert _side_effect_counts(api.runtime) == (0, 0, 0, 0)


def test_missing_user_assertion_invalid_ipc_and_binding_mismatch_are_blocked(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    body = {
        "account_id": "POSTING.AUTH",
        "scope": "THIS_ONLY",
        "client_action_id": str(uuid.uuid4()),
        "user_action_nonce": "n" * 48,
        "expected_transaction_version": 1,
    }
    missing = api.client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={"Idempotency-Key": str(uuid.uuid4()), "If-Match": 'W/"1"'},
        json=body,
    )
    assert missing.status_code == 401
    assert missing.json()["reason_code"] == "USER_ASSERTION_MISSING"
    invalid_ipc = api.client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={
            **api.headers(
                "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id
            ),
            "Authorization": "Bearer invalid",
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json=body,
    )
    assert invalid_ipc.status_code == 401
    assert invalid_ipc.json()["reason_code"] == "IPC_CREDENTIAL_INVALID"
    mismatched = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce="n" * 48,
        user_assertion=api.assertion(
            "ASSIGNMENT_CREATE",
            "ACCOUNTING_TRANSACTION",
            txn_id,
            {"tenant_id": "other-tenant"},
        ),
    )
    assert mismatched.status_code == 403
    assert mismatched.json()["reason_code"] == "TENANT_COMPANY_MISMATCH"
    assert _side_effect_counts(api.runtime) == (0, 0, 0, 0)


def test_same_service_rechecks_role_registry_after_live_revocation(
    authorized_api,
):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    administrator = AdminContext(
        admin_id_digest=sha256_text("box5-test-administrator"),
        role="admin",
        admin_session_digest=sha256_text("box5-test-administrator-session"),
        auth_method="test_only",
    )
    service_identity = id(api.service)
    api.service.role_registry.remove_member(
        actor=administrator,
        target_admin_id_digest=sha256_text(TEST_SUBJECT),
    )
    response = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=nonce,
    )
    assert response.status_code == 403
    assert response.json()["reason_code"] == "USER_ROLE_NOT_REGISTERED"
    assert id(api.client.app.state.box5_accounting_dependencies.authorization_service) == service_identity
    assert _side_effect_counts(api.runtime) == (0, 0, 0, 0)


def test_submitter_selected_trust_cannot_enable_product_composition(
    authorized_api, monkeypatch
):
    api = authorized_api
    assert api.trust_path.is_file()
    monkeypatch.setattr(authorization_module, "PRODUCT_TRUST_PATH", api.trust_path)
    assert authorization_module.APPROVED_PRODUCTION_TRUST_POLICY_SHA256 is None
    product_service = build_product_authorization_service(api.token_manager)
    assert product_service.authority_available is False
    with pytest.raises(AssignmentError, match="BLOCK_HUMAN_AUTHORITY_UNRESOLVED"):
        product_service.authorize(
            authorization=f"Bearer {api.token}",
            user_authorization=api.assertion(
                "ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_authorization_001"
            ),
            profile=api.profile,
            action="ACCOUNTING_REVIEW_VIEW",
            resource_type="REVIEW_BATCH",
            resource_id="batch_authorization_001",
        )


def test_owner_distribution_stamp_binds_product_policy_without_runtime_input(
    authorized_api, tmp_path: Path, monkeypatch
):
    api = authorized_api
    resources = tmp_path / "Butler.app" / "Contents" / "Resources"
    policy_dir = resources / "box5"
    policy_dir.mkdir(parents=True)
    policy = policy_dir / "authorization-trust-policy-v2.json"
    policy.write_bytes(api.trust_path.read_bytes())
    policy.chmod(0o600)
    digest = hashlib.sha256(policy.read_bytes()).hexdigest()
    helper_digest = "b" * 64
    (resources / "BUILD_INFO.json").write_text(
        json.dumps(
            {
                "distribution": {
                    "schema_version": "butler.build_info.distribution.v1",
                    "release_distribution": True,
                    "not_for_distribution": False,
                    "root_anchor_sha256": "a" * 64,
                },
                "box5_authority": {
                    "bundled": True,
                    "helper_identifier": "com.butler.box5.user-authority.v2",
                    "helper_sha256": helper_digest,
                    "policy_sha256": digest,
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(authorization_module, "_PRODUCT_RESOURCE_ROOT", resources)
    monkeypatch.setattr(authorization_module, "PRODUCT_TRUST_PATH", policy)
    product_service = build_product_authorization_service(api.token_manager)
    assert product_service.authority_available is True


def test_non_app_build_stamp_cannot_select_product_trust(
    authorized_api, tmp_path: Path, monkeypatch
):
    api = authorized_api
    monkeypatch.setattr(authorization_module, "_PRODUCT_RESOURCE_ROOT", tmp_path)
    monkeypatch.setattr(authorization_module, "PRODUCT_TRUST_PATH", api.trust_path)
    assert build_product_authorization_service(api.token_manager).authority_available is False


def test_product_composition_has_one_shared_transport_authenticator(tmp_path: Path):
    parameters = tuple(
        inspect.signature(install_product_accounting_dependencies).parameters
    )
    assert parameters == ("app", "ipc_authenticator")

    app = fastapi.FastAPI()
    token_manager = CapabilityTokenManager(tmp_path / "product-sidecar-token")
    token = token_manager.generate()
    install_product_accounting_dependencies(app, token_manager)
    dependencies = app.state.box5_accounting_dependencies

    assert dependencies.ipc_authenticator is token_manager
    session = dependencies.authorization_service.verify_transport(
        f"Bearer {token}"
    )
    assert session.session_digest == hashlib.sha256(token.encode()).hexdigest()
    assert dependencies.authorization_service.authority_available is False
    with pytest.raises(
        RuntimeError, match="BOX5_ACCOUNTING_DEPENDENCIES_ALREADY_INSTALLED"
    ):
        install_product_accounting_dependencies(app, token_manager)


def test_contract_forgery_inputs_are_not_product_route_dependencies(
    authorized_api, monkeypatch
):
    api = authorized_api
    installer_parameters = set(
        inspect.signature(install_product_accounting_dependencies).parameters
    )
    route_parameters = set(inspect.signature(assign_account).parameters)
    forbidden_dependency_inputs = {
        "verifier",
        "verifier_proof",
        "claims",
        "role",
        "capabilities",
        "capability_session",
        "user_authority",
        "trust_policy",
    }
    assert installer_parameters.isdisjoint(forbidden_dependency_inputs)
    assert route_parameters.isdisjoint(forbidden_dependency_inputs)

    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    before = _side_effect_counts(api.runtime)
    forged = api.client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={
            **api.headers(
                "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "account_id": "POSTING.AUTH",
            "scope": "THIS_ONLY",
            "client_action_id": str(uuid.uuid4()),
            "user_action_nonce": nonce,
            "expected_transaction_version": 1,
            "role": "manager",
            "capabilities": ["ASSIGN_THIS_ONLY", "CREATE_FUTURE_RULE"],
            "verifier_proof": "caller-selected",
        },
    )
    assert forged.status_code == 422
    assert _side_effect_counts(api.runtime) == before

    monkeypatch.setenv("TEST_ROLE_OVERRIDE", "manager")
    monkeypatch.setenv("BUTLER_TEST_ADMIN", "1")
    product_service = build_product_authorization_service(api.token_manager)
    assert product_service.authority_available is False
    with pytest.raises(AssignmentError, match="BLOCK_HUMAN_AUTHORITY_UNRESOLVED"):
        product_service.authorize(
            authorization=f"Bearer {api.token}",
            user_authorization=api.assertion(
                "ACCOUNTING_REVIEW_VIEW", "REVIEW_BATCH", "batch_authorization_001"
            ),
            profile=api.profile,
            action="ACCOUNTING_REVIEW_VIEW",
            resource_type="REVIEW_BATCH",
            resource_id="batch_authorization_001",
        )


def test_production_authorization_import_graph_contains_no_issuer_or_private_key():
    source = Path(authorization_module.__file__).read_text(encoding="utf-8")
    assert "Ed25519PrivateKey" not in source
    assert "authorization_testkit" not in source
    assert "issue_test_assertion" not in source


def test_signed_assertion_replay_is_rejected_without_second_effect(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    key = str(uuid.uuid4())
    client_action_id = str(uuid.uuid4())
    assertion = api.assertion(
        "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id
    )
    first = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=nonce,
        idempotency_key=key,
        client_action_id=client_action_id,
        user_assertion=assertion,
    )
    assert first.status_code == 200
    replay = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=nonce,
        idempotency_key=key,
        client_action_id=client_action_id,
        user_assertion=assertion,
    )
    assert replay.status_code == 409
    assert replay.json()["reason_code"] == "USER_ASSERTION_REPLAYED"
    assert _side_effect_counts(api.runtime)[:3] == (1, 0, 1)


def test_same_assertion_is_blocked_after_authorization_service_restart(
    authorized_api,
):
    api = authorized_api
    txn_id = _transaction_id(api)
    assertion = api.assertion(
        "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id
    )
    first = api.service.authorize(
        authorization=f"Bearer {api.token}",
        user_authorization=assertion,
        profile=api.profile,
        action="ASSIGNMENT_CREATE",
        resource_type="ACCOUNTING_TRANSACTION",
        resource_id=txn_id,
    )
    assert first.authorization_decision_id

    restarted = Box5AuthorizationService(
        ipc_authenticator=api.token_manager,
        user_authority=ExistingUserAuthorizationAuthority(api.trust),
        role_registry=api.service.role_registry,
        replay_store_provider=lambda: api.runtime.authorization_replay_store,
    )
    with pytest.raises(AssignmentError, match="USER_ASSERTION_REPLAYED"):
        restarted.authorize(
            authorization=f"Bearer {api.token}",
            user_authorization=assertion,
            profile=api.profile,
            action="ASSIGNMENT_CREATE",
            resource_type="ACCOUNTING_TRANSACTION",
            resource_id=txn_id,
        )


def test_twenty_identical_product_requests_create_exactly_one_side_effect(
    authorized_api,
):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    key = str(uuid.uuid4())
    client_action_id = str(uuid.uuid4())
    assertion = api.assertion(
        "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id
    )

    def submit(_index: int):
        return _assignment_request(
            api,
            txn_id,
            scope="THIS_ONLY",
            action="ASSIGNMENT_CREATE",
            nonce=nonce,
            idempotency_key=key,
            client_action_id=client_action_id,
            user_assertion=assertion,
        )

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(submit, range(20)))
    statuses = [response.status_code for response in responses]
    assert statuses.count(200) == 1
    assert statuses.count(409) == 19
    assert {
        response.json()["reason_code"]
        for response in responses
        if response.status_code == 409
    } == {"USER_ASSERTION_REPLAYED"}
    assert _side_effect_counts(api.runtime)[:3] == (1, 0, 1)


def test_audit_event_binds_signed_decision_policy_request_nonce_and_session(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    action = "ASSIGNMENT_CREATE"
    nonce = _nonce(api, txn_id, action, "THIS_ONLY")
    assertion = api.assertion(action, "ACCOUNTING_TRANSACTION", txn_id)
    client_action_id = str(uuid.uuid4())
    response = api.client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={
            "Butler-User-Authorization": assertion,
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "account_id": "POSTING.AUTH",
            "scope": "THIS_ONLY",
            "client_action_id": client_action_id,
            "user_action_nonce": nonce,
            "expected_transaction_version": 1,
        },
    )
    assert response.status_code == 200
    with sqlite3.connect(api.runtime.store.path) as conn:
        event = json.loads(
            conn.execute(
                "SELECT payload_json FROM assignment_events WHERE event_type='ASSIGNMENT_CREATED'"
            ).fetchone()[0]
        )
    payload_segment = assertion.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(
        payload_segment + "=" * (-len(payload_segment) % 4)
    ))
    assert event["authorization_decision_id"] == claims["jti"]
    assert event["authorization_policy_digest"] == api.trust.policy_digest
    assert event["authorization_assertion_digest"] == hashlib.sha256(
        assertion.encode("utf-8")
    ).hexdigest()
    assert event["authorization_resource_digest"] == hashlib.sha256(
        txn_id.encode("utf-8")
    ).hexdigest()
    assert event["session_id_digest"] == api.local_session.session_digest
    assert event["action"] == action
    assert event["nonce_digest"] == hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    assert event["request_digest"]

    with sqlite3.connect(api.runtime.store.path) as conn:
        conn.row_factory = sqlite3.Row
        authority_event = dict(conn.execute(
            "SELECT event_id,event_type,actor_id_digest,tenant_digest,company_digest,"
            "ipc_session_digest,authorization_assertion_digest,authorization_decision_id,"
            "policy_version,policy_digest,action,resource_digest,nonce_digest,request_digest,"
            "occurred_epoch_ms,previous_event_hash,event_hash "
            "FROM accounting_authority_bound_events"
        ).fetchone())
    schema_path = (
        Path(authorization_module.__file__).parent
        / "contracts"
        / "authority-bound-event-v2.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    ).validate(authority_event)
    stored_hash = authority_event.pop("event_hash")
    assert stored_hash == hashlib.sha256(
        json.dumps(
            authority_event,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with sqlite3.connect(api.runtime.store.path) as conn:
        conn.row_factory = sqlite3.Row
        audit = dict(conn.execute(
            "SELECT sequence,event_id,observed_at,actor_hash,tenant_id,company_id,"
            "action,resource_hash,decision,reason_code,policy_digest,"
            "assertion_jti_hash,request_id,trace_id,role_registry_version,"
            "before_hash,after_hash,prev_hash,event_hash "
            "FROM accounting_authorization_audit_v2"
        ).fetchone())
    schema = json.loads(
        (Path(authorization_module.__file__).parent / "contracts" /
         "authorization-audit-v2.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(
        {"schema_version": "2.0", **audit}
    )
    verified = verify_database(api.runtime.store.path)
    assert verified["event_count"] == 1
    assert verified["allow_actions"] == ["ASSIGNMENT_CREATE"]


def test_authority_audit_failure_rolls_back_privileged_write(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    with sqlite3.connect(api.runtime.store.path) as conn:
        conn.execute(
            "CREATE TRIGGER force_authority_audit_failure "
            "BEFORE INSERT ON accounting_authorization_audit_v2 "
            "BEGIN SELECT RAISE(ABORT, 'FORCED_AUDIT_FAILURE'); END"
        )
    response = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=nonce,
    )
    assert response.status_code == 503
    assert _side_effect_counts(api.runtime) == (0, 0, 0, 0)


def test_ac11_schema_mismatch_blocks_product_write_and_audits_denial(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    assertion = api.assertion(
        "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id
    )
    replay_table = "accounting_authorization_replay_v2"
    replay_contract = (
        Path(authorization_module.__file__).parent
        / "contracts"
        / "authorization-replay-v2.sql"
    ).read_text(encoding="utf-8")
    weakened_schema = mutation_corpus(replay_contract)["same_columns_no_constraints"]
    with sqlite3.connect(api.runtime.store.path) as connection:
        connection.execute(f"DROP TABLE {replay_table}")
        connection.executescript(weakened_schema)
        audit_before = int(
            connection.execute(
                "SELECT count(*) FROM accounting_authorization_audit_v2"
            ).fetchone()[0]
        )

    business_before = _side_effect_counts(api.runtime)
    response = _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=nonce,
        user_assertion=assertion,
    )

    assert response.status_code == 503
    assert response.json()["reason_code"] == "AUTHORIZATION_REPLAY_STORE_UNAVAILABLE"
    assert _side_effect_counts(api.runtime) == business_before
    with sqlite3.connect(api.runtime.store.path) as connection:
        replay_rows = int(
            connection.execute(f"SELECT count(*) FROM {replay_table}").fetchone()[0]
        )
        denial = connection.execute(
            "SELECT decision,reason_code,before_hash,after_hash "
            "FROM accounting_authorization_audit_v2 ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        audit_after = int(
            connection.execute(
                "SELECT count(*) FROM accounting_authorization_audit_v2"
            ).fetchone()[0]
        )
    assert replay_rows == 0
    assert audit_after == audit_before + 1
    assert denial == (
        "DENY",
        "AUTHORIZATION_REPLAY_STORE_UNAVAILABLE",
        denial[2],
        denial[2],
    )
    print(
        "AC11_PRODUCT_SCHEMA_MISMATCH=BLOCKED BUSINESS_WRITE_DELTA=0 "
        "REPLAY_ROWS=0 DENY_AUDIT_DELTA=1"
    )


@pytest.mark.parametrize(
    ("attack", "expected"),
    [
        ("payload", "AUDIT_EVENT_HASH_MISMATCH"),
        ("delete", "AUDIT_EVENT_MISSING"),
        ("sequence", "AUDIT_SEQUENCE_INVALID"),
        ("insert", "AUDIT_EVENT_HASH_MISMATCH"),
    ],
)
def test_independent_audit_verifier_detects_raw_chain_attacks(
    authorized_api, tmp_path, attack, expected
):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    assert _assignment_request(
        api,
        txn_id,
        scope="THIS_ONLY",
        action="ASSIGNMENT_CREATE",
        nonce=nonce,
    ).status_code == 200
    attacked = tmp_path / f"audit-{attack}.sqlite3"
    with sqlite3.connect(api.runtime.store.path) as source, sqlite3.connect(attacked) as target:
        source.backup(target)
    with sqlite3.connect(attacked) as connection:
        if attack == "payload":
            connection.execute("DROP TRIGGER accounting_authorization_audit_v2_no_update")
            connection.execute(
                "UPDATE accounting_authorization_audit_v2 SET reason_code='FORGED'"
            )
        elif attack == "delete":
            connection.execute("DROP TRIGGER accounting_authorization_audit_v2_no_delete")
            connection.execute("DELETE FROM accounting_authorization_audit_v2")
        elif attack == "sequence":
            connection.execute("DROP TRIGGER accounting_authorization_audit_v2_no_update")
            connection.execute(
                "UPDATE accounting_authorization_audit_v2 SET sequence=2"
            )
        else:
            connection.execute(
                """INSERT INTO accounting_authorization_audit_v2
                   (event_id,observed_at,actor_hash,tenant_id,company_id,action,
                    resource_hash,decision,reason_code,policy_digest,assertion_jti_hash,
                    request_id,trace_id,role_registry_version,before_hash,after_hash,
                    prev_hash,event_hash)
                   SELECT 'ffffffffffffffffffffffffffffffff',observed_at,actor_hash,
                    tenant_id,company_id,action,resource_hash,decision,reason_code,
                    policy_digest,assertion_jti_hash,request_id,trace_id,
                    role_registry_version,before_hash,after_hash,event_hash,?
                   FROM accounting_authorization_audit_v2 WHERE sequence=1""",
                ("f" * 64,),
            )
    with pytest.raises(ValueError, match=expected):
        verify_database(attacked)


def test_caller_cannot_inject_role_capabilities_verifier_or_context(authorized_api):
    api = authorized_api
    txn_id = _transaction_id(api)
    nonce = _nonce(api, txn_id, "ASSIGNMENT_CREATE", "THIS_ONLY")
    response = api.client.post(
        f"/v1/accounting/unaccounted/{txn_id}/assign",
        headers={
            **api.headers(
                "ASSIGNMENT_CREATE", "ACCOUNTING_TRANSACTION", txn_id
            ),
            "Idempotency-Key": str(uuid.uuid4()),
            "If-Match": 'W/"1"',
        },
        json={
            "account_id": "POSTING.AUTH",
            "scope": "THIS_ONLY",
            "client_action_id": str(uuid.uuid4()),
            "user_action_nonce": nonce,
            "expected_transaction_version": 1,
            "role": "admin",
            "capabilities": ["RULE_FUTURE_CREATE"],
            "verifier": "echo",
            "context": {"allowed": True},
        },
    )
    assert response.status_code == 422
    assert _side_effect_counts(api.runtime) == (0, 0, 0, 0)
    forged_transport = LocalIpcSession.from_token("attacker-controlled")
    assert not hasattr(forged_transport, "role")
    assert not hasattr(forged_transport, "actor_id")
