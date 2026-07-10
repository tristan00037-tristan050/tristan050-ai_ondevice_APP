from __future__ import annotations

import json
from dataclasses import dataclass

from butler_pc_core.cards.box3.actual_fail_class import PARTIAL_HELPER_SDK_UNAVAILABLE
from butler_pc_core.cards.box3.helper_sdk_bridge import (
    DigestOnlyReceipt,
    StyledDraft,
    _extract_helper8_styled_text,
)

ORIG = "제목: 원본 요약\n핵심내용: 원본 값입니다. (근거1)"


@dataclass
class _ExternalStyled:
    # 외부 SDK 객체 계약: draft_text
    draft_text: str


@dataclass
class _InternalStyled:
    # bridge 내부 계약: draft_text_runtime
    draft_text_runtime: str


# 1. 외부 dataclass draft_text → 추출
def test_external_dataclass_draft_text_extracted():
    styled = _ExternalStyled("제목: 스타일 요약\n핵심내용: 스타일 값입니다.")
    value, fail_class = _extract_helper8_styled_text(styled, original_draft=ORIG)
    assert value == "제목: 스타일 요약\n핵심내용: 스타일 값입니다."
    assert fail_class is None
    assert "StyledDraft(" not in value
    assert value.count("\n") == 1  # multiline 보존


# 2. 내부형 객체 draft_text_runtime → 추출
def test_internal_object_draft_text_runtime_extracted():
    styled = _InternalStyled("첫째 줄입니다.\n둘째 줄입니다.")
    value, fail_class = _extract_helper8_styled_text(styled, original_draft=ORIG)
    assert value == "첫째 줄입니다.\n둘째 줄입니다."
    assert fail_class is None


# 3. dict {"draft_text": ...} → 추출
def test_dict_draft_text_extracted():
    value, fail_class = _extract_helper8_styled_text({"draft_text": "딕셔너리\n값입니다."}, original_draft=ORIG)
    assert value == "딕셔너리\n값입니다."
    assert fail_class is None


# 4. 문자열 직접반환 → 그대로
def test_plain_string_passthrough():
    value, fail_class = _extract_helper8_styled_text("문자열 그대로\n두번째 줄", original_draft=ORIG)
    assert value == "문자열 그대로\n두번째 줄"
    assert fail_class is None


# 5. unknown object → repr 노출 0, 원본 유지, PARTIAL_HELPER_SDK_UNAVAILABLE
def test_unknown_object_fail_closed_without_repr():
    class _Weird:
        def __str__(self) -> str:  # str(styled) 를 절대 호출하지 않음을 증명
            return "StyledDraft(draft_text_runtime='유출되면안됨')"

    value, fail_class = _extract_helper8_styled_text(_Weird(), original_draft=ORIG)
    assert value == ORIG
    assert fail_class == PARTIAL_HELPER_SDK_UNAVAILABLE
    assert "StyledDraft(" not in value
    assert "유출되면안됨" not in value


# 6. 값 자체가 "StyledDraft(...)" 문자열이어도 차단
def test_repr_string_value_is_blocked():
    value, fail_class = _extract_helper8_styled_text(
        "StyledDraft(draft_text_runtime='제목: x')", original_draft=ORIG
    )
    assert value == ORIG
    assert fail_class == PARTIAL_HELPER_SDK_UNAVAILABLE
    assert "StyledDraft(" not in value


# 추가 assert: raw_text_logged is False (영속 payload 는 digest-only, 원문 미로깅)
def test_styled_draft_persistable_is_digest_only_raw_text_not_logged():
    receipt = DigestOnlyReceipt(
        "box3.helper_sdk.receipt.v1_2", "sha256:" + "0" * 64, "helper8_style", {}, "partial", PARTIAL_HELPER_SDK_UNAVAILABLE
    )
    raw = "제목: 기밀 문서\n핵심내용: 원문 기밀 값입니다."
    styled = StyledDraft(raw, False, PARTIAL_HELPER_SDK_UNAVAILABLE, receipt)
    persisted = styled.persistable_dict()
    encoded = json.dumps(persisted, ensure_ascii=False)
    assert "기밀 문서" not in encoded and "원문 기밀 값" not in encoded
    assert persisted["draft_digest"].startswith("sha256:")
    assert "StyledDraft(" not in encoded
