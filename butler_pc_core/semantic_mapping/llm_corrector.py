"""llm_corrector.py — needs_review 결정에 대한 Qwen3-4B structured correction (단계 6).

적용 영역 (알고리즘 팀 보고서 §4):
  - combined_score < 0.70 (needs_review=True) 결정만
  - heuristic 영역이 우선; LLM은 재검토 역할
  - LLM 실패 / SKIP_LLM=true → heuristic fallback

모델 탐색 우선순위:
  1. SKIP_LLM=true 환경변수 → 즉시 None (테스트/CI)
  2. sidecar HTTP (127.0.0.1:8765, 이미 카드 1/2/5에서 사용 중)
  3. 로컬 모델 경로 (T7Shield SSD / ~/.butler/models/)
  4. 없으면 fallback
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable, List, Optional

from .contracts import MappingDecision, SourceField, TargetSlot
from .verifier import verify_llm_response

_SIDECAR_INFERENCE_URL = "http://127.0.0.1:8765/inference"
_SIDECAR_HEALTH_URL    = "http://127.0.0.1:8765/health"

_MODEL_PATHS: list[Path] = [
    Path("/Volumes/T7Shield/models/qwen3-4b-instruct"),
    Path.home() / ".butler/models/qwen3-4b-instruct",
]

_PROMPT_TEMPLATE = """\
당신은 문서 필드를 양식 슬롯에 매핑하는 전문가입니다.

[소스 필드]
레이블: {label}
값: {value}
감지 타입: {detected_type}

[후보 슬롯 목록]
{slots}

[현재 heuristic 결정]
슬롯: {current_slot}
신뢰도: {current_confidence:.2f}

위 소스 필드에 가장 적합한 슬롯을 JSON 형식으로만 응답하세요 (다른 텍스트 X):
{{"slot_id": "슬롯ID", "confidence": 0.0~1.0, "reason": "한국어 이유"}}\
"""


def _build_prompt(
    source: SourceField,
    decision: MappingDecision,
    candidate_slots: List[TargetSlot],
) -> str:
    slots_desc = "\n".join(
        f"  {s.slot_id}: {s.heading} "
        f"[허용타입: {', '.join(t.value for t in s.allowed_types)}]"
        f" 별칭: {', '.join(s.aliases[:5])}"
        for s in candidate_slots
    )
    current_slot = decision.target_slot.slot_id if decision.mapped else "unmapped"
    return _PROMPT_TEMPLATE.format(
        label=source.label,
        value=source.value,
        detected_type=source.detected_type.value,
        slots=slots_desc,
        current_slot=current_slot,
        current_confidence=decision.confidence,
    )


def _call_sidecar(prompt: str) -> str:
    """sidecar HTTP /inference 엔드포인트 호출."""
    payload = json.dumps({"prompt": prompt, "max_tokens": 256}).encode()
    req = urllib.request.Request(
        _SIDECAR_INFERENCE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        return data.get("text") or data.get("response") or str(data)


def _sidecar_available() -> bool:
    try:
        urllib.request.urlopen(_SIDECAR_HEALTH_URL, timeout=1)
        return True
    except Exception:
        return False


def _get_default_callable() -> Optional[Callable[[str], str]]:
    """환경에 따라 사용 가능한 LLM callable 반환 (없으면 None)."""
    if os.environ.get("SKIP_LLM") == "true":
        return None

    if _sidecar_available():
        return _call_sidecar

    # 로컬 모델 경로 확인 (모델 로딩은 단계 5 예정)
    for path in _MODEL_PATHS:
        if path.exists():
            # TODO(stage-5): 로컬 transformers 추론 구현
            return None

    return None


def correct_mapping(
    decision: MappingDecision,
    source: SourceField,
    candidate_slots: List[TargetSlot],
    llm_callable: Optional[Callable[[str], str]] = None,
) -> MappingDecision:
    """
    needs_review=True 결정에 LLM structured correction 적용.

    Args:
        decision:        slot_resolver 출력 결정 (needs_review=True 대상)
        source:          해당 소스 필드
        candidate_slots: 유효 슬롯 목록 (hallucination 차단에 사용)
        llm_callable:    테스트 주입용 callable — None이면 자동 탐색

    Returns:
        LLM 정정된 MappingDecision, 또는 실패 시 원본 heuristic 결정
    """
    # ★ 알고리즘 팀 §4: needs_review=False 영역 LLM 호출 X
    if not decision.needs_review:
        return decision

    call_fn = llm_callable if llm_callable is not None else _get_default_callable()
    if call_fn is None:
        return decision   # fallback: heuristic 유지

    try:
        prompt = _build_prompt(source, decision, candidate_slots)
        raw = call_fn(prompt)
        return verify_llm_response(raw, candidate_slots, decision)
    except Exception:
        return decision   # 모든 오류 → heuristic fallback
