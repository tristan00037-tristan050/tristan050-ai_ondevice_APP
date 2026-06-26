"""PR-C Box1 router: chat request to router_decision.v1.

The router is a contract consumer. It validates PR-A request/decision schemas,
uses device-local runtime content only for classification, and never calls a
card/helper endpoint.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from .policy_precheck import (
    PolicyPrecheck,
    ensure_policy_precheck,
    is_route_allowed,
    policy_reason_code,
)
from .schema_validator import validate_chat_request, validate_router_decision

KNOWN_INTENT_THRESHOLD = 0.62
AMBIGUITY_DELTA = 0.12
BUSINESS_INTENTS = {"memory_search", "form_convert", "draft_write", "accounting_classify"}
HIGH_RISK_INTENTS = {"accounting_classify"}
LOW_CONFIDENCE_GENERAL_CHAT_REASON = "GENERAL_CHAT_SAFE_DEFAULT"
ACCOUNTING_GUARD_REASON = "ACCOUNTING_SIGNAL_REQUIRES_CARD"
BUSINESS_GUARD_REASON = "BUSINESS_SIGNAL_REQUIRES_CARD"

ROUTE_TABLE: dict[str, tuple[str, str]] = {
    "memory_search": ("helper1", "POST /v1/helpers/1/search"),
    "form_convert": ("2", "POST /v1/cards/2/rewrite"),
    "draft_write": ("3", "POST /v1/cards/3/draft"),
    "accounting_classify": ("5", "POST /accounting/classify"),
    "general_chat": ("chat", "none"),
    "unknown": ("none", "none"),
}

FALLBACK_INTENTS = {"general_chat", "unknown"}

_SIGNALS: dict[str, dict[str, tuple[str, ...]]] = {
    "memory_search": {
        "strong": ("찾아", "찾아줘", "검색", "어디 있었지", "문서 찾아", "기록 찾아"),
        "weak": ("이전", "과거", "지난", "예전", "보관"),
    },
    "form_convert": {
        "strong": ("우리 양식", "변환", "서식 맞춰", "양식 변경", "포맷 변경"),
        "weak": ("형식", "템플릿", "서식", "맞춰줘"),
    },
    "draft_write": {
        "strong": ("초안", "작성", "메일 써", "보고서 작성", "안건 작성"),
        "weak": ("문안", "써줘", "정리해서 보내", "새 상황"),
    },
    "accounting_classify": {
        "strong": ("거래내역", "계정과목", "회계분류", "분개", "매출", "비용 분류"),
        "weak": ("비용", "수입", "통장", "입금", "출금"),
    },
    "general_chat": {
        "strong": (
            "안녕하세요",
            "무엇을 할 수",
            "기능 설명",
            "도움말",
            "사용법",
            "소개",
            "너를 소개",
            "자기소개",
            "무엇을 목표",
            "목표로 만들어",
            "자유대화",
            "대화 가능",
        ),
        "weak": ("고마워", "감사", "질문", "설명해", "말해줘", "알려줘", "궁금", "대화"),
    },
}


@dataclass(frozen=True)
class RouterRuntimeContext:
    runtime_text: str | None
    policy_precheck: PolicyPrecheck
    policy_reason_code: str | None = None


class Box1Router(Protocol):
    def decide(self, chat_request: dict[str, Any], runtime: RouterRuntimeContext) -> dict[str, Any]:
        """Return router_decision.v1. The returned dict contains no runtime content."""


@dataclass(frozen=True)
class _IntentScore:
    intent_label: str
    score: float
    strong_count: int
    weak_count: int


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def _score_intents(text: str) -> list[_IntentScore]:
    normalized = " ".join(text.casefold().split())
    scores: list[_IntentScore] = []
    for intent, signal in _SIGNALS.items():
        strong_count = _count_terms(normalized, signal["strong"])
        weak_count = _count_terms(normalized, signal["weak"])
        score = min(1.0, 0.35 + (0.15 * strong_count) + (0.05 * weak_count))
        if strong_count == 0 and weak_count == 0:
            score = 0.0
        scores.append(_IntentScore(intent, round(score, 4), strong_count, weak_count))
    return sorted(scores, key=lambda item: item.score, reverse=True)


def _has_signal(score: _IntentScore) -> bool:
    return score.strong_count > 0 or score.weak_count > 0


def canonical_sha256(text: str) -> str:
    """chat_request.text_digest 와 동일 규칙으로 원문 digest 를 만든다.

    계약(chat_request.v1)의 text_digest 는 '입력 원문의 sha256' 이며 형식은
    `sha256:<64 hex>`. 정규화 없이 **원문 UTF-8 바이트**를 해시한다(생성·검증 양측이
    동일 규칙을 써야 false mismatch 가 발생하지 않는다).
    """
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def runtime_text_digest_ok(runtime_text: str | None, chat_request: dict[str, Any]) -> bool | None:
    """runtime_text 와 chat_request.text_digest 의 일치 여부.

    반환: None = 대조 스킵(runtime_text 또는 text_digest 부재), True/False = 일치 여부.
    (text_digest 는 chat_request.v1 에서 required 이므로 스킵 경로는 방어적 분기다.)
    """
    text_digest = chat_request.get("text_digest")
    if not runtime_text or not text_digest:
        return None
    return canonical_sha256(runtime_text) == text_digest


def _classify(runtime_text: str | None) -> tuple[str, float, str]:
    if runtime_text is None or not runtime_text.strip():
        return "unknown", 0.0, "RUNTIME_TEXT_MISSING"

    scores = _score_intents(runtime_text)
    by_intent = {score.intent_label: score for score in scores}
    empty = _IntentScore("unknown", 0.0, 0, 0)

    # 회계는 weak 신호 하나라도 일반대화로 보내지 않는다. 임계 이상이면 Box5,
    # 미달이면 카드 안내로 남겨 금액/계정 환각을 막는다.
    accounting = by_intent.get("accounting_classify", empty)
    if accounting.intent_label in HIGH_RISK_INTENTS and _has_signal(accounting):
        if accounting.score >= KNOWN_INTENT_THRESHOLD:
            second = max(
                (
                    score
                    for score in scores
                    if score.intent_label in BUSINESS_INTENTS and score.intent_label != "accounting_classify"
                ),
                key=lambda item: item.score,
                default=empty,
            )
            if second.score > 0 and (accounting.score - second.score) < AMBIGUITY_DELTA:
                return "unknown", accounting.score, "AMBIGUOUS_INTENT_FALLBACK"
            return "accounting_classify", accounting.score, "INTENT_KEYWORD_MATCH"
        return "unknown", accounting.score, ACCOUNTING_GUARD_REASON

    business_scores = sorted(
        [score for score in scores if score.intent_label in BUSINESS_INTENTS],
        key=lambda item: item.score,
        reverse=True,
    )
    best = business_scores[0]
    second = business_scores[1] if len(business_scores) > 1 else empty

    if best.score >= KNOWN_INTENT_THRESHOLD:
        if second.score > 0 and (best.score - second.score) < AMBIGUITY_DELTA:
            return "unknown", best.score, "AMBIGUOUS_INTENT_FALLBACK"
        return best.intent_label, best.score, "INTENT_KEYWORD_MATCH"
    if best.strong_count > 0:
        return "unknown", best.score, BUSINESS_GUARD_REASON

    general = by_intent.get("general_chat", _IntentScore("general_chat", 0.0, 0, 0))
    return "general_chat", max(general.score, 0.35), LOW_CONFIDENCE_GENERAL_CHAT_REASON


class RuleBasedBox1Router:
    def decide(self, chat_request: dict[str, Any], runtime: RouterRuntimeContext) -> dict[str, Any]:
        validate_chat_request(chat_request)
        policy = ensure_policy_precheck(runtime.policy_precheck)

        intent_label, confidence, reason_code = _classify(runtime.runtime_text)

        # Codex P2 (2026-05-30): runtime_text ↔ chat_request.text_digest fail-closed 대조.
        # 로컬 runtime context 가 다른 대기 요청과 잘못 짝지어지면 wrong text 를 다른
        # request_id/digest 로 라우팅해 감사 추적을 오염시킨다. 불일치 시 fail-closed.
        if runtime_text_digest_ok(runtime.runtime_text, chat_request) is False:
            intent_label, confidence, reason_code = "unknown", 0.0, "TEXT_DIGEST_MISMATCH"

        target_box_id, target_endpoint = ROUTE_TABLE[intent_label]
        fallback_required = intent_label in FALLBACK_INTENTS

        if not is_route_allowed(policy):
            target_endpoint = "none"
            fallback_required = True
            reason_code = policy_reason_code(policy, runtime.policy_reason_code)

        decision = {
            "request_id": chat_request["request_id"],
            "intent_label": intent_label,
            "target_box_id": target_box_id,
            "target_endpoint": target_endpoint,
            "routing_confidence": confidence,
            "reason_code": reason_code,
            "fallback_required": fallback_required,
            "policy_precheck": policy,
            "schema_version": "router_decision.v1",
        }
        validate_router_decision(decision)
        return decision
