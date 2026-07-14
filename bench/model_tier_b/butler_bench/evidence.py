from __future__ import annotations

import re
import stat
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .canonical import canonical_sha256, read_json_closed, sha256_file, write_canonical_json
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ENVELOPE_KEYS = {
    "schema_version", "receipt_type", "run_id", "subject", "parents", "payload",
    "created_at_utc", "canonicalization", "receipt_sha256",
}


class EvidenceWriter:
    __slots__ = ("root", "run_id", "_digests")

    def __init__(self, root: Path, run_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", run_id):
            _block("RUN_ID", ExitCode.SCHEMA)
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._digests: set[str] = set()

    def write_receipt(
        self,
        receipt_type: str,
        *,
        subject: list[dict[str, str]],
        parents: list[str],
        payload: dict[str, Any],
        created_at_utc: str | None = None,
    ) -> tuple[Path, str]:
        if not re.fullmatch(r"[a-z][A-Za-z0-9_]{0,63}", receipt_type):
            _block("RECEIPT_TYPE", ExitCode.SCHEMA)
        _validate_subjects(subject)
        if len(parents) != len(set(parents)) or any(not _SHA256.fullmatch(item) for item in parents):
            _block("PARENT_DIGEST", ExitCode.SCHEMA)
        envelope: dict[str, Any] = {
            "schema_version": "butler.model-tier-b.receipt.v2.8",
            "receipt_type": receipt_type,
            "run_id": self.run_id,
            "subject": subject,
            "parents": [{"receipt_sha256": item} for item in sorted(parents)],
            "payload": payload,
            "created_at_utc": created_at_utc or datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "canonicalization": "RFC8785-JCS-IINTEGER",
        }
        digest = canonical_sha256(envelope)
        if digest in self._digests:
            _block("DUPLICATE_RECEIPT_DIGEST")
        envelope["receipt_sha256"] = digest
        path = self.root / f"{digest}.json"
        if path.exists():
            _block("RECEIPT_PATH_EXISTS")
        write_canonical_json(path, envelope)
        self._digests.add(digest)
        return path, digest


def verify_receipt(envelope: dict[str, Any]) -> str:
    if set(envelope) != _ENVELOPE_KEYS or envelope["schema_version"] != "butler.model-tier-b.receipt.v2.8":
        _block("RECEIPT_KEYS", ExitCode.SCHEMA)
    if envelope["canonicalization"] != "RFC8785-JCS-IINTEGER":
        _block("RECEIPT_CANONICALIZATION", ExitCode.SCHEMA)
    declared = envelope["receipt_sha256"]
    unsigned = {key: value for key, value in envelope.items() if key != "receipt_sha256"}
    if not isinstance(declared, str) or not _SHA256.fullmatch(declared) or canonical_sha256(unsigned) != declared:
        _block("RECEIPT_DIGEST", ExitCode.DIGEST)
    _validate_subjects(envelope["subject"])
    parents = envelope["parents"]
    if not isinstance(parents, list) or len(parents) != len({str(item) for item in parents}):
        _block("PARENT_LIST", ExitCode.SCHEMA)
    for parent in parents:
        if not isinstance(parent, dict) or set(parent) != {"receipt_sha256"} or not _SHA256.fullmatch(parent["receipt_sha256"]):
            _block("PARENT_ENTRY", ExitCode.SCHEMA)
    return declared


def verify_evidence_directory(root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve(strict=True)
    if set(profile) != {"profile_version", "mandatory_receipts", "final_pointer", "max_receipts"}:
        _block("PROFILE_KEYS", ExitCode.SCHEMA)
    if profile["profile_version"] != "v2.8":
        _block("PROFILE_VERSION", ExitCode.SCHEMA)
    mandatory = profile["mandatory_receipts"]
    if not isinstance(mandatory, list) or len(mandatory) < 16 or len(mandatory) != len(set(mandatory)):
        _block("PROFILE_MANDATORY", ExitCode.SCHEMA)
    max_receipts = profile["max_receipts"]
    if not isinstance(max_receipts, int) or not 16 <= max_receipts <= 100_000:
        _block("PROFILE_MAX_RECEIPTS", ExitCode.SCHEMA)
    pointer = profile["final_pointer"]
    if not isinstance(pointer, str) or not re.fullmatch(r"receipts/[0-9a-f]{64}\.json", pointer):
        _block("PROFILE_FINAL_POINTER", ExitCode.SCHEMA)
    receipt_dir = root / "receipts"
    final_pointer_file = root / "final_receipt_path.txt"
    if not receipt_dir.is_dir() or not final_pointer_file.is_file():
        _block("RECEIPT_SET_MISSING")
    observed_pointer = final_pointer_file.read_text(encoding="ascii").strip()
    if observed_pointer != pointer:
        _block("FINAL_POINTER_MISMATCH")
    receipts: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    paths = sorted(receipt_dir.glob("*.json"))
    if not paths or len(paths) > max_receipts:
        _block("RECEIPT_CARDINALITY")
    for path in paths:
        value = read_json_closed(path)
        if not isinstance(value, dict):
            _block("RECEIPT_OBJECT", ExitCode.SCHEMA)
        digest = verify_receipt(value)
        if path.name != f"{digest}.json" or digest in receipts:
            _block("RECEIPT_FILENAME_OR_DUPLICATE")
        receipts[digest] = value
        counts[value["receipt_type"]] += 1
    missing = sorted(set(mandatory) - set(counts))
    if missing:
        _block("MANDATORY_RECEIPT_MISSING")
    final_digest = PurePosixPath(pointer).stem
    final = receipts.get(final_digest)
    if final is None or final["receipt_type"] != "final_verdict":
        _block("FINAL_RECEIPT_INVALID")
    _verify_dag(receipts, final_digest)
    return {
        "schema_version": "butler.model-tier-b.evidence-graph-verdict.v2.8",
        "receipt_count": len(receipts),
        "final_receipt_sha256": final_digest,
        "mandatory_types_present": sorted(set(mandatory)),
        "orphan_count": 0,
        "cycle_count": 0,
    }


def _verify_dag(receipts: dict[str, dict[str, Any]], final_digest: str) -> None:
    colors: dict[str, int] = {}
    reachable: set[str] = set()

    def visit(digest: str) -> None:
        color = colors.get(digest, 0)
        if color == 1:
            _block("RECEIPT_CYCLE")
        if color == 2:
            return
        receipt = receipts.get(digest)
        if receipt is None:
            _block("PARENT_MISSING")
        colors[digest] = 1
        reachable.add(digest)
        for parent in receipt["parents"]:
            visit(parent["receipt_sha256"])
        colors[digest] = 2

    visit(final_digest)
    if reachable != set(receipts):
        _block("ORPHAN_RECEIPT")


def build_artifact_manifest(root: Path, output_name: str = "artifact_manifest.jcs.json") -> dict[str, Any]:
    root = root.resolve(strict=True)
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise GateError(FailClass.SECURITY_PRIVACY, "ARTIFACT_PATH_UNSAFE", exit_code=ExitCode.SECURITY)
        if not path.is_file() or path.name == output_name:
            continue
        relative = path.relative_to(root).as_posix()
        if PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:
            raise GateError(FailClass.SECURITY_PRIVACY, "ARTIFACT_PATH_ESCAPE", exit_code=ExitCode.SECURITY)
        files.append({"relative_path": relative, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    payload: dict[str, Any] = {
        "schema_version": "butler.model-tier-b.artifact-manifest.v2.8",
        "self_exclusion": output_name,
        "files": files,
    }
    payload["artifact_manifest_sha256"] = canonical_sha256(payload)
    write_canonical_json(root / output_name, payload)
    return payload


def _validate_subjects(value: object) -> None:
    if not isinstance(value, list) or not value:
        _block("SUBJECT_EMPTY", ExitCode.SCHEMA)
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "sha256"}:
            _block("SUBJECT_KEYS", ExitCode.SCHEMA)
        if not isinstance(item["name"], str) or not item["name"] or item["name"] in seen:
            _block("SUBJECT_NAME", ExitCode.SCHEMA)
        if not isinstance(item["sha256"], str) or not _SHA256.fullmatch(item["sha256"]):
            _block("SUBJECT_DIGEST", ExitCode.SCHEMA)
        seen.add(item["name"])


def _block(detail: str, exit_code: ExitCode = ExitCode.EVIDENCE) -> None:
    raise GateError(FailClass.EVIDENCE, detail, exit_code=exit_code)
