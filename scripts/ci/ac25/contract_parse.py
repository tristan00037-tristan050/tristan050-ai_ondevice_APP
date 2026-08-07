"""A-04 — 계약 출력을 ★손실 없이★ 구조화한다.

v3.1 §5 가 이 모듈의 계약이다.

    이전 판의 결함(내가 만든 것)
      `_CONTRACT_KEY_RE` 의 값 문자집합이 공백을 받지 않아, 멈춘 지점을
      이름으로 말해 주는 ★단 하나의 키★(`REPO_CONTRACTS_LAST_GUARD` 류,
      값에 공백 있음)를 버렸다. UNPARSED 398 줄 · 실패 키 79 개가 이름 없이
      묻혔다.

    이 판
      출력 라인을 세 종류로 나눈다 — ① KEY=VALUE 구조화 키
      ② primary summary(공백 허용) ③ 그 밖의 unparsed.
      unparsed 는 원문 대신 (ordinal · sha256 · bytes) 지문 manifest 로 남긴다.

★UTF-8 strict 다. replacement decoding 으로 손상을 정상값처럼 쓰지 않는다.
★raw 원문은 이 모듈 밖으로 나가지 않는다. 지문과 개수만 나간다.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

# ── 오류 코드 ──────────────────────────────────────────────────────────
CONTRACT_OUTPUT_NOT_UTF8 = "CONTRACT_OUTPUT_NOT_UTF8"
CONTRACT_PRIMARY_GUARD_INVALID = "CONTRACT_PRIMARY_GUARD_INVALID"
CONTRACT_DUPLICATE_PRIMARY = "CONTRACT_DUPLICATE_PRIMARY"
CONTRACT_DUPLICATE_KEY = "CONTRACT_DUPLICATE_KEY"
CONTRACT_MALFORMED_GUARD_KEY = "CONTRACT_MALFORMED_GUARD_KEY"
PARSE_OK = "NONE"

PRIMARY_KEY = "REPO_CONTRACTS_FAILED_GUARD"
PRIMARY_UNPARSED = "UNPARSED"
PRIMARY_UNPARSED_DUPLICATE = "UNPARSED_DUPLICATE"

# 구조화 키. 값은 0/1 또는 공백 없는 안전 문자열이다.
_KEY_LINE_RE = re.compile(r"\A([A-Z][A-Z0-9_]{2,79})=([01]|[A-Za-z0-9_.:+-]{1,120})\Z")
_GUARD_KEY_RE = re.compile(r"\A[A-Z][A-Z0-9_]{0,76}_OK\Z")

# 계약 자신의 진단 줄. canonical job 에서는 이 줄이 공개 로그에 그대로 나온다 —
# 같은 공개 수준의 meta-only 텍스트만 통과시킨다(경로·고정 문구, raw 내용 없음).
_BLOCK_LINE_RE = re.compile(r"\ABLOCK: [A-Za-z0-9 ._:/()<>=-]{1,180}\Z")
_BLOCK_LINE_LIMIT = 8

# ★§5-2 — primary 값 규칙. 앞뒤 공백을 제거하지 않는다.
#   UTF-8 · 1~160 bytes · 개행·NUL·제어문자 없음 ·
#   허용 문자 = 영문·숫자·공백·점·밑줄·콜론·슬래시·괄호·하이픈
_PRIMARY_VALUE_RE = re.compile(r"\A[A-Za-z0-9 ._:/()\-]+\Z")
_PRIMARY_MAX_BYTES = 160

_OK_SUFFIX = "_OK"


@dataclass(frozen=True)
class ContractParseResult:
    keys: tuple[tuple[str, str], ...]
    primary_failed_guard: str
    failing_guard_keys: tuple[str, ...]
    block_lines: tuple[str, ...]
    unparsed_line_count: int
    unparsed_total_bytes: int
    unparsed_manifest_sha256: str
    primary_line_sha256: str
    primary_line_bytes: int
    parse_error_code: str


def _canonical_manifest_sha256(entries: list[dict]) -> str:
    payload = json.dumps(
        entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _valid_primary_value(value: str) -> bool:
    if not value:
        return False
    encoded = value.encode("utf-8")
    if len(encoded) > _PRIMARY_MAX_BYTES:
        return False
    return _PRIMARY_VALUE_RE.match(value) is not None


def parse_contract_output(stdout: bytes) -> ContractParseResult:
    """계약 stdout 을 §5-2 규칙 그대로 읽는다. 판정하지 않는다 — 구조만 낸다."""
    closed = ContractParseResult(
        keys=(), primary_failed_guard=PRIMARY_UNPARSED, failing_guard_keys=(),
        block_lines=(),
        unparsed_line_count=0, unparsed_total_bytes=0,
        unparsed_manifest_sha256=_canonical_manifest_sha256([]),
        primary_line_sha256="", primary_line_bytes=0,
        parse_error_code=CONTRACT_OUTPUT_NOT_UTF8,
    )
    try:
        text = stdout.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return closed

    keys: list[tuple[str, str]] = []
    block_lines: list[str] = []
    primary_values: list[str] = []
    primary_lines: list[bytes] = []
    primary_invalid = False
    duplicate_key = False
    malformed_guard_key = False
    seen_keys: set[str] = set()
    unparsed_entries: list[dict] = []
    unparsed_total_bytes = 0

    for ordinal, line in enumerate(text.splitlines()):
        if not line.strip():
            continue

        # ① primary summary — 구조화 키보다 먼저 본다. 값에 공백이 올 수 있다.
        if line.startswith(f"{PRIMARY_KEY}="):
            value = line[len(PRIMARY_KEY) + 1:]
            raw_line = line.encode("utf-8")
            primary_lines.append(raw_line)
            if _valid_primary_value(value):
                primary_values.append(value)
            else:
                primary_invalid = True
            continue

        # ② KEY=VALUE 구조화 키 — 값 그대로, 순서 그대로, 중복 그대로 보존한다.
        match = _KEY_LINE_RE.match(line)
        if match is not None:
            key, value = match.group(1), match.group(2)
            if key in seen_keys:
                duplicate_key = True
            seen_keys.add(key)
            if key.endswith(_OK_SUFFIX) and _GUARD_KEY_RE.fullmatch(key) is None:
                malformed_guard_key = True
            keys.append((key, value))
            continue

        # `_OK` 판정처럼 보이는 malformed line을 일반 unparsed로 숨기지 않는다.
        key_part, separator, _value_part = line.partition("=")
        if separator and key_part.endswith(_OK_SUFFIX):
            malformed_guard_key = True

        # ②′ 계약 자신의 BLOCK 진단 — canonical 공개 로그와 같은 수준의
        #    meta-only 문구만. 한도를 넘거나 검증 실패면 unparsed 로 남는다.
        if line.startswith("BLOCK: ") and _BLOCK_LINE_RE.match(line) and (
            len(block_lines) < _BLOCK_LINE_LIMIT
        ):
            block_lines.append(line)
            continue

        # ③ unparsed — 원문은 담지 않는다. 지문만 남긴다.
        raw_line = line.encode("utf-8")
        unparsed_entries.append({
            "ordinal": ordinal,
            "sha256": hashlib.sha256(raw_line).hexdigest(),
            "bytes": len(raw_line),
        })
        unparsed_total_bytes += len(raw_line)

    # §5-2 — 값이 정확히 "0" 이고 `_OK` 로 끝나는 모든 키의 정렬·중복 제거 집합
    failing = tuple(sorted({
        key for key, value in keys if key.endswith(_OK_SUFFIX) and value == "0"
    }))

    parse_error = PARSE_OK
    if len(primary_lines) > 1:
        primary = PRIMARY_UNPARSED_DUPLICATE
        parse_error = CONTRACT_DUPLICATE_PRIMARY
    elif primary_invalid:
        primary = PRIMARY_UNPARSED
        parse_error = CONTRACT_PRIMARY_GUARD_INVALID
    elif primary_values:
        primary = primary_values[0]
    else:
        # summary 줄 자체가 없다. "없음" 을 "괜찮음" 으로 읽지 않는다(제1부 §D).
        primary = PRIMARY_UNPARSED

    if duplicate_key and parse_error == PARSE_OK:
        parse_error = CONTRACT_DUPLICATE_KEY
    if malformed_guard_key and parse_error == PARSE_OK:
        parse_error = CONTRACT_MALFORMED_GUARD_KEY

    if len(primary_lines) == 1:
        primary_line_sha256 = hashlib.sha256(primary_lines[0]).hexdigest()
        primary_line_bytes = len(primary_lines[0])
    elif primary_lines:
        primary_manifest = [
            {
                "ordinal": ordinal,
                "sha256": hashlib.sha256(raw_line).hexdigest(),
                "bytes": len(raw_line),
            }
            for ordinal, raw_line in enumerate(primary_lines)
        ]
        primary_line_sha256 = _canonical_manifest_sha256(primary_manifest)
        primary_line_bytes = sum(len(raw_line) for raw_line in primary_lines)
    else:
        primary_line_sha256 = ""
        primary_line_bytes = 0

    return ContractParseResult(
        keys=tuple(keys),
        primary_failed_guard=primary,
        failing_guard_keys=failing,
        block_lines=tuple(block_lines),
        unparsed_line_count=len(unparsed_entries),
        unparsed_total_bytes=unparsed_total_bytes,
        unparsed_manifest_sha256=_canonical_manifest_sha256(unparsed_entries),
        primary_line_sha256=primary_line_sha256,
        primary_line_bytes=primary_line_bytes,
        parse_error_code=parse_error,
    )


def resolve_primary(result: ContractParseResult, *, exit_code: int) -> str:
    """Compatibility API: preserve the observed primary; state evaluation is separate."""
    del exit_code
    return result.primary_failed_guard


def failing_keys_sha256(failing: tuple[str, ...]) -> str:
    payload = json.dumps(list(failing), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "CONTRACT_OUTPUT_NOT_UTF8",
    "CONTRACT_PRIMARY_GUARD_INVALID",
    "CONTRACT_DUPLICATE_PRIMARY",
    "CONTRACT_DUPLICATE_KEY",
    "CONTRACT_MALFORMED_GUARD_KEY",
    "PARSE_OK",
    "PRIMARY_KEY",
    "PRIMARY_UNPARSED",
    "PRIMARY_UNPARSED_DUPLICATE",
    "ContractParseResult",
    "failing_keys_sha256",
    "parse_contract_output",
    "resolve_primary",
]
