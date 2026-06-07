from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .v7_activation_gate import V7SmokeMetrics, evaluate_v7_final_gate
from .v7_asset_manifest import verify_v7_q4_asset
from .v7_preconditions import verify_pr785_precondition
from .v7_security import assert_digest_only, sha256_text, stable_json_digest

@dataclass(frozen=True)
class V7SmokeEvidence:
    schema_version: str
    request_digest: str
    draft_digest: str | None
    output_digest: str | None
    status: str
    fail_class: str | None
    unsupported_count: int
    degeneration_detected: bool
    citation_accuracy: float
    section_completeness: float
    raw_saved_zero: bool
    external_send_zero: bool
    production_claim_allowed: bool
    memory_backend: str | None
    peak_memory_mb: float | None
    latency_ms: float | None
    v7_asset_digest: str
    pr785_precondition_digest: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_digest_only(payload)
        return payload


def build_v7_smoke_evidence(*, drafting_request: str, reference_docs: list[str], draft_text: str, metrics: V7SmokeMetrics, human_approval_allowed: bool = False) -> V7SmokeEvidence:
    request_digest = stable_json_digest({
        "drafting_request_digest": sha256_text(drafting_request),
        "reference_digests": [sha256_text(x) for x in reference_docs],
    })
    pre = verify_pr785_precondition()
    asset = verify_v7_q4_asset()
    decision = evaluate_v7_final_gate(draft_text=draft_text, metrics=metrics, request_digest=request_digest, precondition=pre, asset_verdict=asset, human_approval_allowed=human_approval_allowed)
    degen = next((c for c in decision.conditions if c["name"] == "degeneration_false"), {})
    section = next((c for c in decision.conditions if c["name"] == "section_completeness"), {})
    return V7SmokeEvidence(
        schema_version="box3.v7_smoke_evidence.v1_2",
        request_digest=request_digest,
        draft_digest=sha256_text(draft_text) if draft_text else None,
        output_digest=sha256_text(draft_text) if draft_text else None,
        status=decision.status,
        fail_class=decision.fail_class,
        unsupported_count=metrics.unsupported_count,
        degeneration_detected=not bool(degen.get("passed", False)),
        citation_accuracy=metrics.citation_accuracy,
        section_completeness=float(section.get("section_completeness", 0.0)),
        raw_saved_zero=metrics.raw_saved_zero,
        external_send_zero=metrics.external_send_zero,
        production_claim_allowed=metrics.production_claim_allowed,
        memory_backend=metrics.memory_backend,
        peak_memory_mb=metrics.peak_memory_mb,
        latency_ms=metrics.latency_ms,
        v7_asset_digest=stable_json_digest(asset.to_dict()),
        pr785_precondition_digest=pre.source_digest,
    )
