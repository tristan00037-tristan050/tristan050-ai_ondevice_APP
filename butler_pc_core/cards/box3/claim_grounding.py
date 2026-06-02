from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from .security import assert_runtime_text_safe, sha256_digest


ClaimSupportLevel = Literal["supported", "unsupported", "no_evidence", "non_claim"]

NON_FACTUAL_SECTIONS = {"제목", "근거", "확인 필요"}
FACTUAL_SECTIONS = {"배경", "핵심 내용", "합의사항", "금액/일정", "최종 문안"}
SECTION_RE = re.compile(r"^\s*(?P<section>[^:\n]{1,24})\s*:\s*(?P<body>.*)\s*$")
SHA256_DIGEST_RE = re.compile(r"sha256:[a-f0-9]{64}")


@dataclass(frozen=True)
class RuntimeClaim:
    claim_id: str
    claim_digest: str
    section: str
    text: str = field(repr=False)
    factual: bool

    def to_meta(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "claim_digest": self.claim_digest,
            "section": self.section,
            "factual": self.factual,
        }


@dataclass(frozen=True)
class ClaimVerdict:
    claim_id: str
    claim_digest: str
    support_level: ClaimSupportLevel
    evidence_digests: list[str]
    confidence: float
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimGroundingSummary:
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


def normalize_claim_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def extract_runtime_claims(draft_text: str) -> list[RuntimeClaim]:
    assert_runtime_text_safe(draft_text)
    claims: list[RuntimeClaim] = []
    for index, raw_line in enumerate(draft_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = SECTION_RE.match(line)
        section = match.group("section").strip() if match else "본문"
        body = match.group("body").strip() if match else line
        if not body or body.startswith("[") and body.endswith("]"):
            factual = False
        elif section in NON_FACTUAL_SECTIONS:
            factual = False
        elif section in FACTUAL_SECTIONS:
            factual = True
        else:
            factual = bool(re.search(r"[가-힣A-Za-z]", body))
        claim_digest = sha256_digest(f"{section}:{body}")
        claims.append(
            RuntimeClaim(
                claim_id=f"claim_{index:03d}",
                claim_digest=claim_digest,
                section=section,
                text=body,
                factual=factual,
            )
        )
    return claims


def ground_claims(
    *,
    draft_text: str,
    evidence_texts: list[str],
    evidence_digests: list[str],
) -> tuple[list[ClaimVerdict], ClaimGroundingSummary]:
    if len(evidence_texts) != len(evidence_digests):
        raise ValueError("EVIDENCE_TEXT_DIGEST_COUNT_MISMATCH")
    assert_runtime_text_safe(draft_text)
    for text in evidence_texts:
        assert_runtime_text_safe(text)

    claims = extract_runtime_claims(draft_text)
    normalized_evidence = [normalize_claim_text(text) for text in evidence_texts]
    cited_digest_set = set(SHA256_DIGEST_RE.findall(draft_text))
    verdicts: list[ClaimVerdict] = []
    cited_supported_count = 0

    for claim in claims:
        if not claim.factual:
            verdicts.append(
                ClaimVerdict(
                    claim_id=claim.claim_id,
                    claim_digest=claim.claim_digest,
                    support_level="non_claim",
                    evidence_digests=[],
                    confidence=1.0,
                    reason_code="SECTION_NON_FACTUAL",
                )
            )
            continue

        if not evidence_texts:
            verdicts.append(
                ClaimVerdict(
                    claim_id=claim.claim_id,
                    claim_digest=claim.claim_digest,
                    support_level="no_evidence",
                    evidence_digests=[],
                    confidence=0.0,
                    reason_code="NO_EVIDENCE_AVAILABLE",
                )
            )
            continue

        normalized_claim = normalize_claim_text(claim.text)
        matched = [
            evidence_digests[index]
            for index, evidence in enumerate(normalized_evidence)
            if normalized_claim and normalized_claim in evidence
        ]
        if matched:
            cited_matches = [digest for digest in matched if digest in cited_digest_set]
            if cited_matches:
                cited_supported_count += 1
            verdicts.append(
                ClaimVerdict(
                    claim_id=claim.claim_id,
                    claim_digest=claim.claim_digest,
                    support_level="supported",
                    evidence_digests=matched,
                    confidence=1.0 if cited_matches else 0.5,
                    reason_code=(
                        "CLAIM_TEXT_EXACTLY_GROUNDED_WITH_CITATION"
                        if cited_matches
                        else "CLAIM_TEXT_GROUNDED_BUT_CITATION_MISSING"
                    ),
                )
            )
        else:
            verdicts.append(
                ClaimVerdict(
                    claim_id=claim.claim_id,
                    claim_digest=claim.claim_digest,
                    support_level="unsupported",
                    evidence_digests=[],
                    confidence=0.0,
                    reason_code="CLAIM_NOT_FOUND_IN_EVIDENCE",
                )
            )

    factual = [item for item in verdicts if item.support_level != "non_claim"]
    supported = [item for item in factual if item.support_level == "supported"]
    unsupported = [item for item in factual if item.support_level == "unsupported"]
    no_evidence = [item for item in factual if item.support_level == "no_evidence"]
    factual_count = len(factual)
    unsupported_rate = len(unsupported) / max(factual_count, 1)
    no_evidence_rate = len(no_evidence) / max(factual_count, 1)
    citation_accuracy = cited_supported_count / max(factual_count, 1)

    if factual_count == 0:
        fail_class = "BLOCK_NO_FACTUAL_CLAIMS"
    elif unsupported:
        fail_class = "BLOCK_UNSUPPORTED_CLAIM"
    elif no_evidence:
        fail_class = "NEEDS_REVIEW_NO_EVIDENCE_CLAIM"
    else:
        fail_class = None

    summary = ClaimGroundingSummary(
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
    return verdicts, summary
