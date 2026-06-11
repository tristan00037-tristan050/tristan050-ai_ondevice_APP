"""Box3 real 융합 — claim 단위 grounding 판정(단일 계약 ClaimVerdict 출력).

- 베이스: maindev real_grounding(numeric 대조·부정모순·evidence_kind coverage·
  '키워드 overlap 만으론 supported 아님' 경계 0.60).
- 흡수: alg _facts / _entailment(숫자+날짜 사실단위 대조), codex
  ClaimGroundingSummary(supported/unsupported/no_evidence/non_claim count + rate
  + citation_accuracy) 및 citation 연결.

판정은 supported / unsupported / no_evidence / non_claim 4종, reason_code 는
EVIDENCE_ENTAILS / EVIDENCE_CONTRADICTS / NO_MATCHING_EVIDENCE / NON_FACTUAL 4종으로
단일 계약(real_contracts.ClaimVerdict)에 고정한다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable

from .real_contracts import (
    ClaimVerdict,
    DraftClaim,
    EvidenceUnit,
    sha256_text,
)

_SENTENCE_SPLIT_RE = re.compile(r"\n+|[.!?。！？]+\s*|다\.\s*|요\.\s*")
_TOKEN_RE = re.compile(r"[0-9]+(?:[,.][0-9]+)*(?:원|만원|억원|%|일|월|년)?|[A-Za-z가-힣]{2,}")
_NUM_RE = re.compile(r"[0-9]+(?:[,.][0-9]+)*(?:원|만원|억원|%|일|월|년)?")
# alg 흡수 — 단위 포함 숫자 + 날짜를 사실단위로 추출(maindev numeric_tokens 의 상위집합).
_FACT_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:억원|억|만원|만|%|개사|개|명|일|월|년)?")
_FACT_DATE_RE = re.compile(r"\d{4}년\s*\d{1,2}월(?:\s*\d{1,2}일)?|\d{1,2}월\s*\d{1,2}일")
_FULL_DATE_RE = re.compile(r"(?P<year>\d{4})년\s*(?P<month>\d{1,2})월(?:\s*(?P<day>\d{1,2})일)?")
_MONTH_DAY_RE = re.compile(r"(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일")
_NON_CLAIM_PREFIXES = ("제목", "목차", "인사말", "감사합니다", "안녕하세요")
_FACT_HINTS = (
    "계약", "금액", "일정", "담당", "발행", "합의", "납품", "보고", "완료", "검토",
    "요청", "승인", "기한", "수량", "기간", "비용", "매출", "지급", "수정",
)
_NEGATION_MARKERS = ("아니다", "없다", "취소", "거절", "불가", "미승인", "보류")


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().replace("•", " ").replace("-", " ").split())


def tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(normalize_text(text)))


def numeric_tokens(text: str) -> set[str]:
    return set(_NUM_RE.findall(normalize_text(text)))


def _facts(text: str) -> set[str]:
    """alg 흡수 — 단위 포함 숫자/날짜 사실단위 집합(공백 제거)."""
    nums = {m.group(0).replace(" ", "") for m in _FACT_NUM_RE.finditer(text) if m.group(0).strip()}
    dates = {m.group(0).replace(" ", "") for m in _FACT_DATE_RE.finditer(text)}
    # Evidence 가 "2026년 6월 1일"처럼 더 구체적인 날짜를 담으면
    # "6월 1일" 수준의 claim 도 포섭된다. 반대로 claim 이 연도까지 명시했는데
    # evidence 가 월/일만 가진 경우는 full-date fact 가 빠져 계속 차단된다.
    for match in _FULL_DATE_RE.finditer(text):
        month = match.group("month")
        day = match.group("day")
        dates.add(f"{match.group('year')}년{month}월")
        dates.add(f"{month}월")
        if day is not None:
            dates.add(f"{match.group('year')}년{month}월{day}일")
            dates.add(f"{month}월{day}일")
            dates.add(f"{day}일")
    for match in _MONTH_DAY_RE.finditer(text):
        dates.add(f"{match.group('month')}월{match.group('day')}일")
    return nums | dates


def _kind_for_unit(text: str) -> str:
    normalized = normalize_text(text)
    if "|" in text or "\t" in text or len(numeric_tokens(text)) >= 3:
        return "table"
    if "그림" in normalized or "figure" in normalized or "차트" in normalized or "도표" in normalized:
        return "figure"
    return "text"


def extract_evidence_units(reference_docs: list[str]) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    for doc_index, doc in enumerate(reference_docs):
        source_digest = sha256_text(doc)
        chunks = [part.strip() for part in re.split(r"\n{2,}|(?<=다\.)\s+", doc) if part.strip()]
        if not chunks and doc.strip():
            chunks = [doc.strip()]
        for unit_index, chunk in enumerate(chunks):
            units.append(EvidenceUnit(
                evidence_id=f"e{doc_index + 1}-{unit_index + 1}",
                source_digest=source_digest,
                evidence_digest=sha256_text(chunk),
                kind=_kind_for_unit(chunk),  # type: ignore[arg-type]
                text_runtime_only=chunk,
            ))
    return units


def _is_non_claim(sentence: str) -> bool:
    stripped = sentence.strip()
    if not stripped:
        return True
    if stripped in {"보고서", "보고", "요약", "초안"}:
        return True
    if any(stripped.startswith(prefix) for prefix in _NON_CLAIM_PREFIXES):
        return True
    normalized = normalize_text(stripped)
    if "[문서에 근거 없음]" in stripped:
        return True
    if "근거 범위에서 확인" in normalized:
        return True
    if (
        len(tokens(stripped)) < 3
        and not numeric_tokens(stripped)
        and not any(hint in normalized for hint in _FACT_HINTS)
    ):
        return True
    return False


def _is_factual(sentence: str) -> bool:
    if _is_non_claim(sentence):
        return False
    if numeric_tokens(sentence):
        return True
    normalized = normalize_text(sentence)
    return any(hint in normalized for hint in _FACT_HINTS)


def extract_claims(draft_text: str) -> list[DraftClaim]:
    claims: list[DraftClaim] = []
    raw_parts: list[str] = []
    for line in draft_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line and len(line.split(":", 1)[0]) <= 20:
            # 제목/확인필요 등 라벨은 표현 메타데이터이므로 사실 분모를 부풀리지 않는다.
            # 배경/핵심내용/최종문안처럼 한 라벨 안에 여러 사실문이 들어오면 문장 단위로 다시 쪼갠다.
            label, content = line.split(":", 1)
            label = label.strip()
            label_norm = label.replace(" ", "")
            content = content.strip()

            if label_norm in {"제목", "확인필요"}:
                raw_parts.append(label)
            elif content:
                raw_parts.extend(part.strip() for part in _SENTENCE_SPLIT_RE.split(content) if part.strip())
            else:
                raw_parts.append(label)
        else:
            raw_parts.extend(part.strip() for part in _SENTENCE_SPLIT_RE.split(line) if part.strip())
    for index, sentence in enumerate(raw_parts, start=1):
        factual = _is_factual(sentence)
        claim_type = "factual" if factual else "non_claim"
        claims.append(DraftClaim(
            claim_id=f"c{index}",
            claim_digest=sha256_text(sentence),
            is_factual=factual,
            claim_type=claim_type,
            claim_text_runtime_only=sentence,
        ))
    return claims


def _overlap_score(claim_text: str, evidence_text: str) -> float:
    claim_tokens = tokens(claim_text) - set(_NEGATION_MARKERS)
    evidence_tokens = tokens(evidence_text) - set(_NEGATION_MARKERS)
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))


def _has_negation_contradiction(claim_text: str, evidence_text: str) -> bool:
    claim_norm = normalize_text(claim_text)
    evidence_norm = normalize_text(evidence_text)
    claim_neg = any(marker in claim_norm for marker in _NEGATION_MARKERS)
    evidence_neg = any(marker in evidence_norm for marker in _NEGATION_MARKERS)
    return claim_neg != evidence_neg and _overlap_score(claim_text, evidence_text) >= 0.55


def verdict_claim(claim: DraftClaim, evidence_units: list[EvidenceUnit]) -> ClaimVerdict:
    if not claim.is_factual:
        return ClaimVerdict(claim.claim_id, claim.claim_digest, "non_claim", [], 1.0, "NON_FACTUAL")

    claim_text = claim.claim_text_runtime_only
    evidence_all_text = "\n".join(unit.text_runtime_only for unit in evidence_units)

    # alg 흡수 — 사실단위(숫자+날짜) 대조. claim 의 사실이 근거에 포섭되지 않으면 모순.
    claim_facts = _facts(claim_text)
    evidence_facts = _facts(evidence_all_text)
    if claim_facts and not claim_facts.issubset(evidence_facts):
        return ClaimVerdict(claim.claim_id, claim.claim_digest, "unsupported", [], 0.95, "EVIDENCE_CONTRADICTS")

    best_unit: EvidenceUnit | None = None
    best_score = 0.0
    contradiction = False
    for unit in evidence_units:
        score = _overlap_score(claim_text, unit.text_runtime_only)
        if _has_negation_contradiction(claim_text, unit.text_runtime_only):
            contradiction = True
            best_unit = unit
            best_score = max(best_score, score)
            break
        if score > best_score:
            best_score = score
            best_unit = unit

    if contradiction:
        return ClaimVerdict(
            claim.claim_id, claim.claim_digest, "unsupported",
            [best_unit.evidence_digest] if best_unit else [], 0.95, "EVIDENCE_CONTRADICTS",
        )

    # 직접 지지는 숫자/사실 정합(위에서 확인) + 단일 근거와의 강한 의미 overlap 을 함께 요구한다.
    # 키워드가 코퍼스 어딘가에 등장한다는 이유만으로 supported 표기하지 않는다(경계 0.60).
    if best_unit is not None and best_score >= 0.60:
        return ClaimVerdict(
            claim.claim_id, claim.claim_digest, "supported",
            [best_unit.evidence_digest], min(0.99, round(best_score, 4)), "EVIDENCE_ENTAILS",
        )
    return ClaimVerdict(claim.claim_id, claim.claim_digest, "no_evidence", [], 0.0, "NO_MATCHING_EVIDENCE")


def ground_claims(claims: list[DraftClaim], evidence_units: list[EvidenceUnit]) -> list[ClaimVerdict]:
    return [verdict_claim(claim, evidence_units) for claim in claims]


def evidence_kind_coverage(evidence_units: list[EvidenceUnit], citations: Iterable[dict[str, str]]) -> float:
    units_by_digest = {unit.evidence_digest: unit for unit in evidence_units}
    required = {unit.evidence_digest for unit in evidence_units if unit.kind in {"table", "figure"}}
    if not required:
        return 1.0
    cited = {
        citation.get("evidence_digest")
        for citation in citations
        if citation.get("evidence_digest") in units_by_digest
    }
    return len(required & cited) / len(required)


@dataclass(frozen=True)
class ClaimGroundingSummary:
    """codex 흡수 — 판정 요약(영속 가능, digest/지표만)."""

    factual_claim_count: int
    supported_claim_count: int
    unsupported_claim_count: int
    no_evidence_claim_count: int
    non_claim_count: int
    unsupported_claim_rate: float
    no_evidence_rate: float
    citation_accuracy: float
    claim_grounding_verified: bool
    fail_class: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def summarize_grounding(verdicts: list[ClaimVerdict]) -> ClaimGroundingSummary:
    """ClaimVerdict 리스트에서 codex 형식 요약을 산출한다.

    citation_accuracy = (근거 digest 를 보유한 supported) / supported.
    supported 는 구성상 evidence_digests 를 보유하므로 인용 누락 시에만 하락한다.
    """
    factual = [v for v in verdicts if v.support_level != "non_claim"]
    supported = [v for v in factual if v.support_level == "supported"]
    unsupported = [v for v in factual if v.support_level == "unsupported"]
    no_evidence = [v for v in factual if v.support_level == "no_evidence"]
    cited_supported = [v for v in supported if v.evidence_digests]
    factual_count = len(factual)
    unsupported_rate = 0.0 if factual_count == 0 else len(unsupported) / factual_count
    no_evidence_rate = 0.0 if factual_count == 0 else len(no_evidence) / factual_count
    citation_accuracy = 0.0 if not supported else len(cited_supported) / len(supported)

    if factual_count == 0:
        fail_class: str | None = "BLOCK_NO_FACTUAL_CLAIMS"
    elif unsupported:
        fail_class = "BLOCK_UNSUPPORTED_CLAIM"
    elif no_evidence_rate > 0.05:
        # SSOT 임계(≤0.05)와 일치 — 허용 한도 내 no_evidence 는 요약을 blocked 로 표시하지
        # 않는다(metric_fail_class 와 동일 정책 → stage_trace 모순 방지).
        fail_class = "NEEDS_REVIEW_NO_EVIDENCE_CLAIM"
    else:
        fail_class = None

    return ClaimGroundingSummary(
        factual_claim_count=factual_count,
        supported_claim_count=len(supported),
        unsupported_claim_count=len(unsupported),
        no_evidence_claim_count=len(no_evidence),
        non_claim_count=len(verdicts) - factual_count,
        unsupported_claim_rate=round(unsupported_rate, 4),
        no_evidence_rate=round(no_evidence_rate, 4),
        citation_accuracy=round(citation_accuracy, 4),
        claim_grounding_verified=fail_class is None,
        fail_class=fail_class,
    )
