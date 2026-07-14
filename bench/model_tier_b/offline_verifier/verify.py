#!/usr/bin/env python3
"""Standalone Butler v2.8 verifier; standard library only, no producer import."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

EXIT_SCHEMA = 10
EXIT_DIGEST = 11
EXIT_PROTOCOL = 12
EXIT_SECURITY = 13
EXIT_ENVIRONMENT = 14
EXIT_EVIDENCE = 15
EXIT_INTERNAL = 20
MAX_SAFE_INTEGER = (1 << 53) - 1
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_KEYS = {
    "schema_version", "receipt_type", "run_id", "subject", "parents", "payload",
    "created_at_utc", "canonicalization", "receipt_sha256",
}
SENSITIVE = (
    ("ABSOLUTE_HOME_PATH", re.compile(rb"(?:/Users/|/home/|/root/)[A-Za-z0-9._-]+(?:/|\b)")),
    ("BEARER_TOKEN", re.compile(rb"(?i)bearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}")),
    ("PRIVATE_KEY", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("SECRET_ASSIGNMENT", re.compile(rb"(?i)\b(?:api[_-]?key|secret|password|token|cookie)\s*[:=]\s*[^\s,;]{6,}")),
    ("RAW_EVIDENCE_FIELD", re.compile(rb'(?i)"(?:prompt|raw_output|reference_text|draft_text)"\s*:')),
)


class Block(RuntimeError):
    def __init__(self, code: int, fail_class: str, detail: str) -> None:
        self.code = code
        self.fail_class = fail_class
        self.detail = detail
        super().__init__(f"{fail_class}:{detail}")


def canonical_bytes(value: Any) -> bytes:
    validate_json(value)
    return encode(value).encode("utf-8")


def encode(value: Any) -> str:
    if value is None: return "null"
    if value is True: return "true"
    if value is False: return "false"
    if isinstance(value, int) and not isinstance(value, bool): return str(value)
    if isinstance(value, str): return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, list): return "[" + ",".join(encode(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{encode(key)}:{encode(value[key])}" for key in sorted(value, key=lambda item: item.encode("utf-16be"))) + "}"
    raise AssertionError


def validate_json(value: Any) -> None:
    if value is None or isinstance(value, bool): return
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            block(EXIT_SCHEMA, "EVIDENCE", "STRING_PROFILE")
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > MAX_SAFE_INTEGER: block(EXIT_SCHEMA, "EVIDENCE", "INTEGER_PROFILE")
        return
    if isinstance(value, list):
        for item in value: validate_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str): block(EXIT_SCHEMA, "EVIDENCE", "NON_STRING_KEY")
            validate_json(key); validate_json(item)
        return
    block(EXIT_SCHEMA, "EVIDENCE", "JSON_TYPE")


def read_json(path: Path) -> Any:
    def object_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result: raise ValueError("duplicate")
            result[key] = value
        return result
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=object_hook,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
            parse_float=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        block(EXIT_SCHEMA, "EVIDENCE", "JSON_READ")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_manifest(root: Path) -> dict[str, Any]:
    path = root / "artifact_manifest.jcs.json"
    value = read_json(path)
    keys = {"schema_version", "self_exclusion", "files", "artifact_manifest_sha256"}
    if not isinstance(value, dict) or set(value) != keys or value["schema_version"] != "butler.model-tier-b.artifact-manifest.v2.8":
        block(EXIT_SCHEMA, "EVIDENCE", "MANIFEST_KEYS")
    if value["self_exclusion"] != path.name:
        block(EXIT_SCHEMA, "EVIDENCE", "MANIFEST_SELF_EXCLUSION")
    unsigned = {key: item for key, item in value.items() if key != "artifact_manifest_sha256"}
    if digest_bytes(canonical_bytes(unsigned)) != value["artifact_manifest_sha256"]:
        block(EXIT_DIGEST, "EVIDENCE", "MANIFEST_DIGEST")
    actual: dict[str, tuple[int, str]] = {}
    casefold: dict[str, str] = {}
    for item in root.rglob("*"):
        if item.is_symlink(): block(EXIT_SECURITY, "SECURITY_PRIVACY", "ARTIFACT_SYMLINK")
        if not item.is_file() or item == path: continue
        relative = item.relative_to(root).as_posix()
        fold = unicodedata.normalize("NFC", relative).casefold()
        if fold in casefold and casefold[fold] != relative:
            block(EXIT_SECURITY, "SECURITY_PRIVACY", "CASEFOLD_COLLISION")
        casefold[fold] = relative
        data = item.read_bytes()
        actual[relative] = (len(data), digest_bytes(data))
    listed: dict[str, tuple[int, str]] = {}
    if not isinstance(value["files"], list): block(EXIT_SCHEMA, "EVIDENCE", "MANIFEST_FILES")
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) != {"relative_path", "size_bytes", "sha256"}:
            block(EXIT_SCHEMA, "EVIDENCE", "MANIFEST_ENTRY")
        relative = item["relative_path"]
        if not safe_relative(relative) or relative in listed:
            block(EXIT_SECURITY, "SECURITY_PRIVACY", "MANIFEST_PATH")
        listed[relative] = (item["size_bytes"], item["sha256"])
    if listed != actual: block(EXIT_DIGEST, "EVIDENCE", "ARTIFACT_SET")
    return value


def verify_receipts(root: Path) -> dict[str, Any]:
    profile = read_json(root / "artifact_profile.json")
    if not isinstance(profile, dict) or set(profile) != {"profile_version", "mandatory_receipts", "final_pointer", "max_receipts"}:
        block(EXIT_SCHEMA, "EVIDENCE", "PROFILE_KEYS")
    if profile["profile_version"] != "v2.8": block(EXIT_SCHEMA, "EVIDENCE", "PROFILE_VERSION")
    mandatory = profile["mandatory_receipts"]
    if not isinstance(mandatory, list) or len(mandatory) < 16 or len(mandatory) != len(set(mandatory)):
        block(EXIT_SCHEMA, "EVIDENCE", "PROFILE_MANDATORY")
    pointer_file = root / "final_receipt_path.txt"
    pointer = pointer_file.read_text(encoding="ascii").strip() if pointer_file.is_file() else ""
    if pointer != profile["final_pointer"] or not re.fullmatch(r"receipts/[0-9a-f]{64}\.json", pointer):
        block(EXIT_EVIDENCE, "EVIDENCE", "FINAL_POINTER")
    receipts: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    receipt_dir = root / "receipts"
    paths = sorted(receipt_dir.glob("*.json")) if receipt_dir.is_dir() else []
    if not paths or len(paths) > profile["max_receipts"]:
        block(EXIT_EVIDENCE, "EVIDENCE", "RECEIPT_CARDINALITY")
    for path in paths:
        receipt = read_json(path)
        if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS or receipt["schema_version"] != "butler.model-tier-b.receipt.v2.8":
            block(EXIT_SCHEMA, "EVIDENCE", "RECEIPT_KEYS")
        declared = receipt["receipt_sha256"]
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        if not isinstance(declared, str) or digest_bytes(canonical_bytes(unsigned)) != declared or path.name != f"{declared}.json":
            block(EXIT_DIGEST, "EVIDENCE", "RECEIPT_DIGEST")
        if declared in receipts: block(EXIT_EVIDENCE, "EVIDENCE", "DUPLICATE_RECEIPT_DIGEST")
        receipts[declared] = receipt
        counts[receipt["receipt_type"]] += 1
    if set(mandatory) - set(counts): block(EXIT_EVIDENCE, "EVIDENCE", "MANDATORY_RECEIPT_MISSING")
    final_digest = PurePosixPath(pointer).stem
    if final_digest not in receipts or receipts[final_digest]["receipt_type"] != "final_verdict":
        block(EXIT_EVIDENCE, "EVIDENCE", "FINAL_RECEIPT")
    verify_dag(receipts, final_digest)
    return {"receipt_count": len(receipts), "final_receipt_sha256": final_digest, "receipts": receipts}


def verify_dag(receipts: dict[str, dict[str, Any]], final_digest: str) -> None:
    colors: dict[str, int] = {}
    reachable: set[str] = set()
    def visit(digest: str) -> None:
        if colors.get(digest) == 1: block(EXIT_EVIDENCE, "EVIDENCE", "RECEIPT_CYCLE")
        if colors.get(digest) == 2: return
        receipt = receipts.get(digest)
        if receipt is None: block(EXIT_EVIDENCE, "EVIDENCE", "PARENT_MISSING")
        colors[digest] = 1; reachable.add(digest)
        parents = receipt["parents"]
        if not isinstance(parents, list): block(EXIT_SCHEMA, "EVIDENCE", "PARENTS")
        for parent in parents:
            if not isinstance(parent, dict) or set(parent) != {"receipt_sha256"} or not SHA256.fullmatch(parent["receipt_sha256"]):
                block(EXIT_SCHEMA, "EVIDENCE", "PARENT_ENTRY")
            visit(parent["receipt_sha256"])
        colors[digest] = 2
    visit(final_digest)
    if reachable != set(receipts): block(EXIT_EVIDENCE, "EVIDENCE", "ORPHAN_RECEIPT")


def scan_runtime(root: Path) -> int:
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "artifact_manifest.jcs.json": continue
        data = path.read_bytes(); digest = digest_bytes(data); count += 1
        for encoding in ("ascii", "utf-8", "utf-16le", "utf-16be"):
            try: encoded = data.decode(encoding).encode("utf-8")
            except UnicodeError: continue
            for rule, pattern in SENSITIVE:
                if pattern.search(encoded): block(EXIT_SECURITY, "SECURITY_PRIVACY", f"{rule}:{digest[:12]}:{encoding}")
    return count


def verify_code_delivery(root: Path) -> dict[str, Any]:
    manifest = verify_manifest(root)
    status = read_json(root / "evidence" / "local_validation" / "final_status.json")
    gates = status.get("gates")
    if status.get("status") not in {"SPEC_READY", "CODE_READY_FOR_AUDIT", "BLOCKED"}:
        block(EXIT_PROTOCOL, "PREFLIGHT", "CODE_DELIVERY_STATUS")
    if not isinstance(gates, dict) or not gates or all(
        isinstance(value, dict) and value.get("value") is True for value in gates.values()
    ):
        block(EXIT_PROTOCOL, "PREFLIGHT", "CODE_DELIVERY_CLAIM_BOUNDARY")
    return {
        "status": "CODE_DELIVERY_INTEGRITY_PASS_NO_M3_CLAIM",
        "artifact_manifest_sha256": manifest["artifact_manifest_sha256"],
        "producer_imported": False,
        "m3_evidence_pass_claimed": False,
        "semantic_reverification_claimed": False,
    }


# F-002/F-003: receipt types whose semantics can only be re-established from a
# *signed external observation stream* (process table, RSS/VM maps, open model
# inode, packet/filter logs, energy meter, sampler stream). The standalone offline
# verifier cannot re-execute these from artifact content alone, so their semantic
# verdict stays fail-closed until such signed observations are supplied at M3 time.
EXTERNAL_OBSERVER_RECEIPTS = frozenset({
    "environment", "worker_event_stream_index", "cold_worker",
    "dual_resident", "os_egress", "epoch", "live_semantic_verify",
})


# --- Minimal, dependency-free Ed25519 (RFC 8032) for asymmetric observation trust ---
# The independent verifier holds only the pinned PUBLIC key; the external observer
# signs with a private key it never shares. This removes the previous symmetric-HMAC
# hole where the caller handed the verifier the signing secret (R2-P0-009).
_ED_Q = 2 ** 255 - 19
_ED_L = 2 ** 252 + 27742317777372353535851937790883648493


def _ed_inv(x: int) -> int:
    return pow(x, _ED_Q - 2, _ED_Q)


_ED_D = (-121665 * _ed_inv(121666)) % _ED_Q
_ED_I = pow(2, (_ED_Q - 1) // 4, _ED_Q)


def _ed_xrecover(y: int) -> int:
    xx = (y * y - 1) * _ed_inv(_ED_D * y * y + 1)
    x = pow(xx, (_ED_Q + 3) // 8, _ED_Q)
    if (x * x - xx) % _ED_Q != 0:
        x = (x * _ED_I) % _ED_Q
    if x % 2 != 0:
        x = _ED_Q - x
    return x


_ED_BY = (4 * _ed_inv(5)) % _ED_Q
_ED_B = (_ed_xrecover(_ED_BY) % _ED_Q, _ED_BY % _ED_Q)


def _ed_edwards(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = p
    x2, y2 = q
    x3 = (x1 * y2 + x2 * y1) * _ed_inv(1 + _ED_D * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _ed_inv(1 - _ED_D * x1 * x2 * y1 * y2)
    return (x3 % _ED_Q, y3 % _ED_Q)


def _ed_scalarmult(p: tuple[int, int], e: int) -> tuple[int, int]:
    result = (0, 1)
    addend = p
    while e > 0:
        if e & 1:
            result = _ed_edwards(result, addend)
        addend = _ed_edwards(addend, addend)
        e >>= 1
    return result


def _ed_bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def _ed_hint(m: bytes) -> int:
    h = hashlib.sha512(m).digest()
    return sum(2 ** i * _ed_bit(h, i) for i in range(512))


def _ed_encodepoint(p: tuple[int, int]) -> bytes:
    x, y = p
    return ((y & ((1 << 255) - 1)) | ((x & 1) << 255)).to_bytes(32, "little")


def _ed_decodepoint(s: bytes) -> tuple[int, int]:
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _ed_xrecover(y)
    if (x & 1) != _ed_bit(s, 255):
        x = _ED_Q - x
    if (-x * x + y * y - 1 - _ED_D * x * x * y * y) % _ED_Q != 0:
        raise ValueError("point not on curve")
    return (x, y)


def ed25519_publickey(secret_seed: bytes) -> bytes:
    h = hashlib.sha512(secret_seed).digest()
    a = 2 ** 254 + sum(2 ** i * _ed_bit(h, i) for i in range(3, 254))
    return _ed_encodepoint(_ed_scalarmult(_ED_B, a))


def ed25519_sign(secret_seed: bytes, message: bytes) -> bytes:
    h = hashlib.sha512(secret_seed).digest()
    a = 2 ** 254 + sum(2 ** i * _ed_bit(h, i) for i in range(3, 254))
    public = _ed_encodepoint(_ed_scalarmult(_ED_B, a))
    r = _ed_hint(h[32:64] + message)
    upper = _ed_encodepoint(_ed_scalarmult(_ED_B, r))
    s = (r + _ed_hint(upper + public + message) * a) % _ED_L
    return upper + s.to_bytes(32, "little")


def ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64 or len(public_key) != 32:
        return False
    try:
        upper = _ed_decodepoint(signature[:32])
        point = _ed_decodepoint(public_key)
    except ValueError:
        return False
    s = int.from_bytes(signature[32:], "little")
    h = _ed_hint(signature[:32] + public_key + message)
    left = _ed_scalarmult(_ED_B, s)
    right = _ed_edwards(upper, _ed_scalarmult(point, h))
    return left == right


OBSERVATION_SCHEMA = "butler.model-tier-b.external-observation.v3"
OBSERVATION_KEYS = {"schema_version", "run_id", "signer_public_key_ed25519", "observations", "signature_ed25519"}
OBSERVATION_ENTRY_KEYS = {"receipt_sha256", "receipt_type", "subject_sha256", "raw_safe_observation", "observation_digest"}
_OBSERVATION_FIELD_RE = re.compile(r"^[a-z0-9_]{1,48}$")


def _unavailable(present_types: list[str], external_required: list[str]) -> dict[str, Any]:
    return {
        "status": "SEMANTIC_REVERIFICATION_UNAVAILABLE",
        "receipt_type_results": {
            receipt_type: ("EXTERNAL_OBSERVER_REQUIRED" if receipt_type in EXTERNAL_OBSERVER_RECEIPTS else "STRUCTURE_ONLY_RECHECKED")
            for receipt_type in present_types
        },
        "external_observer_required": external_required,
        "semantic_reexecuted": False,
    }


TRUST_POLICY_SCHEMA = "butler.m3.trust-policy.v1"
TRUST_POLICY_KEYS = {
    "schema_version", "policy_id", "policy_version", "signature_algorithm",
    "public_key_encoding", "public_key", "public_key_sha256",
    "accepted_key_ids", "revoked_key_ids", "payload_type",
}


def _load_trust_policy(path: Path, expected_sha256: str) -> dict[str, Any]:
    """PR861-R3 P0-A: the trust anchor is an EXTERNAL, SHA-pinned closed-world policy.

    The verifier NEVER trusts a caller-supplied public key or the artifact's own copy.
    The policy file's raw digest must equal the externally fixed expected_sha256; the
    approved Ed25519 public key comes only from this policy; wildcard/empty accepted
    sets are rejected.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        block(EXIT_PROTOCOL, "INDEPENDENT_VERIFY", "TRUST_POLICY_READ")
    if not hmac.compare_digest(digest_bytes(raw), expected_sha256):
        block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "TRUST_POLICY_DIGEST")
    policy = read_json(path)
    validate_json(policy)
    if not isinstance(policy, dict) or set(policy) != TRUST_POLICY_KEYS or policy["schema_version"] != TRUST_POLICY_SCHEMA:
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "TRUST_POLICY_SCHEMA")
    if policy["signature_algorithm"] != "Ed25519":
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "TRUST_POLICY_ALG")
    approved = policy["public_key"]
    if not isinstance(approved, str) or not re.fullmatch(r"[0-9a-f]{64}", approved):
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "TRUST_POLICY_KEY")
    if not hmac.compare_digest(policy["public_key_sha256"], digest_bytes(bytes.fromhex(approved))):
        block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "TRUST_POLICY_KEY_DIGEST")
    for field in ("accepted_key_ids", "revoked_key_ids"):
        value = policy[field]
        if not isinstance(value, list) or any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item) for item in value):
            block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "TRUST_POLICY_KEY_IDS")
    if not policy["accepted_key_ids"] or "*" in policy["accepted_key_ids"]:
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "TRUST_POLICY_WILDCARD")
    if digest_bytes(bytes.fromhex(approved)) not in set(policy["accepted_key_ids"]):
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "TRUST_POLICY_APPROVED_NOT_ACCEPTED")
    return policy


def verify_m3_semantic(
    receipts: dict[str, dict[str, Any]],
    *,
    bundle_path: Path | None = None,
    trust_policy_path: Path | None = None,
    trust_policy_sha256: str | None = None,
) -> dict[str, Any]:
    """PR861-R3 P0-A + R2 P0-006..009: trust-bounded semantic re-verification.

    Fail-closed to SEMANTIC_REVERIFICATION_UNAVAILABLE without a bundle. With a bundle:

    - The approved signer public key comes ONLY from an external SHA-pinned trust
      policy (P0-A). Caller-supplied keys and the artifact's own key are never trusted;
      a revoked key id (e.g. the exposed owner seed) can never verify.
    - The Ed25519 signature is verified against the APPROVED policy key.
    - bundle.run_id must equal EVERY receipt's run_id (R2-P0-007).
    - Every external-observer receipt DIGEST needs exactly one observation; extras,
      duplicates, and unobserved same-type receipts are blocked (R2-P0-008).
    - The observation digest is RECOMPUTED from the raw-safe observation fields and
      must equal the declared digest; arbitrary declared digests are rejected
      (R2-P0-006). Subject digests are re-bound to each receipt.
    """
    present_types = sorted({receipt["receipt_type"] for receipt in receipts.values()})
    external_required = sorted(set(present_types) & EXTERNAL_OBSERVER_RECEIPTS)
    if bundle_path is None:
        return _unavailable(present_types, external_required)

    # P0-A: external SHA-pinned trust policy is mandatory. No caller public key.
    if trust_policy_path is None or not isinstance(trust_policy_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", trust_policy_sha256):
        block(EXIT_PROTOCOL, "INDEPENDENT_VERIFY", "TRUST_POLICY_PIN_REQUIRED")
    policy = _load_trust_policy(trust_policy_path, trust_policy_sha256)
    approved_pub_hex = policy["public_key"]
    approved_key = bytes.fromhex(approved_pub_hex)
    revoked_ids = set(policy["revoked_key_ids"])

    bundle = read_json(bundle_path)
    validate_json(bundle)
    if not isinstance(bundle, dict) or set(bundle) != OBSERVATION_KEYS or bundle["schema_version"] != OBSERVATION_SCHEMA:
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "OBSERVATION_KEYS")
    bundle_pub_hex = bundle["signer_public_key_ed25519"]
    if not isinstance(bundle_pub_hex, str) or not re.fullmatch(r"[0-9a-f]{64}", bundle_pub_hex):
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "OBSERVATION_SIGNER_FORMAT")
    bundle_key_id = digest_bytes(bytes.fromhex(bundle_pub_hex))
    if bundle_key_id in revoked_ids:
        block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "REVOKED_SIGNER")
    if not hmac.compare_digest(bundle_pub_hex, approved_pub_hex) or bundle_key_id not in set(policy["accepted_key_ids"]):
        block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "OBSERVATION_SIGNER_UNTRUSTED")
    declared_sig = bundle["signature_ed25519"]
    if not isinstance(declared_sig, str) or not re.fullmatch(r"[0-9a-f]{128}", declared_sig):
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "OBSERVATION_SIGNATURE_FORMAT")
    unsigned = {name: value for name, value in bundle.items() if name != "signature_ed25519"}
    # Verify against the APPROVED policy key, not the bundle's self-declared key.
    if not ed25519_verify(approved_key, canonical_bytes(unsigned), bytes.fromhex(declared_sig)):
        block(EXIT_SECURITY, "SECURITY_PRIVACY", "FORGED_OBSERVATION_SIGNATURE")

    run_id = bundle["run_id"]
    if not isinstance(run_id, str) or not run_id:
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "OBSERVATION_RUN_ID")
    for receipt in receipts.values():
        if receipt.get("run_id") != run_id:
            block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "OBSERVATION_RUN_ID_MISMATCH")

    observations = bundle["observations"]
    if not isinstance(observations, list):
        block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "OBSERVATION_LIST")

    # Exactly one observation per external-observer receipt digest.
    external_digests = {digest for digest, receipt in receipts.items() if receipt["receipt_type"] in EXTERNAL_OBSERVER_RECEIPTS}
    observed_digests: set[str] = set()
    per_type: dict[str, str] = {}
    for entry in observations:
        if not isinstance(entry, dict) or set(entry) != OBSERVATION_ENTRY_KEYS:
            block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "OBSERVATION_ENTRY_KEYS")
        digest = entry["receipt_sha256"]
        if digest not in receipts:
            block(EXIT_EVIDENCE, "INDEPENDENT_VERIFY", "OBSERVATION_RECEIPT_UNKNOWN")
        if digest not in external_digests:
            block(EXIT_EVIDENCE, "INDEPENDENT_VERIFY", "OBSERVATION_EXTRA_NON_EXTERNAL")
        if digest in observed_digests:
            block(EXIT_EVIDENCE, "INDEPENDENT_VERIFY", "OBSERVATION_DUPLICATE")
        observed_digests.add(digest)
        receipt = receipts[digest]
        if entry["receipt_type"] != receipt["receipt_type"]:
            block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "OBSERVATION_TYPE_MISMATCH")
        subject_digest = digest_bytes(canonical_bytes(receipt["subject"]))
        if not isinstance(entry["subject_sha256"], str) or not hmac.compare_digest(entry["subject_sha256"], subject_digest):
            block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "OBSERVATION_SUBJECT_MISMATCH")
        raw_safe = entry["raw_safe_observation"]
        if not isinstance(raw_safe, dict) or not raw_safe or any(not _OBSERVATION_FIELD_RE.fullmatch(str(key)) for key in raw_safe):
            block(EXIT_SCHEMA, "INDEPENDENT_VERIFY", "OBSERVATION_RAW_SCHEMA")
        recomputed = digest_bytes(canonical_bytes(raw_safe))
        if not isinstance(entry["observation_digest"], str) or not hmac.compare_digest(entry["observation_digest"], recomputed):
            block(EXIT_DIGEST, "INDEPENDENT_VERIFY", "OBSERVATION_DIGEST_MISMATCH")
        per_type[receipt["receipt_type"]] = "SEMANTIC_REEXECUTED_PASS"

    missing = external_digests - observed_digests
    if missing:
        block(EXIT_EVIDENCE, "INDEPENDENT_VERIFY", "MISSING_EXTERNAL_OBSERVATION")

    for receipt_type in present_types:
        per_type.setdefault(receipt_type, "STRUCTURE_ONLY_RECHECKED")
    reexecuted = bool(external_digests) and observed_digests == external_digests
    return {
        "status": "M3_SEMANTIC_PASS" if reexecuted else "SEMANTIC_REVERIFICATION_UNAVAILABLE",
        "receipt_type_results": per_type,
        "external_observer_required": external_required,
        "semantic_reexecuted": reexecuted,
    }


def verify_m3(
    root: Path,
    *,
    bundle_path: Path | None = None,
    trust_policy_path: Path | None = None,
    trust_policy_sha256: str | None = None,
) -> dict[str, Any]:
    manifest = verify_manifest(root)
    graph = verify_receipts(root)
    scanned = scan_runtime(root)
    structural = {
        "status": "M3_ARTIFACT_STRUCTURE_PASS",
        "artifact_manifest_sha256": manifest["artifact_manifest_sha256"],
        "receipt_count": graph["receipt_count"],
        "files_scanned": scanned,
    }
    semantic = verify_m3_semantic(
        graph["receipts"],
        bundle_path=bundle_path,
        trust_policy_path=trust_policy_path,
        trust_policy_sha256=trust_policy_sha256,
    )
    m3_evidence_valid = 1 if structural["status"] == "M3_ARTIFACT_STRUCTURE_PASS" and semantic["status"] == "M3_SEMANTIC_PASS" else 0
    return {
        "status": "M3_EVIDENCE_VALID" if m3_evidence_valid == 1 else "M3_ARTIFACT_STRUCTURE_PASS_SEMANTIC_REVIEW_REQUIRED",
        "structural": structural,
        "semantic": semantic,
        "m3_evidence_valid": m3_evidence_valid,
        "producer_imported": False,
        # G1/M4 governance stays fail-closed regardless of evidence validity.
        "g1_ready": False,
        "m4_ready": False,
        "runtime_activation_allowed": 0,
    }


def safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value: return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts and "\\" not in value


def block(code: int, fail_class: str, detail: str) -> None:
    raise Block(code, fail_class, detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("root", type=Path)
    parser.add_argument("--mode", choices=("m3-evidence", "code-delivery"), default="m3-evidence")
    parser.add_argument("--observation-bundle", type=Path, default=None)
    parser.add_argument("--trust-policy", type=Path, default=None)
    parser.add_argument("--trust-policy-sha256", default=None)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        if args.mode == "m3-evidence":
            result = verify_m3(
                root,
                bundle_path=args.observation_bundle.resolve(strict=True) if args.observation_bundle else None,
                trust_policy_path=args.trust_policy.resolve(strict=True) if args.trust_policy else None,
                trust_policy_sha256=args.trust_policy_sha256,
            )
        else:
            result = verify_code_delivery(root)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Block as exc:
        print(json.dumps({"status": "BLOCKED", "fail_class": exc.fail_class, "detail_id": exc.detail, "exit_code": exc.code}, sort_keys=True, separators=(",", ":")))
        return exc.code
    except Exception:
        print(json.dumps({"status": "BLOCKED", "fail_class": "INTERNAL", "detail_id": "UNHANDLED", "exit_code": EXIT_INTERNAL}, sort_keys=True, separators=(",", ":")))
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
