"""단계 6.5.5 Day 2 — Gate 7 evidence consistency 단위 테스트 (5건).

Gate 7 (scripts/evalset/check_evidence_consistency.py):
- label_status in {gold_reviewed, approved, adjudicated} 만 검증
- gold.deadline.evidence / gold.materials[*].evidence / gold.actions[*].evidence 가
  text(synthetic_gold) 또는 text_redacted(userlog) 안에 substring 존재해야 함
- fail-closed (JSON parse 오류도 fail)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT    = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "evalset"
PY      = sys.executable

GATE = SCRIPTS / "check_evidence_consistency.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(GATE), *args], capture_output=True, text=True)


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


# ── 1. evidence 가 text 에 있으면 PASS ──────────────────────────────────

def test_evidence_consistency_pass_when_evidence_in_text(tmp_path):
    item = {
        "sample_id":      "card1_000100",
        "text":           "회의록 정리해서 공유해 주세요",
        "text_redacted":  None,
        "raw_digest16":   "sha256:1111111111111111",
        "source":         "synthetic_gold",
        "intent_type":    "REQUEST",
        "deadline_type":  "NONE",
        "label_status":   "gold_reviewed",
        "gold": {
            "deadline":  None,
            "materials": [{"text": "회의록", "type": "document",
                           "evidence": "회의록 정리"}],
            "actions":   [{"action_text": "회의록 정리",
                           "evidence": "회의록 정리해서"}],
        },
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["violation_count"] == 0
    assert out["enforced_items"]  == 1


# ── 2. evidence 가 text 에 없으면 FAIL ─────────────────────────────────

def test_evidence_consistency_fail_when_evidence_not_in_text(tmp_path):
    item = {
        "sample_id":      "card1_000101",
        "text":           "회의록 정리해서 공유해 주세요",
        "text_redacted":  None,
        "raw_digest16":   "sha256:2222222222222222",
        "source":         "synthetic_gold",
        "intent_type":    "REQUEST",
        "deadline_type":  "NONE",
        "label_status":   "gold_reviewed",
        "gold": {
            "deadline":  None,
            "materials": [],
            "actions":   [{"action_text": "회의록 정리",
                           "evidence": "원문에 없는 문장 입니다"}],
        },
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "EVIDENCE_NOT_IN_TEXT"
    assert out["violation_count"] >= 1


# ── 3. label_status=draft 면 검증 면제 ─────────────────────────────────

def test_evidence_consistency_skip_when_label_status_draft(tmp_path):
    """draft 상태는 evidence 가 text 에 없어도 PASS (검증 면제)."""
    item = {
        "sample_id":      "card1_000102",
        "text":           "회의록 정리해서 공유해 주세요",
        "text_redacted":  None,
        "raw_digest16":   "sha256:3333333333333333",
        "source":         "synthetic_gold",
        "intent_type":    "REQUEST",
        "deadline_type":  "NONE",
        "label_status":   "draft",
        "gold": {
            "actions": [{"action_text": "??",
                         "evidence":   "전혀 없는 문장"}],
        },
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["exempt_items"]  == 1
    assert out["enforced_items"] == 0


# ── 4. userlog_redacted 는 text_redacted 사용 ──────────────────────────

def test_evidence_consistency_userlog_uses_text_redacted(tmp_path):
    """text=null, text_redacted 에 evidence 가 있으면 PASS."""
    item = {
        "sample_id":      "card1_000103",
        "text":           None,
        "text_redacted":  "[EMAIL]으로 보고서 보내주세요",
        "raw_digest16":   "sha256:4444444444444444",
        "source":         "internal_log_redacted",
        "intent_type":    "REQUEST",
        "deadline_type":  "NONE",
        "label_status":   "approved",
        "gold": {
            "materials": [{"text": "보고서", "type": "document",
                           "evidence": "보고서 보내주세요"}],
        },
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True


# ── 5. 복합 액션 — 각 action evidence 모두 검증 ─────────────────────────

def test_evidence_consistency_multi_action_all_evidence_required(tmp_path):
    """3개 action 중 1개라도 evidence 미일치면 FAIL."""
    item = {
        "sample_id":      "card1_000104",
        "text":           "보고서 검토하고 수정 사항 정리해서 보내주세요",
        "text_redacted":  None,
        "raw_digest16":   "sha256:5555555555555555",
        "source":         "synthetic_gold",
        "intent_type":    "REQUEST",
        "deadline_type":  "NONE",
        "label_status":   "gold_reviewed",
        "gold": {
            "actions": [
                {"action_text": "보고서 검토", "evidence": "보고서 검토하고"},
                {"action_text": "수정사항 정리", "evidence": "수정 사항 정리"},
                {"action_text": "보고서 전달",  "evidence": "원문에 없음 (위반)"},
            ],
        },
    }
    p = _write_jsonl(tmp_path, [item])
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    # 3개 중 1개만 위반
    assert out["violation_count"] == 1
    assert out["violations"][0]["kind"] == "action_evidence_not_in_text"
