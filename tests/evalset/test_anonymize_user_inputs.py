"""단계 6.5.5 Day 1 — anonymize_user_inputs.py 단위 테스트 (5건)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evalset"))

from anonymize_user_inputs import (   # noqa: E402
    anonymize_line, digest16, to_eval_item, FORBIDDEN_KEYS,
)


def test_anonymize_replaces_all_pii_tokens():
    """EMAIL / PHONE / URL / PR / SERVER 토큰 한 줄에서 모두 치환."""
    raw = "test@example.com 010-1234-5678 https://x.com PR #42 10.0.0.1"
    out, ent = anonymize_line(raw)
    assert "[EMAIL]"  in out
    assert "[PHONE]"  in out
    assert "[URL]"    in out
    assert "[PR]"     in out
    assert "[SERVER]" in out
    # 원본 PII 가 출력에 남아있지 않아야 함
    assert "test@example.com" not in out
    assert "010-1234-5678"    not in out


def test_anonymize_no_raw_text_leak():
    """to_eval_item 산출물에 raw_text 등 금지 키가 절대 포함되지 않는다."""
    item = to_eval_item("hello world", source="synthetic_gold", idx=1)
    keys = set(item.keys())
    for k in FORBIDDEN_KEYS:
        assert k not in keys, f"forbidden key leaked: {k}"


def test_digest16_deterministic():
    """동일 입력 → 동일 digest16. 다른 입력 → 다른 digest16."""
    a = digest16("hello")
    b = digest16("hello")
    c = digest16("world")
    assert a == b
    assert a != c
    assert a.startswith("sha256:")
    assert len(a) == len("sha256:") + 16


def test_anonymize_forbidden_keys_not_stored():
    """JSON 직렬화 후에도 금지 키 미포함."""
    item = to_eval_item("test@example.com 보내 주세요", source="synthetic_gold", idx=2)
    js = json.dumps(item, ensure_ascii=False)
    for k in FORBIDDEN_KEYS:
        assert f'"{k}"' not in js


def test_anonymize_pr_branch_keyword_replacement():
    """PR #/feat 브랜치 키워드 치환."""
    raw = "feat/foo-bar 브랜치 PR #999 확인"
    out, _ = anonymize_line(raw)
    assert "[BRANCH]" in out
    assert "[PR]"     in out
    assert "feat/foo-bar" not in out
    assert "PR #999"      not in out
