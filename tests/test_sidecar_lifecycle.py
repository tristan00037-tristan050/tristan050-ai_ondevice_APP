"""회귀 테스트: sidecar lifecycle — subprocess 격리 + timeout 강제 종료."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# 테스트용 미니 _AnalyzeParams (butler_sidecar 임포트 없이 독립 실행 가능)
# ---------------------------------------------------------------------------
@dataclass
class _TestParams:
    query: str = ""
    card_mode: str = "free"
    total_chunks: int = 1
    output_dir: str = "."
    file_paths: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
async def _run_isolated(params: _TestParams, chunk_idx: int, timeout_sec: float) -> str:
    """chunk_worker.py 경로를 직접 사용하는 격리 실행 함수."""
    worker = _REPO_ROOT / "butler_pc_core" / "inference" / "chunk_worker.py"
    params_json = json.dumps(params.__dict__, default=str)
    cmd = [
        sys.executable,
        str(worker),
        "--params", params_json,
        "--chunk-idx", str(chunk_idx),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        result = json.loads(stdout.decode())
        return str(result.get("result", ""))
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        raise


# ---------------------------------------------------------------------------
# 헬퍼: slow subprocess — 직접 timeout+kill 패턴 검증용
# ---------------------------------------------------------------------------
async def _run_slow_process(timeout_sec: float) -> str:
    """60초 sleep 프로세스를 timeout_sec 후 SIGKILL → TimeoutError re-raise."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        return stdout.decode()
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        raise


# ---------------------------------------------------------------------------
# 결함 2 회귀: timeout 시 subprocess 강제 종료 → 누수 없음
# ---------------------------------------------------------------------------
def test_adv_chunk_timeout_kills_subprocess():
    """60초 sleep 프로세스를 1초 timeout으로 강제 종료 — 누수 없이 3초 내 반환."""

    async def _run():
        start = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            await _run_slow_process(timeout_sec=1.0)
        elapsed = time.monotonic() - start
        # 60초 기다리지 않고 1초 + 약간의 여유 안에 반환
        assert elapsed < 3.0, f"강제 종료 실패 — {elapsed:.1f}초 소요"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 경계 테스트: worker 정상 완료 (llama-cpp 미설치 → stub 응답)
# ---------------------------------------------------------------------------
def test_happy_real_chunk_work_isolated_completes():
    """llama-cpp-python 미설치 환경에서도 stub 응답이 정상 반환된다."""

    async def _run():
        params = _TestParams(query="안녕하세요", card_mode="free")
        result = await _run_isolated(params, chunk_idx=0, timeout_sec=30.0)
        assert isinstance(result, str)
        assert len(result) > 0

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 경계 테스트: 동시 청크 — 하나 timeout 시 다른 청크 영향 없음
# ---------------------------------------------------------------------------
def test_boundary_concurrent_chunks_no_lock_starvation():
    """A(60초 sleep, 1초 timeout) + B(즉시 완료) 동시 실행 — B는 영향 없이 완료."""

    async def _run():
        task_a = asyncio.create_task(_run_slow_process(timeout_sec=1.0))
        params_b = _TestParams(query="정상 쿼리", card_mode="free")
        task_b = asyncio.create_task(_run_isolated(params_b, 1, timeout_sec=30.0))

        results = await asyncio.gather(task_a, task_b, return_exceptions=True)

        # A: TimeoutError 예상
        assert isinstance(results[0], asyncio.TimeoutError), f"A가 timeout 아님: {results[0]}"
        # B: 정상 문자열 예상
        assert isinstance(results[1], str) and len(results[1]) > 0, f"B 실패: {results[1]}"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 결함 2 회귀: wrapper exec (& 없음) → python3가 wrapper PID 점유
# ---------------------------------------------------------------------------
def test_adv_wrapper_no_orphan_after_kill():
    """결함 2 회귀: wrapper에 & 없으면 exec 후 wrapper PID = python3 PID.
    kill 시 sidecar도 함께 종료 → orphan 없음."""
    wrapper = "/Applications/Butler.app/Contents/MacOS/butler-sidecar"
    if not os.path.exists(wrapper):
        pytest.skip("Butler.app 미설치 환경")

    proc = subprocess.Popen(
        [wrapper, "--port", "5911", "--host", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wrapper_pid = proc.pid
    time.sleep(3)

    # exec 정상: wrapper PID의 command가 python3를 포함해야 함
    ps_result = subprocess.run(
        ["ps", "-p", str(wrapper_pid), "-o", "pid=,command="],
        capture_output=True,
        text=True,
    )
    assert ps_result.returncode == 0, "wrapper 프로세스 없음 — exec & 버그 재발"
    assert "python" in ps_result.stdout.lower(), (
        f"exec 실패 — wrapper PID가 python3가 아님: {ps_result.stdout!r}"
    )

    # kill 후 포트 5911 잔여 프로세스 없어야 함
    proc.kill()
    time.sleep(1)

    lsof_result = subprocess.run(
        ["lsof", "-ti", ":5911"],
        capture_output=True,
        text=True,
    )
    assert lsof_result.stdout.strip() == "", (
        f"orphan sidecar 발견 (포트 5911 점유): {lsof_result.stdout.strip()}"
    )
