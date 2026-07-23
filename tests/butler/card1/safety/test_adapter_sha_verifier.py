"""
Card 1 adapter_sha_verifier 회귀 방지 테스트.

Codex P2 결함 정정 (2026-05-22, PR #749) 후 추가.
SHA-256 hex digest 비교는 case-insensitive + whitespace-tolerant 이어야 한다.
"""
import hashlib
from pathlib import Path

import pytest

from src.butler.card1.safety.adapter_sha_verifier import verify_adapter_sha256


@pytest.fixture
def sample_adapter(tmp_path: Path) -> tuple[Path, str]:
    """샘플 어댑터 파일 + 정상 SHA-256 (소문자) 반환."""
    adapter = tmp_path / "adapter.bin"
    payload = b"butler-card1-adapter-test-payload-2026-05-22"
    adapter.write_bytes(payload)
    sha_lower = hashlib.sha256(payload).hexdigest()
    return adapter, sha_lower


def test_sha_match_lowercase(sample_adapter):
    """소문자 expected → PASS (raises 없음)."""
    adapter, sha = sample_adapter
    verify_adapter_sha256(adapter, sha)


def test_sha_match_uppercase(sample_adapter):
    """대문자 expected → PASS (case-insensitive)."""
    adapter, sha = sample_adapter
    verify_adapter_sha256(adapter, sha.upper())


def test_sha_match_mixed_case(sample_adapter):
    """대소문자 혼재 expected → PASS."""
    adapter, sha = sample_adapter
    mixed = "".join(c.upper() if i % 2 == 0 else c for i, c in enumerate(sha))
    verify_adapter_sha256(adapter, mixed)


def test_sha_match_with_whitespace(sample_adapter):
    """앞뒤 공백/줄바꿈 expected → PASS (strip)."""
    adapter, sha = sample_adapter
    verify_adapter_sha256(adapter, f"  {sha.upper()}\n")


def test_sha_mismatch_raises_value_error(sample_adapter):
    """실제 mismatch → ValueError + 메시지 정합."""
    adapter, _ = sample_adapter
    wrong = "0" * 64
    with pytest.raises(ValueError, match="adapter SHA-256 mismatch"):
        verify_adapter_sha256(adapter, wrong)
