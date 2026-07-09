from __future__ import annotations

from butler_pc_core.cards.box3.actual_fail_class import (
    BLOCK_UNSUPPORTED_CLAIM,
    NEEDS_REVIEW_UNSUPPORTED_CLAIM,
    NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL,
    is_blocking_actual_fail_class,
)
from butler_pc_core.cards.box3.real_contracts import ClaimVerdict, sha256_text
from butler_pc_core.cards.box3.real_grounding import summarize_grounding
from butler_pc_core.cards.box3.grounded_prompt import evaluate_usefulness_gate
from butler_pc_core.cards.box3.unsupported_labeling import (
    FULL_REVIEW_BANNER,
    LABEL_PREFIX,
    annotate_unsupported_lines,
    normalize_draft_claim_line,
    scan_outbound_text_for_pii_or_secret,
)


def _unsupported(text: str) -> ClaimVerdict:
    return ClaimVerdict(
        "claim-1",
        sha256_text(text),
        "unsupported",
        [sha256_text("근거")],
        0.9,
        "EVIDENCE_CONTRADICTS",
    )


def _supported(text: str) -> ClaimVerdict:
    return ClaimVerdict(
        "claim-2",
        sha256_text(text),
        "supported",
        [sha256_text("근거")],
        0.95,
        "EVIDENCE_ENTAILS",
    )


def test_severity_map_demotes_only_unsupported_review_label():
    assert is_blocking_actual_fail_class(BLOCK_UNSUPPORTED_CLAIM) is True
    assert is_blocking_actual_fail_class(NEEDS_REVIEW_UNSUPPORTED_CLAIM) is False
    assert is_blocking_actual_fail_class(NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL) is False
    assert is_blocking_actual_fail_class("BLOCK_HUMAN_APPROVAL_SCOPE_MISMATCH") is True
    assert is_blocking_actual_fail_class("UNKNOWN_NEW_FAIL_CLASS") is True


def test_grounding_and_usefulness_emit_needs_review_for_unsupported():
    verdicts = [_unsupported("매출 목표: 10억원")]
    summary = summarize_grounding(verdicts)
    useful = evaluate_usefulness_gate("핵심 내용: 매출 목표는 10억원입니다", verdicts)

    assert summary.fail_class == NEEDS_REVIEW_UNSUPPORTED_CLAIM
    assert useful.status == "PARTIAL"
    assert useful.fail_class == NEEDS_REVIEW_UNSUPPORTED_CLAIM


def test_annotate_unsupported_lines_exact_match_preserves_draft_delivery():
    draft = "제목: 사업계획\n핵심 내용: 매출 목표는 10억원입니다\n근거: 첨부 자료"
    unsupported = {sha256_text("매출 목표는 10억원입니다")}

    annotated, meta = annotate_unsupported_lines(draft, unsupported)

    assert LABEL_PREFIX in annotated
    assert "핵심 내용:" in annotated
    assert meta.unsupported_claim_count == 1
    assert meta.annotated_claim_count == 1
    assert meta.label_coverage_ok is True
    assert meta.label_banner_applied is False


def test_annotate_fail_safe_labels_all_candidate_lines_on_digest_miss():
    draft = "제목: 사업계획\n핵심 내용: 매출 목표는 10억원입니다\n근거: 첨부 자료"
    unsupported = {sha256_text("digest miss")}

    annotated, meta = annotate_unsupported_lines(draft, unsupported)

    assert annotated.startswith(FULL_REVIEW_BANNER)
    assert annotated.count(LABEL_PREFIX) >= 3
    assert meta.label_coverage_ok is False
    assert meta.review_reason_code == NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL


def test_no_unsupported_no_label():
    annotated, meta = annotate_unsupported_lines("제목: 정상", set())
    assert annotated == "제목: 정상"
    assert meta.unsupported_claim_count == 0
    assert meta.annotated_claim_count == 0
    assert meta.label_coverage_ok is True


def test_outbound_dlp_guard_blocks_labeled_secret_before_output():
    verdict = scan_outbound_text_for_pii_or_secret(f"{LABEL_PREFIX} api_key: abcdef123456")
    assert verdict.blocked is True
    assert verdict.reason_code == "BLOCK_DLP_OUTBOUND_DRAFT"


def test_normalize_draft_claim_line_matches_label_stripping_contract():
    assert normalize_draft_claim_line("- 핵심 내용: 매출 목표는 10억원입니다") == "매출 목표는 10억원입니다"
    assert normalize_draft_claim_line("1. 일정: 2026년 7월 9일") == "2026년 7월 9일"
