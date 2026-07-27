from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .errors import AssetError, block
from .manifest import canonical_json_bytes

MAX_PROVENANCE_BYTES = 2 * 1024 * 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_KEY_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


@dataclass(frozen=True)
class GitOID:
    algorithm: str
    hex: str

    @classmethod
    def parse(cls, value: object) -> "GitOID":
        if not isinstance(value, dict) or set(value) != {"algorithm", "hex"}:
            raise block("BLOCK_PROVENANCE_INVALID")
        algorithm = value["algorithm"]
        hexadecimal = value["hex"]
        lengths = {"sha1": 40, "sha256": 64}
        if (
            algorithm not in lengths
            or not isinstance(hexadecimal, str)
            or len(hexadecimal) != lengths[algorithm]
            or any(ch not in "0123456789abcdef" for ch in hexadecimal)
            or hexadecimal in {"0" * lengths[algorithm], "f" * lengths[algorithm]}
        ):
            raise block("BLOCK_PROVENANCE_INVALID")
        return cls(algorithm, hexadecimal)

    def payload(self) -> dict[str, str]:
        return {"algorithm": self.algorithm, "hex": self.hex}


@dataclass(frozen=True)
class VerifiedProvenance:
    source_oid: GitOID
    source_tree_oid: GitOID
    pr_head_oid: GitOID
    manifest_set_sha256: str
    package_sha256: str
    trust_policy_digest: str
    signer_key_id: str
    builder_id: str
    workflow_id: str


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise block("BLOCK_PROVENANCE_INVALID")
        result[key] = value
    return result


def _load_strict(path: Path) -> tuple[dict[str, object], bytes]:
    try:
        if not path.exists():
            raise block("BLOCK_POLICY_MISSING")
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_size > MAX_PROVENANCE_BYTES:
            raise block("BLOCK_POLICY_MISSING")
        raw = path.read_bytes()
        if not raw or raw.startswith(b"\xef\xbb\xbf"):
            raise block("BLOCK_PROVENANCE_INVALID")
        text = raw.decode("utf-8")
        if text != unicodedata.normalize("NFC", text):
            raise block("BLOCK_PROVENANCE_INVALID")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                block("BLOCK_PROVENANCE_INVALID")
            ),
        )
    except AssetError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise block("BLOCK_PROVENANCE_INVALID") from exc
    if not isinstance(value, dict):
        raise block("BLOCK_PROVENANCE_INVALID")
    return value, raw


def _sha(value: object, *, code: str = "BLOCK_PROVENANCE_INVALID") -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise block(code)
    return value


def _verify_git(repository: Path, source: GitOID, tree: GitOID) -> None:
    if source.algorithm != tree.algorithm:
        raise block("BLOCK_PROVENANCE_INVALID")
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{source.hex}^{{commit}}"],
            cwd=repository,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        actual = subprocess.run(
            ["git", "rev-parse", f"{source.hex}^{{tree}}"],
            cwd=repository,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise block("BLOCK_SOURCE_OID_UNVERIFIED") from exc
    if actual != tree.hex:
        raise block("BLOCK_SOURCE_TREE_MISMATCH")


def verify_signed_provenance(
    *,
    trust_policy_path: Path,
    provenance_path: Path,
    expected_manifest_set: str,
    expected_package_sha256: str | None = None,
    repository: Path | None = None,
) -> VerifiedProvenance:
    policy, policy_raw = _load_strict(trust_policy_path)
    envelope, _envelope_raw = _load_strict(provenance_path)
    policy_keys = {
        "schema_version",
        "allowed_oid_algorithms",
        "allowed_repository_uris",
        "allowed_builder_ids",
        "allowed_workflow_ids",
        "signing_keys",
    }
    if set(policy) != policy_keys or policy["schema_version"] != 1:
        raise block("BLOCK_POLICY_DIGEST_MISMATCH")
    if (
        not isinstance(policy["allowed_oid_algorithms"], list)
        or not set(policy["allowed_oid_algorithms"]) <= {"sha1", "sha256"}
        or not isinstance(policy["allowed_repository_uris"], list)
        or not isinstance(policy["allowed_builder_ids"], list)
        or not isinstance(policy["allowed_workflow_ids"], list)
        or not isinstance(policy["signing_keys"], list)
    ):
        raise block("BLOCK_POLICY_DIGEST_MISMATCH")
    if set(envelope) != {"schema_version", "payload", "signature"} or envelope[
        "schema_version"
    ] != 1:
        raise block("BLOCK_PROVENANCE_INVALID")
    payload = envelope["payload"]
    signature = envelope["signature"]
    required_payload = {
        "package_sha256",
        "repository_uri",
        "source_oid",
        "source_tree_oid",
        "manifest_set_sha256",
        "build_configuration_sha256",
        "builder_id",
        "workflow_id",
        "invocation_id",
        "pr_head_oid",
        "trust_policy_sha256",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required_payload
        or not isinstance(signature, dict)
        or set(signature) != {"algorithm", "key_id", "value_b64"}
    ):
        raise block("BLOCK_PROVENANCE_INVALID")
    policy_digest = hashlib.sha256(policy_raw).hexdigest()
    if payload["trust_policy_sha256"] != policy_digest:
        raise block("BLOCK_POLICY_DIGEST_MISMATCH")
    package_sha = _sha(payload["package_sha256"])
    manifest_set = _sha(payload["manifest_set_sha256"])
    _sha(payload["build_configuration_sha256"])
    if manifest_set != expected_manifest_set:
        raise block("BLOCK_MANIFEST_BINDING_MISMATCH")
    if expected_package_sha256 is not None and package_sha != expected_package_sha256:
        raise block("BLOCK_PACKAGE_BINDING_MISMATCH")
    source_oid = GitOID.parse(payload["source_oid"])
    tree_oid = GitOID.parse(payload["source_tree_oid"])
    pr_head_oid = GitOID.parse(payload["pr_head_oid"])
    if (
        source_oid.algorithm not in policy["allowed_oid_algorithms"]
        or tree_oid.algorithm not in policy["allowed_oid_algorithms"]
        or pr_head_oid.algorithm not in policy["allowed_oid_algorithms"]
        or source_oid != pr_head_oid
    ):
        raise block("BLOCK_PROVENANCE_INVALID")
    repository_uri = payload["repository_uri"]
    builder_id = payload["builder_id"]
    workflow_id = payload["workflow_id"]
    if (
        repository_uri not in policy["allowed_repository_uris"]
        or builder_id not in policy["allowed_builder_ids"]
        or workflow_id not in policy["allowed_workflow_ids"]
        or not isinstance(payload["invocation_id"], str)
        or not payload["invocation_id"]
    ):
        raise block("BLOCK_BUILDER_UNTRUSTED")

    key_id = signature["key_id"]
    if (
        signature["algorithm"] != "ed25519"
        or not isinstance(key_id, str)
        or not _KEY_ID_RE.fullmatch(key_id)
    ):
        raise block("BLOCK_SIGNER_UNPINNED")
    key_rows = [
        row
        for row in policy["signing_keys"]
        if isinstance(row, dict) and row.get("key_id") == key_id
    ]
    if len(key_rows) != 1 or set(key_rows[0]) != {
        "key_id",
        "algorithm",
        "public_key_b64",
    }:
        raise block("BLOCK_SIGNER_UNPINNED")
    if key_rows[0]["algorithm"] != "ed25519":
        raise block("BLOCK_SIGNER_UNPINNED")
    try:
        public = base64.b64decode(
            key_rows[0]["public_key_b64"], validate=True
        )
        signature_raw = base64.b64decode(signature["value_b64"], validate=True)
        if len(public) != 32 or len(signature_raw) != 64:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature_raw, canonical_json_bytes(payload)
        )
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise block("BLOCK_SIGNATURE_INVALID") from exc
    if repository is not None:
        _verify_git(repository, source_oid, tree_oid)
    return VerifiedProvenance(
        source_oid=source_oid,
        source_tree_oid=tree_oid,
        pr_head_oid=pr_head_oid,
        manifest_set_sha256=manifest_set,
        package_sha256=package_sha,
        trust_policy_digest=policy_digest,
        signer_key_id=key_id,
        builder_id=str(builder_id),
        workflow_id=str(workflow_id),
    )


def verify_packaged_provenance(
    resource_root: Path,
    *,
    expected_manifest_set: str,
    expected_package_sha256: str | None = None,
) -> VerifiedProvenance:
    return verify_signed_provenance(
        trust_policy_path=resource_root / "assets/trust/trust-policy.v1.json",
        provenance_path=resource_root
        / "assets/provenance/signed-provenance.v1.json",
        expected_manifest_set=expected_manifest_set,
        expected_package_sha256=expected_package_sha256,
    )
