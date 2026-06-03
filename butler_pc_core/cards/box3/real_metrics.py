"""Box3 real 융합 — claim-level 지표 + fixed-eval 게이트(단일 정의).

베이스: maindev real_metrics(claim 지표·format/style 준수·table_figure coverage).
임계는 지시서 6장 정본: unsupported_claim_rate==0, no_evidence≤0.05,
citation_accuracy≥0.95, format≥0.85, style≥0.70, table_figure≥0.70.
"""
from __future__ import annotations

from .real_contracts import Box3RealMetrics, ClaimVerdict, EvidenceUnit
from .real_fail_class import (
    BLOCK_FINAL_GATE_UNSUPPORTED,
    CITATION_ACCURACY_BELOW_GATE,
    FORMAT_MATCH_BELOW_GATE,
    NEEDS_REVIEW_NO_EVIDENCE,
    STYLE_MATCH_BELOW_GATE,
    TABLE_FIGURE_COVERAGE_BELOW_GATE,
)
from .real_grounding import evidence_kind_coverage

REQUIRED_SECTIONS = ["제목", "배경", "핵심 내용", "근거", "확인 필요", "최종 문안"]
FORBIDDEN_STYLE_TERMS = ["무조건", "반드시 보장", "법적으로 확정", "100% 확실"]

REAL_METRIC_THRESHOLDS: dict[str, float] = {
    "unsupported_claim_rate": 0.0,
    "no_evidence_claim_rate": 0.05,
    "citation_accuracy": 0.95,
    "format_compliance": 0.85,
    "style_compliance": 0.70,
    "table_figure_coverage": 0.70,
}


def calculate_claim_metrics(verdicts: list[ClaimVerdict]) -> dict[str, int | float]:
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    supported = [v for v in factual if v.support_level == "supported"]
    unsupported = [v for v in factual if v.support_level == "unsupported"]
    no_evidence = [v for v in factual if v.support_level == "no_evidence"]
    factual_count = len(factual)
    valid_supported = [v for v in supported if v.evidence_digests]
    return {
        "factual_claim_count": factual_count,
        "supported_count": len(supported),
        "unsupported_count": len(unsupported),
        "no_evidence_count": len(no_evidence),
        "unsupported_claim_rate": 0.0 if factual_count == 0 else len(unsupported) / factual_count,
        "no_evidence_claim_rate": 0.0 if factual_count == 0 else len(no_evidence) / factual_count,
        "citation_accuracy": 0.0 if not supported else len(valid_supported) / len(supported),
    }


def format_compliance(draft_text: str) -> float:
    if not draft_text.strip():
        return 0.0
    hits = sum(1 for section in REQUIRED_SECTIONS if f"{section}:" in draft_text or f"{section} :" in draft_text)
    return hits / len(REQUIRED_SECTIONS)


def style_compliance(draft_text: str) -> float:
    if not draft_text.strip():
        return 0.0
    lowered = draft_text.casefold()
    bad = sum(1 for term in FORBIDDEN_STYLE_TERMS if term.casefold() in lowered)
    return max(0.0, 1.0 - (bad / max(1, len(FORBIDDEN_STYLE_TERMS))))


def build_metrics(
    *,
    draft_text: str,
    verdicts: list[ClaimVerdict],
    evidence_units: list[EvidenceUnit],
    citations: list[dict[str, str]],
) -> Box3RealMetrics:
    claim = calculate_claim_metrics(verdicts)
    return Box3RealMetrics(
        unsupported_claim_rate=float(claim["unsupported_claim_rate"]),
        no_evidence_claim_rate=float(claim["no_evidence_claim_rate"]),
        citation_accuracy=float(claim["citation_accuracy"]),
        format_compliance=format_compliance(draft_text),
        style_compliance=style_compliance(draft_text),
        table_figure_coverage=evidence_kind_coverage(evidence_units, citations),
        factual_claim_count=int(claim["factual_claim_count"]),
        unsupported_count=int(claim["unsupported_count"]),
        no_evidence_count=int(claim["no_evidence_count"]),
        supported_count=int(claim["supported_count"]),
    )


def fixed_eval_metric_pass(metrics: Box3RealMetrics) -> bool:
    return (
        metrics.unsupported_claim_rate == 0.0
        and metrics.no_evidence_claim_rate <= 0.05
        and metrics.citation_accuracy >= 0.95
        and metrics.format_compliance >= 0.85
        and metrics.style_compliance >= 0.70
        and metrics.table_figure_coverage >= 0.70
    )


def metric_fail_class(metrics: Box3RealMetrics) -> str | None:
    """final gate 에서 첫 위반 사유를 reason code 로 반환(없으면 None)."""
    if metrics.unsupported_count > 0 or metrics.unsupported_claim_rate > 0.0:
        return BLOCK_FINAL_GATE_UNSUPPORTED
    # SSOT 임계(no_evidence_claim_rate ≤ 0.05)와 일치 — 허용 한도(예: 1/20=0.05) 내의
    # no_evidence 는 게이트를 통과시킨다. count>0 만으로 막으면 동일 모듈 임계보다 엄격해진다.
    if metrics.no_evidence_claim_rate > 0.05:
        return NEEDS_REVIEW_NO_EVIDENCE
    if metrics.citation_accuracy < 0.95:
        return CITATION_ACCURACY_BELOW_GATE
    if metrics.format_compliance < 0.85:
        return FORMAT_MATCH_BELOW_GATE
    if metrics.style_compliance < 0.70:
        return STYLE_MATCH_BELOW_GATE
    if metrics.table_figure_coverage < 0.70:
        return TABLE_FIGURE_COVERAGE_BELOW_GATE
    return None


# 박스 3 real 실제 켜기 v1.3 (2026-06-03) — MAINDEV enablement 5 모듈이 호출하는 3 함수.
# main 본진 Box3RealMetrics dataclass · EvidenceUnit.kind 와 시그니처 정합.
def compute_claim_metrics(
    claim_verdicts,
    *,
    format_compliance: float = 0.0,
    style_compliance: float = 0.0,
    evidence_units=None,
) -> Box3RealMetrics:
    verdicts = list(claim_verdicts)
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    supported = [v for v in factual if v.support_level == "supported"]
    unsupported = [v for v in factual if v.support_level == "unsupported"]
    no_evidence = [v for v in factual if v.support_level == "no_evidence"]
    factual_count = len(factual)
    citation_accuracy = (
        1.0
        if not supported
        else sum(1 for v in supported if v.evidence_digests) / len(supported)
    )
    if evidence_units:
        kinds = {unit.kind for unit in evidence_units}
        needed = {"table", "figure"}
        if kinds & needed:
            covered = 0
            for kind in needed:
                if kind not in kinds:
                    continue
                digests = {u.evidence_digest for u in evidence_units if u.kind == kind}
                if any(set(v.evidence_digests) & digests for v in supported):
                    covered += 1
            table_figure_coverage = covered / max(1, len(kinds & needed))
        else:
            table_figure_coverage = 1.0
    else:
        table_figure_coverage = 0.0
    return Box3RealMetrics(
        unsupported_claim_rate=0.0 if factual_count == 0 else len(unsupported) / factual_count,
        no_evidence_claim_rate=0.0 if factual_count == 0 else len(no_evidence) / factual_count,
        citation_accuracy=citation_accuracy,
        format_compliance=max(0.0, min(1.0, format_compliance)),
        style_compliance=max(0.0, min(1.0, style_compliance)),
        table_figure_coverage=max(0.0, min(1.0, table_figure_coverage)),
        factual_claim_count=factual_count,
        unsupported_count=len(unsupported),
        no_evidence_count=len(no_evidence),
        supported_count=len(supported),
    )


def estimate_format_compliance(draft_text: str) -> float:
    required = ["제목", "배경", "핵심 내용", "근거", "확인 필요", "최종 문안"]
    hits = sum(1 for item in required if f"{item}:" in draft_text)
    return hits / len(required)


def estimate_style_compliance(draft_text: str) -> float:
    forbidden = ["무조건", "반드시 법적으로 확정", "보장합니다", "책임 없습니다"]
    if any(term in draft_text for term in forbidden):
        return 0.0
    return 0.75
