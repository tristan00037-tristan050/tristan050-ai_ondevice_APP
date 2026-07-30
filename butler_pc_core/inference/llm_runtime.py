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
from typing import Any, Iterator

from butler_pc_core.assets import LoadedModelReceipt, NativeReadHandle
from butler_pc_core.runtime.json_grammar import normalize_model_response_to_text
from .verified_model_loader import VerifiedLlamaLoader, VerifiedLlamaSession


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
        model_handle: NativeReadHandle | None = None,
        loader: VerifiedLlamaLoader | None = None,
        n_ctx: int = 4096,
        n_threads: int = 0,
        *,
        model_path: str | None = None,
    ) -> None:
        if model_path is not None:
            raise TypeError("BLOCK_LOADER_AUTHORITY_REQUIRED")
        self._model_handle = model_handle
        self._loader = loader or VerifiedLlamaLoader()
        self._n_ctx = n_ctx
        self._n_threads = n_threads or max(1, (os.cpu_count() or 2) - 1)
        self._session: VerifiedLlamaSession | None = None
        self._llm: Any | None = None
        self._status: str = "no_model"
        self._last_error: str = ""
        self._lock = threading.Lock()

        if model_handle is not None:
            self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._model_handle is None:
            self._status = "no_model"
            return
        self._status = "loading"
        try:
            self._session = self._loader.load_from_verified_handle(
                self._model_handle,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
            )
            self._llm = self._session.backend
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

    @property
    def loaded_model_receipt(self) -> LoadedModelReceipt | None:
        return self._session.receipt if self._session is not None else None

    def duplicate_verified_handle(self) -> NativeReadHandle:
        if self._session is None:
            raise RuntimeError("BLOCK_LOADER_AUTHORITY_REQUIRED")
        return self._session._handle.duplicate()

    def reload(self, model_handle: NativeReadHandle) -> None:
        with self._lock:
            if self._session is not None:
                self._session.close()
            self._model_handle = model_handle
            self._session = None
            self._llm = None
            self._load()

    def close(self) -> None:
        with self._lock:
            if self._session is not None:
                self._session.close()
            self._session = None
            self._llm = None
            self._status = "no_model"

    def _reset_llama_kv_cache(self) -> bool:
        if self._llm is None:
            return False
        reset = getattr(self._llm, "reset", None)
        if not callable(reset):
            return False
        reset()
        return True

    # ------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
        grammar: Any | None = None,
    ) -> str:
        if self._status != "ready" or self._llm is None:
            return self._stub_response(prompt)

        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        call_kwargs: dict[str, Any] = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop_tokens,
            "echo": False,
        }
        if grammar is not None:
            call_kwargs["grammar"] = grammar
            call_kwargs["temperature"] = min(float(temperature), 0.1)
            call_kwargs["top_p"] = 0.95
        with self._lock:
            output = self._llm(prompt, **call_kwargs)
        text = normalize_model_response_to_text(output).strip()
        return _strip_residual_stop_tokens(text)

    def create_chat_completion(self, **kwargs: Any) -> Any:
        if self._status != "ready" or self._llm is None:
            raise RuntimeError("BLOCK_LOADER_AUTHORITY_REQUIRED")
        with self._lock:
            return self._llm.create_chat_completion(**kwargs)

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
        grammar: Any | None = None,
    ) -> Iterator[str]:
        if self._status != "ready" or self._llm is None:
            yield self._stub_response(prompt)
            return

        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        call_kwargs: dict[str, Any] = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop_tokens,
            "echo": False,
            "stream": True,
        }
        if grammar is not None:
            call_kwargs["grammar"] = grammar
            call_kwargs["temperature"] = min(float(temperature), 0.1)
            call_kwargs["top_p"] = 0.95
        for chunk in self._llm(prompt, **call_kwargs):  # type: ignore[union-attr]
            yield normalize_model_response_to_text(chunk)

    def generate_with_cancel(
        self,
        prompt: str,
        cancel_event: threading.Event,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
        grammar: Any | None = None,
    ) -> str:
        """per-token cancel_event 확인 — asyncio timeout 시 executor thread 조기 종료."""
        if self._status != "ready" or self._llm is None:
            return self._stub_response(prompt)
        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        call_kwargs: dict[str, Any] = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop_tokens,
            "echo": False,
            "stream": True,
        }
        if grammar is not None:
            call_kwargs["grammar"] = grammar
            call_kwargs["temperature"] = min(float(temperature), 0.1)
            call_kwargs["top_p"] = 0.95
        tokens: list[str] = []
        with self._lock:
            for chunk in self._llm(prompt, **call_kwargs):
                if cancel_event.is_set():
                    break
                tokens.append(normalize_model_response_to_text(chunk))
        return _strip_residual_stop_tokens("".join(tokens))

    def generate_stream_with_cancel(
        self,
        prompt: str,
        cancel_event: threading.Event,
        max_tokens: int = 512,
        temperature: float = 0.2,
        stop: list[str] | None = None,
        grammar: Any | None = None,
    ) -> Iterator[str]:
        """Token-by-token streaming with cancel_event support."""
        if self._status != "ready" or self._llm is None:
            yield self._stub_response(prompt)
            return
        stop_tokens = stop if stop is not None else DEFAULT_STOP_TOKENS
        call_kwargs: dict[str, Any] = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop_tokens,
            "echo": False,
            "stream": True,
        }
        if grammar is not None:
            call_kwargs["grammar"] = grammar
            call_kwargs["temperature"] = min(float(temperature), 0.1)
            call_kwargs["top_p"] = 0.95
        with self._lock:
            reset_ok = False
            try:
                reset_ok = self._reset_llama_kv_cache()
            except Exception:
                reset_ok = False
            if not reset_ok:
                # fail-closed: 세션 격리(KV reset) 확인 불가 → 오염 가능 출력 차단
                yield self._kv_reset_failed_response()
                return
            for chunk in self._llm(prompt, **call_kwargs):
                if cancel_event.is_set():
                    break
                yield normalize_model_response_to_text(chunk)

    # ------------------------------------------------------------------
    @staticmethod
    def _stub_response(prompt: str) -> str:
        return (
            "[사용 불가] 검증된 로컬 모델 자산을 사용할 수 없습니다. "
            f"(prompt_len={len(prompt)})"
        )

    @staticmethod
    def _kv_reset_failed_response() -> str:
        return "[격리 미확인] 세션 상태를 초기화하지 못해 안전을 위해 응답을 생성하지 않았습니다."
