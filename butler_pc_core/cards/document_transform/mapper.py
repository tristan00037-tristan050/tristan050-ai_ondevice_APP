"""mapper.py — D-4 Card 2 외부 사실 → 우리 양식 슬롯 매핑.

M-52 본질: "출처 없는 것을 잘 비워두기". source_fact_id 또는 citation 이
없으면 confidence 와 무관하게 blank 로 격리한다.

raw/original text data retention 0 — SourceFact 는 redacted value 와 citation
참조만 보유하며 원문 문단(raw_paragraph 등)을 저장하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SourceFact:
    """외부 문서에서 추출한 사실 단위 — redacted value + 출처 인용만."""
    fact_id: str
    label: str
    value: str                       # redacted 값 (원문 문단 아님)
    value_type: str = "unknown"      # number | date | money | text | unknown
    citation: Optional[str] = None   # 출처 인용 참조 (없으면 None → blank 강제)
    factpack_ok: bool = True
    wiki_only: bool = False          # source_fact 부재, wiki 보조만 → auto_fill 불가
    is_negated: bool = False


@dataclass(frozen=True)
class TemplateSlot:
    """우리 양식의 채울 슬롯."""
    slot_id: str
    heading: str
    expected_type: str = "text"
    placeholder: str = ""


@dataclass(frozen=True)
class SlotMapping:
    slot_id: str
    source_fact_id: Optional[str]
    confidence: float
    decision: str                    # auto_fill | review | blank
    citation: Optional[str] = None
    factpack_ok: bool = True
    fail_class: Optional[str] = None
    confidence_factors: dict = field(default_factory=dict)


# ── 8요소 confidence 산식 ────────────────────────────────────────────────────
# 각 요소 [0,1], 가중치 합 1.0. confidence = clamp(Σ w_i·f_i, 0, 1).
CONFIDENCE_WEIGHTS = {
    "label_similarity":   0.22,   # 사실 label ↔ 슬롯 heading 유사도
    "value_type_match":   0.18,   # value_type ↔ slot expected_type 일치
    "citation_present":   0.16,   # 출처 인용 존재
    "source_fact_present":0.14,   # 사실 자체 존재
    "lexicon_hit":        0.12,   # slot_pattern_lexicon 매칭
    "factpack_ok":        0.10,   # factpack 규칙 통과
    "unit_consistency":   0.05,   # 수치/단위 정합
    "negation_free":      0.03,   # 부정형 아님
}


def _label_similarity(fact_label: str, slot_heading: str) -> float:
    """토큰 자카드 유사도 — 결정적, 외부 의존 0."""
    a = {t for t in fact_label.lower().split() if t}
    b = {t for t in slot_heading.lower().split() if t}
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def compute_slot_confidence(
    fact: Optional[SourceFact],
    slot: TemplateSlot,
    lexicon: Optional[dict] = None,
) -> tuple[float, dict]:
    """8요소 confidence 산출. fact 가 None 이면 source_fact_present=0 → 낮은 값."""
    lexicon = lexicon or {}
    if fact is None:
        factors = {k: 0.0 for k in CONFIDENCE_WEIGHTS}
        return 0.0, factors

    lex_terms = set(lexicon.get(slot.slot_id, []))
    factors = {
        "label_similarity": _label_similarity(fact.label, slot.heading),
        "value_type_match": 1.0 if fact.value_type == slot.expected_type else 0.0,
        "citation_present": 1.0 if fact.citation else 0.0,
        "source_fact_present": 1.0,
        "lexicon_hit": 1.0 if (lex_terms & set(fact.label.lower().split())) else 0.0,
        "factpack_ok": 1.0 if fact.factpack_ok else 0.0,
        "unit_consistency": 1.0 if fact.value.strip() else 0.0,
        "negation_free": 0.0 if fact.is_negated else 1.0,
    }
    raw = sum(CONFIDENCE_WEIGHTS[k] * factors[k] for k in CONFIDENCE_WEIGHTS)
    return max(0.0, min(1.0, raw)), factors


def classify_slot_fill(confidence, routing, source_fact_id=None,
                       citation=None, factpack_ok=True):
    """M-52 불변식 — 출처 없는 사실은 confidence 무관 blank.

    명령서 v1.1 §1(2) 고정 본질. 순서를 변경하지 않는다.
    """
    if not source_fact_id or not citation:
        return "blank"
    if not factpack_ok:
        return "blank"
    if confidence < routing.threshold_blank:
        return "blank"
    if not routing.auto_fill_allowed:
        return "review"
    if (routing.threshold_auto_fill is not None
            and confidence >= routing.threshold_auto_fill):
        return "auto_fill"
    return "review"


def map_facts_to_template_slots(
    source_facts: list,
    template_slots: list,
    routing,
    lexicon: Optional[dict] = None,
) -> list:
    """각 슬롯에 가장 잘 맞는 source_fact 를 매핑하고 fill 결정을 산출한다.

    wiki_only 사실(원천 사실 부재, wiki 보조만)은 매칭되어도 auto_fill 불가 —
    fail_class=WIKI_ONLY_FACT_NOT_AUTOFILLABLE 로 blank 격리.
    """
    by_id = {f.fact_id: f for f in source_facts}
    mappings = []
    for slot in template_slots:
        best_fact = None
        best_conf = -1.0
        best_factors: dict = {}
        for fact in source_facts:
            conf, factors = compute_slot_confidence(fact, slot, lexicon)
            if conf > best_conf:
                best_conf, best_fact, best_factors = conf, fact, factors

        if best_fact is None:
            mappings.append(SlotMapping(
                slot_id=slot.slot_id, source_fact_id=None, confidence=0.0,
                decision="blank", citation=None, factpack_ok=True,
                fail_class="SOURCE_FACT_MISSING",
            ))
            continue

        fail_class = None
        decision = classify_slot_fill(
            best_conf, routing,
            source_fact_id=best_fact.fact_id,
            citation=best_fact.citation,
            factpack_ok=best_fact.factpack_ok,
        )
        # wiki-only 사실은 auto_fill 금지 강제 (M-52 / WIKI_ONLY fail class)
        if best_fact.wiki_only and decision == "auto_fill":
            decision = "blank"
            fail_class = "WIKI_ONLY_FACT_NOT_AUTOFILLABLE"
        elif decision == "blank":
            if not best_fact.citation:
                fail_class = "SOURCE_CITATION_MISSING"
            elif not best_fact.factpack_ok:
                fail_class = "UNSUPPORTED_FACT_MAPPING"

        mappings.append(SlotMapping(
            slot_id=slot.slot_id,
            source_fact_id=best_fact.fact_id if best_fact.fact_id in by_id else None,
            confidence=round(best_conf, 4),
            decision=decision,
            citation=best_fact.citation,
            factpack_ok=best_fact.factpack_ok,
            fail_class=fail_class,
            confidence_factors=best_factors,
        ))
    return mappings
