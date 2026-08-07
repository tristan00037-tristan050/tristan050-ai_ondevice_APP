#!/usr/bin/env python3
"""Assemble and verify the product-approval inventory embedded in Helper1 packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.helper1.approval_closure import (  # noqa: E402
    REQUIRED_EVIDENCE_ROLES,
    THRESHOLD_POLICY_ROLE,
)

SCHEMA = "butler.helper1.product-approval-bundle.v1"
MANIFEST_NAME = "MANIFEST.json"
LEGACY_FILES = (
    "APPROVED_ASSET_CLOSURE.json",
    "REAL_ASSET_E2E_RECEIPT.json",
    "M3_M4_MEASUREMENT.json",
    "MACOS_SANDBOX_E2E_RECEIPT.json",
)
APPROVAL_ROLES = (*REQUIRED_EVIDENCE_ROLES, THRESHOLD_POLICY_ROLE)
APPROVAL_FILES = tuple(
    sorted(
        ["ACTIVATION_GRANT.json"]
        + [
            filename
            for role in APPROVAL_ROLES
            for filename in (f"{role}.envelope.json", f"{role}.payload.json")
        ]
    )
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class ProductApprovalBundleError(RuntimeError):
    pass


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _record(raw: bytes) -> dict[str, object]:
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "mode": "0644"}


def _read_regular(path: Path, code: str) -> bytes:
    try:
        info = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(info.st_mode)
            or not 0 < info.st_size <= MAX_FILE_BYTES
            or info.st_mode & 0o022
        ):
            raise ProductApprovalBundleError(code)
        raw = path.read_bytes()
    except OSError as exc:
        raise ProductApprovalBundleError(code) from exc
    return raw


def _exact_directory(root: Path, expected: set[str], code: str) -> None:
    try:
        info = root.lstat()
        if root.is_symlink() or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o002:
            raise ProductApprovalBundleError(code)
        observed = {item.name for item in root.iterdir()}
    except OSError as exc:
        raise ProductApprovalBundleError(code) from exc
    if observed != expected:
        raise ProductApprovalBundleError(code)


def _read_source(source_root: Path, *, manifest_present: bool = False) -> dict[str, bytes]:
    legacy_root = source_root / "legacy"
    approval_root = source_root / "approval"
    objects_root = source_root / "objects"
    expected_root = {"legacy", "approval", "objects"}
    if manifest_present:
        expected_root.add(MANIFEST_NAME)
    _exact_directory(source_root, expected_root, "PRODUCT_APPROVAL_INVENTORY_INVALID")
    _exact_directory(legacy_root, set(LEGACY_FILES), "PRODUCT_APPROVAL_LEGACY_INVENTORY_INVALID")
    _exact_directory(approval_root, set(APPROVAL_FILES), "PRODUCT_APPROVAL_ROLE_INVENTORY_INVALID")
    try:
        object_names = {item.name for item in objects_root.iterdir()}
    except OSError as exc:
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_OBJECT_INVENTORY_INVALID") from exc
    if not object_names or any(SHA256.fullmatch(name) is None for name in object_names):
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_OBJECT_INVENTORY_INVALID")
    _exact_directory(objects_root, object_names, "PRODUCT_APPROVAL_OBJECT_INVENTORY_INVALID")

    files: dict[str, bytes] = {}
    total = 0
    for directory, names in (
        (legacy_root, LEGACY_FILES),
        (approval_root, APPROVAL_FILES),
        (objects_root, tuple(sorted(object_names))),
    ):
        prefix = directory.name
        for name in names:
            raw = _read_regular(directory / name, "PRODUCT_APPROVAL_FILE_INVALID")
            if prefix == "objects" and hashlib.sha256(raw).hexdigest() != name:
                raise ProductApprovalBundleError("PRODUCT_APPROVAL_OBJECT_DIGEST_MISMATCH")
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ProductApprovalBundleError("PRODUCT_APPROVAL_BUNDLE_TOO_LARGE")
            files[f"{prefix}/{name}"] = raw
    return files


def build_manifest(
    files: Mapping[str, bytes],
    *,
    subject_commit: str,
    subject_tree: str,
    producer_run: str,
) -> dict[str, Any]:
    if (
        SHA40.fullmatch(subject_commit) is None
        or SHA40.fullmatch(subject_tree) is None
        or not producer_run
    ):
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_SUBJECT_INVALID")
    expected = {
        *(f"legacy/{name}" for name in LEGACY_FILES),
        *(f"approval/{name}" for name in APPROVAL_FILES),
    }
    observed = set(files)
    object_names = {name for name in observed if name.startswith("objects/")}
    if observed != expected | object_names or not object_names:
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_INVENTORY_INVALID")
    if any(
        PurePosixPath(name).parts != ("objects", PurePosixPath(name).name)
        or SHA256.fullmatch(PurePosixPath(name).name) is None
        or hashlib.sha256(files[name]).hexdigest() != PurePosixPath(name).name
        for name in object_names
    ):
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_OBJECT_DIGEST_MISMATCH")
    return {
        "schema_version": SCHEMA,
        "subject_commit": subject_commit,
        "subject_tree": subject_tree,
        "producer_run": producer_run,
        "files": {name: _record(raw) for name, raw in sorted(files.items())},
    }


def verify_files(
    files: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    *,
    subject_commit: str,
    subject_tree: str,
    producer_run: str,
) -> None:
    expected_manifest = build_manifest(
        files,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
        producer_run=producer_run,
    )
    if dict(manifest) != expected_manifest:
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_MANIFEST_UNBOUND")


def assemble(
    source_root: Path,
    output_root: Path,
    *,
    subject_commit: str,
    subject_tree: str,
    producer_run: str,
) -> dict[str, Any]:
    files = _read_source(source_root)
    manifest = build_manifest(
        files,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
        producer_run=producer_run,
    )
    if output_root.exists() or output_root.is_symlink():
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_OUTPUT_EXISTS")
    temporary = output_root.with_name(f".{output_root.name}.tmp-{os.getpid()}")
    try:
        temporary.mkdir(parents=True, mode=0o700)
        for name, raw in sorted(files.items()):
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(raw)
            target.chmod(0o600)
        (temporary / MANIFEST_NAME).write_bytes(canonical_json(manifest) + b"\n")
        (temporary / MANIFEST_NAME).chmod(0o600)
        os.replace(temporary, output_root)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def load_bundle(
    root: Path,
    *,
    subject_commit: str,
    subject_tree: str,
    producer_run: str,
) -> dict[str, bytes]:
    try:
        manifest_raw = _read_regular(root / MANIFEST_NAME, "PRODUCT_APPROVAL_MANIFEST_INVALID")
        manifest = json.loads(manifest_raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_MANIFEST_INVALID") from exc
    if type(manifest) is not dict:
        raise ProductApprovalBundleError("PRODUCT_APPROVAL_MANIFEST_INVALID")
    files = _read_source(root, manifest_present=True)
    verify_files(
        files,
        manifest,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
        producer_run=producer_run,
    )
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--subject-commit", required=True)
    parser.add_argument("--subject-tree", required=True)
    parser.add_argument("--producer-run", required=True)
    args = parser.parse_args()
    try:
        assemble(
            args.source_root,
            args.output_root,
            subject_commit=args.subject_commit,
            subject_tree=args.subject_tree,
            producer_run=args.producer_run,
        )
        print("HELPER1_PRODUCT_APPROVAL_BUNDLE_OK=1")
        print("ERROR_CODE=NONE")
        return 0
    except (OSError, ProductApprovalBundleError) as exc:
        print("HELPER1_PRODUCT_APPROVAL_BUNDLE_OK=0")
        print(
            f"ERROR_CODE={exc if isinstance(exc, ProductApprovalBundleError) else 'PRODUCT_APPROVAL_BUNDLE_IO_FAILED'}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
