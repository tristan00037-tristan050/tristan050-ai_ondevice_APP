"""intent_normalizer.py — 알고리즘 팀 §6 Intent 후처리 normalizer.

단계 6.5.2 Patch 1: REPORT marker override (9개)
단계 6.5.3 Patch 1: REPORT marker 확장 (9→18) + REQUEST_MARKERS 확장
단계 6.5.3 Patch 2: COMMAND normalizer 신규 (13 COMMAND + 5 SOFT_REQUEST)

적용 시점: LLM JSON 파싱 직후 / Verifier 직전 (llm_extractor._v1_dict_to_extraction).
호출 순서: normalize_report_intent → normalize_command_intent (chain).
"""
from __future__ import annotations

from typing import Tuple


# ─────────────────────────────────────────────────────────────────────────
# Patch 1 — REPORT_MARKERS 확장 (9 → 18)
# ─────────────────────────────────────────────────────────────────────────

REPORT_MARKERS = [
    # 기존 9개 (단계 6.5.2)
    "예정입니다", "예정이에요",
    "할 예정", "진행 예정", "제출할 예정",
    "완료했습니다", "공유했습니다",
    "제출했습니다", "전달했습니다",

    # 6.5.3 신규 9개
    "보고드립니다",
    "말씀드리겠습니다",
    "공유드리겠습니다",
    "안내드리겠습니다",
    "전달드리겠습니다",
    "보고드리겠습니다",
    "설명드리겠습니다",
    "알려드립니다",
    "안내드립니다",

    # 6.5.4 신규 4개
    "보내드리겠습니다",
    "재발송하겠습니다",
    "처리하겠습니다",
    "공유해드립니다",
]

REQUEST_MARKERS = [
    "해주세요", "해 주세요",
    "부탁드립니다", "가능할까요",
    "주실 수 있나요", "요청드립니다",
    "전달해 주세요", "공유해 주세요",
    "확인해 주세요",
]

REPORT_OVERRIDE_REASON  = "REPORT_MARKER_OVERRIDES"
COMMAND_OVERRIDE_REASON = "COMMAND_MARKER_OVERRIDES"

# 단계 6.5.2 호환 alias — 기존 import 유지
OVERRIDE_REASON = REPORT_OVERRIDE_REASON


def normalize_report_intent(source_text: str, llm_intent: str) -> Tuple[str, str]:
    """REPORT marker가 있고 REQUEST marker가 없으면 'report' override."""
    has_report  = any(m in source_text for m in REPORT_MARKERS)
    has_request = any(m in source_text for m in REQUEST_MARKERS)
    if has_report and not has_request:
        return "report", REPORT_OVERRIDE_REASON
    return llm_intent, "OK"


# 6.5.2 호환 alias — 기존 함수명 유지
def post_fix_intent_type(source_text: str, llm_intent: str) -> Tuple[str, str]:
    """6.5.2 호환 — normalize_report_intent의 alias."""
    return normalize_report_intent(source_text, llm_intent)


# ─────────────────────────────────────────────────────────────────────────
# Patch 2 — COMMAND normalizer (신규)
# ─────────────────────────────────────────────────────────────────────────

# 상하관계 명령형 어미 — "~하세요/하십시오/할 것/해라"
COMMAND_MARKERS = [
    "하세요", "하십시오", "해라", "할 것",
    "진행하세요", "작성하세요", "제출하세요",
    "정리하세요", "확인하세요", "검토하세요",
    "반영하세요", "공유하세요", "보내세요",
]

# 정중 요청 어미 — COMMAND_MARKERS와 공존 시 override 보류
# (알고리즘 팀 지침: "~해 주세요"는 REQUEST 유지)
SOFT_REQUEST_MARKERS = [
    "가능할까요", "주실 수 있나요",
    "부탁드립니다", "요청드립니다",
    "전달 부탁드립니다",
]


def normalize_command_intent(source_text: str, llm_intent: str) -> Tuple[str, str]:
    """COMMAND marker가 있고 SOFT_REQUEST marker가 없으면 'command' override.

    주의: "~해 주세요/주세요" 계열은 SOFT_REQUEST가 아니지만 COMMAND_MARKERS에도 없으므로
          override 안 됨 → 기본 REQUEST 유지 (알고리즘 팀 과잉 보정 방지).
    """
    has_command      = any(m in source_text for m in COMMAND_MARKERS)
    has_soft_request = any(m in source_text for m in SOFT_REQUEST_MARKERS)
    if has_command and not has_soft_request:
        return "command", COMMAND_OVERRIDE_REASON
    return llm_intent, "OK"


# ─────────────────────────────────────────────────────────────────────────
# Normalizer chain (Patch 1 + Patch 2)
# ─────────────────────────────────────────────────────────────────────────

def normalize_intent_chain(source_text: str, llm_intent: str) -> Tuple[str, str]:
    """REPORT → COMMAND 순서로 normalizer 체인 적용.

    Returns:
        (final_intent, reason_code)
        reason_code: REPORT_OVERRIDE_REASON / COMMAND_OVERRIDE_REASON / "OK"
    """
    fixed, why = normalize_report_intent(source_text, llm_intent)
    if why == REPORT_OVERRIDE_REASON:
        return fixed, why
    fixed, why = normalize_command_intent(source_text, fixed)
    if why == COMMAND_OVERRIDE_REASON:
        return fixed, why
    return llm_intent, "OK"
