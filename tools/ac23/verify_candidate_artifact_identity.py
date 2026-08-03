#!/usr/bin/env python3
"""Independent, network-free verifier for Butler AC-23 artifacts.

The script is intentionally self-contained so the exact file can be copied to
``AC23_FINAL/VERIFY`` and executed without importing candidate source code.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import urllib.parse
import zlib
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "butler.box5.candidate-artifact-identity.v1"
APPROVED_REPOSITORY_URL = (
    "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP.git"
)
APPROVED_BASE_COMMIT = "de3dd4ebaf5b3935a142b988dd61e6198aa9536d"
APPROVED_BASE_TREE = "8c3509db047145714d2a1a84dfc76fb0a4c0fec9"
NORMATIVE_CONTRACT_PATH = (
    "butler_pc_core/accounting/assignment/contracts/authorization-replay-v2.sql"
)
NORMATIVE_CONTRACT_SHA256 = (
    "b0e11b52b7efd3d74c41fcfb46726312ba442c2dfa7a7a04203f7424342bd729"
)
MAX_MEMBERS = 100_000
MAX_MEMBER_SIZE = 1 << 30
MAX_TOTAL_SIZE = 4 << 30
MAX_MANIFEST_SIZE = 1 << 20
MAX_JSON_SIZE = 16 << 20
MAX_JUNIT_SIZE = 16 << 20
MANIFEST_KEYS = {
    "schema_version",
    "digest_algorithm",
    "repository_url",
    "object_format",
    "base_commit",
    "base_tree",
    "head_commit",
    "head_tree",
    "submitted_head_tree",
    "patch_applied_tree",
    "source_archive_tree",
    "patch_sha256",
    "source_archive_sha256",
    "changed_path_manifest_sha256",
    "evidence_sha256",
    "normative_contract_path",
    "normative_contract_sha256",
}
PACKAGE_FILES = {
    "IDENTITY/candidate_artifact_identity.json",
    "IDENTITY/changed_paths.nul",
    "PATCH/cumulative.patch",
    "SOURCE/candidate_source.tar",
    "SOURCE/candidate_repository.bundle",
    "EVIDENCE/evidence_raw.tar",
    "VERIFY/verify_candidate_artifact_identity.py",
    "VERIFY/candidate-artifact-identity-v1.schema.json",
    "VERIFY/evidence_policy_v2.json",
    "README_KO.md",
    "SHA256SUMS.txt",
}
POLICY_PATH = "tools/ac23/evidence_policy_v2.json"
POLICY_KEYS = {
    "schema_version",
    "object_format",
    "required_runs",
    "frozen_acceptance",
    "legacy_mutation_categories",
    "evidence_semantic_cases",
    "limits",
}
COMMAND_KEYS = {
    "sequence",
    "run_id",
    "argv",
    "cwd",
    "start_utc",
    "end_utc",
    "exit_code",
    "stdout_path",
    "stdout_sha256",
    "stderr_path",
    "stderr_sha256",
}


class VerificationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fail(code: str) -> None:
    raise VerificationError(code)


def _git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "TMPDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if extra:
        env.update(extra)
    return env


def _git(
    cwd: Path,
    *args: str | os.PathLike[str],
    input_bytes: bytes | None = None,
    check: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    argv = [
        "git",
        "-c",
        "core.autocrlf=false",
        "-c",
        "core.safecrlf=false",
        "-c",
        "core.filemode=true",
        "-c",
        "core.symlinks=true",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        f"core.excludesFile={os.devnull}",
        *(os.fspath(arg) for arg in args),
    ]
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=_git_env(extra_env),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, argv, output=result.stdout, stderr=result.stderr
        )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same(left: str | bytes, right: str | bytes) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return hmac.compare_digest(left.encode("ascii"), right.encode("ascii"))
    if isinstance(left, bytes) and isinstance(right, bytes):
        return hmac.compare_digest(left, right)
    return False


def normalize_repository_url(raw: str) -> str:
    if not isinstance(raw, str):
        fail("E_REPOSITORY_URL")
    value = raw.strip().rstrip("/")
    scp = re.fullmatch(r"git@([^:/\s]+):(.+)", value)
    if scp:
        value = f"ssh://git@{scp.group(1)}/{scp.group(2)}"
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        fail("E_REPOSITORY_URL")
    scheme = parsed.scheme.lower()
    if scheme not in {"https", "ssh"} or not parsed.hostname:
        fail("E_REPOSITORY_URL")
    if parsed.query or parsed.fragment or parsed.password is not None:
        fail("E_REPOSITORY_URL")
    username = parsed.username
    if username is not None and not (scheme == "ssh" and username == "git"):
        fail("E_REPOSITORY_URL")
    if "\\" in parsed.path or not parsed.path.startswith("/"):
        fail("E_REPOSITORY_URL")
    path = parsed.path.rstrip("/")
    parts = path.split("/")[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail("E_REPOSITORY_URL")
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        fail("E_REPOSITORY_URL")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = ("git@" if username else "") + host
    if port is not None:
        netloc += f":{port}"
    return urllib.parse.urlunsplit((scheme, netloc, path, "", ""))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            fail("E_SCHEMA")
        output[key] = value
    return output


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError:
        fail("E_SCHEMA")
    if len(raw) > MAX_MANIFEST_SIZE:
        fail("E_SCHEMA")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, VerificationError):
        fail("E_SCHEMA")
    if not isinstance(value, dict) or set(value) != MANIFEST_KEYS:
        fail("E_SCHEMA")
    if value.get("schema_version") != SCHEMA_VERSION:
        fail("E_SCHEMA")
    if value.get("digest_algorithm") != "sha256":
        fail("E_SCHEMA")
    if value.get("object_format") != "sha1":
        fail("E_OBJECT_FORMAT_UNSUPPORTED")
    oid_length = 40
    for key in (
        "base_commit",
        "base_tree",
        "head_commit",
        "head_tree",
        "submitted_head_tree",
        "patch_applied_tree",
        "source_archive_tree",
    ):
        field = value.get(key)
        if not isinstance(field, str) or not re.fullmatch(
            rf"[0-9a-f]{{{oid_length}}}", field
        ):
            fail("E_SCHEMA")
    for key in (
        "patch_sha256",
        "source_archive_sha256",
        "changed_path_manifest_sha256",
        "evidence_sha256",
        "normative_contract_sha256",
    ):
        field = value.get(key)
        if not isinstance(field, str) or not re.fullmatch(r"[0-9a-f]{64}", field):
            fail("E_SCHEMA")
    if not isinstance(value.get("repository_url"), str):
        fail("E_SCHEMA")
    if not isinstance(value.get("normative_contract_path"), str):
        fail("E_SCHEMA")
    return value


def _archive_segments(name: str) -> tuple[str, ...]:
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        fail("E_ARCHIVE_SAFETY")
    parts = tuple(name.rstrip("/").split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail("E_ARCHIVE_SAFETY")
    if any(part.casefold() == ".git" for part in parts):
        fail("E_ARCHIVE_SAFETY")
    return parts


def _inspect_source_tar(path: Path) -> list[tarfile.TarInfo]:
    try:
        archive = tarfile.open(path, "r:*", encoding="utf-8", errors="surrogateescape")
    except (OSError, tarfile.TarError):
        fail("E_ARCHIVE_SAFETY")
    members: list[tarfile.TarInfo] = []
    exact: set[str] = set()
    folded: dict[str, str] = {}
    symlinks: set[str] = set()
    total = 0
    try:
        with archive:
            for index, member in enumerate(archive):
                if index >= MAX_MEMBERS:
                    fail("E_ARCHIVE_SAFETY")
                parts = _archive_segments(member.name)
                if parts[0] != "candidate":
                    fail("E_ARCHIVE_SAFETY")
                canonical = "/".join(parts)
                if canonical in exact:
                    fail("E_ARCHIVE_SAFETY")
                exact.add(canonical)
                folded_key = "/".join(
                    unicodedata.normalize("NFC", part).casefold() for part in parts
                )
                if folded_key in folded and folded[folded_key] != canonical:
                    fail("E_ARCHIVE_SAFETY")
                folded[folded_key] = canonical
                if any(
                    "/".join(parts[:depth]) in symlinks
                    for depth in range(1, len(parts))
                ):
                    fail("E_ARCHIVE_SAFETY")
                if member.islnk() or member.ischr() or member.isblk() or member.isfifo():
                    fail("E_ARCHIVE_SAFETY")
                if not (member.isdir() or member.isfile() or member.issym()):
                    fail("E_ARCHIVE_SAFETY")
                if member.size < 0 or member.size > MAX_MEMBER_SIZE:
                    fail("E_ARCHIVE_SAFETY")
                total += member.size
                if total > MAX_TOTAL_SIZE:
                    fail("E_ARCHIVE_SAFETY")
                if member.issym():
                    target = member.linkname
                    if (
                        not target
                        or target.startswith("/")
                        or "\\" in target
                        or "\x00" in target
                        or "" in target.split("/")
                    ):
                        fail("E_ARCHIVE_SAFETY")
                    resolved = posixpath.normpath(
                        posixpath.join(*parts[:-1], target)
                    )
                    if resolved == "candidate" or not resolved.startswith("candidate/"):
                        fail("E_ARCHIVE_SAFETY")
                    symlinks.add(canonical)
                members.append(member)
    except (OSError, tarfile.TarError):
        fail("E_ARCHIVE_SAFETY")
    return members


def _load_json_bytes(payload: bytes, code: str, maximum: int = MAX_JSON_SIZE) -> Any:
    if len(payload) > maximum:
        fail(code)
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, VerificationError):
        fail(code)


def verify_package_inventory(package_root: Path) -> None:
    actual: set[str] = set()
    folded: dict[str, str] = {}
    for path in package_root.rglob("*"):
        relative = path.relative_to(package_root).as_posix()
        parts = _archive_segments(relative)
        canonical = "/".join(parts)
        folded_key = "/".join(
            unicodedata.normalize("NFC", part).casefold() for part in parts
        )
        if folded_key in folded and folded[folded_key] != canonical:
            fail("E_PACKAGE_INVENTORY")
        folded[folded_key] = canonical
        try:
            stat_result = path.lstat()
        except OSError:
            fail("E_PACKAGE_INVENTORY")
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            fail("E_PACKAGE_INVENTORY")
        if path.is_file():
            if stat_result.st_nlink != 1:
                fail("E_PACKAGE_INVENTORY")
            actual.add(canonical)
    if actual != PACKAGE_FILES:
        fail("E_PACKAGE_INVENTORY")

    checksum_path = package_root / "SHA256SUMS.txt"
    try:
        raw = checksum_path.read_bytes()
    except OSError:
        fail("E_PACKAGE_INVENTORY")
    if not raw or not raw.endswith(b"\n") or raw.endswith(b"\n\n") or b"\r" in raw:
        fail("E_PACKAGE_CHECKSUM_FORMAT")
    entries: list[tuple[bytes, str]] = []
    seen: set[str] = set()
    pattern = re.compile(rb"([0-9a-f]{64})  ([!-~]+)\n")
    for line in raw.splitlines(keepends=True):
        matched = pattern.fullmatch(line)
        if matched is None:
            fail("E_PACKAGE_CHECKSUM_FORMAT")
        try:
            relative = matched.group(2).decode("ascii")
        except UnicodeDecodeError:
            fail("E_PACKAGE_CHECKSUM_FORMAT")
        canonical = "/".join(_archive_segments(relative))
        if canonical != relative or relative in seen or relative == "SHA256SUMS.txt":
            fail("E_PACKAGE_CHECKSUM_FORMAT")
        seen.add(relative)
        entries.append((matched.group(1), relative))
    if [relative.encode("ascii") for _, relative in entries] != sorted(
        relative.encode("ascii") for _, relative in entries
    ):
        fail("E_PACKAGE_CHECKSUM_FORMAT")
    if seen != PACKAGE_FILES - {"SHA256SUMS.txt"}:
        fail("E_PACKAGE_INVENTORY")
    for expected, relative in entries:
        try:
            actual_digest = _sha256(package_root / relative).encode("ascii")
        except OSError:
            fail("E_PACKAGE_CHECKSUM_DIGEST")
        if not _same(actual_digest, expected):
            fail("E_PACKAGE_CHECKSUM_DIGEST")


def load_evidence_policy(payload: bytes) -> dict[str, Any]:
    value = _load_json_bytes(payload, "E_EVIDENCE_POLICY")
    if not isinstance(value, dict) or set(value) != POLICY_KEYS:
        fail("E_EVIDENCE_POLICY")
    if value.get("schema_version") != "butler.box5.ac23-evidence-policy.v2":
        fail("E_EVIDENCE_POLICY")
    if value.get("object_format") != "sha1":
        fail("E_OBJECT_FORMAT_UNSUPPORTED")
    limits = value.get("limits")
    expected_limits = {
        "max_tar_members": MAX_MEMBERS,
        "max_total_bytes": MAX_TOTAL_SIZE,
        "max_single_file_bytes": MAX_MEMBER_SIZE,
        "max_json_bytes": MAX_JSON_SIZE,
        "max_junit_bytes": MAX_JUNIT_SIZE,
        "max_output_bytes_per_stream": 1 << 28,
    }
    if limits != expected_limits:
        fail("E_EVIDENCE_POLICY")
    runs = value.get("required_runs")
    if not isinstance(runs, list) or not runs:
        fail("E_EVIDENCE_POLICY")
    run_ids: set[str] = set()
    for run in runs:
        if not isinstance(run, dict) or set(run) != {
            "run_id", "argv", "cwd", "parser", "result_path", "required_results", "required"
        }:
            fail("E_EVIDENCE_POLICY")
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in run_ids:
            fail("E_EVIDENCE_POLICY")
        run_ids.add(run_id)
        if run.get("required") is not True or run.get("parser") not in {
            "pytest-junit", "vitest", "cargo", "integration-lock"
        }:
            fail("E_EVIDENCE_POLICY")
        if not isinstance(run.get("argv"), list) or not all(
            isinstance(item, str) and item for item in run["argv"]
        ):
            fail("E_EVIDENCE_POLICY")
        if not isinstance(run.get("cwd"), str) or not run["cwd"]:
            fail("E_EVIDENCE_POLICY")
        if not isinstance(run.get("result_path"), str):
            fail("E_EVIDENCE_POLICY")
        results = run.get("required_results")
        if not isinstance(results, list) or len(results) != len(set(results)) or not all(
            isinstance(item, str) and item for item in results
        ):
            fail("E_EVIDENCE_POLICY")
    frozen = value.get("frozen_acceptance")
    expected_ids = {
        *(f"AC-{number:02d}" for number in range(3, 12)),
        "AC-13", "AC-14", "AC-15",
        *(f"AC-{number:02d}" for number in range(17, 23)),
        "AC-24",
    }
    if not isinstance(frozen, list) or {item.get("acceptance_id") for item in frozen if isinstance(item, dict)} != expected_ids:
        fail("E_EVIDENCE_POLICY")
    for item in frozen:
        if not isinstance(item, dict) or set(item) != {"acceptance_id", "run_ids", "required_results"}:
            fail("E_EVIDENCE_POLICY")
        if not item["run_ids"] or not set(item["run_ids"]).issubset(run_ids):
            fail("E_EVIDENCE_POLICY")
        if not item["required_results"] or len(item["required_results"]) != len(set(item["required_results"])):
            fail("E_EVIDENCE_POLICY")
    categories = value.get("legacy_mutation_categories")
    if not isinstance(categories, list) or [item.get("category") for item in categories if isinstance(item, dict)] != list(range(1, 21)):
        fail("E_EVIDENCE_POLICY")
    all_legacy: list[str] = []
    for item in categories:
        if set(item) != {"category", "testcases"} or not isinstance(item["testcases"], list) or not item["testcases"]:
            fail("E_EVIDENCE_POLICY")
        all_legacy.extend(item["testcases"])
    if len(all_legacy) != 27 or len(set(all_legacy)) != 27:
        fail("E_EVIDENCE_POLICY")
    semantic = value.get("evidence_semantic_cases")
    if not isinstance(semantic, list) or len(semantic) != 36:
        fail("E_EVIDENCE_POLICY")
    if len({item.get("name") for item in semantic if isinstance(item, dict)}) != 36:
        fail("E_EVIDENCE_POLICY")
    for item in semantic:
        if not isinstance(item, dict) or set(item) != {"name", "testcase", "expected_error"}:
            fail("E_EVIDENCE_POLICY")
        if not all(isinstance(item[key], str) and item[key] for key in item):
            fail("E_EVIDENCE_POLICY")
    return value


def inspect_evidence_tar(path: Path) -> dict[str, bytes]:
    seen: set[str] = set()
    folded: dict[str, str] = {}
    payloads: dict[str, bytes] = {}
    total = 0
    try:
        archive = tarfile.open(path, "r:", encoding="utf-8", errors="strict")
        with archive:
            for index, member in enumerate(archive):
                if index >= MAX_MEMBERS:
                    fail("E_EVIDENCE_INVENTORY")
                parts = _archive_segments(member.name)
                canonical = "/".join(parts)
                if canonical in seen:
                    fail("E_EVIDENCE_INVENTORY")
                seen.add(canonical)
                folded_key = "/".join(unicodedata.normalize("NFC", part).casefold() for part in parts)
                if folded_key in folded and folded[folded_key] != canonical:
                    fail("E_EVIDENCE_INVENTORY")
                folded[folded_key] = canonical
                if not (member.isdir() or member.isfile()) or member.islnk() or member.issym():
                    fail("E_EVIDENCE_INVENTORY")
                if member.size < 0 or member.size > MAX_MEMBER_SIZE:
                    fail("E_EVIDENCE_INVENTORY")
                total += member.size
                if total > MAX_TOTAL_SIZE:
                    fail("E_EVIDENCE_INVENTORY")
                if member.isfile():
                    source = archive.extractfile(member)
                    if source is None:
                        fail("E_EVIDENCE_INVENTORY")
                    payloads[canonical] = source.read()
    except VerificationError:
        raise
    except (OSError, UnicodeError, tarfile.TarError):
        fail("E_EVIDENCE_INVENTORY")
    forbidden = (b"/Users/", b"/private/tmp/", b"\\Users\\")
    if any(marker in payload for payload in payloads.values() for marker in forbidden):
        fail("E_EVIDENCE_SEMANTICS")
    return payloads


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value) is None:
        fail("E_EVIDENCE_TIMESTAMP")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail("E_EVIDENCE_TIMESTAMP")


def parse_command_records(payload: bytes, policy: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        fail("E_EVIDENCE_COMMAND")
    runs = policy["required_runs"]
    if len(lines) != len(runs):
        fail("E_EVIDENCE_COMMAND")
    records: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    for sequence, (line, run) in enumerate(zip(lines, runs), start=1):
        entry = _load_json_bytes(line.encode("utf-8"), "E_EVIDENCE_COMMAND")
        if not isinstance(entry, dict) or set(entry) != COMMAND_KEYS:
            fail("E_EVIDENCE_COMMAND")
        if entry["sequence"] != sequence or entry["run_id"] != run["run_id"]:
            fail("E_EVIDENCE_COMMAND")
        if entry["argv"] != run["argv"] or entry["cwd"] != run["cwd"]:
            fail("E_EVIDENCE_COMMAND")
        if not isinstance(entry["exit_code"], int) or isinstance(entry["exit_code"], bool):
            fail("E_EVIDENCE_COMMAND")
        if entry["exit_code"] != 0:
            fail("E_EVIDENCE_NONZERO_EXIT")
        start = _timestamp(entry["start_utc"])
        end = _timestamp(entry["end_utc"])
        if start > end or (previous_end is not None and start < previous_end):
            fail("E_EVIDENCE_TIMESTAMP")
        previous_end = end
        expected_stdout = f"stdout/{sequence:04d}.bin"
        expected_stderr = f"stderr/{sequence:04d}.bin"
        if entry["stdout_path"] != expected_stdout or entry["stderr_path"] != expected_stderr:
            fail("E_EVIDENCE_COMMAND")
        for key in ("stdout_sha256", "stderr_sha256"):
            if not isinstance(entry[key], str) or re.fullmatch(r"[0-9a-f]{64}", entry[key]) is None:
                fail("E_EVIDENCE_COMMAND")
        records.append(entry)
    return records


def verify_command_raw_streams(payloads: dict[str, bytes], records: list[dict[str, Any]]) -> None:
    for record in records:
        for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
            relative = record[path_key]
            if relative not in payloads:
                fail("E_EVIDENCE_RAW_MISSING")
            if hashlib.sha256(payloads[relative]).hexdigest() != record[digest_key]:
                fail("E_EVIDENCE_RAW_DIGEST")


def parse_junit_results(payload: bytes) -> set[str]:
    if len(payload) > MAX_JUNIT_SIZE or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        fail("E_EVIDENCE_JUNIT")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        fail("E_EVIDENCE_JUNIT")
    if "}" in root.tag or root.tag not in {"testsuite", "testsuites"}:
        fail("E_EVIDENCE_JUNIT")
    suites = [root] if root.tag == "testsuite" else list(root)
    if not suites or any(suite.tag != "testsuite" or list(suite.findall("testsuite")) for suite in suites):
        fail("E_EVIDENCE_JUNIT")
    results: set[str] = set()
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        cases = [child for child in suite if child.tag == "testcase"]
        observed = {
            "tests": len(cases),
            "failures": sum(any(child.tag == "failure" for child in case) for case in cases),
            "errors": sum(any(child.tag == "error" for child in case) for case in cases),
            "skipped": sum(any(child.tag == "skipped" for child in case) for case in cases),
        }
        for key, count in observed.items():
            declared = suite.attrib.get(key, "0")
            if not declared.isdigit() or int(declared) != count:
                fail("E_EVIDENCE_JUNIT")
            totals[key] += count
        for case in cases:
            if "}" in case.tag or any("}" in child.tag for child in case):
                fail("E_EVIDENCE_JUNIT")
            if any(child.tag in {"failure", "error", "skipped"} for child in case):
                fail("E_EVIDENCE_JUNIT")
            classname = case.attrib.get("classname")
            name = case.attrib.get("name")
            if not classname or not name:
                fail("E_EVIDENCE_JUNIT")
            testcase = f"{classname}::{name}"
            if testcase in results:
                fail("E_EVIDENCE_TESTCASE_SET")
            results.add(testcase)
    if root.tag == "testsuites":
        for key, count in totals.items():
            declared = root.attrib.get(key)
            if declared is not None and (not declared.isdigit() or int(declared) != count):
                fail("E_EVIDENCE_JUNIT")
    return results


def _run_results(payloads: dict[str, bytes], records: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    for run, record in zip(policy["required_runs"], records):
        if run["parser"] == "pytest-junit":
            result_path = run["result_path"]
            if result_path not in payloads:
                fail("E_EVIDENCE_RAW_MISSING")
            results = parse_junit_results(payloads[result_path])
        elif run["parser"] == "vitest":
            results = {"vitest_exit=0"} if b"Tests" in payloads[record["stdout_path"]] and b"passed" in payloads[record["stdout_path"]] else set()
        elif run["parser"] == "cargo":
            results = {"cargo_exit=0"} if b"test result: ok." in payloads[record["stdout_path"]] else set()
        else:
            results = {"STATUS=PASS"} if b"STATUS=PASS" in payloads[record["stdout_path"]] else set()
        if not set(run["required_results"]).issubset(results):
            fail("E_EVIDENCE_SEMANTICS")
        output[run["run_id"]] = results
    return output


def verify_mutation_results(payloads: dict[str, bytes], policy: dict[str, Any]) -> None:
    relative = "mutation/mutation_results_v2.json"
    value = _load_json_bytes(payloads[relative], "E_EVIDENCE_SCHEMA")
    keys = {
        "schema_version", "argv", "cwd", "start_utc", "end_utc", "exit_code",
        "legacy_categories", "evidence_semantic_cases", "stdout_path", "stdout_sha256",
        "stderr_path", "stderr_sha256", "junit_path", "junit_sha256", "summary",
    }
    if not isinstance(value, dict) or set(value) != keys or any("provisional" in key for key in value):
        fail("E_EVIDENCE_SCHEMA")
    if value["schema_version"] != "butler.box5.ac23-mutation-results.v2" or value["exit_code"] != 0:
        fail("E_EVIDENCE_NONZERO_EXIT")
    if value["argv"] != [
        "python3", "-m", "pytest", "-q", "--disable-warnings",
        "tests/ac23/test_candidate_artifact_identity.py",
        "tests/ac23/test_evidence_semantics.py", "-k",
        "mutation or evidence_semantics_attack",
        "--junitxml=.ac23-mutation-run/results.xml", "--basetemp",
        ".ac23-mutation-run/tmp",
    ] or value["cwd"] != "candidate":
        fail("E_EVIDENCE_COMMAND")
    if _timestamp(value["start_utc"]) > _timestamp(value["end_utc"]):
        fail("E_EVIDENCE_TIMESTAMP")
    for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256"), ("junit_path", "junit_sha256")):
        path = value[path_key]
        if path not in payloads:
            fail("E_EVIDENCE_RAW_MISSING")
        if hashlib.sha256(payloads[path]).hexdigest() != value[digest_key]:
            fail("E_EVIDENCE_RAW_DIGEST")
    observed_tests = parse_junit_results(payloads[value["junit_path"]])
    expected_categories = policy["legacy_mutation_categories"]
    if value["legacy_categories"] != [
        {"category": item["category"], "testcases": item["testcases"], "status": "PASS"}
        for item in expected_categories
    ]:
        fail("E_EVIDENCE_MUTATION_MAPPING")
    expected_semantic = policy["evidence_semantic_cases"]
    if value["evidence_semantic_cases"] != [
        {**item, "status": "PASS"} for item in expected_semantic
    ]:
        fail("E_EVIDENCE_MUTATION_MAPPING")
    expected_tests = {
        testcase for item in expected_categories for testcase in item["testcases"]
    } | {item["testcase"] for item in expected_semantic}
    if observed_tests != expected_tests:
        fail("E_EVIDENCE_TESTCASE_SET")
    expected_summary = {
        "failed": 0,
        "legacy_categories_passed": 20,
        "legacy_subcases_passed": 27,
        "semantic_attacks_passed": 36,
    }
    if value["summary"] != expected_summary:
        fail("E_EVIDENCE_SUMMARY")


def verify_frozen_acceptance(payloads: dict[str, bytes], policy: dict[str, Any], run_results: dict[str, set[str]]) -> None:
    details = _load_json_bytes(payloads["regression/frozen_19_details.json"], "E_EVIDENCE_FROZEN_MAPPING")
    if not isinstance(details, list) or len(details) != 19:
        fail("E_EVIDENCE_FROZEN_MAPPING")
    expected: list[dict[str, Any]] = []
    for mapping in policy["frozen_acceptance"]:
        available = set().union(*(run_results[run_id] for run_id in mapping["run_ids"]))
        required = mapping["required_results"]
        if not set(required).issubset(available):
            fail("E_EVIDENCE_FROZEN_MAPPING")
        expected.append({
            "acceptance_id": mapping["acceptance_id"],
            "run_ids": mapping["run_ids"],
            "required_results": required,
            "observed_results": required,
            "status": "PASS",
        })
    if details != expected:
        fail("E_EVIDENCE_FROZEN_MAPPING")
    summary = _load_json_bytes(payloads["regression/frozen_19_summary.json"], "E_EVIDENCE_SUMMARY")
    if summary != {"failed": 0, "passed": 19, "total": 19}:
        fail("E_EVIDENCE_SUMMARY")


def verify_tree_reconstruction_evidence(payload: bytes, manifest: dict[str, Any]) -> None:
    value = _load_json_bytes(payload, "E_EVIDENCE_SCHEMA")
    expected = {
        "head_commit": manifest["head_commit"],
        "head_tree": manifest["head_tree"],
        "patch_applied_tree": manifest["patch_applied_tree"],
        "source_archive_tree": manifest["source_archive_tree"],
        "submitted_head_tree": manifest["submitted_head_tree"],
        "patch_command_id": "git-apply-index-v1",
        "source_reconstruction_id": "git-archive-index-v1",
    }
    if value != expected:
        fail("E_EVIDENCE_SEMANTICS")


def verify_evidence_semantics(path: Path, manifest: dict[str, Any], policy: dict[str, Any]) -> None:
    payloads = inspect_evidence_tar(path)
    base_required = {
        "environment.json", "commands.jsonl", "clean_status.bin", "tree_reconstruction.json",
        "regression/frozen_19_details.json", "regression/frozen_19_summary.json",
        "mutation/mutation_results_v2.json", "mutation/pytest_mutation.stdout.bin",
        "mutation/pytest_mutation.stderr.bin", "mutation/pytest_mutation.xml",
    }
    if not base_required.issubset(payloads):
        fail("E_EVIDENCE_INVENTORY")
    records = parse_command_records(payloads["commands.jsonl"], policy)
    expected_files = set(base_required)
    for sequence, run in enumerate(policy["required_runs"], start=1):
        expected_files.update({f"stdout/{sequence:04d}.bin", f"stderr/{sequence:04d}.bin"})
        if run["result_path"]:
            expected_files.add(run["result_path"])
    if payloads["clean_status.bin"] != b"":
        fail("E_CLEAN_STATUS")
    environment = _load_json_bytes(payloads["environment.json"], "E_EVIDENCE_SCHEMA")
    if not isinstance(environment, dict) or set(environment) != {"os", "architecture", "git", "python", "locale", "timezone"} or environment["locale"] != "C" or environment["timezone"] != "UTC":
        fail("E_EVIDENCE_SCHEMA")
    verify_command_raw_streams(payloads, records)
    if set(payloads) != expected_files:
        fail("E_EVIDENCE_INVENTORY")
    run_results = _run_results(payloads, records, policy)
    verify_mutation_results(payloads, policy)
    verify_frozen_acceptance(payloads, policy, run_results)
    verify_tree_reconstruction_evidence(payloads["tree_reconstruction.json"], manifest)


def _extract_source_tar(path: Path, destination: Path, members: list[tarfile.TarInfo]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = tarfile.open(path, "r:*", encoding="utf-8", errors="surrogateescape")
        with archive:
            materialized = {member.name: member for member in archive.getmembers()}
            for member in members:
                if member.issym():
                    continue
                parts = _archive_segments(member.name)
                output = destination.joinpath(*parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                if member.isdir():
                    output.mkdir(exist_ok=True)
                    os.chmod(output, member.mode & 0o777)
                    continue
                source = archive.extractfile(materialized[member.name])
                if source is None:
                    fail("E_ARCHIVE_SAFETY")
                with source, output.open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                os.chmod(output, member.mode & 0o777)
            for member in members:
                if not member.issym():
                    continue
                parts = _archive_segments(member.name)
                output = destination.joinpath(*parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(member.linkname, output)
    except (OSError, tarfile.TarError):
        fail("E_ARCHIVE_SAFETY")


def _write_loose_blob(repository: Path, payload: bytes, object_format: str) -> bytes:
    framed = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    oid = hashlib.new(object_format, framed).hexdigest().encode("ascii")
    object_path = repository / ".git" / "objects" / oid[:2].decode("ascii") / oid[2:].decode("ascii")
    if not object_path.exists():
        object_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = object_path.with_name(object_path.name + ".tmp")
        with temporary.open("xb") as stream:
            stream.write(zlib.compress(framed))
        os.replace(temporary, object_path)
    return oid


def _source_tree(
    path: Path, temporary: Path, object_format: str = "sha1"
) -> tuple[str, bool]:
    temporary.mkdir(parents=True, exist_ok=True)
    members = _inspect_source_tar(path)
    _extract_source_tar(path, temporary / "extracted", members)
    repository = temporary / "tree-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--quiet", f"--object-format={object_format}")
    except subprocess.CalledProcessError:
        fail("E_SOURCE_TREE")
    rows: list[tuple[bytes, bytes]] = []
    self_reference = False
    try:
        archive = tarfile.open(path, "r:*", encoding="utf-8", errors="surrogateescape")
        with archive:
            by_name = {member.name: member for member in archive.getmembers()}
            for member in members:
                parts = _archive_segments(member.name)
                if len(parts) == 1 or member.isdir():
                    continue
                relative = "/".join(parts[1:]).encode("utf-8", "surrogateescape")
                if parts[-1] == "candidate_artifact_identity.json":
                    self_reference = True
                if member.issym():
                    payload = member.linkname.encode("utf-8", "surrogateescape")
                    mode = b"120000"
                else:
                    source = archive.extractfile(by_name[member.name])
                    if source is None:
                        fail("E_SOURCE_TREE")
                    payload = source.read()
                    mode = b"100755" if member.mode & 0o111 else b"100644"
                    if member.name.endswith(".json") and len(payload) <= MAX_MANIFEST_SIZE:
                        try:
                            parsed = json.loads(payload.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            parsed = None
                        if isinstance(parsed, dict) and parsed.get("schema_version") == SCHEMA_VERSION:
                            self_reference = True
                oid = _write_loose_blob(repository, payload, object_format)
                rows.append((relative, mode + b" " + oid + b"\t" + relative + b"\0"))
        rows.sort(key=lambda item: item[0])
        index_input = b"".join(row for _, row in rows)
        _git(repository, "update-index", "-z", "--index-info", input_bytes=index_input)
        tree = _git(repository, "write-tree").stdout.decode("ascii").strip()
    except (OSError, tarfile.TarError, subprocess.CalledProcessError):
        fail("E_SOURCE_TREE")
    return tree, self_reference


def _changed_paths(repository: Path, base: str, head: str) -> bytes:
    try:
        output = _git(
            repository,
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            base,
            head,
            "--",
        ).stdout
    except subprocess.CalledProcessError:
        fail("E_CHANGED_PATH_DIGEST")
    if output and not output.endswith(b"\0"):
        fail("E_CHANGED_PATH_DIGEST")
    paths = output[:-1].split(b"\0") if output else []
    if len(paths) != len(set(paths)):
        fail("E_CHANGED_PATH_DIGEST")
    for path in paths:
        if not path or path.startswith(b"/") or b"\\" in path:
            fail("E_CHANGED_PATH_DIGEST")
        if any(segment in {b"", b".", b".."} for segment in path.split(b"/")):
            fail("E_CHANGED_PATH_DIGEST")
    return b"".join(path + b"\0" for path in sorted(paths))


def _prepare_bundle(bundle: Path, temporary: Path, manifest: dict[str, Any]) -> tuple[Path, str]:
    repository = temporary / "bundle-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--bare", "--quiet")
        verified = _git(repository, "bundle", "verify", bundle)
        verification_text = (verified.stdout + verified.stderr).decode("utf-8", "replace")
        if "complete history" not in verification_text.lower():
            fail("E_BUNDLE")
        heads = _git(repository, "bundle", "list-heads", bundle).stdout.splitlines()
        selected_ref: str | None = None
        for line in heads:
            oid, separator, ref = line.partition(b" ")
            if separator and oid.decode("ascii", "strict") == manifest["head_commit"]:
                selected_ref = ref.decode("utf-8", "surrogateescape")
                break
        if selected_ref is None:
            fail("E_HEAD_OBJECT")
        _git(
            repository,
            "fetch",
            "--no-tags",
            bundle,
            f"{selected_ref}:refs/ac23/candidate",
        )
        object_format = _git(repository, "rev-parse", "--show-object-format").stdout.decode(
            "ascii"
        ).strip()
    except VerificationError:
        raise
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_BUNDLE")
    return repository, object_format


def _verify_objects(repository: Path, manifest: dict[str, Any], object_format: str) -> None:
    if object_format != manifest["object_format"]:
        fail("E_SCHEMA")
    try:
        if _git(repository, "cat-file", "-t", manifest["base_commit"]).stdout.strip() != b"commit":
            fail("E_BASE_OBJECT")
    except subprocess.CalledProcessError:
        fail("E_BASE_OBJECT")
    try:
        actual_base_tree = _git(
            repository, "show", "-s", "--format=%T", manifest["base_commit"]
        ).stdout.decode("ascii").strip()
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_BASE_TREE")
    if not _same(actual_base_tree, manifest["base_tree"]):
        fail("E_BASE_TREE")
    try:
        if _git(repository, "cat-file", "-t", manifest["head_commit"]).stdout.strip() != b"commit":
            fail("E_HEAD_OBJECT")
    except subprocess.CalledProcessError:
        fail("E_HEAD_OBJECT")
    try:
        actual_head_tree = _git(
            repository, "show", "-s", "--format=%T", manifest["head_commit"]
        ).stdout.decode("ascii").strip()
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_HEAD_TREE")
    if not _same(actual_head_tree, manifest["head_tree"]):
        fail("E_HEAD_TREE")
    ancestry = _git(
        repository,
        "merge-base",
        "--is-ancestor",
        manifest["base_commit"],
        manifest["head_commit"],
        check=False,
    )
    if ancestry.returncode != 0:
        fail("E_ANCESTRY")


def _patch_tree(bundle: Path, patch: Path, temporary: Path, manifest: dict[str, Any]) -> str:
    repository = temporary / "patch-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--quiet")
        _git(
            repository,
            "fetch",
            "--no-tags",
            bundle,
            "refs/heads/candidate:refs/ac23/candidate",
        )
        _git(repository, "checkout", "--detach", "--force", manifest["base_commit"])
        before = _git(
            repository, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ).stdout
        if before:
            fail("E_CLEAN_STATUS")
        checked = _git(repository, "apply", "--check", "--binary", patch, check=False)
        if checked.returncode != 0:
            fail("E_PATCH_APPLY")
        applied = _git(
            repository, "apply", "--binary", "--index", patch, check=False
        )
        if applied.returncode != 0:
            fail("E_PATCH_APPLY")
        if _git(repository, "diff", "--cached", "--check", check=False).returncode != 0:
            fail("E_PATCH_APPLY")
        status = _git(
            repository, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ).stdout
        if any(record.startswith(b"?? ") for record in status.split(b"\0") if record):
            fail("E_PATCH_APPLY")
        return _git(repository, "write-tree").stdout.decode("ascii").strip()
    except VerificationError:
        raise
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_PATCH_APPLY")


def _checkout_clean(bundle: Path, temporary: Path, manifest: dict[str, Any]) -> None:
    repository = temporary / "checkout-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--quiet")
        _git(
            repository,
            "fetch",
            "--no-tags",
            bundle,
            "refs/heads/candidate:refs/ac23/candidate",
        )
        _git(repository, "checkout", "--detach", "--force", manifest["head_commit"])
        status = _git(
            repository, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ).stdout
    except subprocess.CalledProcessError:
        fail("E_CLEAN_STATUS")
    if status:
        fail("E_CLEAN_STATUS")


def verify(package_root: Path, expected_repository_url: str | None = None) -> None:
    package_root = package_root.resolve()
    if not package_root.is_dir():
        fail("E_SCHEMA")
    verify_package_inventory(package_root)
    manifest = _load_manifest(
        package_root / "IDENTITY" / "candidate_artifact_identity.json"
    )
    try:
        packaged_policy_bytes = (
            package_root / "VERIFY" / "evidence_policy_v2.json"
        ).read_bytes()
    except OSError:
        fail("E_EVIDENCE_POLICY")
    policy = load_evidence_policy(packaged_policy_bytes)

    normalized = normalize_repository_url(manifest["repository_url"])
    if not _same(normalized, manifest["repository_url"]):
        fail("E_REPOSITORY_URL")
    if not _same(normalized, APPROVED_REPOSITORY_URL):
        fail("E_REPOSITORY_URL")
    if expected_repository_url is not None:
        expected = normalize_repository_url(expected_repository_url)
        if not _same(normalized, expected):
            fail("E_REPOSITORY_URL")
    if not _same(manifest["base_commit"], APPROVED_BASE_COMMIT):
        fail("E_BASE_OBJECT")
    if not _same(manifest["base_tree"], APPROVED_BASE_TREE):
        fail("E_BASE_TREE")
    if manifest["normative_contract_path"] != NORMATIVE_CONTRACT_PATH:
        fail("E_CONTRACT_DIGEST")
    if not _same(manifest["normative_contract_sha256"], NORMATIVE_CONTRACT_SHA256):
        fail("E_CONTRACT_DIGEST")

    paths = {
        "patch": package_root / "PATCH" / "cumulative.patch",
        "source": package_root / "SOURCE" / "candidate_source.tar",
        "changed": package_root / "IDENTITY" / "changed_paths.nul",
        "evidence": package_root / "EVIDENCE" / "evidence_raw.tar",
        "bundle": package_root / "SOURCE" / "candidate_repository.bundle",
    }
    digest_checks = (
        ("patch", "patch_sha256", "E_PATCH_DIGEST"),
        ("source", "source_archive_sha256", "E_SOURCE_DIGEST"),
        ("changed", "changed_path_manifest_sha256", "E_CHANGED_PATH_DIGEST"),
        ("evidence", "evidence_sha256", "E_EVIDENCE_DIGEST"),
    )
    for file_key, manifest_key, error_code in digest_checks:
        try:
            actual = _sha256(paths[file_key])
        except OSError:
            fail(error_code)
        if not _same(actual, manifest[manifest_key]):
            fail(error_code)

    with tempfile.TemporaryDirectory(prefix="ac23-verify-") as temporary_text:
        temporary = Path(temporary_text)
        repository, object_format = _prepare_bundle(paths["bundle"], temporary, manifest)
        _verify_objects(repository, manifest, object_format)
        try:
            committed_policy_bytes = _git(
                repository, "show", f"{manifest['head_commit']}:{POLICY_PATH}"
            ).stdout
        except subprocess.CalledProcessError:
            fail("E_EVIDENCE_POLICY")
        if not _same(committed_policy_bytes, packaged_policy_bytes):
            fail("E_EVIDENCE_POLICY")
        verify_evidence_semantics(paths["evidence"], manifest, policy)

        try:
            contract = _git(
                repository,
                "show",
                f"{manifest['head_commit']}:{NORMATIVE_CONTRACT_PATH}",
            ).stdout
        except subprocess.CalledProcessError:
            fail("E_CONTRACT_DIGEST")
        contract_digest = hashlib.sha256(contract).hexdigest()
        if not _same(contract_digest, manifest["normative_contract_sha256"]):
            fail("E_CONTRACT_DIGEST")

        expected_changed = _changed_paths(
            repository, manifest["base_commit"], manifest["head_commit"]
        )
        try:
            submitted_changed = paths["changed"].read_bytes()
        except OSError:
            fail("E_CHANGED_PATH_DIGEST")
        if not _same(expected_changed, submitted_changed):
            fail("E_CHANGED_PATH_DIGEST")

        patch_tree = _patch_tree(paths["bundle"], paths["patch"], temporary, manifest)
        if not _same(patch_tree, manifest["patch_applied_tree"]):
            fail("E_PATCH_TREE")

        source_tree, self_reference = _source_tree(
            paths["source"], temporary / "source-verification", object_format
        )
        if self_reference:
            fail("E_SELF_REFERENCE")
        if not _same(source_tree, manifest["source_archive_tree"]):
            fail("E_SOURCE_TREE")

        expected_tree = manifest["head_tree"]
        tree_values = (
            manifest["submitted_head_tree"],
            manifest["patch_applied_tree"],
            manifest["source_archive_tree"],
            patch_tree,
            source_tree,
        )
        if any(not _same(value, expected_tree) for value in tree_values):
            fail("E_TREE_MISMATCH")
        _checkout_clean(paths["bundle"], temporary, manifest)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Butler AC-23 candidate identity")
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--expected-repository-url")
    args = parser.parse_args(argv)
    try:
        verify(args.package_root, args.expected_repository_url)
    except VerificationError as error:
        print(
            json.dumps(
                {"ac23_pass": 0, "error_code": error.code},
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {"ac23_pass": 0, "error_code": "E_SCHEMA"},
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print('{"ac23_pass":1,"error_code":""}')
    print("AC23_PASS=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
