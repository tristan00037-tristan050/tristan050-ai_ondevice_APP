"""verifier_card1.py — 6.5.6 Day 11 D mode 전용 verifier ruleset (10가지 hard rules).

알고리즘 팀 Day 11 명세 (2026-05-14):
  V1. schema_valid=true 아니면 reject (기존 Block 6 흡수)
  V2. evidence 없는 action/material/deadline reject (기존 Block 1~3 흡수)
  V3. false deadline reject (기존 Block 7 흡수)
  V4. NO_ACTION + action 생성 reject (기존 Block 4 흡수)
  V5. G23 hard violation reject (PURE_QUESTION_MISLABELED_AS_REQUEST / REPORT_MISLABELED_AS_REQUEST)
  V6. G22 duplicate/strict warning reject (사전 검증 단계에서 차단)
  V7. auto_apply 는 verifier_errors == 0 일 때만 허용
  V8. auto_apply gold-equivalent safe class 조건 (intent ∈ {REQUEST, REPORT, NO_ACTION})
  V9. 외부 전송/삭제/배포/결제/계약/개인정보 task auto_apply 금지
  V10. deadline_type INQUIRY/URGENCY/CONDITION → actionable=true 금지
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# G23 hard fail 패턴 (검사 단계에서 차단)
PURE_QUESTION_PATTERNS = ["어떻게 되나요", "언제인가요", "누구인가요", "어디인가요"]
REPORT_FIXED_PATTERNS  = ["완료했습니다", "보고드립니다", "안내드립니다",
                          "공유했습니다", "전달했습니다"]
ACTION_VERB_PATTERNS   = [
    "보내", "전달", "공유", "검토", "작성", "수정", "제출", "회신",
    "업로드", "확인 부탁", "조율", "해 주", "부탁드립", "보고 부탁",
    "정리해", "보내주", "주실 수 있나요",
]

# 위험 작업 키워드 (V9)
RISKY_TASK_WORDS = ["삭제", "배포", "결제", "계약", "외부 전송",
                    "이메일 발송", "메신저 전송", "권한 변경", "권한 회수"]
RISKY_TAGS = {"risky_action", "external_send", "deployment",
              "file_delete", "permission_change"}

SAFE_INTENT_FOR_AUTO = {"REQUEST", "REPORT", "NO_ACTION"}
NON_ACTIONABLE_DEADLINE = {"INQUIRY", "URGENCY", "CONDITION"}


@dataclass
class VerifierResult:
    """row 단위 verifier 결과."""
    sample_id:      str
    schema_valid:   bool
    errors:         List[str]  = field(default_factory=list)
    detail:         List[str]  = field(default_factory=list)
    blocked_auto:   bool       = False  # auto_apply 금지

    @property
    def error_count(self) -> int:
        return len(self.errors)


def _has_action_verb(text: str) -> bool:
    return any(v in text for v in ACTION_VERB_PATTERNS)


def _g23_hard_violation(text: str, intent: str, action_required: bool) -> Optional[str]:
    if not text:
        return None
    if intent == "REQUEST" and action_required and not _has_action_verb(text):
        for p in PURE_QUESTION_PATTERNS:
            if p in text:
                return f"V5/G23 PURE_QUESTION_MISLABELED_AS_REQUEST pattern={p}"
    if intent == "REQUEST":
        for p in REPORT_FIXED_PATTERNS:
            if p in text:
                return f"V5/G23 REPORT_MISLABELED_AS_REQUEST pattern={p}"
    return None


def apply_card1_hard_rules(
    *,
    sample_id:        str,
    text:             str,
    pred:             Dict[str, Any],
    schema_valid:     bool,
    base_verifier_errors: List[str],
    duplicate_strict_warning: bool = False,
    auto_apply_candidate: bool = False,
) -> VerifierResult:
    """단일 row 의 V1~V10 적용.

    Codex P1-2 정정 (옵션 B+C): V8/V9 는 auto_apply_candidate=True 인 경우에만
    적용. candidate 산출은 외부 (_mode_d_compute_auto_candidate) 에서 calibrated
    confidence + intent + action_required 기준으로 결정한다.

    pred 필수 필드:
      - intent_type, action_required, answer_required
      - deadline_type, deadline_is_actionable
      - actions (list of {action_text, evidence})
      - slice_tags (list, 옵션)
    """
    errors: List[str] = []
    detail: List[str] = []

    intent  = pred.get("intent_type")
    ar      = bool(pred.get("action_required"))
    dtype   = pred.get("deadline_type")
    dact    = bool(pred.get("deadline_is_actionable"))
    tags    = set(pred.get("slice_tags") or [])

    # V1
    if not schema_valid:
        errors.append("V1/SCHEMA_INVALID")
        detail.append("schema_valid=false")
    # V2/V3/V4 — base verifier 결과 흡수
    for e in (base_verifier_errors or []):
        errors.append(f"V234/{e}")
        detail.append(f"base verifier: {e}")
    # V5 — G23 hard
    g23 = _g23_hard_violation(text, intent, ar)
    if g23:
        errors.append("V5/G23_HARD")
        detail.append(g23)
    # V6 — G22 strict warning 사전 검증
    if duplicate_strict_warning:
        errors.append("V6/G22_STRICT_WARNING")
        detail.append("G22 strict warning carried into prediction")
    # V10 — deadline non-actionable
    if dtype in NON_ACTIONABLE_DEADLINE and dact:
        errors.append("V10/DEADLINE_NONACTIONABLE_TRUE")
        detail.append(f"deadline_type={dtype} 인데 deadline_is_actionable=true")

    # V7/V8/V9 — auto_apply_candidate 인 경우에만 위험 검사 (Codex P1-2 정정)
    blocked = False
    if auto_apply_candidate:
        pre_errors = list(errors)
        # V8 — gold-equivalent safe intent class
        if intent not in SAFE_INTENT_FOR_AUTO:
            errors.append("V8/AUTO_APPLY_NOT_GOLD_EQUIVALENT_SAFE_CLASS")
            detail.append(f"intent={intent} 는 auto_apply 허용 클래스가 아님")
            blocked = True
        # V9 — 위험 작업 태그/키워드
        if tags & RISKY_TAGS:
            errors.append("V9/AUTO_APPLY_RISKY_TASK_BLOCKED")
            detail.append(f"risky tag: {sorted(tags & RISKY_TAGS)}")
            blocked = True
        elif any(w in (text or "") for w in RISKY_TASK_WORDS):
            errors.append("V9/AUTO_APPLY_RISKY_TASK_BLOCKED")
            detail.append("risky word in text")
            blocked = True
        # V7 — V1~V6/V10 위반 동반 시 차단
        if pre_errors:
            errors.append("V7/AUTO_APPLY_WITH_ERRORS")
            detail.append(f"auto_apply candidate 지만 verifier errors > 0: {pre_errors}")
            blocked = True

    return VerifierResult(
        sample_id    = sample_id,
        schema_valid = schema_valid,
        errors       = errors,
        detail       = detail,
        blocked_auto = blocked,
    )
