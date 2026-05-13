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
    """[EMAIL] 가 70% 초과 시 fail (TOKEN_DISTRIBUTION_SKEWED)."""
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
    assert res.returncode == 1
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["fail_class"] == "TOKEN_DISTRIBUTION_SKEWED"
    assert out["skew_top_token"] == "[EMAIL]"


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
    """토큰 0개 — 검사 skip (ok=True). 데이터 없음 알림."""
    items = [{
        "sample_id":"card1_200001","text":None,
        "text_redacted":"안녕하세요","raw_digest16":"sha256:0000000000000001",
        "source":"internal_log_redacted",
    }]
    p = _write_jsonl(tmp_path, items)
    res = _run("--input", str(p))
    # 토큰 0개 + skew_threshold 검사 통과 (0 > threshold 거짓)
    assert res.returncode == 0
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["total_tokens"] == 0
