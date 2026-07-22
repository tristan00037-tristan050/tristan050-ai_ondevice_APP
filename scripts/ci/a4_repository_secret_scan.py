#!/usr/bin/env python3
"""Fail-closed secret scan for the Box5 A4 merge gate.

The scanner inspects the complete tracked worktree and every reachable Git blob.
It never emits matched values or repository-relative paths. Findings contain only
rule identifiers, object identifiers, line numbers, and one-way path digests.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import re
import subprocess
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


SCHEMA_VERSION = "butler.box5.a4.repository_secret_scan.v1"
DEFAULT_MAX_BLOB_BYTES = 32 * 1024 * 1024
MAX_DECODED_CANDIDATE_BYTES = 16 * 1024


@dataclass(frozen=True)
class SecretRule:
    rule_id: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Finding:
    scope: str
    rule_id: str
    object_id: str
    path_digest: str
    line_number: int
    line_digest: str
    encoding: str


@dataclass(frozen=True)
class ScanError:
    scope: str
    error_code: str
    object_id: str
    path_digest: str


@dataclass(frozen=True)
class ScanSummary:
    tracked_objects: int
    history_blobs: int
    findings: tuple[Finding, ...]
    errors: tuple[ScanError, ...]
    baseline_suppressed: int = 0
    stale_baseline_entries: int = 0
    rotation_suppressed: int = 0
    rotation_evidence_status: str = "NOT_PROVIDED"

    @property
    def ok(self) -> bool:
        return (
            not self.findings
            and not self.errors
            and self.rotation_evidence_status != "BLOCKED_EXTERNAL"
        )


DIRECT_RULES: tuple[SecretRule, ...] = (
    SecretRule("OPENAI_API_KEY", re.compile(r"\b(?P<secret>sk-(?:proj-|live-)?[A-Za-z0-9._-]{16,})\b")),
    SecretRule("AWS_ACCESS_KEY", re.compile(r"\b(?P<secret>(?:AKIA|ASIA)[0-9A-Z]{16})\b")),
    SecretRule(
        "AZURE_SECRET",
        re.compile(
            r"(?i)\b(?:AccountKey|AZURE_[A-Z0-9_]*(?:KEY|SECRET))\s*[=:]\s*"
            r"[\"']?(?!\$\{|\{\{)(?P<secret>[A-Za-z0-9+/._-]{20,}={0,2})"
        ),
    ),
    SecretRule(
        "GITHUB_TOKEN",
        re.compile(r"\b(?P<secret>(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}))\b"),
    ),
    SecretRule("SLACK_TOKEN", re.compile(r"\b(?P<secret>xox[baprs]-[A-Za-z0-9-]{16,})\b")),
    SecretRule(
        "JWT",
        re.compile(r"\b(?P<secret>eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})\b"),
    ),
    SecretRule(
        "GENERIC_BEARER",
        re.compile(r"(?i)\bBearer[ \t]+(?!\$\{|\{\{)(?P<secret>[A-Za-z0-9._~+/=-]{16,})\b"),
    ),
    SecretRule(
        "PASSWORD_URI",
        re.compile(
            r"(?i)\b[a-z][a-z0-9+.-]{1,15}://[^\s/:@]{1,128}:"
            r"(?P<secret>(?!\$\{|\{\{)[^\s/@]{8,128})@"
        ),
    ),
    SecretRule(
        "PRIVATE_KEY_HEADER",
        re.compile(r"-----BEGIN[ \t]+(?:RSA[ \t]+|EC[ \t]+|OPENSSH[ \t]+|DSA[ \t]+)?PRIVATE KEY-----"),
    ),
)

GENERIC_ENV_SECRET_RE = re.compile(
    r"(?i)^[ \t]*(?:export[ \t]+)?(?:password|passwd|pwd|api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|client[_-]?secret|export[_-]?sign[_-]?secret)[ \t]*=[ \t]*"
    r"[\"']?(?P<secret>[^\s\"'#]{8,})[\"']?[ \t]*(?:#.*)?$"
)
GENERIC_STRUCTURED_SECRET_RE = re.compile(
    r"(?i)[\"']?(?:password|passwd|pwd|api[_-]?key|access[_-]?token|auth[_-]?token|"
    r"client[_-]?secret|export[_-]?sign[_-]?secret)[\"']?[ \t]*:[ \t]*"
    r"[\"'](?P<secret>[^\"']{8,})[\"']"
)

BASE64_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")
HEX_CANDIDATE_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])")
URL_ENCODED_CANDIDATE_RE = re.compile(r"(?:%[0-9A-Fa-f]{2}){4,}")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()


def _path_digest(path: str) -> str:
    return _sha256_text(path)


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _plausible_secret(value: str) -> bool:
    lowered = value.casefold()
    if any(
        marker in lowered
        for marker in (
            "example", "sample", "dummy", "redacted", "changeme", "change-me",
            "replace-me", "your-", "placeholder", "not-a-real", "fake-token",
        )
    ):
        return False
    if any(character in value for character in ("$", "{", "}", "<", ">", "*")):
        return False
    if re.search(r"(?:abcde|01234|12345|qwerty|(?:[a-z]\d){4,})", lowered):
        return False
    compact = re.sub(r"[^A-Za-z0-9]", "", value)
    return len(compact) >= 8 and len(set(compact)) >= 6 and _entropy(compact) >= 2.8


def _rule_match_is_plausible(rule_id: str, match: re.Match[str]) -> bool:
    if rule_id == "PRIVATE_KEY_HEADER":
        return True
    secret = match.groupdict().get("secret") or ""
    if rule_id == "PASSWORD_URI" and re.search(r"(?i)(?:localhost|example\.(?:com|org|net)|\.invalid)(?:[:/]|$)", match.group(0)):
        return False
    if rule_id == "JWT":
        try:
            for segment in secret.split(".")[:2]:
                decoded = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
                if not isinstance(json.loads(decoded), dict):
                    return False
        except (ValueError, UnicodeError, json.JSONDecodeError):
            return False
    return _plausible_secret(secret)


def _decode_text_variants(payload: bytes) -> tuple[tuple[str, str], ...]:
    variants: list[tuple[str, str]] = [("utf-8", payload.decode("utf-8", errors="replace"))]
    if payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16" if payload.startswith(b"\xff\xfe") else "utf-16-be"
        try:
            variants.append((encoding, payload.decode(encoding, errors="strict")))
        except UnicodeError:
            pass
    return tuple(variants)


def _direct_matches(text: str) -> Iterator[tuple[str, int, str]]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule in DIRECT_RULES:
            match = rule.pattern.search(line)
            if match and _rule_match_is_plausible(rule.rule_id, match):
                yield rule.rule_id, line_number, _sha256_text(line)
        for pattern in (GENERIC_ENV_SECRET_RE, GENERIC_STRUCTURED_SECRET_RE):
            match = pattern.search(line)
            if match and _plausible_secret(match.group("secret")):
                yield "GENERIC_SECRET_ASSIGNMENT", line_number, _sha256_text(line)


def _decoded_matches(text: str) -> Iterator[tuple[str, int, str, str]]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        decoded_values: list[tuple[str, str]] = []
        if URL_ENCODED_CANDIDATE_RE.search(line):
            decoded_values.append(("url", urllib.parse.unquote(line)))
        for match in BASE64_CANDIDATE_RE.finditer(line):
            token = match.group(0)
            if len(token) > MAX_DECODED_CANDIDATE_BYTES * 2:
                continue
            try:
                padded = token + "=" * (-len(token) % 4)
                decoded = base64.b64decode(padded, validate=True)
            except (ValueError, base64.binascii.Error):
                continue
            if len(decoded) <= MAX_DECODED_CANDIDATE_BYTES:
                decoded_values.append(("base64", decoded.decode("utf-8", errors="replace")))
        for match in HEX_CANDIDATE_RE.finditer(line):
            token = match.group(0)
            if len(token) % 2 or len(token) > MAX_DECODED_CANDIDATE_BYTES * 2:
                continue
            try:
                decoded = bytes.fromhex(token)
            except ValueError:
                continue
            decoded_values.append(("hex", decoded.decode("utf-8", errors="replace")))
        for encoding, decoded_text in decoded_values:
            for rule_id, _, _ in _direct_matches(decoded_text):
                yield f"{encoding.upper()}_ENCODED_{rule_id}", line_number, _sha256_text(line), encoding


def scan_payload(*, scope: str, object_id: str, path: str, payload: bytes) -> tuple[Finding, ...]:
    findings: dict[tuple[str, str, str, int, str], Finding] = {}
    path_hash = _path_digest(path)
    for text_encoding, text in _decode_text_variants(payload):
        for rule_id, line_number, line_digest in _direct_matches(text):
            finding = Finding(scope, rule_id, object_id, path_hash, line_number, line_digest, text_encoding)
            findings[(rule_id, object_id, path_hash, line_number, line_digest)] = finding
        for rule_id, line_number, line_digest, encoding in _decoded_matches(text):
            finding = Finding(scope, rule_id, object_id, path_hash, line_number, line_digest, encoding)
            findings[(rule_id, object_id, path_hash, line_number, line_digest)] = finding
    return tuple(sorted(findings.values(), key=lambda item: (item.path_digest, item.line_number, item.rule_id)))


def _git(repo: Path, args: Sequence[str], *, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git command failed: {' '.join(args)}")
    return completed.stdout


def _tracked_blob_index(repo: Path) -> tuple[tuple[str, int, str], ...]:
    raw = _git(repo, ["ls-files", "-s", "-z"])
    entries: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, path_bytes = record.split(b"\t", 1)
        _, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise RuntimeError("unmerged tracked entry")
        path = path_bytes.decode("utf-8", errors="surrogateescape")
        entries.append((object_id, path))
    query = b"".join(object_id.encode("ascii") + b"\n" for object_id, _ in entries)
    checked = _git(
        repo,
        ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        input_bytes=query,
    ).decode("ascii").splitlines()
    if len(checked) != len(entries):
        raise RuntimeError("git cat-file omitted a tracked object")
    result: list[tuple[str, int, str]] = []
    # The product still supports the bundled Python 3.9 runtime. Length equality
    # is checked immediately above, so strict=True would add no safety here and
    # would make the scanner itself unavailable on that supported runtime.
    for (object_id, path), line in zip(entries, checked):
        returned_id, object_type, size_text = line.split()
        if returned_id != object_id or object_type != "blob":
            raise RuntimeError("tracked object is not a blob")
        result.append((object_id, int(size_text), path))
    return tuple(result)


def _history_blob_index(repo: Path) -> tuple[tuple[str, int, str], ...]:
    objects = _git(repo, ["-c", "core.quotePath=false", "rev-list", "--objects", "--all"])
    checked = _git(
        repo,
        ["cat-file", "--batch-check=%(objectname)\t%(objecttype)\t%(objectsize)\t%(rest)"],
        input_bytes=objects,
    )
    blobs: dict[str, tuple[int, str]] = {}
    for raw_line in checked.decode("utf-8", errors="surrogateescape").splitlines():
        parts = raw_line.split("\t", 3)
        if len(parts) != 4:
            continue
        object_id, object_type, size_text, path = parts
        if object_type == "blob" and object_id not in blobs:
            blobs[object_id] = (int(size_text), path)
    return tuple((object_id, size, path) for object_id, (size, path) in sorted(blobs.items()))


def _read_blobs(repo: Path, blobs: Sequence[tuple[str, int, str]]) -> Iterator[tuple[str, str, bytes]]:
    process = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        for object_id, expected_size, path in blobs:
            process.stdin.write(object_id.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii", errors="strict").strip().split()
            if len(header) != 3 or header[1] != "blob" or int(header[2]) != expected_size:
                raise RuntimeError("git cat-file returned an invalid blob header")
            payload = process.stdout.read(expected_size)
            terminator = process.stdout.read(1)
            if len(payload) != expected_size or terminator != b"\n":
                raise RuntimeError("git cat-file returned a truncated blob")
            yield object_id, path, payload
    finally:
        process.stdin.close()
        process.wait(timeout=30)
        if process.returncode != 0:
            raise RuntimeError("git cat-file batch failed")


def scan_repository(repo: Path, *, max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> ScanSummary:
    repo = repo.resolve()
    findings: list[Finding] = []
    errors: list[ScanError] = []
    tracked = _tracked_blob_index(repo)
    eligible_tracked: list[tuple[str, int, str]] = []
    for object_id, size, path in tracked:
        if size > max_blob_bytes:
            errors.append(ScanError("tracked", "OVERSIZED_TRACKED_FILE", object_id, _path_digest(path)))
        else:
            eligible_tracked.append((object_id, size, path))
    for object_id, path, payload in _read_blobs(repo, eligible_tracked):
        findings.extend(scan_payload(scope="tracked", object_id=object_id, path=path, payload=payload))

    history_blobs = _history_blob_index(repo)
    eligible: list[tuple[str, int, str]] = []
    for object_id, size, path in history_blobs:
        if size > max_blob_bytes:
            errors.append(ScanError("history", "OVERSIZED_HISTORY_BLOB", object_id, _path_digest(path)))
        else:
            eligible.append((object_id, size, path))
    for object_id, path, payload in _read_blobs(repo, eligible):
        findings.extend(scan_payload(scope="history", object_id=object_id, path=path, payload=payload))

    unique_findings = tuple(
        sorted(
            set(findings),
            key=lambda item: (item.scope, item.path_digest, item.object_id, item.line_number, item.rule_id),
        )
    )
    return ScanSummary(len(tracked), len(history_blobs), unique_findings, tuple(errors))


def _finding_baseline_key(item: Finding) -> tuple[str, str, str, str]:
    return item.scope, item.rule_id, item.path_digest, item.line_digest


def apply_baseline(summary: ScanSummary, baseline_path: Path) -> ScanSummary:
    document = json.loads(baseline_path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != "butler.box5.a4.secret_scan_baseline.v5.5"
        or not isinstance(document.get("entries"), list)
    ):
        raise ValueError("secret scan baseline is invalid")
    baseline_keys: set[tuple[str, str, str, str]] = set()
    for entry in document["entries"]:
        if not isinstance(entry, dict) or set(entry) != {
            "scope", "rule_id", "path_digest", "line_digest", "reason"
        }:
            raise ValueError("secret scan baseline entry is invalid")
        if entry["scope"] not in {"tracked", "history"} or entry["reason"] != "AUDITED_NON_SECRET_FIXTURE_OR_PLACEHOLDER":
            raise ValueError("secret scan baseline entry is not auditable")
        for name in ("path_digest", "line_digest"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(entry[name])):
                raise ValueError("secret scan baseline digest is invalid")
        baseline_keys.add(
            (entry["scope"], entry["rule_id"], entry["path_digest"], entry["line_digest"])
        )
    observed_keys = {_finding_baseline_key(item) for item in summary.findings}
    remaining = tuple(
        item for item in summary.findings if _finding_baseline_key(item) not in baseline_keys
    )
    return ScanSummary(
        summary.tracked_objects,
        summary.history_blobs,
        remaining,
        summary.errors,
        baseline_suppressed=len(summary.findings) - len(remaining),
        stale_baseline_entries=len(baseline_keys - observed_keys),
        rotation_suppressed=summary.rotation_suppressed,
        rotation_evidence_status=summary.rotation_evidence_status,
    )


_ROTATION_TOP_LEVEL_FIELDS = {
    "schema_version",
    "status",
    "raw_values_included",
    "raw_paths_included",
    "exposure_scope",
    "exposure_blob_oid",
    "source_path_digest",
    "finding_rule_id",
    "finding_line_digest",
    "credentials",
    "merge_gate",
}
_ROTATION_CREDENTIAL_FIELDS = {
    "credential_id",
    "status",
    "revoked_at_utc",
    "rotated_at_utc",
    "rotated_by",
    "evidence_url",
    "evidence_sha256",
}
_ROTATION_CREDENTIAL_IDS = {"DATABASE_URL", "EXPORT_SIGN_SECRET"}


def _is_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0)


def _is_safe_actor(value: object) -> bool:
    return (
        isinstance(value, str)
        and 3 <= len(value) <= 128
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _is_https_evidence_url(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    parsed = urllib.parse.urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


def _validate_rotation_credential(entry: object) -> tuple[str, bool]:
    if not isinstance(entry, dict) or set(entry) != _ROTATION_CREDENTIAL_FIELDS:
        raise ValueError("secret rotation credential entry is invalid")
    credential_id = entry.get("credential_id")
    if credential_id not in _ROTATION_CREDENTIAL_IDS:
        raise ValueError("secret rotation credential id is invalid")
    status = entry.get("status")
    evidence_fields = (
        entry.get("revoked_at_utc"),
        entry.get("rotated_at_utc"),
        entry.get("rotated_by"),
        entry.get("evidence_url"),
        entry.get("evidence_sha256"),
    )
    if status == "ROTATION_EVIDENCE_REQUIRED":
        if any(value is not None for value in evidence_fields):
            raise ValueError("incomplete rotation evidence must not be partially asserted")
        return credential_id, False
    if status != "ROTATED":
        raise ValueError("secret rotation credential status is invalid")
    if not _is_utc_timestamp(entry.get("revoked_at_utc")):
        raise ValueError("secret revocation timestamp is invalid")
    if not _is_utc_timestamp(entry.get("rotated_at_utc")):
        raise ValueError("secret rotation timestamp is invalid")
    if not _is_safe_actor(entry.get("rotated_by")):
        raise ValueError("secret rotation actor is invalid")
    if not _is_https_evidence_url(entry.get("evidence_url")):
        raise ValueError("secret rotation evidence URL is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("evidence_sha256"))):
        raise ValueError("secret rotation evidence digest is invalid")
    return credential_id, True


def apply_rotation_evidence(summary: ScanSummary, status_path: Path) -> ScanSummary:
    """Release one exact historical finding only after complete external rotation proof.

    The status document never contains the old or replacement credential values. A
    completed attestation is bound to one Git object, one path digest, one line
    digest, and both affected credential identifiers. Any malformed or partial
    claim fails the scan rather than weakening it.
    """

    document = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != _ROTATION_TOP_LEVEL_FIELDS:
        raise ValueError("secret rotation status is invalid")
    if document.get("schema_version") != "butler.box5.a4.secret_rotation_status.v5.5":
        raise ValueError("secret rotation schema is invalid")
    if document.get("raw_values_included") is not False or document.get("raw_paths_included") is not False:
        raise ValueError("secret rotation status must remain raw-zero")
    if document.get("exposure_scope") != "history":
        raise ValueError("secret rotation exposure scope is invalid")
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", str(document.get("exposure_blob_oid"))):
        raise ValueError("secret rotation object id is invalid")
    for name in ("source_path_digest", "finding_line_digest"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(document.get(name))):
            raise ValueError("secret rotation finding digest is invalid")
    if not isinstance(document.get("finding_rule_id"), str) or not document["finding_rule_id"]:
        raise ValueError("secret rotation finding rule is invalid")
    credentials = document.get("credentials")
    if not isinstance(credentials, list) or len(credentials) != len(_ROTATION_CREDENTIAL_IDS):
        raise ValueError("secret rotation credential set is invalid")
    validated = [_validate_rotation_credential(item) for item in credentials]
    if {credential_id for credential_id, _ in validated} != _ROTATION_CREDENTIAL_IDS:
        raise ValueError("secret rotation credential set is incomplete")

    status = document.get("status")
    if status == "BLOCKED_EXTERNAL":
        if any(is_complete for _, is_complete in validated):
            raise ValueError("partial rotation completion is not accepted")
        if document.get("merge_gate") != "BLOCKED_UNTIL_ALL_ROTATION_EVIDENCE_IS_PRESENT":
            raise ValueError("secret rotation blocked merge gate is invalid")
        return ScanSummary(
            summary.tracked_objects,
            summary.history_blobs,
            summary.findings,
            summary.errors,
            summary.baseline_suppressed,
            summary.stale_baseline_entries,
            summary.rotation_suppressed,
            "BLOCKED_EXTERNAL",
        )
    if status != "COMPLETE" or not all(is_complete for _, is_complete in validated):
        raise ValueError("secret rotation completion is invalid")
    if document.get("merge_gate") != "ROTATION_EVIDENCE_COMPLETE_PENDING_SECRET_SCAN":
        raise ValueError("secret rotation completion merge gate is invalid")

    target = (
        document["exposure_scope"],
        document["exposure_blob_oid"],
        document["source_path_digest"],
        document["finding_rule_id"],
        document["finding_line_digest"],
    )
    remaining = tuple(
        item
        for item in summary.findings
        if (item.scope, item.object_id, item.path_digest, item.rule_id, item.line_digest) != target
    )
    return ScanSummary(
        summary.tracked_objects,
        summary.history_blobs,
        remaining,
        summary.errors,
        summary.baseline_suppressed,
        summary.stale_baseline_entries,
        summary.rotation_suppressed + len(summary.findings) - len(remaining),
        "COMPLETE_VERIFIED",
    )


def _write_report(path: Path, summary: ScanSummary) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if summary.ok else "BLOCKED",
        "raw_values_included": False,
        "raw_paths_included": False,
        "tracked_objects": summary.tracked_objects,
        "history_blobs": summary.history_blobs,
        "baseline_suppressed": summary.baseline_suppressed,
        "stale_baseline_entries": summary.stale_baseline_entries,
        "rotation_suppressed": summary.rotation_suppressed,
        "rotation_evidence_status": summary.rotation_evidence_status,
        "findings": [asdict(item) for item in summary.findings],
        "errors": [asdict(item) for item in summary.errors],
    }
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _print_summary(summary: ScanSummary) -> None:
    rotation_blocked = summary.rotation_evidence_status == "BLOCKED_EXTERNAL"
    print(f"A4_REPOSITORY_SECRET_SCAN_OK={1 if summary.ok else 0}")
    print(f"A4_TRACKED_SECRET_SCAN_OK={1 if not any(item.scope == 'tracked' for item in summary.findings + summary.errors) else 0}")
    print(
        "A4_HISTORY_SECRET_SCAN_OK="
        f"{1 if not rotation_blocked and not any(item.scope == 'history' for item in summary.findings + summary.errors) else 0}"
    )
    print(f"METRIC_TRACKED_OBJECTS={summary.tracked_objects}")
    print(f"METRIC_HISTORY_BLOBS={summary.history_blobs}")
    print(f"METRIC_SECRET_FINDINGS={len(summary.findings)}")
    print(f"METRIC_SCAN_ERRORS={len(summary.errors)}")
    print(f"METRIC_BASELINE_SUPPRESSED={summary.baseline_suppressed}")
    print(f"METRIC_STALE_BASELINE_ENTRIES={summary.stale_baseline_entries}")
    print(f"METRIC_ROTATION_SUPPRESSED={summary.rotation_suppressed}")
    print(f"ROTATION_EVIDENCE_STATUS={summary.rotation_evidence_status}")
    for item in summary.findings:
        print(
            "ERROR_CODE=SECRET_CANDIDATE "
            f"scope={item.scope} rule={item.rule_id} object={item.object_id} "
            f"path_digest={item.path_digest} line={item.line_number}"
        )
    for item in summary.errors:
        print(
            f"ERROR_CODE={item.error_code} scope={item.scope} object={item.object_id} "
            f"path_digest={item.path_digest}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--rotation-status", type=Path)
    parser.add_argument("--max-blob-bytes", type=int, default=DEFAULT_MAX_BLOB_BYTES)
    args = parser.parse_args(argv)
    if args.max_blob_bytes <= 0:
        parser.error("--max-blob-bytes must be positive")
    try:
        summary = scan_repository(args.repo, max_blob_bytes=args.max_blob_bytes)
        if args.baseline:
            summary = apply_baseline(summary, args.baseline)
        if args.rotation_status:
            summary = apply_rotation_evidence(summary, args.rotation_status)
    except Exception:
        print("A4_REPOSITORY_SECRET_SCAN_OK=0")
        print("ERROR_CODE=SECRET_SCAN_INTERNAL_FAILURE")
        return 2
    if args.report:
        _write_report(args.report, summary)
    _print_summary(summary)
    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
