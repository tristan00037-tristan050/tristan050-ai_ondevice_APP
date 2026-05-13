"""단계 6.5.5 Day 4 — PR #704 P1-B 정정 효과 실증 (2건).

G15 (check_label_consistency.py) 가 adjudicated + auto_apply_allowed=true 의
evidence consistency 도 검사하는지 실제 데이터로 확인.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "evalset"
PY      = sys.executable
GATE    = SCRIPTS / "check_label_consistency.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(GATE), *args], capture_output=True, text=True)


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


def _adjudicated_item(auto_apply: bool, evidence: str):
    return {
        "sample_id":              "card1_999100",
        "text":                   "회의록 보내주세요",
        "text_redacted":          None,
        "raw_digest16":           "sha256:00000000000000a0",
        "source":                 "synthetic_gold",
        "intent_type":            "REQUEST",
        "deadline_type":          "NONE",
        "deadline_is_actionable": False,
        "slice_tags":             [],
        "action_required":        True,
        "answer_required":        True,
        "auto_apply_allowed":     auto_apply,
        "label_status":           "adjudicated",
        "adjudicator":            {"id": "adj1", "decision": "approved",
                                   "reviewed_at": "2026-05-13T11:00:00Z"},
        "final_gold": {
            "intent_type":         "REQUEST",
            "deadline_type":       "NONE",
            "auto_apply_allowed":  auto_apply,
            "deadline":            None,
            "actions":             [],
            "materials":           [],
            "finalized_at":        "2026-05-13T11:30:00Z",
        },
        "gold": {
            "intent_type": "REQUEST",
            "deadline":    None,
            "materials":   [],
            "actions":     [{"action_text": "보내기", "evidence": evidence}],
        },
    }


def test_adjudicated_auto_apply_evidence_inconsistency_blocked(tmp_path):
    """adjudicated + auto_apply_allowed=true + evidence 가 text 에 없음 → G15 Block.

    PR #704 P1-B 정정 후 adjudicated 도 G15 검사 — 본 테스트가 정정 효과 실증.
    """
    item = _adjudicated_item(auto_apply=True, evidence="원문에 없는 문장")
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "EVIDENCE_INCONSISTENT_WHEN_APPROVED"


def test_adjudicated_auto_apply_evidence_consistency_passes(tmp_path):
    """adjudicated + auto_apply_allowed=true + evidence 일치 → PASS."""
    item = _adjudicated_item(auto_apply=True, evidence="회의록 보내주세요")
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
