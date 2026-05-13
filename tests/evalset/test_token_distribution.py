"""단계 6.5.5 Day 3 — Gate G16 단위 테스트 (3건)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[2]
GATE    = ROOT / "scripts" / "evalset" / "check_token_distribution.py"
PY      = sys.executable


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([PY, str(GATE), *args], capture_output=True, text=True)


def _write_jsonl(tmp_path: Path, items: list) -> Path:
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items),
                 encoding="utf-8")
    return p


def test_token_distribution_warns_on_skewed_distribution(tmp_path):
    """[EMAIL] 가 70% 초과 시 WARNING (BLOCK 아님 — P1 정정 후)."""
    items = []
    for i in range(1, 11):
        items.append({
            "sample_id":    f"card1_{200000 + i:06d}",
            "text":         None,
            "text_redacted":"[EMAIL] 으로 보내주세요",   # [EMAIL] 다수
            "raw_digest16": f"sha256:{i:016x}",
            "source":       "internal_log_redacted",
        })
    # 마지막 1건만 다른 토큰
    items.append({
        "sample_id":    "card1_200011",
        "text":         None,
        "text_redacted":"[DOCUMENT] 확인",
        "raw_digest16": "sha256:000000000000000b",
        "source":       "internal_log_redacted",
    })
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p))
    # P1 정정 후: SKEW 는 WARNING (exit 0, ok=true)
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    skew = [w for w in out["warnings"] if w["type"] == "TOKEN_DISTRIBUTION_SKEW"]
    assert len(skew) == 1
    assert skew[0]["top_token"] == "[EMAIL]"


def test_token_distribution_passes_on_balanced(tmp_path):
    items = [
        {"sample_id":"card1_200001","text":None,
         "text_redacted":"[EMAIL] [DOCUMENT] [PR]","raw_digest16":"sha256:0000000000000001",
         "source":"internal_log_redacted"},
        {"sample_id":"card1_200002","text":None,
         "text_redacted":"[DATE] [TIME] [SERVER]","raw_digest16":"sha256:0000000000000002",
         "source":"internal_log_redacted"},
    ]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p))
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True


def test_token_distribution_handles_zero_tokens(tmp_path):
    """단일 userlog + 토큰 0개 — P1 정정 후 BLOCK (TOKEN_DISTRIBUTION_EMPTY)."""
    items = [{
        "sample_id":"card1_200001","text":None,
        "text_redacted":"안녕하세요","raw_digest16":"sha256:0000000000000001",
        "source":"internal_log_redacted",
    }]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p))
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"] == "TOKEN_DISTRIBUTION_EMPTY"


# ── PR #704 P1 정정 신규 회귀 (3건) ────────────────────────────────────

def test_token_distribution_empty_blocks_when_userlog_meets_min(tmp_path):
    """userlog 60건 + 표준 토큰 0개 → BLOCK (TOKEN_DISTRIBUTION_EMPTY)."""
    items = []
    for i in range(1, 61):
        items.append({
            "sample_id":    f"card1_{200000 + i:06d}",
            "text":         None,
            "text_redacted":"안녕하세요 답변 부탁드려요",   # 표준 토큰 없음
            "raw_digest16": f"sha256:{i:016x}",
            "source":       "internal_log_redacted",
        })
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--min-userlog", "30")
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["fail_class"]   == "TOKEN_DISTRIBUTION_EMPTY"
    assert out["userlog_count"] == 60
    assert out["total_tokens"]  == 0


def test_token_distribution_warning_does_not_block_skew(tmp_path):
    """userlog 60건 + [DOCUMENT] 90% — SKEW 경고만 (BLOCK 아님)."""
    items = []
    # 54건 [DOCUMENT], 6건 다른 토큰 → 54/60 = 90%
    for i in range(1, 55):
        items.append({
            "sample_id":    f"card1_{200000 + i:06d}",
            "text":         None,
            "text_redacted":"[DOCUMENT] 확인 부탁드립니다",
            "raw_digest16": f"sha256:{i:016x}",
            "source":       "internal_log_redacted",
        })
    for i in range(55, 61):
        items.append({
            "sample_id":    f"card1_{200000 + i:06d}",
            "text":         None,
            "text_redacted":"[EMAIL] 회신 부탁드립니다",
            "raw_digest16": f"sha256:{i:016x}",
            "source":       "internal_log_redacted",
        })
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--min-userlog", "30")
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    skew = [w for w in out["warnings"] if w["type"] == "TOKEN_DISTRIBUTION_SKEW"]
    assert len(skew) == 1
    assert skew[0]["top_token"] == "[DOCUMENT]"
    assert skew[0]["block_type"] == "WARNING"


def test_token_distribution_low_variety_warning_only(tmp_path):
    """userlog 60건 + 토큰 종류 3개 (< 8) — LOW_VARIETY 경고만."""
    samples = ["[DOCUMENT] 확인", "[EMAIL] 회신", "[PR] 머지"]
    items = []
    for i in range(1, 61):
        items.append({
            "sample_id":    f"card1_{200000 + i:06d}",
            "text":         None,
            "text_redacted":samples[i % 3],
            "raw_digest16": f"sha256:{i:016x}",
            "source":       "internal_log_redacted",
        })
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p), "--min-userlog", "30")
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["ok"] is True
    low = [w for w in out["warnings"] if w["type"] == "TOKEN_VARIETY_LOW"]
    assert len(low) == 1
    assert low[0]["detected_count"] == 3
