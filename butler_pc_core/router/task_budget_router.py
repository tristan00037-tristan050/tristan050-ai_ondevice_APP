"""
task_budget_router.py
=====================
Butler PC Core – 작업 등급 분류기

Tier 정의 (파일 경로 기반, v1)
---------
S       : ≤ 50 KB   – 즉시 처리
M       : ≤ 200 KB  – 단일 청크 처리
L       : ≤ 1 MB    – 멀티청크 처리
XL      : > 1 MB    – 즉시 차단 + Team Hub 안내
Media-L : 음성·이미지 파일 – 별도 미디어 파이프라인
empty   : 0 바이트  – 처리 거부

Route 정의 (바이트·토큰·허브 페어링 기반, v2 — D-1-A)
---------
PC_DIRECT              : ≤ 50 KB  또는 ≤ 8K tokens
PC_CHUNKED             : ≤ 200 KB 또는 ≤ 24K tokens 또는 ≤ 15 페이지
TEAM_HUB_RECOMMENDED   : ≤ 1 MB  + hub_paired=True
PC_PREVIEW_TEAM_HUB    : ≤ 1 MB  + hub_paired=False
REFUSE_TEAM_HUB        : > 1 MB

변경 이력
---------
v1.1.0 (Day 1.5 hotfix): 비파일 경로 사전 거절 + 빈 파일 처리
v2.0.0 (D-1-A PR #667): Route/TaskBudget/decide_task_budget 추가
"""
from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from enum import Enum
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

Tier = Literal["S", "M", "L", "XL", "Media-L", "empty"]


# ---------------------------------------------------------------------------
# 커스텀 예외
# ---------------------------------------------------------------------------

class NotAFileError(OSError):
    """경로가 존재하지만 일반 파일이 아닌 경우 (심볼릭 링크 등)."""


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
    IsADirectoryError
        경로가 디렉터리일 때.
    NotAFileError
        경로가 심볼릭 링크 등 일반 파일이 아닐 때.
    """
    path = Path(file_path)

    # ── 존재 여부
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    # ── 파일 종류 검증
    if path.is_dir():
        raise IsADirectoryError(
            f"폴더가 아닌 개별 파일을 첨부해 주세요: {file_path}"
        )
    if not path.is_file():
        raise NotAFileError(
            f"일반 파일이 아닙니다 (심볼릭 링크 등): {file_path}"
        )

    # ── 빈 파일
    size_bytes = path.stat().st_size
    if size_bytes == 0:
        return BudgetResult(
            tier="empty",
            size_kb=0.0,
            estimated_chunks=0,
            estimated_seconds=0.0,
            blocked=True,
            block_reason="내용이 없는 파일입니다. 내용을 추가한 후 다시 시도하세요.",
        )
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


# ---------------------------------------------------------------------------
# v2: Route / TaskBudget / decide_task_budget (D-1-A)
# ---------------------------------------------------------------------------

class Route(str, Enum):
    PC_DIRECT = "pc_direct"
    PC_CHUNKED = "pc_chunked_with_progress"
    TEAM_HUB_RECOMMENDED = "team_hub_recommended"
    PC_PREVIEW_TEAM_HUB = "pc_preview_with_hub_recommendation"
    REFUSE_TEAM_HUB = "refuse_with_team_hub_message"


@dataclass(frozen=True)
class TaskBudget:
    file_bytes: int
    estimated_tokens: int
    page_count: int
    route: Route
    max_wall_time_sec: int
    reason: str
    user_message: str


_ROUTE_THRESHOLDS = {
    "direct_bytes": 50 * 1024,        # 50 KB
    "direct_tokens": 8_000,
    "chunked_bytes": 200 * 1024,       # 200 KB
    "chunked_tokens": 24_000,
    "chunked_pages": 15,
    "refuse_bytes": 1024 * 1024,       # 1 MB
}

_USER_MESSAGES: dict[Route, str] = {
    Route.PC_DIRECT: "PC에서 안전하게 처리합니다.",
    Route.PC_CHUNKED: "단계별 분할 처리합니다.",
    Route.TEAM_HUB_RECOMMENDED: "이 자료는 팀 허브 PC에서 더 안정적으로 처리됩니다.",
    Route.PC_PREVIEW_TEAM_HUB: (
        "PC에서는 미리보기 요약만 제공합니다. "
        "전체 분석은 팀 허브 연결 후 가능합니다."
    ),
    Route.REFUSE_TEAM_HUB: (
        "이 자료는 PC Core 단독 처리 권장 범위를 초과합니다. "
        "팀 허브 PC에서 처리해야 합니다."
    ),
}


def decide_task_budget(
    file_bytes: int,
    estimated_tokens: int,
    page_count: int = 0,
    hub_paired: bool = False,
    task_type: str = "general",
) -> TaskBudget:
    """자료 크기·토큰·허브 페어링 상태로 라우팅을 결정한다.

    Parameters
    ----------
    file_bytes       : 첨부 파일 합계 바이트 (없으면 0)
    estimated_tokens : 예상 토큰 수 (없으면 0)
    page_count       : 페이지 수 (PDF 파서 미구현 시 0)
    hub_paired       : Team Hub PC와 페어링 여부
    task_type        : 카드 모드 또는 태스크 유형 (현재 미사용, 확장용)
    """
    t = _ROUTE_THRESHOLDS

    # 텍스트 전용(파일 없음) 또는 초소형 → 즉시 처리
    is_direct = (
        (file_bytes == 0 and estimated_tokens == 0)
        or file_bytes <= t["direct_bytes"]
        or estimated_tokens <= t["direct_tokens"]
    )
    if is_direct:
        return TaskBudget(
            file_bytes=file_bytes,
            estimated_tokens=estimated_tokens,
            page_count=page_count,
            route=Route.PC_DIRECT,
            max_wall_time_sec=60,
            reason="file_bytes ≤ 50 KB 또는 tokens ≤ 8K",
            user_message=_USER_MESSAGES[Route.PC_DIRECT],
        )

    # 중형 → 분할 청크 처리
    is_chunked = (
        file_bytes <= t["chunked_bytes"]
        or estimated_tokens <= t["chunked_tokens"]
        or (page_count > 0 and page_count <= t["chunked_pages"])
    )
    if is_chunked:
        return TaskBudget(
            file_bytes=file_bytes,
            estimated_tokens=estimated_tokens,
            page_count=page_count,
            route=Route.PC_CHUNKED,
            max_wall_time_sec=180,
            reason="file_bytes ≤ 200 KB 또는 tokens ≤ 24K 또는 pages ≤ 15",
            user_message=_USER_MESSAGES[Route.PC_CHUNKED],
        )

    # 1 MB 초과 → 무조건 거부
    if file_bytes > t["refuse_bytes"]:
        return TaskBudget(
            file_bytes=file_bytes,
            estimated_tokens=estimated_tokens,
            page_count=page_count,
            route=Route.REFUSE_TEAM_HUB,
            max_wall_time_sec=3,
            reason="file_bytes > 1 MB",
            user_message=_USER_MESSAGES[Route.REFUSE_TEAM_HUB],
        )

    # 200 KB ~ 1 MB 범위 → 허브 페어링 여부로 분기
    if hub_paired:
        return TaskBudget(
            file_bytes=file_bytes,
            estimated_tokens=estimated_tokens,
            page_count=page_count,
            route=Route.TEAM_HUB_RECOMMENDED,
            max_wall_time_sec=3,
            reason="200 KB < file_bytes ≤ 1 MB, hub_paired=True",
            user_message=_USER_MESSAGES[Route.TEAM_HUB_RECOMMENDED],
        )

    return TaskBudget(
        file_bytes=file_bytes,
        estimated_tokens=estimated_tokens,
        page_count=page_count,
        route=Route.PC_PREVIEW_TEAM_HUB,
        max_wall_time_sec=30,
        reason="200 KB < file_bytes ≤ 1 MB, hub_paired=False",
        user_message=_USER_MESSAGES[Route.PC_PREVIEW_TEAM_HUB],
    )


# ---------------------------------------------------------------------------
# v1: classify_bytes (기존 API — 하위 호환 유지)
# ---------------------------------------------------------------------------
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
