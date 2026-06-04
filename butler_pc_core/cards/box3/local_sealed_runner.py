from __future__ import annotations

import concurrent.futures
import os
import time
from dataclasses import asdict, dataclass
from typing import Callable

from .actual_contracts import Box3ActualRuntimeEnvelope, sha256_text
from .actual_fail_class import (
    BLOCK_MOCK_RUNNER_FOR_REAL,
    BLOCK_RUNNER_ERROR,
    BLOCK_RUNNER_TIMEOUT,
    PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED,
    PARTIAL_PEAK_MEMORY_UNMEASURED,
    PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
)
from .actual_runner_assets import ActualRunnerAssetConfig, verify_base_model_asset
from .helper_component_guard import verify_helper_component_use_guard
from .peak_memory import measure_peak_memory

RealRunner = Callable[[Box3ActualRuntimeEnvelope], str]

@dataclass(frozen=True)
class AdapterStackProbeVerdict:
    allowed: bool
    fail_class: str | None
    model_adapters: list[str]
    helper_sdk_stack_attempt_zero: bool
    detail: dict

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass(frozen=True)
class ActualRunnerSmokeResult:
    ok: bool
    draft_text: str | None
    fail_class: str | None
    latency_ms: float
    model_load_ms: float | None
    tokens_in: int
    tokens_out: int
    peak_memory_mb: float | None
    runner_id: str
    model_digest: str | None
    engine: str
    output_digest: str | None
    adapter_stack: dict | None = None
    test_only_runner: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("draft_text", None)
        return data

def compose_runner_prompt(envelope: Box3ActualRuntimeEnvelope) -> str:
    refs = "\n\n".join(f"[REF {idx + 1}]\n{text}" for idx, text in enumerate(envelope.reference_text_runtime_only))
    return (
        "Use only the provided references. Do not invent dates, amounts, people, or legal conclusions.\n"
        "Return Korean sections: 제목, 배경, 핵심 내용, 근거, 확인 필요, 최종 문안.\n"
        f"FORMAT_HINT: {envelope.format_hint}\n"
        f"REQUEST:\n{envelope.drafting_request_runtime_only}\n\n"
        f"REFERENCES:\n{refs}\n"
    )

def probe_helper3_helper5_adapter_stack(helper_guard: dict | None = None) -> AdapterStackProbeVerdict:
    """Probe only helper3/helper5 model-adapter stack capability.

    helper4/helper7/helper8 are SDK modules and must never be stacked into the model.
    """
    guard = verify_helper_component_use_guard(helper_guard)
    if not guard.allowed:
        return AdapterStackProbeVerdict(False, guard.fail_class, [], True, guard.to_dict())
    if os.environ.get("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK") != "1":
        return AdapterStackProbeVerdict(
            False,
            PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED,
            ["helper3_format", "helper5_tool_call"],
            True,
            {"reason": "multi_lora_stack_not_enabled_or_unmeasured"},
        )
    return AdapterStackProbeVerdict(True, None, ["helper3_format", "helper5_tool_call"], True, {"stack_capability": "declared_by_local_probe"})

def build_local_sealed_real_runner(
    config: ActualRunnerAssetConfig | None = None,
    *,
    helper_guard: dict | None = None,
) -> RealRunner:
    stack = probe_helper3_helper5_adapter_stack(helper_guard)
    if not stack.allowed:
        raise RuntimeError(stack.fail_class or PARTIAL_MODEL_ADAPTER_STACK_UNSUPPORTED)
    asset = verify_base_model_asset(config)
    if not asset.allowed:
        raise RuntimeError(asset.fail_class or PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE)
    if asset.required_engine != "llama_cpp":
        raise RuntimeError(PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE)
    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependent
        raise RuntimeError(PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE) from exc
    model_path = os.environ.get((config or ActualRunnerAssetConfig()).model_path_env)
    if not model_path:
        raise RuntimeError(PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE)
    start = time.perf_counter()
    # Keep helper4/7/8 out of the model constructor. Only helper3/5 LoRA stack is eligible.
    llm = Llama(model_path=model_path, verbose=False)
    load_ms = (time.perf_counter() - start) * 1000

    def _runner(envelope: Box3ActualRuntimeEnvelope) -> str:
        prompt = compose_runner_prompt(envelope)
        result = llm(prompt, max_tokens=envelope.max_new_tokens, temperature=0.0, stop=["</s>"])
        choices = result.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("text") or "").strip()

    setattr(_runner, "_box3_model_load_ms", load_ms)
    setattr(_runner, "_box3_runner_engine", "llama_cpp")
    setattr(_runner, "_box3_adapter_stack", stack.to_dict())
    return _runner

def _call_with_timeout(runner: RealRunner, envelope: Box3ActualRuntimeEnvelope, timeout_seconds: float) -> str:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(runner, envelope)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(BLOCK_RUNNER_TIMEOUT) from exc

def run_actual_runner_smoke(
    envelope: Box3ActualRuntimeEnvelope,
    *,
    runner: RealRunner | None = None,
    timeout_seconds: float = 30.0,
    config: ActualRunnerAssetConfig | None = None,
    helper_guard: dict | None = None,
) -> ActualRunnerSmokeResult:
    if runner is None:
        try:
            runner = build_local_sealed_real_runner(config, helper_guard=helper_guard)
        except RuntimeError as exc:
            return ActualRunnerSmokeResult(
                False, None, str(exc) or PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
                0.0, None, 0, 0, None, "box3-local-sealed-runner", None, "unavailable", None,
            )
    if getattr(runner, "_box3_mock_or_stub", False):
        return ActualRunnerSmokeResult(
            False, None, BLOCK_MOCK_RUNNER_FOR_REAL, 0.0, None, 0, 0, None,
            "box3-local-sealed-runner", None, "test", None, test_only_runner=True,
        )
    test_only = bool(getattr(runner, "_box3_test_only", False))
    start = time.perf_counter()
    try:
        measured = measure_peak_memory(lambda: _call_with_timeout(runner, envelope, timeout_seconds))
    except TimeoutError:
        return ActualRunnerSmokeResult(
            False, None, BLOCK_RUNNER_TIMEOUT, timeout_seconds * 1000.0, None, 0, 0, None,
            "box3-local-sealed-runner", None, "timeout", None, test_only_runner=test_only,
        )
    except Exception:
        return ActualRunnerSmokeResult(
            False, None, BLOCK_RUNNER_ERROR, 0.0, None, 0, 0, None,
            "box3-local-sealed-runner", None, "error", None, test_only_runner=test_only,
        )
    latency_ms = (time.perf_counter() - start) * 1000
    draft = str(measured.result or "").strip()
    if measured.peak_memory_mb is None:
        return ActualRunnerSmokeResult(
            False, None, PARTIAL_PEAK_MEMORY_UNMEASURED, latency_ms,
            getattr(runner, "_box3_model_load_ms", None), 0, 0, None,
            "box3-local-sealed-runner", None, getattr(runner, "_box3_runner_engine", "unknown"), None,
            adapter_stack=getattr(runner, "_box3_adapter_stack", None), test_only_runner=test_only,
        )
    return ActualRunnerSmokeResult(
        ok=bool(draft),
        draft_text=draft if draft else None,
        fail_class=None if draft else BLOCK_RUNNER_ERROR,
        latency_ms=round(latency_ms, 3),
        model_load_ms=getattr(runner, "_box3_model_load_ms", None),
        tokens_in=max(1, len(compose_runner_prompt(envelope).split())),
        tokens_out=max(0, len(draft.split())),
        peak_memory_mb=measured.peak_memory_mb,
        runner_id="box3-local-sealed-runner",
        model_digest=None,
        engine=getattr(runner, "_box3_runner_engine", "custom"),
        output_digest=sha256_text(draft) if draft else None,
        adapter_stack=getattr(runner, "_box3_adapter_stack", None),
        test_only_runner=test_only,
    )

def build_deterministic_test_runner() -> RealRunner:
    def _runner(envelope: Box3ActualRuntimeEnvelope) -> str:
        return (
            "제목: 참고 문서 기반 초안\n"
            "배경: 참고 문서에는 납품 일정이 2026년 6월 10일로 명시되어 있습니다.\n"
            "핵심 내용: 납품 일정은 2026년 6월 10일입니다.\n"
            "근거: source_digest citation으로 확인합니다.\n"
            "확인 필요: 담당자와 금액은 원문에 명확하지 않으면 확정하지 않습니다.\n"
            "최종 문안: 납품 일정은 2026년 6월 10일 기준으로 검토합니다."
        )
    setattr(_runner, "_box3_test_only", True)
    setattr(_runner, "_box3_runner_engine", "test_only")
    setattr(_runner, "_box3_model_load_ms", 0.0)
    setattr(_runner, "_box3_adapter_stack", {"model_adapters": ["helper3_format", "helper5_tool_call"], "test_only": True})
    return _runner
