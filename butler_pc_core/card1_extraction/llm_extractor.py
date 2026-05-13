"""llm_extractor.py — Qwen3-4B structured extraction (알고리즘 팀 §6).

우선순위 (단계 6.5.1 — 2026-05):
  1. SKIP_LLM=true 또는 skip_llm=True → 즉시 heuristic fallback (테스트/CI)
  2. BUTLER_LLM_MODEL_PATH + llama-cpp-python → 영역 내장 추론 (Metal 가속)
  3. sidecar HTTP (127.0.0.1:8765) — 단계 6.5 이전 영역 호환
  4. 없으면 heuristic fallback

단계 6.5.1 신규 — card1_action_extraction.v1:
  - extract_with_llm_v1(text, parsed_hints, llm_callable) → (Card1Extraction, schema_valid, retry_count, retry_reasons)
  - JSON Schema 강제 + 1회 retry + LLM 자기평가 confidence 폐기
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .contracts import (
    Card1Extraction,
    ExtractedAction,
    IntentType,
    SentenceType,
)

_SIDECAR_INFERENCE_URL = "http://127.0.0.1:8765/inference"
_SIDECAR_HEALTH_URL    = "http://127.0.0.1:8765/health"

# 단계 6.5.1 — llama-cpp-python 영역 영역 영역 (lazy load + thread-safe)
_LLAMA_LOCK: threading.Lock = threading.Lock()
_LLAMA_INSTANCE: Any = None
_LLAMA_LOAD_FAILED: bool = False

_PROMPT_TEMPLATE = """\
당신은 한국 비즈니스 문서에서 요청 핵심을 추출하는 전문가입니다.

[원문]
{text}

[파서 힌트]
마감 후보: {deadlines}
자료 후보: {materials}
액션 후보: {actions}

위 원문을 분석하여 다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "intent": "한 문장 핵심 의도",
  "intent_type": "request|report|question|command|schedule|no_action|unknown",
  "deadline": "YYYY-MM-DD 또는 null",
  "deadline_raw": "원문 마감 표현 또는 빈 문자열",
  "materials": ["자료명1", "자료명2"],
  "actions": [
    {{"action_text": "동사형 액션", "source_evidence": "원문 근거 문장", "confidence": 0.0~1.0}}
  ],
  "confidence": 0.0~1.0,
  "needs_review": true|false,
  "reason_code": "high_confidence|low_evidence|ambiguous|hallucination_risk"
}}\
"""

_INTENT_TYPE_MAP: dict[str, IntentType] = {t.value: t for t in IntentType}


def _build_prompt(text: str, parsed_hints: Dict[str, Any]) -> str:
    return _PROMPT_TEMPLATE.format(
        text=text[:6000],
        deadlines=", ".join(parsed_hints.get("deadlines", [])) or "없음",
        materials=", ".join(parsed_hints.get("materials", [])) or "없음",
        actions="\n  ".join(parsed_hints.get("actions", [])) or "없음",
    )


def _sidecar_available() -> bool:
    try:
        urllib.request.urlopen(_SIDECAR_HEALTH_URL, timeout=1)
        return True
    except Exception:
        return False


def _call_sidecar(prompt: str) -> str:
    payload = json.dumps({"prompt": prompt, "max_tokens": 512}).encode()
    req = urllib.request.Request(
        _SIDECAR_INFERENCE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        return data.get("text") or data.get("response") or str(data)


def _get_llama_instance() -> Any:
    """llama-cpp-python 모델 lazy load — BUTLER_LLM_MODEL_PATH 환경변수 영역.

    한 번 로드된 모델은 프로세스 영역 영역 재사용 (Metal 영역 영역 영역 영역 영역 영역).
    로드 실패 영역 _LLAMA_LOAD_FAILED 영역 영역 영역 재시도 X.
    """
    global _LLAMA_INSTANCE, _LLAMA_LOAD_FAILED
    if _LLAMA_INSTANCE is not None:
        return _LLAMA_INSTANCE
    if _LLAMA_LOAD_FAILED:
        return None

    model_path = os.environ.get("BUTLER_LLM_MODEL_PATH", "").strip()
    if not model_path or not os.path.exists(model_path):
        _LLAMA_LOAD_FAILED = True
        return None

    with _LLAMA_LOCK:
        if _LLAMA_INSTANCE is not None:
            return _LLAMA_INSTANCE
        try:
            from llama_cpp import Llama
        except ImportError:
            _LLAMA_LOAD_FAILED = True
            return None
        try:
            _LLAMA_INSTANCE = Llama(
                model_path=model_path,
                n_ctx=int(os.environ.get("BUTLER_LLM_N_CTX", "4096")),
                n_gpu_layers=int(os.environ.get("BUTLER_LLM_N_GPU_LAYERS", "-1")),
                n_threads=int(os.environ.get("BUTLER_LLM_N_THREADS", "8")),
                verbose=False,
                seed=42,
            )
        except Exception:
            _LLAMA_LOAD_FAILED = True
            return None
        return _LLAMA_INSTANCE


def _call_llama_cpp(prompt: str) -> str:
    """Qwen3 chat template 영역 wrap → llama-cpp 영역 호출.

    `/no_think` 영역 추가로 추론(<think>) 모드 비활성화 — JSON 추출 영역 영역 영역.
    """
    llm = _get_llama_instance()
    if llm is None:
        raise RuntimeError("llama-cpp 모델 미로드")
    # Qwen3 chat template + /no_think 지시
    wrapped = (
        "<|im_start|>system\n"
        "당신은 한국 비즈니스 문서 분석 전문가입니다. JSON으로만 응답합니다.<|im_end|>\n"
        "<|im_start|>user\n"
        f"{prompt}\n\n/no_think<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    max_tokens = int(os.environ.get("BUTLER_LLM_MAX_TOKENS", "512"))
    with _LLAMA_LOCK:
        out = llm(
            wrapped,
            max_tokens=max_tokens,
            temperature=0.1,
            top_p=0.9,
            stop=["<|im_end|>", "<|endoftext|>"],
        )
    return out["choices"][0]["text"]


def _get_callable() -> Optional[Callable[[str], str]]:
    if os.environ.get("SKIP_LLM") == "true":
        return None
    # 1) llama-cpp-python 영역 영역 영역 우선
    if os.environ.get("BUTLER_LLM_MODEL_PATH"):
        if _get_llama_instance() is not None:
            return _call_llama_cpp
    # 2) sidecar HTTP fallback
    if _sidecar_available():
        return _call_sidecar
    return None


def _parse_llm_response(raw: str) -> Optional[dict]:
    # Qwen3 `<think>...</think>` 추론 블록 영역 제거 (`/no_think` 영역 영역 영역 영역 영역)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _heuristic_extraction(text: str, parsed_hints: Dict[str, Any]) -> Card1Extraction:
    """LLM 미사용 시 6-타입 분류 기반 heuristic extraction (알고리즘 팀 §6-3).

    분류 우선순위:
      1. NO_ACTION  — 부정/취소 표현 (최우선)
      2. REPORT     — 보고/드리겠습니다/예정입니다
      3. QUESTION   — 정보 확인형 의문문 (요청형 X)
      4. COMMAND    — 하십시오/하시기 바랍니다/해주십시오
      5. SCHEDULE   — 회의/미팅/일정 + 있습니다
      6. REQUEST    — 주세요/해주세요/봅시다/제안/ACTION_VERBS
      7. UNKNOWN    — 위 패턴 없음
    """
    import re as _re
    from .parser import _ACTION_VERB_RE

    deadlines: List[str]    = parsed_hints.get("deadlines", [])
    materials: List[str]    = parsed_hints.get("materials", [])
    action_sents: List[str] = parsed_hints.get("actions", [])

    intent = action_sents[0][:60] if action_sents else text[:60]

    # ── 패턴 정의 ──────────────────────────────────────────────────────────────
    _no_action_re = _re.compile(
        r"(?:하지\s*않|않습니다|안\s*됩니다|없습니다|없어서|없으니"
        r"|취소(?:되었|됩니다)?|어렵습니다|보류|연기(?:됩니다)?"
        r"|못\s*합니다|불가|진행하지\s*않)"
    )
    # REPORT 패턴 — 단계 8.3 정정: "드리겠습니다/하겠습니다/드립니다" 단독 매칭 시
    # "부탁/요청/감사" 같은 정중 요청 표현 영역은 lookbehind로 제외
    # → "회신 부탁드립니다" / "감사하겠습니다"는 REQUEST로, "보내드리겠습니다"는 REPORT로
    _report_re = _re.compile(
        r"(?:보고드립니다|보고드리겠습니다|보고합니다"
        r"|말씀드리겠습니다|말씀드립니다"
        r"|공유드립니다|공유드리겠습니다|공유해드립니다"
        r"|전달드립니다|전달드리겠습니다"
        r"|알려드립니다|알려드리겠습니다"
        r"|예정입니다"
        r"|(?<!감사)(?<!요청)(?<!부탁)드리겠습니다"
        r"|(?<!감사)(?<!요청)(?<!부탁)하겠습니다"
        r"|(?<!감사)(?<!요청)(?<!부탁)드립니다)"
    )
    # QUESTION: 정보 확인형 의문문 — 행동 요청이 없는 순수 질문
    _question_marker_re = _re.compile(
        r"(?:언제|가능한지|됩니까\s*[?？]?|받으셨|어떻게|무엇|어디|왜)"
    )
    _question_form_re = _re.compile(
        r"(?:나요\s*[?？]?|까요\s*[?？]?|합니까\s*[?？]?|[?？])"
    )
    # REQUEST 표지 (QUESTION과 구분 기준) — 단계 8.3 정중 요청 패턴 보강
    _request_keyword_re = _re.compile(
        r"(?:주세요|해주세요|보내주세요|전달해주세요|공유해주세요|회신해주세요|제출해주세요"
        r"|부탁드립니다|부탁드리|부탁합니다|요청드립니다"
        r"|주시기\s*바랍니다|주시면\s*감사|주시면|주실|주시겠"
        r"|감사하겠습니다|감사드립니다|바랍니다)"
    )
    # COMMAND: 격식체 명령 (해주세요 제외)
    _command_re = _re.compile(
        r"(?:하십시오|해주십시오|주십시오|하시기\s*바랍니다)"
    )
    _command_haseyo_re = _re.compile(r"하세요")   # "해주세요"와 구분 — 별도 처리
    _schedule_re = _re.compile(
        r"(?:회의|미팅|일정|행사|세미나|워크숍)\s*(?:이|가|은|는)?\s*있습니다"
    )
    _propositive_re = _re.compile(
        r"(?:합시다|봅시다|해봅시다|해봐요|하죠|해보죠|해봐요)"
    )

    # ── 분류 ───────────────────────────────────────────────────────────────────
    has_request_keyword = bool(_request_keyword_re.search(text))
    has_하세요          = bool(_command_haseyo_re.search(text))
    is_command_form    = (has_하세요 and not has_request_keyword)

    if _no_action_re.search(text):
        intent_type = IntentType.NO_ACTION

    elif _report_re.search(text):
        intent_type = IntentType.REPORT

    elif (_question_form_re.search(text)
          and _question_marker_re.search(text)
          and not has_request_keyword):
        intent_type = IntentType.QUESTION

    elif _command_re.search(text) or is_command_form:
        intent_type = IntentType.COMMAND

    elif _schedule_re.search(text):
        intent_type = IntentType.SCHEDULE

    elif action_sents or has_request_keyword or _propositive_re.search(text):
        intent_type = IntentType.REQUEST

    elif _question_form_re.search(text):
        # 요청형 의문문 (REQUEST disguised as question)
        intent_type = IntentType.REQUEST

    else:
        intent_type = IntentType.UNKNOWN

    actions = [
        ExtractedAction(
            action_text=sent[:100],
            source_evidence=sent[:100],
            confidence=0.70,
        )
        for sent in action_sents[:3]
    ]

    return Card1Extraction(
        intent=intent,
        intent_type=intent_type,
        deadline=None,
        deadline_raw=deadlines[0] if deadlines else "",
        materials=materials,
        actions=actions,
        sentence_type=SentenceType.DECLARATIVE,
        confidence=0.55,
        needs_review=True,
        reason_code="heuristic_fallback",
    )


def extract_with_llm(
    text: str,
    parsed_hints: Dict[str, Any],
    llm_callable: Optional[Callable[[str], str]] = None,
) -> Card1Extraction:
    """
    Qwen3-4B structured extraction.

    Args:
        text:         원문 텍스트
        parsed_hints: parser 출력 힌트 {deadlines, materials, actions}
        llm_callable: 테스트 주입용 callable — None이면 자동 탐색

    Returns:
        Card1Extraction (LLM 실패/SKIP_LLM 시 heuristic fallback)
    """
    call_fn = llm_callable if llm_callable is not None else _get_callable()
    if call_fn is None:
        return _heuristic_extraction(text, parsed_hints)

    try:
        prompt = _build_prompt(text, parsed_hints)
        raw = call_fn(prompt)
        data = _parse_llm_response(raw)
        if data is None:
            return _heuristic_extraction(text, parsed_hints)

        # Intent type 검증
        raw_type = data.get("intent_type", "unknown")
        intent_type = _INTENT_TYPE_MAP.get(raw_type, IntentType.UNKNOWN)

        # Actions 파싱
        actions = [
            ExtractedAction(
                action_text=a.get("action_text", "")[:100],
                source_evidence=a.get("source_evidence", "")[:200],
                confidence=max(0.0, min(1.0, float(a.get("confidence", 0.5)))),
            )
            for a in data.get("actions", [])
            if isinstance(a, dict) and a.get("action_text")
        ]

        confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))

        return Card1Extraction(
            intent=str(data.get("intent", ""))[:120],
            intent_type=intent_type,
            deadline=data.get("deadline") or None,
            deadline_raw=str(data.get("deadline_raw", ""))[:60],
            materials=[str(m) for m in data.get("materials", []) if m],
            actions=actions,
            sentence_type=SentenceType.DECLARATIVE,
            confidence=round(confidence, 3),
            needs_review=bool(data.get("needs_review", True)),
            reason_code=str(data.get("reason_code", ""))[:40],
        )

    except Exception:
        return _heuristic_extraction(text, parsed_hints)


# ─────────────────────────────────────────────────────────────────────────────
# 단계 6.5.1 — card1_action_extraction.v1 (알고리즘 팀 §6 — 최종 지침)
# ─────────────────────────────────────────────────────────────────────────────

# 알고리즘 팀 권장 추출 설정 — 결정론 + 한국어 보존
LLM_EXTRACT_CONFIG: Dict[str, Any] = {
    "temperature":    0.0,
    "top_p":          1.0,
    "top_k":          1,
    "repeat_penalty": 1.05,
    "max_tokens":     1200,
    "stop":           ["```"],
}

# v1 schema — card1_action_extraction.v1 (알고리즘 팀 §6 골격)
CARD1_ACTION_EXTRACTION_V1_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent_type", "actions", "no_action", "reason_code"],
    "properties": {
        "intent_type": {
            "type": "string",
            "enum": ["request", "report", "question", "instruction",
                     "schedule", "no_action", "other"],
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action_text", "action_type", "deadline_text",
                             "material_refs", "evidence", "is_negated"],
                "properties": {
                    "action_text":   {"type": "string"},
                    "action_type":   {"type": "string"},
                    "deadline_text": {"type": "string"},
                    "material_refs": {"type": "array", "items": {"type": "string"}},
                    "evidence":      {"type": "string"},
                    "is_negated":    {"type": "boolean"},
                },
            },
        },
        "no_action":   {"type": "boolean"},
        "reason_code": {"type": "string"},
    },
}

# 알고리즘 팀 §6 — System prompt (골격 그대로)
SYSTEM_PROMPT_V1 = (
    "당신은 한국어 업무 문장에서 의도, 마감, 자료, 액션을 추출하는 구조화 추출기입니다.\n\n"
    "반드시 지킬 규칙:\n"
    "1. JSON만 출력합니다.\n"
    "2. 원문에 없는 마감일, 자료, 액션을 만들지 않습니다.\n"
    "3. evidence는 반드시 원문에서 그대로 복사 가능한 짧은 구절이어야 합니다.\n"
    "4. 한 문장 안에 여러 액션이 있으면 actions 배열에 분리합니다.\n"
    '5. "하지 않아도 됩니다", "보류합니다", "제출하지 마세요" 같은 부정형은 '
    "no_action=true 또는 is_negated=true로 표시합니다.\n"
    '6. "처리해 주세요", "진행해 주세요", "챙겨 주세요" 같은 추상 동사는 '
    "주변 목적어를 보고 실행 가능한 action_text로 정리합니다.\n"
    "7. 의문문이라도 실제 요청이면 intent_type=request로 분류합니다.\n"
    "8. 설명, markdown, 코드블록을 출력하지 않습니다."
)


# Few-shot 3개 (알고리즘 팀 §6 — 복합 다중액션 / 추상동사 / 부정형)
_FEW_SHOT_1_USER = "회의록 확인하고 수정해서 공유해 주세요."
_FEW_SHOT_1_ASSISTANT = json.dumps({
    "intent_type": "request",
    "actions": [
        {"action_text": "회의록 확인", "action_type": "확인", "deadline_text": "",
         "material_refs": ["회의록"], "evidence": "회의록 확인하고", "is_negated": False},
        {"action_text": "회의록 수정", "action_type": "수정", "deadline_text": "",
         "material_refs": ["회의록"], "evidence": "수정해서", "is_negated": False},
        {"action_text": "회의록 공유", "action_type": "공유", "deadline_text": "",
         "material_refs": ["회의록"], "evidence": "공유해 주세요", "is_negated": False},
    ],
    "no_action": False,
    "reason_code": "multi_action",
}, ensure_ascii=False)

_FEW_SHOT_2_USER = "내일까지 제안서 정리해서 공유해 주세요."
_FEW_SHOT_2_ASSISTANT = json.dumps({
    "intent_type": "request",
    "actions": [
        {"action_text": "제안서 정리", "action_type": "정리", "deadline_text": "내일까지",
         "material_refs": ["제안서"], "evidence": "제안서 정리해서", "is_negated": False},
        {"action_text": "제안서 공유", "action_type": "공유", "deadline_text": "내일까지",
         "material_refs": ["제안서"], "evidence": "공유해 주세요", "is_negated": False},
    ],
    "no_action": False,
    "reason_code": "abstract_verb_resolved",
}, ensure_ascii=False)

_FEW_SHOT_3_USER = "이번에는 견적서를 제출하지 않아도 됩니다."
_FEW_SHOT_3_ASSISTANT = json.dumps({
    "intent_type": "no_action",
    "actions": [
        {"action_text": "견적서 제출", "action_type": "제출", "deadline_text": "",
         "material_refs": ["견적서"], "evidence": "제출하지 않아도", "is_negated": True},
    ],
    "no_action": True,
    "reason_code": "negated",
}, ensure_ascii=False)


def _build_chat_v1(text: str, parsed_hints: Optional[Dict[str, Any]] = None) -> str:
    """Qwen3 ChatML 템플릿 — system + few-shot 3개 + user.

    parsed_hints 가 있으면 user 메시지에 힌트 블록을 추가한다(모드 C/D).
    parsed_hints 가 비어 있거나 None 이면 LLM only(모드 B).
    """
    hints_block = ""
    if parsed_hints:
        deads = ", ".join(parsed_hints.get("deadlines", [])) or "없음"
        mats  = ", ".join(parsed_hints.get("materials", [])) or "없음"
        acts  = "; ".join(parsed_hints.get("actions",   [])) or "없음"
        hints_block = (
            "\n\n[parser 힌트 — 참고용, 원문 근거 없으면 무시]\n"
            f"마감 후보: {deads}\n자료 후보: {mats}\n액션 후보: {acts}"
        )

    return (
        "<|im_start|>system\n" + SYSTEM_PROMPT_V1 + "<|im_end|>\n"
        "<|im_start|>user\n" + _FEW_SHOT_1_USER + "<|im_end|>\n"
        "<|im_start|>assistant\n" + _FEW_SHOT_1_ASSISTANT + "<|im_end|>\n"
        "<|im_start|>user\n" + _FEW_SHOT_2_USER + "<|im_end|>\n"
        "<|im_start|>assistant\n" + _FEW_SHOT_2_ASSISTANT + "<|im_end|>\n"
        "<|im_start|>user\n" + _FEW_SHOT_3_USER + "<|im_end|>\n"
        "<|im_start|>assistant\n" + _FEW_SHOT_3_ASSISTANT + "<|im_end|>\n"
        "<|im_start|>user\n[원문]\n" + text + hints_block +
        "\n\n/no_think<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


_VALID_INTENT_TYPES = {"request", "report", "question", "instruction",
                       "schedule", "no_action", "other"}


def validate_v1_schema(data: Any) -> List[str]:
    """card1_action_extraction.v1 schema 검증 → 위반 사유 리스트 (빈 = 통과)."""
    errs: List[str] = []
    if not isinstance(data, dict):
        return ["root_not_object"]

    intent_type = data.get("intent_type")
    if not isinstance(intent_type, str) or intent_type not in _VALID_INTENT_TYPES:
        errs.append(f"invalid_intent_type:{intent_type!r}")

    if not isinstance(data.get("no_action"), bool):
        errs.append("no_action_not_bool")

    if not isinstance(data.get("reason_code"), str):
        errs.append("reason_code_not_string")

    actions = data.get("actions")
    if not isinstance(actions, list):
        errs.append("actions_not_list")
        return errs

    for idx, a in enumerate(actions):
        if not isinstance(a, dict):
            errs.append(f"actions[{idx}]_not_object")
            continue
        for key, typ in (
            ("action_text",   str),
            ("action_type",   str),
            ("deadline_text", str),
            ("evidence",      str),
            ("is_negated",    bool),
        ):
            if not isinstance(a.get(key), typ):
                errs.append(f"actions[{idx}].{key}_invalid")
        if not isinstance(a.get("material_refs"), list):
            errs.append(f"actions[{idx}].material_refs_not_list")
    return errs


_V1_GRAMMAR: Any = None  # lazy LlamaGrammar instance


def _get_v1_grammar() -> Any:
    """card1_action_extraction.v1 schema → LlamaGrammar (lazy, thread-safe)."""
    global _V1_GRAMMAR
    if _V1_GRAMMAR is not None:
        return _V1_GRAMMAR
    try:
        from llama_cpp import LlamaGrammar
    except ImportError:
        return None
    with _LLAMA_LOCK:
        if _V1_GRAMMAR is None:
            try:
                _V1_GRAMMAR = LlamaGrammar.from_json_schema(
                    json.dumps(CARD1_ACTION_EXTRACTION_V1_SCHEMA, ensure_ascii=False)
                )
            except Exception:
                _V1_GRAMMAR = False  # 영구 실패 마커
    return _V1_GRAMMAR if _V1_GRAMMAR is not False else None


def _call_llama_v1(prompt: str) -> str:
    """LLM_EXTRACT_CONFIG + JSON Schema grammar 강제 llama-cpp 호출."""
    llm = _get_llama_instance()
    if llm is None:
        raise RuntimeError("llama-cpp 모델 미로드 (BUTLER_LLM_MODEL_PATH 미설정)")

    cfg = dict(LLM_EXTRACT_CONFIG)
    cfg["stop"] = list(cfg.get("stop", [])) + ["<|im_end|>", "<|endoftext|>"]

    kwargs: Dict[str, Any] = {
        "prompt":         prompt,
        "max_tokens":     cfg["max_tokens"],
        "temperature":    cfg["temperature"],
        "top_p":          cfg["top_p"],
        "top_k":          cfg["top_k"],
        "repeat_penalty": cfg["repeat_penalty"],
        "stop":           cfg["stop"],
    }
    grammar = _get_v1_grammar()
    if grammar is not None:
        kwargs["grammar"] = grammar

    with _LLAMA_LOCK:
        out = llm.create_completion(**kwargs)
    return out["choices"][0]["text"]


_INTENT_TYPE_MAP_V1: Dict[str, IntentType] = {
    "request":     IntentType.REQUEST,
    "report":      IntentType.REPORT,
    "question":    IntentType.QUESTION,
    "instruction": IntentType.COMMAND,    # 알고리즘 팀 'instruction' ↔ enum COMMAND
    "command":     IntentType.COMMAND,
    "schedule":    IntentType.SCHEDULE,
    "no_action":   IntentType.NO_ACTION,
    "other":       IntentType.UNKNOWN,
    "unknown":     IntentType.UNKNOWN,
}


def _parse_v1_json(raw: str) -> Optional[dict]:
    """LLM raw text → dict (think 블록 제거 + 첫 JSON object 추출)."""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _v1_dict_to_extraction(data: dict, source_text: str) -> Card1Extraction:
    """v1 JSON dict → Card1Extraction (LLM 자기평가 confidence 폐기).

    - 단계 6.5.2 Patch 1: REPORT marker override.
    - 단계 6.5.3 Patch 1+2: REPORT(18) + COMMAND(13) normalizer chain.
      "~해 주세요" 계열은 SOFT_REQUEST에 없지만 COMMAND_MARKERS에도 없어서
      자동으로 REQUEST 유지 (알고리즘 팀 과잉 보정 방지).
    """
    from .intent_normalizer import normalize_intent_chain

    raw_type           = (data.get("intent_type") or "unknown").lower()
    fixed_type, why    = normalize_intent_chain(source_text, raw_type)
    intent_type        = _INTENT_TYPE_MAP_V1.get(fixed_type, IntentType.UNKNOWN)
    no_action          = bool(data.get("no_action"))
    reason_code        = str(data.get("reason_code", ""))[:40]
    if why != "OK":
        reason_code = why[:40]

    actions: List[ExtractedAction] = []
    deadline_raw_collect: List[str] = []
    materials_collect:    List[str] = []

    for a in data.get("actions", []):
        if not isinstance(a, dict):
            continue
        action_text = str(a.get("action_text", ""))[:120]
        if not action_text:
            continue
        evidence    = str(a.get("evidence", ""))[:200]
        action_type = str(a.get("action_type", ""))[:40]
        deadline_t  = str(a.get("deadline_text", ""))[:60]
        is_neg      = bool(a.get("is_negated", False))
        mat_refs    = [str(m)[:60] for m in (a.get("material_refs") or []) if m]

        actions.append(ExtractedAction(
            action_text     = action_text,
            owner           = "",
            due_date        = None,
            source_evidence = evidence,
            confidence      = 0.0,   # LLM 자기평가 폐기 — 후속 단계에서 재계산
            action_type     = action_type,
            deadline_text   = deadline_t,
            material_refs   = mat_refs,
            is_negated      = is_neg,
        ))
        if deadline_t and deadline_t not in deadline_raw_collect:
            deadline_raw_collect.append(deadline_t)
        for mref in mat_refs:
            if mref and mref not in materials_collect:
                materials_collect.append(mref)

    # no_action=True이면 actions를 모두 is_negated=True 처리(verifier가 제거)
    if no_action:
        for a in actions:
            a.is_negated = True

    intent = actions[0].action_text if actions else source_text[:60]

    return Card1Extraction(
        intent        = intent,
        intent_type   = intent_type,
        deadline      = None,
        deadline_raw  = deadline_raw_collect[0] if deadline_raw_collect else "",
        materials     = materials_collect,
        actions       = actions,
        sentence_type = SentenceType.DECLARATIVE,
        confidence    = 0.0,        # 후속 ConfidenceFeatures 단계에서 재계산
        needs_review  = True,
        reason_code   = reason_code,
    )


@dataclass
class V1ExtractResult:
    """단계 6.5.1 v1 추출 결과 — confidence 산출/verifier 직전 상태."""
    extraction:        Card1Extraction
    schema_valid:      bool
    retry_count:       int                = 0
    retry_reasons:     List[str]          = field(default_factory=list)
    raw_text_first:    str                = ""
    raw_text_retry:    str                = ""


def extract_with_llm_v1(
    text: str,
    parsed_hints: Optional[Dict[str, Any]] = None,
    llm_callable: Optional[Callable[[str], str]] = None,
) -> V1ExtractResult:
    """알고리즘 팀 §6 v1 — Qwen3-4B JSON Schema 추출 + 1회 retry.

    parsed_hints=None → 모드 B (LLM only). 비어있지 않으면 모드 C/D.
    llm_callable: 테스트 주입용. None이면 _call_llama_v1 사용.
    """
    call_fn = llm_callable or _call_llama_v1

    prompt = _build_chat_v1(text, parsed_hints)
    raw1   = call_fn(prompt)
    data1  = _parse_v1_json(raw1)
    errs1  = validate_v1_schema(data1) if data1 is not None else ["json_parse_failed"]

    if not errs1 and data1 is not None:
        return V1ExtractResult(
            extraction     = _v1_dict_to_extraction(data1, text),
            schema_valid   = True,
            retry_count    = 0,
            retry_reasons  = [],
            raw_text_first = raw1,
        )

    # ── retry 1회 — 위반 사유를 user 메시지에 첨부 ────────────────────────────
    retry_user = (
        "[원문]\n" + text +
        "\n\n[직전 출력 위반]\n- " + "\n- ".join(errs1[:6]) +
        "\n\n위반을 모두 수정해서 다시 JSON만 출력하세요.\n\n/no_think"
    )
    base = _build_chat_v1(text, parsed_hints)
    # 마지막 user 블록을 retry_user로 교체
    retry_prompt = re.sub(
        r"<\|im_start\|>user\n\[원문\][\s\S]*?<\|im_end\|>\n<\|im_start\|>assistant\n$",
        f"<|im_start|>user\n{retry_user}<|im_end|>\n<|im_start|>assistant\n",
        base,
    )
    raw2  = call_fn(retry_prompt)
    data2 = _parse_v1_json(raw2)
    errs2 = validate_v1_schema(data2) if data2 is not None else ["json_parse_failed"]

    schema_ok = (not errs2) and (data2 is not None)
    final     = data2 if schema_ok else (data1 if data1 is not None else {
        "intent_type": "unknown", "actions": [],
        "no_action": False, "reason_code": "retry_failed",
    })
    return V1ExtractResult(
        extraction     = _v1_dict_to_extraction(final, text),
        schema_valid   = schema_ok,
        retry_count    = 1,
        retry_reasons  = errs1,
        raw_text_first = raw1,
        raw_text_retry = raw2,
    )
