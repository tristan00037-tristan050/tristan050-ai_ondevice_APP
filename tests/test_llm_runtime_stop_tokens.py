"""회귀 테스트: LlmRuntime stop token 처리 + 후처리."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.inference.llm_runtime import (
    DEFAULT_STOP_TOKENS,
    LlmRuntime,
    _strip_residual_stop_tokens,
)


# ---------------------------------------------------------------------------
# 단위 테스트: _strip_residual_stop_tokens
# ---------------------------------------------------------------------------
def test_happy_strip_removes_qwen3_stop_token():
    """[/S] 토큰이 응답 내에 잔류할 경우 잘라낸다."""
    raw = "이것은 정상 응답입니다[/S][/S][/S]..."
    assert _strip_residual_stop_tokens(raw) == "이것은 정상 응답입니다"


def test_happy_strip_removes_im_end_token():
    """<|im_end|> 토큰이 잔류할 경우 잘라낸다."""
    raw = "응답 본문<|im_end|>\n추가 텍스트"
    result = _strip_residual_stop_tokens(raw)
    assert "<|im_end|>" not in result
    assert result == "응답 본문"


def test_boundary_strip_no_stop_token_unchanged():
    """stop token이 없는 깨끗한 응답은 그대로 반환한다."""
    clean = "완전히 정상적인 응답 텍스트입니다."
    assert _strip_residual_stop_tokens(clean) == clean


# ---------------------------------------------------------------------------
# 통합 테스트: LlmRuntime.generate() — stub 모드
# ---------------------------------------------------------------------------
def test_happy_stub_response_when_no_model():
    """모델 미설치(stub) 환경에서 generate()가 빈 문자열 없이 응답한다."""
    rt = LlmRuntime(model_path=None)
    result = rt.generate("테스트 쿼리")
    assert isinstance(result, str)
    assert len(result) > 0
    assert "[사용 불가]" in result


# ---------------------------------------------------------------------------
# 통합 테스트: DEFAULT_STOP_TOKENS 목록 검증
# ---------------------------------------------------------------------------
def test_boundary_default_stop_tokens_includes_qwen3():
    """DEFAULT_STOP_TOKENS에 Qwen3 필수 토큰이 모두 포함된다."""
    required = {"[/S]", "[END]", "<|im_end|>", "<|endoftext|>", "</s>"}
    missing = required - set(DEFAULT_STOP_TOKENS)
    assert not missing, f"누락된 stop token: {missing}"


# ---------------------------------------------------------------------------
# 통합 테스트: generate() 이 stop 파라미터를 Llama에 전달하는지 확인
# ---------------------------------------------------------------------------
def test_adv_generate_passes_stop_tokens_to_llama():
    """generate()가 DEFAULT_STOP_TOKENS를 Llama 호출에 실제로 전달한다."""
    mock_llm = MagicMock()
    mock_llm.return_value = {"choices": [{"text": "정상 응답"}]}

    rt = LlmRuntime.__new__(LlmRuntime)
    import threading
    rt._llm = mock_llm
    rt._status = "ready"
    rt._lock = threading.Lock()

    rt.generate("프롬프트")

    assert mock_llm.call_args.kwargs.get("stop") == DEFAULT_STOP_TOKENS, (
        f"stop token이 Llama에 전달되지 않음: {mock_llm.call_args}"
    )
    assert "grammar" not in mock_llm.call_args.kwargs
    assert mock_llm.call_args.kwargs.get("temperature") == 0.2


def test_generate_passes_grammar_only_when_provided():
    """grammar 경로에서만 structured kwargs를 추가한다."""
    mock_llm = MagicMock()
    mock_llm.return_value = {"choices": [{"text": "{\"ok\": true}"}]}

    rt = LlmRuntime.__new__(LlmRuntime)
    import threading
    rt._llm = mock_llm
    rt._status = "ready"
    rt._lock = threading.Lock()

    grammar = object()
    rt.generate("프롬프트", grammar=grammar)

    assert mock_llm.call_args.kwargs["grammar"] is grammar
    assert mock_llm.call_args.kwargs["temperature"] == 0.1
    assert mock_llm.call_args.kwargs["top_p"] == 0.95


def test_boundary_strip_token_at_position_zero_preserved():
    """stop token이 위치 0에 있으면 잘라내지 않는다 — 빈 응답 방지."""
    leading_token = "<|im_end|>본문 텍스트"
    result = _strip_residual_stop_tokens(leading_token)
    assert result == leading_token.strip()


def test_generate_stream_with_cancel_resets_llama_kv_cache_before_stream():
    """generate_stream_with_cancel은 같은 Llama 인스턴스의 이전 KV 캐시를 먼저 비운다."""
    import threading

    events: list[str] = []

    class FakeLlama:
        def reset(self):
            events.append("reset")

        def __call__(self, *args, **kwargs):
            events.append("call")
            assert kwargs["stream"] is True
            yield {"choices": [{"text": "안전"}]}
            yield {"choices": [{"text": " 응답"}]}

    rt = LlmRuntime.__new__(LlmRuntime)
    rt._llm = FakeLlama()
    rt._status = "ready"
    rt._lock = threading.Lock()

    tokens = list(rt.generate_stream_with_cancel("프롬프트", threading.Event()))

    assert tokens == ["안전", " 응답"]
    assert events == ["reset", "call"]


def test_generate_with_cancel_passes_grammar_to_streaming_llama():
    """structured Box4/Box6 경로가 streaming completion에도 grammar를 전달한다."""
    import threading

    seen_kwargs = {}

    class FakeLlama:
        def __call__(self, *args, **kwargs):
            seen_kwargs.update(kwargs)
            yield {"choices": [{"text": "{\"ok\":"}]}
            yield {"choices": [{"text": "true}"}]}

    rt = LlmRuntime.__new__(LlmRuntime)
    rt._llm = FakeLlama()
    rt._status = "ready"
    rt._lock = threading.Lock()

    grammar = object()
    assert rt.generate_with_cancel("프롬프트", threading.Event(), grammar=grammar) == '{"ok":true}'
    assert seen_kwargs["grammar"] is grammar
    assert seen_kwargs["stream"] is True
    assert seen_kwargs["temperature"] == 0.1
    assert seen_kwargs["top_p"] == 0.95


def test_generate_stream_with_cancel_fails_closed_when_reset_missing():
    """reset() 메서드가 없으면 오염 가능 스트리밍을 시작하지 않는다."""
    import threading

    events: list[str] = []

    class ResetMissingLlama:
        def __call__(self, *args, **kwargs):
            events.append("call")
            yield {"choices": [{"text": "오염 가능 응답"}]}

    rt = LlmRuntime.__new__(LlmRuntime)
    rt._llm = ResetMissingLlama()
    rt._status = "ready"
    rt._lock = threading.Lock()

    tokens = list(rt.generate_stream_with_cancel("프롬프트", threading.Event()))

    assert tokens == [LlmRuntime._kv_reset_failed_response()]
    assert events == []


def test_generate_stream_with_cancel_fails_closed_when_reset_raises():
    """reset() 예외가 나면 오염 가능 스트리밍을 시작하지 않는다."""
    import threading

    events: list[str] = []

    class ResetFailingLlama:
        def reset(self):
            events.append("reset")
            raise RuntimeError("reset failed")

        def __call__(self, *args, **kwargs):
            events.append("call")
            yield {"choices": [{"text": "오염 가능 응답"}]}

    rt = LlmRuntime.__new__(LlmRuntime)
    rt._llm = ResetFailingLlama()
    rt._status = "ready"
    rt._lock = threading.Lock()

    tokens = list(rt.generate_stream_with_cancel("프롬프트", threading.Event()))

    assert tokens == [LlmRuntime._kv_reset_failed_response()]
    assert events == ["reset"]
