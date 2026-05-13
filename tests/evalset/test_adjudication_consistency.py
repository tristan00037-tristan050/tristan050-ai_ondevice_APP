"""단계 6.5.5 Day 4 — Gate G17~G20 단위 테스트 (8건)."""
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
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "ADJUDICATOR_MISSING_WHEN_ADJUDICATED"


def test_g17_gold_v1_requires_adjudicator(tmp_path):
    item = _base_adjudicated_item(label_status="gold_v1")
    del item["adjudicator"]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "ADJUDICATOR_MISSING_WHEN_ADJUDICATED"


def test_g18_adjudicated_requires_final_gold(tmp_path):
    item = _base_adjudicated_item()
    del item["final_gold"]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "FINAL_GOLD_MISSING_WHEN_ADJUDICATED"


def test_g18_gold_v1_requires_final_gold(tmp_path):
    item = _base_adjudicated_item(label_status="gold_v1")
    del item["final_gold"]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "FINAL_GOLD_MISSING_WHEN_ADJUDICATED"


def test_g19_approved_requires_disagreement_resolution(tmp_path):
    """annotator_a/b 불일치인데 final_gold.disagreement_resolution 누락 → fail."""
    item = _base_adjudicated_item()
    item["annotator_a"] = {"id": "a", "intent_type": "REQUEST",
                            "deadline_type": "NONE",
                            "auto_apply_allowed": False,
                            "labeled_at": "2026-05-13T10:00:00Z"}
    item["annotator_b"] = {"id": "b", "intent_type": "REPORT",   # 불일치
                            "deadline_type": "NONE",
                            "auto_apply_allowed": False,
                            "labeled_at": "2026-05-13T10:30:00Z"}
    # final_gold.disagreement_resolution 누락 (기본 fixture 에 없음)
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "APPROVED_WITHOUT_DISAGREEMENT_RESOLUTION"


def test_g20_auto_apply_requires_reasoning(tmp_path):
    item = _base_adjudicated_item(auto_apply_allowed=True)
    # reasoning 자체 누락
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "AUTO_APPLY_REASONING_MISSING"


def test_g20_auto_apply_reasoning_explanation_min_length(tmp_path):
    """explanation 10자 미만 → fail."""
    item = _base_adjudicated_item(auto_apply_allowed=True)
    item["auto_apply_reasoning"] = {
        "evidence_basis": "evidence ok",
        "verifier_pass":  True,
        "explanation":    "짧음",   # < 10자
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "AUTO_APPLY_REASONING_MISSING"


def test_g20_auto_apply_reasoning_verifier_pass_required(tmp_path):
    """verifier_pass 가 bool 이 아니면 fail."""
    item = _base_adjudicated_item(auto_apply_allowed=True)
    item["auto_apply_reasoning"] = {
        "evidence_basis": "evidence ok",
        "verifier_pass":  "yes",    # not bool
        "explanation":    "evidence 가 text 안 substring 으로 존재하고 verifier 통과",
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "AUTO_APPLY_REASONING_MISSING"
