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
PARSE_OK = "NONE"

PRIMARY_KEY = "REPO_CONTRACTS_FAILED_GUARD"
PRIMARY_UNPARSED = "UNPARSED"
PRIMARY_UNPARSED_DUPLICATE = "UNPARSED_DUPLICATE"

# 구조화 키. 값은 0/1 또는 공백 없는 안전 문자열이다.
_KEY_LINE_RE = re.compile(r"\A([A-Z][A-Z0-9_]{2,79})=([01]|[A-Za-z0-9_.:+-]{1,120})\Z")

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
    primary_line_sha256 = ""
    primary_line_bytes = 0
    primary_invalid = False
    unparsed_entries: list[dict] = []
    unparsed_total_bytes = 0

    for ordinal, line in enumerate(text.splitlines()):
        if not line.strip():
            continue

        # ① primary summary — 구조화 키보다 먼저 본다. 값에 공백이 올 수 있다.
        if line.startswith(f"{PRIMARY_KEY}="):
            value = line[len(PRIMARY_KEY) + 1:]
            raw_line = line.encode("utf-8")
            primary_line_sha256 = hashlib.sha256(raw_line).hexdigest()
            primary_line_bytes = len(raw_line)
            if _valid_primary_value(value):
                primary_values.append(value)
            else:
                primary_invalid = True
            continue

        # ② KEY=VALUE 구조화 키 — 값 그대로, 순서 그대로, 중복 그대로 보존한다.
        match = _KEY_LINE_RE.match(line)
        if match is not None:
            keys.append((match.group(1), match.group(2)))
            continue

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

    if primary_invalid and not primary_values:
        primary = PRIMARY_UNPARSED
    elif len(primary_values) > 1 or (primary_invalid and primary_values):
        # 같은 summary 가 두 번 나오거나(동일 포함) 서로 다르면 닫는다(§5-2)
        primary = PRIMARY_UNPARSED_DUPLICATE
    elif primary_values:
        primary = primary_values[0]
    else:
        # summary 줄 자체가 없다. "없음" 을 "괜찮음" 으로 읽지 않는다(제1부 §D).
        primary = PRIMARY_UNPARSED

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
        parse_error_code=PARSE_OK,
    )


def resolve_primary(result: ContractParseResult, *, exit_code: int) -> str:
    """보고용 primary 를 exit code 와 함께 정한다.

    §5-1 — 실패한 실행이 `NONE` 을 냈다면 그 `NONE` 은 요약이 아니라
    ★요약 실패★ 다. UNPARSED 로 보고한다. (그 줄의 지문·길이는 그대로 남는다.)

    ★반대 방향은 이 저장소의 실측을 따른다 — canonical success(job 92559345428)
      는 `NONE` 과 함께 `*_OK=0` 을 35 개 낸다. 이 저장소에서 `_OK=0` 은
      "해당 없음/미집행" 이지 실패 판정이 아니다. 그래서 exit 0 의 `NONE` 은
      0-key 가 있어도 유효하다. 이 해석 차이는 회신에 명시한다.
    """
    if exit_code != 0 and result.primary_failed_guard == "NONE":
        return PRIMARY_UNPARSED
    return result.primary_failed_guard


def failing_keys_sha256(failing: tuple[str, ...]) -> str:
    payload = json.dumps(list(failing), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "CONTRACT_OUTPUT_NOT_UTF8",
    "PARSE_OK",
    "PRIMARY_KEY",
    "PRIMARY_UNPARSED",
    "PRIMARY_UNPARSED_DUPLICATE",
    "ContractParseResult",
    "failing_keys_sha256",
    "parse_contract_output",
    "resolve_primary",
]
