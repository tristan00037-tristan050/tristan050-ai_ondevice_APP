from __future__ import annotations

from butler_pc_core.cards.box3.actual_fail_class import FAIL_CLASS_SEVERITY

from .capability_registry import BOX3_1P7B_VARIANT_ID, MAIN_4B_VARIANT_ID
from .contracts import BoxPolicy


CASCADE_SOFT_REASON_CODES = frozenset(
    {
        "NEEDS_REVIEW_CONTENT_DRIFT",
        "NEEDS_REVIEW_OUTPUT_SKELETON_ECHO",
        "NEEDS_REVIEW_EVIDENCE_CARD_META_ECHO",
        "NEEDS_REVIEW_UNSUPPORTED_CLAIM",
        "NEEDS_REVIEW_UNSUPPORTED_CLAIM_LABEL_COVERAGE_PARTIAL",
        "NEEDS_REVIEW_NO_EVIDENCE_CLAIM",
        "NEEDS_REVIEW_NO_EVIDENCE",
        "NEEDS_REVIEW_NO_EVIDENCE_CLAIMS",
        "NEEDS_REVIEW_FORMAT_STYLE_GATE",
        "CITATION_ACCURACY_BELOW_GATE",
        "FORMAT_MATCH_BELOW_GATE",
        "STYLE_MATCH_BELOW_GATE",
        "TABLE_FIGURE_COVERAGE_BELOW_GATE",
        "PARTIAL_SUPPORTED_CLAIM_COUNT_LOW",
        "PARTIAL_SECTION_COMPLETENESS_LOW",
        "PARTIAL_ABSTAIN_OVERUSE",
        "BLOCK_NO_FACTUAL_CLAIMS",
        "BLOCK_DEGENERATION",
        "BLOCK_UNSUPPORTED_CLAIM",
        "BLOCK_FINAL_GATE_UNSUPPORTED",
    }
)

_EXPLICIT_HARD_REASONS = {
    reason for reason in FAIL_CLASS_SEVERITY if reason not in CASCADE_SOFT_REASON_CODES
}
_EXPLICIT_HARD_REASONS.update(
    {
        "BLOCK_SECRET_DETECTED",
        "BLOCK_INPUT_REFERENCE_LINEAGE_MISMATCH",
        "BLOCK_RUNTIME_OOM_PREDICTED",
        "BLOCK_CRITICAL_MEMORY_PRESSURE",
        "BLOCK_MODEL_IDENTITY_MISMATCH",
        "BLOCK_RUNTIME_SOURCE_MISMATCH",
        "BLOCK_UNKNOWN_FAIL_CLASS",
    }
)
CASCADE_HARD_REASON_CODES = frozenset(_EXPLICIT_HARD_REASONS)


def classify_cascade_reason(reason_code: str | None) -> str:
    if not reason_code:
        return "pass"
    if reason_code in CASCADE_SOFT_REASON_CODES:
        return "soft"
    return "hard"


def phase0_box1_policy() -> BoxPolicy:
    policy = BoxPolicy(
        schema_version="butler.box_policy.v1",
        box_id="1",
        enabled=True,
        shadow_only=True,
        default_variant_id=None,
        allowed_variant_ids=(MAIN_4B_VARIANT_ID,),
        hard_block_reason_codes=CASCADE_HARD_REASON_CODES,
        cascade_soft_reason_codes=frozenset(),
        minimum_available_memory_bytes={MAIN_4B_VARIANT_ID: 8 * 1024**3},
        max_escalations=1,
    )
    policy.validate()
    return policy


def phase0_box3_policy() -> BoxPolicy:
    policy = BoxPolicy(
        schema_version="butler.box_policy.v1",
        box_id="3",
        enabled=True,
        shadow_only=True,
        default_variant_id=BOX3_1P7B_VARIANT_ID,
        allowed_variant_ids=(BOX3_1P7B_VARIANT_ID, MAIN_4B_VARIANT_ID),
        hard_block_reason_codes=CASCADE_HARD_REASON_CODES,
        cascade_soft_reason_codes=CASCADE_SOFT_REASON_CODES,
        minimum_available_memory_bytes={MAIN_4B_VARIANT_ID: 8 * 1024**3},
        max_escalations=1,
    )
    policy.validate()
    return policy


def phase0_policies() -> dict[str, BoxPolicy]:
    return {"1": phase0_box1_policy(), "3": phase0_box3_policy()}
