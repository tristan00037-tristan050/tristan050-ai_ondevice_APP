"""Test-only signed authority used by product-route authorization tests."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI

from butler_pc_core.accounting.assignment.authorization import (
    ASSERTION_SCHEMA,
    ASSERTION_TYPE,
    AUDIENCE,
    TRUST_SCHEMA,
    AuthorizationTrustPolicy,
    Box5AuthorizationService,
    ExistingUserAuthorizationAuthority,
    load_authorization_trust_policy,
)
from butler_pc_core.accounting.assignment.authorization_replay import (
    AuthorizationReplayStore,
)
from butler_pc_core.accounting.assignment.router import (
    AccountingAssignmentDependencies,
    router as accounting_assignment_router,
)
from butler_pc_core.accounting.assignment.runtime import AccountingReviewRuntime
from butler_pc_core.auth.capability_token import CapabilityTokenManager
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore


TEST_SUBJECT = "subject-test-accounting-001"


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def make_test_authority(
    root: Path,
    token_manager: CapabilityTokenManager,
    replay_store: AuthorizationReplayStore,
) -> tuple[Box5AuthorizationService, Ed25519PrivateKey, AuthorizationTrustPolicy]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    now = int(time.time())
    policy = {
        "schema_version": TRUST_SCHEMA,
        "policy_id": "BOX5-TEST-UA2-POLICY",
        "issuer": "butler.test.user-authority",
        "audience": AUDIENCE,
        "not_before": now - 60,
        "expires_at": now + 3600,
        "keys": [
            {
                "key_id": "box5-test-key-20260803",
                "alg": "EdDSA",
                "public_key_b64url": _b64url(public_key),
                "status": "ACTIVE",
            }
        ],
    }
    path = root / "authorization-trust.test.json"
    path.write_bytes(_canonical(policy) + b"\n")
    path.chmod(0o600)
    trust = load_authorization_trust_policy(
        path,
        now_epoch_s=now,
        expected_policy_digest=hashlib.sha256(path.read_bytes()).hexdigest(),
        allow_test_policy=True,
    )
    role_registry = RoleRegistryStore(root=root / "role-registry")
    administrator = AdminContext(
        admin_id_digest=sha256_text("box5-test-administrator"),
        role="admin",
        admin_session_digest=sha256_text("box5-test-administrator-session"),
        auth_method="test_only",
    )
    role_registry.bootstrap_self_admin(administrator)
    role_registry.upsert_member(
        actor=administrator,
        target_admin_id_digest=sha256_text(TEST_SUBJECT),
        role="manager",
    )
    return (
        Box5AuthorizationService(
            ipc_authenticator=token_manager,
            user_authority=ExistingUserAuthorizationAuthority(trust),
            role_registry=role_registry,
            replay_store_provider=lambda: replay_store,
        ),
        private_key,
        trust,
    )


def make_authorized_test_app(
    *,
    token_manager: CapabilityTokenManager,
    authorization_service: Box5AuthorizationService,
    profile_store_factory: Callable[[], Any],
    runtime: AccountingReviewRuntime,
) -> FastAPI:
    """Build an isolated test composition without mutating product globals."""

    app = FastAPI()
    app.state.box5_accounting_dependencies = AccountingAssignmentDependencies(
        ipc_authenticator=token_manager,
        authorization_service=authorization_service,
        profile_store_factory=profile_store_factory,
        runtime_provider=lambda: runtime,
    )
    app.include_router(accounting_assignment_router)
    return app


def issue_test_assertion(
    private_key: Ed25519PrivateKey,
    trust: AuthorizationTrustPolicy,
    *,
    local_session: Any,
    profile: Any,
    action: str,
    resource_type: str,
    resource_id: str,
    overrides: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    subject = TEST_SUBJECT
    claims: dict[str, Any] = {
        "ver": ASSERTION_SCHEMA,
        "iss": trust.issuer,
        "aud": trust.audience,
        "sub": subject,
        "tenant_id": str(profile.profile_id),
        "company_id": str(profile.profile_digest),
        "device_id": local_session.device_binding_digest,
        "session_id": local_session.session_digest,
        "action": action,
        "resource": f"{resource_type}:{resource_id}",
        "iat": now,
        "nbf": now - 1,
        "exp": now + 120,
        "jti": secrets.token_hex(32),
        "nonce": secrets.token_urlsafe(32),
        "policy_id": trust.policy_id,
        "kid": trust.key_id,
        "alg": "EdDSA",
    }
    protected_overrides = {
        key: value for key, value in (overrides or {}).items() if key == "typ"
    }
    claims.update(
        {key: value for key, value in (overrides or {}).items() if key != "typ"}
    )
    protected = {"alg": "EdDSA", "kid": trust.key_id, "typ": ASSERTION_TYPE}
    protected.update(protected_overrides)
    protected_segment = _b64url(_canonical(protected))
    payload_segment = _b64url(_canonical(claims))
    signing_input = (protected_segment + "." + payload_segment).encode("ascii")
    signature_segment = _b64url(private_key.sign(signing_input))
    return protected_segment + "." + payload_segment + "." + signature_segment
