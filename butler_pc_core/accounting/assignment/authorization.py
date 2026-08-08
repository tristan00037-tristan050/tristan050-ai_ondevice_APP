"""Fail-closed Box5 user authorization bound to the local IPC session.

The local capability token authenticates only the desktop/sidecar transport.
Human identity and accounting permission come from a separately signed,
resource-bound decision issued by Butler's existing user authority.  Production
code contains no issuer and no private key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
    LocalIpcSession,
)
from butler_pc_core.company_policy.role_registry import (
    RoleRegistryLoadError,
    RoleRegistryStore,
    get_default_role_registry_store,
)

from .domain import AssignmentError, TenantContext, sha256_json
from .authorization_replay import (
    AssertionReplayed,
    AuthorizationReplayRecord,
    AuthorizationReplayStore,
)


TRUST_SCHEMA = "2.0"
ASSERTION_SCHEMA = "2.0"
ASSERTION_TYPE = "BUTLER-UA2"
AUDIENCE = "butler-box5-accounting"
ALGORITHM = "EdDSA"
_PRODUCT_RESOURCE_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_TRUST_PATH = (
    _PRODUCT_RESOURCE_ROOT / "box5" / "authorization-trust-policy-v2.json"
)
# Deliberately unset until the protected product authority supplies and approves
# the exact production trust document. A file placed by the submitter can never
# select its own key: enabling trust requires a reviewed code/build change that
# pins this digest outside that document.
APPROVED_PRODUCTION_TRUST_POLICY_SHA256: str | None = None

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_POLICY_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_SUBJECT = re.compile(r"^[A-Za-z0-9._:@-]{1,128}$")
_BOUND_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SESSION_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{16,128}$")
_RESOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_JTI = re.compile(r"^[A-Fa-f0-9]{32,64}$")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{22,86}$")
_MAX_TRUST_BYTES = 32_768
_MAX_ASSERTION_BYTES = 16_384
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MAX_CLOCK_SKEW_S = 5
_MAX_TOKEN_AGE_S = 300
_ACTIONS = frozenset(
    {
        "ACCOUNTING_REVIEW_VIEW",
        "ASSIGNMENT_CREATE",
        "RULE_FUTURE_CREATE",
        "QUARANTINE_ROW_RECOMPILE",
        "RULE_DEACTIVATE",
        "RULE_APPLICATION_REVERT",
        "CONFLICT_RESOLVE",
    }
)
_PRIVILEGED_ACTIONS = frozenset(_ACTIONS - {"ACCOUNTING_REVIEW_VIEW"})
_ROLE_ACTIONS = {
    "employee": frozenset({"ASSIGNMENT_CREATE"}),
    "manager": _PRIVILEGED_ACTIONS,
    "admin": _PRIVILEGED_ACTIONS,
}
_RESOURCE_TYPES = frozenset(
    {
        "ACCOUNTING_TRANSACTION",
        "QUARANTINED_ROW",
        "LEARNED_RULE",
        "RULE_CONFLICT",
        "REVIEW_BATCH",
    }
)


def _release_bound_product_policy_digest() -> str | None:
    """Resolve only an app-signed distribution stamp, never caller input.

    The source checkout intentionally has no approved digest. During an owner
    distribution build, ``write_build_info.py`` binds the policy and separately
    signed helper bytes into ``Contents/Resources/BUILD_INFO.json`` before the
    entire app is signed. Standalone/dev layouts remain unavailable.
    """

    try:
        resources = _PRODUCT_RESOURCE_ROOT.resolve(strict=True)
        if resources.name != "Resources" or resources.parent.name != "Contents":
            return None
        app = resources.parent.parent
        if app.suffix != ".app":
            return None
        raw = _read_regular(resources / "BUILD_INFO.json", 65_536)
        stamp = _strict_json(raw.rstrip(b"\n"))
        distribution = stamp.get("distribution")
        authority = stamp.get("box5_authority")
        if (
            not isinstance(distribution, dict)
            or set(distribution)
            != {
                "schema_version",
                "release_distribution",
                "not_for_distribution",
                "root_anchor_sha256",
            }
            or distribution.get("schema_version")
            != "butler.build_info.distribution.v1"
            or distribution.get("release_distribution") is not True
            or distribution.get("not_for_distribution") is not False
            or not isinstance(authority, dict)
            or set(authority)
            != {
                "bundled",
                "helper_identifier",
                "helper_sha256",
                "policy_sha256",
            }
            or authority.get("bundled") is not True
            or authority.get("helper_identifier")
            != "com.butler.box5.user-authority.v2"
            or not _DIGEST.fullmatch(str(authority.get("helper_sha256", "")))
            or not _DIGEST.fullmatch(str(authority.get("policy_sha256", "")))
        ):
            return None
        return str(authority["policy_sha256"])
    except (OSError, ValueError, TypeError):
        return None


def _fail(code: str, status: int) -> None:
    safe = {
        "IPC_CREDENTIAL_MISSING": "The local IPC credential is required.",
        "IPC_CREDENTIAL_INVALID": "The local IPC credential is invalid.",
        "USER_ASSERTION_MISSING": "User authorization is required.",
        "USER_ASSERTION_INVALID": "User authorization is invalid.",
        "USER_ASSERTION_EXPIRED": "User authorization has expired.",
        "USER_ASSERTION_REVOKED": "User authorization was revoked.",
        "USER_ASSERTION_WRONG_ISSUER": "User authorization issuer is invalid.",
        "USER_ASSERTION_WRONG_AUDIENCE": "User authorization audience is invalid.",
        "USER_ASSERTION_WRONG_TYPE": "User authorization type is invalid.",
        "AUTHORITY_UNAVAILABLE": "The approved user authority is unavailable.",
        "BLOCK_HUMAN_AUTHORITY_UNRESOLVED": "The product human identity authority is unresolved.",
        "TENANT_COMPANY_MISMATCH": "User authorization does not match the active company.",
        "DEVICE_SESSION_BINDING_MISMATCH": "User authorization does not match this device session.",
        "AUTHORIZATION_RESOURCE_MISMATCH": "User authorization does not match this accounting resource.",
        "USER_ASSERTION_REPLAYED": "User authorization was already consumed.",
        "AUTHORIZATION_REPLAY_STORE_UNAVAILABLE": "The authorization replay store is unavailable.",
        "ADMIN_ROLE_REGISTRY_LOAD_FAILED": "The current role registry could not be verified.",
        "USER_ROLE_NOT_REGISTERED": "The current user has no active accounting role.",
        "USER_ACTION_NOT_PERMITTED": "The current role does not allow this accounting action.",
    }.get(code, "Accounting authorization was denied.")
    raise AssignmentError(code, status, safe)


def _strict_json(raw: bytes) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate key")
            out[key] = value
        return out

    def reject_constant(_: str) -> None:
        raise ValueError("non-finite number")

    def reject_float(_: str) -> None:
        raise ValueError("float forbidden")

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=no_duplicates,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid json") from exc
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    def validate(node: Any) -> None:
        if isinstance(node, float):
            raise ValueError("float forbidden")
        if isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise ValueError("string key required")
                validate(item)
        elif isinstance(node, list):
            for item in node:
                validate(item)

    validate(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _read_regular(path: Path, maximum: int) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 1
            or before.st_size > maximum
            or before.st_mode & 0o022
        ):
            raise OSError("unsafe authority trust policy")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(raw) != before.st_size or len(raw) > maximum or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise OSError("authority trust policy changed while reading")
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _b64url_decode(value: str, *, expected_size: int | None = None) -> bytes:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid base64url")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        raise ValueError("non-canonical base64url")
    if expected_size is not None and len(raw) != expected_size:
        raise ValueError("invalid decoded size")
    return raw


@dataclass(frozen=True, slots=True)
class AuthorizationTrustKey:
    key_id: str
    public_key: bytes
    status: str


@dataclass(frozen=True, slots=True)
class AuthorizationTrustPolicy:
    policy_id: str
    issuer: str
    audience: str
    keys: tuple[AuthorizationTrustKey, ...]
    policy_digest: str
    not_before_epoch_s: int
    not_after_epoch_s: int

    @property
    def policy_version(self) -> int:
        return 2

    @property
    def max_clock_skew_s(self) -> int:
        return _MAX_CLOCK_SKEW_S

    @property
    def max_token_age_s(self) -> int:
        return _MAX_TOKEN_AGE_S

    @property
    def key_id(self) -> str:
        active = tuple(key for key in self.keys if key.status == "ACTIVE")
        if len(active) != 1:
            raise ValueError("one active authorization key required")
        return active[0].key_id

    @property
    def public_key(self) -> bytes:
        return self.key_for_verification(self.key_id).public_key

    def key_for_verification(self, key_id: str) -> AuthorizationTrustKey:
        matches = tuple(key for key in self.keys if key.key_id == key_id)
        if len(matches) != 1:
            raise ValueError("authorization key unavailable")
        return matches[0]


def load_authorization_trust_policy(
    path: Path,
    *,
    now_epoch_s: int,
    expected_policy_digest: str,
    allow_test_policy: bool = False,
) -> AuthorizationTrustPolicy:
    """Load the exact UA2 trust-policy schema under a caller-independent pin.

    ``allow_test_policy`` is retained solely for the named test factory API.
    Trust selection is still determined by the raw-byte digest and fixed path,
    never by a field inside the document.
    """

    try:
        raw = _read_regular(path, _MAX_TRUST_BYTES)
        observed_digest = hashlib.sha256(raw).hexdigest()
        if (
            not _DIGEST.fullmatch(expected_policy_digest)
            or not secrets.compare_digest(observed_digest, expected_policy_digest)
        ):
            raise ValueError("unapproved authority trust policy")
        document = _strict_json(raw.rstrip(b"\n"))
    except (OSError, ValueError):
        _fail("AUTHORITY_UNAVAILABLE", 503)
    required = {
        "schema_version",
        "policy_id",
        "issuer",
        "audience",
        "not_before",
        "expires_at",
        "keys",
    }
    if set(document) != required or raw.rstrip(b"\n") != _canonical(document):
        _fail("AUTHORITY_UNAVAILABLE", 503)
    if (
        document.get("schema_version") != TRUST_SCHEMA
        or document.get("audience") != AUDIENCE
        or not _POLICY_IDENTIFIER.fullmatch(str(document.get("policy_id", "")))
        or not 1 <= len(str(document.get("issuer", ""))) <= 200
    ):
        _fail("AUTHORITY_UNAVAILABLE", 503)
    integer_fields = (document.get("not_before"), document.get("expires_at"))
    if any(type(value) is not int for value in integer_fields):
        _fail("AUTHORITY_UNAVAILABLE", 503)
    not_before, not_after = integer_fields
    if not 0 <= not_before < not_after <= _MAX_SAFE_INTEGER or not (
        not_before <= now_epoch_s < not_after
    ):
        _fail("AUTHORITY_UNAVAILABLE", 503)
    raw_keys = document.get("keys")
    if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= 8:
        _fail("AUTHORITY_UNAVAILABLE", 503)
    keys: list[AuthorizationTrustKey] = []
    seen: set[str] = set()
    try:
        for item in raw_keys:
            if not isinstance(item, dict) or set(item) != {
                "key_id",
                "alg",
                "public_key_b64url",
                "status",
            }:
                raise ValueError("invalid authorization key")
            key_id = str(item.get("key_id", ""))
            status = str(item.get("status", ""))
            if (
                not _POLICY_IDENTIFIER.fullmatch(key_id)
                or key_id in seen
                or item.get("alg") != ALGORITHM
                or status not in {"ACTIVE", "RETIRED_VERIFY_ONLY"}
            ):
                raise ValueError("invalid authorization key")
            public_key = _b64url_decode(
                str(item.get("public_key_b64url", "")), expected_size=32
            )
            seen.add(key_id)
            keys.append(AuthorizationTrustKey(key_id, public_key, status))
    except (TypeError, ValueError):
        _fail("AUTHORITY_UNAVAILABLE", 503)
    if len(tuple(key for key in keys if key.status == "ACTIVE")) != 1:
        _fail("AUTHORITY_UNAVAILABLE", 503)
    return AuthorizationTrustPolicy(
        policy_id=str(document["policy_id"]),
        issuer=str(document["issuer"]),
        audience=AUDIENCE,
        keys=tuple(keys),
        policy_digest=observed_digest,
        not_before_epoch_s=not_before,
        not_after_epoch_s=not_after,
    )


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    decision_id: str
    allowed: bool
    reason_code: str
    actor_id_digest: str
    tenant_id: str
    company_id: str
    action: str
    resource_type: str
    resource_id_digest: str
    policy_version: int
    policy_digest: str
    assertion_digest: str
    ipc_session_digest: str
    device_binding_digest: str
    assertion_nonce_digest: str
    issued_epoch_s: int
    expires_epoch_s: int
    assertion_nonce: str
    authorization_resource: str
    role: str = ""
    role_registry_version: int = 0

    @property
    def decision_digest(self) -> str:
        return sha256_json(
            {
                "decision_id": self.decision_id,
                "allowed": self.allowed,
                "reason_code": self.reason_code,
                "actor_id_digest": self.actor_id_digest,
                "tenant_id": self.tenant_id,
                "company_id": self.company_id,
                "action": self.action,
                "resource_type": self.resource_type,
                "resource_id_digest": self.resource_id_digest,
                "policy_version": self.policy_version,
                "policy_digest": self.policy_digest,
                "assertion_digest": self.assertion_digest,
                "ipc_session_digest": self.ipc_session_digest,
                "device_binding_digest": self.device_binding_digest,
                "assertion_nonce_digest": self.assertion_nonce_digest,
                "issued_epoch_s": self.issued_epoch_s,
                "expires_epoch_s": self.expires_epoch_s,
                "role": self.role,
                "role_registry_version": self.role_registry_version,
            }
        )


def compile_authorization_resource(resource_type: str, resource_id: str) -> str:
    if (
        resource_type not in _RESOURCE_TYPES
        or not _RESOURCE.fullmatch(resource_id)
        or "%" in resource_id
        or "//" in resource_id
        or any(part in {"", ".", ".."} for part in resource_id.split("/"))
    ):
        _fail("AUTHORIZATION_RESOURCE_MISMATCH", 403)
    resource = f"{resource_type}:{resource_id}"
    if not _RESOURCE.fullmatch(resource):
        _fail("AUTHORIZATION_RESOURCE_MISMATCH", 403)
    return resource


class ExistingUserAuthorizationAuthority:
    """Public-key-only verifier for the exact UA2 compact wire contract."""

    def __init__(self, trust: AuthorizationTrustPolicy) -> None:
        self._trust = trust

    @property
    def trust(self) -> AuthorizationTrustPolicy:
        return self._trust

    def verify(
        self,
        raw_assertion: str | None,
        *,
        local_session: LocalIpcSession,
        profile: Any,
        action: str,
        resource_type: str,
        resource_id: str,
        now_epoch_s: int,
    ) -> AuthorizationDecision:
        if action not in _PRIVILEGED_ACTIONS:
            _fail("AUTHORIZATION_RESOURCE_MISMATCH", 403)
        expected_resource = compile_authorization_resource(resource_type, resource_id)
        if not raw_assertion:
            _fail("USER_ASSERTION_MISSING", 401)
        if (
            len(raw_assertion.encode("utf-8")) > _MAX_ASSERTION_BYTES
            or any(ord(char) > 127 or char.isspace() for char in raw_assertion)
        ):
            _fail("USER_ASSERTION_INVALID", 401)
        try:
            protected_segment, payload_segment, signature_segment = raw_assertion.split(
                "."
            )
            protected_raw = _b64url_decode(protected_segment)
            payload_raw = _b64url_decode(payload_segment)
            signature = _b64url_decode(signature_segment, expected_size=64)
            protected = _strict_json(protected_raw)
            claims = _strict_json(payload_raw)
            if protected_raw != _canonical(protected) or payload_raw != _canonical(claims):
                raise ValueError("non-canonical assertion JSON")
        except (UnicodeError, ValueError, TypeError):
            _fail("USER_ASSERTION_INVALID", 401)
        if set(protected) != {"alg", "kid", "typ"}:
            _fail("USER_ASSERTION_INVALID", 401)
        if protected.get("typ") != ASSERTION_TYPE:
            _fail("USER_ASSERTION_WRONG_TYPE", 401)
        if protected.get("alg") != ALGORITHM:
            _fail("USER_ASSERTION_INVALID", 401)
        kid = str(protected.get("kid", ""))
        if not _POLICY_IDENTIFIER.fullmatch(kid):
            _fail("USER_ASSERTION_INVALID", 401)
        expected_fields = {
            "ver",
            "iss",
            "aud",
            "sub",
            "tenant_id",
            "company_id",
            "device_id",
            "session_id",
            "action",
            "resource",
            "iat",
            "nbf",
            "exp",
            "jti",
            "nonce",
            "policy_id",
            "kid",
            "alg",
        }
        if set(claims) != expected_fields or claims.get("ver") != ASSERTION_SCHEMA:
            _fail("USER_ASSERTION_INVALID", 401)
        if claims.get("iss") != self._trust.issuer:
            _fail("USER_ASSERTION_WRONG_ISSUER", 401)
        if claims.get("aud") != self._trust.audience:
            _fail("USER_ASSERTION_WRONG_AUDIENCE", 401)
        if (
            claims.get("alg") != ALGORITHM
            or claims.get("kid") != kid
        ):
            _fail("USER_ASSERTION_INVALID", 401)
        if claims.get("policy_id") != self._trust.policy_id:
            _fail("USER_ASSERTION_REVOKED", 403)
        try:
            key = self._trust.key_for_verification(kid)
            Ed25519PublicKey.from_public_bytes(key.public_key).verify(
                signature,
                (protected_segment + "." + payload_segment).encode("ascii"),
            )
        except (InvalidSignature, UnicodeEncodeError, ValueError, TypeError):
            _fail("USER_ASSERTION_INVALID", 401)
        integers = tuple(claims.get(name) for name in ("iat", "nbf", "exp"))
        if any(type(value) is not int for value in integers):
            _fail("USER_ASSERTION_INVALID", 401)
        issued, not_before, expires = integers
        skew = self._trust.max_clock_skew_s
        if not_before > now_epoch_s + skew or issued > now_epoch_s + skew:
            _fail("USER_ASSERTION_INVALID", 401)
        if expires <= now_epoch_s - skew:
            _fail("USER_ASSERTION_EXPIRED", 401)
        if (
            expires <= issued
            or expires - issued > self._trust.max_token_age_s
            or issued < self._trust.not_before_epoch_s
            or expires > self._trust.not_after_epoch_s
        ):
            _fail("USER_ASSERTION_INVALID", 401)
        decision_id = str(claims.get("jti", ""))
        assertion_nonce = str(claims.get("nonce", ""))
        subject = str(claims.get("sub", ""))
        tenant_id = str(claims.get("tenant_id", ""))
        company_id = str(claims.get("company_id", ""))
        device_id = str(claims.get("device_id", ""))
        session_id = str(claims.get("session_id", ""))
        if (
            not _SUBJECT.fullmatch(subject)
            or not _BOUND_IDENTIFIER.fullmatch(tenant_id)
            or not _BOUND_IDENTIFIER.fullmatch(company_id)
            or not _BOUND_IDENTIFIER.fullmatch(device_id)
            or not _SESSION_IDENTIFIER.fullmatch(session_id)
            or not _JTI.fullmatch(decision_id)
            or not _NONCE.fullmatch(assertion_nonce)
        ):
            _fail("USER_ASSERTION_INVALID", 401)
        profile_tenant = str(getattr(profile, "profile_id", ""))
        profile_company = str(getattr(profile, "profile_digest", ""))
        if tenant_id != profile_tenant or company_id != profile_company:
            _fail("TENANT_COMPANY_MISMATCH", 403)
        if (
            session_id != local_session.session_digest
            or device_id != local_session.device_binding_digest
        ):
            _fail("DEVICE_SESSION_BINDING_MISMATCH", 403)
        if claims.get("action") != action or claims.get("resource") != expected_resource:
            _fail("AUTHORIZATION_RESOURCE_MISMATCH", 403)
        actor_digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        expected_resource_digest = hashlib.sha256(resource_id.encode("utf-8")).hexdigest()
        return AuthorizationDecision(
            decision_id=decision_id,
            allowed=True,
            reason_code="ALLOW",
            actor_id_digest=actor_digest,
            tenant_id=profile_tenant,
            company_id=profile_company,
            action=action,
            resource_type=resource_type,
            resource_id_digest=expected_resource_digest,
            policy_version=self._trust.policy_version,
            policy_digest=self._trust.policy_digest,
            assertion_digest=hashlib.sha256(raw_assertion.encode("ascii")).hexdigest(),
            ipc_session_digest=local_session.session_digest,
            device_binding_digest=local_session.device_binding_digest,
            assertion_nonce_digest=hashlib.sha256(
                assertion_nonce.encode("ascii")
            ).hexdigest(),
            issued_epoch_s=issued,
            expires_epoch_s=expires,
            assertion_nonce=assertion_nonce,
            authorization_resource=expected_resource,
        )


class Box5AuthorizationService:
    """Composition-bound verification of IPC and human authorization."""

    def __init__(
        self,
        *,
        ipc_authenticator: CapabilityTokenManager,
        user_authority: ExistingUserAuthorizationAuthority | None,
        role_registry: RoleRegistryStore,
        replay_store_provider: Callable[[], AuthorizationReplayStore] | None,
    ) -> None:
        self._ipc_authenticator = ipc_authenticator
        self._user_authority = user_authority
        self._role_registry = role_registry
        self._replay_store_provider = replay_store_provider

    @property
    def authority_available(self) -> bool:
        return self._user_authority is not None

    @property
    def role_registry(self) -> RoleRegistryStore:
        return self._role_registry

    @property
    def audit_policy_digest(self) -> str:
        if self._user_authority is not None:
            return self._user_authority.trust.policy_digest
        return hashlib.sha256(b"NO_APPROVED_PRODUCTION_AUTHORITY").hexdigest()

    def verify_transport(self, authorization: str | None) -> LocalIpcSession:
        try:
            return self._ipc_authenticator.verify_authorization_header(authorization)
        except CapabilityTokenError as exc:
            code = "IPC_CREDENTIAL_MISSING" if "MISSING" in exc.fail_class.value else "IPC_CREDENTIAL_INVALID"
            _fail(code, 401)

    def authorize(
        self,
        *,
        authorization: str | None,
        user_authorization: str | None,
        profile: Any,
        action: str,
        resource_type: str,
        resource_id: str,
        request_id: str | None = None,
        now_epoch_s: int | None = None,
    ) -> TenantContext:
        local_session = self.verify_transport(authorization)
        if profile is None or getattr(profile, "status", None) != "ACTIVE":
            raise AssignmentError(
                "BLOCK_SECURE_TRANSACTION_PROJECTION_UNAVAILABLE",
                503,
                "An active company profile is required for accounting review.",
            )
        if self._user_authority is None:
            _fail("BLOCK_HUMAN_AUTHORITY_UNRESOLVED", 503)
        observed_now = (
            now_epoch_s
            if now_epoch_s is not None
            else int(datetime.now(timezone.utc).timestamp())
        )
        decision = self._user_authority.verify(
            user_authorization,
            local_session=local_session,
            profile=profile,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            now_epoch_s=observed_now,
        )
        if action in _PRIVILEGED_ACTIONS:
            registry_digest = "sha256:" + decision.actor_id_digest
            try:
                entry = self._role_registry.lookup_active(registry_digest)
            except RoleRegistryLoadError:
                _fail("ADMIN_ROLE_REGISTRY_LOAD_FAILED", 503)
            if entry is None:
                _fail("USER_ROLE_NOT_REGISTERED", 403)
            if action not in _ROLE_ACTIONS.get(entry.role, frozenset()):
                _fail("USER_ACTION_NOT_PERMITTED", 403)
            decision = AuthorizationDecision(
                **{
                    field: getattr(decision, field)
                    for field in decision.__dataclass_fields__
                    if field not in {"role", "role_registry_version"}
                },
                role=entry.role,
                role_registry_version=entry.version,
            )
            if self._replay_store_provider is None:
                _fail("AUTHORIZATION_REPLAY_STORE_UNAVAILABLE", 503)
            try:
                replay_store = self._replay_store_provider()
                replay_store.consume_once(
                    AuthorizationReplayRecord(
                        policy_digest=decision.policy_digest,
                        jti=decision.decision_id,
                        nonce=decision.assertion_nonce,
                        tenant_id=decision.tenant_id,
                        session_id=decision.ipc_session_digest,
                        action=decision.action,
                        resource=decision.authorization_resource,
                        expires_at=decision.expires_epoch_s,
                        consumed_at=observed_now,
                    )
                )
            except AssertionReplayed:
                _fail("USER_ASSERTION_REPLAYED", 409)
            except Exception:
                _fail("AUTHORIZATION_REPLAY_STORE_UNAVAILABLE", 503)
        tenant_id = str(profile.profile_id)
        tenant_digest = hashlib.sha256(
            (tenant_id + ":" + str(profile.profile_digest)).encode("utf-8")
        ).hexdigest()
        actor_id = "actor_" + decision.actor_id_digest[:32]
        return TenantContext(
            tenant_id=tenant_id,
            tenant_digest=tenant_digest,
            actor_id=actor_id,
            actor_id_digest=decision.actor_id_digest,
            session_id_digest=decision.ipc_session_digest,
            device_id_digest=decision.device_binding_digest,
            permission_decision_digest=decision.decision_digest,
            permission_policy_version=f"authority-policy.{decision.policy_version}",
            action=decision.action,
            authorization_decision_id=decision.decision_id,
            authorization_policy_version=decision.policy_version,
            authorization_policy_digest=decision.policy_digest,
            authorization_assertion_digest=decision.assertion_digest,
            authorization_resource_digest=decision.resource_id_digest,
            authorization_role=decision.role,
            role_registry_version=decision.role_registry_version,
            authorization_company_id=decision.company_id,
            request_id=request_id or decision.decision_id,
        )


def build_product_authorization_service(
    token_manager: CapabilityTokenManager,
) -> Box5AuthorizationService:
    """Build the immutable production composition; missing trust stays closed."""

    authority: ExistingUserAuthorizationAuthority | None = None
    approved_digest = (
        APPROVED_PRODUCTION_TRUST_POLICY_SHA256
        or _release_bound_product_policy_digest()
    )
    if isinstance(approved_digest, str) and _DIGEST.fullmatch(approved_digest):
        try:
            trust = load_authorization_trust_policy(
                PRODUCT_TRUST_PATH,
                now_epoch_s=int(datetime.now(timezone.utc).timestamp()),
                expected_policy_digest=approved_digest,
                allow_test_policy=False,
            )
            authority = ExistingUserAuthorizationAuthority(trust)
        except AssignmentError:
            authority = None
    def product_replay_store() -> AuthorizationReplayStore:
        # Lazy import prevents sidecar startup from creating the accounting DB;
        # the provider still resolves only the one canonical product runtime.
        from .runtime import get_accounting_review_runtime

        return get_accounting_review_runtime().authorization_replay_store

    return Box5AuthorizationService(
        ipc_authenticator=token_manager,
        user_authority=authority,
        role_registry=get_default_role_registry_store(),
        replay_store_provider=product_replay_store,
    )
