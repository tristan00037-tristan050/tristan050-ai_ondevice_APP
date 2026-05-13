"""단계 6.5.5 Day 1 — CI Gate 6 스크립트 단위 테스트 (5건)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT     = Path(__file__).resolve().parents[2]
SCRIPTS  = ROOT / "scripts" / "evalset"
SCHEMA   = ROOT / "schemas" / "card1_eval_item.schema.json"
SEED     = ROOT / "tests" / "fixtures" / "card1_evalset_seed_examples.jsonl"
PY       = sys.executable


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(SCRIPTS / script), *args],
        capture_output=True, text=True,
    )


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


def test_check_no_raw_text_detects_forbidden_key(tmp_path):
    bad = _write_jsonl(tmp_path, [{
        "sample_id":   "card1_000001",
        "text_redacted": "ok",
        "raw_text":    "this should be banned",   # 금지 키
        "raw_digest16": "sha256:0000000000000001",
    }])
    res = _run("check_no_raw_text.py", "--input", str(bad))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "RAW_TEXT_STORED"
    # seed 파일은 PASS
    res_ok = _run("check_no_raw_text.py", "--input", str(SEED))
    assert res_ok.returncode == 0


def test_check_digest16_rejects_invalid_format(tmp_path):
    bad = _write_jsonl(tmp_path, [{
        "sample_id":    "card1_000001",
        "text_redacted": "ok",
        "raw_digest16": "md5:abcd",
    }])
    res = _run("check_digest16.py", "--input", str(bad))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "DIGEST16_INVALID"
    res_ok = _run("check_digest16.py", "--input", str(SEED))
    assert res_ok.returncode == 0


def test_check_pii_leak_detects_email_phone(tmp_path):
    bad = _write_jsonl(tmp_path, [{
        "sample_id":     "card1_000001",
        "text_redacted": "leaked test@example.com 010-1234-5678",
        "raw_digest16":  "sha256:0000000000000001",
    }])
    res = _run("check_pii_leak.py", "--input", str(bad))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "PII_LEAK"
    assert out["leak_by_type"]["EMAIL"] >= 1
    assert out["leak_by_type"]["PHONE"] >= 1


def test_check_distribution_counts_correctly(tmp_path):
    items = [
        {"sample_id": f"card1_{i:06d}",
         "text_redacted": "ok",
         "raw_digest16": f"sha256:{i:016x}",
         "intent_type":   "REQUEST" if i % 2 == 0 else "REPORT",
         "deadline_type": "NONE",
         "source":        "synthetic_gold"}
        for i in range(1, 11)
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("check_distribution.py", "--input", str(p), "--min-total", "5")
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["total_items"]   == 10
    assert out["intent_counts"]["REQUEST"] == 5
    assert out["intent_counts"]["REPORT"]  == 5
    # min-total 미달 case
    res2 = _run("check_distribution.py", "--input", str(p), "--min-total", "999")
    assert res2.returncode == 1


def test_compute_agreement_pairs_match(tmp_path):
    items = [
        {"sample_id": "card1_000001", "intent_type": "REQUEST",
         "deadline_type": "NONE", "auto_apply_allowed": False},
        {"sample_id": "card1_000001", "intent_type": "REQUEST",
         "deadline_type": "NONE", "auto_apply_allowed": False},
        {"sample_id": "card1_000002", "intent_type": "REPORT",
         "deadline_type": "NONE", "auto_apply_allowed": False},
        {"sample_id": "card1_000002", "intent_type": "REPORT",
         "deadline_type": "NONE", "auto_apply_allowed": False},
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("compute_agreement.py", "--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["agreement"]["intent_type"]["rate"]        == 1.0
    assert out["agreement"]["deadline_type"]["rate"]      == 1.0
    assert out["agreement"]["auto_apply_allowed"]["rate"] == 1.0
