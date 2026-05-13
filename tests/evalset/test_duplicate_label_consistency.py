"""단계 6.5.5+ Day 6 — Gate G22 단위 테스트 (6건, 알고리즘 팀 명세).

DUPLICATE_LABEL_INCONSISTENCY / GOLD_V1_DUPLICATE_CONFLICT / REVIEWED_DUPLICATE_CONFLICT.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "evalset" / "check_duplicate_label_consistency.py"
PY   = sys.executable


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(GATE), *args], capture_output=True, text=True)


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


def _row(sid: str, digest: str, *, intent="REQUEST", dtype="NONE",
         auto_apply=False, label_status="draft") -> dict:
    return {
        "sample_id":          sid,
        "raw_digest16":       digest,
        "intent_type":        intent,
        "deadline_type":      dtype,
        "auto_apply_allowed": auto_apply,
        "label_status":       label_status,
    }


# ── A. 중복 없음 → PASS ──────────────────────────────────────────────────

def test_g22_passes_when_no_duplicates(tmp_path):
    items = [
        _row("card1_000001", "sha256:1111111111111111"),
        _row("card1_000002", "sha256:2222222222222222"),
        _row("card1_000003", "sha256:3333333333333333"),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["duplicate_groups_checked"] == 0


# ── B. 중복 + 같은 라벨 → PASS ───────────────────────────────────────────

def test_g22_passes_when_duplicates_have_same_labels(tmp_path):
    items = [
        _row("card1_000001", "sha256:aaaaaaaaaaaaaaaa", intent="REQUEST", dtype="HARD"),
        _row("card1_000002", "sha256:aaaaaaaaaaaaaaaa", intent="REQUEST", dtype="HARD"),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["duplicate_groups_checked"] == 1


# ── C. intent_type 불일치 → FAIL ─────────────────────────────────────────

def test_g22_fails_on_duplicate_intent_type_mismatch(tmp_path):
    items = [
        _row("card1_000001", "sha256:bbbbbbbbbbbbbbbb", intent="REQUEST"),
        _row("card1_000002", "sha256:bbbbbbbbbbbbbbbb", intent="REPORT"),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "DUPLICATE_LABEL_INCONSISTENCY"
    grp = out["duplicate_groups"][0]
    assert grp["conflicts"] == ["intent_type"]


# ── D. deadline_type 불일치 + 우선순위 검증 (card1_400052 재현) ──────────

def test_g22_fails_on_duplicate_deadline_type_mismatch(tmp_path):
    """gold_reviewed (priority 4) vs draft (priority 1) — truth_source = gold_reviewed."""
    items = [
        _row("card1_100026", "sha256:9e7e8551f1c91ef3",
             dtype="INQUIRY", label_status="gold_reviewed"),
        _row("card1_400052", "sha256:9e7e8551f1c91ef3",
             dtype="NONE",    label_status="draft"),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "DUPLICATE_LABEL_INCONSISTENCY"
    grp = out["duplicate_groups"][0]
    assert grp["conflicts"] == ["deadline_type"]
    # priority 최상위 = gold_reviewed (card1_100026)
    assert grp["recommended_truth_source"] == "card1_100026"


# ── E. auto_apply_allowed 불일치 → FAIL ──────────────────────────────────

def test_g22_fails_on_duplicate_auto_apply_allowed_mismatch(tmp_path):
    items = [
        _row("card1_400003", "sha256:e95958a6b5943f2b",
             auto_apply=True,  label_status="gold_v1"),
        _row("card1_500103", "sha256:e95958a6b5943f2b",
             auto_apply=False, label_status="draft"),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "DUPLICATE_LABEL_INCONSISTENCY"
    grp = out["duplicate_groups"][0]
    assert grp["conflicts"] == ["auto_apply_allowed"]
    # gold_v1 priority 5 — truth source
    assert grp["recommended_truth_source"] == "card1_400003"


# ── F. gold_v1 두 개끼리 충돌 → GOLD_V1_DUPLICATE_CONFLICT ──────────────

def test_g22_fails_on_gold_v1_duplicate_conflict(tmp_path):
    """같은 digest + gold_v1 + gold_v1 + 라벨 불일치 → 가장 심각."""
    items = [
        _row("card1_400003", "sha256:cccccccccccccccc",
             intent="REQUEST", label_status="gold_v1"),
        _row("card1_400004", "sha256:cccccccccccccccc",
             intent="REPORT",  label_status="gold_v1"),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "GOLD_V1_DUPLICATE_CONFLICT"


# ── Day 7 G22 v2 회귀 (3건) — warning (hard 승격 X) ─────────────────────

def _row_with_required(sid, digest, *, action_required=False,
                       answer_required=False, intent="REQUEST"):
    return {
        "sample_id":          sid,
        "raw_digest16":       digest,
        "intent_type":        intent,
        "deadline_type":      "NONE",
        "auto_apply_allowed": False,
        "label_status":       "draft",
        "action_required":    action_required,
        "answer_required":    answer_required,
    }


def test_g22_v2_warning_on_action_required_mismatch(tmp_path):
    """같은 digest + 다른 action_required + 같은 hard fields → WARNING."""
    items = [
        _row_with_required("card1_700001", "sha256:dddddddddddddddd",
                           action_required=True),
        _row_with_required("card1_700002", "sha256:dddddddddddddddd",
                           action_required=False),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0   # hard fields ok → ok=true 유지
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["warning_count"] >= 1
    assert any(w["warning_class"] == "DUPLICATE_ACTION_REQUIRED_INCONSISTENCY"
               for w in out["warnings"])


def test_g22_v2_warning_on_answer_required_mismatch(tmp_path):
    items = [
        _row_with_required("card1_700003", "sha256:eeeeeeeeeeeeeeee",
                           answer_required=True),
        _row_with_required("card1_700004", "sha256:eeeeeeeeeeeeeeee",
                           answer_required=False),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert any(w["warning_class"] == "DUPLICATE_ANSWER_REQUIRED_INCONSISTENCY"
               for w in out["warnings"])


def test_g22_v2_warning_does_not_fail_when_hard_fields_ok(tmp_path):
    """warning 있어도 hard fields ok 면 fail X (ok=true 유지)."""
    items = [
        _row_with_required("card1_700005", "sha256:ffffffffffffffff",
                           action_required=True, answer_required=True),
        _row_with_required("card1_700006", "sha256:ffffffffffffffff",
                           action_required=False, answer_required=False),
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--out", str(tmp_path / "out.json"))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["violation_count"] == 0
    assert out["warning_count"] >= 1
