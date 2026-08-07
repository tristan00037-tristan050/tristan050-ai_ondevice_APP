"""AC-25 R6 close receipt primitives (v4.2).

Only raw, digest-bound evidence is accepted.  The module deliberately uses the
Python standard library so the protected workflow can import it with ``-S``.
It validates evidence integrity; it does not turn a truthful failure receipt
into an AC-25 pass.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


SCHEMA_VERSION = "butler.ac25.r6_close_receipt.v2"
SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")
DECIMAL_RE = re.compile(r"\A(?:0|[1-9][0-9]*)\Z")
UTC_RE = re.compile(
    r"\A[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z"
)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
JUNIT_FILE_MAX_BYTES = 16 * 1024 * 1024
JUNIT_TOTAL_MAX_BYTES = 64 * 1024 * 1024
TAP_FILE_MAX_BYTES = 16 * 1024 * 1024

ROOT_FILES = frozenset(
    {
        "receipt.json", "receipt.schema.json", "changed_paths.json",
        "contract_evidence.json", "contract/contract.stdout",
        "clean_check.json", "clean-status.porcelain-v2.z",
        "required_checks.json", "observed_checks.json", "provenance.json",
        "DIGESTS.sha256",
        "junit/manifest.json", "tap/manifest.json",
    }
)


class StrictReceiptError(Exception):
    """Stable error code only; evidence bytes and paths never enter output."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _pairs_no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise StrictReceiptError("JSON_DUPLICATE_KEY")
        out[key] = value
    return out


def loads_strict(raw: bytes):
    try:
        text = raw.decode("utf-8", "strict")
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                StrictReceiptError("JSON_NON_FINITE")
            ),
        )
    except StrictReceiptError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrictReceiptError("JSON_INVALID") from exc


def canonical_json_bytes(document) -> bytes:
    try:
        return (
            json.dumps(
                document, ensure_ascii=False, allow_nan=False, sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StrictReceiptError("JSON_INVALID") from exc


def load_canonical_json(path: Path):
    raw = path.read_bytes()
    document = loads_strict(raw)
    if canonical_json_bytes(document) != raw:
        raise StrictReceiptError("JSON_NOT_CANONICAL")
    return document, raw


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_path(path: str) -> str:
    if not isinstance(path, str) or not path or "\\" in path:
        raise StrictReceiptError("PATH_INVALID")
    if path != unicodedata.normalize("NFC", path):
        raise StrictReceiptError("PATH_NOT_NFC")
    if CONTROL_RE.search(path):
        raise StrictReceiptError("PATH_INVALID")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise StrictReceiptError("PATH_TRAVERSAL")
    if str(pure) != path:
        raise StrictReceiptError("PATH_INVALID")
    return path


def validate_unique_paths(paths: Iterable[str]) -> tuple[str, ...]:
    out = []
    raw_seen = set()
    normalized_seen = set()
    for item in paths:
        validate_path(item)
        normalized = unicodedata.normalize("NFC", item)
        if item in raw_seen:
            raise StrictReceiptError("PATH_DUPLICATE")
        if normalized in normalized_seen:
            raise StrictReceiptError("PATH_UNICODE_COLLISION")
        raw_seen.add(item)
        normalized_seen.add(normalized)
        out.append(item)
    return tuple(out)


def _all_files(root: Path) -> tuple[str, ...]:
    if not root.is_dir():
        raise StrictReceiptError("RECEIPT_ROOT_NOT_FOUND")
    paths = []
    for candidate in root.rglob("*"):
        if candidate.is_symlink() or not candidate.is_file():
            if candidate.is_symlink():
                raise StrictReceiptError("SYMLINK_NOT_ALLOWED")
            continue
        paths.append(candidate.relative_to(root).as_posix())
    validate_unique_paths(paths)
    return tuple(sorted(paths, key=lambda value: value.encode("utf-8")))


def build_digest_manifest(root: Path) -> bytes:
    files = [path for path in _all_files(root) if path != "DIGESTS.sha256"]
    return "".join(
        f"{sha256_bytes((root / path).read_bytes())}  {path}\n" for path in files
    ).encode("utf-8")


def verify_digest_manifest(root: Path) -> None:
    manifest_path = root / "DIGESTS.sha256"
    try:
        raw = manifest_path.read_bytes()
        text = raw.decode("utf-8", "strict")
    except (FileNotFoundError, UnicodeDecodeError) as exc:
        raise StrictReceiptError("DIGEST_MANIFEST_INVALID") from exc
    if not text or not text.endswith("\n") or "\r" in text:
        raise StrictReceiptError("DIGEST_MANIFEST_INVALID")
    declared = []
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise StrictReceiptError("DIGEST_MANIFEST_INVALID")
        path = validate_path(match.group(2))
        if path == "DIGESTS.sha256":
            raise StrictReceiptError("DIGEST_MANIFEST_SELF_REFERENCE")
        declared.append((path, match.group(1)))
    validate_unique_paths(path for path, _digest in declared)
    expected_paths = tuple(
        path for path in _all_files(root) if path != "DIGESTS.sha256"
    )
    actual_paths = tuple(path for path, _digest in declared)
    if actual_paths != expected_paths:
        raise StrictReceiptError("DIGEST_MANIFEST_INCOMPLETE")
    for path, expected in declared:
        if sha256_bytes((root / path).read_bytes()) != expected:
            raise StrictReceiptError("DIGEST_MISMATCH")


def _exact_object(document, required: Sequence[str], *, optional: Sequence[str] = ()):
    if not isinstance(document, dict):
        raise StrictReceiptError("JSON_OBJECT_REQUIRED")
    allowed = set(required) | set(optional)
    if set(document) - allowed:
        raise StrictReceiptError("JSON_UNKNOWN_FIELD")
    if set(required) - set(document):
        raise StrictReceiptError("JSON_MISSING_FIELD")


def _nonnegative_int(value, code="COUNT_INVALID") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StrictReceiptError(code)
    return value


def validate_changed_paths(document, *, expected_base: str, expected_head: str):
    _exact_object(document, ("base", "head", "paths"))
    if document["base"] != expected_base or document["head"] != expected_head:
        raise StrictReceiptError("CHANGED_PATH_COORDINATE_MISMATCH")
    if not isinstance(document["paths"], list):
        raise StrictReceiptError("CHANGED_PATHS_INVALID")
    paths = validate_unique_paths(document["paths"])
    if list(paths) != sorted(paths, key=lambda value: value.encode("utf-8")):
        raise StrictReceiptError("CHANGED_PATHS_NOT_SORTED")
    return paths


@dataclass(frozen=True)
class TestCounts:
    tests: int
    passed: int
    failures: int
    errors: int
    skipped: int

    def as_dict(self):
        return {
            "errors": self.errors, "failures": self.failures,
            "passed": self.passed, "skipped": self.skipped,
            "tests": self.tests,
        }


def parse_junit(raw: bytes) -> TestCounts:
    if len(raw) > JUNIT_FILE_MAX_BYTES:
        raise StrictReceiptError("JUNIT_SIZE_LIMIT")
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise StrictReceiptError("JUNIT_DTD_FORBIDDEN")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise StrictReceiptError("JUNIT_XML_INVALID") from exc
    cases = list(root.iter("testcase"))
    failures = errors = skipped = 0
    for case in cases:
        failures += int(any(child.tag == "failure" for child in case))
        errors += int(any(child.tag == "error" for child in case))
        skipped += int(any(child.tag == "skipped" for child in case))
    tests = len(cases)
    passed = tests - failures - errors - skipped
    if passed < 0:
        raise StrictReceiptError("JUNIT_CASE_STATE_INVALID")
    counts = TestCounts(tests, passed, failures, errors, skipped)
    suites = [root] if root.tag == "testsuite" else list(root.findall("./testsuite"))
    for suite in suites:
        declared = {}
        for key in ("tests", "failures", "errors", "skipped"):
            value = suite.get(key)
            if value is None or not re.fullmatch(r"0|[1-9][0-9]*", value):
                raise StrictReceiptError("JUNIT_DECLARED_COUNT_INVALID")
            declared[key] = int(value)
        direct_cases = list(suite.iter("testcase"))
        sf = sum(any(c.tag == "failure" for c in case) for case in direct_cases)
        se = sum(any(c.tag == "error" for c in case) for case in direct_cases)
        ss = sum(any(c.tag == "skipped" for c in case) for case in direct_cases)
        if declared != {
            "tests": len(direct_cases), "failures": sf, "errors": se, "skipped": ss,
        }:
            raise StrictReceiptError("JUNIT_COUNT_MISMATCH")
    return counts


@dataclass(frozen=True)
class TapCounts:
    tests: int
    ok: int
    not_ok: int
    skipped: int
    todo: int

    def as_dict(self):
        return {
            "not_ok": self.not_ok, "ok": self.ok, "skipped": self.skipped,
            "tests": self.tests, "todo": self.todo,
        }


_TAP_RESULT_RE = re.compile(
    r"^(not ok|ok)\s+([0-9]+)(.*)$",
    re.IGNORECASE,
)
_TAP_DIRECTIVE_RE = re.compile(r"\s+#\s*([A-Za-z]+)(?:\s+.*)?$", re.IGNORECASE)


def parse_tap(raw: bytes) -> TapCounts:
    if len(raw) > TAP_FILE_MAX_BYTES:
        raise StrictReceiptError("TAP_SIZE_LIMIT")
    try:
        lines = raw.decode("utf-8", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise StrictReceiptError("TAP_NOT_UTF8") from exc
    if any(line.lstrip().lower().startswith("bail out!") for line in lines):
        raise StrictReceiptError("TAP_BAILOUT")
    plans = []
    results = []
    in_yaml_diagnostics = False
    for source_line in lines:
        # TAP 13 permits an indented YAMLish diagnostics block immediately
        # after a test point.  It is evidence metadata, never another point.
        if source_line.startswith("  ---"):
            if in_yaml_diagnostics:
                raise StrictReceiptError("TAP_MALFORMED")
            in_yaml_diagnostics = True
            continue
        if in_yaml_diagnostics:
            if source_line.startswith("  ..."):
                in_yaml_diagnostics = False
            continue
        stripped = source_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("TAP version"):
            continue
        plan = re.fullmatch(r"1\.\.([0-9]+)(?:\s+#.*)?", stripped, re.IGNORECASE)
        if plan:
            plans.append(int(plan.group(1)))
            continue
        match = _TAP_RESULT_RE.fullmatch(stripped)
        if match:
            directive_match = _TAP_DIRECTIVE_RE.search(match.group(3))
            directive = directive_match.group(1).upper() if directive_match else ""
            if directive not in ("", "SKIP", "TODO"):
                raise StrictReceiptError("TAP_DIRECTIVE_INVALID")
            results.append((match.group(1).lower(), int(match.group(2)), directive))
            continue
        raise StrictReceiptError("TAP_MALFORMED")
    if in_yaml_diagnostics:
        raise StrictReceiptError("TAP_MALFORMED")
    if len(plans) != 1:
        raise StrictReceiptError("TAP_PLAN_MISSING" if not plans else "TAP_PLAN_DUPLICATE")
    total = plans[0]
    numbers = [number for _state, number, _directive in results]
    if len(numbers) != len(set(numbers)):
        raise StrictReceiptError("TAP_DUPLICATE_NUMBER")
    if sorted(numbers) != list(range(1, total + 1)):
        raise StrictReceiptError("TAP_PLAN_MISMATCH")
    return TapCounts(
        total,
        sum(state == "ok" for state, _number, _directive in results),
        sum(state == "not ok" for state, _number, _directive in results),
        sum(directive == "SKIP" for _state, _number, directive in results),
        sum(directive == "TODO" for _state, _number, directive in results),
    )


def validate_test_manifest(
    root: Path, kind: str, parser, *, receipt_digest: str
) -> str:
    document, raw = load_canonical_json(root / kind / "manifest.json")
    _exact_object(document, ("files", "summary"))
    if not isinstance(document["files"], list) or not document["files"]:
        raise StrictReceiptError(f"{kind.upper()}_RAW_NOT_FOUND")
    files = []
    total_bytes = 0
    aggregate = None
    for entry in document["files"]:
        _exact_object(entry, ("path", "sha256", "bytes", "counts"))
        path = validate_path(entry["path"])
        if not path.startswith(kind + "/") or path == f"{kind}/manifest.json":
            raise StrictReceiptError("TEST_ARTIFACT_PATH_INVALID")
        artifact = root / path
        if not artifact.is_file():
            raise StrictReceiptError(f"{kind.upper()}_RAW_NOT_FOUND")
        artifact_raw = artifact.read_bytes()
        total_bytes += len(artifact_raw)
        if kind == "junit" and total_bytes > JUNIT_TOTAL_MAX_BYTES:
            raise StrictReceiptError("JUNIT_SIZE_LIMIT")
        if entry["sha256"] != sha256_bytes(artifact_raw) or entry["bytes"] != len(artifact_raw):
            raise StrictReceiptError("TEST_ARTIFACT_DIGEST_MISMATCH")
        counts = parser(artifact_raw).as_dict()
        if entry["counts"] != counts:
            raise StrictReceiptError(f"{kind.upper()}_COUNT_MISMATCH")
        files.append(path)
        if aggregate is None:
            aggregate = {key: 0 for key in counts}
        for key, value in counts.items():
            aggregate[key] += value
    validate_unique_paths(files)
    if document["summary"] != aggregate:
        raise StrictReceiptError(f"{kind.upper()}_COUNT_MISMATCH")
    return sha256_bytes(raw)


def _check_identity(check, *, code: str) -> tuple[str, int]:
    name = check.get("name") if isinstance(check, dict) else None
    app_id = check.get("app_id") if isinstance(check, dict) else None
    if (
        not isinstance(name, str) or not name or CONTROL_RE.search(name)
        or not isinstance(app_id, int) or isinstance(app_id, bool) or app_id <= 0
    ):
        raise StrictReceiptError(code)
    return name, app_id


def validate_required_checks(document) -> tuple[tuple[str, int], ...]:
    _exact_object(
        document,
        (
            "known", "complete", "source", "branch_protection_pages_complete",
            "ruleset_pages_complete", "checks",
        ),
    )
    if document["known"] is not True or document["complete"] is not True:
        raise StrictReceiptError("REQUIRED_CHECKS_INCOMPLETE")
    if document["source"] not in ("branch-protection", "ruleset", "BOTH"):
        raise StrictReceiptError("REQUIRED_CHECKS_INVALID")
    if (
        document["branch_protection_pages_complete"] is not True
        or document["ruleset_pages_complete"] is not True
    ):
        raise StrictReceiptError("REQUIRED_CHECKS_PAGINATION_INCOMPLETE")
    if not isinstance(document["checks"], list):
        raise StrictReceiptError("REQUIRED_CHECKS_INVALID")
    if not document["checks"]:
        raise StrictReceiptError("REQUIRED_CHECK_SET_EMPTY")
    identities = []
    for check in document["checks"]:
        _exact_object(check, ("name", "app_id"))
        identities.append(_check_identity(check, code="REQUIRED_CHECKS_INVALID"))
    if len(identities) != len(set(identities)):
        raise StrictReceiptError("REQUIRED_CHECKS_DUPLICATE")
    if identities != sorted(identities, key=lambda item: (item[0].encode("utf-8"), item[1])):
        raise StrictReceiptError("REQUIRED_CHECKS_NOT_SORTED")
    return tuple(identities)


def validate_observed_checks(document) -> dict[tuple[str, int], dict]:
    _exact_object(document, ("complete", "head_sha", "checks"))
    if not isinstance(document["complete"], bool) or OID_RE.fullmatch(document["head_sha"] or "") is None:
        raise StrictReceiptError("OBSERVED_CHECKS_INVALID")
    if not isinstance(document["checks"], list):
        raise StrictReceiptError("OBSERVED_CHECKS_INVALID")
    if document["complete"] is not True:
        raise StrictReceiptError("OBSERVED_CHECKS_INCOMPLETE")
    identities = {}
    for check in document["checks"]:
        _exact_object(check, ("name", "app_id", "run_id", "attempt", "status", "conclusion"))
        identity = _check_identity(check, code="OBSERVED_CHECKS_INVALID")
        if identity in identities:
            raise StrictReceiptError("OBSERVED_CHECKS_DUPLICATE")
        if (
            not isinstance(check["run_id"], int) or isinstance(check["run_id"], bool)
            or check["run_id"] <= 0
            or not isinstance(check["attempt"], int) or isinstance(check["attempt"], bool)
            or check["attempt"] <= 0
            or not isinstance(check["status"], str)
            or not isinstance(check["conclusion"], str)
        ):
            raise StrictReceiptError("OBSERVED_CHECKS_INVALID")
        identities[identity] = check
    return identities


def require_successful_checks(
    required: Sequence[tuple[str, int]], observed: Mapping[tuple[str, int], dict]
) -> None:
    observed_names = {name for name, _app_id in observed}
    for identity in required:
        if identity not in observed:
            if identity[0] in observed_names:
                raise StrictReceiptError("REQUIRED_CHECK_APP_ID_MISMATCH")
            raise StrictReceiptError("REQUIRED_CHECK_MISSING")
        check = observed[identity]
        if check["status"] != "completed" or check["conclusion"] != "success":
            raise StrictReceiptError("REQUIRED_CHECK_NOT_SUCCESS")
