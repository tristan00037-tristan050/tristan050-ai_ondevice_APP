from __future__ import annotations

import concurrent.futures
import os
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from .real_contracts import Box3RealRuntimeEnvelope, sha256_text, stable_json_digest
from .real_fail_class import (
    BLOCK_MOCK_RUNNER_FOR_REAL,
    BLOCK_RUNNER_ERROR,
    BLOCK_RUNNER_TIMEOUT,
    PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
)
from .real_runner_assets import Box3RealRunnerConfig, verify_box3_real_runner_assets

RealRunner = Callable[[Box3RealRuntimeEnvelope], str]


@dataclass(frozen=True)
class RunnerCallResult:
    ok: bool
    draft_text: Optional[str]
    fail_class: Optional[str]
    latency_ms: float
    tokens_estimated: int
    load_ms: Optional[float]
    peak_memory_mb: Optional[float]
    runner_id: str
    model_choice: str
    model_digest: Optional[str]
    loader_version: str

    def to_dict(self) -> dict:
        data = asdict(self)
        if data["draft_text"] is not None:
            data["draft_digest"] = sha256_text(data.pop("draft_text"))
        return data


def _compose_prompt(envelope: Box3RealRuntimeEnvelope) -> str:
    reference_block = "\n\n".join(f"[REF {idx + 1}]\n{text}" for idx, text in enumerate(envelope.reference_docs_runtime_only))
    return (
        "You are Butler Box 3 local real draft runner. Use only the provided references.\n"
        "Do not invent dates, amounts, people, legal conclusions, or unsupported commitments.\n"
        "Return Korean draft sections: 제목, 배경, 핵심 내용, 근거, 확인 필요, 최종 문안.\n\n"
        f"FORMAT_HINT: {envelope.format_hint}\n"
        f"DRAFT_REQUEST:\n{envelope.drafting_request_runtime_only}\n\n"
        f"REFERENCES:\n{reference_block}\n"
    )


def build_box3_local_real_runner(config: Box3RealRunnerConfig) -> RealRunner:
    if config.mock_or_stub or config.loader_name in {"mock", "stub"}:
        raise RuntimeError(BLOCK_MOCK_RUNNER_FOR_REAL)
    if config.loader_name != "llama_cpp":
        raise RuntimeError(PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE)
    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local runtime
        raise RuntimeError(PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE) from exc
    model_path = config.model_path
    if model_path is None:
        raise RuntimeError(PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE)
    load_start = time.perf_counter()
    llm = Llama(model_path=str(model_path), verbose=False)  # local file only, no network
    load_ms = (time.perf_counter() - load_start) * 1000.0

    def _runner(envelope: Box3RealRuntimeEnvelope) -> str:
        prompt = _compose_prompt(envelope)
        result = llm(prompt, max_tokens=envelope.max_new_tokens, temperature=0.0, stop=["</s>"])
        choices = result.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("text") or "").strip()

    setattr(_runner, "_box3_load_ms", load_ms)
    return _runner


def _call_runner_with_timeout(runner: RealRunner, envelope: Box3RealRuntimeEnvelope, timeout_seconds: float) -> tuple[str, float]:
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(runner, envelope)
        try:
            draft = future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(BLOCK_RUNNER_TIMEOUT) from exc
    latency_ms = (time.perf_counter() - start) * 1000.0
    return draft, latency_ms


def run_box3_real_enablement_smoke(
    envelope: Box3RealRuntimeEnvelope,
    config: Box3RealRunnerConfig,
    *,
    runner: RealRunner | None = None,
) -> RunnerCallResult:
    if config.mock_or_stub:
        return RunnerCallResult(False, None, BLOCK_MOCK_RUNNER_FOR_REAL, 0.0, 0, None, None, config.runner_id, config.model_choice, config.base_model_sha256_full, config.loader_version)

    if runner is None:
        asset_verdict = verify_box3_real_runner_assets(config)
        if not asset_verdict.allowed:
            return RunnerCallResult(False, None, asset_verdict.fail_class, 0.0, 0, None, None, config.runner_id, config.model_choice, config.base_model_sha256_full, config.loader_version)
        try:
            runner = build_box3_local_real_runner(config)
        except RuntimeError as exc:
            fail = str(exc) if str(exc) else PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE
            return RunnerCallResult(False, None, fail, 0.0, 0, None, None, config.runner_id, config.model_choice, config.base_model_sha256_full, config.loader_version)

    try:
        draft, latency_ms = _call_runner_with_timeout(runner, envelope, config.timeout_seconds)
    except TimeoutError:
        return RunnerCallResult(False, None, BLOCK_RUNNER_TIMEOUT, config.timeout_seconds * 1000.0, 0, None, None, config.runner_id, config.model_choice, config.base_model_sha256_full, config.loader_version)
    except Exception:
        return RunnerCallResult(False, None, BLOCK_RUNNER_ERROR, 0.0, 0, None, None, config.runner_id, config.model_choice, config.base_model_sha256_full, config.loader_version)

    tokens_estimated = max(1, len(draft.split())) if draft else 0
    return RunnerCallResult(
        ok=bool(draft.strip()),
        draft_text=draft if draft.strip() else None,
        fail_class=None if draft.strip() else BLOCK_RUNNER_ERROR,
        latency_ms=latency_ms,
        tokens_estimated=tokens_estimated,
        load_ms=getattr(runner, "_box3_load_ms", None),
        peak_memory_mb=None,  # filled by platform runner if available; absence is PARTIAL in final report.
        runner_id=config.runner_id,
        model_choice=config.model_choice,
        model_digest=config.base_model_sha256_full,
        loader_version=config.loader_version,
    )


def build_test_runner_for_tests() -> RealRunner:
    """Deterministic local test runner. It is explicitly test-only and must never be used as real."""
    def _runner(envelope: Box3RealRuntimeEnvelope) -> str:
        first = envelope.reference_docs_runtime_only[0]
        return (
            "제목: 참고 문서 기반 초안\n"
            "배경: 참고 문서에는 납품 일정이 2026-06-10으로 명시되어 있습니다.\n"
            "핵심 내용: 납품 일정은 2026-06-10입니다.\n"
            "근거: source_digest citation을 확인해야 합니다.\n"
            "확인 필요: 담당자와 금액은 원문에 명확하지 않으면 확정하지 않습니다.\n"
            "최종 문안: 납품 일정은 2026-06-10 기준으로 검토합니다."
        )
    setattr(_runner, "_box3_test_only", True)
    return _runner
