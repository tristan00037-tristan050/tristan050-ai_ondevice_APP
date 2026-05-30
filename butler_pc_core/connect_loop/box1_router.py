from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .policy_precheck import PolicyPrecheck, ensure_policy_precheck, is_executable_policy
from .schema_validator import validate_chat_request, validate_router_decision

IntentLabel = Literal[
    "memory_search",
    "form_convert",
    "draft_write",
    "accounting_classify",
    "general_chat",
    "unknown",
]

KNOWN_INTENT_THRESHOLD = 0.62
AMBIGUITY_DELTA = 0.12

INTENT_ROUTE_MAP: dict[str, tuple[str, str]] = {
    "memory_search": ("helper1", "POST /v1/helpers/1/search"),
    "form_convert": ("2", "POST /v1/cards/2/rewrite"),
    "draft_write": ("3", "POST /v1/cards/3/draft"),
    "accounting_classify": ("5", "POST /accounting/classify"),
    "general_chat": ("chat", "none"),
    "unknown": ("none", "none"),
}

FALLBACK_INTENTS = {"general_chat", "unknown"}

_KEYWORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "memory_search": {
        "strong": (
            "찾아줘", "검색", "어디 있었", "이전 문서", "과거 문서", "문서 찾아", "기억", "근거 찾아",
        ),
        "weak": ("이전", "과거", "문서", "자료", "기록", "내역"),
    },
    "form_convert": {
        "strong": (
            "우리 양식", "변환", "서식 맞", "양식 변경", "양식으로", "외부 양식", "포맷 변경",
        ),
        "weak": ("양식", "서식", "변경", "맞춰", "정리"),
    },
    "draft_write": {
        "strong": (
            "초안", "작성", "메일 써", "보고서 작성", "안건 작성", "문안", "써줘", "새 문서",
        ),
        "weak": ("메일", "보고서", "안건", "작성해", "제안서"),
    },
    "accounting_classify": {
        "strong": (
            "거래내역", "계정과목", "회계분류", "회계 분류", "분개", "비용 분류", "은행거래", "전표",
        ),
        "weak": ("회계", "비용", "입금", "출금", "매출", "분류"),
    },
    "general_chat": {
        "strong": ("안녕", "기능 설명", "뭐 할 수", "도움말", "사용법", "일반 질문"),
        "weak": ("설명", "질문", "가능", "소개"),
    },
}


@dataclass(frozen=True)
class RouterRuntimeContext:
    """Runtime-only input for Box 1 routing.

    The text value is used only inside this process for classification. It is
    never copied into RouterDecision, usage audit records, or evidence files.
    """

    runtime_text: str | None
    policy_precheck: PolicyPrecheck
    policy_reason_code: str | None = None
    runtime_attachment_hints: tuple[str, ...] = field(default_factory=tuple)
    policy_context: dict[str, Any] = field(default_factory=dict)


class Box1Router(Protocol):
    def decide(self, chat_request: dict[str, Any], runtime: RouterRuntimeContext) -> dict[str, Any]:
        """Return a router_decision.v1-compatible dict."""


@dataclass(frozen=True)
class IntentScore:
    intent_label: str
    strong_match_count: int
    weak_match_count: int

    @property
    def score(self) -> float:
        return min(1.0, 0.35 + 0.15 * self.strong_match_count + 0.05 * self.weak_match_count)

    @property
    def has_signal(self) -> bool:
        return self.strong_match_count > 0 or self.weak_match_count > 0


class RuleBasedBox1Router:
    """PR-C minimal Box 1 router.

    This lightweight classifier intentionally avoids model inference. It is a
    deterministic gate for PR-C and delegates endpoint execution to later PRs.
    """

    def decide(self, chat_request: dict[str, Any], runtime: RouterRuntimeContext) -> dict[str, Any]:
        validate_chat_request(chat_request)
        policy = ensure_policy_precheck(runtime.policy_precheck)

        if not _runtime_text_matches_request_digest(runtime.runtime_text, chat_request["text_digest"]):
            return self._build_decision(
                request_id=chat_request["request_id"],
                intent="unknown",
                confidence=0.0,
                reason="TEXT_DIGEST_MISMATCH_FALLBACK",
                policy=policy,
                force_endpoint_none=True,
            )

        intent, confidence, reason = classify_intent(runtime.runtime_text)
        return self._build_decision(
            request_id=chat_request["request_id"],
            intent=intent,
            confidence=confidence,
            reason=reason,
            policy=policy,
            force_endpoint_none=not is_executable_policy(policy),
        )

    def _build_decision(
        self,
        *,
        request_id: str,
        intent: str,
        confidence: float,
        reason: str,
        policy: PolicyPrecheck,
        force_endpoint_none: bool,
    ) -> dict[str, Any]:
        box_id, endpoint = INTENT_ROUTE_MAP[intent]
        fallback = intent in FALLBACK_INTENTS

        if force_endpoint_none:
            endpoint = "none"
            fallback = True
            if policy == "needs_review":
                reason = "POLICY_REVIEW_FALLBACK"
            elif policy == "block":
                reason = "POLICY_BLOCK_FALLBACK"

        decision = {
            "request_id": request_id,
            "intent_label": intent,
            "target_box_id": box_id,
            "target_endpoint": endpoint,
            "routing_confidence": round(float(confidence), 4),
            "reason_code": reason,
            "fallback_required": fallback,
            "policy_precheck": policy,
            "schema_version": "router_decision.v1",
        }
        validate_router_decision(decision)
        return decision


def classify_intent(runtime_text: str | None) -> tuple[str, float, str]:
    if runtime_text is None or not runtime_text.strip():
        return "unknown", 0.0, "NO_RUNTIME_TEXT_FALLBACK"

    normalized = " ".join(runtime_text.lower().split())
    scores = [_score_intent(intent, normalized) for intent in _KEYWORDS]
    scores.sort(key=lambda item: item.score, reverse=True)
    best = scores[0]
    second = scores[1]

    if not best.has_signal or best.score < KNOWN_INTENT_THRESHOLD:
        return "unknown", best.score if best.has_signal else 0.0, "LOW_CONFIDENCE_FALLBACK"

    if second.has_signal and (second.score >= KNOWN_INTENT_THRESHOLD or (best.score - second.score) < AMBIGUITY_DELTA):
        return "unknown", best.score, "AMBIGUOUS_INTENT_FALLBACK"

    return best.intent_label, best.score, _reason_for_intent(best.intent_label)


def _runtime_text_matches_request_digest(runtime_text: str | None, expected_text_digest: str) -> bool:
    if runtime_text is None or not runtime_text.strip():
        return True
    return _sha256_text(runtime_text) == expected_text_digest


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _score_intent(intent: str, text: str) -> IntentScore:
    family = _KEYWORDS[intent]
    strong = _count_keywords(text, family["strong"])
    weak = _count_keywords(text, family["weak"])
    return IntentScore(intent, strong, weak)


def _count_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _reason_for_intent(intent: str) -> str:
    return {
        "memory_search": "INTENT_MEMORY_SEARCH",
        "form_convert": "INTENT_FORM_CONVERT",
        "draft_write": "INTENT_DRAFT_WRITE",
        "accounting_classify": "INTENT_ACCOUNTING_CLASSIFY",
        "general_chat": "INTENT_GENERAL_CHAT",
    }.get(intent, "LOW_CONFIDENCE_FALLBACK")
