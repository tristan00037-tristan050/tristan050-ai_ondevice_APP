from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_sha256, read_json_closed, sha256_file
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POLICY_KEYS = {
    "schema_version", "mode", "certificate_oidc_issuer", "certificate_identity",
    "repository", "workflow", "ref", "commit_sha", "subject_name", "subject_sha256",
    "trusted_root_source", "expiry_utc",
}


@dataclass(frozen=True, slots=True)
class TrustPolicy:
    payload: dict[str, Any]
    digest: str


def load_trust_policy(path: Path, *, expected_sha256: str, now: datetime | None = None) -> TrustPolicy:
    if not _SHA256.fullmatch(expected_sha256):
        _block("EXPECTED_TRUST_DIGEST")
    value = read_json_closed(path)
    if not isinstance(value, dict) or set(value) != _POLICY_KEYS:
        _block("TRUST_POLICY_KEYS")
    if value["schema_version"] != "butler.model-tier-b.trust-policy.v2.8":
        _block("TRUST_POLICY_VERSION")
    for key, item in value.items():
        if isinstance(item, str) and (item.strip().upper() == "UNSET" or not item.strip() or "*" in item or "?" in item):
            _block(f"TRUST_{key.upper()}")
    if value["mode"] not in {"keyless", "key", "kms"}:
        _block("TRUST_MODE")
    if value["subject_name"] != "release.tar.gz" or not _SHA256.fullmatch(value["subject_sha256"]):
        _block("TRUST_SUBJECT")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value["commit_sha"]):
        _block("TRUST_COMMIT")
    _validate_expiry(value["expiry_utc"], now=now)
    digest = canonical_sha256(value)
    if digest != expected_sha256:
        raise GateError(FailClass.POLICY_TRUST, "TRUST_DIGEST_MISMATCH", exit_code=ExitCode.DIGEST)
    return TrustPolicy(value, digest)


def verify_in_toto_statement(statement_path: Path, payload: Path, policy: TrustPolicy) -> str:
    statement = read_json_closed(statement_path)
    required = {"_type", "subject", "predicateType", "predicate"}
    if not isinstance(statement, dict) or set(statement) != required:
        raise GateError(FailClass.ATTESTATION, "STATEMENT_KEYS", exit_code=ExitCode.SCHEMA)
    if statement["_type"] != "https://in-toto.io/Statement/v1":
        raise GateError(FailClass.ATTESTATION, "STATEMENT_TYPE", exit_code=ExitCode.SCHEMA)
    subjects = statement["subject"]
    expected = [{"name": "release.tar.gz", "digest": {"sha256": sha256_file(payload)}}]
    if subjects != expected or subjects[0]["digest"]["sha256"] != policy.payload["subject_sha256"]:
        raise GateError(FailClass.ATTESTATION, "ATTESTATION_SUBJECT", exit_code=ExitCode.DIGEST)
    predicate = statement["predicate"]
    required_predicate = {"repository", "workflow", "ref", "commit_sha", "policy_sha256", "ci_artifact_sha256"}
    if not isinstance(predicate, dict) or set(predicate) != required_predicate:
        raise GateError(FailClass.ATTESTATION, "PREDICATE_KEYS", exit_code=ExitCode.SCHEMA)
    for key in ("repository", "workflow", "ref", "commit_sha"):
        if predicate[key] != policy.payload[key]:
            raise GateError(FailClass.ATTESTATION, f"PREDICATE_{key.upper()}", exit_code=ExitCode.DIGEST)
    for key in ("policy_sha256", "ci_artifact_sha256"):
        if not isinstance(predicate[key], str) or not _SHA256.fullmatch(predicate[key]):
            raise GateError(FailClass.ATTESTATION, f"PREDICATE_{key.upper()}", exit_code=ExitCode.SCHEMA)
    return canonical_sha256(statement)


def replay_sigstore_verification(
    *,
    cosign_binary: Path,
    expected_cosign_sha256: str,
    payload: Path,
    bundle: Path,
    statement: Path,
    policy: TrustPolicy,
    timeout_seconds: int = 60,
) -> dict[str, str]:
    """Replay the signature of an in-toto statement with pinned cosign.

    No shell is used, no network option is added, and a missing executable is a
    hard block.  The caller must provide a bundle containing inclusion proof.
    """

    if sha256_file(cosign_binary) != expected_cosign_sha256:
        raise GateError(FailClass.ATTESTATION, "COSIGN_BINARY_DIGEST", exit_code=ExitCode.DIGEST)
    verify_in_toto_statement(statement, payload, policy)
    mode = policy.payload["mode"]
    # The statement is signed as an ordinary blob.  Its subject is bound to the
    # immutable release payload above, before cosign is invoked.
    command = [str(cosign_binary), "verify-blob", str(statement), "--bundle", str(bundle)]
    if mode == "keyless":
        command.extend([
            "--certificate-identity", policy.payload["certificate_identity"],
            "--certificate-oidc-issuer", policy.payload["certificate_oidc_issuer"],
        ])
    else:
        command.extend(["--key", policy.payload["trusted_root_source"]])
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
            env={"PATH": "", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        raise GateError(FailClass.ATTESTATION, "COSIGN_EXECUTION", exit_code=ExitCode.DIGEST) from None
    if completed.returncode != 0:
        raise GateError(FailClass.ATTESTATION, "COSIGN_VERIFY_FAILED", exit_code=ExitCode.DIGEST)
    return {
        "payload_sha256": sha256_file(payload),
        "bundle_sha256": sha256_file(bundle),
        "statement_sha256": sha256_file(statement),
        "trust_policy_sha256": policy.digest,
        "cosign_binary_sha256": expected_cosign_sha256,
    }


def reject_outer_zip_self_signature(subject_name: str) -> None:
    if subject_name.lower().endswith(".zip"):
        raise GateError(FailClass.ATTESTATION, "OUTER_ZIP_SELF_SIGNATURE", exit_code=ExitCode.DIGEST)


def verify_keyless_claims(claims: dict[str, Any], policy: TrustPolicy) -> None:
    keys = {"issuer", "identity", "repository", "workflow", "ref", "commit_sha", "subject_name", "subject_sha256", "transparency_log_verified"}
    if set(claims) != keys:
        raise GateError(FailClass.POLICY_TRUST, "KEYLESS_CLAIM_KEYS", exit_code=ExitCode.SCHEMA)
    mapping = {
        "issuer": "certificate_oidc_issuer", "identity": "certificate_identity",
        "repository": "repository", "workflow": "workflow", "ref": "ref",
        "commit_sha": "commit_sha", "subject_name": "subject_name", "subject_sha256": "subject_sha256",
    }
    for claim_key, policy_key in mapping.items():
        if claims[claim_key] != policy.payload[policy_key]:
            raise GateError(FailClass.POLICY_TRUST, f"KEYLESS_{claim_key.upper()}", exit_code=ExitCode.DIGEST)
    if claims["transparency_log_verified"] is not True:
        raise GateError(FailClass.POLICY_TRUST, "TRANSPARENCY_LOG", exit_code=ExitCode.DIGEST)


def _validate_expiry(value: object, *, now: datetime | None) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        _block("TRUST_EXPIRY")
    try:
        expiry = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _block("TRUST_EXPIRY")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if expiry <= current.astimezone(timezone.utc):
        _block("TRUST_EXPIRED")


def _block(detail: str) -> None:
    raise GateError(FailClass.POLICY_TRUST, detail, exit_code=ExitCode.SCHEMA)
