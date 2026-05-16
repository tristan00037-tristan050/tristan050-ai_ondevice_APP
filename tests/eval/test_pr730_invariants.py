"""PR #730 Branch C-lite gold/action unit review sentinel — #1~#5."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day24/branch_c_lite_action_unit_review"

from scripts.eval.pr730_branch_c_lite_review import detect_duplicates  # noqa: E402

VALID_SUBTYPES = {
    "A1_action_unit_mismatch",
    "A2_canonical_granularity_mismatch",
    "A3_product_equivalent_prediction",
    "A4_true_model_error",
}
JUDGMENT_FIELDS = ["gold_over_granular", "pred_product_valid",
                   "both_valid_diff_unit", "label_too_narrow",
                   "user_value_unit"]


def _review():
    return json.loads((OUT / "mixed_a_30_review.json").read_text(encoding="utf-8"))


def _dump():
    return json.loads((OUT / "mixed_a_67_full_dump.json").read_text(encoding="utf-8"))


# ── #1 MIXED-A 30건 sample size invariant ────────────────────────────────
def test_mixed_a_30_sample_size_invariant():
    dump = _dump()
    assert dump["mixed_a_total"] == 67
    assert len(dump["rows"]) == 67
    rev = _review()
    assert rev["sample_size"] == 30
    assert len(rev["reviews"]) == 30
    # selected 30 은 67 의 부분집합 + 중복 없음
    dump_ids = {r["sample_id"] for r in dump["rows"]}
    rev_ids = [r["sample_id"] for r in rev["reviews"]]
    assert len(rev_ids) == len(set(rev_ids)), "30건 sample 중복"
    assert set(rev_ids) <= dump_ids


# ── #2 4 subtype 분류 완전성 ─────────────────────────────────────────────
def test_subtype_classification_complete():
    rev = _review()
    for r in rev["reviews"]:
        assert r["subtype"] in VALID_SUBTYPES, f"미정의 subtype: {r['subtype']}"
    align = json.loads(
        (OUT / "action_unit_alignment_report.json").read_text(encoding="utf-8"))
    # subtype 분포 합 == 30
    assert sum(align["subtype_distribution"].values()) == 30


# ── #3 5종 판단 필드 누락 없음 ───────────────────────────────────────────
def test_5_judgment_fields_required():
    rev = _review()
    assert rev["judgment_fields"] == JUDGMENT_FIELDS
    for r in rev["reviews"]:
        for fld in JUDGMENT_FIELDS:
            assert fld in r["judgments"], f"{r['sample_id']} 판단 누락: {fld}"
        # user_value_unit 은 정의된 값만
        assert r["judgments"]["user_value_unit"] in {"gold", "pred", "both"}


# ── #4 Branch C 진입 기준 정합 (A1 >= 8/30) ──────────────────────────────
def test_branch_c_entry_threshold_정합():
    risk = json.loads(
        (OUT / "gold_granularity_risk_report.json").read_text(encoding="utf-8"))
    rev = _review()
    a1 = sum(1 for r in rev["reviews"]
             if r["subtype"] == "A1_action_unit_mismatch")
    assert risk["action_unit_mismatch_count"] == a1
    assert risk["branch_c_entry_threshold"] == 8
    # 권고 플래그가 임계값 산식과 정합
    assert risk["branch_c_entry_recommended"] == (a1 >= 8)


# ── #5 gold / normalized_action label 미수정 ─────────────────────────────
def test_no_gold_modification():
    """full_dump 의 gold 가 live dataset gold 와 동일 — 수정 0건."""
    dataset = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
    live = {}
    for line in dataset.open(encoding="utf-8"):
        if line.strip():
            it = json.loads(line)
            live[it["sample_id"]] = (it.get("gold") or {}).get("actions") or []
    dump = _dump()
    for row in dump["rows"]:
        sid = row["sample_id"]
        assert row["gold_actions"] == live[sid], (
            f"{sid} gold_actions 가 live dataset 과 불일치 — gold 수정 의심")
        assert row["gold_action_count"] == len(live[sid])


# ── #6 MIXED-A source rows duplicate fail-closed (Codex P1-A) ────────────
def test_source_mixed_rows_duplicate_fail_closed():
    dups, excess = detect_duplicates(["a", "b", "b", "c", "b"])
    assert dups == ["b"]
    assert excess == 2   # b 가 3회 → 초과 2
    # 실제 evidence: MIXED-A source 67건 중복 0건
    cov = json.loads((OUT / "coverage_report.json").read_text(encoding="utf-8"))
    assert cov["gold_duplicate_count"] == 0
    assert cov["source_sample_ids_count"] == cov["source_sample_ids_unique_count"]


# ── #7 predictions duplicate fail-closed (Codex P1-B) ────────────────────
def test_predictions_duplicate_fail_closed():
    dups, excess = detect_duplicates(["s1", "s2", "s1", "s1"])
    assert dups == ["s1"]
    assert excess == 2
    # 실제 evidence: predictions 중복 0건, raw 기준 산출 (고정값 0 아님)
    cov = json.loads((OUT / "coverage_report.json").read_text(encoding="utf-8"))
    assert cov["prediction_duplicate_count"] == 0
    assert cov["prediction_sample_ids_count"] == \
        cov["prediction_sample_ids_unique_count"]


# ── #8 duplicate 0건 정상 fixture 통과 ───────────────────────────────────
def test_no_duplicate_normal_fixture_passes():
    dups, excess = detect_duplicates(["x", "y", "z"])
    assert dups == []
    assert excess == 0
    # 빈 리스트도 정상
    assert detect_duplicates([]) == ([], 0)
    # 실제 evidence coverage fail_class 정합 (정상 통과)
    cov = json.loads((OUT / "coverage_report.json").read_text(encoding="utf-8"))
    assert cov["fail_class"] is None
    assert cov["expected_samples"] == 67
    assert cov["measured_samples"] == 67
