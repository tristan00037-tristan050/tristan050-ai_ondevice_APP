"""Native-bound activation grant and one-shot execution receipt authority."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .contracts import (
    Helper1ContractError,
    canonical_json,
    require_digest,
    require_safe_id,
    require_uuid,
    sha256_bytes,
    validate_no_unknown_keys,
)

_GRANT_KEYS = {
    "schema_version",
    "key_id",
    "subject_commit",
    "subject_tree",
    "workspace_id",
    "generation_id",
    "actions",
    "artifact_digests",
    "not_before_epoch_s",
    "expires_at_epoch_s",
    "grant_nonce_sha256",
    "signature_b64",
}
_RECEIPT_KEYS = {
    "schema_version",
    "key_id",
    "subject_commit",
    "subject_tree",
    "workspace_id",
    "generation_id",
    "request_id",
    "session_digest",
    "action",
    "nonce_digest",
    "answer_sha256",
    "issued_at_epoch_s",
    "expires_at_epoch_s",
    "signature_b64",
}
_ACTIONS = frozenset({"ask", "search", "display"})


class ExecutionAuthorityError(RuntimeError):
    pass


def _decode_signature(value: object) -> bytes:
    if not isinstance(value, str):
        raise ExecutionAuthorityError("EXECUTION_SIGNATURE_INVALID")
    try:
        signature = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ExecutionAuthorityError("EXECUTION_SIGNATURE_INVALID") from exc
    if len(signature) != 64:
        raise ExecutionAuthorityError("EXECUTION_SIGNATURE_INVALID")
    return signature


def _verify_signature(public_key: Ed25519PublicKey, value: Mapping[str, Any]) -> None:
    signature = _decode_signature(value.get("signature_b64"))
    unsigned = {key: item for key, item in value.items() if key != "signature_b64"}
    try:
        public_key.verify(signature, canonical_json(unsigned))
    except InvalidSignature as exc:
        raise ExecutionAuthorityError("EXECUTION_SIGNATURE_INVALID") from exc


def _validate_subject(value: Mapping[str, Any], key_id: str) -> None:
    if value.get("key_id") != key_id:
        raise ExecutionAuthorityError("EXECUTION_KEY_ID_MISMATCH")
    for field in ("subject_commit", "subject_tree"):
        item = value.get(field)
        if (
            not isinstance(item, str)
            or len(item) not in {40, 64}
            or any(character not in "0123456789abcdef" for character in item)
        ):
            raise ExecutionAuthorityError("EXECUTION_SUBJECT_INVALID")


@dataclass(frozen=True)
class StaticActivationGrant:
    key_id: str
    subject_commit: str
    subject_tree: str
    workspace_id: str
    generation_id: str
    actions: tuple[str, ...]
    artifact_digests: tuple[str, ...]
    not_before_epoch_s: int
    expires_at_epoch_s: int
    grant_nonce_sha256: str
    signature_b64: str
    schema_version: str = "butler.helper1.activation-grant.v3"

    @classmethod
    def from_signed_dict(
        cls,
        value: Mapping[str, Any],
        *,
        public_key: Ed25519PublicKey,
        key_id: str,
        clock: Callable[[], float],
    ) -> "StaticActivationGrant":
        validate_no_unknown_keys(value, tuple(_GRANT_KEYS), "ACTIVATION_GRANT_UNKNOWN_FIELD")
        if set(value) != _GRANT_KEYS or value.get("schema_version") != "butler.helper1.activation-grant.v3":
            raise ExecutionAuthorityError("ACTIVATION_GRANT_SCHEMA_INVALID")
        _validate_subject(value, key_id)
        try:
            require_uuid(value.get("workspace_id"), "WORKSPACE_ID_INVALID")
            require_uuid(value.get("generation_id"), "GENERATION_ID_INVALID")
            require_digest(value.get("grant_nonce_sha256"), "GRANT_NONCE_INVALID")
        except Helper1ContractError as exc:
            raise ExecutionAuthorityError(str(exc)) from exc
        actions = value.get("actions")
        artifacts = value.get("artifact_digests")
        if (
            not isinstance(actions, list)
            or not actions
            or any(action not in _ACTIONS for action in actions)
            or len(actions) != len(set(actions))
            or not isinstance(artifacts, list)
            or not artifacts
            or len(artifacts) != len(set(artifacts))
        ):
            raise ExecutionAuthorityError("ACTIVATION_GRANT_SCOPE_INVALID")
        try:
            for digest in artifacts:
                require_digest(digest, "ACTIVATION_ARTIFACT_INVALID")
        except Helper1ContractError as exc:
            raise ExecutionAuthorityError(str(exc)) from exc
        not_before = value.get("not_before_epoch_s")
        expires = value.get("expires_at_epoch_s")
        now = int(clock())
        if (
            type(not_before) is not int
            or type(expires) is not int
            or not not_before <= now < expires
            or expires - not_before > 30 * 24 * 60 * 60
        ):
            raise ExecutionAuthorityError("ACTIVATION_GRANT_NOT_CURRENT")
        _verify_signature(public_key, value)
        return cls(
            key_id=key_id,
            subject_commit=str(value["subject_commit"]),
            subject_tree=str(value["subject_tree"]),
            workspace_id=str(value["workspace_id"]),
            generation_id=str(value["generation_id"]),
            actions=tuple(actions),
            artifact_digests=tuple(artifacts),
            not_before_epoch_s=not_before,
            expires_at_epoch_s=expires,
            grant_nonce_sha256=str(value["grant_nonce_sha256"]),
            signature_b64=str(value["signature_b64"]),
        )


@dataclass(frozen=True)
class ExecutionReceipt:
    key_id: str
    subject_commit: str
    subject_tree: str
    workspace_id: str
    generation_id: str
    request_id: str
    session_digest: str
    action: str
    nonce_digest: str
    answer_sha256: str | None
    issued_at_epoch_s: int
    expires_at_epoch_s: int
    signature_b64: str
    schema_version: str = "butler.helper1.execution-receipt.v3"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "key_id": self.key_id,
            "subject_commit": self.subject_commit,
            "subject_tree": self.subject_tree,
            "workspace_id": self.workspace_id,
            "generation_id": self.generation_id,
            "request_id": self.request_id,
            "session_digest": self.session_digest,
            "action": self.action,
            "nonce_digest": self.nonce_digest,
            "answer_sha256": self.answer_sha256,
            "issued_at_epoch_s": self.issued_at_epoch_s,
            "expires_at_epoch_s": self.expires_at_epoch_s,
            "signature_b64": self.signature_b64,
        }


class NativeReceiptSigner(Protocol):
    def __call__(self, challenge: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass
class NativeExecutionAuthority:
    """Verifies every receipt returned by a native signing authority."""

    public_key_bytes: bytes
    expected_public_key_sha256: str
    signed_activation_grant: Mapping[str, Any]
    native_signer: NativeReceiptSigner
    clock: Callable[[], float] = time.time
    is_production_authority: bool = True

    def __post_init__(self) -> None:
        require_digest(self.expected_public_key_sha256, "EXECUTION_KEY_DIGEST_INVALID")
        if len(self.public_key_bytes) != 32 or not hashlib.sha256(self.public_key_bytes).hexdigest() == self.expected_public_key_sha256:
            raise ExecutionAuthorityError("EXECUTION_TRUST_ROOT_INVALID")
        self._public_key = Ed25519PublicKey.from_public_bytes(self.public_key_bytes)
        self._key_id = self.expected_public_key_sha256
        self.grant = StaticActivationGrant.from_signed_dict(
            self.signed_activation_grant,
            public_key=self._public_key,
            key_id=self._key_id,
            clock=self.clock,
        )
        self._seen_nonces: set[str] = set()
        self._lock = threading.Lock()

    def issue(
        self,
        *,
        request_id: str,
        session_digest: str,
        action: str,
        workspace_id: str,
        generation_id: str,
        answer_sha256: str | None,
    ) -> ExecutionReceipt:
        if action not in self.grant.actions:
            raise ExecutionAuthorityError("EXECUTION_ACTION_NOT_GRANTED")
        if workspace_id != self.grant.workspace_id or generation_id != self.grant.generation_id:
            raise ExecutionAuthorityError("EXECUTION_GENERATION_NOT_GRANTED")
        require_uuid(request_id, "REQUEST_ID_INVALID")
        require_digest(session_digest, "SESSION_DIGEST_INVALID")
        if answer_sha256 is not None:
            require_digest(answer_sha256, "ANSWER_DIGEST_INVALID")
        nonce_digest = sha256_bytes(secrets.token_bytes(32))
        challenge = {
            "schema_version": "butler.helper1.execution-challenge.v3",
            "key_id": self._key_id,
            "subject_commit": self.grant.subject_commit,
            "subject_tree": self.grant.subject_tree,
            "workspace_id": workspace_id,
            "generation_id": generation_id,
            "request_id": request_id,
            "session_digest": session_digest,
            "action": action,
            "nonce_digest": nonce_digest,
            "answer_sha256": answer_sha256,
        }
        value = self.native_signer(challenge)
        if type(value) is not dict or set(value) != _RECEIPT_KEYS:
            raise ExecutionAuthorityError("EXECUTION_RECEIPT_SCHEMA_INVALID")
        for key, expected in challenge.items():
            if key == "schema_version":
                continue
            if value.get(key) != expected:
                raise ExecutionAuthorityError("EXECUTION_RECEIPT_BINDING_INVALID")
        if value.get("schema_version") != "butler.helper1.execution-receipt.v3":
            raise ExecutionAuthorityError("EXECUTION_RECEIPT_SCHEMA_INVALID")
        issued = value.get("issued_at_epoch_s")
        expires = value.get("expires_at_epoch_s")
        now = int(self.clock())
        if type(issued) is not int or type(expires) is not int or not issued <= now < expires or expires - issued > 60:
            raise ExecutionAuthorityError("EXECUTION_RECEIPT_NOT_CURRENT")
        _verify_signature(self._public_key, value)
        with self._lock:
            if nonce_digest in self._seen_nonces:
                raise ExecutionAuthorityError("EXECUTION_RECEIPT_REPLAYED")
            self._seen_nonces.add(nonce_digest)
        return ExecutionReceipt(**value)
