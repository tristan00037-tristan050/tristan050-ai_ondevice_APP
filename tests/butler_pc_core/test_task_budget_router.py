"""
tests/butler_pc_core/test_task_budget_router.py
================================================
task_budget_router 12 케이스 단위 테스트.
실제 파일 I/O가 필요한 케이스는 tmp_path fixture로 임시 파일 생성.
"""
from __future__ import annotations

import pytest

from butler_pc_core.router.task_budget_router import (
    BudgetResult,
    classify_bytes,
    classify_file,
)

# ---------------------------------------------------------------------------
# classify_bytes — 파일 없이 크기·파일명만으로 테스트 (케이스 1~10)
# ---------------------------------------------------------------------------

class TestClassifyBytes:
    # --- Tier S (≤ 50 KB) ---
    def test_01_tier_s_exact_boundary(self):
        """50 KB 정확히 → S"""
        r = classify_bytes(50 * 1024, "doc.txt")
        assert r.tier == "S"
        assert not r.blocked
        assert r.block_reason == ""
        assert r.estimated_chunks >= 1

    def test_02_tier_s_small(self):
        """10 KB → S"""
        r = classify_bytes(10 * 1024, "email.txt")
        assert r.tier == "S"
        assert r.size_kb == pytest.approx(10.0, abs=0.1)

    # --- Tier M (50 < KB ≤ 200) ---
    def test_03_tier_m_just_over_s(self):
        """51 KB → M"""
        r = classify_bytes(51 * 1024, "report.docx")
        assert r.tier == "M"
        assert not r.blocked

    def test_04_tier_m_boundary(self):
        """200 KB 정확히 → M"""
        r = classify_bytes(200 * 1024, "budget.xlsx")
        assert r.tier == "M"

    # --- Tier L (200 < KB ≤ 1024) ---
    def test_05_tier_l_just_over_m(self):
        """201 KB → L"""
        r = classify_bytes(201 * 1024, "contract.pdf")
        assert r.tier == "L"
        assert not r.blocked
        assert r.estimated_chunks >= 1
        assert r.estimated_seconds > 0

    def test_06_tier_l_boundary(self):
        """1024 KB (1 MB) 정확히 → L"""
        r = classify_bytes(1024 * 1024, "big_report.pdf")
        assert r.tier == "L"

    # --- Tier XL (> 1 MB) → 차단 ---
    def test_07_tier_xl_just_over_l(self):
        """1025 KB → XL, blocked=True"""
        r = classify_bytes(1025 * 1024, "huge.pdf")
        assert r.tier == "XL"
        assert r.blocked is True
        assert "Team Hub" in r.block_reason
        assert r.estimated_chunks == 0
        assert r.estimated_seconds == 0.0

    def test_08_tier_xl_very_large(self):
        """10 MB → XL, blocked"""
        r = classify_bytes(10 * 1024 * 1024, "archive.pdf")
        assert r.tier == "XL"
        assert r.blocked is True

    # --- Tier Media-L ---
    def test_09_media_image_png(self):
        """.png → Media-L, not blocked"""
        r = classify_bytes(300 * 1024, "scan.png")
        assert r.tier == "Media-L"
        assert not r.blocked
        assert r.estimated_chunks >= 1

    def test_10_media_audio_mp3(self):
        """.mp3 → Media-L, not blocked"""
        r = classify_bytes(2 * 1024 * 1024, "meeting.mp3")
        assert r.tier == "Media-L"
        assert not r.blocked

    # --- 반환 타입 ---
    def test_11_returns_budget_result_type(self):
        """반환값은 항상 BudgetResult"""
        r = classify_bytes(100 * 1024, "sample.txt")
        assert isinstance(r, BudgetResult)


# ---------------------------------------------------------------------------
# classify_file — 실제 임시 파일 I/O (케이스 12)
# ---------------------------------------------------------------------------

class TestClassifyFile:
    def test_12_classify_real_file_tier_s(self, tmp_path):
        """실제 파일 30 KB → S"""
        f = tmp_path / "note.txt"
        f.write_bytes(b"A" * 30 * 1024)
        r = classify_file(f)
        assert r.tier == "S"
        assert r.size_kb == pytest.approx(30.0, abs=0.1)
        assert not r.blocked

    def test_file_not_found_raises(self, tmp_path):
        """존재하지 않는 파일 → FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            classify_file(tmp_path / "ghost.txt")
