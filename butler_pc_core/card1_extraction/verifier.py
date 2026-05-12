"""verifier.py — 원문 근거 검증 + hallucination 차단 (알고리즘 팀 §6-6, §11).

- verify_card1_extraction: 단계 6.3 기준선 (block 1~4) — 기존 호환.
- apply_hard_rules:        단계 6.5.1 알고리즘 팀 §6 — block 1~6 강화.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .contracts import Card1Extraction, ExtractedAction, IntentType, SentenceType
from .parser import ACTION_VERBS, _ACTION_VERB_RE


def verify_card1_extraction(
    extraction: Card1Extraction,
    source_text: str,
) -> Tuple[Card1Extraction, int]:
    """
    원문 근거 검증 → (정정된 Card1Extraction, hallucination 개수).

    Block 기준 (알고리즘 팀 §11):
      1. 원문에 없는 마감일 표현  → deadline/deadline_raw 초기화
      2. 원문에 없는 자료명       → materials에서 제거
      3. 부정형 문장을 액션으로   → actions 전체 제거
      4. 액션 동사 없는 문장을 액션으로 → 해당 액션 제거
    """
    hallucination_count = 0

    # Block 1: 마감일 원문 근거 없음
    deadline_raw = extraction.deadline_raw
    if deadline_raw and deadline_raw not in source_text:
        extraction = _replace(extraction, deadline=None, deadline_raw="")
        hallucination_count += 1

    # Block 2: 자료 원문 근거 없음
    verified_materials = []
    for mat in extraction.materials:
        if mat in source_text:
            verified_materials.append(mat)
        else:
            hallucination_count += 1

    # Block 3: 부정형 문장 전체 → 액션 제거
    if extraction.sentence_type == SentenceType.NEGATIVE:
        hallucination_count += len(extraction.actions)
        extraction = _replace(extraction, materials=verified_materials, actions=[])
        return extraction, hallucination_count

    # Block 4: 액션 동사 없는 액션 항목 제거
    verified_actions = []
    for action in extraction.actions:
        evidence = action.source_evidence or action.action_text
        if _ACTION_VERB_RE.search(evidence) or _ACTION_VERB_RE.search(source_text):
            verified_actions.append(action)
        else:
            hallucination_count += 1

    extraction = _replace(
        extraction,
        materials=verified_materials,
        actions=verified_actions,
    )
    return extraction, hallucination_count


def _replace(extraction: Card1Extraction, **kwargs) -> Card1Extraction:
    """Card1Extraction 필드 부분 교체 (dataclass replace 패턴)."""
    return Card1Extraction(
        intent        = kwargs.get("intent",        extraction.intent),
        intent_type   = kwargs.get("intent_type",   extraction.intent_type),
        deadline      = kwargs.get("deadline",      extraction.deadline),
        deadline_raw  = kwargs.get("deadline_raw",  extraction.deadline_raw),
        materials     = kwargs.get("materials",     extraction.materials),
        actions       = kwargs.get("actions",       extraction.actions),
        sentence_type = kwargs.get("sentence_type", extraction.sentence_type),
        confidence    = kwargs.get("confidence",    extraction.confidence),
        needs_review  = kwargs.get("needs_review",  extraction.needs_review),
        reason_code   = kwargs.get("reason_code",   extraction.reason_code),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 단계 6.5.1 — 알고리즘 팀 §6 hard-rule (6가지 BLOCK)
# ─────────────────────────────────────────────────────────────────────────────

# Block 코드 상수 — 6가지 규칙
BLOCK_NO_EVIDENCE_DEADLINE   = "block_1_no_evidence_deadline"
BLOCK_NO_EVIDENCE_MATERIAL   = "block_2_no_evidence_material"
BLOCK_NO_EVIDENCE_ACTION     = "block_3_no_evidence_action_evidence"
BLOCK_NEGATED_ACTION         = "block_4_negated_action"
BLOCK_AUTO_APPLY_LOW_CONF    = "block_5_auto_apply_low_confidence"
BLOCK_SCHEMA_RETRY_FAILED    = "block_6_schema_retry_failed"

# 단계 6.5.3 Patch 3 — false_deadline hard rule
BLOCK_FALSE_DEADLINE_NO_EVIDENCE = "block_7_false_deadline_no_evidence"

# 알고리즘 팀 §6.5.3 — 마감 표현 식별 marker
DEADLINE_MARKERS = [
    "오늘", "내일", "모레",
    "이번 주", "다음 주",
    "금요일", "월요일", "화요일", "수요일", "목요일", "토요일", "일요일",
    "오전", "오후",
    "까지", "전까지", "중으로",
    "마감", "기한", "due",
]


def has_deadline_evidence(
    source_text: str,
    deadline_text: str | None,
    evidence:    str | None,
) -> bool:
    """단계 6.5.3 Patch 3 — deadline evidence 1차 검증 (text-level).

    True  → 통과 (block 안 함)
    False → BLOCK_FALSE_DEADLINE_NO_EVIDENCE 발동
    """
    if not deadline_text:
        return True
    if evidence and evidence in source_text:
        return True
    if not any(m in source_text for m in DEADLINE_MARKERS):
        return False
    compact_src      = source_text.replace(" ", "")
    compact_deadline = deadline_text.replace(" ", "")
    if compact_deadline and compact_deadline in compact_src:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# 단계 6.5.4 Patch C — verify_deadline (type-aware Block 7 재정의)
# ─────────────────────────────────────────────────────────────────────────
def verify_deadline(
    deadline_text: str | None,
    evidence:      str | None,
    source:        str,
) -> tuple[bool, str]:
    """단계 6.5.4 — type-aware deadline 검증.

    Returns:
        (valid, reason)
        valid=True  → 통과 (deadline 보존)
        valid=False → block (deadline 제거 + reason 기록)

    reason 코드:
      NO_DEADLINE
      DEADLINE_EVIDENCE_NOT_IN_SOURCE
      NOT_A_DEADLINE_deadline_inquiry
      NOT_A_DEADLINE_urgency
      NOT_A_DEADLINE_condition
      NOT_A_DEADLINE_none
      VALID_hard_deadline
      VALID_soft_deadline
    """
    from .deadline_types import classify_deadline_candidate, is_valid_deadline_type

    if not deadline_text:
        return True, "NO_DEADLINE"

    if not evidence or evidence not in source:
        return False, "DEADLINE_EVIDENCE_NOT_IN_SOURCE"

    dtype = classify_deadline_candidate(evidence)
    if not is_valid_deadline_type(dtype):
        return False, f"NOT_A_DEADLINE_{dtype.value}"

    return True, f"VALID_{dtype.value}"


@dataclass
class VerifierReport:
    """알고리즘 팀 §6 hard-rule 검증 결과."""
    extraction:   Card1Extraction
    errors:       List[str]            = field(default_factory=list)  # block 코드
    error_detail: List[str]            = field(default_factory=list)  # 사유 텍스트
    blocked_auto: bool                 = False    # True면 자동 적용 금지

    @property
    def error_count(self) -> int:
        return len(self.errors)


def apply_hard_rules(
    extraction:   Card1Extraction,
    source_text:  str,
    *,
    confidence:   float = 0.0,
    schema_valid: bool  = True,
) -> VerifierReport:
    """알고리즘 팀 §6 — 6가지 hard-rule 적용.

    Block 1. 원문에 없는 마감일             → deadline_raw 제거
    Block 2. 원문에 없는 자료               → materials/material_refs에서 제거
    Block 3. action evidence 원문 부재       → 해당 action 제거
    Block 4. 부정형/no-action을 action으로   → action 전부 제거
    Block 5. confidence < 0.75 자동 적용     → blocked_auto=True
    Block 6. JSON schema validation 실패     → blocked_auto=True
    Block 7. has_deadline_evidence=False     → deadline_text/deadline_raw 제거
    """
    errors:  List[str] = []
    detail:  List[str] = []

    # ── Block 1: 마감일 원문 근거 ─────────────────────────────────────────────
    deadline_raw = extraction.deadline_raw
    if deadline_raw and deadline_raw not in source_text:
        errors.append(BLOCK_NO_EVIDENCE_DEADLINE)
        detail.append(f"deadline_raw='{deadline_raw}' not in source")
        extraction = _replace(extraction, deadline=None, deadline_raw="")

    # ── Block 7: 단계 6.5.4 type-aware verify_deadline ─────────────────────
    if extraction.deadline_raw:
        first_action_ev = (extraction.actions[0].source_evidence
                           if extraction.actions else "")
        ok, reason = verify_deadline(extraction.deadline_raw, first_action_ev,
                                     source_text)
        if not ok:
            errors.append(BLOCK_FALSE_DEADLINE_NO_EVIDENCE)
            detail.append(f"deadline_raw='{extraction.deadline_raw}' {reason}")
            extraction = _replace(extraction, deadline=None, deadline_raw="")

    # ── Block 2: 자료 원문 근거 (materials + 각 action.material_refs) ──────────
    verified_materials: List[str] = []
    for mat in extraction.materials:
        if mat in source_text:
            verified_materials.append(mat)
        else:
            errors.append(BLOCK_NO_EVIDENCE_MATERIAL)
            detail.append(f"materials='{mat}' not in source")

    # ── Block 4: 부정형/no_action 처리 (action 단위 + 문장 단위) ─────────────
    sentence_negative = (extraction.sentence_type == SentenceType.NEGATIVE)
    intent_no_action  = (extraction.intent_type  == IntentType.NO_ACTION)

    survived_actions: List[ExtractedAction] = []
    for action in extraction.actions:
        # 4-1: is_negated 플래그
        if action.is_negated:
            errors.append(BLOCK_NEGATED_ACTION)
            detail.append(f"action '{action.action_text}' is_negated=True")
            continue
        # 4-2: 부정형 문장 전체
        if sentence_negative or intent_no_action:
            errors.append(BLOCK_NEGATED_ACTION)
            detail.append(f"action '{action.action_text}' in negated sentence")
            continue
        # ── Block 3: evidence 원문 부재 ────────────────────────────────────
        evidence = action.source_evidence or ""
        if evidence and evidence not in source_text:
            errors.append(BLOCK_NO_EVIDENCE_ACTION)
            detail.append(f"action evidence '{evidence}' not in source")
            continue
        # Block 3-보조: action_verb 없는 evidence는 보너스로 제거
        if evidence and not _ACTION_VERB_RE.search(evidence) \
                    and not _ACTION_VERB_RE.search(action.action_text) \
                    and not _ACTION_VERB_RE.search(source_text):
            errors.append(BLOCK_NO_EVIDENCE_ACTION)
            detail.append(f"action '{action.action_text}' has no action_verb")
            continue
        # material_refs도 원문에 없으면 제거 (Block 2 확장)
        verified_refs = [m for m in action.material_refs if m in source_text]
        if verified_refs != action.material_refs:
            for m in action.material_refs:
                if m not in source_text:
                    errors.append(BLOCK_NO_EVIDENCE_MATERIAL)
                    detail.append(f"action.material_refs='{m}' not in source")
            action = ExtractedAction(
                action_text     = action.action_text,
                owner           = action.owner,
                due_date        = action.due_date,
                source_evidence = action.source_evidence,
                confidence      = action.confidence,
                action_type     = action.action_type,
                deadline_text   = action.deadline_text,
                material_refs   = verified_refs,
                is_negated      = action.is_negated,
            )
        # Block 1 확장: action.deadline_text 원문 부재
        if action.deadline_text and action.deadline_text not in source_text:
            errors.append(BLOCK_NO_EVIDENCE_DEADLINE)
            detail.append(f"action.deadline_text='{action.deadline_text}' not in source")
            action = ExtractedAction(
                action_text     = action.action_text,
                owner           = action.owner,
                due_date        = action.due_date,
                source_evidence = action.source_evidence,
                confidence      = action.confidence,
                action_type     = action.action_type,
                deadline_text   = "",
                material_refs   = action.material_refs,
                is_negated      = action.is_negated,
            )
        # ── Block 7: type-aware verify_deadline (6.5.4) ──────────────────
        ok_dl, reason_dl = (True, "")
        if action.deadline_text:
            ok_dl, reason_dl = verify_deadline(
                action.deadline_text, action.source_evidence, source_text,
            )
        if action.deadline_text and not ok_dl:
            errors.append(BLOCK_FALSE_DEADLINE_NO_EVIDENCE)
            detail.append(f"action.deadline_text='{action.deadline_text}' {reason_dl}")
            action = ExtractedAction(
                action_text     = action.action_text,
                owner           = action.owner,
                due_date        = action.due_date,
                source_evidence = action.source_evidence,
                confidence      = action.confidence,
                action_type     = action.action_type,
                deadline_text   = "",
                material_refs   = action.material_refs,
                is_negated      = action.is_negated,
            )
        survived_actions.append(action)

    extraction = _replace(
        extraction,
        materials = verified_materials,
        actions   = survived_actions,
    )

    # ── Block 5: confidence < 0.75 자동 적용 금지 ──────────────────────────
    blocked_auto = False
    if confidence < 0.75:
        errors.append(BLOCK_AUTO_APPLY_LOW_CONF)
        detail.append(f"confidence={confidence:.3f} < 0.75")
        blocked_auto = True

    # ── Block 6: JSON Schema 실패 ──────────────────────────────────────────
    if not schema_valid:
        errors.append(BLOCK_SCHEMA_RETRY_FAILED)
        detail.append("JSON schema validation failed after retry")
        blocked_auto = True

    return VerifierReport(
        extraction   = extraction,
        errors       = errors,
        error_detail = detail,
        blocked_auto = blocked_auto,
    )
