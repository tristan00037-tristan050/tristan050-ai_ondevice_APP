#!/usr/bin/env python3
"""Standalone Butler v2.8 verifier; standard library only, no producer import."""

from __future__ import annotations

import argparse
import hashlib
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


def verify_m3_semantic(receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """F-003: semantic verification, reported separately from structural.

    Each receipt type is classified. Types that require external signed observation
    cannot be re-executed offline and are marked EXTERNAL_OBSERVER_REQUIRED. The
    semantic verdict is PASS only when every present receipt type has been semantically
    re-executed and passed; otherwise it is fail-closed as UNAVAILABLE (never PASS on
    structure alone).
    """
    present_types = sorted({receipt["receipt_type"] for receipt in receipts.values()})
    external_required = sorted(set(present_types) & EXTERNAL_OBSERVER_RECEIPTS)
    per_type = {
        receipt_type: ("EXTERNAL_OBSERVER_REQUIRED" if receipt_type in EXTERNAL_OBSERVER_RECEIPTS else "STRUCTURE_ONLY_RECHECKED")
        for receipt_type in present_types
    }
    reexecuted = bool(present_types) and all(status == "SEMANTIC_REEXECUTED_PASS" for status in per_type.values())
    return {
        "status": "M3_SEMANTIC_PASS" if reexecuted else "SEMANTIC_REVERIFICATION_UNAVAILABLE",
        "receipt_type_results": per_type,
        "external_observer_required": external_required,
        "semantic_reexecuted": reexecuted,
    }


def verify_m3(root: Path) -> dict[str, Any]:
    manifest = verify_manifest(root)
    graph = verify_receipts(root)
    scanned = scan_runtime(root)
    structural = {
        "status": "M3_ARTIFACT_STRUCTURE_PASS",
        "artifact_manifest_sha256": manifest["artifact_manifest_sha256"],
        "receipt_count": graph["receipt_count"],
        "files_scanned": scanned,
    }
    semantic = verify_m3_semantic(graph["receipts"])
    m3_evidence_valid = 1 if structural["status"] == "M3_ARTIFACT_STRUCTURE_PASS" and semantic["status"] == "M3_SEMANTIC_PASS" else 0
    return {
        "status": "M3_EVIDENCE_VALID" if m3_evidence_valid == 1 else "M3_ARTIFACT_STRUCTURE_PASS_SEMANTIC_REVIEW_REQUIRED",
        "structural": structural,
        "semantic": semantic,
        "m3_evidence_valid": m3_evidence_valid,
        "producer_imported": False,
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
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        result = verify_m3(root) if args.mode == "m3-evidence" else verify_code_delivery(root)
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
