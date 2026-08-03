#!/usr/bin/env python3
"""Protected Helper1 evidence verifier.

This program intentionally has no CLI option for a policy, verifier, evidence
key, or verdict key. Its trust root is the policy file in the protected
default-branch checkout. A successful verdict additionally requires a private
verdict key supplied by a protected CI environment and matching the public key
pinned in that policy.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from helper1_evidence_semantics import EvidenceMeaningError, verify_measurement_artifacts
from helper1_subject_binding import SubjectBindingError, resolve_commit_tree

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.approval_closure import (  # noqa: E402
    ApprovalState,
    EvidenceArtifact,
    REQUIRED_EVIDENCE_ROLES,
    THRESHOLD_POLICY_ROLE,
    evidence_set_sha256,
    evaluate_product_closure,
)
from butler_pc_core.helper1.canonical_json import (  # noqa: E402
    CanonicalJsonError,
    require_canonical_butler_cj1,
)
from butler_pc_core.helper1.execution import (  # noqa: E402
    ExecutionAuthorityError,
    NativeExecutionAuthority,
)
from butler_pc_core.helper1.replay_store import (  # noqa: E402
    PostgreSQLReplayStore,
    ReplayReservationStore,
    ReplayStoreError,
)
from butler_pc_core.helper1.retrieval_policy import (  # noqa: E402
    ProtectedTrustPolicyProvider,
    RetrievalPolicyAuthority,
    RetrievalPolicyAuthorityError,
)

POLICY_PATH = ROOT / "contracts" / "helper1" / "trusted-verifier-policy-v1.json"
APPROVAL_POLICY_PATH = ROOT / "contracts" / "helper1" / "retrieval-approval-trust-policy-v1.json"
APPROVAL_DIRECTORY_NAME = "approval"
ACTIVATION_GRANT_NAME = "ACTIVATION_GRANT.json"
APPROVAL_ROLES = (*REQUIRED_EVIDENCE_ROLES, THRESHOLD_POLICY_ROLE)
LEGACY_APPROVAL_BINDINGS = {
    "A1_STARTUP_COMPOSITION_RECEIPT": "APPROVED_ASSET_CLOSURE.json",
    "A2_SUBJECT_BINDING_RECEIPT": "REAL_ASSET_E2E_RECEIPT.json",
    "A3_EGRESS_OBSERVATION_RECEIPT": "M3_M4_MEASUREMENT.json",
    "A5_PARSER_ISOLATION_RECEIPT": "MACOS_SANDBOX_E2E_RECEIPT.json",
}
POLICY_KEYS = {
    "schema_version",
    "policy_epoch",
    "enabled",
    "repository",
    "producer_workflow_name",
    "producer_workflow_path",
    "handoff_chain_anchor",
    "protected_verifier_sha256",
    "protected_components_sha256",
    "approved_producer_identity",
    "approved_evidence_key_id",
    "approved_verdict_key_id",
    "approved_public_key_b64",
    "approved_public_key_sha256",
    "approved_verdict_public_key_b64",
    "approved_verdict_public_key_sha256",
    "approval_policy_sha256",
    "approved_activation_public_key_b64",
    "approved_activation_public_key_sha256",
    "required_approval_roles",
    "legacy_approval_role_bindings",
    "required_evidence_files",
    "subject_check_name",
    "subject_check_app_slug",
    "subject_check_required",
}
PROTECTED_COMPONENTS = {
    "scripts/ci/helper1_trusted_verifier.py": Path(__file__).resolve(),
    "scripts/ci/helper1_subject_binding.py": ROOT / "scripts/ci/helper1_subject_binding.py",
    "scripts/ci/helper1_evidence_semantics.py": ROOT / "scripts/ci/helper1_evidence_semantics.py",
    "scripts/ci/helper1_postgresql_replay_probe.py": ROOT / "scripts/ci/helper1_postgresql_replay_probe.py",
    "scripts/ci/publish_helper1_subject_check.py": ROOT / "scripts/ci/publish_helper1_subject_check.py",
    "butler_pc_core/helper1/approval_closure.py": ROOT / "butler_pc_core/helper1/approval_closure.py",
    "butler_pc_core/helper1/canonical_json.py": ROOT / "butler_pc_core/helper1/canonical_json.py",
    "butler_pc_core/helper1/execution.py": ROOT / "butler_pc_core/helper1/execution.py",
    "butler_pc_core/helper1/replay_store.py": ROOT / "butler_pc_core/helper1/replay_store.py",
    "butler_pc_core/helper1/retrieval_policy.py": ROOT / "butler_pc_core/helper1/retrieval_policy.py",
}
REPLAY_STORE_FACTORY: Callable[[str], ReplayReservationStore] = PostgreSQLReplayStore
EVIDENCE_KEYS = {
    "schema_version",
    "evidence_type",
    "subject_commit",
    "subject_tree",
    "run_id",
    "producer_identity_digest",
    "produced_at_epoch_s",
    "expires_at_epoch_s",
    "artifact_digests",
    "signing_key_digest",
    "signing_key_id",
    "nonce_digest",
    "measurement_artifacts",
    "signature_b64",
}
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
KEY_ID = re.compile(r"^[a-z0-9][a-z0-9._:/-]{7,127}$")
MAX_JSON_BYTES = 256 * 1024
MAX_ARTIFACT_OBJECT_BYTES = 4 * 1024 * 1024


class VerificationError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def decode_b64(value: object, *, expected_bytes: int, code: str) -> bytes:
    if type(value) is not str:
        raise VerificationError(code)
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise VerificationError(code) from exc
    if len(decoded) != expected_bytes:
        raise VerificationError(code)
    return decoded


def load_object(path: Path, *, code: str) -> dict[str, Any]:
    try:
        info = path.lstat()
        if not path.is_file() or path.is_symlink() or not 0 < info.st_size <= MAX_JSON_BYTES:
            raise VerificationError(code)
        raw = path.read_bytes()
        value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise VerificationError(code) from exc
    if type(value) is not dict:
        raise VerificationError(code)
    return value


def load_policy() -> dict[str, Any]:
    policy = load_object(POLICY_PATH, code="TRUST_POLICY_INVALID")
    if set(policy) != POLICY_KEYS:
        raise VerificationError("TRUST_POLICY_INVALID")
    if (
        policy["schema_version"] != "butler.helper1.trusted-verifier-policy.v1"
        or type(policy["policy_epoch"]) is not int
        or policy["policy_epoch"] < 1
        or type(policy["enabled"]) is not bool
        or type(policy["repository"]) is not str
        or type(policy["producer_workflow_name"]) is not str
        or type(policy["producer_workflow_path"]) is not str
        or type(policy["protected_verifier_sha256"]) is not str
        or SHA256.fullmatch(policy["protected_verifier_sha256"]) is None
        or type(policy["protected_components_sha256"]) is not dict
        or set(policy["protected_components_sha256"]) != set(PROTECTED_COMPONENTS)
        or any(
            type(digest) is not str or SHA256.fullmatch(digest) is None
            for digest in policy["protected_components_sha256"].values()
        )
        or type(policy["approved_producer_identity"]) is not str
        or SHA256.fullmatch(policy["approved_producer_identity"]) is None
        or type(policy["approved_evidence_key_id"]) is not str
        or KEY_ID.fullmatch(policy["approved_evidence_key_id"]) is None
        or type(policy["approved_verdict_key_id"]) is not str
        or KEY_ID.fullmatch(policy["approved_verdict_key_id"]) is None
        or policy["subject_check_name"] != "helper1-v2/protected-verdict"
        or policy["subject_check_app_slug"] != "github-actions"
        or policy["subject_check_required"] is not True
        or type(policy["required_evidence_files"]) is not list
        or len(policy["required_evidence_files"]) != 4
        or len(set(policy["required_evidence_files"])) != 4
        or policy["required_approval_roles"] != list(APPROVAL_ROLES)
        or policy["legacy_approval_role_bindings"] != LEGACY_APPROVAL_BINDINGS
        or not valid_handoff_chain_anchor(policy["handoff_chain_anchor"])
    ):
        raise VerificationError("TRUST_POLICY_INVALID")
    trust_keys = (
        "approved_public_key_b64",
        "approved_public_key_sha256",
        "approved_verdict_public_key_b64",
        "approved_verdict_public_key_sha256",
        "approval_policy_sha256",
        "approved_activation_public_key_b64",
        "approved_activation_public_key_sha256",
    )
    if policy["enabled"]:
        if any(type(policy[key]) is not str or not policy[key] for key in trust_keys):
            raise VerificationError("TRUST_POLICY_INCOMPLETE")
        if SHA256.fullmatch(policy["approval_policy_sha256"]) is None:
            raise VerificationError("TRUST_POLICY_INCOMPLETE")
    elif any(policy[key] is not None for key in trust_keys):
        raise VerificationError("TRUST_POLICY_DISABLED_WITH_MATERIAL")
    return policy


def valid_handoff_chain_anchor(value: object) -> bool:
    if type(value) is not dict or set(value) != {
        "schema_version",
        "chain_id",
        "successor_generation",
        "immediate_predecessor",
        "forbidden_rollback_fixture",
    }:
        return False
    predecessor = value.get("immediate_predecessor")
    rollback = value.get("forbidden_rollback_fixture")
    generation = value.get("successor_generation")
    if (
        value.get("schema_version") != "butler.helper1.handoff-chain-anchor.v1"
        or type(value.get("chain_id")) is not str
        or not value["chain_id"]
        or type(generation) is not int
        or generation < 2
    ):
        return False
    for record in (predecessor, rollback):
        if (
            type(record) is not dict
            or set(record) != {"generation", "package_sha256", "result_tree"}
            or type(record.get("generation")) is not int
            or type(record.get("package_sha256")) is not str
            or HEX_SHA256.fullmatch(record["package_sha256"]) is None
            or type(record.get("result_tree")) is not str
            or GIT_OBJECT.fullmatch(record["result_tree"]) is None
        ):
            return False
    return (
        predecessor["generation"] == generation - 1
        and rollback["generation"] < predecessor["generation"]
        and rollback["package_sha256"] != predecessor["package_sha256"]
        and rollback["result_tree"] != predecessor["result_tree"]
    )


def verify_protected_components(policy: dict[str, Any]) -> None:
    observed: dict[str, str] = {}
    try:
        for name, path in PROTECTED_COMPONENTS.items():
            observed[name] = sha256(path.read_bytes())
    except OSError as exc:
        raise VerificationError("PROTECTED_COMPONENT_UNAVAILABLE") from exc
    if observed != policy["protected_components_sha256"]:
        raise VerificationError("PROTECTED_COMPONENT_DIGEST_MISMATCH")
    if observed["scripts/ci/helper1_trusted_verifier.py"] != policy["protected_verifier_sha256"]:
        raise VerificationError("PROTECTED_VERIFIER_DIGEST_MISMATCH")


def verify_event(event_path: Path, policy: dict[str, Any]) -> tuple[str, str]:
    event = load_object(event_path, code="WORKFLOW_EVENT_INVALID")
    repository = event.get("repository")
    run = event.get("workflow_run")
    if type(repository) is not dict or type(run) is not dict:
        raise VerificationError("WORKFLOW_EVENT_INVALID")
    head_sha = run.get("head_sha")
    if (
        repository.get("full_name") != policy["repository"]
        or run.get("name") != policy["producer_workflow_name"]
        or run.get("path") != policy["producer_workflow_path"]
        or run.get("conclusion") != "success"
        or type(run.get("id")) is not int
        or type(run.get("run_attempt")) is not int
        or type(head_sha) is not str
        or GIT_OBJECT.fullmatch(head_sha) is None
    ):
        raise VerificationError("PRODUCER_WORKFLOW_NOT_APPROVED")
    return head_sha, f"{run['id']}:{run['run_attempt']}"


def verify_artifact_object(root: Path, digest: str) -> None:
    if SHA256.fullmatch(digest) is None:
        raise VerificationError("ARTIFACT_DIGEST_INVALID")
    candidate = root / "objects" / digest.removeprefix("sha256:")
    try:
        info = candidate.lstat()
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or not 0 < info.st_size <= MAX_ARTIFACT_OBJECT_BYTES
        ):
            raise VerificationError("ARTIFACT_OBJECT_MISSING")
        observed = sha256(candidate.read_bytes())
    except OSError as exc:
        raise VerificationError("ARTIFACT_OBJECT_MISSING") from exc
    if observed != digest:
        raise VerificationError("ARTIFACT_OBJECT_DIGEST_MISMATCH")



def verify_evidence(
    path: Path,
    *,
    public_key: Ed25519PublicKey,
    expected_key_digest: str,
    expected_key_id: str,
    expected_producer: str,
    expected_commit: str,
    expected_tree: str,
    expected_run: str,
    artifact_root: Path,
    now: int,
) -> tuple[str, str, str, str]:
    value = load_object(path, code="EVIDENCE_INVALID")
    if set(value) != EVIDENCE_KEYS or value.get("schema_version") != "butler.helper1.product_evidence.v2":
        raise VerificationError("EVIDENCE_SCHEMA_INVALID")
    if value.get("subject_commit") != expected_commit:
        raise VerificationError("EVIDENCE_SUBJECT_MISMATCH")
    if value.get("subject_tree") != expected_tree:
        raise VerificationError("EVIDENCE_SUBJECT_TREE_MISMATCH")
    if value.get("run_id") != expected_run:
        raise VerificationError("EVIDENCE_RUN_MISMATCH")
    if value.get("producer_identity_digest") != expected_producer:
        raise VerificationError("EVIDENCE_PRODUCER_NOT_APPROVED")
    if (
        value.get("signing_key_digest") != expected_key_digest
        or value.get("signing_key_id") != expected_key_id
    ):
        raise VerificationError("EVIDENCE_KEY_NOT_APPROVED")
    produced = value.get("produced_at_epoch_s")
    expires = value.get("expires_at_epoch_s")
    if type(produced) is not int or type(expires) is not int or not produced <= now < expires or expires - produced > 86_400:
        raise VerificationError("EVIDENCE_TIME_INVALID")
    nonce = value.get("nonce_digest")
    if type(nonce) is not str or SHA256.fullmatch(nonce) is None:
        raise VerificationError("EVIDENCE_NONCE_INVALID")
    artifacts = value.get("artifact_digests")
    if type(artifacts) is not list or not artifacts or len(set(artifacts)) != len(artifacts):
        raise VerificationError("EVIDENCE_ARTIFACTS_INVALID")
    for digest in artifacts:
        if type(digest) is not str:
            raise VerificationError("EVIDENCE_ARTIFACTS_INVALID")
        verify_artifact_object(artifact_root, digest)
    evidence_type = value.get("evidence_type")
    if type(evidence_type) is not str:
        raise VerificationError("EVIDENCE_TYPE_INVALID")
    try:
        verify_measurement_artifacts(
            evidence_type,
            value.get("measurement_artifacts"),
            artifacts,
            artifact_root,
        )
    except EvidenceMeaningError as exc:
        raise VerificationError(str(exc)) from exc
    signature = decode_b64(value.get("signature_b64"), expected_bytes=64, code="EVIDENCE_SIGNATURE_INVALID")
    unsigned = {key: item for key, item in value.items() if key != "signature_b64"}
    try:
        public_key.verify(signature, canonical_json(unsigned))
    except InvalidSignature as exc:
        raise VerificationError("EVIDENCE_SIGNATURE_INVALID") from exc
    return evidence_type, str(value["subject_tree"]), nonce, hashlib.sha256(path.read_bytes()).hexdigest()


def _load_raw_file(path: Path, *, maximum: int, code: str) -> bytes:
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or not 0 < info.st_size <= maximum:
            raise VerificationError(code)
        return path.read_bytes()
    except OSError as exc:
        raise VerificationError(code) from exc


def _digest_strings(value: object) -> set[str]:
    if type(value) is str:
        return {value} if HEX_SHA256.fullmatch(value) is not None else set()
    if type(value) is list:
        return set().union(*(_digest_strings(item) for item in value), set())
    if type(value) is dict:
        return set().union(*(_digest_strings(item) for item in value.values()), set())
    return set()


def _load_approval_artifacts(
    approval_root: Path,
    artifact_root: Path,
) -> tuple[tuple[EvidenceArtifact, ...], dict[str, dict[str, Any]], dict[str, bytes]]:
    expected_names = {ACTIVATION_GRANT_NAME}
    for role in APPROVAL_ROLES:
        expected_names.update({f"{role}.envelope.json", f"{role}.payload.json"})
    try:
        info = approval_root.lstat()
        if approval_root.is_symlink() or not approval_root.is_dir() or info.st_mode & 0o002:
            raise VerificationError("APPROVAL_EVIDENCE_INVENTORY_INVALID")
        observed_names = {path.name for path in approval_root.iterdir()}
    except OSError as exc:
        raise VerificationError("APPROVAL_EVIDENCE_INVENTORY_INVALID") from exc
    if observed_names != expected_names:
        raise VerificationError("APPROVAL_EVIDENCE_INVENTORY_INVALID")

    artifacts: list[EvidenceArtifact] = []
    payloads: dict[str, dict[str, Any]] = {}
    raw_files: dict[str, bytes] = {}
    for role in APPROVAL_ROLES:
        envelope_name = f"{role}.envelope.json"
        payload_name = f"{role}.payload.json"
        envelope_raw = _load_raw_file(
            approval_root / envelope_name,
            maximum=MAX_JSON_BYTES,
            code="APPROVAL_EVIDENCE_INVALID",
        )
        payload_raw = _load_raw_file(
            approval_root / payload_name,
            maximum=MAX_JSON_BYTES,
            code="APPROVAL_EVIDENCE_INVALID",
        )
        try:
            payload = require_canonical_butler_cj1(payload_raw)
        except CanonicalJsonError as exc:
            raise VerificationError("APPROVAL_EVIDENCE_INVALID") from exc
        if type(payload) is not dict:
            raise VerificationError("APPROVAL_EVIDENCE_INVALID")
        attachments: list[tuple[str, bytes]] = []
        for digest in sorted(_digest_strings(payload)):
            candidate = artifact_root / "objects" / digest
            if not candidate.exists():
                continue
            raw = _load_raw_file(
                candidate,
                maximum=MAX_ARTIFACT_OBJECT_BYTES,
                code="APPROVAL_ATTACHMENT_INVALID",
            )
            if not hashlib.sha256(raw).hexdigest() == digest:
                raise VerificationError("APPROVAL_ATTACHMENT_INVALID")
            attachments.append((digest, raw))
        artifacts.append(EvidenceArtifact(envelope_raw, payload_raw, tuple(attachments)))
        payloads[role] = payload
        raw_files[envelope_name] = envelope_raw
        raw_files[payload_name] = payload_raw
    raw_files[ACTIVATION_GRANT_NAME] = _load_raw_file(
        approval_root / ACTIVATION_GRANT_NAME,
        maximum=MAX_JSON_BYTES,
        code="ACTIVATION_GRANT_INVALID",
    )
    return tuple(artifacts), payloads, raw_files


def _verify_legacy_approval_bindings(
    payloads: dict[str, dict[str, Any]],
    legacy_digests: dict[str, str],
) -> None:
    for role, filename in LEGACY_APPROVAL_BINDINGS.items():
        payload = payloads.get(role)
        if payload is None or payload.get("measurement_sha256") != legacy_digests.get(filename):
            raise VerificationError("APPROVAL_LEGACY_BINDING_INVALID")


def _replay_store_error_code(error: ReplayStoreError) -> str:
    return {
        "REPLAY_STORE_DSN_INVALID": "APPROVAL_REPLAY_STORE_CONFIGURATION_INVALID",
        "REPLAY_STORE_DNS_RESOLUTION_FAILED": "APPROVAL_REPLAY_STORE_DNS_RESOLUTION_FAILED",
        "REPLAY_STORE_ENDPOINT_FORBIDDEN": "APPROVAL_REPLAY_STORE_ENDPOINT_FORBIDDEN",
        "REPLAY_STORE_ROUTING_ENV_FORBIDDEN": "APPROVAL_REPLAY_STORE_ROUTING_ENV_FORBIDDEN",
        "REPLAY_STORE_DRIVER_UNAVAILABLE": "APPROVAL_REPLAY_STORE_DRIVER_UNAVAILABLE",
        "REPLAY_STORE_CONNECTION_FAILED": "APPROVAL_REPLAY_STORE_CONNECTION_FAILED",
        "REPLAY_STORE_SCHEMA_FAILED": "APPROVAL_REPLAY_STORE_SCHEMA_FAILED",
        "REPLAY_RESERVATION_FAILED": "APPROVAL_REPLAY_STORE_RESERVATION_FAILED",
    }.get(str(error), "APPROVAL_REPLAY_STORE_FAILED")


def _approval_replay_store() -> ReplayReservationStore:
    configured = os.environ.get("HELPER1_APPROVAL_REPLAY_DSN")
    if not configured:
        raise VerificationError("APPROVAL_REPLAY_STORE_UNAVAILABLE")
    try:
        return REPLAY_STORE_FACTORY(configured)
    except ReplayStoreError as exc:
        raise VerificationError(_replay_store_error_code(exc)) from exc


def verify_approval_closure(
    policy: dict[str, Any],
    *,
    artifact_root: Path,
    subject_commit: str,
    subject_tree: str,
    legacy_digests: dict[str, str],
    now: int,
) -> tuple[str, dict[str, str]]:
    policy_raw = _load_raw_file(
        APPROVAL_POLICY_PATH,
        maximum=MAX_JSON_BYTES,
        code="APPROVAL_TRUST_POLICY_INVALID",
    )
    expected_policy = str(policy["approval_policy_sha256"])
    if sha256(policy_raw) != expected_policy:
        raise VerificationError("APPROVAL_TRUST_POLICY_DIGEST_MISMATCH")
    try:
        provider = ProtectedTrustPolicyProvider._from_composition_root_bytes(
            policy_raw,
            expected_policy.removeprefix("sha256:"),
        )
        authority = RetrievalPolicyAuthority.from_composition_root(
            provider,
            _approval_replay_store(),
            lambda: now,
        )
    except RetrievalPolicyAuthorityError as exc:
        raise VerificationError("APPROVAL_TRUST_POLICY_INVALID") from exc
    snapshot = authority.snapshot
    if (
        not snapshot.enabled
        or snapshot.repository != policy["repository"]
        or snapshot.subject is None
        or snapshot.subject.commit_sha != subject_commit
        or snapshot.subject.tree_sha != subject_tree
    ):
        raise VerificationError("APPROVAL_TRUST_POLICY_INCOMPLETE")

    approval_root = artifact_root / APPROVAL_DIRECTORY_NAME
    artifacts, payloads, raw_files = _load_approval_artifacts(approval_root, artifact_root)
    _verify_legacy_approval_bindings(payloads, legacy_digests)
    closure_digest = evidence_set_sha256(artifacts)
    activation_public = decode_b64(
        policy["approved_activation_public_key_b64"],
        expected_bytes=32,
        code="ACTIVATION_TRUST_ROOT_INVALID",
    )
    if sha256(activation_public) != policy["approved_activation_public_key_sha256"]:
        raise VerificationError("ACTIVATION_TRUST_ROOT_INVALID")
    try:
        activation_grant = json.loads(
            raw_files[ACTIVATION_GRANT_NAME],
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        if type(activation_grant) is not dict:
            raise ValueError
        activation = NativeExecutionAuthority(
            public_key_bytes=activation_public,
            expected_public_key_sha256=hashlib.sha256(activation_public).hexdigest(),
            signed_activation_grant=activation_grant,
            native_signer=lambda _: {},
            clock=lambda: now,
        )
        verdict = evaluate_product_closure(authority, activation, artifacts)
    except ReplayStoreError as exc:
        raise VerificationError(_replay_store_error_code(exc)) from exc
    except (ExecutionAuthorityError, RetrievalPolicyAuthorityError, ValueError) as exc:
        raise VerificationError("APPROVAL_CLOSURE_INVALID") from exc
    failure_codes = {failure.code.value for failure in verdict.failures}
    if "EVIDENCE_REPLAY_DETECTED" in failure_codes:
        raise VerificationError("APPROVAL_EVIDENCE_REPLAYED")
    if (
        verdict.state is not ApprovalState.RELEASE_ALLOWED
        or not verdict.release_allowed
        or verdict.verified_roles != tuple(sorted(APPROVAL_ROLES))
        or verdict.evidence_set_sha256 != closure_digest
    ):
        raise VerificationError("APPROVAL_CLOSURE_INVALID")
    return closure_digest, {
        name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(raw_files.items())
    }


def sign_verdict(policy: dict[str, Any], unsigned: dict[str, Any]) -> str:
    private_b64 = os.environ.get("HELPER1_VERDICT_SIGNING_KEY_B64")
    private_bytes = decode_b64(private_b64, expected_bytes=32, code="VERDICT_SIGNING_KEY_UNAVAILABLE")
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    expected_public = decode_b64(
        policy["approved_verdict_public_key_b64"],
        expected_bytes=32,
        code="VERDICT_TRUST_ROOT_INVALID",
    )
    if public_bytes != expected_public or sha256(public_bytes) != policy["approved_verdict_public_key_sha256"]:
        raise VerificationError("VERDICT_TRUST_ROOT_INVALID")
    return base64.b64encode(private_key.sign(canonical_json(unsigned))).decode("ascii")


def write_result(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with temporary.open("x", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    error = "NONE"
    policy: dict[str, Any] | None = None
    subject_commit: str | None = None
    subject_tree: str | None = None
    run_id: str | None = None
    try:
        policy = load_policy()
        verify_protected_components(policy)
        if not policy["enabled"]:
            raise VerificationError("TRUST_POLICY_DISABLED")
        subject_commit, run_id = verify_event(args.event, policy)
        try:
            subject_tree = resolve_commit_tree(ROOT, subject_commit)
        except SubjectBindingError as exc:
            raise VerificationError(str(exc)) from exc
        evidence_key_bytes = decode_b64(
            policy["approved_public_key_b64"], expected_bytes=32, code="EVIDENCE_TRUST_ROOT_INVALID"
        )
        if sha256(evidence_key_bytes) != policy["approved_public_key_sha256"]:
            raise VerificationError("EVIDENCE_TRUST_ROOT_INVALID")
        evidence_key = Ed25519PublicKey.from_public_bytes(evidence_key_bytes)
        expected_files = tuple(policy["required_evidence_files"])
        observed_files = tuple(sorted(path.name for path in args.evidence_dir.iterdir()))
        if observed_files != tuple(sorted(expected_files)):
            raise VerificationError("EVIDENCE_INVENTORY_MISMATCH")
        types: set[str] = set()
        trees: set[str] = set()
        nonces: set[str] = set()
        legacy_digests: dict[str, str] = {}
        for filename in expected_files:
            evidence_type, tree, nonce, raw_digest = verify_evidence(
                args.evidence_dir / filename,
                public_key=evidence_key,
                expected_key_digest=policy["approved_public_key_sha256"],
                expected_key_id=policy["approved_evidence_key_id"],
                expected_producer=policy["approved_producer_identity"],
                expected_commit=subject_commit,
                expected_tree=subject_tree,
                expected_run=run_id,
                artifact_root=args.artifact_root,
                now=int(time.time()),
            )
            types.add(evidence_type)
            trees.add(tree)
            nonces.add(nonce)
            legacy_digests[filename] = raw_digest
        if types != {"APPROVED_ASSET_CLOSURE", "REAL_ASSET_E2E_RECEIPT", "M3_M4_MEASUREMENT", "MACOS_SANDBOX_E2E_RECEIPT"} or trees != {subject_tree} or len(nonces) != 4:
            raise VerificationError("EVIDENCE_CROSS_BINDING_INVALID")
        approval_closure_digest, approval_file_digests = verify_approval_closure(
            policy,
            artifact_root=args.artifact_root,
            subject_commit=subject_commit,
            subject_tree=subject_tree,
            legacy_digests=legacy_digests,
            now=int(time.time()),
        )
        unsigned = {
            "schema_version": "butler.helper1.trusted-verdict.v1",
            "code_pass": True,
            "product_release_allowed": True,
            "runtime_activation_allowed": True,
            "production_claim_allowed": True,
            "subject_commit": subject_commit,
            "subject_tree": subject_tree,
            "producer_run": run_id,
            "policy_epoch": policy["policy_epoch"],
            "verdict_key_id": policy["approved_verdict_key_id"],
            "policy_sha256": sha256(POLICY_PATH.read_bytes()),
            "verifier_sha256": sha256(Path(__file__).read_bytes()),
            "evidence_bundle_sha256": sha256(
                canonical_json(
                    {
                        "legacy": {
                            name: sha256((args.evidence_dir / name).read_bytes())
                            for name in sorted(expected_files)
                        },
                        "approval": approval_file_digests,
                        "approval_closure_sha256": approval_closure_digest,
                    }
                )
            ),
            "issued_at_epoch_s": int(time.time()),
            "error_code": "NONE",
        }
        result = {**unsigned, "signature_b64": sign_verdict(policy, unsigned)}
        write_result(args.output, result)
        print("PRODUCT_RELEASE_ALLOWED=1")
        print("RUNTIME_ACTIVATION_ALLOWED=1")
        print("HELPER1_PRODUCTION_CLAIM_ALLOWED=1")
        print("CODE_PASS=1")
        print("ERROR_CODE=NONE")
        return 0
    except (OSError, KeyError, TypeError, ValueError, VerificationError, ReplayStoreError) as exc:
        if isinstance(exc, VerificationError):
            error = str(exc)
        elif isinstance(exc, ReplayStoreError):
            error = _replay_store_error_code(exc)
        error_code = error if error != "NONE" else "TRUSTED_VERIFIER_FAILED"
        failure = {
            "schema_version": "butler.helper1.trusted-verdict.v1",
            "code_pass": False,
            "product_release_allowed": False,
            "runtime_activation_allowed": False,
            "production_claim_allowed": False,
            "subject_commit": subject_commit,
            "subject_tree": subject_tree,
            "producer_run": run_id,
            "policy_epoch": policy.get("policy_epoch") if policy is not None else None,
            "verdict_key_id": policy.get("approved_verdict_key_id") if policy is not None else None,
            "policy_sha256": sha256(POLICY_PATH.read_bytes()) if POLICY_PATH.is_file() else None,
            "verifier_sha256": sha256(Path(__file__).read_bytes()),
            "evidence_bundle_sha256": None,
            "issued_at_epoch_s": int(time.time()),
            "error_code": error_code,
            "signature_b64": None,
        }
        try:
            write_result(args.output, failure)
        except OSError:
            error_code = "VERDICT_WRITE_FAILED"
        print("PRODUCT_RELEASE_ALLOWED=0")
        print("RUNTIME_ACTIVATION_ALLOWED=0")
        print("HELPER1_PRODUCTION_CLAIM_ALLOWED=0")
        print("CODE_PASS=0")
        print(f"ERROR_CODE={error_code}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
