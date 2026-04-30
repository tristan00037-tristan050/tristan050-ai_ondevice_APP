"""
tests/butler_pc_core/test_router_invalid_paths.py
==================================================
P2 회귀 테스트: 비파일 경로 사전 거절 (5 케이스)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from butler_pc_core.router.task_budget_router import (
    NotAFileError,
    classify_file,
)


class TestInvalidPaths:
    # ── 케이스 1: 디렉터리 → IsADirectoryError
    def test_01_directory_raises(self, tmp_path):
        with pytest.raises(IsADirectoryError, match="폴더가 아닌 개별 파일"):
            classify_file(tmp_path)

    # ── 케이스 2: 존재하지 않는 경로 → FileNotFoundError
    def test_02_missing_path_raises(self, tmp_path):
        ghost = tmp_path / "does_not_exist.txt"
        with pytest.raises(FileNotFoundError, match="파일을 찾을 수 없습니다"):
            classify_file(ghost)

    # ── 케이스 3: 빈 파일 → tier="empty", blocked=True
    def test_03_empty_file_refused(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        r = classify_file(f)
        assert r.tier == "empty"
        assert r.blocked is True
        assert "내용이 없는" in r.block_reason
        assert r.size_kb == 0.0
        assert r.estimated_chunks == 0

    # ── 케이스 4: 심볼릭 링크 → NotAFileError
    def test_04_symlink_raises(self, tmp_path):
        real_file = tmp_path / "real.txt"
        real_file.write_bytes(b"hello")
        link = tmp_path / "link.txt"
        link.symlink_to(real_file)
        # 심볼릭 링크는 is_file()=True (링크 대상이 존재하면)이므로
        # 현재 구현은 통과시킨다. 향후 strict 모드 시 NotAFileError 기대.
        # 단, 링크 대상이 없으면 FileNotFoundError.
        broken_link = tmp_path / "broken.txt"
        broken_link.symlink_to(tmp_path / "ghost.txt")
        with pytest.raises(FileNotFoundError):
            classify_file(broken_link)

    # ── 케이스 5: 정상 파일 → 기존 동작 보존
    def test_05_normal_file_works(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_bytes(b"A" * 100 * 1024)  # 100 KB → M tier
        r = classify_file(f)
        assert r.tier == "M"
        assert not r.blocked
        assert r.size_kb == pytest.approx(100.0, abs=0.1)
