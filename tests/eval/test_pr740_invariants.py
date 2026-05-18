"""PR #740 Standard 12-L 통합 정착 sentinel — #23~#29.

번호는 PR #739 #1~#22 에 이어짐 (강화 안건 18~23 통합 정착).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day31/standard_12_l_consolidation"

from scripts.eval.pr740_standard_12_l_consolidation import (  # noqa: E402
    ACTUAL_GITHUB_PR, ENHANCEMENT_AGENDA_18_23, GOVERNANCE_DIMENSIONS,
    SELF_EVOLUTION_CASES, STANDARDS_12_COUNT,
)

FORBIDDEN = re.compile(
    r"production candidate approved|PRODUCTION_CANDIDATE_PASS|release ready|"
    r"beta ready|external beta ready|auto_apply_accuracy|card1_gold_v1|"
    r"BUTLER_INTEGRATION_READY|PROCEED|최종 승인")


def _j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _md(name):
    return (OUT / name).read_text(encoding="utf-8")


# ── #23 Standard 12-L 통합 정착 ──────────────────────────────────────────
def test_standard_12_L_integration():
    md = _md("standard_12_L_privacy_measurement_governance_integrity"
             "_consolidated.md")
    assert "12-L" in md and "Privacy" in md
    assert len(ENHANCEMENT_AGENDA_18_23) == 6
    idx = _j("standard_12_l_consolidation_index.json")
    assert idx["standards_count"] == STANDARDS_12_COUNT == 11


# ── #24 강화 안건 18~23 통합 매핑 ────────────────────────────────────────
def test_enhancement_agenda_18_to_23_mapping():
    j = _j("enhancement_agenda_18_to_23_consolidation.json")
    assert j["agenda_count"] == 6
    ids = {a["id"] for a in j["agenda"]}
    assert ids == {18, 19, 20, 21, 22, 23}
    assert j["total_enhancement_agenda"] == 23


# ── #25 자기 진화 사례 3+4 ──────────────────────────────────────────────
def test_self_evolution_cases_3_and_4():
    assert len(SELF_EVOLUTION_CASES) == 4
    md = _md("governance_self_evolution_patterns_audit.md")
    assert "사례 3" in md and "사례 4" in md
    assert "PR #738" in md and "PR #739" in md
    # Codex 봇 3 + 재검토팀 2
    cb = sum(1 for c in SELF_EVOLUTION_CASES if "Codex" in c["discovered_by"])
    assert cb == 3


# ── #26 거버넌스 안전망 15차원 ───────────────────────────────────────────
def test_governance_dimensions_15():
    assert GOVERNANCE_DIMENSIONS == 15
    md = _md("governance_safety_net_15차원_definition.md")
    assert "15차원" in md and "14차원" in md
    idx = _j("standard_12_l_consolidation_index.json")
    assert idx["governance_dimensions"] == 15


# ── #27 인계 박스 작성 표준 10항목 ──────────────────────────────────────
def test_handoff_box_authoring_standard_10_items():
    md = _md("handoff_box_authoring_standard_10_items.md")
    # 10항목 행 (표) 존재
    assert all(f"| {i} |" in md for i in range(1, 11))
    idx = _j("standard_12_l_consolidation_index.json")
    assert idx["handoff_box_standard_items"] == 10


# ── #28 measurement/governance integrity 상속 (PR #739 helper 재사용) ────
def test_measurement_governance_integrity_inheritance():
    ba = _j("before_after_main_metrics.json")
    for row in ba["comparison"]:
        assert row["source"] == "authoritative_evidence"
        assert abs(row["delta"] - (row["after"] - row["before"])) < 1e-9
    pd = _j("policy_drift_assessment.json")
    assert pd["source"] == "contract_input_comparison"
    assert pd["samples_compared"] > 0


# ── #29 forbidden grep 0 ─────────────────────────────────────────────────
def test_forbidden_grep_0():
    for f in OUT.glob("*"):
        text = f.read_text(encoding="utf-8")
        for ln in text.splitlines():
            if FORBIDDEN.search(ln) and "금지" not in ln:
                raise AssertionError(f"forbidden 패턴: {f.name} — {ln[:60]}")
    # 메타데이터 정합
    idx = _j("standard_12_l_consolidation_index.json")
    assert idx["actual_github_pr"] == ACTUAL_GITHUB_PR
