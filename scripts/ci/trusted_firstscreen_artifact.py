#!/usr/bin/env python3
"""Preflight and unpack FirstScreen evidence without executing PR content."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_SOURCE_ENTRIES = 8192
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_SINGLE_BYTES = 128 * 1024 * 1024
MAX_RATIO = 100
MAX_SOURCE_RATIO = 1000
READ_CHUNK = 1024 * 1024
INNER_ARCHIVE = "firstscreen-v9-evidence.zip"
DETACHED_DIGEST = f"{INNER_ARCHIVE}.sha256"
PACKAGE_VERIFY = f"{INNER_ARCHIVE}.verify.json"
PACKAGE_ROOT = "package"
REPORT_NAMES = {
    "reports/vitest-results.json",
    "reports/playwright-success.json",
    "reports/playwright-unavailable.json",
    "reports/contract-pytest.xml",
    "reports/authorities-pytest.xml",
    "reports/canonical-inputs-pytest.xml",
    "reports/product-integration-pytest.xml",
    "reports/windows-trust-pytest.xml",
    "reports/required-node-audit.json",
    "reports/node-verifier-results.json",
    "reports/node-evidence-results.json",
}
CONTEXT_NAMES = {
    "contexts/firstscreen-v9-unit-context.json",
    "contexts/firstscreen-v9-real-sidecar-context.json",
    "contexts/firstscreen-v9-real-sidecar-unavailable-context.json",
    "contexts/contract-context.json",
    "contexts/authorities-context.json",
    "contexts/canonical-inputs-context.json",
    "contexts/product-integration-context.json",
    "contexts/windows-trust-context.json",
    "contexts/firstscreen-v9-required-audit-context.json",
    "contexts/node-verifier-context.json",
    "contexts/node-evidence-context.json",
}
PACKAGE_FILES = {
    "source/source.zip",
    "source/git-ls-tree.txt",
    "source/correction.patch",
    "manifests/required-tests.v3.json",
    "manifests/action-pins.v1.json",
    "manifests/evidence-index.schema.json",
    "EVIDENCE_INDEX.json",
    "security/mutation-generator.json",
    "SHA256SUMS.txt",
    *REPORT_NAMES,
    *CONTEXT_NAMES,
}
RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
PRIVATE_PATH_PATTERNS = (
    re.compile(r"/Users/[^/\s]+/"),
    re.compile(r"/home/(?!runner(?:/|\b))[^/\s]+/"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
)


class ArtifactError(RuntimeError):
    pass


def _json_pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in rows:
        if key in result:
            raise ArtifactError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _json_constant(_: str) -> None:
    raise ArtifactError("JSON_CONSTANT_INVALID")


def _strict_json(path: Path, *, max_bytes: int) -> dict[str, object]:
    _require_regular(path, max_bytes=max_bytes)
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ArtifactError("JSON_BOM_FORBIDDEN")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_json_pairs,
            parse_constant=_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError("JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise ArtifactError("JSON_ROOT_INVALID")
    return value


def _sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(READ_CHUNK)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _sha256_path(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_stream(stream)


def _require_regular(path: Path, *, max_bytes: int) -> os.stat_result:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_size < 1
        or before.st_size > max_bytes
    ):
        raise ArtifactError("ARTIFACT_FILE_INVALID")
    return before


def _safe_member_name(raw: str, *, directory: bool = False) -> str:
    candidate = raw[:-1] if directory and raw.endswith("/") else raw
    if (
        not candidate
        or "\x00" in candidate
        or "\\" in candidate
        or candidate.startswith("/")
        or candidate.endswith("/")
    ):
        raise ArtifactError("ARCHIVE_PATH_INVALID")
    normalized = unicodedata.normalize("NFC", candidate)
    if normalized != candidate:
        raise ArtifactError("ARCHIVE_PATH_NOT_NFC")
    path = PurePosixPath(candidate)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ArtifactError("ARCHIVE_PATH_INVALID")
    for part in path.parts:
        if part.endswith((" ", ".")) or ":" in part:
            raise ArtifactError("ARCHIVE_WINDOWS_PATH_INVALID")
        stem = part.split(".", 1)[0].upper()
        if stem in RESERVED_WINDOWS_NAMES:
            raise ArtifactError("ARCHIVE_WINDOWS_PATH_INVALID")
    return candidate


def _entry_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _preflight(
    stream: BinaryIO,
    *,
    max_entries: int = MAX_ENTRIES,
    max_ratio: int = MAX_RATIO,
) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo]]:
    try:
        archive = zipfile.ZipFile(stream)
        infos = archive.infolist()
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ArtifactError("ARCHIVE_INVALID") from exc
    if not infos or len(infos) > max_entries:
        archive.close()
        raise ArtifactError("ARCHIVE_ENTRY_COUNT_INVALID")
    total = 0
    seen: set[str] = set()
    for info in infos:
        is_directory = info.is_dir()
        name = _safe_member_name(info.filename, directory=is_directory)
        folded = unicodedata.normalize("NFC", name).casefold()
        if folded in seen:
            archive.close()
            raise ArtifactError("ARCHIVE_PATH_COLLISION")
        seen.add(folded)
        if info.flag_bits & 0x1:
            archive.close()
            raise ArtifactError("ARCHIVE_ENCRYPTION_FORBIDDEN")
        mode = _entry_mode(info)
        file_type = stat.S_IFMT(mode)
        expected_type = stat.S_IFDIR if is_directory else stat.S_IFREG
        if file_type not in {0, expected_type}:
            archive.close()
            raise ArtifactError("ARCHIVE_FILE_TYPE_INVALID")
        if is_directory:
            continue
        if info.file_size < 0 or info.file_size > MAX_SINGLE_BYTES:
            archive.close()
            raise ArtifactError("ARCHIVE_ENTRY_TOO_LARGE")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            archive.close()
            raise ArtifactError("ARCHIVE_TOTAL_TOO_LARGE")
        compressed = max(info.compress_size, 1)
        if info.file_size > compressed * max_ratio:
            archive.close()
            raise ArtifactError("ARCHIVE_RATIO_EXCEEDED")
    return archive, infos


def _mkdir_child(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError as exc:
        raise ArtifactError("EXTRACTION_TARGET_EXISTS") from exc
    descriptor = os.open(
        name,
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        dir_fd=parent_fd,
    )
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_nlink < 1:
        os.close(descriptor)
        raise ArtifactError("EXTRACTION_DIRECTORY_INVALID")
    return descriptor


def _write_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    root_fd: int,
) -> None:
    name = _safe_member_name(info.filename, directory=info.is_dir())
    parts = PurePosixPath(name).parts
    descriptors = [root_fd]
    try:
        directory_parts = parts if info.is_dir() else parts[:-1]
        for component in directory_parts:
            try:
                child = os.open(
                    component,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptors[-1],
                )
            except FileNotFoundError:
                child = _mkdir_child(descriptors[-1], component)
            descriptors.append(child)
        if info.is_dir():
            return
        output_fd = os.open(
            parts[-1],
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=descriptors[-1],
        )
        try:
            written = 0
            with archive.open(info, "r") as source:
                while True:
                    chunk = source.read(READ_CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > info.file_size or written > MAX_SINGLE_BYTES:
                        raise ArtifactError("EXTRACTED_SIZE_MISMATCH")
                    view = memoryview(chunk)
                    while view:
                        count = os.write(output_fd, view)
                        if count <= 0:
                            raise ArtifactError("EXTRACTION_WRITE_FAILED")
                        view = view[count:]
            if written != info.file_size:
                raise ArtifactError("EXTRACTED_SIZE_MISMATCH")
            os.fsync(output_fd)
            metadata = os.fstat(output_fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size != info.file_size
            ):
                raise ArtifactError("EXTRACTED_FILE_INVALID")
        finally:
            os.close(output_fd)
    finally:
        for descriptor in reversed(descriptors[1:]):
            os.close(descriptor)


def _extract_zip(path: Path, destination: Path) -> list[str]:
    before = _require_regular(path, max_bytes=MAX_ARCHIVE_BYTES)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    root_fd = os.open(
        destination,
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
                or opened.st_size != before.st_size
            ):
                raise ArtifactError("ARTIFACT_IDENTITY_CHANGED")
            archive, infos = _preflight(stream)
            try:
                for info in infos:
                    _write_member(archive, info, root_fd)
            finally:
                archive.close()
            after = os.fstat(stream.fileno())
            if (
                after.st_dev != opened.st_dev
                or after.st_ino != opened.st_ino
                or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns
            ):
                raise ArtifactError("ARTIFACT_IDENTITY_CHANGED")
        os.fsync(root_fd)
        return sorted(info.filename for info in infos)
    finally:
        os.close(root_fd)


def _strict_detached(path: Path) -> str:
    _require_regular(path, max_bytes=256)
    text = path.read_text(encoding="ascii")
    match = re.fullmatch(
        rf"([0-9a-f]{{64}})  {re.escape(INNER_ARCHIVE)}\n?",
        text,
    )
    if match is None:
        raise ArtifactError("DETACHED_DIGEST_INVALID")
    return match.group(1)


def _verify_checksums(package: Path) -> int:
    checksum_path = package / "SHA256SUMS.txt"
    _require_regular(checksum_path, max_bytes=1024 * 1024)
    rows = checksum_path.read_text(encoding="utf-8").splitlines()
    if not rows:
        raise ArtifactError("CHECKSUMS_EMPTY")
    expected: dict[str, str] = {}
    for row in rows:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", row)
        if match is None:
            raise ArtifactError("CHECKSUM_ROW_INVALID")
        name = _safe_member_name(match.group(2))
        if name == "SHA256SUMS.txt" or name in expected:
            raise ArtifactError("CHECKSUM_TARGET_INVALID")
        expected[name] = match.group(1)
    actual = sorted(
        str(path.relative_to(package)).replace(os.sep, "/")
        for path in package.rglob("*")
        if path.is_file()
    )
    listed = sorted([*expected, "SHA256SUMS.txt"])
    if actual != listed:
        raise ArtifactError("CHECKSUM_FILESET_MISMATCH")
    if set(actual) != PACKAGE_FILES:
        raise ArtifactError("EXPECTED_FILESET_MISMATCH")
    for name, digest in expected.items():
        target = package.joinpath(*PurePosixPath(name).parts)
        _require_regular(target, max_bytes=MAX_SINGLE_BYTES)
        if _sha256_path(target) != digest:
            raise ArtifactError("CHECKSUM_MISMATCH")
    return len(rows)


def _require_oid(value: object, algorithm: object) -> str:
    length = 40 if algorithm == "sha1" else 64 if algorithm == "sha256" else 0
    if not isinstance(value, str) or not length or re.fullmatch(
        rf"[0-9a-f]{{{length}}}",
        value,
    ) is None:
        raise ArtifactError("EVIDENCE_OID_INVALID")
    return value


def _utc_time(value: object) -> datetime:
    if not isinstance(value, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z",
        value,
    ) is None:
        raise ArtifactError("EVIDENCE_INDEX_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ArtifactError("EVIDENCE_INDEX_TIME_INVALID") from exc
    if parsed.tzinfo != timezone.utc:
        raise ArtifactError("EVIDENCE_INDEX_TIME_INVALID")
    return parsed


CONTEXT_KEYS = {
    "schema_version",
    "repository",
    "event_name",
    "pr_number",
    "subject_head",
    "execution_commit",
    "tree",
    "object_format",
    "run_id",
    "run_attempt",
    "workflow_ref",
    "job_name",
    "runner",
    "platform",
    "command",
    "report_path",
    "report_sha256",
    "started_at",
    "finished_at",
    "tool_versions",
}


def _nonempty_string(value: object, *, max_length: int = 4096) -> bool:
    return isinstance(value, str) and 0 < len(value) <= max_length


def _verify_context(
    package: Path,
    run: dict[str, object],
    metadata: dict[str, object],
    producer: dict[str, object],
    tree: dict[str, object],
) -> None:
    report_path = run.get("raw_result_path")
    context_path = run.get("context_path")
    if not isinstance(report_path, str) or not isinstance(context_path, str):
        raise ArtifactError("EVIDENCE_CONTEXT_PATH_INVALID")
    context = _strict_json(
        package.joinpath(*PurePosixPath(context_path).parts),
        max_bytes=64 * 1024,
    )
    tools = context.get("tool_versions")
    if (
        set(context) != CONTEXT_KEYS
        or context.get("schema_version") != 2
        or context.get("repository") != metadata.get("repository")
        or context.get("event_name") != metadata.get("event_name")
        or context.get("pr_number") != metadata.get("pull_request")
        or isinstance(context.get("pr_number"), bool)
        or context.get("subject_head") != metadata.get("subject_head")
        or context.get("execution_commit") != metadata.get("subject_head")
        or context.get("tree") != tree.get("hex")
        or context.get("object_format") != tree.get("algorithm")
        or context.get("run_id") != producer.get("run_id")
        or context.get("run_attempt") != producer.get("run_attempt")
        or isinstance(context.get("run_attempt"), bool)
        or context.get("workflow_ref") != producer.get("workflow_ref")
        or context.get("job_name") != run.get("job_name")
        or context.get("runner") != run.get("runner")
        or context.get("platform") != run.get("platform")
        or context.get("command") != run.get("command")
        or context.get("report_path") != report_path
        or context.get("report_sha256") != run.get("raw_result_sha256")
        or context.get("started_at") != run.get("started_at")
        or context.get("finished_at") != run.get("finished_at")
        or tools != run.get("tool_versions")
        or not isinstance(tools, dict)
        or not tools
        or any(
            not _nonempty_string(value, max_length=256)
            for value in tools.values()
        )
    ):
        raise ArtifactError("EVIDENCE_CONTEXT_INVALID")


def _verify_mutation_report(package: Path) -> None:
    report = _strict_json(
        package / "security" / "mutation-generator.json",
        max_bytes=4 * 1024 * 1024,
    )
    reports = report.get("reports")
    generated = report.get("total_generated_cases")
    if (
        report.get("schema_version") != 1
        or isinstance(generated, bool)
        or not isinstance(generated, int)
        or generated < 3000
        or report.get("accepted_malicious") != 0
        or report.get("unanalysed") != 0
        or not isinstance(reports, list)
        or len(reports) != 3
        or any(
            not isinstance(item, dict)
            or item.get("cases") != 1000
            or item.get("accepted_malicious") != 0
            or item.get("unanalysed") != 0
            for item in reports
        )
    ):
        raise ArtifactError("MUTATION_EVIDENCE_INVALID")


def _validate_index_schema(
    index: dict[str, object],
    protected_index_schema: Path,
) -> None:
    schema = _strict_json(protected_index_schema, max_bytes=2 * 1024 * 1024)
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )
        first_error = next(validator.iter_errors(index), None)
    except SchemaError as exc:
        raise ArtifactError("PROTECTED_INDEX_SCHEMA_INVALID") from exc
    if first_error is not None:
        raise ArtifactError("EVIDENCE_INDEX_SCHEMA_INVALID")


def _verify_index(
    package: Path,
    metadata_path: Path,
    outer_digest: str,
    protected_index_schema: Path,
) -> dict[str, object]:
    metadata = _strict_json(metadata_path, max_bytes=64 * 1024)
    index = _strict_json(package / "EVIDENCE_INDEX.json", max_bytes=1024 * 1024)
    _validate_index_schema(index, protected_index_schema)
    producer = metadata.get("producer")
    artifact = metadata.get("artifact")
    tree = metadata.get("tree_oid")
    subject = index.get("subject")
    workflow = index.get("workflow")
    manifest = index.get("manifest")
    runs = index.get("runs")
    packaged_manifest = package / "manifests" / "required-tests.v3.json"
    if (
        metadata.get("schema_version") != 1
        or not isinstance(producer, dict)
        or not isinstance(artifact, dict)
        or not isinstance(tree, dict)
        or artifact.get("sha256") != outer_digest
        or index.get("schema_version") != 3
        or not isinstance(subject, dict)
        or subject.get("repository") != metadata.get("repository")
        or subject.get("pull_request") != metadata.get("pull_request")
        or not isinstance(subject.get("head_oid"), dict)
        or subject["head_oid"].get("hex") != metadata.get("subject_head")
        or subject["head_oid"].get("algorithm") != tree.get("algorithm")
        or not isinstance(subject.get("tree_oid"), dict)
        or subject["tree_oid"] != tree
        or not isinstance(workflow, dict)
        or workflow.get("runner_kind") != "github-hosted"
        or workflow.get("run_id") != producer.get("run_id")
        or workflow.get("run_attempt") != producer.get("run_attempt")
        or workflow.get("workflow_ref") != producer.get("workflow_ref")
        or not isinstance(manifest, dict)
        or manifest.get("path") != "manifests/required-tests.v3.json"
        or manifest.get("sha256") != _sha256_path(packaged_manifest)
        or manifest.get("required_total") != 92
        or not isinstance(runs, list)
        or len(runs) != len(REPORT_NAMES)
    ):
        raise ArtifactError("EVIDENCE_INDEX_IDENTITY_INVALID")
    _require_oid(metadata.get("subject_head"), tree.get("algorithm"))
    _require_oid(tree.get("hex"), tree.get("algorithm"))

    observed_reports: set[str] = set()
    observed_contexts: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            raise ArtifactError("EVIDENCE_INDEX_RUN_INVALID")
        report_path = run.get("raw_result_path")
        context_path = run.get("context_path")
        if (
            not isinstance(report_path, str)
            or not isinstance(context_path, str)
            or report_path not in REPORT_NAMES
            or context_path not in CONTEXT_NAMES
            or report_path in observed_reports
            or context_path in observed_contexts
            or run.get("exit_code") != 0
            or not _nonempty_string(run.get("job_name"), max_length=256)
            or not _nonempty_string(run.get("runner"), max_length=64)
            or run.get("platform") not in {
                "ubuntu",
                "windows-2025",
                "macos-15",
            }
            or not _nonempty_string(run.get("command"))
            or not isinstance(run.get("tool_versions"), dict)
            or not run.get("tool_versions")
            or not _nonempty_string(run.get("os"), max_length=64)
            or not _nonempty_string(run.get("arch"), max_length=64)
            or not isinstance(run.get("execution_oid"), dict)
            or run["execution_oid"].get("hex") != metadata.get("subject_head")
            or run["execution_oid"].get("algorithm") != tree.get("algorithm")
            or run.get("tree_oid") != tree
        ):
            raise ArtifactError("EVIDENCE_INDEX_RUN_INVALID")
        report = package.joinpath(*PurePosixPath(report_path).parts)
        context = package.joinpath(*PurePosixPath(context_path).parts)
        if (
            run.get("raw_result_sha256") != _sha256_path(report)
            or run.get("context_sha256") != _sha256_path(context)
        ):
            raise ArtifactError("EVIDENCE_INDEX_DIGEST_MISMATCH")
        started = run.get("started_at")
        finished = run.get("finished_at")
        if _utc_time(started) > _utc_time(finished):
            raise ArtifactError("EVIDENCE_INDEX_TIME_INVALID")
        _verify_context(package, run, metadata, producer, tree)
        observed_reports.add(report_path)
        observed_contexts.add(context_path)
    if observed_reports != REPORT_NAMES or observed_contexts != CONTEXT_NAMES:
        raise ArtifactError("EVIDENCE_INDEX_FILESET_MISMATCH")
    _verify_mutation_report(package)
    return metadata


def _verify_privacy(paths: Iterable[Path]) -> None:
    for path in paths:
        if path.suffix.lower() not in {".json", ".xml", ".txt", ".patch"}:
            continue
        metadata = _require_regular(path, max_bytes=MAX_SINGLE_BYTES)
        if metadata.st_size > 32 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ArtifactError("EVIDENCE_TEXT_ENCODING_INVALID") from exc
        if any(pattern.search(text) for pattern in PRIVATE_PATH_PATTERNS):
            raise ArtifactError("EVIDENCE_PRIVATE_PATH_LEAK")


def _parse_artifact_digest(value: str) -> str:
    match = re.fullmatch(r"(?:sha256:)?([0-9a-f]{64})", value)
    if match is None:
        raise ArtifactError("UPLOAD_ARTIFACT_DIGEST_INVALID")
    return match.group(1)


def _verify_packager_receipt(
    path: Path,
    *,
    inner_digest: str,
    metadata: dict[str, object],
) -> None:
    receipt = _strict_json(path, max_bytes=64 * 1024)
    expected_keys = {
        "schema_version",
        "subject_head",
        "tree_oid",
        "checksum_count",
        "context_count",
        "zip_sha256",
        "detached_digest_match",
        "internal_checksums_verified",
    }
    if (
        set(receipt) != expected_keys
        or receipt.get("schema_version") != 3
        or receipt.get("subject_head") != metadata.get("subject_head")
        or receipt.get("tree_oid") != metadata.get("tree_oid")
        or receipt.get("checksum_count") != len(PACKAGE_FILES) - 1
        or receipt.get("context_count") != len(CONTEXT_NAMES)
        or receipt.get("zip_sha256") != inner_digest
        or receipt.get("detached_digest_match") is not True
        or receipt.get("internal_checksums_verified") is not True
    ):
        raise ArtifactError("PACKAGE_VERIFY_RECEIPT_INVALID")


def verify(
    outer: Path,
    destination: Path,
    protected_manifest: Path,
    protected_action_pins: Path,
    protected_index_schema: Path,
    metadata: Path,
    output: Path,
) -> None:
    outer_digest = _sha256_path(outer)
    trusted_metadata = _strict_json(metadata, max_bytes=64 * 1024)
    artifact = trusted_metadata.get("artifact")
    expected_digest = artifact.get("sha256") if isinstance(artifact, dict) else None
    if outer_digest != _parse_artifact_digest(str(expected_digest or "")):
        raise ArtifactError("UPLOAD_ARTIFACT_DIGEST_MISMATCH")
    outer_root = destination / f"outer-{secrets.token_hex(8)}"
    outer_names = _extract_zip(outer, outer_root)
    if outer_names != sorted([DETACHED_DIGEST, INNER_ARCHIVE, PACKAGE_VERIFY]):
        raise ArtifactError("OUTER_FILESET_MISMATCH")
    inner = outer_root / INNER_ARCHIVE
    inner_digest = _sha256_path(inner)
    if inner_digest != _strict_detached(outer_root / DETACHED_DIGEST):
        raise ArtifactError("DETACHED_DIGEST_MISMATCH")
    _verify_packager_receipt(
        outer_root / PACKAGE_VERIFY,
        inner_digest=inner_digest,
        metadata=trusted_metadata,
    )
    inner_root = destination / f"inner-{secrets.token_hex(8)}"
    inner_names = _extract_zip(inner, inner_root)
    if not inner_names or any(
        not name.startswith(f"{PACKAGE_ROOT}/") for name in inner_names
    ):
        raise ArtifactError("INNER_ROOT_INVALID")
    package = inner_root / PACKAGE_ROOT
    checksum_count = _verify_checksums(package)
    _verify_index(package, metadata, outer_digest, protected_index_schema)
    packaged_manifest = package / "manifests" / "required-tests.v3.json"
    _require_regular(protected_manifest, max_bytes=2 * 1024 * 1024)
    _require_regular(packaged_manifest, max_bytes=2 * 1024 * 1024)
    if _sha256_path(packaged_manifest) != _sha256_path(protected_manifest):
        raise ArtifactError("PROTECTED_MANIFEST_MISMATCH")
    protected_pairs = (
        (
            package / "manifests" / "action-pins.v1.json",
            protected_action_pins,
        ),
        (
            package / "manifests" / "evidence-index.schema.json",
            protected_index_schema,
        ),
    )
    for packaged, protected in protected_pairs:
        _require_regular(packaged, max_bytes=2 * 1024 * 1024)
        _require_regular(protected, max_bytes=2 * 1024 * 1024)
        if _sha256_path(packaged) != _sha256_path(protected):
            raise ArtifactError("PROTECTED_CONTRACT_MISMATCH")
    source_zip = package / "source" / "source.zip"
    with source_zip.open("rb") as source:
        archive, _ = _preflight(
            source,
            max_entries=MAX_SOURCE_ENTRIES,
            max_ratio=MAX_SOURCE_RATIO,
        )
        archive.close()
    _verify_privacy(path for path in package.rglob("*") if path.is_file())
    result = {
        "schema_version": 1,
        "package_relative": str(package.relative_to(destination)),
        "upload_artifact_sha256": outer_digest,
        "evidence_zip_sha256": _sha256_path(inner),
        "protected_manifest_sha256": _sha256_path(protected_manifest),
        "trusted_metadata_sha256": _sha256_path(metadata),
        "checksum_count": checksum_count,
    }
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("TRUSTED_ARTIFACT_PREFLIGHT_OK=1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outer", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--protected-manifest", type=Path, required=True)
    parser.add_argument("--protected-action-pins", type=Path, required=True)
    parser.add_argument("--protected-index-schema", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(
            args.outer,
            args.destination,
            args.protected_manifest,
            args.protected_action_pins,
            args.protected_index_schema,
            args.metadata,
            args.output,
        )
    except (ArtifactError, OSError, ValueError, zipfile.BadZipFile) as exc:
        code = str(exc) if str(exc).isupper() else "TRUSTED_ARTIFACT_PREFLIGHT_FAILED"
        print("TRUSTED_ARTIFACT_PREFLIGHT_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
