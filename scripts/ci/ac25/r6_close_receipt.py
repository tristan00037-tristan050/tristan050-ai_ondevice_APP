"""A-03 — 단일 SSOT 결과 receipt. v3.1 §6 판.

"하나의 출처" 는 모든 숫자를 한 job 에서 억지로 만드는 뜻이 아니다(§6-2).
여러 권위 있는 측정값을 ★한 receipt 가 수집★ 하고, 각 필드가 자기 출처
(provenance)를 보존한다는 뜻이다. Python 시험 수 · Node 시험 수 · GitHub
required check 수는 원래 출처가 다르므로 서로의 수치로 덮어쓰지 않는다.

★strict 다(§6-3) — 모르는 키 거부 · 중복 키 거부 · head/attempt 혼합 거부 ·
  만료 뒤 발행 거부. JSON 은 UTF-8 · LF · 정렬 키 · 끝 newline 한 개로
  canonicalize 하고, 그 bytes 의 SHA-256 이 receipt 의 신원이다.
★검증 규칙의 정본은 `contracts/r6_close_receipt.v1.schema.json` 이다.
  이 모듈은 그 규칙을 표준 라이브러리만으로 강제한다(§7 — jsonschema 를
  production 에 끌어오지 않는다). 시험이 두 정의의 일치를 결속한다.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = "r6_close_receipt.v1"
SCHEMA_PATH = Path(__file__).resolve().parent / "contracts" / "r6_close_receipt.v1.schema.json"

# ── 오류 코드 ──────────────────────────────────────────────────────────
RECEIPT_NOT_OBJECT = "RECEIPT_NOT_OBJECT"
RECEIPT_DUPLICATE_KEY = "RECEIPT_DUPLICATE_KEY"
RECEIPT_UNKNOWN_FIELD = "RECEIPT_UNKNOWN_FIELD"
RECEIPT_MISSING_FIELD = "RECEIPT_MISSING_FIELD"
RECEIPT_FIELD_INVALID = "RECEIPT_FIELD_INVALID"
RECEIPT_HEAD_MIXED = "RECEIPT_HEAD_MIXED"
RECEIPT_ATTEMPT_MIXED = "RECEIPT_ATTEMPT_MIXED"
RECEIPT_URL_OUT_OF_SCOPE = "RECEIPT_URL_OUT_OF_SCOPE"
RECEIPT_EXPIRED_AT_ISSUE = "RECEIPT_EXPIRED_AT_ISSUE"
RECEIPT_PROVENANCE_INVALID = "RECEIPT_PROVENANCE_INVALID"

_OID_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_SHA256_OR_NONE_RE = re.compile(r"\A([0-9a-f]{64}|NONE)\Z")
_UTC_RE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_REPO_RE = re.compile(r"\A[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_CODE_RE = re.compile(r"\A[A-Z0-9_]{1,80}\Z")
_PRIMARY_RE = re.compile(r"\A[A-Za-z0-9 ._:/()\-]{1,160}\Z")
_PHASE_RE = re.compile(r"\A(NONE|P0|P1:[0-9]{1,4}|P2|P3|NOT_EVALUATED)\Z")

_TOP_REQUIRED = (
    "schema_version", "repository", "pr_number", "head_sha", "head_tree",
    "base_sha", "run_id", "run_attempt", "workflow_file_sha256",
    "canonical_workflow_sha256", "command_plan_sha256", "plan_diff",
    "exact_head_contract", "clean_evidence", "guard_evidence",
    "python_tests", "node_tests", "required_checks", "review_threads",
    "changed_path_manifest_sha256", "generated_at", "expires_at",
)
_PLAN_DIFF_KEYS = ("missing", "extra", "reordered", "mutated", "unsupported")
_CONTRACT_KEYS = ("conclusion", "job_id", "exit_code", "error_code", "provenance")
_CLEAN_KEYS = (
    "clean_check_executed", "final_worktree_clean", "dirty_path_count",
    "dirty_path_manifest_sha256", "first_dirty_phase",
    "clean_check_error_code", "provenance",
)
_GUARD_KEYS = (
    "primary_failed_guard", "primary_failed_guard_line_sha256",
    "primary_failed_guard_line_bytes", "failing_guard_key_count",
    "failing_guard_keys_sha256", "unparsed_line_count",
    "unparsed_total_bytes", "unparsed_manifest_sha256",
    "parse_error_code", "provenance",
)
_TEST_KEYS = ("total", "passed", "failed", "skipped", "report_sha256", "provenance")
_CHECK_KEYS = (
    "required_total", "success", "failure", "cancelled", "timed_out",
    "action_required", "neutral", "skipped", "missing", "pending",
    "unintended_skipped", "skip_allowlist", "provenance",
)
_REVIEW_KEYS = ("query_complete", "total", "resolved", "non_outdated_unresolved", "provenance")
_PROVENANCE_REQUIRED = ("source_type", "observed_at")
_PROVENANCE_ALLOWED = _PROVENANCE_REQUIRED + (
    "source_url", "command_argv", "source_run_id", "source_run_attempt",
    "source_job_id", "source_head_sha",
)
_SOURCE_TYPES = ("github_job", "github_api", "local_command")
_CONTRACT_CONCLUSIONS = ("success", "failure", "cancelled", "not_run")
_CLEAN_STATES = ("YES", "NO", "NOT_EVALUATED")


class ReceiptError(Exception):
    """코드와 위반 지점 경로만 담는다. 값 자체는 담지 않는다."""

    def __init__(self, code: str, where: str = "") -> None:
        super().__init__(f"{code}:{where}" if where else code)
        self.code = code
        self.where = where


# ── 파싱 — 중복 키를 예외로 닫는다 ─────────────────────────────────────
def _reject_duplicates(pairs):
    seen = set()
    result = {}
    for key, value in pairs:
        if key in seen:
            raise ReceiptError(RECEIPT_DUPLICATE_KEY, key)
        seen.add(key)
        result[key] = value
    return result


def loads_strict(raw: bytes) -> dict:
    try:
        text = raw.decode("utf-8", "strict")
        document = json.loads(text, object_pairs_hook=_reject_duplicates)
    except ReceiptError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(RECEIPT_FIELD_INVALID, "json") from exc
    if not isinstance(document, dict):
        raise ReceiptError(RECEIPT_NOT_OBJECT)
    return document


# ── 필드 검증 ──────────────────────────────────────────────────────────
def _require_keys(obj: dict, required: tuple, where: str) -> None:
    if not isinstance(obj, dict):
        raise ReceiptError(RECEIPT_FIELD_INVALID, where)
    for key in required:
        if key not in obj:
            raise ReceiptError(RECEIPT_MISSING_FIELD, f"{where}.{key}")
    for key in obj:
        if key not in required and key not in _extra_allowed(where):
            raise ReceiptError(RECEIPT_UNKNOWN_FIELD, f"{where}.{key}")


def _extra_allowed(where: str) -> tuple:
    return _PROVENANCE_ALLOWED if where.endswith("provenance") else ()


def _count(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReceiptError(RECEIPT_FIELD_INVALID, where)
    return value


def _match(value, pattern: re.Pattern, where: str) -> str:
    if not isinstance(value, str) or pattern.match(value) is None:
        raise ReceiptError(RECEIPT_FIELD_INVALID, where)
    return value


def _enum(value, allowed: tuple, where: str):
    if value not in allowed:
        raise ReceiptError(RECEIPT_FIELD_INVALID, where)
    return value


def _validate_provenance(obj, *, receipt: dict, where: str) -> None:
    _require_keys(obj, _PROVENANCE_REQUIRED, where)
    _enum(obj["source_type"], _SOURCE_TYPES, f"{where}.source_type")
    _match(obj["observed_at"], _UTC_RE, f"{where}.observed_at")
    if obj["source_type"] == "local_command":
        argv = obj.get("command_argv")
        if not isinstance(argv, list) or not argv or not all(
            isinstance(item, str) and 1 <= len(item) <= 300 for item in argv
        ):
            raise ReceiptError(RECEIPT_PROVENANCE_INVALID, f"{where}.command_argv")
    else:
        url = obj.get("source_url")
        if not isinstance(url, str):
            raise ReceiptError(RECEIPT_PROVENANCE_INVALID, f"{where}.source_url")
        # ★URL 은 github.com 의 ★이 저장소★ 범위만 허용한다(§6-3)
        prefix = f"https://github.com/{receipt['repository']}"
        if url != prefix and not url.startswith(prefix + "/"):
            raise ReceiptError(RECEIPT_URL_OUT_OF_SCOPE, f"{where}.source_url")
    if "source_run_id" in obj:
        _count(obj["source_run_id"], f"{where}.source_run_id")
    if "source_job_id" in obj:
        _count(obj["source_job_id"], f"{where}.source_job_id")
    if "source_run_attempt" in obj:
        attempt = obj["source_run_attempt"]
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ReceiptError(RECEIPT_FIELD_INVALID, f"{where}.source_run_attempt")
        # ★run attempt 가 다른 job 의 증거를 섞지 않는다(§6-3)
        if obj["source_type"] == "github_job" and attempt != receipt["run_attempt"]:
            raise ReceiptError(RECEIPT_ATTEMPT_MIXED, where)
    if "source_head_sha" in obj:
        head = _match(obj["source_head_sha"], _OID_RE, f"{where}.source_head_sha")
        # ★head_sha 가 다른 증거를 섞지 않는다(§6-3)
        if head != receipt["head_sha"]:
            raise ReceiptError(RECEIPT_HEAD_MIXED, where)
    # ★github_job 증거는 어느 head 의 관측인지 스스로 말해야 한다
    if obj["source_type"] == "github_job" and "source_head_sha" not in obj:
        raise ReceiptError(RECEIPT_PROVENANCE_INVALID, f"{where}.source_head_sha")


def _validate_tests(obj, *, receipt: dict, where: str) -> None:
    _require_keys(obj, _TEST_KEYS, where)
    for key in ("total", "passed", "failed", "skipped"):
        _count(obj[key], f"{where}.{key}")
    _match(obj["report_sha256"], _SHA256_RE, f"{where}.report_sha256")
    _validate_provenance(obj["provenance"], receipt=receipt, where=f"{where}.provenance")


def validate(receipt: dict) -> None:
    """strict schema 전체를 강제한다. 위반은 코드+경로로 닫는다."""
    _require_keys(receipt, _TOP_REQUIRED, "receipt")
    _enum(receipt["schema_version"], (SCHEMA_VERSION,), "receipt.schema_version")
    _match(receipt["repository"], _REPO_RE, "receipt.repository")
    _count(receipt["pr_number"], "receipt.pr_number")
    for key in ("head_sha", "head_tree", "base_sha"):
        _match(receipt[key], _OID_RE, f"receipt.{key}")
    _count(receipt["run_id"], "receipt.run_id")
    attempt = receipt["run_attempt"]
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ReceiptError(RECEIPT_FIELD_INVALID, "receipt.run_attempt")
    for key in ("workflow_file_sha256", "canonical_workflow_sha256",
                "command_plan_sha256", "changed_path_manifest_sha256"):
        _match(receipt[key], _SHA256_RE, f"receipt.{key}")

    diff = receipt["plan_diff"]
    _require_keys(diff, _PLAN_DIFF_KEYS, "plan_diff")
    for key in _PLAN_DIFF_KEYS:
        _count(diff[key], f"plan_diff.{key}")

    contract = receipt["exact_head_contract"]
    _require_keys(contract, _CONTRACT_KEYS, "exact_head_contract")
    _enum(contract["conclusion"], _CONTRACT_CONCLUSIONS, "exact_head_contract.conclusion")
    _count(contract["job_id"], "exact_head_contract.job_id")
    if not isinstance(contract["exit_code"], int) or isinstance(contract["exit_code"], bool):
        raise ReceiptError(RECEIPT_FIELD_INVALID, "exact_head_contract.exit_code")
    _match(contract["error_code"], _CODE_RE, "exact_head_contract.error_code")
    _validate_provenance(
        contract["provenance"], receipt=receipt, where="exact_head_contract.provenance"
    )

    clean = receipt["clean_evidence"]
    _require_keys(clean, _CLEAN_KEYS, "clean_evidence")
    if not isinstance(clean["clean_check_executed"], bool):
        raise ReceiptError(RECEIPT_FIELD_INVALID, "clean_evidence.clean_check_executed")
    _enum(clean["final_worktree_clean"], _CLEAN_STATES, "clean_evidence.final_worktree_clean")
    _count(clean["dirty_path_count"], "clean_evidence.dirty_path_count")
    _match(clean["dirty_path_manifest_sha256"], _SHA256_OR_NONE_RE,
           "clean_evidence.dirty_path_manifest_sha256")
    _match(clean["first_dirty_phase"], _PHASE_RE, "clean_evidence.first_dirty_phase")
    _match(clean["clean_check_error_code"], _CODE_RE, "clean_evidence.clean_check_error_code")
    # ★YES 나 NO 는 실행했다는 뜻이다. 실행 없이 그 값이면 receipt 가 모순이다(§2)
    if clean["final_worktree_clean"] in ("YES", "NO") and not clean["clean_check_executed"]:
        raise ReceiptError(RECEIPT_FIELD_INVALID, "clean_evidence.final_worktree_clean")
    _validate_provenance(clean["provenance"], receipt=receipt, where="clean_evidence.provenance")

    guard = receipt["guard_evidence"]
    _require_keys(guard, _GUARD_KEYS, "guard_evidence")
    _match(guard["primary_failed_guard"], _PRIMARY_RE, "guard_evidence.primary_failed_guard")
    _match(guard["primary_failed_guard_line_sha256"], _SHA256_OR_NONE_RE,
           "guard_evidence.primary_failed_guard_line_sha256")
    for key in ("primary_failed_guard_line_bytes", "failing_guard_key_count",
                "unparsed_line_count", "unparsed_total_bytes"):
        _count(guard[key], f"guard_evidence.{key}")
    _match(guard["failing_guard_keys_sha256"], _SHA256_RE, "guard_evidence.failing_guard_keys_sha256")
    _match(guard["unparsed_manifest_sha256"], _SHA256_RE, "guard_evidence.unparsed_manifest_sha256")
    _match(guard["parse_error_code"], _CODE_RE, "guard_evidence.parse_error_code")
    _validate_provenance(guard["provenance"], receipt=receipt, where="guard_evidence.provenance")

    _validate_tests(receipt["python_tests"], receipt=receipt, where="python_tests")
    _validate_tests(receipt["node_tests"], receipt=receipt, where="node_tests")

    checks = receipt["required_checks"]
    _require_keys(checks, _CHECK_KEYS, "required_checks")
    for key in _CHECK_KEYS:
        if key in ("skip_allowlist", "provenance"):
            continue
        _count(checks[key], f"required_checks.{key}")
    allowlist = checks["skip_allowlist"]
    if not isinstance(allowlist, list) or not all(
        isinstance(item, str) and 1 <= len(item) <= 200 for item in allowlist
    ):
        raise ReceiptError(RECEIPT_FIELD_INVALID, "required_checks.skip_allowlist")
    # ★의도된 skip 은 allowlist 로만 정당화된다(§6-4)
    if checks["skipped"] - checks["unintended_skipped"] > len(allowlist):
        raise ReceiptError(RECEIPT_FIELD_INVALID, "required_checks.skipped")
    _validate_provenance(checks["provenance"], receipt=receipt, where="required_checks.provenance")

    review = receipt["review_threads"]
    _require_keys(review, _REVIEW_KEYS, "review_threads")
    if not isinstance(review["query_complete"], bool):
        raise ReceiptError(RECEIPT_FIELD_INVALID, "review_threads.query_complete")
    for key in ("total", "resolved", "non_outdated_unresolved"):
        _count(review[key], f"review_threads.{key}")
    _validate_provenance(review["provenance"], receipt=receipt, where="review_threads.provenance")

    generated = _match(receipt["generated_at"], _UTC_RE, "receipt.generated_at")
    expires = _match(receipt["expires_at"], _UTC_RE, "receipt.expires_at")
    # ★만료 뒤에는 발행하지 않는다(§6-3). 문자열 비교가 곧 시간 비교다(고정 폭 UTC)
    if generated > expires:
        raise ReceiptError(RECEIPT_EXPIRED_AT_ISSUE)


# ── canonicalize + digest ──────────────────────────────────────────────
def canonical_bytes(receipt: dict) -> bytes:
    """UTF-8 · LF · 정렬 키 · 끝 newline 한 개(§6-3)."""
    validate(receipt)
    text = json.dumps(
        receipt, ensure_ascii=False, separators=(",", ": "), sort_keys=True, indent=2
    )
    return (text.rstrip("\n") + "\n").encode("utf-8")


def receipt_sha256(receipt: dict) -> str:
    return hashlib.sha256(canonical_bytes(receipt)).hexdigest()


def load_and_validate(raw: bytes) -> tuple[dict, str]:
    """bytes → (receipt, canonical digest). 어느 단계든 위반이면 닫는다."""
    receipt = loads_strict(raw)
    return receipt, receipt_sha256(receipt)


def schema_document() -> dict:
    """정본 schema 파일. 시험이 validator 상수와의 일치를 결속한다."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ── §9 CLOSE-1 ~ CLOSE-6 기계 판정 ─────────────────────────────────────
def close_judgement(receipt: dict, *, production_python3_s_pass: bool) -> dict:
    """CLOSE 판정을 receipt 값에서만 계산한다. 사람이 다시 세지 않는다(§6-1).

    CLOSE-3(깨끗한 runner 의 `python3 -S` 재현)은 receipt 밖의 로컬 실행
    증거이므로 호출자가 그 결과를 ★명시적으로★ 넘긴다. 기본값이 없다 —
    안 넘기면 판정이 없다.
    """
    validate(receipt)
    contract = receipt["exact_head_contract"]
    clean = receipt["clean_evidence"]
    diff = receipt["plan_diff"]
    checks = receipt["required_checks"]
    review = receipt["review_threads"]

    close1 = contract["conclusion"] == "success"
    close2 = (
        clean["clean_check_executed"] is True
        and clean["final_worktree_clean"] == "YES"
        and clean["dirty_path_count"] == 0
        and all(diff[key] == 0 for key in _PLAN_DIFF_KEYS)
    )
    close3 = bool(production_python3_s_pass)
    close4 = (
        checks["failure"] == 0
        and checks["cancelled"] == 0
        and checks["timed_out"] == 0
        and checks["action_required"] == 0
        and checks["missing"] == 0
        and checks["pending"] == 0
        and checks["unintended_skipped"] == 0
        and checks["success"] == checks["required_total"]
    )
    close5 = True  # validate() 를 통과한 receipt 만 여기 온다
    close6 = review["query_complete"] is True and review["non_outdated_unresolved"] == 0

    complete = all((close1, close2, close3, close4, close5, close6))
    if complete:
        block_reason = "NONE"
    elif not close1 and contract["conclusion"] == "cancelled":
        block_reason = "EXACT_HEAD_JOB_CANCELLED"
    elif not close1:
        block_reason = contract["error_code"]
    elif not close2:
        block_reason = "CLEAN_OR_PLAN_NOT_EXACT"
    elif not close3:
        block_reason = "PRODUCTION_PYTHON3_S_FAILED"
    elif not close4:
        block_reason = "REQUIRED_CHECKS_NOT_ALL_SUCCESS"
    else:
        block_reason = "REVIEW_THREADS_UNRESOLVED"
    return {
        "close1": close1, "close2": close2, "close3": close3,
        "close4": close4, "close5": close5, "close6": close6,
        "complete": complete, "block_reason": block_reason,
    }


def render_summary(receipt: dict) -> str:
    """receipt 에서 사람이 읽을 요약을 ★결정적으로★ 생성한다(§6-1·§6-5).

    같은 receipt 는 언제나 byte 동일한 요약을 낳는다. 수치를 손으로 다시
    입력하는 API 는 없다 — 입력은 receipt 하나다.
    """
    validate(receipt)
    checks = receipt["required_checks"]
    lines = [
        "# AC-25 R6 close receipt summary",
        "",
        f"    repository   : {receipt['repository']}",
        f"    pr           : #{receipt['pr_number']}",
        f"    head         : {receipt['head_sha']}",
        f"    tree         : {receipt['head_tree']}",
        f"    run          : {receipt['run_id']} attempt {receipt['run_attempt']}",
        "",
        f"    exact_head_contract : {receipt['exact_head_contract']['conclusion']}"
        f" (exit {receipt['exact_head_contract']['exit_code']},"
        f" {receipt['exact_head_contract']['error_code']})",
        f"    final_worktree_clean: {receipt['clean_evidence']['final_worktree_clean']}"
        f" (executed={'YES' if receipt['clean_evidence']['clean_check_executed'] else 'NO'},"
        f" dirty={receipt['clean_evidence']['dirty_path_count']})",
        f"    plan_diff           : missing={receipt['plan_diff']['missing']}"
        f" extra={receipt['plan_diff']['extra']}"
        f" reordered={receipt['plan_diff']['reordered']}"
        f" mutated={receipt['plan_diff']['mutated']}"
        f" unsupported={receipt['plan_diff']['unsupported']}",
        f"    primary_failed_guard: {receipt['guard_evidence']['primary_failed_guard']}",
        f"    python_tests        : {receipt['python_tests']['passed']}"
        f"/{receipt['python_tests']['total']} passed,"
        f" skipped {receipt['python_tests']['skipped']}",
        f"    node_tests          : {receipt['node_tests']['passed']}"
        f"/{receipt['node_tests']['total']} passed,"
        f" skipped {receipt['node_tests']['skipped']}",
        f"    required_checks     : {checks['success']}/{checks['required_total']} success,"
        f" failure {checks['failure']}, cancelled {checks['cancelled']},"
        f" unintended_skipped {checks['unintended_skipped']}",
        f"    review_threads      : {receipt['review_threads']['non_outdated_unresolved']}"
        f" unresolved of {receipt['review_threads']['total']}",
        "",
        f"    generated_at : {receipt['generated_at']}",
        f"    receipt_sha256 : {receipt_sha256(receipt)}",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "RECEIPT_ATTEMPT_MIXED",
    "RECEIPT_DUPLICATE_KEY",
    "RECEIPT_EXPIRED_AT_ISSUE",
    "RECEIPT_FIELD_INVALID",
    "RECEIPT_HEAD_MIXED",
    "RECEIPT_MISSING_FIELD",
    "RECEIPT_NOT_OBJECT",
    "RECEIPT_PROVENANCE_INVALID",
    "RECEIPT_UNKNOWN_FIELD",
    "RECEIPT_URL_OUT_OF_SCOPE",
    "SCHEMA_PATH",
    "SCHEMA_VERSION",
    "ReceiptError",
    "canonical_bytes",
    "close_judgement",
    "load_and_validate",
    "loads_strict",
    "receipt_sha256",
    "render_summary",
    "schema_document",
    "validate",
]
