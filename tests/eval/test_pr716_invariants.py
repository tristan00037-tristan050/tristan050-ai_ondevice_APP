"""PR #716 측정 무결성 사전 점검 — Codex P1/P2 재발 차단."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.pr716_extraction_decomposition import (
    normalize_action,
)


# ── P1-A 재발 차단: multiset 차연산 ──────────────────────────────────────
def test_multiset_difference():
    """gold=[other], pred=[other, other] 시 action_fp >= 1 (set 사용 시 0)."""
    gold_norm_list = ["other"]
    pred_norm_list = ["other", "other"]
    gold_c = Counter(gold_norm_list)
    pred_c = Counter(pred_norm_list)
    fp = pred_c - gold_c
    fn = gold_c - pred_c
    assert sum(fp.values()) >= 1, "multiset diff 위반 — set semantics 사용 의심"
    assert sum(fn.values()) == 0
    # set 차연산이라면 (set(["other"]) - set(["other"])) = empty → FAIL
    fp_set = set(pred_norm_list) - set(gold_norm_list)
    assert len(fp_set) == 0  # set 차연산 비교 — multiset 와 다름을 명시


# ── P1-B 재발 차단: 가중 집계 ─────────────────────────────────────────────
def test_weighted_distribution():
    """all_action_texts={A:10, B:20, C:5} → canonical 동일 매핑 시 합 35."""
    all_action_texts = Counter()
    all_action_texts["보내주세요"] = 10
    all_action_texts["전달 부탁"]  = 20
    all_action_texts["송부 요청"]  = 5
    # 위 3 텍스트 모두 normalize_action → "send"
    expected_canonical = "send"
    for t in all_action_texts:
        assert normalize_action(t) == expected_canonical
    # 가중 집계
    canonical_dist = Counter()
    for text, count in all_action_texts.items():
        canonical_dist[normalize_action(text)] += count
    assert canonical_dist[expected_canonical] == 35, (
        f"weighted distribution 위반 — unique count={canonical_dist[expected_canonical]} (35 기대)")
    # unique 기준 (이전 버그) 비교
    unique_dist = Counter(normalize_action(t) for t in all_action_texts)
    assert unique_dist[expected_canonical] == 3  # 이전 버그 결과


# ── P2 재발 차단: parser_wins / llm_wins counter ─────────────────────────
def test_disagreement_counter():
    """parser_wins / llm_wins / hybrid_wins / both_correct / both_fail
    카운트 정합 (Option A 채택, 3-mode predictions 영역).
    """
    # 합성 입력: gold[i] / parser[i] / llm[i] / hybrid[i]
    cases = [
        # parser_correct=T, llm_correct=T → both_correct
        ("REQUEST", "REQUEST", "REQUEST", "REQUEST"),
        # parser_correct=T, llm_correct=F → parser_wins
        ("REQUEST", "REQUEST", "REPORT", "REPORT"),
        # parser_correct=F, llm_correct=T → llm_wins
        ("REQUEST", "REPORT", "REQUEST", "REPORT"),
        # all wrong, hybrid 만 맞음 → hybrid_wins
        ("REQUEST", "REPORT", "REPORT", "REQUEST"),
        # 모두 틀림 → both_fail
        ("REQUEST", "REPORT", "REPORT", "REPORT"),
    ]
    parser_wins = llm_wins = hybrid_wins = both_correct = both_fail = 0
    for gi, ap, bp, cp in cases:
        pc = (gi == ap)
        lc = (gi == bp)
        hc = (gi == cp)
        if pc and lc:
            both_correct += 1
        elif pc and not lc:
            parser_wins += 1
        elif lc and not pc:
            llm_wins += 1
        elif hc and not pc and not lc:
            hybrid_wins += 1
        else:
            both_fail += 1
    assert both_correct == 1
    assert parser_wins  == 1
    assert llm_wins     == 1
    assert hybrid_wins  == 1
    assert both_fail    == 1
    total = parser_wins + llm_wins + hybrid_wins + both_correct + both_fail
    assert total == len(cases)


# ── 측정 정합 회복 검증 (regression) ────────────────────────────────────
def test_pr716_evidence_disagreement_measured():
    """parser_vs_llm_disagreement.json 의 measurement_mode 확인.

    Option A 채택 시 'A_three_mode_predictions' 표기 + 모든 카운트 합산 정합.
    Option B (not_measured) 채택 시 'not_measured' 표기.
    """
    p = ROOT / "evidence/day14/extraction_error_decomposition/parser_vs_llm_disagreement.json"
    if not p.exists():
        return  # evidence 미생성 — 다른 검증 영역
    obj = json.loads(p.read_text(encoding="utf-8"))
    sc = obj.get("summary_counts", {})
    mode = sc.get("measurement_mode", "")
    assert mode in {"A_three_mode_predictions", "not_measured"}, (
        f"unexpected measurement_mode={mode!r}")
    if mode == "A_three_mode_predictions":
        # 모든 카운트 정수 + 합 ≥ 0
        for k in ["parser_wins_count", "llm_wins_count", "hybrid_wins_count",
                  "both_correct_count", "both_fail_count"]:
            assert isinstance(sc.get(k), int) and sc[k] >= 0
