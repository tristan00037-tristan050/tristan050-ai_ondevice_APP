"""Box 3 draft service: v1.0 endpoint contract + v1.2 reference pipeline.

기존(v1.0) 엔드포인트 계약과 codex v1.2 reference-from-existing 파이프라인을
동일 모듈에 병행 노출한다. 두 인터페이스는 독립적으로 작동한다:

- v1.0 (무회귀 의무): MODEL_CHAIN / SEALED_SHA / DEFAULT_MAX_NEW_TOKENS /
  MAX_NEW_TOKENS_LIMIT / build_draft_inference_config / draft_from_existing /
  DraftResult / digest_text — sidecar route /v1/cards/3/draft가 import.
- v1.2 (codex 베이스): Box3ContractError / validate_current_contract_input /
  compose_box3_current_contract_input / draft_from_current_contract — digest-only
  계약, security 모듈의 raw-text 가드와 함께 fail-closed.

Contract-safe by default. Real model execution은 caller가 runner를 주입했을 때만.
원문 입력 텍스트를 디스크에 저장하지 않으며 네트워크 호출 0.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from .security import assert_runtime_text_safe, sha256_digest, stable_json_digest


# ── v1.0 endpoint contract (무회귀 의무) ──────────────────────────────────

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


# ── v1.2 reference pipeline contract (codex 베이스) ──────────────────────

BOX3_DRAFT_ENDPOINT = "/v1/cards/3/draft"
BOX3_CURRENT_CONTRACT_FIELDS = ("input_text", "prompt_template", "max_new_tokens")
DEFAULT_REQUIRED_SECTIONS = [
    "제목",
    "배경",
    "핵심 내용",
    "근거",
    "확인 필요",
    "최종 문안",
]


class Box3ContractError(ValueError):
    """Raised for current endpoint contract violations."""


def validate_current_contract_input(
    input_text: str,
    prompt_template: str,
    max_new_tokens: int,
) -> None:
    if not isinstance(input_text, str) or not input_text:
        raise Box3ContractError("INPUT_TEXT_REQUIRED")
    if not isinstance(prompt_template, str) or "{input}" not in prompt_template:
        raise Box3ContractError("PROMPT_TEMPLATE_REQUIRES_INPUT_PLACEHOLDER")
    if not isinstance(max_new_tokens, int) or not 1 <= max_new_tokens <= 1024:
        raise Box3ContractError("MAX_NEW_TOKENS_OUT_OF_RANGE")
    assert_runtime_text_safe(input_text)
    assert_runtime_text_safe(prompt_template.replace("{input}", ""))


def compose_box3_current_contract_input(
    *,
    reference_doc_digests: list[str],
    request_digest: str,
    format_hint: str = "freeform",
    max_new_tokens: int = 512,
) -> dict[str, object]:
    input_text = "\n".join(
        [
            "BOX3_DIGEST_ONLY_INPUT",
            f"request_digest={request_digest}",
            "reference_doc_digests=" + ",".join(reference_doc_digests),
            f"format_hint_digest={sha256_digest(format_hint)}",
        ]
    )
    prompt_template = (
        "You are Butler Box 3. Use only digest-linked evidence units. "
        "Do not invent dates, amounts, names, or legal conclusions. "
        "Return a draft with citations by source_digest. Input: {input}"
    )
    validate_current_contract_input(input_text, prompt_template, max_new_tokens)
    return {
        "input_text": input_text,
        "prompt_template": prompt_template,
        "max_new_tokens": max_new_tokens,
    }


def draft_from_current_contract(
    *,
    input_text: str,
    prompt_template: str,
    max_new_tokens: int = 512,
    real_model_runner=None,
) -> dict[str, object]:
    validate_current_contract_input(input_text, prompt_template, max_new_tokens)
    request_digest = stable_json_digest(
        {
            "input_text_digest": sha256_digest(input_text),
            "prompt_template_digest": sha256_digest(prompt_template),
            "max_new_tokens": max_new_tokens,
        }
    )
    if real_model_runner is None:
        draft_text = "[CONTRACT_ONLY_BOX3_DRAFT_NOT_EXECUTED]"
        return {
            "status": "contract_only",
            "draft_text": draft_text,
            "draft_digest": sha256_digest(draft_text),
            "request_digest": request_digest,
            "mock_result": False,
            "contract_only": True,
            "real_claim_allowed": False,
            "external_send_zero": True,
            "raw_saved_zero": True,
            "raw_doc_logged": False,
            "fail_class": "ASSET_INTERFACE_PENDING",
        }
    draft_text = real_model_runner(
        prompt_template.replace("{input}", input_text),
        max_new_tokens=max_new_tokens,
    )
    assert_runtime_text_safe(draft_text)
    return {
        "status": "real",
        "draft_text": draft_text,
        "draft_digest": sha256_digest(draft_text),
        "request_digest": request_digest,
        "mock_result": False,
        "contract_only": False,
        "real_claim_allowed": True,
        "external_send_zero": True,
        "raw_saved_zero": True,
        "raw_doc_logged": False,
        "fail_class": None,
    }
