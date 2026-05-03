"""결함 B 회귀 테스트: 공유 모델 싱글톤 — 1회 로드, 동시 호출 안전성."""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import butler_sidecar as sidecar
from butler_pc_core.inference.llm_runtime import LlmRuntime


# ---------------------------------------------------------------------------
# 픽스처: 테스트마다 싱글톤 초기화 격리
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_singleton():
    """각 테스트 전후로 _SHARED_LLM을 원래 상태로 복원한다."""
    original = sidecar._SHARED_LLM
    yield
    sidecar._SHARED_LLM = original


# ---------------------------------------------------------------------------
# 단위 테스트: _init_shared_llm
# ---------------------------------------------------------------------------
def test_happy_init_shared_llm_creates_instance():
    """모델 경로 미설정 시 _init_shared_llm 이 stub 모드 LlmRuntime 을 생성한다."""
    sidecar._SHARED_LLM = None
    env_backup = os.environ.pop("BUTLER_MODEL_PATH", None)
    try:
        sidecar._init_shared_llm()
        assert sidecar._SHARED_LLM is not None
        assert isinstance(sidecar._SHARED_LLM, LlmRuntime)
        assert sidecar._SHARED_LLM.status == "no_model"
    finally:
        if env_backup is not None:
            os.environ["BUTLER_MODEL_PATH"] = env_backup


def test_happy_init_shared_llm_called_twice_updates_singleton():
    """_init_shared_llm 재호출 시 최신 인스턴스로 교체된다."""
    sidecar._SHARED_LLM = None
    os.environ.pop("BUTLER_MODEL_PATH", None)
    sidecar._init_shared_llm()
    first = sidecar._SHARED_LLM
    sidecar._init_shared_llm()
    second = sidecar._SHARED_LLM
    # 두 인스턴스는 다른 객체여야 하며 둘 다 유효
    assert first is not second
    assert second is not None
    assert second.status == "no_model"


# ---------------------------------------------------------------------------
# 단위 테스트: _real_chunk_work_inprocess — stub 모드
# ---------------------------------------------------------------------------
@dataclass
class _TestParams:
    query: str = ""
    card_mode: str = "free"
    total_chunks: int = 1
    output_dir: str = "."
    file_paths: list = field(default_factory=list)


def test_happy_inprocess_returns_stub_when_no_model():
    """모델 없는 환경에서 _real_chunk_work_inprocess 가 stub 응답을 반환한다."""
    sidecar._SHARED_LLM = LlmRuntime(model_path=None)  # stub 모드 고정

    async def _run():
        params = _TestParams(query="테스트 쿼리", card_mode="free")
        result = await sidecar._real_chunk_work_inprocess(params, 0, 30.0)
        assert isinstance(result, str)
        assert len(result) > 0

    asyncio.run(_run())


def test_happy_inprocess_fallback_when_singleton_none():
    """싱글톤 None 상태에서도 인라인 초기화로 stub 응답을 반환한다."""
    sidecar._SHARED_LLM = None
    os.environ.pop("BUTLER_MODEL_PATH", None)

    async def _run():
        params = _TestParams(query="폴백 테스트", card_mode="free")
        result = await sidecar._real_chunk_work_inprocess(params, 0, 30.0)
        assert isinstance(result, str)
        assert len(result) > 0

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 동시 호출 안전성: asyncio.Lock 직렬화 확인
# ---------------------------------------------------------------------------
def test_adv_concurrent_inprocess_calls_all_succeed():
    """동시 3개 호출 — LlmRuntime threading.Lock 직렬화, 모두 정상 완료."""
    sidecar._SHARED_LLM = LlmRuntime(model_path=None)

    async def _run():
        params = _TestParams(query="동시 호출 테스트", card_mode="free")
        tasks = [
            asyncio.create_task(sidecar._real_chunk_work_inprocess(params, i, 30.0))
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, str) and len(r) > 0

    asyncio.run(_run())


def test_adv_inprocess_uses_shared_singleton_not_new_instance():
    """_real_chunk_work_inprocess 가 _SHARED_LLM 인스턴스를 재사용하는지 확인.
    generate() 호출 횟수로 검증 — 새 LlmRuntime 이 생성되면 mock 이 호출되지 않는다."""
    mock_llm = MagicMock(spec=LlmRuntime)
    mock_llm.status = "ready"
    mock_llm.generate.return_value = "mock 응답"
    sidecar._SHARED_LLM = mock_llm

    async def _run():
        params = _TestParams(query="싱글톤 확인", card_mode="free")
        result = await sidecar._real_chunk_work_inprocess(params, 0, 30.0)
        return result

    result = asyncio.run(_run())
    assert mock_llm.generate.called, "싱글톤의 generate()가 호출되지 않음 — 새 인스턴스 생성 버그"
    assert result == "mock 응답"


# ---------------------------------------------------------------------------
# 모델 로딩 1회 확인: 스레드 카운트 기반
# ---------------------------------------------------------------------------
def test_boundary_model_loaded_once_across_multiple_calls():
    """동일 LlmRuntime 인스턴스로 N번 generate 호출 — 인스턴스 생성은 1회."""
    call_count = 0
    original_init = LlmRuntime.__init__

    def _counting_init(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        original_init(self, *args, **kwargs)

    with patch.object(LlmRuntime, "__init__", _counting_init):
        sidecar._SHARED_LLM = None
        os.environ.pop("BUTLER_MODEL_PATH", None)
        sidecar._init_shared_llm()
        init_count_after_singleton = call_count

        async def _run_three():
            params = _TestParams(query="반복 쿼리", card_mode="free")
            for _ in range(3):
                await sidecar._real_chunk_work_inprocess(params, 0, 30.0)

        asyncio.run(_run_three())

    # 싱글톤 초기화 1회 + 추가 생성 없음
    assert init_count_after_singleton == 1, "싱글톤 초기화 횟수가 1이어야 함"
    assert call_count == 1, f"LlmRuntime 생성 {call_count}회 — 모델 재로드 버그"
