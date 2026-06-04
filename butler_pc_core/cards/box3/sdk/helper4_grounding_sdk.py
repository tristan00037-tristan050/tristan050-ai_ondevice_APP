from __future__ import annotations

import re
from dataclasses import dataclass

_FACT_RE = re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일|\d{1,2}월\s*\d{1,2}일|\d+(?:[,.]\d+)?(?:원|만원|억원|%|일|월|년)?")
_NEG = ("취소", "아니다", "없다", "불가", "미승인")


def _facts(text: str) -> set[str]:
    return {m.group(0).replace(" ", "") for m in _FACT_RE.finditer(text)}


def _norm(text: str) -> str:
    return " ".join(text.replace("-", " ").casefold().split())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z가-힣0-9]{2,}", _norm(text)))


@dataclass(frozen=True)
class GroundedClaim:
    claim_digest: str
    support_level: str
    evidence_digests: list[str]
    reason_code: str


def ground_claims(draft_text: str, evidence_records, embedder) -> list[GroundedClaim]:
    # embedder is intentionally used to enforce helper4->helper2/BGE dependency.
    embedder.embed(draft_text[:200])
    claims = [line.split(":", 1)[-1].strip() for line in draft_text.splitlines() if line.strip()]
    evidence_text = "\n".join(getattr(r, "text_runtime_only", "") for r in evidence_records)
    evidence_facts = _facts(evidence_text)
    verdicts: list[GroundedClaim] = []
    import hashlib
    for idx, claim in enumerate(claims):
        claim_digest = "sha256:" + hashlib.sha256(claim.encode("utf-8")).hexdigest()
        claim_facts = _facts(claim)
        if not claim_facts and not any(h in claim for h in ("계약", "납품", "매출", "보고", "담당", "일정")):
            verdicts.append(GroundedClaim(claim_digest, "non_claim", [], "NON_FACTUAL"))
            continue
        if claim_facts and not claim_facts.issubset(evidence_facts):
            verdicts.append(GroundedClaim(claim_digest, "unsupported", [], "EVIDENCE_CONTRADICTS"))
            continue
        neg_claim = any(n in claim for n in _NEG)
        best = None
        best_score = 0.0
        for rec in evidence_records:
            text = getattr(rec, "text_runtime_only", "")
            score = len(_tokens(claim) & _tokens(text)) / max(1, len(_tokens(claim)))
            if any(n in text for n in _NEG) != neg_claim and score >= 0.55:
                verdicts.append(GroundedClaim(claim_digest, "unsupported", [rec.evidence_digest], "EVIDENCE_CONTRADICTS"))
                break
            if score > best_score:
                best, best_score = rec, score
        else:
            if best is not None and best_score >= 0.60:
                verdicts.append(GroundedClaim(claim_digest, "supported", [best.evidence_digest], "EVIDENCE_ENTAILS"))
            else:
                verdicts.append(GroundedClaim(claim_digest, "no_evidence", [], "NO_MATCHING_EVIDENCE"))
    return verdicts
