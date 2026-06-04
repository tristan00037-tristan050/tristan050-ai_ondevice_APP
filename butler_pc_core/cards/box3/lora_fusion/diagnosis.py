from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .constants import (
    SCHEMA_VERSION_DIAGNOSIS,
    SDK_HELPERS_FORBIDDEN_IN_STACK,
    PASS_DIAGNOSIS_ONLY,
    PARTIAL,
    BLOCK,
    FAIL_BLOCK_DOUBLE_FUSION,
    FAIL_BLOCK_DIAGNOSIS_REQUIRED,
    FAIL_BLOCK_RAW_EVIDENCE_LEAK,
    FAIL_BLOCK_SDK_HELPER_STACK_ATTEMPT,
    FAIL_PARTIAL_DIAGNOSIS_INSUFFICIENT,
)
from .security import assert_no_raw_or_path_material, is_sha256_digest, stable_json_digest

AxisVerdict = Literal["already_fused", "not_fused", "inconclusive"]


@dataclass(frozen=True)
class FusionEvidenceAxis:
    """Digest-only diagnosis evidence for one of the four required axes.

    Raw prompt/output/model metadata text must never be stored here. Use
    evidence_digest and optional ref-like source labels only.
    """

    axis: Literal["lineage_build", "gguf_metadata", "runner_code", "behavior_probe"]
    verdict: AxisVerdict
    evidence_digest: str
    confidence: float
    evidence_ref: str | None = None
    raw_saved_zero: bool = True
    external_send_zero: bool = True

    def __post_init__(self) -> None:
        if not is_sha256_digest(self.evidence_digest):
            raise ValueError("EVIDENCE_DIGEST_INVALID")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("EVIDENCE_CONFIDENCE_INVALID")
        if not self.raw_saved_zero or not self.external_send_zero:
            raise ValueError(FAIL_BLOCK_RAW_EVIDENCE_LEAK)
        assert_no_raw_or_path_material(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FusionDiagnosisVerdict:
    schema_version: str
    diagnosis_status: Literal[
        "ALREADY_FUSED_CONFIRMED",
        "NOT_FUSED_CONFIRMED",
        "INCONCLUSIVE",
        "BLOCKED",
    ]
    status: str
    fail_class: str | None
    axis_counts: dict[str, int]
    agreed_axes: list[str]
    contradictory_axes: list[str]
    action: Literal[
        "DO_NOT_FUSE_REPORT_MODEL_LIMIT",
        "FUSION_ALLOWED_RUNTIME_LORA_OR_MERGE_GGUF",
        "FUSION_FORBIDDEN_REMEASURE",
        "BLOCKED",
    ]
    fusion_allowed: bool
    raw_saved_zero: bool = True
    external_send_zero: bool = True
    diagnosis_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["diagnosis_digest"] is None:
            core = {k: v for k, v in payload.items() if k != "diagnosis_digest"}
            payload["diagnosis_digest"] = stable_json_digest(core)
        assert_no_raw_or_path_material(payload)
        return payload


def diagnose_helper35_fusion(
    axes: list[FusionEvidenceAxis],
    *,
    attempted_stack_helpers: list[str] | None = None,
    previous_fusion_manifest_digest: str | None = None,
) -> FusionDiagnosisVerdict:
    """Phase A/B diagnosis gate.

    A/B can be confirmed only when at least three evidence axes agree and no
    high-confidence core evidence contradicts that conclusion. Otherwise the
    result is INCONCLUSIVE and fusion is forbidden.
    """

    attempted_stack_helpers = attempted_stack_helpers or []
    forbidden = sorted(set(attempted_stack_helpers) & SDK_HELPERS_FORBIDDEN_IN_STACK)
    if forbidden:
        return _blocked(FAIL_BLOCK_SDK_HELPER_STACK_ATTEMPT, {"sdk_helpers": forbidden})
    if previous_fusion_manifest_digest is not None and not isinstance(previous_fusion_manifest_digest, str):
        return _blocked(FAIL_BLOCK_DOUBLE_FUSION, {"previous_fusion_manifest_digest_invalid": True})
    if previous_fusion_manifest_digest:
        return _blocked(FAIL_BLOCK_DOUBLE_FUSION, {"previous_fusion_manifest_digest": previous_fusion_manifest_digest})

    if not axes:
        return FusionDiagnosisVerdict(
            SCHEMA_VERSION_DIAGNOSIS, "INCONCLUSIVE", PARTIAL,
            FAIL_PARTIAL_DIAGNOSIS_INSUFFICIENT, {"already_fused": 0, "not_fused": 0, "inconclusive": 0},
            [], [], "FUSION_FORBIDDEN_REMEASURE", False,
        )

    seen = set()
    for item in axes:
        if item.axis in seen:
            return _blocked("BLOCK_DIAGNOSIS_DUPLICATE_AXIS", {"axis": item.axis})
        seen.add(item.axis)
        # Constructor already validates; re-check material after caller collection.
        assert_no_raw_or_path_material(item.to_dict())

    counts = {
        "already_fused": sum(1 for item in axes if item.verdict == "already_fused"),
        "not_fused": sum(1 for item in axes if item.verdict == "not_fused"),
        "inconclusive": sum(1 for item in axes if item.verdict == "inconclusive"),
    }

    # High-confidence contradictions in runner_code or behavior_probe are core conflicts.
    has_conflict = counts["already_fused"] > 0 and counts["not_fused"] > 0
    core_conflict = any(
        item.axis in {"runner_code", "behavior_probe"} and item.confidence >= 0.85
        for item in axes
        if item.verdict in {"already_fused", "not_fused"}
    ) and has_conflict

    if counts["already_fused"] >= 3 and not core_conflict and counts["not_fused"] == 0:
        return _confirmed("ALREADY_FUSED_CONFIRMED", axes, counts)
    if counts["not_fused"] >= 3 and not core_conflict and counts["already_fused"] == 0:
        return _confirmed("NOT_FUSED_CONFIRMED", axes, counts)

    fail_class = FAIL_PARTIAL_DIAGNOSIS_INSUFFICIENT
    if has_conflict:
        fail_class = "PARTIAL_DIAGNOSIS_CONFLICTING_EVIDENCE"
    return FusionDiagnosisVerdict(
        SCHEMA_VERSION_DIAGNOSIS, "INCONCLUSIVE", PASS_DIAGNOSIS_ONLY if has_conflict else PARTIAL,
        fail_class, counts,
        [item.axis for item in axes if item.verdict != "inconclusive"],
        [item.axis for item in axes if has_conflict and item.verdict != "inconclusive"],
        "FUSION_FORBIDDEN_REMEASURE",
        False,
    )


def _confirmed(status: str, axes: list[FusionEvidenceAxis], counts: dict[str, int]) -> FusionDiagnosisVerdict:
    if status == "ALREADY_FUSED_CONFIRMED":
        action = "DO_NOT_FUSE_REPORT_MODEL_LIMIT"
        fusion_allowed = False
    else:
        action = "FUSION_ALLOWED_RUNTIME_LORA_OR_MERGE_GGUF"
        fusion_allowed = True
    return FusionDiagnosisVerdict(
        SCHEMA_VERSION_DIAGNOSIS, status, PASS_DIAGNOSIS_ONLY,
        None, counts,
        [item.axis for item in axes if item.verdict != "inconclusive"],
        [],
        action, fusion_allowed,
    )


def _blocked(fail_class: str, detail: dict[str, Any]) -> FusionDiagnosisVerdict:
    digest = stable_json_digest({"fail_class": fail_class, "detail": detail})
    return FusionDiagnosisVerdict(
        SCHEMA_VERSION_DIAGNOSIS, "BLOCKED", BLOCK, fail_class,
        {"already_fused": 0, "not_fused": 0, "inconclusive": 0},
        [], list(detail.keys()), "BLOCKED", False, diagnosis_digest=digest,
    )
