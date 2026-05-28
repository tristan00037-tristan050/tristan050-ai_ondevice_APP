"""Box 3 draft service: compose a new draft from an existing document.

Contract-safe by default. Real model execution happens only when Claude Code
injects a local runner after the 4-stage adapter stack and assets are verified.
No raw input text is persisted; no network calls are made here.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

MODEL_CHAIN = ["base", "butler_v3", "tool_call", "box3_smoke"]

SEALED_SHA = {
    "box3_smoke": "4d86414ddf74b048d6db011659e4227641257ad0d931faab690dcddeea58cf74",
    "tool_call": "ad852bbb79aee63cc68750eac3ebe02de372d4eb9529659ae065490c78c933ca",
    "butler_v3": "7b4d474cba6cf8113b1402a44a490f153e3beea031ba54827c2fae848b7b4b41",
}

# 박스 3 추론 표준 (보강 63): repetition_penalty >= 1.2 + no_repeat_ngram_size = 3.
# box3-4.1 분리 검증 결과: v0_baseline 70% looping -> rep_pen 적용 시 0%.
MIN_REPETITION_PENALTY = 1.2
REQUIRED_NO_REPEAT_NGRAM_SIZE = 3
DEFAULT_MAX_NEW_TOKENS = 300
MAX_NEW_TOKENS_LIMIT = 1024

CONTRACT_ONLY_DRAFT = "[CONTRACT_ONLY_DRAFT_NOT_EXECUTED]"


@dataclass(frozen=True)
class DraftResult:
    draft_text: str
    duration_ms: int
    model_chain: list[str]
    inference_config: dict[str, Any]
    contract_only: bool
    external_send_zero: bool
    raw_saved_zero: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_draft_inference_config(max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS) -> dict[str, Any]:
    """Return the enforced Box 3 inference config.

    repetition_penalty is floored at MIN_REPETITION_PENALTY and
    no_repeat_ngram_size is fixed, regardless of caller input, so the
    looping defect identified in box3-4.1 cannot reappear via config drift.
    """
    bounded_tokens = max(1, min(int(max_new_tokens), MAX_NEW_TOKENS_LIMIT))
    return {
        "do_sample": False,
        "max_new_tokens": bounded_tokens,
        "repetition_penalty": MIN_REPETITION_PENALTY,
        "no_repeat_ngram_size": REQUIRED_NO_REPEAT_NGRAM_SIZE,
    }


def digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def draft_from_existing(
    input_text: str,
    prompt_template: str,
    *,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    runner: Callable[[str, dict[str, Any]], str] | None = None,
) -> DraftResult:
    """Compose a draft from an existing document.

    When ``runner`` is None the service stays contract-only and never
    fabricates a draft. When Claude Code injects a local runner (after the
    4-stage stack + asset SHA verification), the enforced inference config is
    passed through and the produced draft is returned. Raw input text is never
    written to disk by this function.
    """
    config = build_draft_inference_config(max_new_tokens)
    prompt = prompt_template.replace("{input}", input_text) if "{input}" in prompt_template else f"{prompt_template}\n\n{input_text}"

    if runner is None:
        return DraftResult(
            draft_text=CONTRACT_ONLY_DRAFT,
            duration_ms=0,
            model_chain=list(MODEL_CHAIN),
            inference_config=config,
            contract_only=True,
            external_send_zero=True,
            raw_saved_zero=True,
        )

    start = time.time()
    produced = runner(prompt, config)
    duration_ms = int((time.time() - start) * 1000)
    return DraftResult(
        draft_text=produced,
        duration_ms=duration_ms,
        model_chain=list(MODEL_CHAIN),
        inference_config=config,
        contract_only=False,
        external_send_zero=True,
        raw_saved_zero=True,
    )
