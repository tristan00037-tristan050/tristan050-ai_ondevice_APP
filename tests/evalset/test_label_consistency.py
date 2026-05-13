"""단계 6.5.5 Day 3 — Gate G8~G15 단위 테스트 (10건)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def _base_gold_item(**overrides):
    """기본 정합 샘플 (synthetic_gold + gold_reviewed). 위반 없으면 ok."""
    item = {
        "sample_id":              "card1_100001",
        "text":                   "보고서 보내주세요",
        "text_redacted":          None,
        "raw_digest16":           "sha256:0000000000000001",
        "source":                 "synthetic_gold",
        "intent_type":            "REQUEST",
        "deadline_type":          "NONE",
        "deadline_is_actionable": False,
        "slice_tags":             [],
        "action_required":        True,
        "answer_required":        True,
        "auto_apply_allowed":     False,
        "label_status":           "gold_reviewed",
        "reviewer":               {"id": "r1", "decision": "approved",
                                   "reviewed_at": "2026-05-13T09:00:00Z"},
        "gold": {
            "intent_type": "REQUEST",
            "deadline":    None,
            "materials":   [{"text": "보고서", "evidence": "보고서 보내주세요"}],
            "actions":     [{"action_text": "보내기", "evidence": "보고서 보내주세요"}],
        },
    }
    item.update(overrides)
    return item


def test_g8_double_labeled_requires_both_annotators(tmp_path):
    item = _base_gold_item(label_status="double_labeled")
    item.pop("reviewer", None)
    # annotator_a 만 있음 (b 누락)
    item["annotator_a"] = {"id": "a", "intent_type": "REQUEST",
                            "deadline_type": "NONE",
                            "auto_apply_allowed": False,
                            "labeled_at": "2026-05-13T10:00:00Z"}
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "ANNOTATOR_MISSING_WHEN_DOUBLE_LABELED"


def test_g9_approved_requires_reviewer(tmp_path):
    item = _base_gold_item(label_status="approved")
    item.pop("reviewer", None)
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "REVIEWER_MISSING_WHEN_APPROVED"


def test_g9_gold_reviewed_requires_reviewer(tmp_path):
    item = _base_gold_item()
    item.pop("reviewer", None)
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "REVIEWER_MISSING_WHEN_APPROVED"


def test_g10_primary_intent_must_match_gold_intent_type(tmp_path):
    item = _base_gold_item()
    item["intent_type"] = "REQUEST"
    item["gold"]["intent_type"] = "REPORT"   # 불일치
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "PRIMARY_INTENT_MISMATCH_GOLD"


def test_g11_inquiry_deadline_type_forbids_deadline_object(tmp_path):
    """deadline_type=INQUIRY 인데 gold.deadline 존재 → fail."""
    item = _base_gold_item(intent_type="QUESTION", deadline_type="INQUIRY")
    item["gold"]["intent_type"] = "QUESTION"
    item["gold"]["deadline"] = {"text": "언제까지", "type": "INQUIRY",
                                 "evidence": "보고서 보내주세요"}
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "DEADLINE_TYPE_INCONSISTENT_WITH_OBJECT"


def test_g11_hard_deadline_requires_deadline_object(tmp_path):
    """deadline_type=HARD 인데 gold.deadline=null → fail."""
    item = _base_gold_item(deadline_type="HARD", deadline_is_actionable=True)
    item["gold"]["deadline"] = None
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "DEADLINE_TYPE_INCONSISTENT_WITH_OBJECT"


def test_g12_no_action_requires_empty_actions(tmp_path):
    """NO_ACTION 인데 gold.actions 비어있지 않음 → fail."""
    item = _base_gold_item(
        intent_type="NO_ACTION",
        action_required=False, answer_required=False,
    )
    item["gold"]["intent_type"] = "NO_ACTION"
    # actions 가 비어있지 않음
    item["gold"]["actions"] = [{"action_text": "?", "evidence": "보고서 보내주세요"}]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "NO_ACTION_HAS_NONEMPTY_ACTIONS"


def test_g13_auto_apply_allowed_requires_approved_like(tmp_path):
    """PR #704 P2 정정 후: auto_apply_allowed=true + gold_reviewed → PASS (APPROVED_LIKE).

    이전 spec 은 approved 만 허용하던 결함 (스키마 enum 에 approved 없음).
    P2 정정: APPROVED_LIKE_STATUSES = {approved, gold_reviewed, gold_v1, adjudicated}.
    """
    item = _base_gold_item(auto_apply_allowed=True)   # label_status=gold_reviewed
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True


def test_g14_userlog_text_must_be_null_strict(tmp_path):
    """userlog 인데 text != null → fail (스키마 + Gate 이중 차단)."""
    item = {
        "sample_id":              "card1_200001",
        "text":                   "leaked raw content",     # ← 위반
        "text_redacted":          "[EMAIL] 으로 보내주세요",
        "raw_digest16":           "sha256:1111111111111111",
        "source":                 "internal_log_redacted",
        "intent_type":            "REQUEST",
        "deadline_type":          "NONE",
        "deadline_is_actionable": False,
        "slice_tags":             [],
        "action_required":        True,
        "answer_required":        True,
        "auto_apply_allowed":     False,
        "label_status":           "draft",
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "USERLOG_TEXT_NOT_NULL"


def test_g15_evidence_inconsistency_blocks_approved(tmp_path):
    """evidence 가 text 에 없음 + label_status=gold_reviewed → fail."""
    item = _base_gold_item()
    item["gold"]["actions"] = [{"action_text": "보내기",
                                "evidence": "원문에 없는 문장"}]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "EVIDENCE_INCONSISTENT_WHEN_APPROVED"


# ── PR #704 P2 정정 회귀 (5건) — G13 APPROVED_LIKE_STATUSES ─────────────

def test_g13_auto_apply_passes_with_approved(tmp_path):
    item = _base_gold_item(label_status="approved", auto_apply_allowed=True)
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0


def test_g13_auto_apply_passes_with_gold_reviewed(tmp_path):
    item = _base_gold_item(label_status="gold_reviewed", auto_apply_allowed=True)
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0


def test_g13_auto_apply_passes_with_gold_v1(tmp_path):
    item = _base_gold_item(label_status="gold_v1", auto_apply_allowed=True)
    # gold_v1 도 reviewer 필요 (G9 conditional)
    item["reviewer"] = {"id": "r1", "decision": "approved",
                        "reviewed_at": "2026-05-13T09:00:00Z"}
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0


def test_g13_auto_apply_passes_with_adjudicated(tmp_path):
    item = _base_gold_item(label_status="adjudicated", auto_apply_allowed=True)
    item.pop("reviewer", None)
    item["adjudicator"] = {"id": "adj1", "decision": "approved",
                           "reviewed_at": "2026-05-13T11:00:00Z"}
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0


def test_g13_auto_apply_fails_with_draft(tmp_path):
    """auto_apply_allowed=true 인데 draft → AUTO_APPLY_REQUIRES_APPROVED_LIKE."""
    item = _base_gold_item(label_status="draft", auto_apply_allowed=True)
    item.pop("reviewer", None)
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "AUTO_APPLY_REQUIRES_APPROVED_LIKE"


# ── PR #704 P1-B 정정 회귀 (2건) — G15 adjudicated 포함 ────────────────

def test_adjudicated_auto_apply_requires_evidence_consistency(tmp_path):
    """adjudicated + auto_apply_allowed=true + evidence 불일치 → fail (G15)."""
    item = _base_gold_item(label_status="adjudicated", auto_apply_allowed=True)
    item.pop("reviewer", None)
    item["adjudicator"] = {"id": "adj1", "decision": "approved",
                           "reviewed_at": "2026-05-13T11:00:00Z"}
    # evidence 가 text 에 없도록 강제 위반
    item["gold"]["actions"] = [{"action_text": "보내기",
                                "evidence": "원문에 없는 문장 입니다"}]
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "EVIDENCE_INCONSISTENT_WHEN_APPROVED"


def test_adjudicated_auto_apply_passes_with_evidence_consistency(tmp_path):
    """adjudicated + auto_apply_allowed=true + evidence 일치 → PASS."""
    item = _base_gold_item(label_status="adjudicated", auto_apply_allowed=True)
    item.pop("reviewer", None)
    item["adjudicator"] = {"id": "adj1", "decision": "approved",
                           "reviewed_at": "2026-05-13T11:00:00Z"}
    # 기본 item 의 evidence 는 모두 text 에 있음
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
