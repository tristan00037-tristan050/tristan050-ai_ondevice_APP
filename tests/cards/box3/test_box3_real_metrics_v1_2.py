"""융합 지표 — 임계 게이트(unsupported==0·no_evidence≤0.05·citation≥0.95 등)."""
from __future__ import annotations

from butler_pc_core.cards.box3.real_contracts import ClaimVerdict, EvidenceUnit, sha256_text
from butler_pc_core.cards.box3.real_metrics import (
    build_metrics,
    fixed_eval_metric_pass,
    metric_fail_class,
)


def _supported(claim_id: str, digest: str) -> ClaimVerdict:
    return ClaimVerdict(claim_id, sha256_text(claim_id), "supported", [digest], 0.9, "EVIDENCE_ENTAILS")


def _unit(text: str, kind: str = "text") -> EvidenceUnit:
    return EvidenceUnit(text[:4], sha256_text("src"), sha256_text(text), kind, text)  # type: ignore[arg-type]


def test_clean_supported_draft_passes_all_gates():
    unit = _unit("표 | 납품일 2026년 3월 31일", "table")
    verdicts = [_supported("c1", unit.evidence_digest)]
    citations = [unit.citation()]
    draft = "제목:x\n배경:x\n핵심 내용:x\n근거:x\n확인 필요:x\n최종 문안:x"
    metrics = build_metrics(draft_text=draft, verdicts=verdicts, evidence_units=[unit], citations=citations)
    assert metrics.unsupported_claim_rate == 0.0
    assert metrics.citation_accuracy == 1.0
    assert metrics.table_figure_coverage == 1.0
    assert fixed_eval_metric_pass(metrics)
    assert metric_fail_class(metrics) is None


def test_unsupported_claim_blocks_final_gate():
    verdicts = [ClaimVerdict("c1", sha256_text("c1"), "unsupported", [], 0.9, "EVIDENCE_CONTRADICTS")]
    metrics = build_metrics(draft_text="제목:x", verdicts=verdicts, evidence_units=[], citations=[])
    assert metrics.unsupported_claim_rate > 0.0
    assert metric_fail_class(metrics) == "BLOCK_FINAL_GATE_UNSUPPORTED"


def test_uncited_table_figure_below_coverage_gate():
    unit = _unit("표 | 매출 1억원", "table")
    verdicts = [_supported("c1", sha256_text("other"))]  # 표 단위를 인용하지 않음
    # 다른 게이트(format/style/citation)는 통과시키고 table_figure 만 단독 실패시킨다.
    full_format = "제목:x\n배경:x\n핵심 내용:x\n근거:x\n확인 필요:x\n최종 문안:x"
    metrics = build_metrics(draft_text=full_format, verdicts=verdicts, evidence_units=[unit], citations=[])
    assert metrics.format_compliance >= 0.85 and metrics.style_compliance >= 0.70
    assert metrics.citation_accuracy >= 0.95
    assert metrics.table_figure_coverage < 0.70
    assert metric_fail_class(metrics) == "TABLE_FIGURE_COVERAGE_BELOW_GATE"
