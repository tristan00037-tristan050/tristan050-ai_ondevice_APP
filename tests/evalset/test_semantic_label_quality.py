"""단계 6.5.5+ Day 8 — Gate G23 v0 단위 테스트 (알고리즘 팀 옵션 C).

SEMANTIC_LABEL_PATTERN_GUARD: PURE_QUESTION / REPORT_FIXED 패턴 vs REQUEST 의미 충돌.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "evalset" / "check_semantic_label_quality.py"
PY   = sys.executable


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(GATE), *args], capture_output=True, text=True)


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


def _row(sid: str, text: str, *, intent: str,
         action_required: bool = False, answer_required: bool = False) -> dict:
    return {
        "sample_id":       sid,
        "text":            text,
        "intent_type":     intent,
        "action_required": action_required,
        "answer_required": answer_required,
    }


# ── 1. PURE_QUESTION + REQUEST + 행동동사 없음 → FAIL ────────────────────

def test_g23_pure_question_mislabeled_as_request_fails(tmp_path):
    items = [
        _row("card1_test001", "회사 주소가 어떻게 되나요?",
             intent="REQUEST", action_required=True, answer_required=True),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "SEMANTIC_LABEL_PATTERN_VIOLATION"
    assert out["violations"][0]["fail_class"] == "PURE_QUESTION_MISLABELED_AS_REQUEST"


# ── 2. PURE_QUESTION + 행동동사 동반 → PASS (REQUEST 정당) ───────────────

def test_g23_pure_question_with_action_verb_passes(tmp_path):
    items = [
        _row("card1_test002", "회사 주소가 어떻게 되나요? 정리해서 보내주세요",
             intent="REQUEST", action_required=True, answer_required=True),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["violation_count"] == 0


# ── 3. REPORT_FIXED + REQUEST → FAIL ─────────────────────────────────────

def test_g23_report_mislabeled_as_request_fails(tmp_path):
    items = [
        _row("card1_test003", "[PR] 머지 완료했습니다",
             intent="REQUEST", action_required=True),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["violations"][0]["fail_class"] == "REPORT_MISLABELED_AS_REQUEST"


# ── 4. REPORT_FIXED + REPORT → PASS ──────────────────────────────────────

def test_g23_report_correctly_labeled_passes(tmp_path):
    items = [
        _row("card1_test004", "배포 결과는 추후 안내드립니다",
             intent="REPORT", action_required=False, answer_required=False),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["violation_count"] == 0


# ── 5. AMBIGUOUS REQUEST / REPORT pattern → WARNING ONLY ─────────────────

def test_g23_warning_on_ambiguous_pattern(tmp_path):
    items = [
        _row("card1_test005", "이 일정 처리 가능한가요?",
             intent="REQUEST", action_required=True, answer_required=True),
        _row("card1_test006", "이슈 검토 후 처리하겠습니다",
             intent="REPORT", action_required=False),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["violation_count"] == 0
    classes = {w["warning_class"] for w in out["warnings"]}
    assert "AMBIGUOUS_REQUEST_PATTERN" in classes
    assert "AMBIGUOUS_REPORT_PATTERN"  in classes


# ── Day 10 G23 v1: PROMISE_BOUNDARY_PATTERN warning ──────────────────────

def test_g23_promise_boundary_warning_only(tmp_path):
    """진행하겠습니다 / 전달드리겠습니다 + REPORT → warning only, ok=true."""
    items = [
        _row("card1_test007", "검토 후 진행하겠습니다",
             intent="REPORT", action_required=False),
        _row("card1_test008", "결과 정리해서 전달드리겠습니다",
             intent="REPORT", action_required=False),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["violation_count"] == 0
    classes = {w["warning_class"] for w in out["warnings"]}
    assert "PROMISE_BOUNDARY_PATTERN" in classes
