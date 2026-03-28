from __future__ import annotations

import re
from dataclasses import dataclass


HALLUCINATION_PATTERNS = {
    "general": [
        r"아마도\s+\w+일\s+것이다",
        r"\w+으?로\s+알려져\s+있다",
        r"정확하지\s+않을\s+수\s+있",
        r"추정되는",
        r"확인되지\s+않은",
    ],
    "legal": [
        r"판결이\s+내려진\s+것으로\s+보인다",
        r"법적으로\s+추정",
    ],
    "finance": [
        r"수익이\s+예상된다",
        r"투자\s+추정",
        r"주가\s+전망",
    ],
    "medical": [
        r"치료\s+효과가\s+있을\s+것으로",
        r"부작용\s+가능성\s+있음",
    ],
}

DOMAIN_KEYWORDS = {
    "legal": ["판결", "법원", "소송", "계약서", "법률", "조항", "규정"],
    "finance": ["주식", "금리", "투자", "펀드", "대출", "보험", "세금"],
    "medical": ["진단", "처방", "증상", "치료", "약물", "수술", "환자"],
}

DOMAIN_HALLUCINATION_LIMIT = {
    "legal": 0,
    "finance": 0,
    "medical": 0,
    "general": 2,
}

RESTRICTED_DOMAINS = {"legal", "finance", "medical"}


@dataclass
class QualityResult:
    score: float
    domain: str
    hallucination_count: int
    ngram_duplication_ratio: float
    passed: bool
    reject_reason: str = ""


class QualityFilter:
    def __init__(
        self,
        min_score: float = 0.3,
        max_ngram_dup: float = 0.4,
        restricted_min_score: float = 0.5,
    ):
        self.min_score = float(min_score)
        self.max_ngram_dup = float(max_ngram_dup)
        self.restricted_min_score = float(restricted_min_score)

    def _detect_domain(self, text: str) -> str:
        scores = {
            domain: sum(1 for keyword in keywords if keyword in text)
            for domain, keywords in DOMAIN_KEYWORDS.items()
        }
        best_domain = max(scores, key=scores.get)
        return best_domain if scores[best_domain] > 0 else "general"

    def _hallucination_count(self, text: str, domain: str) -> int:
        patterns = list(HALLUCINATION_PATTERNS.get("general", []))
        patterns.extend(HALLUCINATION_PATTERNS.get(domain, []))
        return sum(1 for pattern in patterns if re.search(pattern, text))

    @staticmethod
    def _ngram_dup(text: str, n: int = 4) -> float:
        tokens = [tok for tok in re.split(r"\s+", text.strip()) if tok]
        if len(tokens) < n:
            return 0.0
        ngrams = [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
        return 1.0 - (len(set(ngrams)) / len(ngrams))

    def evaluate(self, text: str) -> QualityResult:
        domain = self._detect_domain(text)
        hallucination_count = self._hallucination_count(text, domain)
        ngram_duplication = self._ngram_dup(text)
        hallucination_limit = DOMAIN_HALLUCINATION_LIMIT.get(domain, 2)

        score = 1.0 - (hallucination_count * 0.15) - (ngram_duplication * 0.5)
        if domain in RESTRICTED_DOMAINS:
            score -= 0.05 * hallucination_count
        score = max(0.0, min(1.0, score))

        reject_reason = ""
        if hallucination_count > hallucination_limit:
            reject_reason = "hallucination_dense"
        elif ngram_duplication > self.max_ngram_dup:
            reject_reason = "ngram_dup_too_high"
        elif domain in RESTRICTED_DOMAINS and score < self.restricted_min_score:
            reject_reason = "domain_policy_reject"
        elif score < self.min_score:
            reject_reason = "score_too_low"

        return QualityResult(
            score=round(score, 4),
            domain=domain,
            hallucination_count=hallucination_count,
            ngram_duplication_ratio=round(ngram_duplication, 4),
            passed=(reject_reason == ""),
            reject_reason=reject_reason,
        )
