#!/usr/bin/env python3
"""Build and verify the fixed-path Helper1 producer package."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_helper1_v51_package import _load_protected_chain_authority  # noqa: E402
from scripts.ci.helper1_product_approval_bundle import (  # noqa: E402
    MANIFEST_NAME as PRODUCT_MANIFEST_NAME,
    ProductApprovalBundleError,
    load_bundle as load_product_approval_bundle,
    verify_files as verify_product_approval_files,
)
from butler_pc_core.helper1.approval_input import (  # noqa: E402
    provenance_from_dict,
    verify_approval_input_bytes,
)
from butler_pc_core.helper1.quality_evidence import (  # noqa: E402
    QualityEvidenceError,
    load_quality_directory,
    verify_manifest as verify_quality_manifest,
)
from scripts.ci.helper1_protected_bootstrap import (  # noqa: E402
    PRODUCER_WORKFLOW_ID,
    PRODUCER_WORKFLOW_PATH,
    ProtectedBootstrapError,
    VerifiedUntrustedArtifact,
    build_bootstrap_receipts,
    verify_untrusted_artifact,
)

POLICY_PATH = ROOT / "contracts/helper1/trusted-verifier-policy-v1.json"
PACKAGE_RELATIVE = PurePosixPath("package/helper1-v51.zip")
DESCRIPTOR_RELATIVE = PurePosixPath("package/helper1-v51.candidate.json")
ZIP_ROOT = "helper1-v51"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 1024 * 1024
MAX_EVIDENCE_BYTES = 256 * 1024 * 1024
MAX_PACKAGE_BYTES = 320 * 1024 * 1024
EXPECTED_LANES = {
    "desktop-helper1-v51": "PASSED",
    "native-macos-helper1-v51": "BLOCKED",
    "python-helper1-protected-replay": "PASSED",
    "python-helper1-v4-original": "PASSED",
    "python-helper1-v51-targeted": "PASSED",
    "python-helper1-v61-quality": "PASSED",
}
EXPECTED_CHECKS = {
    "desktop-lock-install-v51",
    "desktop-typecheck-v51",
    "git-diff-check-v51",
    "helper1-mutation-gate-v51",
    "helper1-static-verifier-v51",
    "python-compileall-v51",
    "python-helper1-collect-v51",
}
APPROVAL_PRODUCER_REPOSITORY_ID = 1097940756
# The protected bootstrap has one measured source identity. A separate approval
# producer is deliberately not trusted until it is folded into the protected path.
APPROVAL_PRODUCER_WORKFLOW_ID = PRODUCER_WORKFLOW_ID
LEGACY_APPROVAL_WORKFLOW_ID = 0
LEGACY_APPROVAL_WORKFLOW_PATH = ".github/workflows/helper1-v2-approval-evidence.yml"
LEGACY_APPROVAL_WORKFLOW_SHA256 = (
    "51e951131bf4e0881d1abfc660fc6d9c1f9137899e06a46bf7e7b6045164cd77"
)


class ProducerPackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedProducerPackage:
    package_sha256: str
    chain_authority_sha256: str
    subject_commit: str
    subject_tree: str
    producer_run: str
    test_evidence: Mapping[str, bytes]
    legacy_evidence: Mapping[str, bytes]
    approval_files: Mapping[str, bytes]
    objects: Mapping[str, bytes]
    quality_evidence: Mapping[str, bytes]
    bootstrap_receipts: Mapping[str, bytes]
    manifest: Mapping[str, Any]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _decode_json(raw: bytes, code: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProducerPackageError(code)
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ProducerPackageError(code) from exc
    if type(value) is not dict:
        raise ProducerPackageError(code)
    return value


def _load_json(path: Path, code: str) -> tuple[dict[str, Any], bytes]:
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or not 0 < info.st_size <= MAX_JSON_BYTES:
            raise ProducerPackageError(code)
        raw = path.read_bytes()
    except OSError as exc:
        raise ProducerPackageError(code) from exc
    return _decode_json(raw, code), raw


def _canonical_producer_workflow_identity(
    policy: Mapping[str, Any],
) -> tuple[str, str]:
    path = policy.get("quality_producer_workflow_path")
    digest = policy.get("quality_producer_workflow_sha256")
    components = policy.get("protected_components_sha256")
    if (
        path != PRODUCER_WORKFLOW_PATH
        or type(digest) is not str
        or not digest.startswith("sha256:")
        or SHA256.fullmatch(digest.removeprefix("sha256:")) is None
        or type(components) is not dict
        or components.get(path) != digest
    ):
        raise ProducerPackageError("PRODUCER_PACKAGE_POLICY_INVALID")
    return path, digest.removeprefix("sha256:")


def _policy() -> tuple[dict[str, Any], bytes]:
    policy, raw = _load_json(POLICY_PATH, "PRODUCER_PACKAGE_POLICY_INVALID")
    _canonical_producer_workflow_identity(policy)
    contract = policy.get("producer_package_contract")
    if (
        type(policy.get("enabled")) is not bool
        or type(contract) is not dict
        or set(contract) != {
            "schema_version",
            "chain_id",
            "candidate_generation",
            "package_relative_path",
            "descriptor_relative_path",
            "immediate_predecessor",
            "rollback_record",
        }
        or contract.get("schema_version") != "butler.helper1.producer-package-contract.v1"
        or contract.get("chain_id") != "helper1-v51-a4-closure"
        or contract.get("candidate_generation") != 15
        or contract.get("package_relative_path") != PACKAGE_RELATIVE.as_posix()
        or contract.get("descriptor_relative_path") != DESCRIPTOR_RELATIVE.as_posix()
        or not _valid_record(contract.get("immediate_predecessor"), 14)
        or not _valid_record(contract.get("rollback_record"), 13)
        or contract["immediate_predecessor"] == contract["rollback_record"]
    ):
        raise ProducerPackageError("PRODUCER_PACKAGE_POLICY_INVALID")
    return contract, raw


def _valid_record(value: object, generation: int) -> bool:
    return (
        type(value) is dict
        and set(value) == {"generation", "package_sha256", "result_tree"}
        and value.get("generation") == generation
        and type(value.get("package_sha256")) is str
        and SHA256.fullmatch(value["package_sha256"]) is not None
        and type(value.get("result_tree")) is str
        and SHA40.fullmatch(value["result_tree"]) is not None
    )


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ProducerPackageError("PRODUCER_PACKAGE_PATH_INVALID")
    return path.as_posix()


def _approval_workflow_ref(value: object, repository: object) -> str:
    if type(value) is not str or type(repository) is not str:
        raise ProducerPackageError("APPROVAL_INPUT_INVALID")
    prefix = f"{repository}/{LEGACY_APPROVAL_WORKFLOW_PATH}@"
    if not value.startswith(prefix) or SHA40.fullmatch(value.removeprefix(prefix)) is None:
        raise ProducerPackageError("APPROVAL_INPUT_INVALID")
    return value


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(ROOT), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise ProducerPackageError("PRODUCER_SUBJECT_GIT_INVALID")
    return completed.stdout.decode("utf-8").strip()


def _subject(path: Path, *, require_head: bool) -> tuple[dict[str, Any], bytes, str]:
    subject, raw = _load_json(path, "PRODUCER_SUBJECT_INVALID")
    commit = subject.get("subject_sha")
    if (
        subject.get("schema_version") != "butler.helper1.canonical-subject.v1"
        or subject.get("repository_full_name")
        != "tristan00037-tristan050/tristan050-ai_ondevice_APP"
        or type(commit) is not str
        or SHA40.fullmatch(commit) is None
    ):
        raise ProducerPackageError("PRODUCER_SUBJECT_INVALID")
    if require_head and _git("rev-parse", "HEAD") != commit:
        raise ProducerPackageError("PRODUCER_SUBJECT_COMMIT_MISMATCH")
    tree = _git("rev-parse", f"{commit}^{{tree}}")
    if SHA40.fullmatch(tree) is None:
        raise ProducerPackageError("PRODUCER_SUBJECT_TREE_INVALID")
    return subject, raw, tree


def _evidence_files(root: Path, expected_tree: str) -> dict[str, bytes]:
    index_path = root / "TEST_EVIDENCE_INDEX.v1.json"
    index, _raw = _load_json(index_path, "PRODUCER_EVIDENCE_INVALID")
    lanes = index.get("lanes")
    checks = index.get("checks")
    lane_statuses = (
        {item.get("lane_id"): item.get("status") for item in lanes}
        if type(lanes) is list and all(type(item) is dict for item in lanes)
        else {}
    )
    check_statuses = (
        {item.get("check_id"): item.get("status") for item in checks}
        if type(checks) is list and all(type(item) is dict for item in checks)
        else {}
    )
    if (
        index.get("schema_version") != "butler.helper1.test-evidence-index.v1"
        or index.get("source_tree") != expected_tree
        or index.get("all_required_checks_passed") is not True
        or index.get("all_required_lanes_passed") is not False
        or index.get("required_lanes_blocked") != 1
        or len(lane_statuses) != len(lanes or ())
        or lane_statuses != EXPECTED_LANES
        or len(check_statuses) != len(checks or ())
        or set(check_statuses) != EXPECTED_CHECKS
        or set(check_statuses.values()) != {"PASSED"}
    ):
        raise ProducerPackageError("PRODUCER_EVIDENCE_INVALID")
    files: dict[str, bytes] = {}
    total = 0
    try:
        candidates = sorted(root.rglob("*"))
    except OSError as exc:
        raise ProducerPackageError("PRODUCER_EVIDENCE_INVALID") from exc
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or (path.exists() and not path.is_file() and not path.is_dir()):
            raise ProducerPackageError("PRODUCER_EVIDENCE_TYPE_INVALID")
        if path.is_dir():
            continue
        name = _safe_relative(relative)
        raw = path.read_bytes()
        total += len(raw)
        if total > MAX_EVIDENCE_BYTES:
            raise ProducerPackageError("PRODUCER_EVIDENCE_TOO_LARGE")
        files[f"TEST_EVIDENCE/{name}"] = raw
    if "TEST_EVIDENCE/TEST_EVIDENCE_INDEX.v1.json" not in files:
        raise ProducerPackageError("PRODUCER_EVIDENCE_INVALID")
    return files


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(f"{ZIP_ROOT}/{name}", ZIP_TIME)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _event_path() -> Path:
    value = os.environ.get("GITHUB_EVENT_PATH")
    if not value:
        raise ProducerPackageError("WORKFLOW_EVENT_UNAVAILABLE")
    return Path(value)


def _write_package_files(
    artifact_root: Path,
    files: Mapping[str, bytes],
    *,
    contract: Mapping[str, Any],
    subject_commit: str,
    subject_tree: str,
) -> dict[str, Any]:
    package_path = artifact_root / PACKAGE_RELATIVE
    descriptor_path = artifact_root / DESCRIPTOR_RELATIVE
    package_dir = package_path.parent
    if (
        artifact_root.is_symlink()
        or (artifact_root.exists() and not artifact_root.is_dir())
        or package_dir.is_symlink()
        or (package_dir.exists() and not package_dir.is_dir())
        or package_path.exists()
        or package_path.is_symlink()
        or descriptor_path.exists()
        or descriptor_path.is_symlink()
    ):
        raise ProducerPackageError("PRODUCER_PACKAGE_OUTPUT_INVALID")
    package_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = package_path.with_name(f".{package_path.name}.tmp")
    try:
        descriptor_fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        with os.fdopen(descriptor_fd, "w+b") as stream:
            with zipfile.ZipFile(
                stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for name, raw in sorted(files.items()):
                    archive.writestr(_zip_info(name), raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, package_path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    package_digest = hashlib.sha256(_freeze_package(package_path)).hexdigest()
    descriptor = _derived_descriptor(
        contract,
        package_sha256=package_digest,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
    )
    _atomic_write(descriptor_path, _canonical(descriptor) + b"\n")
    return descriptor


def build_protected_bootstrap_package(
    artifact_root: Path,
    event_path: Path,
    *,
    request_json=None,
    request_archive=None,
) -> tuple[VerifiedUntrustedArtifact, dict[str, Any]]:
    """Turn downloaded raw material into a non-release protected-side package."""
    contract, policy_raw = _policy()
    policy = _decode_json(policy_raw, "PRODUCER_PACKAGE_POLICY_INVALID")
    try:
        verified = verify_untrusted_artifact(
            artifact_root,
            event_path,
            policy,
            request_json=request_json,
            request_archive=request_archive,
        )
        receipts = build_bootstrap_receipts(
            verified,
            policy_enabled=policy["enabled"],
        )
    except ProtectedBootstrapError as exc:
        raise ProducerPackageError(str(exc)) from exc
    files = {
        "SUBJECT/CANONICAL_SUBJECT.json": verified.subject_raw,
        "SUBJECT/SUBMISSION.json": verified.submission_raw,
        **{
            f"TEST_EVIDENCE/{name}": raw
            for name, raw in sorted(verified.test_files.items())
        },
        **{
            f"PROTECTED_BOOTSTRAP/{name}": raw
            for name, raw in sorted(receipts.items())
        },
    }
    manifest = {
        "schema_version": "butler.helper1.producer-package.v4-bootstrap",
        "subject_commit": verified.subject["subject_sha"],
        "subject_tree": verified.source_tree,
        "producer_run": verified.producer_run,
        "policy_sha256": hashlib.sha256(policy_raw).hexdigest(),
        "release_eligible": False,
        "files": {
            name: {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "mode": "0644",
            }
            for name, raw in sorted(files.items())
        },
    }
    files["MANIFEST.json"] = _canonical(manifest)
    files["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(raw).hexdigest()}  {name}\n"
        for name, raw in sorted(files.items())
    ).encode("utf-8")
    descriptor = _write_package_files(
        artifact_root,
        files,
        contract=contract,
        subject_commit=verified.subject["subject_sha"],
        subject_tree=verified.source_tree,
    )
    return verified, descriptor


def build(
    artifact_root: Path,
    canonical_subject: Path,
    submission_path: Path,
    evidence_root: Path,
    product_approval_root: Path,
    quality_evidence_root: Path,
    approval_input_artifact: Path | None = None,
    approval_input_provenance: Path | None = None,
) -> dict[str, Any]:
    contract, policy_raw = _policy()
    subject, subject_raw, subject_tree = _subject(canonical_subject, require_head=True)
    submission, submission_raw = _load_json(submission_path, "PRODUCER_SUBMISSION_INVALID")
    if (
        submission.get("schema_version") != "butler.helper1.untrusted-submission.v1"
        or submission.get("subject_commit") != subject["subject_sha"]
        or submission.get("canonical_subject_sha256")
        != hashlib.sha256(_canonical(subject)).hexdigest()
        or submission.get("product_evidence_present") is not True
        or type(submission.get("run_id")) is not str
        or not submission["run_id"]
    ):
        raise ProducerPackageError("PRODUCER_SUBMISSION_INVALID")
    package_path = artifact_root / PACKAGE_RELATIVE
    descriptor_path = artifact_root / DESCRIPTOR_RELATIVE
    if artifact_root.is_symlink() or (artifact_root.exists() and not artifact_root.is_dir()):
        raise ProducerPackageError("PRODUCER_PACKAGE_OUTPUT_INVALID")
    package_dir = package_path.parent
    if package_dir.is_symlink() or (package_dir.exists() and not package_dir.is_dir()):
        raise ProducerPackageError("PRODUCER_PACKAGE_OUTPUT_INVALID")
    if package_path.exists() or package_path.is_symlink() or descriptor_path.exists() or descriptor_path.is_symlink():
        raise ProducerPackageError("PRODUCER_PACKAGE_OUTPUT_EXISTS")
    try:
        product_files = load_product_approval_bundle(
            product_approval_root,
            subject_commit=subject["subject_sha"],
            subject_tree=subject_tree,
            producer_run=submission["run_id"],
        )
    except ProductApprovalBundleError as exc:
        raise ProducerPackageError(str(exc)) from exc
    try:
        quality_files = load_quality_directory(quality_evidence_root)
    except QualityEvidenceError as exc:
        raise ProducerPackageError(str(exc)) from exc
    files = {
        "SUBJECT/CANONICAL_SUBJECT.json": subject_raw,
        "SUBJECT/SUBMISSION.json": submission_raw,
        **_evidence_files(evidence_root, subject_tree),
        **{
            f"PRODUCT_APPROVAL/{name}": raw
            for name, raw in sorted(product_files.items())
        },
        f"PRODUCT_APPROVAL/{PRODUCT_MANIFEST_NAME}": (
            product_approval_root / PRODUCT_MANIFEST_NAME
        ).read_bytes(),
        **{
            f"SEARCH_QUALITY/{name}": raw
            for name, raw in sorted(quality_files.items())
        },
    }
    if approval_input_artifact is None or approval_input_provenance is None:
        raise ProducerPackageError("APPROVAL_INPUT_INCOMPLETE")
    try:
        approval_bytes = approval_input_artifact.read_bytes()
        provenance_bytes = approval_input_provenance.read_bytes()
        provenance_value = _decode_json(
            provenance_bytes,
            "APPROVAL_INPUT_PROVENANCE_INVALID",
        )
        provenance = provenance_from_dict(provenance_value)
        workflow_ref = _approval_workflow_ref(
            provenance.producer_workflow_ref,
            subject["repository_full_name"],
        )
        verify_approval_input_bytes(
            approval_bytes,
            provenance,
            expected_repository_id=APPROVAL_PRODUCER_REPOSITORY_ID,
            expected_repository_name=subject["repository_full_name"],
            expected_subject_commit=subject["subject_sha"],
            expected_subject_tree=subject_tree,
            expected_run_id=provenance.run_id,
            expected_run_attempt=provenance.run_attempt,
            expected_workflow_ref=workflow_ref,
            expected_workflow_id=LEGACY_APPROVAL_WORKFLOW_ID,
            expected_workflow_sha256=LEGACY_APPROVAL_WORKFLOW_SHA256,
            expected_artifact_id=provenance.artifact_id,
            expected_artifact_name=provenance.artifact_name,
            expected_canonical_subject_sha256=hashlib.sha256(
                _canonical(subject)
            ).hexdigest(),
        )
    except Exception as exc:
        raise ProducerPackageError("APPROVAL_INPUT_INVALID") from exc
    files["APPROVAL_INPUT/approval-input.zip"] = approval_bytes
    files["APPROVAL_INPUT/APPROVAL_INPUT_PROVENANCE.v2.json"] = provenance_bytes
    manifest = {
        "schema_version": "butler.helper1.producer-package.v3",
        "subject_commit": subject["subject_sha"],
        "subject_tree": subject_tree,
        "policy_sha256": hashlib.sha256(policy_raw).hexdigest(),
        "files": {
            name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "mode": "0644"}
            for name, raw in sorted(files.items())
        },
    }
    files["MANIFEST.json"] = _canonical(manifest)
    files["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(raw).hexdigest()}  {name}\n"
        for name, raw in sorted(files.items())
    ).encode("utf-8")
    package_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = package_path.with_name(f".{package_path.name}.tmp")
    try:
        descriptor_fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0), 0o600
        )
        with os.fdopen(descriptor_fd, "w+b") as stream:
            with zipfile.ZipFile(
                stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for name, raw in sorted(files.items()):
                    archive.writestr(_zip_info(name), raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, package_path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    package_digest = hashlib.sha256(_freeze_package(package_path)).hexdigest()
    descriptor = _derived_descriptor(
        contract,
        package_sha256=package_digest,
        subject_commit=subject["subject_sha"],
        subject_tree=subject_tree,
    )
    _atomic_write(descriptor_path, _canonical(descriptor) + b"\n")
    return descriptor


def _freeze_regular_file(
    path: Path,
    *,
    max_bytes: int,
    missing_code: str,
    changed_code: str,
) -> bytes:
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= max_bytes:
                raise ProducerPackageError(missing_code)
            raw = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or len(raw) != before.st_size:
            raise ProducerPackageError(changed_code)
        return raw
    except OSError as exc:
        raise ProducerPackageError(missing_code) from exc


def _freeze_package(path: Path) -> bytes:
    return _freeze_regular_file(
        path,
        max_bytes=MAX_PACKAGE_BYTES,
        missing_code="PRODUCER_PACKAGE_MISSING",
        changed_code="PRODUCER_PACKAGE_CHANGED_DURING_READ",
    )


def verify_protected_package_layout(package_path: Path) -> None:
    """Require the exact package produced inside the protected verifier."""
    package_dir = package_path.parent
    artifact_root = package_dir.parent
    try:
        if (
            package_path.name != "helper1-v51.zip"
            or package_dir.name != "package"
            or package_dir.is_symlink()
            or artifact_root.is_symlink()
            or not package_dir.is_dir()
            or not artifact_root.is_dir()
        ):
            raise ProducerPackageError("PRODUCER_ARTIFACT_LAYOUT_INVALID")
        root_names = {item.name for item in artifact_root.iterdir()}
        package_names = {item.name for item in package_dir.iterdir()}
    except OSError as exc:
        raise ProducerPackageError("PRODUCER_ARTIFACT_LAYOUT_INVALID") from exc
    raw_roots = {"CANONICAL_SUBJECT.json", "SUBMISSION.json", "test-evidence", "package"}
    if root_names not in ({"package"}, raw_roots) or package_names != {
        "helper1-v51.zip",
        "helper1-v51.candidate.json",
    }:
        raise ProducerPackageError("PRODUCER_ARTIFACT_LAYOUT_INVALID")


def _read_package_bytes(raw: bytes) -> tuple[dict[str, bytes], dict[str, Any]]:
    try:
        if not 0 < len(raw) <= MAX_PACKAGE_BYTES:
            raise ProducerPackageError("PRODUCER_PACKAGE_MISSING")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names: list[str] = []
            folded_names: set[str] = set()
            files: dict[str, bytes] = {}
            uncompressed_total = 0
            for item in members:
                name = _safe_relative(item.filename)
                parts = PurePosixPath(name).parts
                mode = item.external_attr >> 16
                folded = name.casefold()
                uncompressed_total += item.file_size
                if (
                    len(parts) < 2
                    or parts[0] != ZIP_ROOT
                    or name in names
                    or folded in folded_names
                    or item.is_dir()
                    or not stat.S_ISREG(mode)
                    or stat.S_IMODE(mode) != 0o644
                    or item.date_time != ZIP_TIME
                    or item.extra
                    or uncompressed_total > MAX_EVIDENCE_BYTES + (4 * MAX_JSON_BYTES)
                ):
                    raise ProducerPackageError("PRODUCER_PACKAGE_ARCHIVE_INVALID")
                names.append(name)
                folded_names.add(folded)
                files[PurePosixPath(*parts[1:]).as_posix()] = archive.read(item)
            if names != sorted(names):
                raise ProducerPackageError("PRODUCER_PACKAGE_ARCHIVE_INVALID")
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        if isinstance(exc, ProducerPackageError):
            raise
        raise ProducerPackageError("PRODUCER_PACKAGE_ARCHIVE_INVALID") from exc
    try:
        manifest = _decode_json(
            files["MANIFEST.json"], "PRODUCER_PACKAGE_MANIFEST_INVALID"
        )
        sums = {
            line.split("  ", 1)[1]: line.split("  ", 1)[0]
            for line in files["SHA256SUMS.txt"].decode("utf-8").splitlines()
        }
    except (KeyError, UnicodeError, ValueError) as exc:
        raise ProducerPackageError("PRODUCER_PACKAGE_MANIFEST_INVALID") from exc
    payload = set(files) - {"MANIFEST.json", "SHA256SUMS.txt"}
    expected_files = manifest.get("files")
    if (
        manifest.get("schema_version")
        not in {
            "butler.helper1.producer-package.v1",
            "butler.helper1.producer-package.v2",
            "butler.helper1.producer-package.v3",
            "butler.helper1.producer-package.v4-bootstrap",
        }
        or type(expected_files) is not dict
        or set(expected_files) != payload
        or set(sums) != set(files) - {"SHA256SUMS.txt"}
        or any(
            expected_files[name]
            != {"bytes": len(files[name]), "sha256": hashlib.sha256(files[name]).hexdigest(), "mode": "0644"}
            for name in payload
        )
        or any(hashlib.sha256(files[name]).hexdigest() != digest for name, digest in sums.items())
    ):
        raise ProducerPackageError("PRODUCER_PACKAGE_MANIFEST_INVALID")
    return files, manifest


def _read_package(path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    return _read_package_bytes(_freeze_package(path))


def _derived_descriptor(
    contract: Mapping[str, Any],
    *,
    package_sha256: str,
    subject_commit: str,
    subject_tree: str,
) -> dict[str, Any]:
    return {
        "schema_version": "butler.helper1.handoff-chain-candidate.v2",
        "chain_id": contract["chain_id"],
        "successor_generation": contract["candidate_generation"],
        "package_relative_path": PACKAGE_RELATIVE.as_posix(),
        "package_sha256": package_sha256,
        "subject_commit": subject_commit,
        "subject_tree": subject_tree,
        "immediate_predecessor": contract["immediate_predecessor"],
        "rollback_record": contract["rollback_record"],
        "authority_state": "UNCONFIGURED",
        "signature_state": "MISSING",
        "provenance_state": "UNVERIFIED",
    }


def _verify_bootstrap_receipts(
    files: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
    subject_commit: str,
    subject_tree: str,
    producer_run: str,
) -> dict[str, bytes]:
    if policy.get("enabled") is not False:
        raise ProducerPackageError("BOOTSTRAP_PACKAGE_FORBIDDEN_WHEN_POLICY_ENABLED")
    workflow_path, workflow_sha256 = _canonical_producer_workflow_identity(policy)
    names = {
        name.removeprefix("PROTECTED_BOOTSTRAP/"): raw
        for name, raw in files.items()
        if name.startswith("PROTECTED_BOOTSTRAP/")
    }
    if set(names) != {
        "RAW_ARTIFACT_PROVENANCE.v1.json",
        "QUALITY_MEASUREMENT.v1.json",
        "APPROVAL_RECEIPT.v1.json",
    }:
        raise ProducerPackageError("BOOTSTRAP_RECEIPT_INVENTORY_INVALID")
    provenance = _decode_json(
        names["RAW_ARTIFACT_PROVENANCE.v1.json"],
        "BOOTSTRAP_PROVENANCE_INVALID",
    )
    quality = _decode_json(
        names["QUALITY_MEASUREMENT.v1.json"],
        "BOOTSTRAP_QUALITY_INVALID",
    )
    approval = _decode_json(
        names["APPROVAL_RECEIPT.v1.json"],
        "BOOTSTRAP_APPROVAL_INVALID",
    )
    test_index_raw = files.get("TEST_EVIDENCE/TEST_EVIDENCE_INDEX.v1.json")
    if test_index_raw is None:
        raise ProducerPackageError("PRODUCER_EVIDENCE_INVALID")
    test_index = _decode_json(test_index_raw, "PRODUCER_EVIDENCE_INVALID")
    if (
        manifest.get("release_eligible") is not False
        or manifest.get("producer_run") != producer_run
        or provenance.get("schema_version")
        != "butler.helper1.untrusted-artifact-provenance.v1"
        or provenance.get("repository_id") != APPROVAL_PRODUCER_REPOSITORY_ID
        or provenance.get("repository") != policy.get("repository")
        or provenance.get("subject_commit") != subject_commit
        or provenance.get("subject_tree") != subject_tree
        or provenance.get("producer_run") != producer_run
        or provenance.get("producer_workflow_id") != APPROVAL_PRODUCER_WORKFLOW_ID
        or provenance.get("producer_workflow_path") != workflow_path
        or provenance.get("producer_workflow_sha256") != workflow_sha256
        or provenance.get("test_evidence_index_sha256")
        != hashlib.sha256(test_index_raw).hexdigest()
        or quality.get("schema_version")
        != "butler.helper1.protected-bootstrap-quality.v1"
        or quality.get("subject_commit") != subject_commit
        or quality.get("subject_tree") != subject_tree
        or quality.get("producer_run") != producer_run
        or quality.get("provenance_sha256")
        != hashlib.sha256(names["RAW_ARTIFACT_PROVENANCE.v1.json"]).hexdigest()
        or quality.get("all_required_checks_passed")
        is not test_index.get("all_required_checks_passed")
        or quality.get("all_required_lanes_passed")
        is not test_index.get("all_required_lanes_passed")
        or quality.get("required_lanes_blocked")
        != test_index.get("required_lanes_blocked")
        or quality.get("quality_approved") != 0
        or quality.get("state") != "UNAPPROVED"
        or quality.get("reason_code")
        != "PROTECTED_QUALITY_APPROVAL_NOT_CONFIGURED"
        or approval.get("schema_version")
        != "butler.helper1.protected-bootstrap-approval.v1"
        or approval.get("subject_commit") != subject_commit
        or approval.get("subject_tree") != subject_tree
        or approval.get("producer_run") != producer_run
        or approval.get("quality_measurement_sha256")
        != hashlib.sha256(names["QUALITY_MEASUREMENT.v1.json"]).hexdigest()
        or approval.get("policy_enabled") is not False
        or approval.get("approval_values")
        != {
            "code_pass": 0,
            "external_handoff_allowed": 0,
            "product_release_allowed": 0,
            "production_claim_allowed": 0,
            "runtime_activation_allowed": 0,
        }
        or approval.get("state") != "UNSIGNED_ZERO"
        or approval.get("reason_code") != "TRUST_POLICY_DISABLED"
        or approval.get("signature_b64") is not None
    ):
        raise ProducerPackageError("BOOTSTRAP_RECEIPT_BINDING_INVALID")
    return names


def load_verified_package(
    package_path: Path,
    *,
    policy: Mapping[str, Any],
    policy_raw: bytes,
    require_authority: bool = True,
) -> VerifiedProducerPackage:
    """Freeze one package FD and derive every final-verdict input from those bytes."""
    _canonical_producer_workflow_identity(policy)
    verify_protected_package_layout(package_path)
    raw = _freeze_package(package_path)
    package_sha256 = hashlib.sha256(raw).hexdigest()
    files, manifest = _read_package_bytes(raw)
    contract = policy.get("producer_package_contract")
    if type(contract) is not dict:
        raise ProducerPackageError("PRODUCER_PACKAGE_POLICY_INVALID")
    try:
        subject = _decode_json(
            files["SUBJECT/CANONICAL_SUBJECT.json"], "PRODUCER_SUBJECT_INVALID"
        )
        submission = _decode_json(
            files["SUBJECT/SUBMISSION.json"], "PRODUCER_SUBMISSION_INVALID"
        )
    except KeyError as exc:
        raise ProducerPackageError("PRODUCER_PACKAGE_SUBJECT_MISMATCH") from exc
    subject_commit = subject.get("subject_sha")
    subject_tree = manifest.get("subject_tree")
    producer_run = submission.get("run_id")
    if (
        subject.get("schema_version") != "butler.helper1.canonical-subject.v1"
        or subject.get("repository_full_name") != policy.get("repository")
        or type(subject_commit) is not str
        or SHA40.fullmatch(subject_commit) is None
        or type(subject_tree) is not str
        or SHA40.fullmatch(subject_tree) is None
        or manifest.get("subject_commit") != subject_commit
        or manifest.get("policy_sha256") != hashlib.sha256(policy_raw).hexdigest()
        or submission.get("schema_version") != "butler.helper1.untrusted-submission.v1"
        or submission.get("subject_commit") != subject_commit
        or submission.get("canonical_subject_sha256")
        != hashlib.sha256(_canonical(subject)).hexdigest()
        or submission.get("product_evidence_present") is not True
        or type(producer_run) is not str
        or not producer_run
    ):
        raise ProducerPackageError("PRODUCER_PACKAGE_SUBJECT_MISMATCH")

    if manifest.get("schema_version") == "butler.helper1.producer-package.v4-bootstrap":
        try:
            observed_tree = _git("rev-parse", f"{subject_commit}^{{tree}}")
        except ProducerPackageError as exc:
            raise ProducerPackageError("PRODUCER_SUBJECT_GIT_INVALID") from exc
        if observed_tree != subject_tree:
            raise ProducerPackageError("PRODUCER_SUBJECT_TREE_MISMATCH")
        bootstrap = _verify_bootstrap_receipts(
            files,
            manifest,
            policy=policy,
            subject_commit=subject_commit,
            subject_tree=subject_tree,
            producer_run=producer_run,
        )
        test_evidence = {
            name.removeprefix("TEST_EVIDENCE/"): payload
            for name, payload in files.items()
            if name.startswith("TEST_EVIDENCE/")
        }
        descriptor = _derived_descriptor(
            contract,
            package_sha256=package_sha256,
            subject_commit=subject_commit,
            subject_tree=subject_tree,
        )
        observed_descriptor = _decode_json(
            _freeze_regular_file(
                package_path.with_name("helper1-v51.candidate.json"),
                max_bytes=MAX_JSON_BYTES,
                missing_code="PRODUCER_PACKAGE_DESCRIPTOR_MISSING",
                changed_code="PRODUCER_PACKAGE_DESCRIPTOR_CHANGED_DURING_READ",
            ),
            "PRODUCER_PACKAGE_DESCRIPTOR_INVALID",
        )
        if observed_descriptor != descriptor:
            raise ProducerPackageError("PRODUCER_PACKAGE_DESCRIPTOR_MISMATCH")
        return VerifiedProducerPackage(
            package_sha256=package_sha256,
            chain_authority_sha256="",
            subject_commit=subject_commit,
            subject_tree=subject_tree,
            producer_run=producer_run,
            test_evidence=MappingProxyType(test_evidence),
            legacy_evidence=MappingProxyType({}),
            approval_files=MappingProxyType({}),
            objects=MappingProxyType({}),
            quality_evidence=MappingProxyType({}),
            bootstrap_receipts=MappingProxyType(bootstrap),
            manifest=MappingProxyType(manifest),
        )

    try:
        test_index = _decode_json(
            files["TEST_EVIDENCE/TEST_EVIDENCE_INDEX.v1.json"],
            "PRODUCER_EVIDENCE_INVALID",
        )
        product_manifest = _decode_json(
            files[f"PRODUCT_APPROVAL/{PRODUCT_MANIFEST_NAME}"],
            "PRODUCT_APPROVAL_MANIFEST_INVALID",
        )
    except KeyError as exc:
        raise ProducerPackageError("PRODUCER_PACKAGE_INVENTORY_INVALID") from exc
    if manifest.get("schema_version") in {
        "butler.helper1.producer-package.v2",
        "butler.helper1.producer-package.v3",
    }:
        try:
            approval_provenance_value = _decode_json(
                files["APPROVAL_INPUT/APPROVAL_INPUT_PROVENANCE.v2.json"],
                "APPROVAL_INPUT_PROVENANCE_INVALID",
            )
            approval_provenance = provenance_from_dict(approval_provenance_value)
            workflow_ref = _approval_workflow_ref(
                approval_provenance.producer_workflow_ref,
                policy.get("repository"),
            )
            verify_approval_input_bytes(
                files["APPROVAL_INPUT/approval-input.zip"],
                approval_provenance,
                expected_repository_id=APPROVAL_PRODUCER_REPOSITORY_ID,
                expected_repository_name=policy["repository"],
                expected_subject_commit=subject_commit,
                expected_subject_tree=subject_tree,
                expected_run_id=approval_provenance.run_id,
                expected_run_attempt=approval_provenance.run_attempt,
                expected_workflow_ref=workflow_ref,
                expected_workflow_id=LEGACY_APPROVAL_WORKFLOW_ID,
                expected_workflow_sha256=LEGACY_APPROVAL_WORKFLOW_SHA256,
                expected_artifact_id=approval_provenance.artifact_id,
                expected_artifact_name=approval_provenance.artifact_name,
                expected_canonical_subject_sha256=hashlib.sha256(
                    _canonical(subject)
                ).hexdigest(),
            )
        except Exception as exc:
            raise ProducerPackageError("APPROVAL_INPUT_INVALID") from exc
    if (
        test_index.get("source_tree") != subject_tree
        or test_index.get("all_required_checks_passed") is not True
    ):
        raise ProducerPackageError("PRODUCER_EVIDENCE_INVALID")

    test_evidence = {
        name.removeprefix("TEST_EVIDENCE/"): payload
        for name, payload in files.items()
        if name.startswith("TEST_EVIDENCE/")
    }
    product_files = {
        name.removeprefix("PRODUCT_APPROVAL/"): payload
        for name, payload in files.items()
        if name.startswith("PRODUCT_APPROVAL/")
        and name != f"PRODUCT_APPROVAL/{PRODUCT_MANIFEST_NAME}"
    }
    try:
        verify_product_approval_files(
            product_files,
            product_manifest,
            subject_commit=subject_commit,
            subject_tree=subject_tree,
            producer_run=producer_run,
        )
    except ProductApprovalBundleError as exc:
        raise ProducerPackageError(str(exc)) from exc
    legacy = {
        name.removeprefix("legacy/"): payload
        for name, payload in product_files.items()
        if name.startswith("legacy/")
    }
    approval = {
        name.removeprefix("approval/"): payload
        for name, payload in product_files.items()
        if name.startswith("approval/")
    }
    objects = {
        name.removeprefix("objects/"): payload
        for name, payload in product_files.items()
        if name.startswith("objects/")
    }
    quality = {
        name.removeprefix("SEARCH_QUALITY/"): payload
        for name, payload in files.items()
        if name.startswith("SEARCH_QUALITY/")
    }
    if manifest.get("schema_version") == "butler.helper1.producer-package.v3":
        try:
            verify_quality_manifest(quality)
        except QualityEvidenceError as exc:
            raise ProducerPackageError(str(exc)) from exc
    elif quality:
        raise ProducerPackageError("QUALITY_INVENTORY_INVALID")
    descriptor = _derived_descriptor(
        contract,
        package_sha256=package_sha256,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
    )
    observed_descriptor = _decode_json(
        _freeze_regular_file(
            package_path.with_name("helper1-v51.candidate.json"),
            max_bytes=MAX_JSON_BYTES,
            missing_code="PRODUCER_PACKAGE_DESCRIPTOR_MISSING",
            changed_code="PRODUCER_PACKAGE_DESCRIPTOR_CHANGED_DURING_READ",
        ),
        "PRODUCER_PACKAGE_DESCRIPTOR_INVALID",
    )
    if observed_descriptor != descriptor:
        raise ProducerPackageError("PRODUCER_PACKAGE_DESCRIPTOR_MISMATCH")
    authority_sha256 = verify_authority(descriptor) if require_authority else ""
    return VerifiedProducerPackage(
        package_sha256=package_sha256,
        chain_authority_sha256=authority_sha256,
        subject_commit=subject_commit,
        subject_tree=subject_tree,
        producer_run=producer_run,
        test_evidence=MappingProxyType(test_evidence),
        legacy_evidence=MappingProxyType(legacy),
        approval_files=MappingProxyType(approval),
        objects=MappingProxyType(objects),
        quality_evidence=MappingProxyType(quality),
        bootstrap_receipts=MappingProxyType({}),
        manifest=MappingProxyType(manifest),
    )


def verify_structure(
    artifact_root: Path,
    canonical_subject: Path | None = None,
) -> dict[str, Any]:
    """Compatibility entrypoint; all authority-bearing bytes still come from the ZIP."""
    del canonical_subject
    contract, policy_raw = _policy()
    policy = _decode_json(policy_raw, "PRODUCER_PACKAGE_POLICY_INVALID")
    loaded = load_verified_package(
        artifact_root / PACKAGE_RELATIVE,
        policy=policy,
        policy_raw=policy_raw,
        require_authority=False,
    )
    return _derived_descriptor(
        contract,
        package_sha256=loaded.package_sha256,
        subject_commit=loaded.subject_commit,
        subject_tree=loaded.subject_tree,
    )


def verify_authority(descriptor: dict[str, Any]) -> str:
    loaded = _load_protected_chain_authority()
    if loaded is None:
        raise ProducerPackageError("PACKAGE_CHAIN_AUTHORITY_NOT_CONFIGURED")
    (anchor, _raw), _public_key = loaded
    candidate = anchor["candidate"]
    expected_candidate = {
        "generation": descriptor["successor_generation"],
        "package_sha256": descriptor["package_sha256"],
        "result_tree": descriptor["subject_tree"],
    }
    if (
        anchor["chain_id"] != descriptor["chain_id"]
        or anchor["successor_generation"] != descriptor["successor_generation"]
        or anchor["immediate_predecessor"] != descriptor["immediate_predecessor"]
        or anchor["rollback_record"] != descriptor["rollback_record"]
        or any(candidate.get(key) != value for key, value in expected_candidate.items())
    ):
        raise ProducerPackageError("PRODUCER_PACKAGE_CHAIN_AUTHORITY_MISMATCH")
    authority_sha256 = anchor.get("authority_sha256")
    if type(authority_sha256) is not str or SHA256.fullmatch(authority_sha256) is None:
        raise ProducerPackageError("PRODUCER_PACKAGE_CHAIN_AUTHORITY_INVALID")
    return authority_sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--artifact-root", required=True, type=Path)
    build_parser.add_argument("--canonical-subject", required=True, type=Path)
    build_parser.add_argument("--submission", required=True, type=Path)
    build_parser.add_argument("--test-evidence-root", required=True, type=Path)
    build_parser.add_argument("--product-approval-root", required=True, type=Path)
    build_parser.add_argument("--quality-evidence-root", required=True, type=Path)
    build_parser.add_argument("--approval-input-artifact", required=True, type=Path)
    build_parser.add_argument("--approval-input-provenance", required=True, type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--producer-package", required=True, type=Path)
    subject_parser = sub.add_parser("extract-subject")
    subject_parser.add_argument("--producer-package", required=True, type=Path)
    subject_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            descriptor = build(
                args.artifact_root,
                args.canonical_subject,
                args.submission,
                args.test_evidence_root,
                args.product_approval_root,
                args.quality_evidence_root,
                args.approval_input_artifact,
                args.approval_input_provenance,
            )
            print("HELPER1_PRODUCER_PACKAGE_BUILD_OK=1")
        elif args.command == "verify":
            _contract, policy_raw = _policy()
            policy = _decode_json(policy_raw, "PRODUCER_PACKAGE_POLICY_INVALID")
            loaded = load_verified_package(
                args.producer_package,
                policy=policy,
                policy_raw=policy_raw,
                require_authority=policy["enabled"],
            )
            print("HELPER1_PRODUCER_PACKAGE_STRUCTURE_OK=1")
            print("HELPER1_PRODUCER_PACKAGE_VERIFY_OK=1")
            print(f"PRODUCER_PACKAGE_SHA256={loaded.package_sha256}")
            print(
                "CHAIN_AUTHORITY_SHA256="
                + (loaded.chain_authority_sha256 or "UNCONFIGURED")
            )
        else:
            verified, _descriptor = build_protected_bootstrap_package(
                args.producer_package.parent.parent,
                _event_path(),
            )
            subject_raw = verified.subject_raw
            _decode_json(subject_raw, "PRODUCER_SUBJECT_INVALID")
            _atomic_write(args.output, subject_raw)
            print("HELPER1_PRODUCER_PACKAGE_SUBJECT_OK=1")
        print("ERROR_CODE=NONE")
        return 0
    except (OSError, ProducerPackageError) as exc:
        if args.command == "build":
            print("HELPER1_PRODUCER_PACKAGE_BUILD_OK=0")
        elif args.command == "extract-subject":
            print("HELPER1_PRODUCER_PACKAGE_SUBJECT_OK=0")
        else:
            print("HELPER1_PRODUCER_PACKAGE_VERIFY_OK=0")
        print(f"ERROR_CODE={exc if isinstance(exc, ProducerPackageError) else 'PRODUCER_PACKAGE_IO_FAILED'}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
