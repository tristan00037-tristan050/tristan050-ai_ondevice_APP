"""
task_budget_router.py
=====================
Butler PC Core – 작업 등급 분류기

Tier 정의
---------
S       : ≤ 50 KB   – 즉시 처리
M       : ≤ 200 KB  – 단일 청크 처리
L       : ≤ 1 MB    – 멀티청크 처리
XL      : > 1 MB    – 즉시 차단 + Team Hub 안내
Media-L : 음성·이미지 파일 – 별도 미디어 파이프라인
"""
from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
_TIER_S_KB  = 50
_TIER_M_KB  = 200
_TIER_L_KB  = 1024  # 1 MB

_MEDIA_MIME_PREFIXES = ("audio/", "video/")
_MEDIA_EXTENSIONS    = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac",
    ".mp4", ".mov", ".avi", ".mkv",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic",
}

# chunk size assumptions for estimation
_CHUNK_KB   = 50        # KB per chunk
_SEC_PER_CHUNK = 4.0    # seconds per chunk (conservative)

_TEAM_HUB_BLOCK_MSG = (
    "파일 크기가 1 MB를 초과하여 Butler PC Core에서 직접 처리할 수 없습니다. "
    "Team Hub에 작업을 위임하거나 파일을 분할하여 다시 시도하세요. "
    "[Team Hub 연결 → /api/teamhub/delegate]"
)

Tier = Literal["S", "M", "L", "XL", "Media-L"]


# ---------------------------------------------------------------------------
# 결과 데이터클래스
# ---------------------------------------------------------------------------
@dataclass
class BudgetResult:
    tier: Tier
    size_kb: float
    estimated_chunks: int
    estimated_seconds: float
    blocked: bool
    block_reason: str


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------
def classify_file(file_path: str | os.PathLike) -> BudgetResult:
    """
    파일 경로를 받아 작업 등급을 분류한다.

    Parameters
    ----------
    file_path : str | PathLike
        분류할 파일의 절대·상대 경로.

    Returns
    -------
    BudgetResult
        tier, size_kb, estimated_chunks, estimated_seconds, blocked, block_reason

    Raises
    ------
    FileNotFoundError
        파일이 존재하지 않을 때.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    size_bytes = path.stat().st_size
    size_kb    = size_bytes / 1024.0

    # Media 판별 (MIME 또는 확장자 기준)
    mime_type, _ = mimetypes.guess_type(str(path))
    is_media = (
        path.suffix.lower() in _MEDIA_EXTENSIONS
        or (mime_type is not None and any(mime_type.startswith(p) for p in _MEDIA_MIME_PREFIXES))
    )

    if is_media:
        chunks  = max(1, int(size_kb / _CHUNK_KB))
        seconds = chunks * _SEC_PER_CHUNK
        return BudgetResult(
            tier="Media-L",
            size_kb=round(size_kb, 2),
            estimated_chunks=chunks,
            estimated_seconds=round(seconds, 1),
            blocked=False,
            block_reason="",
        )

    # 텍스트/문서 등급 분류
    if size_kb <= _TIER_S_KB:
        tier = "S"
    elif size_kb <= _TIER_M_KB:
        tier = "M"
    elif size_kb <= _TIER_L_KB:
        tier = "L"
    else:
        tier = "XL"

    blocked      = tier == "XL"
    block_reason = _TEAM_HUB_BLOCK_MSG if blocked else ""
    chunks       = max(1, int(size_kb / _CHUNK_KB)) if not blocked else 0
    seconds      = chunks * _SEC_PER_CHUNK if not blocked else 0.0

    return BudgetResult(
        tier=tier,
        size_kb=round(size_kb, 2),
        estimated_chunks=chunks,
        estimated_seconds=round(seconds, 1),
        blocked=blocked,
        block_reason=block_reason,
    )


def classify_bytes(size_bytes: int, filename: str = "unknown.txt") -> BudgetResult:
    """
    실제 파일 없이 바이트 크기와 파일명만으로 등급을 분류한다.
    테스트·precheck 미리보기용.
    """
    size_kb = size_bytes / 1024.0

    path = Path(filename)
    mime_type, _ = mimetypes.guess_type(filename)
    is_media = (
        path.suffix.lower() in _MEDIA_EXTENSIONS
        or (mime_type is not None and any(mime_type.startswith(p) for p in _MEDIA_MIME_PREFIXES))
    )

    if is_media:
        chunks  = max(1, int(size_kb / _CHUNK_KB))
        seconds = chunks * _SEC_PER_CHUNK
        return BudgetResult(
            tier="Media-L",
            size_kb=round(size_kb, 2),
            estimated_chunks=chunks,
            estimated_seconds=round(seconds, 1),
            blocked=False,
            block_reason="",
        )

    if size_kb <= _TIER_S_KB:
        tier = "S"
    elif size_kb <= _TIER_M_KB:
        tier = "M"
    elif size_kb <= _TIER_L_KB:
        tier = "L"
    else:
        tier = "XL"

    blocked      = tier == "XL"
    block_reason = _TEAM_HUB_BLOCK_MSG if blocked else ""
    chunks       = max(1, int(size_kb / _CHUNK_KB)) if not blocked else 0
    seconds      = chunks * _SEC_PER_CHUNK if not blocked else 0.0

    return BudgetResult(
        tier=tier,
        size_kb=round(size_kb, 2),
        estimated_chunks=chunks,
        estimated_seconds=round(seconds, 1),
        blocked=blocked,
        block_reason=block_reason,
    )
