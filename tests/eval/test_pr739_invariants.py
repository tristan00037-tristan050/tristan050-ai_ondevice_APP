"""PR #739 Standard 12-B~K 통합 정착 sentinel — #1~#17."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day30/standard_12_b_to_k_통합_정착"

from scripts.eval.pr739_standard_12_b_to_k_consolidation import (  # noqa: E402
    ACTUAL_GITHUB_PR, GOVERNANCE_DIMENSIONS, LEGACY_HANDOFF_LABEL,
    REUSABLE_HELPERS, STANDARDS_12, _meta,
)


def _j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _md(name, base=OUT):
    return (base / name).read_text(encoding="utf-8")


# ── #1 Standard 12-B Quantitative Reversal Reporting ─────────────────────
def test_standard_12_b_quantitative_reversal_reporting():
    md = _md("quantitative_reversal_reporting_standard.md")
    assert "12-B" in md and "expected_vs_observed" in md
    assert "PR #726 H1" in md and "PR #730" in md


# ── #2 Standard 12-C 분류 계약 명세 ──────────────────────────────────────
def test_standard_12_c_분류_계약_명세():
    f = ROOT / "evidence/day25/metric_design_review/classification_contract_specification.md"
    assert f.exists()


# ── #3 Standard 12-D evidence 재현성 ─────────────────────────────────────
def test_standard_12_d_evidence_재현성():
    f = ROOT / "evidence/day25/metric_design_review/evidence_reproducibility_audit.md"
    assert f.exists()


# ── #4 Standard 12-E text-only guard 한계 ────────────────────────────────
def test_standard_12_e_text_only_guard_한계():
    md = _md("text_only_guard_limit_standard.md")
    assert "12-E" in md and "M-1" in md
    assert "표면형" in md


# ── #5 Standard 12-F regex case-sensitivity ──────────────────────────────
def test_standard_12_f_regex_case_sensitivity():
    f = ROOT / "evidence/day26/b2g_over_extraction_guard/regex_case_sensitivity_audit.md"
    assert f.exists()


# ── #6 Standard 12-G .gitignore evidence ─────────────────────────────────
def test_standard_12_g_gitignore_evidence():
    md = _md("gitignore_evidence_compliance_standard.md")
    assert "12-G" in md and "git add -f" in md


# ── #7 Standard 12-H proxy vs 권위 분리 ──────────────────────────────────
def test_standard_12_h_proxy_vs_권위_분리():
    md = _md("proxy_vs_authoritative_measurement_standard.md")
    assert "12-H" in md and "proxy" in md and "M-10" in md


# ── #8 Standard 12-I readiness gate integrity ────────────────────────────
def test_standard_12_i_readiness_gate_integrity():
    f = ROOT / "evidence/day27/internal_alpha_feedback/readiness_gate_integrity_audit.md"
    assert f.exists()


# ── #9 Standard 12-J dataset integrity coverage ──────────────────────────
def test_standard_12_j_dataset_integrity_coverage():
    f = ROOT / "evidence/day28/final_beta_readiness_measurement/dataset_integrity_coverage_audit.md"
    assert f.exists()


# ── #10 Standard 12-K metadata 무결성 (강화 안건 17) ────────────────────
def test_standard_12_k_metadata_무결성():
    md = _md("metadata_integrity_consolidated_standard.md")
    assert "12-K" in md and "actual_github_pr" in md and "legacy_handoff_label" in md


# ── #11 Standard 9 본질적 강화 정합 ──────────────────────────────────────
def test_standard_9_본질적_강화_정합():
    md = _md("standard_9_본질적_강화_완성.md")
    assert "duplicate" in md and "missing" in md
    assert "compute_coverage" in md


# ── #12 재사용 helper 3개 통합 정합 ──────────────────────────────────────
def test_reusable_helpers_3개_통합_정합():
    assert len(REUSABLE_HELPERS) == 3
    names = {h["name"] for h in REUSABLE_HELPERS}
    assert names == {"detect_duplicates", "compute_readiness", "compute_coverage"}
    md = _md("reusable_helpers_누적_audit.md")
    for n in names:
        assert n in md


# ── #13 거버넌스 안전망 14차원 정합 ──────────────────────────────────────
def test_거버넌스_안전망_14차원_정합():
    assert GOVERNANCE_DIMENSIONS == 14
    md = _md("governance_safety_net_14차원_definition.md")
    assert "14차원" in md and "13차원" in md
    idx = _j("standard_12_consolidation_index.json")
    assert idx["governance_dimensions"] == 14


# ── #14 거버넌스 안전망 자기 진화 사례 1+2 정량 ─────────────────────────
def test_거버넌스_안전망_자기_진화_사례_1_2_정량():
    md = _md("governance_self_evolution_patterns_audit.md")
    assert "사례 1" in md and "사례 2" in md
    assert "PR #734" in md and "PR #737" in md


# ── #15 main 측정값 변동 0 (통합 PR 본질) ───────────────────────────────
def test_main_측정값_변동_0():
    ba = _j("before_after_main_metrics.json")
    for row in ba["comparison"]:
        assert row["before"] == row["after"]
        assert row["delta"] == 0.0
    assert ba["safety_6_delta_zero"] is True


# ── #16 metric contract v2.0.0 유지 (자문 6차 M-8) ──────────────────────
def test_metric_contract_v2_0_0_유지():
    d = _j("policy_drift_assessment.json")
    assert d["contract_version"] == "2.0.0"
    assert d["contract_version_changed"] is False
    assert d["drift_rate"] == 0.0


# ── #17 PR 번호 정합성 메타데이터 정합 (강화 안건 17) ───────────────────
def test_PR_번호_정합성_메타데이터_정합():
    m = _meta()
    assert m["actual_github_pr"] == ACTUAL_GITHUB_PR
    assert m["legacy_handoff_label"] == LEGACY_HANDOFF_LABEL
    assert m["source_pr"] == ACTUAL_GITHUB_PR
    idx = _j("standard_12_consolidation_index.json")
    assert idx["actual_github_pr"] == ACTUAL_GITHUB_PR
    assert idx["standards_count"] == len(STANDARDS_12) == 10
