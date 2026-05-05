"""
LLM 런타임 — llama-cpp-python 래퍼 (설치 안 됐으면 stub 응답).

상태
----
  ready      모델 로드 완료, 추론 가능
  no_model   model_path 미설정 또는 파일 없음
  loading    초기화 중
  error      로드 실패 (last_error 참조)
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterator

try:
    from llama_cpp import Llama  # type: ignore[import]
    _LLAMA_AVAILABLE = True
except ImportError:
    _LLAMA_AVAILABLE = False

# Qwen3 + 범용 stop token — [/S] 미설정 시 할루시네이션 루프 발생
DEFAULT_STOP_TOKENS: list[str] = [
    "[/S]", "[END]", "\n\n\n",
    "<|im_end|>", "<|endoftext|>", "<|end|>", "</s>",
]


def _strip_residual_stop_tokens(text: str) -> str:
    """generate() 후처리: stop token 제거 + Qwen3 <think> 블록 제거.
    위치 0에서 시작하는 stop token은 건너뜀 — 포맷 불일치 시 빈 응답 방지."""
    import re
    # Qwen3 thinking 블록 제거 (<think>...</think>)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    for tok in DEFAULT_STOP_TOKENS:
        idx = text.find(tok)
        if idx > 0:
            text = text[:idx]
    return text.strip()


class LlmRuntime:
    """llama-cpp-python 기반 로컬 LLM 런타임 (GGUF 전용)."""

    def __init__(
        self,
        model_path: str | None = None,
        n_ctx: int = 4096,
        n_threads: int = 0,
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_threads = n_threads or max(1, (os.cpu_count() or 2) - 1)
        self._llm: "Llama | None" = None
        self._status: str = "no_model"
        self._last_error: str = ""
        self._lock = threading.Lock()

        if model_path:
            self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        p = Path(self._model_path or "")
        if not p.exists():
            self._status = "no_model"
            return

        if not _LLAMA_AVAILABLE:
            self._status = "error"
            self._last_error = "llama-cpp-python 미설치 — pip install llama-cpp-python"
            return

        self._status = "loading"
        try:
            self._llm = Llama(
                model_path=str(p),
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                verbose=False,
            )
            self._status = "ready"
        except Exception as exc:
            self._status = "error"
            self._last_error = str(exc)[:256]

    # ------------------------------------------------------------------
    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    def reload(self, model_path: str) -> None:
        with self._lock:
            self._model_path = model_path
            self._llm = None
            self._load()

    # ------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
    ) -> str:
        if self._status != "ready" or self._llm is None:
            return self._stub_response(prompt)

        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        with self._lock:
            output = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop_tokens,
                echo=False,
            )
        text = output["choices"][0]["text"].strip()
        return _strip_residual_stop_tokens(text)

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
    ) -> Iterator[str]:
        if self._status != "ready" or self._llm is None:
            yield self._stub_response(prompt)
            return

        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        for chunk in self._llm(  # type: ignore[union-attr]
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop_tokens,
            echo=False,
            stream=True,
        ):
            yield chunk["choices"][0]["text"]

    def generate_with_cancel(
        self,
        prompt: str,
        cancel_event: threading.Event,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
    ) -> str:
        """per-token cancel_event 확인 — asyncio timeout 시 executor thread 조기 종료."""
        if self._status != "ready" or self._llm is None:
            return self._stub_response(prompt)
        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        tokens: list[str] = []
        with self._lock:
            for chunk in self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop_tokens,
                echo=False,
                stream=True,
            ):
                if cancel_event.is_set():
                    break
                tokens.append(chunk["choices"][0]["text"])
        return _strip_residual_stop_tokens("".join(tokens))

    def generate_stream_with_cancel(
        self,
        prompt: str,
        cancel_event: threading.Event,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
    ) -> Iterator[str]:
        """Token-by-token streaming with cancel_event support."""
        if self._status != "ready" or self._llm is None:
            yield self._stub_response(prompt)
            return
        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        with self._lock:
            for chunk in self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop_tokens,
                echo=False,
                stream=True,
            ):
                if cancel_event.is_set():
                    break
                yield chunk["choices"][0]["text"]

    # ------------------------------------------------------------------
    @staticmethod
    def _stub_response(prompt: str) -> str:
        return (
            "[stub] 모델 미설치 — BUTLER_MODEL_PATH 환경변수에 .gguf 경로를 설정하고 "
            f"llama-cpp-python을 설치한 뒤 재시작하세요. (prompt_len={len(prompt)})"
        )
