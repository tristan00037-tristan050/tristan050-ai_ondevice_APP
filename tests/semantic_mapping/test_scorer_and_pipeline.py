"""test_scorer_and_pipeline.py — D-4 semantic_mapping 단계 2 검증 (+20).

카드 2 원래 결함 영역 시뮬레이션:
  외부 필드 5건 [협업 영역, 기간, 금액, 시작일, 연락처]
  → map_fields() → 각 필드가 정확한 슬롯에 매핑되는지 검증
"""
from __future__ import annotations

import pytest

from butler_pc_core.semantic_mapping.contracts import (
    MappingCandidate,
    MappingDecision,
    SourceField,
    ValueType,
)
from butler_pc_core.semantic_mapping.semantic_scorer import (
    compute_alias_score,
    compute_semantic_score,
)
from butler_pc_core.semantic_mapping.type_scorer import (
    apply_hard_guards,
    compute_type_score,
)
from butler_pc_core.semantic_mapping.slot_schema import SLOT_BY_ID, TARGET_SLOTS
from butler_pc_core.semantic_mapping.slot_resolver import resolve_slot_assignments
from butler_pc_core.semantic_mapping.pipeline import map_fields


# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

@pytest.fixture
def defect_fields():
    """카드 2 원래 결함 영역: 4개가 '사업 영역'으로 몰리던 5개 외부 필드."""
    return [
        SourceField("협업 영역", "AI 컨설팅",         "1. 협업 영역: AI 컨설팅"),
        SourceField("기간",     "6개월",              "2. 기간: 6개월"),
        SourceField("금액",     "5천만원",             "3. 금액: 5천만원"),
        SourceField("시작일",   "2026년 6월 1일",     "4. 시작일: 2026년 6월 1일"),
        SourceField("연락처",   "contact@partner.com", "연락처: contact@partner.com"),
    ]


def _d(decisions: list[MappingDecision], slot_id: str) -> MappingDecision:
    return next(d for d in decisions if d.target_slot.slot_id == slot_id)


# ── semantic_scorer tests (5) ─────────────────────────────────────────────────

def test_semantic_score_heading_match():
    """'기간' vs business_period — heading '사업 기간'에 '기간' 토큰 공유 → ≥ 0.80."""
    src = SourceField("기간", "6개월", "기간: 6개월")
    assert compute_semantic_score(src, SLOT_BY_ID["business_period"]) >= 0.80


def test_semantic_score_alias_match():
    """'금액' vs budget — alias '금액' 직접 포함 → ≥ 0.80."""
    src = SourceField("금액", "5천만원", "금액: 5천만원")
    assert compute_semantic_score(src, SLOT_BY_ID["budget"]) >= 0.80


def test_semantic_score_token_overlap():
    """'협업 영역' vs business_area — heading '사업 영역'의 '영역' 공유 → ≥ 0.70."""
    src = SourceField("협업 영역", "AI 컨설팅", "협업 영역: AI 컨설팅")
    assert compute_semantic_score(src, SLOT_BY_ID["business_area"]) >= 0.70


def test_semantic_score_no_relation():
    """'기간' vs contact — 관련 없음 → 0.0."""
    src = SourceField("기간", "6개월", "기간: 6개월")
    assert compute_semantic_score(src, SLOT_BY_ID["contact"]) == 0.0


def test_alias_score_direct_hit():
    """'연락처' vs contact — alias 집합에 '연락처' 직접 포함 → 1.0."""
    src = SourceField("연락처", "contact@partner.com", "연락처: contact@partner.com")
    assert compute_alias_score(src, SLOT_BY_ID["contact"]) == 1.0


# ── type_scorer tests (5) ─────────────────────────────────────────────────────

def test_type_score_email_in_contact():
    """EMAIL 타입 → contact (EMAIL 허용) → 1.0."""
    src = SourceField("연락처", "a@b.com", "연락처: a@b.com", detected_type=ValueType.EMAIL)
    assert compute_type_score(src, SLOT_BY_ID["contact"]) == 1.0


def test_type_score_money_in_budget():
    """MONEY 타입 → budget (MONEY 허용) → 1.0."""
    src = SourceField("금액", "5천만원", "금액: 5천만원", detected_type=ValueType.MONEY)
    assert compute_type_score(src, SLOT_BY_ID["budget"]) == 1.0


def test_type_score_date_partial_compat():
    """DATE 타입 → business_period (DATE_RANGE만 허용) → 0.45 부분 호환."""
    src = SourceField("시작일", "2026-01-01", "시작일: 2026-01-01", detected_type=ValueType.DATE)
    assert compute_type_score(src, SLOT_BY_ID["business_period"]) == pytest.approx(0.45)


def test_type_score_incompatible():
    """EMAIL 타입 → business_period → 완전 비호환 → 0.0."""
    src = SourceField("연락처", "a@b.com", "연락처: a@b.com", detected_type=ValueType.EMAIL)
    assert compute_type_score(src, SLOT_BY_ID["business_period"]) == 0.0


def test_hard_guard_type_zero():
    """type_score == 0.0 → apply_hard_guards → 최종 ≤ 0.49."""
    result = apply_hard_guards(0.80, 0.0)
    assert result <= 0.49


# ── pipeline integration tests (10) ──────────────────────────────────────────

def test_consulting_area_maps_to_business_area(defect_fields):
    """★ '협업 영역: AI 컨설팅' → business_area 슬롯 정확 매핑."""
    decisions = map_fields(defect_fields, TARGET_SLOTS)
    d = _d(decisions, "business_area")
    assert d.mapped
    assert d.source_field is not None
    assert "영역" in d.source_field.label


def test_period_maps_to_business_period(defect_fields):
    """★ '기간: 6개월' → business_period 슬롯 정확 매핑."""
    decisions = map_fields(defect_fields, TARGET_SLOTS)
    d = _d(decisions, "business_period")
    assert d.mapped
    assert d.source_field.label == "기간"


def test_money_maps_to_budget(defect_fields):
    """★ '금액: 5천만원' → budget 슬롯 정확 매핑."""
    decisions = map_fields(defect_fields, TARGET_SLOTS)
    d = _d(decisions, "budget")
    assert d.mapped
    assert d.source_field.label == "금액"


def test_start_date_maps_to_schedule(defect_fields):
    """★ '시작일: 2026년 6월 1일' → schedule 슬롯 정확 매핑."""
    decisions = map_fields(defect_fields, TARGET_SLOTS)
    d = _d(decisions, "schedule")
    assert d.mapped
    assert d.source_field.label == "시작일"


def test_contact_email_maps_to_contact(defect_fields):
    """★ '연락처: contact@partner.com' → contact 슬롯 정확 매핑."""
    decisions = map_fields(defect_fields, TARGET_SLOTS)
    d = _d(decisions, "contact")
    assert d.mapped
    assert d.source_field.label == "연락처"


def test_contact_never_maps_to_business_period(defect_fields):
    """★ Block: '연락처'(EMAIL)가 business_period에 절대 매핑 X."""
    decisions = map_fields(defect_fields, TARGET_SLOTS)
    d = _d(decisions, "business_period")
    if d.mapped:
        assert d.source_field.label != "연락처", (
            "연락처(EMAIL)가 business_period(DATE_RANGE 전용)에 매핑됨 — hard guard 미작동"
        )


def test_money_never_maps_to_business_area(defect_fields):
    """'금액'(MONEY)이 business_area(TEXT/CATEGORY 전용)에 절대 매핑 X."""
    decisions = map_fields(defect_fields, TARGET_SLOTS)
    d = _d(decisions, "business_area")
    if d.mapped:
        assert d.source_field.label != "금액", (
            "금액(MONEY)이 business_area(TEXT/CATEGORY 전용)에 매핑됨 — 타입 guard 미작동"
        )


def test_slot_collapse_prevented():
    """4개 소스 모두 business_area를 경쟁해도 슬롯당 1:1 할당 유지 (one-to-many collapse X)."""
    fields = [
        SourceField("영역",   "AI",   "영역: AI"),
        SourceField("분야",   "ML",   "분야: ML"),
        SourceField("업무",   "DL",   "업무: DL"),
        SourceField("서비스", "NLP",  "서비스: NLP"),
    ]
    decisions = map_fields(fields, TARGET_SLOTS)
    mapped_slot_ids = [d.target_slot.slot_id for d in decisions if d.mapped]
    # 매핑된 슬롯에 중복 없어야 함
    assert len(mapped_slot_ids) == len(set(mapped_slot_ids))


def test_hard_guard_contact_unmapped_for_period():
    """'연락처'(EMAIL) 단독 → business_period는 unmapped (hard guard 작동)."""
    fields = [SourceField("연락처", "contact@example.com", "연락처: contact@example.com")]
    decisions = map_fields(fields, TARGET_SLOTS)
    d = _d(decisions, "business_period")
    assert not d.mapped, "EMAIL 타입이 DATE_RANGE 전용 슬롯에 매핑됨 — hard guard 실패"


def test_low_confidence_needs_review():
    """combined_score 0.49 ~ 0.70 범위 후보 → needs_review=True."""
    slot = SLOT_BY_ID["business_overview"]
    src  = SourceField("임시", "임시 값", "임시: 임시 값", detected_type=ValueType.TEXT)
    cand = MappingCandidate(
        source_field=src,
        target_slot=slot,
        semantic_score=0.5,
        type_score=1.0,
        combined_score=0.55,    # 0.49 ≤ x < 0.70 → needs_review
    )
    decisions = resolve_slot_assignments([cand], TARGET_SLOTS)
    d = _d(decisions, "business_overview")
    assert d.mapped
    assert d.needs_review
