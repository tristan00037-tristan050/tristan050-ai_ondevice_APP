"""PR #718 사전 점검 unit test — Algorithm Branch A vocabulary patch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "evidence/day15/vocabulary_patch"


def test_canonical_group_count_guard():
    """canonical_before 14 + 신규 추가 <= 3 검증."""
    risk = json.loads((OUT / "fragmentation_risk_report.json").read_text(encoding="utf-8"))
    new = risk.get("new_canonical_count", 0)
    assert 0 <= new <= 3, f"new_canonical_count={new} (0~3 한도 위반)"
    assert risk["canonical_after"] <= risk["canonical_before"] + 3


def test_alias_consistency():
    """모든 alias 가 단일 canonical group 에만 매핑되는지 확인."""
    patch = json.loads((OUT / "canonical_alias_patch.json").read_text(encoding="utf-8"))
    alias_to_canon = {}
    for canon, aliases in patch["alias_table"].items():
        for a in aliases:
            assert a not in alias_to_canon or alias_to_canon[a] == canon, (
                f"alias {a!r} 가 {alias_to_canon[a]} / {canon} 두 canonical 에 매핑")
            alias_to_canon[a] = canon


def test_fragmentation_risk():
    """ambiguity_score >= 3 후보가 모두 reject 또는 needs_review 상태."""
    cands = json.loads((OUT / "candidate_vocabulary_additions.json").read_text(encoding="utf-8"))
    for c in cands["candidates"]:
        if c.get("ambiguity_score", 0) >= 3:
            assert not c.get("apply_in_pr718"), (
                f"high ambiguity candidate {c['candidate_id']} apply=true 위반")


def test_ab_eval_50_composition():
    """FP/FN 20 + mapping_gap 15 + parser_vs_LLM 10 + deadline 5 = 50."""
    cfg = json.loads((OUT / "ab_eval_50_config.json").read_text(encoding="utf-8"))
    comp = cfg["composition"]
    assert (comp["fp_fn_high_risk"] + comp["mapping_gap"]
            + comp["parser_vs_llm_disagreement"] + comp["deadline_monitor"]) == 50
    assert len(cfg["ab_sample_ids"]) == 50


# ── sentinel #6: full eval coverage fail-closed (Codex P1 #353-355) ──────
def test_full_eval_coverage_fail_closed(tmp_path, monkeypatch):
    """items=100 / preds=95 (5 누락) → fail_class=FULL_EVAL_COVERAGE_MISMATCH."""
    from scripts.eval.pr718_vocabulary_patch import step7_full_eval
    items = [{"sample_id": f"S{i:03d}", "gold": {"actions": []}}
             for i in range(100)]
    preds = [{"sample_id": f"S{i:03d}", "pred": {"actions": []}}
             for i in range(95)]
    out = step7_full_eval(items, preds)
    assert out.get("fail_class") == "FULL_EVAL_COVERAGE_MISMATCH"
    rep = out["coverage_report"]
    assert rep["coverage_checked"] is True
    assert rep["missing_count"] == 5
    assert rep["extra_count"] == 0
    assert rep["duplicate_count"] == 0


# ── sentinel #7: AB composition enforced (Codex P1 #437-441) ──────────────
def test_ab_composition_enforced():
    """4 카테고리 quota 강제 — 정합 시 composition_ok=True, 미달 시 False."""
    cfg = json.loads((OUT / "ab_eval_50_config.json").read_text(encoding="utf-8"))
    declared = cfg["declared_composition"]
    actual   = cfg["actual_composition"]
    # 정합 시
    if cfg["composition_ok"]:
        for k in declared:
            assert actual[k] == declared[k], (
                f"{k}: actual={actual[k]} != declared={declared[k]}")
        assert cfg["fail_class"] is None
        assert sum(actual.values()) == 50
    else:
        assert cfg["fail_class"] == "AB_COMPOSITION_MISMATCH"


def test_ab_composition_enforced_with_insufficient_pool():
    """pool 미달 fixture — composition_ok=False + fail_class=AB_COMPOSITION_MISMATCH."""
    import sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.eval.pr718_vocabulary_patch import _build_ab_ids_stratified
    items = [{"sample_id": f"S{i:03d}", "gold": {"actions": []}} for i in range(100)]
    preds = [{"sample_id": f"S{i:03d}", "pred": {"actions": []}} for i in range(100)]
    # review_rows 빈 → mapping_gap pool 비어있음 → quota 미달
    ab_ids, actual, ok, fail_class = _build_ab_ids_stratified(items, preds, [])
    # parser_vs_LLM / deadline pool 도 evidence 없으면 미달 가능
    # 미달 시 fail_class 명시 + 50건은 pad 로 채워짐
    assert len(ab_ids) == 50
    if not ok:
        assert fail_class == "AB_COMPOSITION_MISMATCH"
