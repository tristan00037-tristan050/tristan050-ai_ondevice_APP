"""
timeout_controller.py
=====================
Butler PC Core – Timeout / Cancel / Partial Result 컨트롤러

동작 방식
---------
- hard timeout  : 180 초 (전체 작업 한도)
- chunk timeout : 45 초  (청크 단위 한도)
- 중단 발생 시  : partial_result.json 자동 생성 후 PartialResultError 발생

스레드 안전성
-----------
TimeoutController 인스턴스는 한 작업에만 사용한다.
동시 다발 사용은 보장하지 않는다.
"""
from __future__ import annotations

import json
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
HARD_TIMEOUT_SEC  = 180.0
CHUNK_TIMEOUT_SEC = 45.0


# ---------------------------------------------------------------------------
# 안전 직렬화 헬퍼
# ---------------------------------------------------------------------------

def _safe_json_default(obj: Any) -> Any:
    """JSON 직렬화 불가능 객체를 안전하게 변환."""
    if isinstance(obj, (set, frozenset)):
        return {"__type__": "set", "values": sorted(obj, key=str)}
    if isinstance(obj, bytes):
        return {
            "__type__": "bytes",
            "size": len(obj),
            "preview": obj[:64].hex(),
        }
    if hasattr(obj, "__dict__"):
        return {
            "__type__": obj.__class__.__name__,
            "repr": repr(obj)[:200],
        }
    return {"__type__": "unserializable", "repr": repr(obj)[:200]}


# ---------------------------------------------------------------------------
# 예외
# ---------------------------------------------------------------------------
class PartialResultError(RuntimeError):
    """partial_result.json 이 생성된 뒤 발생하는 중단 신호."""
    def __init__(self, message: str, partial_path: Path):
        super().__init__(message)
        self.partial_path = partial_path


class HardTimeoutError(PartialResultError):
    """전체 작업 hard_timeout(180초) 초과."""


class ChunkTimeoutError(PartialResultError):
    """단일 청크 chunk_timeout(45초) 초과."""


class UserCancelledError(PartialResultError):
    """사용자가 명시적으로 취소."""


# 하위 호환 별칭
TaskCancelledError = UserCancelledError


# ---------------------------------------------------------------------------
# 결과 컨테이너
# ---------------------------------------------------------------------------
@dataclass
class ChunkResult:
    index: int
    content: Any
    elapsed_sec: float


@dataclass
class PartialResult:
    task_id: str
    completed_chunks: list[ChunkResult] = field(default_factory=list)
    total_elapsed_sec: float = 0.0
    abort_reason: str = ""        # "hard_timeout" | "chunk_timeout" | "cancelled"
    partial: bool = True


# ---------------------------------------------------------------------------
# 컨트롤러
# ---------------------------------------------------------------------------
class TimeoutController:
    """
    작업 전체 및 청크 단위 timeout 관리자.

    Parameters
    ----------
    task_id : str
        현재 작업을 식별하는 고유 ID.
    output_dir : str | Path
        partial_result.json 이 저장될 디렉터리.
    hard_timeout : float
        전체 작업 제한 시간(초). 기본 180.
    chunk_timeout : float
        청크 단위 제한 시간(초). 기본 45.

    Example
    -------
    >>> ctrl = TimeoutController("task-001", "/tmp")
    >>> with ctrl.run_chunk(0) as ctx:
    ...     result = heavy_work()
    ...     ctx.set_result(result)
    """

    def __init__(
        self,
        task_id: str,
        output_dir: str | Path = ".",
        hard_timeout: float = HARD_TIMEOUT_SEC,
        chunk_timeout: float = CHUNK_TIMEOUT_SEC,
    ):
        self.task_id      = task_id
        self.output_dir   = Path(output_dir)
        self.hard_timeout = hard_timeout
        self.chunk_timeout = chunk_timeout

        self._start_time  = time.monotonic()
        self._cancelled   = threading.Event()
        self._partial     = PartialResult(task_id=task_id)
        self._lock        = threading.Lock()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    def cancel(self):
        """외부에서 즉시 작업을 취소한다."""
        self._cancelled.set()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def check_hard_timeout(self):
        """호출 지점에서 hard timeout 초과 여부를 확인한다."""
        if self._cancelled.is_set():
            self._abort("cancelled")
        if self.elapsed > self.hard_timeout:
            self._abort("hard_timeout")

    def run_chunk(self, chunk_index: int) -> "_ChunkContext":
        """청크 처리 컨텍스트 매니저를 반환한다."""
        self.check_hard_timeout()
        return _ChunkContext(self, chunk_index)

    def run_with_chunk_timeout(
        self,
        chunk_index: int,
        fn: Callable[[], Any],
    ) -> Any:
        """
        fn 을 별도 스레드에서 실행하고 chunk_timeout 초과 시 ChunkTimeoutError 를 발생시킨다.

        Parameters
        ----------
        chunk_index : int
        fn : Callable[[], Any]
            순수 함수여야 한다 (예외가 있어도 catch 가능).
        """
        self.check_hard_timeout()
        result_box: list[Any] = []
        exc_box:    list[BaseException] = []

        def _target():
            try:
                result_box.append(fn())
            except Exception as exc:  # noqa: BLE001
                exc_box.append(exc)

        t = threading.Thread(target=_target, daemon=True)
        t0 = time.monotonic()
        t.start()
        t.join(timeout=self.chunk_timeout)

        if t.is_alive():
            # 스레드는 daemon=True 이므로 프로세스 종료 시 회수됨
            self._abort("chunk_timeout")

        elapsed = time.monotonic() - t0
        if exc_box:
            raise exc_box[0]

        content = result_box[0] if result_box else None
        with self._lock:
            self._partial.completed_chunks.append(
                ChunkResult(index=chunk_index, content=content, elapsed_sec=round(elapsed, 3))
            )
        return content

    def finalize(self) -> PartialResult:
        """성공적으로 완료된 경우 partial 플래그를 False 로 설정하고 반환한다."""
        with self._lock:
            self._partial.total_elapsed_sec = round(self.elapsed, 3)
            self._partial.partial = False
        return self._partial

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------
    def _abort(self, reason: str) -> None:
        """partial_result.json 저장 후 적절한 예외를 발생시킨다."""
        with self._lock:
            self._partial.abort_reason     = reason
            self._partial.total_elapsed_sec = round(self.elapsed, 3)

        path = self._save_partial()

        if reason == "hard_timeout":
            raise HardTimeoutError(
                f"[hard_timeout] {self.hard_timeout}초 초과 → {path}", path
            )
        if reason == "chunk_timeout":
            raise ChunkTimeoutError(
                f"[chunk_timeout] {self.chunk_timeout}초 초과 → {path}", path
            )
        raise UserCancelledError(f"[cancelled] 작업 취소 → {path}", path)

    def _save_partial(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"partial_result_{self.task_id}.json"
        payload = {
            "task_id":           self._partial.task_id,
            "partial":           self._partial.partial,
            "abort_reason":      self._partial.abort_reason,
            "total_elapsed_sec": self._partial.total_elapsed_sec,
            "completed_chunks":  [
                {
                    "index":       c.index,
                    "elapsed_sec": c.elapsed_sec,
                    "content":     c.content,
                }
                for c in self._partial.completed_chunks
            ],
        }
        try:
            text = json.dumps(payload, ensure_ascii=False, indent=2,
                              default=_safe_json_default)
            path.write_text(text, encoding="utf-8")
        except Exception as primary_exc:  # noqa: BLE001
            # 직렬화 자체 실패 → 최소 메타데이터 fallback
            fallback = {
                "task_id":         self._partial.task_id,
                "partial":         True,
                "abort_reason":    self._partial.abort_reason,
                "total_elapsed_sec": self._partial.total_elapsed_sec,
                "completed_count": len(self._partial.completed_chunks),
                "serialization_error": {
                    "error_class": type(primary_exc).__name__,
                    "message":     str(primary_exc)[:300],
                },
                "fallback":        True,
                "saved_at":        datetime.now(timezone.utc).isoformat(),
            }
            try:
                path.write_text(
                    json.dumps(fallback, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001
                # 파일 쓰기 자체 실패 시에도 경로는 반환 (호출자가 처리)
                pass
        return path


# ---------------------------------------------------------------------------
# 청크 컨텍스트 매니저 (동기식 단순 버전)
# ---------------------------------------------------------------------------
class _ChunkContext:
    """with ctrl.run_chunk(i) as ctx: ctx.set_result(value)"""

    def __init__(self, ctrl: TimeoutController, index: int):
        self._ctrl  = ctrl
        self._index = index
        self._t0    = 0.0
        self._value: Any = None

    def set_result(self, value: Any):
        self._value = value

    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.monotonic() - self._t0
        if elapsed > self._ctrl.chunk_timeout:
            self._ctrl._abort("chunk_timeout")  # noqa: SLF001
        if exc_type is None:
            with self._ctrl._lock:  # noqa: SLF001
                self._ctrl._partial.completed_chunks.append(
                    ChunkResult(index=self._index, content=self._value, elapsed_sec=round(elapsed, 3))
                )
        return False  # 예외 전파
