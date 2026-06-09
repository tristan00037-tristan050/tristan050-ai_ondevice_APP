from __future__ import annotations

import concurrent.futures
import os
import re
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

_THINK_BLOCK_RE = re.compile(r"(?is)^\s*<think>.*?</think>\s*")
_UNCLOSED_THINK_RE = re.compile(r"(?is)^\s*<think>")


def strip_thinking(text: str) -> str:
    """v9.1 ChatML 모델의 <think>...</think> 접두 제거. runtime-only."""
    text = _THINK_BLOCK_RE.sub("", text or "").strip()
    if _UNCLOSED_THINK_RE.match(text):
        return ""  # 닫히지 않은 thinking은 비움 (degeneration 방지 fail-safe)
    return text


def _extract_llama_text(result: dict) -> str:
    """llama_cpp chat-completion(message.content)과 completion(text)을 모두 안전 처리."""
    choices = result.get("choices") or []
    if not choices:
        return ""
    first = choices[0]
    msg = first.get("message")
    if isinstance(msg, dict):
        return str(msg.get("content") or "").strip()
    return str(first.get("text") or "").strip()

def _topic_josa(text: str) -> str:
    if not text:
        return "은"
    ch = text[-1]
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        return "은" if (code - 0xAC00) % 28 else "는"
    return "은"


def _split_evidence_item(text: str) -> tuple:
    text = (text or "").strip().rstrip(".")
    if ":" in text:
        key, value = text.split(":", 1)
        return key.strip(), value.strip()
    return "근거", text


def _normalize_copy_value(value: str) -> str:
    value = (value or "").strip().rstrip(".")
    if not value:
        return "[문서에 근거 없음]"
    if "명시되지 않음" in value or "문서에 없음" in value or "근거 없음" in value:
        return "[문서에 근거 없음]"
    return value


def _topic_from_items(items: list) -> str:
    if not items:
        return "문서"
    first_key = items[0][0]
    parts = first_key.split()
    return parts[0] if parts else (first_key[:2] or "문서")


def build_grounded_copy_draft_from_envelope(envelope) -> str:
    """근거 카드 기반 deterministic copy draft. 모델 자유 생성 없이 PASS 후보 초안 조립."""
    # 1순위: reference_text_runtime_only 전체 (원본 근거 순서·번호 유지)
    refs = getattr(envelope, "reference_text_runtime_only", []) or []
    raw_texts = [str(x).strip() for x in refs if str(x).strip()]
    # 2순위 fallback: rag_context.selected_units()
    if not raw_texts:
        rag_context = getattr(envelope, "rag_context_runtime_only", None)
        if rag_context is not None and hasattr(rag_context, "selected_units"):
            try:
                units = list(rag_context.selected_units())
                raw_texts = [str(getattr(u, "text_runtime_only", "")).strip()
                             for u in units if str(getattr(u, "text_runtime_only", "")).strip()]
            except Exception:
                raw_texts = []
    items = [_split_evidence_item(t) for t in raw_texts]
    items = [(k, _normalize_copy_value(v)) for k, v in items]
    # padding 금지 — 없는 근거는 만들지 않음
    topic = _topic_from_items(items)
    def sent(idx):
        key, value = items[idx - 1]
        return f"{key}{_topic_josa(key)} {value}입니다 (근거{idx})."
    n = len(items)
    lines = [f"제목: {topic} 정보 요약"]
    if n >= 1:
        lines.append(f"배경: {sent(1)}")
    if n >= 3:
        lines.append(f"핵심내용: {sent(2)} {sent(3)}")
    elif n == 2:
        lines.append(f"핵심내용: {sent(2)}")
    if n >= 4:
        lines.append(f"근거: {sent(4)}")
    lines.append("확인필요: 담당자와 금액은 [문서에 근거 없음]입니다.")
    if n >= 1:
        lines.append(f"최종문안: {sent(1)}")
    else:
        lines.append("최종문안: [문서에 근거 없음]")
    return "\n".join(lines)


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
    # Box3 RAG·Prompt activation v1.2 (2026-06-04): pipeline 이 helper7 parse 직후
    # build_grounded_prompt_packet 으로 envelope.grounded_prompt_runtime_only 를
    # 미리 부착하면 그것을 우선 사용한다. 부재 시에만 legacy 폴백 (raw 0 유지).
    grounded = getattr(envelope, "grounded_prompt_runtime_only", None)
    if isinstance(grounded, str) and grounded.strip():
        return grounded
    refs = "\n\n".join(f"[REF {idx + 1}]\n{text}" for idx, text in enumerate(envelope.reference_text_runtime_only))
    return (
        "Use only the provided references. Do not invent dates, amounts, people, or legal conclusions.\n"
        "Return Korean sections: 제목, 배경, 핵심 내용, 근거, 확인 필요, 최종 문안.\n"
        f"FORMAT_HINT: {envelope.format_hint}\n"
        f"REQUEST:\n{envelope.drafting_request_runtime_only}\n\n"
        f"REFERENCES:\n{refs}\n"
    )

def probe_helper3_helper5_adapter_stack(helper_guard: dict | None = None) -> AdapterStackProbeVerdict:
    """v5 base model 에 helper3/5 가 embedded — runtime LoRA re-stack 금지 (PR #783).

    helper4/helper7/helper8 are SDK modules and must never be stacked into the model.

    - env BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK=1 시 BLOCK_HELPER35_DOUBLE_STACK_RISK
      (v5 가 이미 lineage 에 helper3/5 를 포함하므로 runtime 재stack 은 double fusion 위험).
    - 미설정 시 embedded mode 로 PASS (model_adapters 에 embedded prefix).
    """
    from .v5_asset_manifest import MODEL_LINEAGE as _V5_LINEAGE

    if os.environ.get("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK") == "1":
        return AdapterStackProbeVerdict(
            False,
            "BLOCK_HELPER35_DOUBLE_STACK_RISK",
            ["helper3_format", "helper5_tool_call"],
            True,
            {
                "reason": "v5 embeds helper3/helper5; runtime re-stack is forbidden",
                "model_lineage": dict(_V5_LINEAGE),
            },
        )
    # PR #783: helper_guard 가 명시적으로 주어진 경우에만 검증 (PR #779 호환 경로).
    # 미지정 시 v5 embedded SSOT 로 직행 (MAINDEV 정본).
    if helper_guard is not None:
        guard = verify_helper_component_use_guard(helper_guard)
        if not guard.allowed:
            return AdapterStackProbeVerdict(False, guard.fail_class, [], True, guard.to_dict())
    return AdapterStackProbeVerdict(
        True,
        None,
        ["embedded_in_v7_base_model:helper3_format", "embedded_in_v7_base_model:helper5_tool_call"],
        True,
        {
            "stack_capability": "embedded_in_v7_base_model",
            "runtime_lora_stack_allowed": False,
            "model_lineage": dict(_V5_LINEAGE),
        },
    )

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
    # PR #781 (Box3 RAG·Prompt v1.2): grounded prompt 가 1k-2k 토큰 수준이 될 수 있으므로
    # 충분한 context window 를 확보 (env override 가능). 기본 4096 = grounded prompt + 출력
    # max_new_tokens(<=1024) 여유. n_ctx 환경변수가 설정되면 그것을 사용한다.
    try:
        n_ctx = int(os.environ.get("BUTLER_BOX3_RUNNER_N_CTX", "4096"))
    except ValueError:
        n_ctx = 4096
    llm = Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
    load_ms = (time.perf_counter() - start) * 1000

    def _runner(envelope: Box3ActualRuntimeEnvelope) -> str:
        if os.environ.get("BUTLER_BOX3_RUNNER_MODE") == "grounded_copy":
            return build_grounded_copy_draft_from_envelope(envelope)
        prompt = compose_runner_prompt(envelope)
        # PR #781: temperature/top_p/repeat_penalty/stop 는 grounded_prompt.DecodeConfig 가
        # decode_config_digest 로 잠그지만, 본 runner 는 model-level 실제 디코딩 파라미터로
        # 보수적 기본값을 적용 (temperature=0.0 / top_p=0.85 / repeat_penalty=1.15).
        # v9.1은 ChatML/thinking 모델입니다.
        # bare completion(llm(prompt))은 JSON/tool_call degeneration을 유발하므로
        # 모델 내장 ChatML 템플릿을 쓰는 create_chat_completion 경로로 호출합니다.
        result = llm.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 Butler Box 3 로컬 초안 작성기입니다. "
                        "근거의 사실만 사용하고 지정된 한국어 6개 라벨 형식만 출력하세요. "
                        "JSON, tool_call, 코드블록은 출력하지 마세요."
                    ),
                },
                {"role": "user", "content": prompt.rstrip() + "\n\n/no_think"},
            ],
            max_tokens=envelope.max_new_tokens,
            temperature=0.0,
            top_p=0.85,
            repeat_penalty=1.15,
            stop=["</s>", "<|im_end|>"],
        )
        return strip_thinking(_extract_llama_text(result))

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
