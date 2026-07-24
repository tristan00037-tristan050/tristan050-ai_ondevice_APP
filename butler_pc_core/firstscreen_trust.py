"""Canonical FirstScreen v2.5 trust and release-policy verifier.

This module is the single Python authority used by product startup observation,
release tooling, and CI.  It deliberately accepts already-read bytes instead of
paths so callers cannot accidentally make a path or environment variable part
of the trust decision.  The bootstrap digest must come from a separately
trusted channel (the signed app binary, a protected workflow, or an installed
consumer policy).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


MAX_DOCUMENT_BYTES = 256 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 16_384
MAX_KEYS = 32
MAX_SIGNATURES = 16
MAX_REVOCATION_ITEMS = 4_096
POLICY_ID = "butler-firstscreen-trust"
DOMAIN_PREFIX = b"BUTLER-FIRSTSCREEN-SIGNED\x00"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_ID_RE = re.compile(r"^ed25519\.[0-9a-f]{64}$")
UTC_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")


class TrustVerificationError(RuntimeError):
    """Fail-closed error carrying only a stable public code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise TrustVerificationError(code)


def _reject_float(_raw: str) -> None:
    _fail("BLOCK_JSON_NUMBER")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("BLOCK_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _check_limits(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail("BLOCK_JSON_RESOURCE_LIMIT")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif not isinstance(current, (str, int, bool, type(None))):
            _fail("BLOCK_JSON_TYPE")


def strict_json_loads(raw: bytes, *, maximum: int = MAX_DOCUMENT_BYTES) -> dict[str, Any]:
    """Decode closed-world JSON, rejecting duplicates and non-integer numbers."""

    if not raw or len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        _fail("BLOCK_JSON_RESOURCE_LIMIT")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except TrustVerificationError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        _fail("BLOCK_JSON_PARSE")
    if not isinstance(value, dict):
        _fail("BLOCK_JSON_OBJECT_REQUIRED")
    _check_limits(value)
    return value


def canonical_json(value: Any) -> bytes:
    """Return the project canonical JSON form (UTF-8, sorted keys, integers only)."""

    _check_limits(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("BLOCK_JSON_CANONICALIZATION")


def _unsigned(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "signatures"}


def canonical_payload(document: Mapping[str, Any]) -> bytes:
    return canonical_json(_unsigned(document))


def document_digest(document: Mapping[str, Any]) -> str:
    """Digest the signed payload, independent of signature ordering."""

    return hashlib.sha256(canonical_payload(document)).hexdigest()


def signature_message(document_type: str, document: Mapping[str, Any]) -> bytes:
    schema = document.get("schema_version")
    if not isinstance(schema, str) or not document_type or "\x00" in document_type:
        _fail("BLOCK_SIGNATURE_DOMAIN")
    try:
        return (
            DOMAIN_PREFIX
            + document_type.encode("ascii", errors="strict")
            + b"\x00"
            + schema.encode("ascii", errors="strict")
            + b"\x00"
            + canonical_payload(document)
        )
    except UnicodeError:
        _fail("BLOCK_SIGNATURE_DOMAIN")


def _exact_keys(value: Mapping[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        _fail(code)


def _string(value: Any, *, minimum: int = 1, maximum: int = 256, code: str) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        _fail(code)
    return value


def _integer(value: Any, *, minimum: int = 0, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(code)
    return value


def _sha256(value: Any, code: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        _fail(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail(code)
    return parsed


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        _fail("BLOCK_TIMEZONE_REQUIRED")
    return current.astimezone(timezone.utc)


def _b64url(value: Any, expected_size: int, code: str) -> bytes:
    if not isinstance(value, str) or "=" in value:
        _fail(code)
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
    except (ValueError, binascii.Error):
        _fail(code)
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != expected_size or canonical != value:
        _fail(code)
    return decoded


def key_id_for_public_key(public_key: bytes) -> str:
    if len(public_key) != 32:
        _fail("BLOCK_PUBLIC_KEY")
    return f"ed25519.{hashlib.sha256(public_key).hexdigest()}"


def _sequence(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    return value


def _unique_strings(value: Any, code: str) -> list[str]:
    values = _sequence(value, code)
    if any(not isinstance(item, str) or not item for item in values) or len(values) != len(set(values)):
        _fail(code)
    return values


def _validate_signatures(value: Any, code: str) -> list[Any]:
    signatures = _sequence(value, code)
    if not signatures or len(signatures) > MAX_SIGNATURES:
        _fail(code)
    # Signature envelopes are deliberately outside the signed payload. Their
    # individual shape/encoding is evaluated by the threshold verifier so one
    # malformed or unknown envelope cannot poison an otherwise valid quorum.
    return signatures


def _validate_root(document: dict[str, Any]) -> None:
    _exact_keys(
        document,
        {
            "schema_version",
            "policy_id",
            "version",
            "expires_at_utc",
            "consistent_snapshot",
            "keys",
            "roles",
            "previous_root_digest",
            "signatures",
        },
        "BLOCK_ROOT_SCHEMA",
    )
    if document["schema_version"] != "butler.firstscreen.root-policy.v1" or document["policy_id"] != POLICY_ID:
        _fail("BLOCK_ROOT_SCHEMA")
    _integer(document["version"], minimum=1, code="BLOCK_ROOT_SCHEMA")
    _utc(document["expires_at_utc"], "BLOCK_ROOT_SCHEMA")
    if document["consistent_snapshot"] is not True:
        _fail("BLOCK_ROOT_SCHEMA")
    keys = document["keys"]
    if not isinstance(keys, dict) or not keys or len(keys) > MAX_KEYS:
        _fail("BLOCK_ROOT_SCHEMA")
    for key_id, key in keys.items():
        if not isinstance(key_id, str) or KEY_ID_RE.fullmatch(key_id) is None or not isinstance(key, dict):
            _fail("BLOCK_ROOT_SCHEMA")
        _exact_keys(key, {"algorithm", "public_key"}, "BLOCK_ROOT_SCHEMA")
        if key["algorithm"] != "ed25519":
            _fail("BLOCK_ROOT_SCHEMA")
        public = _b64url(key["public_key"], 32, "BLOCK_ROOT_SCHEMA")
        if key_id_for_public_key(public) != key_id:
            _fail("BLOCK_ROOT_KEY_ID")
    roles = document["roles"]
    expected_roles = {"root", "risk-decision", "revocation", "release"}
    if not isinstance(roles, dict) or set(roles) != expected_roles:
        _fail("BLOCK_ROOT_SCHEMA")
    for role in roles.values():
        if not isinstance(role, dict):
            _fail("BLOCK_ROOT_SCHEMA")
        _exact_keys(role, {"key_ids", "threshold"}, "BLOCK_ROOT_SCHEMA")
        ids = _unique_strings(role["key_ids"], "BLOCK_ROOT_SCHEMA")
        threshold = _integer(role["threshold"], minimum=1, code="BLOCK_ROOT_SCHEMA")
        if threshold > len(ids) or any(key_id not in keys for key_id in ids):
            _fail("BLOCK_ROOT_SCHEMA")
    previous = document["previous_root_digest"]
    if previous is not None:
        _sha256(previous, "BLOCK_ROOT_SCHEMA")
    _validate_signatures(document["signatures"], "BLOCK_ROOT_SCHEMA")


def _verify_ed25519(public_key: bytes, signature: bytes, message: bytes) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
        return True
    except ImportError:
        _fail("BLOCK_CRYPTO_DEPENDENCY")
    except (InvalidSignature, ValueError):
        return False


@dataclass(frozen=True)
class VerifiedThreshold:
    """The cryptographically verified, eligible signer set for one role.

    This is intentionally not the set of signer ids submitted by the caller.
    Unknown, duplicate, malformed-for-the-role, invalid, and revoked envelopes
    cannot increase the threshold and cannot poison later revocation checks.
    """

    valid_signer_ids: tuple[str, ...]
    valid_signature_count: int
    rejected_envelope_count: int
    payload_digest: str
    role: str
    threshold: int


def _verify_threshold(
    *,
    document_type: str,
    document: Mapping[str, Any],
    keys: Mapping[str, Any],
    role: Mapping[str, Any],
    error_code: str,
    role_name: str | None = None,
    revoked_key_ids: Iterable[str] = (),
) -> VerifiedThreshold:
    allowed = set(role["key_ids"])
    revoked = set(revoked_key_ids)
    valid: set[str] = set()
    rejected = 0
    message = signature_message(document_type, document)
    for envelope in document["signatures"]:
        if not isinstance(envelope, dict) or set(envelope) != {"key_id", "signature"}:
            rejected += 1
            continue
        key_id = envelope.get("key_id")
        signature_text = envelope.get("signature")
        if (
            not isinstance(key_id, str)
            or KEY_ID_RE.fullmatch(key_id) is None
            or not isinstance(signature_text, str)
        ):
            rejected += 1
            continue
        if key_id in valid or key_id not in allowed or key_id in revoked:
            rejected += 1
            continue
        key = keys.get(key_id)
        if not isinstance(key, dict):
            rejected += 1
            continue
        try:
            public = _b64url(key.get("public_key"), 32, error_code)
            signature = _b64url(signature_text, 64, error_code)
        except TrustVerificationError:
            rejected += 1
            continue
        if _verify_ed25519(public, signature, message):
            valid.add(key_id)
        else:
            rejected += 1
    if len(valid) < role["threshold"]:
        _fail(error_code)
    return VerifiedThreshold(
        valid_signer_ids=tuple(sorted(valid)),
        valid_signature_count=len(valid),
        rejected_envelope_count=rejected,
        payload_digest=document_digest(document),
        role=role_name or document_type,
        threshold=role["threshold"],
    )


@dataclass(frozen=True)
class BootstrapRoot:
    policy_digest: str
    minimum_root_version: int = 1
    minimum_revocation_version: int = 1

    def __post_init__(self) -> None:
        _sha256(self.policy_digest, "BLOCK_BOOTSTRAP_ROOT_MISMATCH")
        _integer(self.minimum_root_version, minimum=1, code="BLOCK_BOOTSTRAP_ROOT_MISMATCH")
        _integer(self.minimum_revocation_version, minimum=1, code="BLOCK_BOOTSTRAP_ROOT_MISMATCH")


@dataclass(frozen=True)
class TrustedState:
    root_version: int
    root_digest: str
    revocation_version: int
    revocation_digest: str


@dataclass(frozen=True)
class VerifiedRoot:
    document: Mapping[str, Any]
    digest: str
    valid_signer_ids: tuple[str, ...] = ()

    @property
    def version(self) -> int:
        return int(self.document["version"])


@dataclass(frozen=True)
class VerifiedRevocations:
    document: Mapping[str, Any]
    digest: str
    valid_signer_ids: tuple[str, ...] = ()

    @property
    def version(self) -> int:
        return int(self.document["version"])


@dataclass(frozen=True)
class VerifiedRiskDecision:
    decision_id: str
    root_policy_digest: str
    source_blob_digest: str


def verify_current_root(
    candidate_bytes: bytes,
    *,
    now: datetime | None = None,
    _threshold_error: str = "BLOCK_ROOT_THRESHOLD",
) -> VerifiedRoot:
    """Verify a self-consistent current root; persistence enforces monotonicity."""

    candidate = strict_json_loads(candidate_bytes)
    _validate_root(candidate)
    digest = document_digest(candidate)
    current_time = _now(now)
    if _utc(candidate["expires_at_utc"], "BLOCK_ROOT_SCHEMA") <= current_time:
        _fail("BLOCK_ROOT_EXPIRED")
    verified_threshold = _verify_threshold(
        document_type="root-policy",
        document=candidate,
        keys=candidate["keys"],
        role=candidate["roles"]["root"],
        error_code=_threshold_error,
        role_name="root",
    )
    return VerifiedRoot(
        document=candidate,
        digest=digest,
        valid_signer_ids=verified_threshold.valid_signer_ids,
    )

def load_trusted_root_for_update(candidate_bytes: bytes) -> VerifiedRoot:
    """Load the already-trusted root used only to authenticate exactly N+1.

    TUF root update deliberately ignores expiry of N while verifying the
    N-to-N+1 transition. The candidate/final root is still expiry-checked by
    :func:`verify_current_root`.
    """

    candidate = strict_json_loads(candidate_bytes)
    _validate_root(candidate)
    verified_threshold = _verify_threshold(
        document_type="root-policy",
        document=candidate,
        keys=candidate["keys"],
        role=candidate["roles"]["root"],
        error_code="BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK",
        role_name="root",
    )
    return VerifiedRoot(
        document=candidate,
        digest=document_digest(candidate),
        valid_signer_ids=verified_threshold.valid_signer_ids,
    )


def verify_root_chain(
    bootstrap: BootstrapRoot,
    candidate_bytes: bytes,
    *,
    trusted: VerifiedRoot | None = None,
    now: datetime | None = None,
) -> VerifiedRoot:
    verified = verify_current_root(
        candidate_bytes,
        now=now,
        _threshold_error="BLOCK_ROOT_THRESHOLD" if trusted is None else "BLOCK_ROTATION_NEW_THRESHOLD",
    )
    candidate = verified.document
    digest = verified.digest
    version = candidate["version"]
    if trusted is None:
        if digest != bootstrap.policy_digest or version < bootstrap.minimum_root_version:
            _fail("BLOCK_BOOTSTRAP_ROOT_MISMATCH")
        if candidate["previous_root_digest"] is not None:
            _fail("BLOCK_BOOTSTRAP_ROOT_MISMATCH")
    else:
        if version <= trusted.version:
            _fail("BLOCK_ROOT_ROLLBACK")
        if version != trusted.version + 1:
            _fail("BLOCK_ROOT_VERSION_GAP")
        if candidate["previous_root_digest"] != trusted.digest:
            _fail("BLOCK_ROOT_CHAIN")
        _verify_threshold(
            document_type="root-policy",
            document=candidate,
            keys=trusted.document["keys"],
            role=trusted.document["roles"]["root"],
            error_code="BLOCK_ROTATION_OLD_THRESHOLD",
            role_name="root-old",
        )
    return verified


def _validate_revocations(document: dict[str, Any]) -> None:
    _exact_keys(
        document,
        {
            "schema_version",
            "policy_id",
            "version",
            "generated_at_utc",
            "expires_at_utc",
            "previous_digest",
            "root_policy_digest",
            "revoked_decision_ids",
            "revoked_key_ids",
            "revoked_epochs",
            "signatures",
        },
        "BLOCK_REVOCATION_SCHEMA",
    )
    if document["schema_version"] != "butler.firstscreen.revocations.v2" or document["policy_id"] != POLICY_ID:
        _fail("BLOCK_REVOCATION_SCHEMA")
    _integer(document["version"], minimum=1, code="BLOCK_REVOCATION_SCHEMA")
    _utc(document["generated_at_utc"], "BLOCK_REVOCATION_SCHEMA")
    _utc(document["expires_at_utc"], "BLOCK_REVOCATION_SCHEMA")
    previous = document["previous_digest"]
    if previous is not None:
        _sha256(previous, "BLOCK_REVOCATION_SCHEMA")
    _sha256(document["root_policy_digest"], "BLOCK_REVOCATION_SCHEMA")
    decision_ids = _unique_strings(document["revoked_decision_ids"], "BLOCK_REVOCATION_SCHEMA")
    key_ids = _unique_strings(document["revoked_key_ids"], "BLOCK_REVOCATION_SCHEMA")
    if any(KEY_ID_RE.fullmatch(value) is None for value in key_ids):
        _fail("BLOCK_REVOCATION_SCHEMA")
    epochs = _sequence(document["revoked_epochs"], "BLOCK_REVOCATION_SCHEMA")
    if any(len(items) > MAX_REVOCATION_ITEMS for items in (decision_ids, key_ids, epochs)):
        _fail("BLOCK_REVOCATION_RESOURCE_LIMIT")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in epochs) or len(epochs) != len(set(epochs)):
        _fail("BLOCK_REVOCATION_SCHEMA")
    _validate_signatures(document["signatures"], "BLOCK_REVOCATION_SCHEMA")


def verify_current_revocations(
    root: VerifiedRoot,
    candidate_bytes: bytes,
    *,
    now: datetime | None = None,
) -> VerifiedRevocations:
    """Verify the current signed revocation snapshot without advancing state."""

    document = strict_json_loads(candidate_bytes)
    _validate_revocations(document)
    digest = document_digest(document)
    current_time = _now(now)
    generated = _utc(document["generated_at_utc"], "BLOCK_REVOCATION_SCHEMA")
    expires = _utc(document["expires_at_utc"], "BLOCK_REVOCATION_SCHEMA")
    if generated > current_time or generated >= expires or expires <= current_time:
        _fail("BLOCK_REVOCATION_EXPIRED")
    if document["root_policy_digest"] != root.digest:
        _fail("BLOCK_REVOCATION_ROOT")
    verified_threshold = _verify_threshold(
        document_type="revocations",
        document=document,
        keys=root.document["keys"],
        role=root.document["roles"]["revocation"],
        error_code="BLOCK_REVOCATION_THRESHOLD",
        role_name="revocation",
    )
    return VerifiedRevocations(
        document=document,
        digest=digest,
        valid_signer_ids=verified_threshold.valid_signer_ids,
    )


def verify_revocations(
    root: VerifiedRoot,
    candidate_bytes: bytes,
    *,
    bootstrap: BootstrapRoot,
    current_state: TrustedState | None = None,
    previous: VerifiedRevocations | None = None,
    now: datetime | None = None,
) -> VerifiedRevocations:
    verified = verify_current_revocations(root, candidate_bytes, now=now)
    document = verified.document
    digest = verified.digest
    version = document["version"]
    if current_state is None:
        if version < bootstrap.minimum_revocation_version or document["previous_digest"] is not None:
            _fail("BLOCK_REVOCATION_ROLLBACK")
    else:
        if current_state.root_version != root.version or current_state.root_digest != root.digest:
            _fail("BLOCK_TRUSTED_STATE")
        if version <= current_state.revocation_version:
            _fail("BLOCK_REVOCATION_ROLLBACK")
        if version != current_state.revocation_version + 1:
            _fail("BLOCK_REVOCATION_VERSION_GAP")
        if document["previous_digest"] != current_state.revocation_digest:
            _fail("BLOCK_REVOCATION_CHAIN")
    if previous is not None:
        if previous.digest != document["previous_digest"] or previous.version + 1 != version:
            _fail("BLOCK_REVOCATION_CHAIN")
        for field in ("revoked_decision_ids", "revoked_key_ids", "revoked_epochs"):
            if not set(previous.document[field]).issubset(set(document[field])):
                _fail("BLOCK_REVOCATION_WEAKENED")
    return verified


def _validate_decision(document: dict[str, Any]) -> None:
    _exact_keys(
        document,
        {
            "schema_version",
            "policy_id",
            "decision_id",
            "version",
            "approved_at_utc",
            "expires_at_utc",
            "scope",
            "protection_boundary",
            "data_classification",
            "owner_role",
            "revocation_epoch",
            "root_policy_digest",
            "source_blob_digest",
            "canonical_ssot_location",
            "signatures",
        },
        "BLOCK_DECISION_SCHEMA",
    )
    if document["schema_version"] != "butler.firstscreen.risk-decision.v2" or document["policy_id"] != POLICY_ID:
        _fail("BLOCK_DECISION_SCHEMA")
    _string(document["decision_id"], maximum=128, code="BLOCK_DECISION_SCHEMA")
    _integer(document["version"], minimum=1, code="BLOCK_DECISION_SCHEMA")
    _utc(document["approved_at_utc"], "BLOCK_DECISION_SCHEMA")
    _utc(document["expires_at_utc"], "BLOCK_DECISION_SCHEMA")
    scope = _unique_strings(document["scope"], "BLOCK_DECISION_SCHEMA")
    if set(scope) != {"CONVERSATION_TITLE", "FTS_TITLE_INDEX"}:
        _fail("BLOCK_DECISION_SCOPE")
    boundaries = set(_unique_strings(document["protection_boundary"], "BLOCK_DECISION_SCHEMA"))
    if not {"ON_DEVICE", "OS_USER_BOUNDARY", "APP_DATA_PATH", "OWNER_MODE_GUARD"}.issubset(boundaries):
        _fail("BLOCK_DECISION_SCOPE")
    if document["data_classification"] != "CONFIDENTIAL" or document["owner_role"] != "ATLINK_REPRESENTATIVE":
        _fail("BLOCK_DECISION_SCOPE")
    _integer(document["revocation_epoch"], minimum=0, code="BLOCK_DECISION_SCHEMA")
    _sha256(document["root_policy_digest"], "BLOCK_DECISION_SCHEMA")
    _sha256(document["source_blob_digest"], "BLOCK_DECISION_SCHEMA")
    location = _string(document["canonical_ssot_location"], maximum=512, code="BLOCK_DECISION_SCHEMA")
    path = PurePosixPath(location)
    if path.is_absolute() or ".." in path.parts or "\\" in location or path.as_posix() != location:
        _fail("BLOCK_DECISION_SCHEMA")
    _validate_signatures(document["signatures"], "BLOCK_DECISION_SCHEMA")


def verify_risk_decision(
    root: VerifiedRoot,
    revocations: VerifiedRevocations,
    decision_bytes: bytes,
    *,
    now: datetime | None = None,
) -> VerifiedRiskDecision:
    document = strict_json_loads(decision_bytes)
    _validate_decision(document)
    current_time = _now(now)
    approved = _utc(document["approved_at_utc"], "BLOCK_DECISION_SCHEMA")
    expires = _utc(document["expires_at_utc"], "BLOCK_DECISION_SCHEMA")
    if approved > current_time or approved >= expires or expires <= current_time:
        _fail("BLOCK_DECISION_EXPIRED")
    if document["root_policy_digest"] != root.digest or revocations.document["root_policy_digest"] != root.digest:
        _fail("BLOCK_DECISION_ROOT")
    verified_threshold = _verify_threshold(
        document_type="risk-decision",
        document=document,
        keys=root.document["keys"],
        role=root.document["roles"]["risk-decision"],
        error_code="BLOCK_DECISION_THRESHOLD",
        role_name="risk-decision",
        revoked_key_ids=revocations.document["revoked_key_ids"],
    )
    revoked = revocations.document
    if (
        document["decision_id"] in revoked["revoked_decision_ids"]
        or document["revocation_epoch"] in revoked["revoked_epochs"]
        or set(verified_threshold.valid_signer_ids).intersection(revoked["revoked_key_ids"])
    ):
        _fail("BLOCK_DECISION_REVOKED")
    return VerifiedRiskDecision(
        decision_id=document["decision_id"],
        root_policy_digest=root.digest,
        source_blob_digest=document["source_blob_digest"],
    )


def validate_build_context(document: Mapping[str, Any]) -> None:
    _exact_keys(
        document,
        {
            "schema_version",
            "mode",
            "repository",
            "commit_oid",
            "tree_oid",
            "source_manifest_digest",
            "python_lock_digest",
            "npm_lock_digest",
            "cargo_lock_digest",
            "toolchain_identity",
            "workflow_identity",
            "created_at_utc",
        },
        "BLOCK_BUILD_CONTEXT_SCHEMA",
    )
    if document["schema_version"] != "butler.firstscreen.build-context.v1" or document["mode"] != "production":
        _fail("BLOCK_BUILD_CONTEXT_SCHEMA")
    repository = _string(document["repository"], maximum=160, code="BLOCK_BUILD_CONTEXT_SCHEMA")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        _fail("BLOCK_BUILD_CONTEXT_SCHEMA")
    if not isinstance(document["commit_oid"], str) or re.fullmatch(r"[0-9a-f]{40,64}", document["commit_oid"]) is None:
        _fail("BLOCK_BUILD_CONTEXT_IDENTITY")
    if not isinstance(document["tree_oid"], str) or re.fullmatch(r"[0-9a-f]{40,64}", document["tree_oid"]) is None:
        _fail("BLOCK_BUILD_CONTEXT_IDENTITY")
    for field in ("source_manifest_digest", "python_lock_digest", "npm_lock_digest", "cargo_lock_digest"):
        _sha256(document[field], "BLOCK_BUILD_CONTEXT_SCHEMA")
    _string(document["toolchain_identity"], minimum=8, maximum=512, code="BLOCK_BUILD_CONTEXT_SCHEMA")
    _string(document["workflow_identity"], minimum=8, maximum=256, code="BLOCK_BUILD_CONTEXT_SCHEMA")
    _utc(document["created_at_utc"], "BLOCK_BUILD_CONTEXT_SCHEMA")


def build_context_digest(document: Mapping[str, Any]) -> str:
    validate_build_context(document)
    return hashlib.sha256(canonical_json(document)).hexdigest()


def _validate_subject(subject: Any) -> None:
    if not isinstance(subject, dict):
        _fail("BLOCK_RELEASE_SUBJECTS_SCHEMA")
    _exact_keys(subject, {"name", "size", "sha256", "build_context_digest"}, "BLOCK_RELEASE_SUBJECTS_SCHEMA")
    _string(subject["name"], maximum=200, code="BLOCK_RELEASE_SUBJECTS_SCHEMA")
    _integer(subject["size"], minimum=1, code="BLOCK_RELEASE_SUBJECTS_SCHEMA")
    _sha256(subject["sha256"], "BLOCK_RELEASE_SUBJECTS_SCHEMA")
    _sha256(subject["build_context_digest"], "BLOCK_RELEASE_SUBJECTS_SCHEMA")


def verify_release_subjects(
    root: VerifiedRoot,
    release_bytes: bytes,
    *,
    expected_build_context_digest: str,
    artifacts: Mapping[str, bytes],
    revoked_key_ids: Iterable[str] = (),
    now: datetime | None = None,
) -> Mapping[str, Any]:
    document = strict_json_loads(release_bytes)
    _exact_keys(
        document,
        {"schema_version", "policy_id", "build_context_digest", "subjects", "created_at_utc", "signatures"},
        "BLOCK_RELEASE_SUBJECTS_SCHEMA",
    )
    if document["schema_version"] != "butler.firstscreen.release-subjects.v1" or document["policy_id"] != POLICY_ID:
        _fail("BLOCK_RELEASE_SUBJECTS_SCHEMA")
    if document["build_context_digest"] != _sha256(expected_build_context_digest, "BLOCK_RELEASE_SUBJECTS_SCHEMA"):
        _fail("BLOCK_BUILD_IDENTITY")
    created = _utc(document["created_at_utc"], "BLOCK_RELEASE_SUBJECTS_SCHEMA")
    if created > _now(now):
        _fail("BLOCK_RELEASE_SUBJECTS_SCHEMA")
    subjects = document["subjects"]
    expected_names = {"source_archive", "web_dist_archive", "macos_artifact", "sbom"}
    if not isinstance(subjects, dict) or set(subjects) != expected_names:
        _fail("BLOCK_RELEASE_SUBJECTS_SCHEMA")
    for logical_name, subject in subjects.items():
        _validate_subject(subject)
        if subject["build_context_digest"] != expected_build_context_digest:
            _fail("BLOCK_BUILD_IDENTITY")
        payload = artifacts.get(logical_name)
        if payload is None or len(payload) != subject["size"] or hashlib.sha256(payload).hexdigest() != subject["sha256"]:
            _fail("BLOCK_RELEASE_SUBJECT_MISMATCH")
    _validate_signatures(document["signatures"], "BLOCK_RELEASE_SUBJECTS_SCHEMA")
    _verify_threshold(
        document_type="release-subjects",
        document=document,
        keys=root.document["keys"],
        role=root.document["roles"]["release"],
        error_code="BLOCK_RELEASE_THRESHOLD",
        role_name="release",
        revoked_key_ids=revoked_key_ids,
    )
    return document


def sign_document(document_type: str, document: Mapping[str, Any], private_key: Any, key_id: str) -> dict[str, str]:
    """Signing helper for owner tooling and deterministic test vectors only."""

    if KEY_ID_RE.fullmatch(key_id) is None:
        _fail("BLOCK_SIGNATURE_KEY_ID")
    signature = private_key.sign(signature_message(document_type, document))
    return {
        "key_id": key_id,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def trusted_state(root: VerifiedRoot, revocations: VerifiedRevocations) -> TrustedState:
    return TrustedState(
        root_version=root.version,
        root_digest=root.digest,
        revocation_version=revocations.version,
        revocation_digest=revocations.digest,
    )
