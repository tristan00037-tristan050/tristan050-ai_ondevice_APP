"""단계 6.5.5 Day 4~5 — Gate G17~G21 단위 테스트."""
from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "evalset"
PY      = sys.executable
GATE    = SCRIPTS / "check_adjudication_consistency.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(GATE), *args], capture_output=True, text=True)


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


def _base_adjudicated_item(**overrides):
    item = {
        "sample_id":              "card1_999001",
        "text":                   "회의록 보내주세요",
        "text_redacted":          None,
        "raw_digest16":           "sha256:0000000000000099",
        "source":                 "synthetic_gold",
        "intent_type":            "REQUEST",
        "deadline_type":          "NONE",
        "deadline_is_actionable": False,
        "slice_tags":             [],
        "action_required":        True,
        "answer_required":        True,
        "auto_apply_allowed":     False,
        "label_status":           "adjudicated",
        "adjudicator":            {"id": "adj1", "decision": "approved",
                                   "reviewed_at": "2026-05-13T11:00:00Z"},
        "final_gold": {
            "intent_type":         "REQUEST",
            "deadline_type":       "NONE",
            "auto_apply_allowed":  False,
            "deadline":            None,
            "actions":             [],
            "materials":           [],
            "finalized_at":        "2026-05-13T11:30:00Z",
        },
        "gold": {
            "intent_type":  "REQUEST",
            "deadline":     None,
            "materials":    [],
            "actions":      [{"action_text": "보내기", "evidence": "회의록 보내주세요"}],
        },
    }
    item.update(overrides)
    return item


def test_g17_adjudicated_requires_adjudicator(tmp_path):
    item = _base_adjudicated_item()
    del item["adjudicator"]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    assert "ADJUDICATOR_MISSING" in res.stdout


def test_g17_gold_v1_requires_adjudicator(tmp_path):
    item = _base_adjudicated_item(label_status="gold_v1")
    del item["adjudicator"]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1


def test_g18_adjudicated_requires_final_gold(tmp_path):
    item = _base_adjudicated_item()
    del item["final_gold"]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    assert "FINAL_GOLD_MISSING" in res.stdout


def test_g19_disagreement_requires_resolution(tmp_path):
    item = _base_adjudicated_item()
    item["annotator_a"] = {"id": "a", "intent_type": "REQUEST",
                            "deadline_type": "NONE",
                            "auto_apply_allowed": False,
                            "labeled_at": "t"}
    item["annotator_b"] = {"id": "b", "intent_type": "REPORT",
                            "deadline_type": "NONE",
                            "auto_apply_allowed": False,
                            "labeled_at": "t"}
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    assert "DISAGREEMENT_RESOLUTION" in res.stdout


def test_g20_auto_apply_requires_reasoning(tmp_path):
    item = _base_adjudicated_item(auto_apply_allowed=True)
    item["final_gold"]["auto_apply_allowed"] = True
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    assert "REASONING" in res.stdout


def test_g20_final_gold_auto_apply_triggers_reasoning_check(tmp_path):
    """top-level=false, final_gold=true → reasoning 필수 (P2-B)."""
    item = _base_adjudicated_item(auto_apply_allowed=False)
    item["final_gold"]["auto_apply_allowed"] = True
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "AUTO_APPLY_REASONING_MISSING"


def test_g21_top_vs_final_gold_mismatch(tmp_path):
    """top=true, final=false → AUTO_APPLY_MISMATCH (P2-C)."""
    item = _base_adjudicated_item(auto_apply_allowed=True)
    item["final_gold"]["auto_apply_allowed"] = False
    item["auto_apply_reasoning"] = {
        "evidence_basis": "evidence ok",
        "verifier_pass":  True,
        "explanation":    "evidence 가 text 에 있고 verifier 통과",
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "AUTO_APPLY_MISMATCH"


def test_all_gates_pass_on_clean_item(tmp_path):
    item = _base_adjudicated_item()
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0
