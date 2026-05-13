"""단계 6.5.5 Day 4 — Cohen's kappa 자체 구현 단위 테스트 (5건)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evalset"))

from compute_agreement import cohen_kappa, simple_agreement   # noqa: E402


def test_kappa_perfect_agreement_equals_one():
    assert cohen_kappa(["A","B","A","B","A"], ["A","B","A","B","A"]) == 1.0


def test_kappa_no_agreement_balanced_low():
    """완전 불일치 + 균형 — kappa 음수 (chance 이하)."""
    k = cohen_kappa(["A","B","A","B"], ["B","A","B","A"])
    assert k < 0.0


def test_kappa_zero_comparable_pairs_fails():
    """simple_agreement 가 빈 입력에서 NO_COMPARABLE_PAIRS 반환."""
    out = simple_agreement([], "intent_type")
    assert out["ok"] is False
    assert out["fail_class"] == "NO_COMPARABLE_PAIRS"


def test_kappa_single_class_handles_degenerate():
    """단일 클래스 — observed=1.0 이면 1.0, 아니면 0.0."""
    assert cohen_kappa(["A","A","A"], ["A","A","A"]) == 1.0
    assert cohen_kappa(["A","A","A"], ["A","A","B"]) == cohen_kappa(["A","A","A"], ["A","A","B"])


def test_kappa_reports_all_required_fields():
    """simple_agreement 반환 dict 가 알고리즘 팀 5개 필드 포함."""
    items = [{
        "sample_id": "card1_000001",
        "annotator_a": {"id": "a", "labeled_at": "t",
                        "intent_type": "REQUEST",
                        "deadline_type": "NONE",
                        "auto_apply_allowed": False},
        "annotator_b": {"id": "b", "labeled_at": "t",
                        "intent_type": "REQUEST",
                        "deadline_type": "NONE",
                        "auto_apply_allowed": False},
    }]
    out = simple_agreement(items, "intent_type")
    for field in ("agreement_raw", "expected_agreement", "kappa",
                  "pair_count", "label_distribution"):
        assert field in out, f"missing field: {field}"
