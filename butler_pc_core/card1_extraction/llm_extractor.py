"""llm_extractor.py — Qwen3-4B structured extraction (알고리즘 팀 §6).

우선순위:
  1. SKIP_LLM=true → 즉시 heuristic fallback (테스트/CI)
  2. sidecar HTTP (127.0.0.1:8765)
  3. 없으면 heuristic fallback
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .contracts import (
    Card1Extraction,
    ExtractedAction,
    IntentType,
    SentenceType,
)

_SIDECAR_INFERENCE_URL = "http://127.0.0.1:8765/inference"
_SIDECAR_HEALTH_URL    = "http://127.0.0.1:8765/health"

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


def _get_callable() -> Optional[Callable[[str], str]]:
    if os.environ.get("SKIP_LLM") == "true":
        return None
    if _sidecar_available():
        return _call_sidecar
    return None


def _parse_llm_response(raw: str) -> Optional[dict]:
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
    _report_re = _re.compile(
        r"(?:보고드립니다|보고드리겠습니다|말씀드리겠습니다|공유드립니다"
        r"|전달드립니다|알려드립니다|공유해드립니다|보고합니다"
        r"|드립니다|드리겠습니다|예정입니다|하겠습니다)"
    )
    # QUESTION: 정보 확인형 의문문 — 행동 요청이 없는 순수 질문
    _question_marker_re = _re.compile(
        r"(?:언제|가능한지|됩니까\s*[?？]?|받으셨|어떻게|무엇|어디|왜)"
    )
    _question_form_re = _re.compile(
        r"(?:나요\s*[?？]?|까요\s*[?？]?|합니까\s*[?？]?|[?？])"
    )
    # REQUEST 표지 (QUESTION과 구분 기준)
    _request_keyword_re = _re.compile(
        r"(?:주세요|해주세요|부탁드|주시기\s*바랍니다|주시면)"
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
