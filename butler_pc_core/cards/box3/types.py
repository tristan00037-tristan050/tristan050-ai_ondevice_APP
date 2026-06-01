from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


Box3Status = Literal[
    "contract_only",
    "real",
    "needs_review",
    "blocked",
]


class Box3Citation(TypedDict):
    source_digest: str
    evidence_unit_digest: str
    support_level: Literal["supported", "partial", "unsupported"]


class Box3Grounding(TypedDict):
    reference_coverage: float
    grounding_pass_rate: float
    unsupported_claim_rate: float
    contradiction_count: int
    source_digest_coverage: float


class Box3Format(TypedDict):
    format_match_score: float
    required_sections_present: bool
    required_sections: list[str]


class Box3Style(TypedDict):
    style_match_score: float
    forbidden_style_zero: bool


class Box3PipelineResult(TypedDict):
    status: Box3Status
    draft_text: str | None
    draft_digest: str | None
    citations: list[Box3Citation]
    grounding: Box3Grounding
    format: Box3Format
    style: Box3Style
    external_send_zero: bool
    raw_saved_zero: bool
    raw_doc_logged: bool
    fail_class: str | None
    contract_only: bool
    real_claim_allowed: bool


@dataclass(frozen=True)
class EvidenceUnit:
    unit_digest: str
    unit_type: str
    confidence: float
    source_digest: str
    has_table_or_figure: bool = False


@dataclass(frozen=True)
class Box3Request:
    reference_docs: list[str]
    draft_request: str
    format_hint: str = "freeform"
    max_new_tokens: int = 512


JSONDict = dict[str, Any]

