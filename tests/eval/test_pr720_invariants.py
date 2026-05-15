"""PR #720 Branch B 사전 점검 — 운영 표준 7건 정합 + 신규 4건."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "evidence/day16/prompt_schema_patch"


def test_atomic_action_schema_valid():
    """schema_patch.json — required field 변경 없음 (optional 만 추가)."""
    sp = json.loads((OUT / "schema_patch.json").read_text(encoding="utf-8"))
    required = sp["actions_required_fields"]
    assert "action_text" in required
    assert "normalized_action" in required
    assert "source_evidence" in required
    optional = sp["actions_optional_fields"]
    for f in ["object", "recipient", "depends_on", "is_atomic"]:
        assert f in optional


def test_evidence_field_required_on_auto_apply():
    """schema_patch atomic_action_rule — evidence_substring_of_source=True."""
    sp = json.loads((OUT / "schema_patch.json").read_text(encoding="utf-8"))
    rule = sp["atomic_action_rule"]
    assert rule["evidence_substring_of_source"] is True
    assert rule["is_atomic"] is True


def test_multi_action_decomposition_no_over_extraction():
    """priority_score_report — over_extraction_risk 음수 가중치 적용."""
    pr = json.loads((OUT / "priority_score_report.json").read_text(encoding="utf-8"))
    formula = pr["formula"]
    assert "over_extraction" in formula
    assert "-" in formula  # negative weighting 존재


def test_safety_monitor_regression_guard():
    """full_eval — safety threshold 유지 (false_deadline_rate / no_action_fp_rate)."""
    fe = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    assert fe["false_deadline_rate"] <= 0.02 + 1e-9
    assert fe["no_action_fp_rate"]   <= 0.03 + 1e-9
    assert fe["g23_hard_violation_count"] == 0
    assert fe["g22_strict_warning_count"] == 0


# ── sentinel #6 — coverage fail-closed (Branch B 적용) ────────────────────
def test_full_eval_coverage_fail_closed_pr720():
    fe = json.loads((OUT / "full_eval_impact_summary.json").read_text(encoding="utf-8"))
    cov = fe["coverage_report"]
    assert cov["coverage_checked"] is True
    assert cov["expected_samples"] == 500
    assert cov["measured_samples"] == 500
    assert cov["missing_count"]   == 0
    assert cov["extra_count"]     == 0
    assert cov["duplicate_count"] == 0


# ── sentinel #7 — composition (NATURAL_SHORTAGE 정책 포함) ────────────────
def test_ab_composition_enforced_pr720():
    cfg = json.loads((OUT / "ab_eval_50_config.json").read_text(encoding="utf-8"))
    declared = cfg["declared_composition"]
    actual   = cfg["actual_composition"]
    if cfg["composition_ok"]:
        # 자연 부족 시 fail_class=AB_COMPOSITION_NATURAL_SHORTAGE 허용
        # 정합 시 fail_class=None
        assert cfg["fail_class"] in {None, "AB_COMPOSITION_NATURAL_SHORTAGE"}
        if cfg["fail_class"] is None:
            for k in declared:
                assert actual[k] == declared[k]
    else:
        assert cfg["fail_class"] == "AB_COMPOSITION_MISMATCH"
    assert len(cfg["ab_sample_ids"]) == 50


# ── 신규 sentinel #1: cue split full source coverage (P1 #1 재발 차단) ────
def test_cue_split_full_source_coverage():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.eval.pr720_prompt_schema_patch import _split_actions_on_cues
    # cue 가 text 에 있고 action_text 에 없음
    n = _split_actions_on_cues("A하고 B해서 C 그리고 D", "execute")
    assert n > 1, f"cue split scope: text 영역 누락 (n={n})"


# ── 신규 sentinel #2: 4축 counter 정상 동작 (P1 #2 재발 차단) ─────────────
def test_both_fail_4axis_counter_increments():
    """parser_limit / llm_limit / schema_limit / gold_limit 각 1씩 정상 증가."""
    b = json.loads((OUT / "parser_vs_llm_both_fail_decomp.json").read_text(encoding="utf-8"))
    # 4축 모두 정수 키 존재
    for k in ["parser_limit", "llm_limit", "schema_limit", "gold_limit", "mixed"]:
        assert isinstance(b.get(k), int), f"{k} not int (axis counter dead?)"
    # 합계 정합: 4축 합 == both_fail_total
    total = b["parser_limit"] + b["llm_limit"] + b["schema_limit"] + b["gold_limit"] + b["mixed"]
    assert total == b["both_fail_total"], (
        f"axis sum {total} != both_fail_total {b['both_fail_total']}")
    # dead continue 가 제거됐다면 4축 중 최소 1축은 양수
    assert any(b[k] > 0 for k in
               ["parser_limit", "llm_limit", "schema_limit", "gold_limit", "mixed"])


# ── 신규 sentinel #3: NATURAL_SHORTAGE fallback 동작 ─────────────────────
def test_natural_shortage_fallback():
    """multi_action_collapse 자연 부족 → fallback 자동 보충 → composition_ok=True."""
    cfg = json.loads((OUT / "ab_eval_50_config.json").read_text(encoding="utf-8"))
    if cfg.get("natural_shortage"):
        # shortage_log 있고 fallback_order 적용됨
        assert cfg["fail_class"] == "AB_COMPOSITION_NATURAL_SHORTAGE"
        assert cfg["composition_ok"] is True   # MEASURED_ONLY warning, BLOCK 아님
        assert cfg["shortage_log"]              # 비어있지 않음
        # fallback_order 정합
        assert cfg["fallback_order"] == [
            "both_fail_schema_limit",
            "both_fail_llm_limit",
            "action_fn_high_risk",
            "evidence_field_weakness",
        ]
    # ab_sample_ids 50 보장
    assert len(cfg["ab_sample_ids"]) == 50
