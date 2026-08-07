"""Verified Helper1 v6.1 approval-artifact transport boundary.

The product receives immutable artifact bytes plus independently obtained run
metadata.  This module intentionally exposes no repository-fixture path API.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

from .approval_closure import KNOWN_ROLES, ROLE_MEDIA_TYPES
from .canonical_json import canonicalize_butler_cj1
from .failure_codes import Helper1FailureCode, Helper1V61Error

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WORKFLOW_REF_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
INVENTORY_NAME = "APPROVAL_INPUT_INVENTORY.v2.json"
SCHEMA = "butler.helper1.approval-input-provenance.v2"
INVENTORY_SCHEMA = "butler.helper1.approval-input-inventory.v2"
LEGACY_FILES = (
    "legacy/APPROVED_ASSET_CLOSURE.json",
    "legacy/REAL_ASSET_E2E_RECEIPT.json",
    "legacy/M3_M4_MEASUREMENT.json",
    "legacy/MACOS_SANDBOX_E2E_RECEIPT.json",
)
APPROVAL_FILES = tuple(
    sorted(
        path
        for role in KNOWN_ROLES
        for path in (
            f"approval/{role}.envelope.json",
            f"approval/{role}.payload.json",
        )
    )
)
MAX_FILES = 256
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _positive_int(value: object, code: Helper1FailureCode) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise Helper1V61Error(code)
    return value


@dataclass(frozen=True, slots=True)
class ApprovalInputProvenanceV2:
    repository_id: int
    repository_name: str
    subject_commit: str
    subject_tree: str
    producer_workflow_ref: str
    producer_workflow_id: int
    producer_workflow_sha256: str
    run_id: int
    run_attempt: int
    event_name: str
    artifact_id: int
    artifact_name: str
    artifact_sha256: str
    inventory_sha256: str
    canonical_subject_sha256: str
    schema_version: str = SCHEMA
    mode: str = "ARTIFACT"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA or self.mode != "ARTIFACT":
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH)
        _positive_int(self.repository_id, Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH)
        _positive_int(self.run_id, Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        _positive_int(self.run_attempt, Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        _positive_int(self.producer_workflow_id, Helper1FailureCode.PRODUCER_RUN_MISMATCH)
        _positive_int(self.artifact_id, Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH)
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository_name)
            or SHA40_RE.fullmatch(self.subject_commit) is None
            or SHA40_RE.fullmatch(self.subject_tree) is None
            or WORKFLOW_REF_RE.fullmatch(self.producer_workflow_ref) is None
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.artifact_name)
            or not re.fullmatch(r"[A-Za-z_]+", self.event_name)
        ):
            raise Helper1V61Error(Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH)
        for digest in (
            self.producer_workflow_sha256,
            self.artifact_sha256,
            self.inventory_sha256,
            self.canonical_subject_sha256,
        ):
            if SHA256_RE.fullmatch(digest) is None:
                raise Helper1V61Error(Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "repository_id": self.repository_id,
            "repository_name": self.repository_name,
            "subject_commit": self.subject_commit,
            "subject_tree": self.subject_tree,
            "producer_workflow_ref": self.producer_workflow_ref,
            "producer_workflow_id": self.producer_workflow_id,
            "producer_workflow_sha256": self.producer_workflow_sha256,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "event_name": self.event_name,
            "artifact_id": self.artifact_id,
            "artifact_name": self.artifact_name,
            "artifact_sha256": self.artifact_sha256,
            "inventory_sha256": self.inventory_sha256,
            "canonical_subject_sha256": self.canonical_subject_sha256,
        }


@dataclass(frozen=True, slots=True)
class VerifiedApprovalInputV2:
    provenance: ApprovalInputProvenanceV2
    inventory: Mapping[str, Any]
    files: Mapping[str, bytes]


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
    return path.as_posix()


def _read_zip_bytes(artifact_bytes: bytes) -> dict[str, bytes]:
    if not isinstance(artifact_bytes, bytes) or not artifact_bytes:
        raise Helper1V61Error(Helper1FailureCode.NO_EXPLICIT_PRODUCER)
    files: dict[str, bytes] = {}
    casefolded: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(artifact_bytes), "r") as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_FILES:
                raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
            for member in members:
                name = _safe_member_name(member.filename)
                if member.is_dir():
                    continue
                mode = (member.external_attr >> 16) & 0o177777
                if mode and (stat.S_ISLNK(mode) or not stat.S_ISREG(mode)):
                    raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
                folded = name.casefold()
                if name in files or folded in casefolded:
                    raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
                if member.file_size < 1 or member.file_size > MAX_FILE_BYTES:
                    raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
                raw = archive.read(member)
                if len(raw) != member.file_size:
                    raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
                total += len(raw)
                if total > MAX_TOTAL_BYTES:
                    raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE)
                files[name] = raw
                casefolded.add(folded)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise Helper1V61Error(Helper1FailureCode.UNSAFE_ARCHIVE) from exc
    return files


def _load_inventory(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE) from exc
    if not isinstance(value, dict) or value.get("schema_version") != INVENTORY_SCHEMA:
        raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
    if _canonical_json(value) + b"\n" != raw:
        raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
    return value


def _verify_inventory(files: Mapping[str, bytes], inventory: Mapping[str, Any]) -> None:
    declared = inventory.get("files")
    if not isinstance(declared, dict):
        raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
    actual_names = set(files) - {INVENTORY_NAME}
    required = {*LEGACY_FILES, *APPROVAL_FILES}
    objects = {name for name in actual_names if name.startswith("objects/")}
    if not objects or actual_names != required | objects or set(declared) != actual_names:
        raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
    for name, raw in files.items():
        if name == INVENTORY_NAME:
            continue
        record = declared.get(name)
        if not isinstance(record, dict) or set(record) != {
            "bytes",
            "sha256",
            "media_type",
            "role",
        }:
            raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
        if record["bytes"] != len(raw) or record["sha256"] != _digest(raw):
            raise Helper1V61Error(Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH)
        if name.startswith("objects/"):
            object_digest = PurePosixPath(name).name
            if SHA256_RE.fullmatch(object_digest) is None or object_digest != _digest(raw):
                raise Helper1V61Error(Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH)
        elif name.startswith("approval/"):
            role = PurePosixPath(name).name.rsplit(".", 2)[0]
            if role not in KNOWN_ROLES or record["role"] != role:
                raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
            expected_media = ROLE_MEDIA_TYPES[role]
            if name.endswith(".payload.json") and record["media_type"] != expected_media:
                raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
            if name.endswith(".envelope.json") and record["media_type"] != "application/vnd.butler.helper1.evidence-envelope+json;v=1":
                raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
            try:
                canonicalize_butler_cj1(json.loads(raw))
            except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
                raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE) from exc


def verify_approval_input_bytes(
    artifact_bytes: bytes,
    provenance: ApprovalInputProvenanceV2,
    *,
    expected_repository_id: int,
    expected_repository_name: str,
    expected_subject_commit: str,
    expected_subject_tree: str,
    expected_run_id: int,
    expected_run_attempt: int,
    expected_workflow_ref: str,
    expected_workflow_id: int,
    expected_workflow_sha256: str,
    expected_artifact_id: int,
    expected_artifact_name: str,
    expected_canonical_subject_sha256: str,
) -> VerifiedApprovalInputV2:
    """Verify immutable bytes against independently supplied selection metadata."""
    if provenance.repository_id != expected_repository_id or provenance.repository_name != expected_repository_name:
        raise Helper1V61Error(Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH)
    if provenance.subject_commit != expected_subject_commit or provenance.subject_tree != expected_subject_tree:
        raise Helper1V61Error(Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH)
    if provenance.run_id != expected_run_id or provenance.run_attempt != expected_run_attempt:
        raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
    if (
        provenance.producer_workflow_ref != expected_workflow_ref
        or provenance.producer_workflow_id != expected_workflow_id
        or provenance.producer_workflow_sha256 != expected_workflow_sha256
    ):
        raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
    if provenance.artifact_id != expected_artifact_id or provenance.artifact_name != expected_artifact_name:
        raise Helper1V61Error(Helper1FailureCode.PRODUCER_RUN_MISMATCH)
    if provenance.canonical_subject_sha256 != expected_canonical_subject_sha256:
        raise Helper1V61Error(Helper1FailureCode.PRODUCER_SUBJECT_MISMATCH)
    if _digest(artifact_bytes) != provenance.artifact_sha256:
        raise Helper1V61Error(Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH)
    files = _read_zip_bytes(artifact_bytes)
    inventory_raw = files.get(INVENTORY_NAME)
    if inventory_raw is None or _digest(inventory_raw) != provenance.inventory_sha256:
        raise Helper1V61Error(Helper1FailureCode.ARTIFACT_DIGEST_MISMATCH)
    inventory = _load_inventory(inventory_raw)
    _verify_inventory(files, inventory)
    return VerifiedApprovalInputV2(
        provenance=provenance,
        inventory=inventory,
        files=dict(files),
    )


def inspect_approval_input_bytes(artifact_bytes: bytes) -> tuple[dict[str, Any], str]:
    """Validate archive structure and return its inventory plus byte digest."""
    files = _read_zip_bytes(artifact_bytes)
    inventory_raw = files.get(INVENTORY_NAME)
    if inventory_raw is None:
        raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
    inventory = _load_inventory(inventory_raw)
    _verify_inventory(files, inventory)
    return inventory, _digest(inventory_raw)


def provenance_from_dict(value: Mapping[str, object]) -> ApprovalInputProvenanceV2:
    if set(value) != {
        "schema_version",
        "mode",
        "repository_id",
        "repository_name",
        "subject_commit",
        "subject_tree",
        "producer_workflow_ref",
        "producer_workflow_id",
        "producer_workflow_sha256",
        "run_id",
        "run_attempt",
        "event_name",
        "artifact_id",
        "artifact_name",
        "artifact_sha256",
        "inventory_sha256",
        "canonical_subject_sha256",
    }:
        raise Helper1V61Error(Helper1FailureCode.INVENTORY_INCOMPLETE)
    return ApprovalInputProvenanceV2(**dict(value))  # type: ignore[arg-type]
