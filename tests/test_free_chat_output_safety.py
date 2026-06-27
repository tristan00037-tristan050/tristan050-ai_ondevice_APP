from __future__ import annotations

import pytest

from butler_pc_core.output_safety.guarded_stream import guard_buffered_tokens, strip_think_blocks
from butler_pc_core.output_safety.guards import (
    CONFIRM_REQUIRED_TEXT,
    SAFE_FIXED_TEXT,
    GuardAction,
    GuardContext,
    SafeChatGuard,
)
from butler_pc_core.sidecar.safe_general_chat import build_safe_general_chat_prompt


def test_safe_general_chat_prompt_is_strong():
    prompt = build_safe_general_chat_prompt("너를 소개해줘")

    assert "반드시 한국어로만 답합니다" in prompt
    assert "어떤 수치도 지어내지 않습니다" in prompt
    assert "회사 데이터를 외부로 보낼 수 있다는 취지의 표현을 절대 하지 않습니다" in prompt
    assert "일반 대화에서 회사DB/회계자료/검색/메모리/내부문서에 접근하지 않습니다" in prompt
    assert "자기소개 요청에는 Butler의 역할과 안전 원칙만 2~3문장으로 답합니다" in prompt
    assert "/no_think" in prompt


def test_strip_think_blocks_global_and_unclosed():
    assert strip_think_blocks("앞<think>숨김</think>뒤<think>또 숨김</think>끝") == "앞뒤끝"
    assert strip_think_blocks("정상 답변<think>닫히지 않은 추론") == "정상 답변"


def test_empty_after_think_strip_replaced():
    text, verdict = guard_buffered_tokens(["<think>", "내부 추론만 있음"])

    assert text == SAFE_FIXED_TEXT
    assert verdict.action == GuardAction.REPLACE
    assert verdict.code == "EMPTY_AFTER_THINK_STRIP"


@pytest.mark.parametrize(
    "text",
    [
        "Butler는 회사 데이터를 기기 밖으로 보낼 수 있는 제품입니다.",
        "회사 데이터를 외부에 업로드할 수 있습니다.",
        "데이터를 외부로 안전하게 전송 가능하도록 설계되었습니다.",
    ],
)
def test_privacy_reversal_variants_blocked(text):
    verdict = SafeChatGuard().evaluate(text, GuardContext(profile="free_general_chat"))

    assert verdict.action == GuardAction.REPLACE
    assert verdict.code == "DEVICE_PRIVACY_INVARIANT_REPLACED"


@pytest.mark.parametrize(
    "text",
    [
        "Butler는 회사 데이터를 기기 밖으로 보낼 수 없습니다.",
        "Butler는 회사 데이터를 외부로 전송할 수 없도록 설계되었습니다.",
    ],
)
def test_negated_privacy_statements_allowed(text):
    verdict = SafeChatGuard().evaluate(text, GuardContext(profile="free_general_chat"))

    assert verdict.action == GuardAction.ALLOW
    assert verdict.code == "OK"


@pytest.mark.parametrize(
    "text",
    [
        "수출액은 300억 달러입니다.",
        "재고량: 7,000개/일",
        "재고량은 7,000개입니다.",
        "생산량은 12,000건입니다.",
        "운영 비용은 5,000달러/월입니다.",
        "생산량 12,000건/년을 처리합니다.",
    ],
)
def test_unsupported_global_numbers_blocked(text):
    verdict = SafeChatGuard().evaluate(text, GuardContext(profile="free_general_chat"))

    assert verdict.action == GuardAction.REPLACE
    assert verdict.code == "UNSUPPORTED_NUMBER_REPLACED"
    assert verdict.allowed_text == CONFIRM_REQUIRED_TEXT
    assert int(verdict.details["unsupported_numbers"]) >= 1


@pytest.mark.parametrize(
    "text",
    [
        "Butler는 安全 模式로 동작합니다.",
        "Butler는 excellent secure private assistant 입니다.",
    ],
)
def test_language_mix_blocked(text):
    verdict = SafeChatGuard().evaluate(text, GuardContext(profile="free_general_chat"))

    assert verdict.action == GuardAction.REPLACE
    assert verdict.code == "LANGUAGE_MIX_BLOCKED"


def test_allowed_terms_not_language_mix():
    verdict = SafeChatGuard().evaluate(
        "Butler AI OS는 Qwen3 LLM 기반의 온디바이스 업무 도우미입니다.",
        GuardContext(profile="free_general_chat"),
    )

    assert verdict.action == GuardAction.ALLOW
    assert verdict.code == "OK"


def test_safe_chat_allows_clean_intro():
    verdict = SafeChatGuard().evaluate(
        "Butler는 회사 데이터를 기기 밖으로 보내지 않고 로컬에서 처리하는 온디바이스 AI 업무 OS입니다. "
        "일반 대화에서는 확인된 범위 안에서 안전하게 안내합니다.",
        GuardContext(profile="free_general_chat"),
    )

    assert verdict.action == GuardAction.ALLOW
    assert verdict.code == "OK"
