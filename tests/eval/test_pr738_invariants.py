"""PR #738 Residual A4 9 Review Protocol sentinel — #1~#17.

actual_github_pr 는 gh pr create 후 확정 (강화 안건 17 정합).
#15~#17 — Privacy meta-only (강화 안건 18, Codex P1 정정).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day30/residual_a4_9_review_protocol"

from scripts.eval.pr738_residual_a4_9_review_protocol import (  # noqa: E402
    ACTUAL_GITHUB_PR, LEGACY_HANDOFF_LABEL, _meta, classify_residual,
    utterance_digest,
)


def _j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _md(name):
    return (OUT / name).read_text(encoding="utf-8")


# ── #1 잔여 A4 9건 본질 분석 정합 ────────────────────────────────────────
def test_residual_a4_9_본질_분석_정합():
    j = _j("residual_a4_9_본질_분석.json")
    assert j["residual_a4_count"] == 9
    assert len(j["rows"]) == 9
    dist = j["surface_form_distribution"]
    assert dist["polite_request_surface_form"] == 7
    assert dist["intent_to_report_surface_form"] == 2


# ── #2 표면형 ambiguous case 재정의 (자문 6차 M-2) ──────────────────────
def test_표면형_ambiguous_case_재정의():
    j = _j("residual_a4_9_본질_분석.json")
    assert "surface-form ambiguous" in j["case_redefinition_M2"]
    assert j["text_only_separable"] is False
    # classify_residual 결정적
    assert classify_residual("보고서 검토 부탁드립니다") == "polite_request_surface_form"
    assert classify_residual("결과 정리 후 보고드리려고 합니다") == \
        "intent_to_report_surface_form"


# ── #3 평가 protocol 분리 정합 ──────────────────────────────────────────
def test_평가_protocol_분리_정합():
    md = _md("evaluation_protocol_separation.md")
    assert "FP 로 유지" in md and "gold/contract review path" in md


# ── #4 Internal Alpha feedback target 지정 (자문 6차 M-5) ───────────────
def test_internal_alpha_feedback_target_지정():
    md = _md("internal_alpha_feedback_target.md")
    for cat in ["useful", "irrelevant", "unsafe", "needs_edit"]:
        assert cat in md
    assert "M-5" in md


# ── #5 semantic-aware guard v0 허용 형태 (자문 6차 §5/M-7) ──────────────
def test_semantic_aware_guard_v0_허용_형태():
    md = _md("semantic_aware_guard_v0_candidate.md")
    assert "post-hoc" in md and "warning" in md and "low_confidence" in md


# ── #6 semantic-aware guard 절대 금지 형태 (자문 6차 §12) ───────────────
def test_semantic_aware_guard_절대_금지_형태():
    md = _md("semantic_aware_guard_v0_candidate.md")
    assert "LoRA" in md and "금지" in md
    assert "prompt recall" in md


# ── #7 metric contract v2.1.0 즉시 bump 0 (자문 6차 M-8) ────────────────
def test_metric_contract_v2_1_0_즉시_bump_0():
    md = _md("metric_contract_v2_1_0_candidate.md")
    assert "즉시" in md and "bump" in md
    d = _j("policy_drift_assessment.json")
    assert d["contract_version"] == "2.0.0"
    assert d["contract_version_changed"] is False


# ── #8 metric contract v2.1.0 후보 명세 (M-8 후보) ──────────────────────
def test_metric_contract_v2_1_0_후보_명세():
    j = _j("residual_a4_9_metric_연동_명세.json")
    for m in ["manual_suggestion_precision", "suggestion_usefulness_rate",
              "unsafe_suggestion_rate", "edit_required_rate"]:
        assert m in j["layer2_candidate_metrics"]


# ── #9 text-only guard 추가 강화 0 (자문 6차 M-1) ───────────────────────
def test_text_only_guard_추가_강화_0():
    md = _md("text_only_guard_한계_정량_확정.md")
    assert "M-1" in md and "금지" in md
    assert "정량 확정" in md


# ── #10 gold label 수정 0 (자문 6차 M-3) ────────────────────────────────
def test_gold_label_수정_0():
    md = _md("residual_a4_9_review_protocol.md")
    assert "gold label 수정 절대 금지" in md or "gold/label 수정 0" in md


# ── #11 main 측정값 변동 0 ──────────────────────────────────────────────
def test_main_측정값_변동_0():
    ba = _j("before_after_main_metrics.json")
    for row in ba["comparison"]:
        assert row["before"] == row["after"]
        assert row["delta"] == 0.0
    assert ba["safety_6_delta_zero"] is True


# ── #12 metric contract v2.0.0 유지 (자문 6차 M-8) ──────────────────────
def test_metric_contract_v2_0_0_유지():
    d = _j("policy_drift_assessment.json")
    assert d["contract_version"] == "2.0.0"
    assert d["drift_rate"] == 0.0


# ── #13 auto_apply OFF 절대 준수 (자문 6차 M-14) ────────────────────────
def test_auto_apply_off_절대_준수():
    md = _md("semantic_aware_guard_v0_candidate.md")
    assert "auto_apply OFF" in md


# ── #14 PR 번호 정합성 메타데이터 정합 (강화 안건 17) ───────────────────
def test_PR_번호_정합성_메타데이터_정합():
    m = _meta()
    assert m["actual_github_pr"] == ACTUAL_GITHUB_PR
    assert m["legacy_handoff_label"] == LEGACY_HANDOFF_LABEL
    assert m["source_pr"] == ACTUAL_GITHUB_PR
    # evidence 에 actual_github_pr 기록
    j = _j("residual_a4_9_본질_분석.json")
    assert j["actual_github_pr"] == ACTUAL_GITHUB_PR
    assert j["legacy_handoff_label"] == LEGACY_HANDOFF_LABEL


# ── #15 rows 내 원문 utterance 키 부재 (Privacy meta-only, Codex P1) ─────
def test_rows_내_text_키_부재():
    """원문 utterance 키 부재 — Butler 지침서 §7 / AGENTS.md 원문0 정합."""
    j = _j("residual_a4_9_본질_분석.json")
    forbidden = {"text", "raw_text", "utterance", "raw_utterance",
                 "original_text"}
    for row in j["rows"]:
        leak = set(row.keys()) & forbidden
        assert leak == set(), f"Privacy 결함: {leak} 키 발견"


# ── #16 meta-only 필드만 정합 (강화 안건 18) ────────────────────────────
def test_meta_only_정합():
    j = _j("residual_a4_9_본질_분석.json")
    allowed = {"sample_id", "surface_form", "gold_intent",
               "utterance_digest", "text_len", "redaction_status"}
    for row in j["rows"]:
        assert set(row.keys()) <= allowed, f"비허용 키: {set(row.keys()) - allowed}"
        assert row["redaction_status"] == "meta_only"


# ── #17 utterance_digest sha256 16자 정합 ────────────────────────────────
def test_utterance_digest_정합():
    pat = re.compile(r"^[a-f0-9]{16}$")
    j = _j("residual_a4_9_본질_분석.json")
    for row in j["rows"]:
        assert pat.match(row["utterance_digest"]), row["utterance_digest"]
    # 함수 결정성
    assert utterance_digest("회신 부탁드립니다") == utterance_digest("회신 부탁드립니다")
    assert pat.match(utterance_digest("test"))
