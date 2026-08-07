"""A-04 — 계약 출력 구조화가 §5 계약 그대로인가.

기준 사실(v3.1 §5-1): 실패 job 92559345313 은 primary summary 를 `NONE` 으로
내면서 동시에 `*_OK=0` 을 79 개 냈다. "실패 guard 가 없었다" 가 아니라
★요약이 파싱되지 않았다★ 가 맞는 보고다.

★이 파일의 픽스처는 오염 guard(`*_OK=1` 금지)를 지키기 위해 값 1 짜리
  guard key 를 이어붙이기로만 만든다.
"""
from __future__ import annotations

import pytest
from ac25 import contract_parse as cpar

pytestmark = pytest.mark.no_sidecar_token

PRIMARY = "REPO_CONTRACTS_FAILED_GUARD"


def line(key: str, value: str) -> bytes:
    return f"{key}={value}\n".encode()


def ok_one(key: str) -> bytes:
    """`<key>_OK` 값 1 — 소스에 금지 패턴이 남지 않게 이어붙여 만든다."""
    return (key + "_OK=" + "1").encode() + b"\n"


# ══ primary — 공백 없는/있는 이름 ═════════════════════════════════════
def test_primary_without_spaces_is_parsed():
    result = cpar.parse_contract_output(line(PRIMARY, "simple_guard_v1"))
    assert result.primary_failed_guard == "simple_guard_v1"
    assert result.parse_error_code == cpar.PARSE_OK


def test_primary_with_spaces_is_parsed_not_dropped():
    """★이것이 이전 판이 버린 형태다 — canonical 의 LAST_GUARD 값과 같은 꼴."""
    name = "mcp zero trust drift contract v1"
    result = cpar.parse_contract_output(line(PRIMARY, name))
    assert result.primary_failed_guard == name
    assert result.primary_line_bytes == len(f"{PRIMARY}={name}".encode())
    assert result.primary_line_sha256 != ""


def test_primary_value_is_not_stripped():
    result = cpar.parse_contract_output(line(PRIMARY, " padded guard "))
    assert result.primary_failed_guard == " padded guard "


# ══ 160-byte 경계 ══════════════════════════════════════════════════════
def test_primary_at_160_bytes_is_accepted():
    name = "g" * 160
    result = cpar.parse_contract_output(line(PRIMARY, name))
    assert result.primary_failed_guard == name


def test_primary_at_161_bytes_is_unparsed():
    result = cpar.parse_contract_output(line(PRIMARY, "g" * 161))
    assert result.primary_failed_guard == cpar.PRIMARY_UNPARSED


# ══ 빈 값·제어문자·NUL·잘못된 UTF-8 ═══════════════════════════════════
@pytest.mark.parametrize(
    "value", ["", "bad\tguard", "bad\x00guard", "bad\x1bguard", "질문"],
    ids=["empty", "tab", "nul", "escape", "non-ascii"],
)
def test_invalid_primary_values_are_unparsed(value):
    result = cpar.parse_contract_output(line(PRIMARY, value))
    assert result.primary_failed_guard == cpar.PRIMARY_UNPARSED


def test_invalid_utf8_closes_everything():
    result = cpar.parse_contract_output(b"\xff\xfe not utf8")
    assert result.parse_error_code == cpar.CONTRACT_OUTPUT_NOT_UTF8
    assert result.keys == ()
    assert result.primary_failed_guard == cpar.PRIMARY_UNPARSED


# ══ primary 누락 + 0-key 존재 → UNPARSED ══════════════════════════════
def test_zero_keys_without_primary_are_unparsed_not_none():
    result = cpar.parse_contract_output(b"SOME_GUARD" + b"_OK=0\n")
    assert result.primary_failed_guard == cpar.PRIMARY_UNPARSED
    assert result.failing_guard_keys == ("SOME_GUARD_OK",)


def test_missing_summary_line_is_never_reported_as_none():
    """줄 자체가 없다 — "없음" 을 "괜찮음" 으로 읽지 않는다(제1부 §D)."""
    result = cpar.parse_contract_output(b"OTHER_KEY=value\n")
    assert result.primary_failed_guard == cpar.PRIMARY_UNPARSED


# ══ primary 중복 — 동일·상충 모두 닫는다 ══════════════════════════════
def test_duplicate_identical_primary_is_closed():
    payload = line(PRIMARY, "guard a") + line(PRIMARY, "guard a")
    result = cpar.parse_contract_output(payload)
    assert result.primary_failed_guard == cpar.PRIMARY_UNPARSED_DUPLICATE


def test_duplicate_conflicting_primary_is_closed():
    payload = line(PRIMARY, "guard a") + line(PRIMARY, "guard b")
    result = cpar.parse_contract_output(payload)
    assert result.primary_failed_guard == cpar.PRIMARY_UNPARSED_DUPLICATE


# ══ 0-key 전수 보존 ════════════════════════════════════════════════════
def test_79_zero_keys_survive_sorted_without_loss():
    keys = [f"GUARD_{i:03d}_SUFFIX_OK" for i in range(79)]
    payload = b"".join(line(k, "0") for k in reversed(keys))
    result = cpar.parse_contract_output(payload)
    assert result.failing_guard_keys == tuple(sorted(keys))
    assert len(result.failing_guard_keys) == 79


def test_duplicate_zero_key_is_deduplicated():
    payload = line("DUP_GUARD_OK", "0") * 3
    result = cpar.parse_contract_output(payload)
    assert result.failing_guard_keys == ("DUP_GUARD_OK",)
    # keys 자체는 손실 없이 순서·중복 그대로 보존된다
    assert len(result.keys) == 3


def test_value_one_is_not_in_the_failing_set():
    payload = ok_one("PASSING_GUARD") + line("FAILING_GUARD_OK", "0")
    result = cpar.parse_contract_output(payload)
    assert result.failing_guard_keys == ("FAILING_GUARD_OK",)


def test_non_ok_zero_values_are_not_failing_keys():
    result = cpar.parse_contract_output(line("SOME_COUNT", "0"))
    assert result.failing_guard_keys == ()


# ══ unparsed manifest — 결정성·무유출 ═════════════════════════════════
def test_unparsed_manifest_is_deterministic():
    payload = b"== guard: alpha ==\nKEY_A=1\n== guard: beta ==\n"
    first = cpar.parse_contract_output(payload)
    second = cpar.parse_contract_output(payload)
    assert first.unparsed_manifest_sha256 == second.unparsed_manifest_sha256
    assert first.unparsed_line_count == 2
    assert first.unparsed_total_bytes == len(b"== guard: alpha ==") + len(
        b"== guard: beta =="
    )


def test_raw_unparsed_content_never_leaves_the_parser():
    secret = "SECRET_RAW_CONTENT_DO_NOT_LEAK"
    result = cpar.parse_contract_output(f"junk {secret} junk\n".encode())
    assert secret not in repr(result)
    assert result.unparsed_line_count == 1


# ══ exit code 와의 결합 (§5-1·§5-4) ═══════════════════════════════════
def test_nonzero_exit_preserves_none_summary_for_state_cross_check():
    """v4.1 keeps raw semantics; contract_state rejects this tuple later."""
    result = cpar.parse_contract_output(line(PRIMARY, "NONE"))
    assert cpar.resolve_primary(result, exit_code=1) == "NONE"


def test_zero_exit_preserves_none_and_zero_key_for_state_cross_check():
    """The parser records the tuple; v4.1 contract_state marks it INVALID."""
    payload = line(PRIMARY, "NONE") + line("NOT_APPLICABLE_GUARD_OK", "0")
    result = cpar.parse_contract_output(payload)
    assert cpar.resolve_primary(result, exit_code=0) == "NONE"


def test_named_guard_passes_through_resolution_unchanged():
    result = cpar.parse_contract_output(line(PRIMARY, "some guard v1"))
    assert cpar.resolve_primary(result, exit_code=1) == "some guard v1"


# ══ 구조화 키 규칙 ═════════════════════════════════════════════════════
def test_keys_preserve_order_and_values():
    payload = line("KEY_B", "x") + line("KEY_A", "y")
    result = cpar.parse_contract_output(payload)
    assert result.keys == (("KEY_B", "x"), ("KEY_A", "y"))


def test_failing_keys_digest_is_deterministic():
    keys = ("A_GUARD_OK", "B_GUARD_OK")
    assert cpar.failing_keys_sha256(keys) == cpar.failing_keys_sha256(keys)
    assert cpar.failing_keys_sha256(keys) != cpar.failing_keys_sha256(keys[:1])


# ══ BLOCK 진단 줄 — canonical 공개 로그와 같은 수준만 통과 ════════════
def test_block_lines_are_captured_meta_only():
    payload = (
        b"BLOCK: long line (>2000) detected in scripts/some/file.txt\n"
        b"BLOCK: sensitive pattern detected in reports/proofs\n"
        b"junk raw line\n"
    )
    result = cpar.parse_contract_output(payload)
    assert result.block_lines == (
        "BLOCK: long line (>2000) detected in scripts/some/file.txt",
        "BLOCK: sensitive pattern detected in reports/proofs",
    )
    assert result.unparsed_line_count == 1


def test_block_lines_with_unsafe_content_stay_unparsed():
    payload = b"BLOCK: bad\tcontrol\nBLOCK: " + b"x" * 300 + b"\n"
    result = cpar.parse_contract_output(payload)
    assert result.block_lines == ()
    assert result.unparsed_line_count == 2


def test_block_lines_are_bounded():
    payload = b"".join(
        f"BLOCK: item number {i} detected\n".encode() for i in range(20)
    )
    result = cpar.parse_contract_output(payload)
    assert len(result.block_lines) == 8
    assert result.unparsed_line_count == 12
