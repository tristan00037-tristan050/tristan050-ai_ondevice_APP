from __future__ import annotations

from dataclasses import dataclass

from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCK_NO_FACTUAL_CLAIMS,
    FAIL_CLASS_SEVERITY,
    PARTIAL_HELPER8_STYLE_OUTPUT_UNSUPPORTED,
    is_blocking_actual_fail_class,
)
from butler_pc_core.cards.box3.helper_sdk_bridge import _extract_helper8_styled_text


# === #1: helper8 StyledDraft repr 오염 방지 (dataclass multiline 보존) ===

@dataclass
class _FakeStyled:
    draft_text_runtime: str


def test_extract_helper8_styled_text_preserves_dataclass_multiline_without_repr():
    multiline = "제목: 요약\n핵심내용: 값입니다. (근거1)\n최종문안: 근거 범위에서 확인합니다."
    styled = _FakeStyled(draft_text_runtime=multiline)
    out = _extract_helper8_styled_text(styled)
    assert out == multiline
    assert "\n" in out and out.count("\n") == 2
    assert "_FakeStyled(" not in out and "draft_text_runtime=" not in out


def test_extract_helper8_styled_text_handles_str_and_dict():
    assert _extract_helper8_styled_text("그대로 문자열\n두번째 줄") == "그대로 문자열\n두번째 줄"
    assert _extract_helper8_styled_text({"draft_text": "딕셔너리 값"}) == "딕셔너리 값"
    assert _extract_helper8_styled_text({"text": "text 키"}) == "text 키"


def test_extract_helper8_styled_text_fails_closed_on_unknown_shape():
    # .draft_text 계열 속성이 없는 객체 -> repr 오염 대신 None (호출부가 fail-closed).
    class _Weird:
        pass

    assert _extract_helper8_styled_text(_Weird()) is None
    assert _extract_helper8_styled_text(12345) is None
    assert _extract_helper8_styled_text({"unrelated": "x"}) is None
    assert _extract_helper8_styled_text("   ") == "   "  # 문자열은 공백이어도 repr 오염 아님


def test_helper8_style_output_unsupported_is_nonblocking():
    # 스타일 실패는 부가기능이라 초안을 차단하지 않는다.
    assert FAIL_CLASS_SEVERITY[PARTIAL_HELPER8_STYLE_OUTPUT_UNSUPPORTED] == "nonblocking"
    assert is_blocking_actual_fail_class(PARTIAL_HELPER8_STYLE_OUTPUT_UNSUPPORTED) is False


# === #2: BLOCK_NO_FACTUAL_CLAIMS 상수화 + severity 등록 ===

def test_block_no_factual_claims_registered_as_block_provisional():
    assert BLOCK_NO_FACTUAL_CLAIMS == "BLOCK_NO_FACTUAL_CLAIMS"
    assert FAIL_CLASS_SEVERITY[BLOCK_NO_FACTUAL_CLAIMS] == "block"
    assert is_blocking_actual_fail_class(BLOCK_NO_FACTUAL_CLAIMS) is True


def test_real_grounding_uses_the_registered_constant_for_zero_factual_claims():
    from butler_pc_core.cards.box3.real_grounding import summarize_grounding

    # 사실 문장 0건이면 BLOCK_NO_FACTUAL_CLAIMS (상수 참조).
    summary = summarize_grounding([])
    assert summary.fail_class == BLOCK_NO_FACTUAL_CLAIMS
