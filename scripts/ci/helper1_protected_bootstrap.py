#!/usr/bin/env python3
"""Verify one untrusted Helper1 artifact before protected-side packaging."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import stat
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Mapping

from butler_pc_core.helper1.test_evidence import (
    CHECKS,
    LANES,
    CheckResult,
    LaneResult,
    TestEvidenceError,
    parse_junit_bytes,
    parse_vitest_bytes,
)

REPOSITORY_ID = 1097940756
REPOSITORY = "tristan00037-tristan050/tristan050-ai_ondevice_APP"
PRODUCER_WORKFLOW_ID = 326757693
PRODUCER_WORKFLOW_NAME = "helper1-v2-evidence-producer"
PRODUCER_WORKFLOW_PATH = ".github/workflows/helper1-v2-evidence.yml"
UNTRUSTED_JOB_NAME = "helper1-v2-untrusted-evidence"
EXPECTED_LANES = frozenset(
    {
        "desktop-helper1-v51",
        "native-macos-helper1-v51",
        "python-helper1-protected-replay",
        "python-helper1-v4-original",
        "python-helper1-v51-targeted",
        "python-helper1-v61-quality",
    }
)
EXPECTED_CHECKS = frozenset(
    {
        "desktop-lock-install-v51",
        "desktop-typecheck-v51",
        "git-diff-check-v51",
        "helper1-mutation-gate-v51",
        "helper1-static-verifier-v51",
        "python-compileall-v51",
        "python-helper1-collect-v51",
    }
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_API_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


class ProtectedBootstrapError(RuntimeError):
    pass


class _CrossOriginAuthStrippingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep the API token at api.github.com when following artifact redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        source = urllib.parse.urlsplit(req.full_url)
        destination = urllib.parse.urlsplit(newurl)
        if destination.scheme != "https":
            raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_DOWNLOAD_FAILED")
        if (source.scheme, source.hostname, source.port) != (
            destination.scheme,
            destination.hostname,
            destination.port,
        ):
            redirected.remove_header("Authorization")
            redirected.remove_header("Proxy-Authorization")
            redirected.remove_header("Cookie")
        return redirected


@dataclass(frozen=True)
class VerifiedUntrustedArtifact:
    subject: Mapping[str, Any]
    subject_raw: bytes
    submission: Mapping[str, Any]
    submission_raw: bytes
    source_tree: str
    producer_run: str
    artifact_id: int
    artifact_name: str
    artifact_sha256: str
    artifact_size_bytes: int
    content_sha256: str
    workflow_sha256: str
    test_index: Mapping[str, Any]
    test_index_raw: bytes
    test_files: Mapping[str, bytes]


JsonRequest = Callable[[str], Mapping[str, Any]]
BytesRequest = Callable[[str], bytes]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _object(raw: bytes, code: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProtectedBootstrapError(code)
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ProtectedBootstrapError(code) from exc
    if type(value) is not dict:
        raise ProtectedBootstrapError(code)
    return value


def _read_regular(path: Path, code: str, *, allow_empty: bool = False) -> bytes:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            before = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size < int(not allow_empty)
                or before.st_size > MAX_FILE_BYTES
                or before.st_mode & 0o022
            ):
                raise ProtectedBootstrapError(code)
            raw = handle.read(MAX_FILE_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise ProtectedBootstrapError(code) from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity or len(raw) != before.st_size:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_CHANGED_DURING_READ")
    return raw


def verify_raw_producer_artifact_layout(root: Path) -> Path:
    """Accept only the producer's exact raw-only top-level layout."""
    try:
        root_info = root.lstat()
        root_names = {item.name for item in root.iterdir()}
    except OSError as exc:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_LAYOUT_INVALID") from exc
    if root.is_symlink() or not stat.S_ISDIR(root_info.st_mode) or root_info.st_mode & 0o022:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_LAYOUT_INVALID")
    allowed_roots = {"CANONICAL_SUBJECT.json", "SUBMISSION.json", "test-evidence"}
    if root_names != allowed_roots:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_LAYOUT_INVALID")
    test_root = root / "test-evidence"
    try:
        test_info = test_root.lstat()
    except OSError as exc:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_LAYOUT_INVALID") from exc
    if test_root.is_symlink() or not stat.S_ISDIR(test_info.st_mode) or test_info.st_mode & 0o022:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_LAYOUT_INVALID")
    return test_root


def _raw_inventory(root: Path) -> tuple[dict[str, bytes], str]:
    test_root = verify_raw_producer_artifact_layout(root)
    try:
        candidates = sorted(test_root.rglob("*"))
    except OSError as exc:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_LAYOUT_INVALID") from exc
    files = {
        "CANONICAL_SUBJECT.json": _read_regular(
            root / "CANONICAL_SUBJECT.json", "UNTRUSTED_SUBJECT_INVALID"
        ),
        "SUBMISSION.json": _read_regular(
            root / "SUBMISSION.json", "UNTRUSTED_SUBMISSION_INVALID"
        ),
    }
    total = sum(len(raw) for raw in files.values())
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        pure = PurePosixPath(relative)
        if path.is_symlink() or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_LAYOUT_INVALID")
        if path.is_dir():
            continue
        raw = _read_regular(path, "UNTRUSTED_EVIDENCE_INVALID", allow_empty=True)
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_TOO_LARGE")
        files[relative] = raw
    if "test-evidence/TEST_EVIDENCE_INDEX.v1.json" not in files:
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
    manifest = {
        name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in sorted(files.items())
    }
    return files, hashlib.sha256(_canonical(manifest)).hexdigest()


def _default_request_json(url: str) -> Mapping[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "butler-helper1-protected-bootstrap-v1",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(MAX_API_BYTES + 1)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ProtectedBootstrapError("UNTRUSTED_PRODUCER_LOOKUP_FAILED") from exc
    if not 0 < len(raw) <= MAX_API_BYTES:
        raise ProtectedBootstrapError("UNTRUSTED_PRODUCER_LOOKUP_FAILED")
    return MappingProxyType(_object(raw, "UNTRUSTED_PRODUCER_LOOKUP_FAILED"))


def _default_request_bytes(url: str) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "butler-helper1-protected-bootstrap-v1",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_DOWNLOAD_FAILED")
    headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_CrossOriginAuthStrippingRedirectHandler())
    try:
        with opener.open(request, timeout=60) as response:
            raw = response.read(MAX_ARCHIVE_BYTES + 1)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_DOWNLOAD_FAILED") from exc
    if not 0 < len(raw) <= MAX_ARCHIVE_BYTES:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_DOWNLOAD_FAILED")
    return raw


def _archive_inventory(raw: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    folded: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for item in archive.infolist():
                name = item.filename.removesuffix("/")
                pure = PurePosixPath(name)
                if (
                    pure.is_absolute()
                    or "\\" in name
                    or any(part in {"", ".", ".."} for part in pure.parts)
                ):
                    raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_ARCHIVE_INVALID")
                if item.is_dir():
                    continue
                mode = item.external_attr >> 16
                normalized = pure.as_posix()
                if (
                    normalized in files
                    or normalized.casefold() in folded
                    or stat.S_IFMT(mode) not in {0, stat.S_IFREG}
                    or item.file_size < 0
                    or item.file_size > MAX_FILE_BYTES
                    or total + item.file_size > MAX_TOTAL_BYTES
                ):
                    raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_ARCHIVE_INVALID")
                payload = archive.read(item)
                total += len(payload)
                if total > MAX_TOTAL_BYTES:
                    raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_TOO_LARGE")
                files[normalized] = payload
                folded.add(normalized.casefold())
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        if isinstance(exc, ProtectedBootstrapError):
            raise
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_ARCHIVE_INVALID") from exc
    return files


def _workflow_bytes(value: Mapping[str, Any]) -> bytes:
    content = value.get("content")
    if value.get("encoding") != "base64" or type(content) is not str:
        raise ProtectedBootstrapError("UNTRUSTED_WORKFLOW_IDENTITY_INVALID")
    try:
        encoded = content.encode("ascii")
        normalized = encoded.replace(b"\r", b"").replace(b"\n", b"")
        decoded = base64.b64decode(normalized, validate=True)
    except (UnicodeError, ValueError) as exc:
        raise ProtectedBootstrapError("UNTRUSTED_WORKFLOW_IDENTITY_INVALID") from exc
    if base64.b64encode(decoded) != normalized:
        raise ProtectedBootstrapError("UNTRUSTED_WORKFLOW_IDENTITY_INVALID")
    return decoded


def _record_dataclass(
    value: object,
    cls: type[LaneResult] | type[CheckResult],
    code: str,
) -> LaneResult | CheckResult:
    if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
        raise ProtectedBootstrapError(code)
    try:
        return cls(**value)
    except (TypeError, ValueError) as exc:
        raise ProtectedBootstrapError(code) from exc


def _verify_referenced_file(
    test_files: Mapping[str, bytes],
    path_value: object,
    digest_value: object,
) -> None:
    if path_value is None:
        if digest_value != hashlib.sha256(b"").hexdigest():
            raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_DIGEST_MISMATCH")
        return
    if type(path_value) is not str or type(digest_value) is not str:
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_DIGEST_MISMATCH")
    pure = PurePosixPath(path_value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_DIGEST_MISMATCH")
    raw = test_files.get(path_value)
    if raw is None or hashlib.sha256(raw).hexdigest() != digest_value:
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_DIGEST_MISMATCH")


def _validate_test_index(
    raw: bytes,
    test_files: Mapping[str, bytes],
    *,
    subject_commit: str,
) -> tuple[dict[str, Any], str]:
    index = _object(raw, "UNTRUSTED_EVIDENCE_INVALID")
    if set(index) != {
        "schema_version",
        "source_tree",
        "lanes",
        "checks",
        "all_required_lanes_passed",
        "all_required_checks_passed",
        "required_lanes_blocked",
    } or index.get("schema_version") != "butler.helper1.test-evidence-index.v1":
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
    source_tree = index.get("source_tree")
    lanes = index.get("lanes")
    checks = index.get("checks")
    if (
        type(source_tree) is not str
        or SHA40.fullmatch(source_tree) is None
        or type(lanes) is not list
        or type(checks) is not list
    ):
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
    lane_records = [
        _record_dataclass(value, LaneResult, "UNTRUSTED_EVIDENCE_INVALID")
        for value in lanes
    ]
    check_records = [
        _record_dataclass(value, CheckResult, "UNTRUSTED_EVIDENCE_INVALID")
        for value in checks
    ]
    if (
        {record.lane_id for record in lane_records} != EXPECTED_LANES
        or len(lane_records) != len(EXPECTED_LANES)
        or {record.check_id for record in check_records} != EXPECTED_CHECKS
        or len(check_records) != len(EXPECTED_CHECKS)
        or any(
            record.source_commit != subject_commit or record.source_tree != source_tree
            for record in (*lane_records, *check_records)
        )
    ):
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
    for record in lane_records:
        spec = LANES[record.lane_id]
        if (
            type(record.argv) is not list
            or tuple(record.argv) != spec.argv
            or record.cwd_rel != spec.cwd_rel
        ):
            raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
        if spec.report_kind == "unavailable":
            if (
                record.return_code is not None
                or record.report_sha256 is not None
                or record.status != "BLOCKED"
                or record.error_code != "MACOS_NATIVE_LANE_NOT_CONFIGURED"
            ):
                raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
        else:
            report_raw = test_files.get(spec.report_name)
            if (
                report_raw is None
                or type(record.report_sha256) is not str
                or hashlib.sha256(report_raw).hexdigest() != record.report_sha256
                or type(record.return_code) is not int
            ):
                raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
            try:
                counts = (
                    parse_junit_bytes(report_raw)
                    if spec.report_kind == "junit"
                    else parse_vitest_bytes(report_raw)
                )
            except TestEvidenceError as exc:
                raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID") from exc
            declared = (
                record.collected,
                record.passed,
                record.failed,
                record.errors,
                record.skipped,
            )
            passed = (
                record.return_code == 0
                and counts[2] == 0
                and counts[3] == 0
                and (
                    spec.expected_collected is None
                    or counts[0] == spec.expected_collected
                )
            )
            if (
                counts != declared
                or record.status != ("PASSED" if passed else "FAILED")
                or record.error_code != ("NONE" if passed else "TEST_LANE_FAILED")
            ):
                raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
        _verify_referenced_file(test_files, record.stdout_path, record.stdout_sha256)
        _verify_referenced_file(test_files, record.stderr_path, record.stderr_sha256)
    for record in check_records:
        spec = CHECKS[record.check_id]
        if (
            type(record.argv) is not list
            or tuple(record.argv) != spec.argv
            or record.cwd_rel != spec.cwd_rel
            or type(record.return_code) is not int
            or record.status != ("PASSED" if record.return_code == 0 else "FAILED")
            or record.error_code
            != ("NONE" if record.return_code == 0 else "CHECK_FAILED")
        ):
            raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
        _verify_referenced_file(test_files, record.stdout_path, record.stdout_sha256)
        _verify_referenced_file(test_files, record.stderr_path, record.stderr_sha256)
    all_lanes_passed = all(record.status == "PASSED" for record in lane_records)
    all_checks_passed = all(record.status == "PASSED" for record in check_records)
    blocked = sum(record.status == "BLOCKED" for record in lane_records)
    if (
        index.get("all_required_lanes_passed") is not all_lanes_passed
        or index.get("all_required_checks_passed") is not all_checks_passed
        or index.get("required_lanes_blocked") != blocked
    ):
        raise ProtectedBootstrapError("UNTRUSTED_EVIDENCE_INVALID")
    return index, source_tree


def verify_untrusted_artifact(
    artifact_root: Path,
    event_path: Path,
    policy: Mapping[str, Any],
    *,
    api_base: str | None = None,
    request_json: JsonRequest | None = None,
    request_archive: BytesRequest | None = None,
) -> VerifiedUntrustedArtifact:
    files, content_sha256 = _raw_inventory(artifact_root)
    subject_raw = files["CANONICAL_SUBJECT.json"]
    submission_raw = files["SUBMISSION.json"]
    subject = _object(subject_raw, "UNTRUSTED_SUBJECT_INVALID")
    submission = _object(submission_raw, "UNTRUSTED_SUBMISSION_INVALID")
    try:
        event = _object(_read_regular(event_path, "WORKFLOW_EVENT_INVALID"), "WORKFLOW_EVENT_INVALID")
    except ProtectedBootstrapError:
        raise
    repository = event.get("repository")
    event_run = event.get("workflow_run")
    if type(repository) is not dict or type(event_run) is not dict:
        raise ProtectedBootstrapError("WORKFLOW_EVENT_INVALID")
    run_id = event_run.get("id")
    run_attempt = event_run.get("run_attempt")
    head_sha = event_run.get("head_sha")
    producer_run = f"{run_id}:{run_attempt}"
    expected_workflow_digest = policy.get("quality_producer_workflow_sha256")
    if (
        repository.get("id") != REPOSITORY_ID
        or repository.get("full_name") != REPOSITORY
        or type(run_id) is not int
        or run_id < 1
        or type(run_attempt) is not int
        or run_attempt < 1
        or type(head_sha) is not str
        or SHA40.fullmatch(head_sha) is None
        or event_run.get("name") != PRODUCER_WORKFLOW_NAME
        or event_run.get("path") != PRODUCER_WORKFLOW_PATH
        or event_run.get("status") != "completed"
        or event_run.get("conclusion") not in {"success", "failure"}
        or policy.get("repository") != REPOSITORY
        or policy.get("producer_workflow_name") != PRODUCER_WORKFLOW_NAME
        or policy.get("producer_workflow_path") != PRODUCER_WORKFLOW_PATH
        or policy.get("quality_producer_workflow_id") != PRODUCER_WORKFLOW_ID
        or policy.get("quality_producer_workflow_path") != PRODUCER_WORKFLOW_PATH
        or type(expected_workflow_digest) is not str
        or SHA256.fullmatch(expected_workflow_digest) is None
    ):
        raise ProtectedBootstrapError("UNTRUSTED_PRODUCER_IDENTITY_INVALID")
    if (
        subject.get("schema_version") != "butler.helper1.canonical-subject.v1"
        or subject.get("repository_id") != REPOSITORY_ID
        or subject.get("repository_full_name") != REPOSITORY
        or subject.get("subject_repository_full_name") != REPOSITORY
        or subject.get("subject_sha") != head_sha
        or subject.get("event_name") != event_run.get("event")
        or subject.get("approval_eligible") is not True
        or submission.get("schema_version") != "butler.helper1.untrusted-submission.v1"
        or submission.get("run_id") != producer_run
        or submission.get("subject_commit") != head_sha
        or submission.get("canonical_subject_sha256")
        != hashlib.sha256(_canonical(subject)).hexdigest()
        or submission.get("product_evidence_present") is not True
    ):
        raise ProtectedBootstrapError("UNTRUSTED_SUBJECT_BINDING_INVALID")

    request = request_json or _default_request_json
    base = (api_base or os.environ.get("HELPER1_GITHUB_API_BASE") or "https://api.github.com").rstrip("/")
    run = request(f"{base}/repos/{REPOSITORY}/actions/runs/{run_id}")
    run_repository = run.get("repository")
    if (
        type(run_repository) is not dict
        or run_repository.get("id") != REPOSITORY_ID
        or run_repository.get("full_name") != REPOSITORY
        or run.get("id") != run_id
        or run.get("run_attempt") != run_attempt
        or run.get("head_sha") != head_sha
        or run.get("workflow_id") != PRODUCER_WORKFLOW_ID
        or run.get("name") != PRODUCER_WORKFLOW_NAME
        or run.get("path") != PRODUCER_WORKFLOW_PATH
        or run.get("event") != subject.get("event_name")
        or run.get("status") != "completed"
        or run.get("conclusion") not in {"success", "failure"}
    ):
        raise ProtectedBootstrapError("UNTRUSTED_PRODUCER_IDENTITY_INVALID")
    jobs_value = request(
        f"{base}/repos/{REPOSITORY}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
    )
    jobs = jobs_value.get("jobs")
    candidates = (
        [job for job in jobs if type(job) is dict and job.get("name") == UNTRUSTED_JOB_NAME]
        if type(jobs) is list
        else []
    )
    if (
        len(candidates) != 1
        or candidates[0].get("run_id") != run_id
        or candidates[0].get("run_attempt") != run_attempt
        or candidates[0].get("head_sha") != head_sha
        or candidates[0].get("workflow_name") != PRODUCER_WORKFLOW_NAME
        or candidates[0].get("status") != "completed"
        or candidates[0].get("conclusion") != "success"
    ):
        raise ProtectedBootstrapError("UNTRUSTED_CANDIDATE_JOB_NOT_SUCCESSFUL")
    artifacts_value = request(
        f"{base}/repos/{REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100"
    )
    artifacts = artifacts_value.get("artifacts")
    expected_name = f"helper1-v2-evidence-{run_id}-{run_attempt}"
    matching = (
        [item for item in artifacts if type(item) is dict and item.get("name") == expected_name]
        if type(artifacts) is list
        else []
    )
    if len(matching) != 1:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_IDENTITY_INVALID")
    artifact = matching[0]
    nested_run = artifact.get("workflow_run")
    artifact_id = artifact.get("id")
    artifact_digest = artifact.get("digest")
    artifact_size = artifact.get("size_in_bytes")
    if (
        type(artifact_id) is not int
        or artifact_id < 1
        or type(artifact_digest) is not str
        or SHA256.fullmatch(artifact_digest) is None
        or type(artifact_size) is not int
        or artifact_size < 1
        or artifact.get("expired") is not False
        or type(nested_run) is not dict
        or nested_run.get("id") != run_id
        or nested_run.get("head_sha") != head_sha
        or nested_run.get("repository_id") != REPOSITORY_ID
        or nested_run.get("head_repository_id") != REPOSITORY_ID
    ):
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_IDENTITY_INVALID")
    archive_url = f"{base}/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"
    archive_raw = (request_archive or _default_request_bytes)(archive_url)
    if (
        len(archive_raw) != artifact_size
        or hashlib.sha256(archive_raw).hexdigest()
        != artifact_digest.removeprefix("sha256:")
    ):
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_DIGEST_MISMATCH")
    if _archive_inventory(archive_raw) != files:
        raise ProtectedBootstrapError("UNTRUSTED_ARTIFACT_CONTENT_MISMATCH")
    workflow_path = urllib.parse.quote(PRODUCER_WORKFLOW_PATH, safe="/")
    workflow = request(
        f"{base}/repos/{REPOSITORY}/contents/{workflow_path}?ref={head_sha}"
    )
    workflow_sha256 = hashlib.sha256(_workflow_bytes(workflow)).hexdigest()
    if f"sha256:{workflow_sha256}" != expected_workflow_digest:
        raise ProtectedBootstrapError("UNTRUSTED_WORKFLOW_IDENTITY_INVALID")
    test_files = {
        name.removeprefix("test-evidence/"): raw
        for name, raw in files.items()
        if name.startswith("test-evidence/")
    }
    index_raw = test_files["TEST_EVIDENCE_INDEX.v1.json"]
    index, source_tree = _validate_test_index(
        index_raw,
        test_files,
        subject_commit=head_sha,
    )
    return VerifiedUntrustedArtifact(
        subject=MappingProxyType(subject),
        subject_raw=subject_raw,
        submission=MappingProxyType(submission),
        submission_raw=submission_raw,
        source_tree=source_tree,
        producer_run=producer_run,
        artifact_id=artifact_id,
        artifact_name=expected_name,
        artifact_sha256=artifact_digest.removeprefix("sha256:"),
        artifact_size_bytes=artifact_size,
        content_sha256=content_sha256,
        workflow_sha256=workflow_sha256,
        test_index=MappingProxyType(index),
        test_index_raw=index_raw,
        test_files=MappingProxyType(test_files),
    )


def build_bootstrap_receipts(
    artifact: VerifiedUntrustedArtifact,
    *,
    policy_enabled: bool,
) -> dict[str, bytes]:
    if policy_enabled:
        raise ProtectedBootstrapError("BOOTSTRAP_PACKAGE_FORBIDDEN_WHEN_POLICY_ENABLED")
    provenance = {
        "schema_version": "butler.helper1.untrusted-artifact-provenance.v1",
        "repository_id": REPOSITORY_ID,
        "repository": REPOSITORY,
        "subject_commit": artifact.subject["subject_sha"],
        "subject_tree": artifact.source_tree,
        "producer_run": artifact.producer_run,
        "producer_workflow_id": PRODUCER_WORKFLOW_ID,
        "producer_workflow_path": PRODUCER_WORKFLOW_PATH,
        "producer_workflow_sha256": artifact.workflow_sha256,
        "artifact_id": artifact.artifact_id,
        "artifact_name": artifact.artifact_name,
        "artifact_sha256": artifact.artifact_sha256,
        "artifact_size_bytes": artifact.artifact_size_bytes,
        "extracted_content_sha256": artifact.content_sha256,
        "test_evidence_index_sha256": hashlib.sha256(artifact.test_index_raw).hexdigest(),
    }
    provenance_raw = _canonical(provenance) + b"\n"
    index = artifact.test_index
    quality = {
        "schema_version": "butler.helper1.protected-bootstrap-quality.v1",
        "subject_commit": artifact.subject["subject_sha"],
        "subject_tree": artifact.source_tree,
        "producer_run": artifact.producer_run,
        "provenance_sha256": hashlib.sha256(provenance_raw).hexdigest(),
        "all_required_checks_passed": index["all_required_checks_passed"],
        "all_required_lanes_passed": index["all_required_lanes_passed"],
        "required_lanes_blocked": index["required_lanes_blocked"],
        "quality_approved": 0,
        "state": "UNAPPROVED",
        "reason_code": "PROTECTED_QUALITY_APPROVAL_NOT_CONFIGURED",
    }
    quality_raw = _canonical(quality) + b"\n"
    approval = {
        "schema_version": "butler.helper1.protected-bootstrap-approval.v1",
        "subject_commit": artifact.subject["subject_sha"],
        "subject_tree": artifact.source_tree,
        "producer_run": artifact.producer_run,
        "quality_measurement_sha256": hashlib.sha256(quality_raw).hexdigest(),
        "policy_enabled": False,
        "approval_values": {
            "code_pass": 0,
            "external_handoff_allowed": 0,
            "product_release_allowed": 0,
            "production_claim_allowed": 0,
            "runtime_activation_allowed": 0,
        },
        "state": "UNSIGNED_ZERO",
        "reason_code": "TRUST_POLICY_DISABLED",
        "signature_b64": None,
    }
    return {
        "RAW_ARTIFACT_PROVENANCE.v1.json": provenance_raw,
        "QUALITY_MEASUREMENT.v1.json": quality_raw,
        "APPROVAL_RECEIPT.v1.json": _canonical(approval) + b"\n",
    }
