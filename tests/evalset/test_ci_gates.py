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


def test_distribution_fails_on_json_parse_error(tmp_path):
    """PR #704 P1-A 정정 — JSON parse 오류 fail-closed (Day 1 P2 원칙 동일)."""
    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text(
        '{"sample_id":"card1_000001","intent_type":"REQUEST",'
        '"deadline_type":"NONE","source":"synthetic_gold"}\n'
        '{not valid json}\n',
        encoding="utf-8",
    )
    res = _run("check_distribution.py", "--input", str(bad_path), "--min-total", "1")
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "JSON_PARSE_ERROR"
    assert out["parse_error_count"] >= 1


def test_distribution_passes_on_clean_jsonl(tmp_path):
    """정상 JSONL 100건 → distribution PASS."""
    items = [
        {"sample_id": f"card1_{i:06d}",
         "intent_type": "REQUEST" if i % 2 else "REPORT",
         "deadline_type": "NONE",
         "source": "synthetic_gold"}
        for i in range(1, 101)
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("check_distribution.py", "--input", str(p), "--min-total", "100")
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["total_items"] == 100


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
    # P1 정정 후 응답 구조: out["fields"][field]
    assert out["fields"]["intent_type"]["rate"]        == 1.0
    assert out["fields"]["deadline_type"]["rate"]      == 1.0
    assert out["fields"]["auto_apply_allowed"]["rate"] == 1.0


# ── P1 정정 회귀 3건 (PR #702 리뷰) ──────────────────────────────────────

def test_compute_agreement_fails_when_no_pairs(tmp_path):
    """1인 라벨만 있으면 NO_COMPARABLE_PAIRS 로 fail (fail-closed)."""
    items = [
        {"sample_id": "card1_000001", "intent_type": "REQUEST",
         "deadline_type": "NONE", "auto_apply_allowed": False},
        {"sample_id": "card1_000002", "intent_type": "REPORT",
         "deadline_type": "NONE", "auto_apply_allowed": False},
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("compute_agreement.py", "--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "NO_COMPARABLE_PAIRS"


def test_compute_agreement_fails_when_below_threshold(tmp_path):
    """2인 라벨이지만 합의도가 임계값 미만이면 fail."""
    # 4 sample × 2인 — intent_type 1/4 match (0.25 << 0.85)
    items = []
    for i in range(1, 5):
        items.append({"sample_id": f"card1_{i:06d}", "intent_type": "REQUEST",
                      "deadline_type": "NONE", "auto_apply_allowed": False})
        # 한 명만 동일한 답, 나머지 3 sample 은 다른 답
        other = "REQUEST" if i == 1 else "REPORT"
        items.append({"sample_id": f"card1_{i:06d}", "intent_type": other,
                      "deadline_type": "NONE", "auto_apply_allowed": False})
    p = _write_jsonl(tmp_path, items)
    res = _run("compute_agreement.py", "--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fields"]["intent_type"]["fail_class"] == "BELOW_AGREEMENT_THRESHOLD"
    assert out["fields"]["intent_type"]["rate"] < 0.85


def test_compute_agreement_passes_when_all_threshold_met(tmp_path):
    """모든 field 가 임계값 이상이면 PASS."""
    items = [
        {"sample_id": "card1_000001", "intent_type": "REQUEST",
         "deadline_type": "NONE", "auto_apply_allowed": False},
        {"sample_id": "card1_000001", "intent_type": "REQUEST",
         "deadline_type": "NONE", "auto_apply_allowed": False},
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("compute_agreement.py", "--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True


# ── P2 정정 회귀 2건 (PR #702 리뷰) ──────────────────────────────────────

def test_check_pii_leak_fails_on_json_parse_error(tmp_path):
    """JSON parse 오류 시 ok=False, fail_class=JSON_PARSE_ERROR."""
    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text(
        '{"sample_id":"card1_000001","text_redacted":"ok","raw_digest16":"sha256:0000000000000001"}\n'
        '{this is not json}\n',
        encoding="utf-8",
    )
    res = _run("check_pii_leak.py", "--input", str(bad_path))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "JSON_PARSE_ERROR"
    assert out["parse_error_count"] >= 1


def test_check_pii_leak_fails_on_both_leak_and_parse_error(tmp_path):
    """PII leak + parse error 동시 발생 — 둘 다 보고 + fail-closed."""
    bad_path = tmp_path / "both.jsonl"
    bad_path.write_text(
        '{"sample_id":"card1_000001","text_redacted":"leak test@example.com",'
        '"raw_digest16":"sha256:0000000000000001"}\n'
        '{this is not json}\n',
        encoding="utf-8",
    )
    res = _run("check_pii_leak.py", "--input", str(bad_path))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    # parse error 우선 (검사 자체 불가능이라서 더 심각)
    assert out["fail_class"] == "JSON_PARSE_ERROR"
    assert out["parse_error_count"] >= 1
    assert out["leak_count"]       >= 1
    assert len(out["violations"])  >= 1
    assert len(out["parse_errors"]) >= 1
