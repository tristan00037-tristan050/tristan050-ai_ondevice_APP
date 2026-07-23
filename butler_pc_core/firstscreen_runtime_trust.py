"""Runtime adapter for the canonical FirstScreen trust authority.

This module turns the already-verified root/revocation/decision/release chain
into one closed-world receipt consumed unchanged by release tooling, the
sidecar/UI, and the native Keychain CAS command.  It never enables runtime
activation; activation remains a separate all-gates release decision.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from butler_pc_core.firstscreen_trust import (
    TrustVerificationError,
    BootstrapRoot,
    build_context_digest,
    canonical_json,
    document_digest,
    strict_json_loads,
    verify_release_subjects,
    verify_current_revocations,
    verify_current_root,
    verify_root_chain,
    verify_risk_decision,
)


DEVELOPMENT_OWNER_FINGERPRINT = "SHA256:8JMrjrlD8gzcIqf6sU+yTzgFjlZ/oJNUWpPLcTC0qa0"
MAX_PIN_BYTES = 4 * 1024
RECEIPT_SCHEMA = "butler.firstscreen.runtime-trust-receipt.v1"
STATE_SCHEMA = "butler.firstscreen.trusted-state.v3"


class RuntimeTrustError(RuntimeError):
    """Fail-closed runtime trust error carrying only a stable public code."""


def _fail(code: str) -> None:
    raise RuntimeTrustError(code)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fingerprint(public_key: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(public_key + "=" * ((4 - len(public_key) % 4) % 4))
    except Exception as exc:
        raise RuntimeTrustError("BLOCK_EXTERNAL_ROOT_PIN") from exc
    if len(raw) != 32:
        _fail("BLOCK_EXTERNAL_ROOT_PIN")
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")


def read_secure_regular_file(
    path: Path,
    *,
    maximum: int,
    application_root: Path | None = None,
) -> bytes:
    """Open, validate, and read one immutable file description.

    No security decision is made from a pre-open ``stat`` followed by a second
    path open.  Identity, ownership, permissions, size and mutation checks all
    refer to the same descriptor.
    """

    if maximum < 1:
        _fail("BLOCK_TRUST_INPUT_OPEN")
    candidate = path.absolute()
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise RuntimeTrustError("BLOCK_TRUST_INPUT_OPEN") from exc
    if application_root is not None:
        try:
            application = application_root.resolve(strict=True)
        except OSError as exc:
            raise RuntimeTrustError("BLOCK_EXTERNAL_ROOT_PIN") from exc
        lexical = resolved_parent / candidate.name
        if lexical == application or application in lexical.parents:
            _fail("BLOCK_ROOT_PIN_INSIDE_BUNDLE")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    try:
        parent_descriptor = os.open(resolved_parent, directory_flags)
        try:
            parent_metadata = os.fstat(parent_descriptor)
            if not stat.S_ISDIR(parent_metadata.st_mode) or parent_metadata.st_mode & 0o022:
                _fail("BLOCK_TRUST_INPUT_METADATA")
            descriptor = os.open(candidate.name, flags, dir_fd=parent_descriptor)
            try:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or not 0 < before.st_size <= maximum
                    or before.st_mode & 0o022
                    or (hasattr(os, "getuid") and before.st_uid != os.getuid())
                ):
                    _fail("BLOCK_TRUST_INPUT_METADATA")
                chunks: list[bytes] = []
                remaining = before.st_size
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 1024 * 1024))
                    if not chunk:
                        _fail("BLOCK_TRUST_INPUT_CHANGED")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1):
                    _fail("BLOCK_TRUST_INPUT_CHANGED")
                after = os.fstat(descriptor)
                identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                if identity_before != identity_after:
                    _fail("BLOCK_TRUST_INPUT_CHANGED")
                return b"".join(chunks)
            finally:
                os.close(descriptor)
        finally:
            os.close(parent_descriptor)
    except RuntimeTrustError:
        raise
    except OSError as exc:
        raise RuntimeTrustError("BLOCK_TRUST_INPUT_OPEN") from exc


def read_external_root_pin(path: Path, *, application_root: Path) -> bytes:
    """Read an owner pin from one secure FD outside the application tree."""

    try:
        return read_secure_regular_file(
            path,
            maximum=MAX_PIN_BYTES,
            application_root=application_root,
        )
    except RuntimeTrustError as exc:
        if exc.args and exc.args[0] == "BLOCK_ROOT_PIN_INSIDE_BUNDLE":
            raise
        raise RuntimeTrustError("BLOCK_EXTERNAL_ROOT_PIN") from exc


def _validate_pin(
    pin_bytes: bytes,
    root_document: Mapping[str, Any],
    *,
    expected_owner_fingerprint: str,
) -> tuple[str, str]:
    pin = strict_json_loads(pin_bytes, maximum=MAX_PIN_BYTES)
    if set(pin) != {"schema_version", "phase", "root_fingerprint"}:
        _fail("BLOCK_EXTERNAL_ROOT_PIN")
    phase = pin.get("phase")
    fingerprint = pin.get("root_fingerprint")
    if (
        pin.get("schema_version") != "butler.firstscreen.external-root-pin.v1"
        or phase not in {"development", "release"}
        or not isinstance(fingerprint, str)
    ):
        _fail("BLOCK_EXTERNAL_ROOT_PIN")
    root_role = root_document.get("roles", {}).get("root", {})
    key_ids = root_role.get("key_ids")
    threshold = root_role.get("threshold")
    keys = root_document.get("keys")
    if not isinstance(key_ids, list) or not isinstance(keys, dict):
        _fail("BLOCK_EXTERNAL_ROOT_PIN")
    fingerprints = {
        _fingerprint(keys[key_id]["public_key"])
        for key_id in key_ids
        if isinstance(key_id, str) and isinstance(keys.get(key_id), dict)
    }
    if fingerprint not in fingerprints:
        _fail("BLOCK_EXTERNAL_ROOT_PIN")
    if phase == "development":
        if fingerprint != expected_owner_fingerprint or threshold != 1 or len(key_ids) != 1:
            _fail("BLOCK_DEVELOPMENT_ROOT_POLICY")
    elif not isinstance(threshold, int) or threshold < 2 or len(key_ids) < 3:
        _fail("BLOCK_RELEASE_ROOT_THRESHOLD")
    return phase, fingerprint


class RuntimeTrustStateStore(Protocol):
    def load(self) -> Mapping[str, Any] | None: ...
    def compare_and_swap(self, expected_digest: str | None, replacement: Mapping[str, Any]) -> bool: ...


@dataclass
class InMemoryRuntimeTrustStateStore:
    """Deterministic CAS used by tests and non-persistent verification tools."""

    value: dict[str, Any] | None = None

    def load(self) -> Mapping[str, Any] | None:
        return None if self.value is None else json.loads(json.dumps(self.value))

    def compare_and_swap(self, expected_digest: str | None, replacement: Mapping[str, Any]) -> bool:
        current = None if self.value is None else _sha256(canonical_json(self.value))
        if current != expected_digest:
            return False
        self.value = json.loads(json.dumps(replacement))
        return True


def _state_digest(state: Mapping[str, Any] | None) -> str | None:
    return None if state is None else _sha256(canonical_json(state))


def _integer(value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail("BLOCK_KEYCHAIN_STATE")
    return value


def _validate_previous_state(state: Mapping[str, Any] | None) -> None:
    if state is None:
        return
    expected = {
        "schema_version", "policy_id", "environment", "generation",
        "current_root", "root_version", "root_digest", "current_revocations", "revocation_version",
        "revocation_digest", "revoked_decision_ids", "revoked_key_ids",
        "revoked_epochs", "valid_root_signer_ids", "valid_revocation_signer_ids",
        "source_commit_oid", "source_tree_oid", "native_build_identity_digest",
        "receipt_version", "receipt_digest", "previous_receipt_digest",
        "binding_digest", "committed_at_utc", "runtime_activation_allowed",
    }
    if (
        set(state) != expected
        or state.get("schema_version") != STATE_SCHEMA
        or state.get("policy_id") != "butler-firstscreen-trust"
        or state.get("environment") not in {"development", "release"}
        or state.get("runtime_activation_allowed") is not False
    ):
        _fail("BLOCK_KEYCHAIN_STATE")
    _integer(state.get("generation"), minimum=1)
    _integer(state.get("root_version"), minimum=1)
    _integer(state.get("revocation_version"), minimum=1)
    _integer(state.get("receipt_version"), minimum=1)
    for field in (
        "root_digest", "revocation_digest", "receipt_digest", "binding_digest",
        "native_build_identity_digest",
    ):
        value = state.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            _fail("BLOCK_KEYCHAIN_STATE")
    for field in ("revoked_decision_ids", "revoked_key_ids", "revoked_epochs"):
        if not isinstance(state.get(field), list):
            _fail("BLOCK_KEYCHAIN_STATE")
    for field in ("valid_root_signer_ids", "valid_revocation_signer_ids"):
        value = state.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            _fail("BLOCK_KEYCHAIN_STATE")
    if not isinstance(state.get("current_root"), dict) or not isinstance(state.get("current_revocations"), dict):
        _fail("BLOCK_KEYCHAIN_STATE")
    if document_digest(state["current_root"]) != state["root_digest"]:
        _fail("BLOCK_KEYCHAIN_STATE")
    if document_digest(state["current_revocations"]) != state["revocation_digest"]:
        _fail("BLOCK_KEYCHAIN_STATE")
    for field in ("source_commit_oid", "source_tree_oid"):
        value = state.get(field)
        if not isinstance(value, str) or len(value) not in {40, 64} or any(c not in "0123456789abcdef" for c in value):
            _fail("BLOCK_KEYCHAIN_STATE")
    previous_receipt = state.get("previous_receipt_digest")
    if previous_receipt is not None and (
        not isinstance(previous_receipt, str)
        or len(previous_receipt) != 64
        or any(c not in "0123456789abcdef" for c in previous_receipt)
    ):
        _fail("BLOCK_KEYCHAIN_STATE")


def _enforce_monotonic(
    previous: Mapping[str, Any] | None,
    *,
    root_document: Mapping[str, Any],
    root_digest: str,
    revocation_document: Mapping[str, Any],
    revocation_digest: str,
) -> None:
    if previous is None:
        if root_document["version"] != 1 or root_document["previous_root_digest"] is not None:
            _fail("BLOCK_ROOT_ROLLBACK")
        if revocation_document["version"] != 1 or revocation_document["previous_digest"] is not None:
            _fail("BLOCK_REVOCATION_ROLLBACK")
        return
    old_root = _integer(previous["root_version"], minimum=1)
    new_root = _integer(root_document["version"], minimum=1)
    if new_root < old_root or (new_root == old_root and root_digest != previous["root_digest"]):
        _fail("BLOCK_ROOT_ROLLBACK")
    if new_root > old_root and (new_root != old_root + 1 or root_document["previous_root_digest"] != previous["root_digest"]):
        _fail("BLOCK_ROOT_CHAIN")
    old_revocation = _integer(previous["revocation_version"], minimum=1)
    new_revocation = _integer(revocation_document["version"], minimum=1)
    if new_revocation < old_revocation or (
        new_revocation == old_revocation and revocation_digest != previous["revocation_digest"]
    ):
        _fail("BLOCK_REVOCATION_ROLLBACK")
    if new_revocation > old_revocation and (
        new_revocation != old_revocation + 1
        or revocation_document["previous_digest"] != previous["revocation_digest"]
    ):
        _fail("BLOCK_REVOCATION_CHAIN")
    for field in ("revoked_decision_ids", "revoked_key_ids", "revoked_epochs"):
        if not set(previous[field]).issubset(set(revocation_document[field])):
            _fail("BLOCK_REVOCATION_WEAKENED")


def verify_and_advance_runtime_trust(
    *,
    root_bytes: bytes,
    revocation_bytes: bytes,
    decision_bytes: bytes,
    build_context_bytes: bytes,
    release_subjects_bytes: bytes,
    artifacts: Mapping[str, bytes],
    external_pin_bytes: bytes,
    store: RuntimeTrustStateStore,
    now: datetime | None = None,
    expected_owner_fingerprint: str = DEVELOPMENT_OWNER_FINGERPRINT,
) -> dict[str, Any]:
    """Verify all product trust inputs and CAS a monotonic runtime receipt."""

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    previous = store.load()
    _validate_previous_state(previous)
    expected_state_digest = _state_digest(previous)
    try:
        root_document = strict_json_loads(root_bytes)
        anchor_document = root_document if previous is None else previous["current_root"]
        phase, fingerprint = _validate_pin(
            external_pin_bytes,
            anchor_document,
            expected_owner_fingerprint=expected_owner_fingerprint,
        )
        root_digest = document_digest(root_document)
        if previous is None:
            root = verify_current_root(root_bytes, now=current_time)
        else:
            trusted_bytes = canonical_json(previous["current_root"])
            trusted_root = verify_current_root(trusted_bytes, now=current_time)
            if trusted_root.digest != previous["root_digest"] or trusted_root.version != previous["root_version"]:
                _fail("BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK")
            if root_document["version"] == trusted_root.version:
                root = verify_current_root(root_bytes, now=current_time)
                if root.digest != trusted_root.digest:
                    _fail("BLOCK_ROOT_ROLLBACK")
            else:
                root = verify_root_chain(
                    BootstrapRoot(trusted_root.digest),
                    root_bytes,
                    trusted=trusted_root,
                    now=current_time,
                )
        revocation_document = strict_json_loads(revocation_bytes)
        revocation_digest = document_digest(revocation_document)
        _enforce_monotonic(
            previous,
            root_document=root_document,
            root_digest=root_digest,
            revocation_document=revocation_document,
            revocation_digest=revocation_digest,
        )
        revocations = verify_current_revocations(root, revocation_bytes, now=current_time)
        decision = verify_risk_decision(root, revocations, decision_bytes, now=current_time)
        context = strict_json_loads(build_context_bytes, maximum=64 * 1024)
        context_digest = build_context_digest(context)
        release = verify_release_subjects(
            root,
            release_subjects_bytes,
            expected_build_context_digest=context_digest,
            artifacts=artifacts,
            revoked_key_ids=revocations.document["revoked_key_ids"],
            now=current_time,
        )
    except TrustVerificationError as exc:
        raise RuntimeTrustError(exc.code) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeTrustError("BLOCK_RUNTIME_TRUST_INPUT") from exc

    release_digest = document_digest(release)
    binding_digest = _sha256(canonical_json({
        "root_digest": root.digest,
        "revocation_digest": revocations.digest,
        "decision_id": decision.decision_id,
        "decision_source_blob_digest": decision.source_blob_digest,
        "build_context_digest": context_digest,
        "release_subjects_digest": release_digest,
        "external_root_fingerprint": fingerprint,
    }))
    receipt_version = root.version * 1_000_000 + revocations.version
    if previous is not None and binding_digest != previous["binding_digest"]:
        if receipt_version <= _integer(previous["receipt_version"], minimum=1):
            _fail("BLOCK_RECEIPT_VERSION_ROLLBACK")
        previous_receipt_digest = previous["receipt_digest"]
    elif previous is not None:
        receipt_version = _integer(previous["receipt_version"], minimum=1)
        previous_receipt_digest = previous["previous_receipt_digest"]
    else:
        previous_receipt_digest = None
    unsigned_receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "VERIFIED",
        "phase": phase,
        "receipt_version": receipt_version,
        "previous_receipt_digest": previous_receipt_digest,
        "root_version": root.version,
        "root_digest": root.digest,
        "revocation_version": revocations.version,
        "revocation_digest": revocations.digest,
        "decision_id": decision.decision_id,
        "decision_source_blob_digest": decision.source_blob_digest,
        "build_context_digest": context_digest,
        "release_subjects_digest": release_digest,
        "external_root_fingerprint": fingerprint,
        "verified_at_utc": release["created_at_utc"],
        "runtime_activation_allowed": False,
    }
    receipt_digest = _sha256(canonical_json(unsigned_receipt))
    receipt = {**unsigned_receipt, "receipt_digest": receipt_digest}
    replacement = {
        "schema_version": STATE_SCHEMA,
        "policy_id": "butler-firstscreen-trust",
        "environment": phase,
        "generation": 1 if previous is None else _integer(previous["generation"], minimum=1) + (
            0 if binding_digest == previous["binding_digest"] else 1
        ),
        "current_root": json.loads(canonical_json(root.document)),
        "root_version": root.version,
        "root_digest": root.digest,
        "current_revocations": json.loads(canonical_json(revocations.document)),
        "revocation_version": revocations.version,
        "revocation_digest": revocations.digest,
        "revoked_decision_ids": list(revocations.document["revoked_decision_ids"]),
        "revoked_key_ids": list(revocations.document["revoked_key_ids"]),
        "revoked_epochs": list(revocations.document["revoked_epochs"]),
        "valid_root_signer_ids": list(root.valid_signer_ids),
        "valid_revocation_signer_ids": list(revocations.valid_signer_ids),
        "source_commit_oid": context["commit_oid"],
        "source_tree_oid": context["tree_oid"],
        "native_build_identity_digest": context_digest,
        "receipt_version": receipt_version,
        "receipt_digest": receipt_digest,
        "previous_receipt_digest": previous_receipt_digest,
        "binding_digest": binding_digest,
        "committed_at_utc": release["created_at_utc"],
        "runtime_activation_allowed": False,
    }
    if not store.compare_and_swap(expected_state_digest, replacement):
        _fail("BLOCK_KEYCHAIN_CAS_CONFLICT")
    return receipt
