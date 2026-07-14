"""Canonical model-tier-B product adapter (P0-4).

Exposes the six benchmark entrypoints the harness requires. Each entrypoint reaches
a *real* Box3 / DLP product function (grounding extraction, claim extraction, claim
grounding, grounding summary, runtime DLP scan) and records the reach through the
passive observer hook. Returns are digest/count summaries only — no raw text, paths,
or user identifiers — and are byte-identical whether or not an observer is registered.

Model execution is intentionally *not* performed here: that is M3-only and owner-run.
RUNTIME_ACTIVATION_ALLOWED stays 0. This module exists so the harness can prove it
reaches the real product surface and that the observation hook works, without
changing any existing product routing or behavior.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Real Box3 product functions (deterministic, no model inference required).
from butler_pc_core.cards.box3.real_grounding import (
    extract_claims,
    extract_evidence_units,
    ground_claims,
    summarize_grounding,
)

# Real runtime DLP product function.
from butler_pc_core.dlp.runtime import scan_runtime

from butler_pc_core.model_tier_bench.observer import observe

# Deploy-time identity injection point. The harness verifies the *committed blob* of
# this file (and every entrypoint owner) against the approved commit tree, so this
# placeholder is replaced with the approved commit oid at deploy time; it is never
# trusted on its own.
__butler_product_commit_oid__ = "0" * 40

# Fixed, non-sensitive runtime-only reference/draft text used to exercise the real
# grounding path deterministically. No PII; the observer only ever sees digests.
_REFERENCE_DOC = "공급사는 2026년 3월 1일 계약 수량을 전량 납품했다.\n\n검수는 같은 날 완료됐다."
_DRAFT_TEXT = "공급사는 2026년 3월 1일 전량 납품했다."
_DLP_PROBE = "정산 요약 문서 검토 요청입니다."


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reach(entrypoint: str, product_callable: str, result_digest: str, count: int) -> dict[str, Any]:
    """Record a reach into a real product function and return its safe summary."""
    observe({
        "entrypoint": entrypoint,
        "product_callable": product_callable,
        "result_sha256": result_digest,
        "reached_count": count,
    })
    return {
        "entrypoint": entrypoint,
        "product_callable": product_callable,
        "result_sha256": result_digest,
        "reached_count": count,
        "runtime_activation_allowed": 0,
    }


def Box3ProductPipelineRuntime(*args: Any, **kwargs: Any) -> dict[str, Any]:
    units = extract_evidence_units([_REFERENCE_DOC])
    claims = extract_claims(_DRAFT_TEXT)
    verdicts = ground_claims(claims, units)
    summary = summarize_grounding(verdicts)
    digest = _digest(f"{len(units)}:{len(claims)}:{len(verdicts)}:{summary.supported_claim_count}")
    return _reach("Box3ProductPipelineRuntime", "butler_pc_core.cards.box3.real_grounding.ground_claims", digest, len(verdicts))


def run_product_matrix(*args: Any, **kwargs: Any) -> dict[str, Any]:
    units = extract_evidence_units([_REFERENCE_DOC])
    digest = _digest(":".join(unit.evidence_digest for unit in units))
    return _reach("run_product_matrix", "butler_pc_core.cards.box3.real_grounding.extract_evidence_units", digest, len(units))


def run_cold_worker_handshake(*args: Any, **kwargs: Any) -> dict[str, Any]:
    claims = extract_claims(_DRAFT_TEXT)
    digest = _digest(":".join(claim.claim_digest for claim in claims) if claims else "0")
    return _reach("run_cold_worker_handshake", "butler_pc_core.cards.box3.real_grounding.extract_claims", digest, len(claims))


def measure_dual_resident_pressure(*args: Any, **kwargs: Any) -> dict[str, Any]:
    units = extract_evidence_units([_REFERENCE_DOC])
    claims = extract_claims(_DRAFT_TEXT)
    verdicts = ground_claims(claims, units)
    digest = _digest(":".join(verdict.support_level for verdict in verdicts) if verdicts else "0")
    return _reach("measure_dual_resident_pressure", "butler_pc_core.cards.box3.real_grounding.ground_claims", digest, len(verdicts))


def verify_samples_first(*args: Any, **kwargs: Any) -> dict[str, Any]:
    units = extract_evidence_units([_REFERENCE_DOC])
    claims = extract_claims(_DRAFT_TEXT)
    summary = summarize_grounding(ground_claims(claims, units))
    digest = _digest(f"{summary.supported_claim_count}:{summary.unsupported_claim_count}:{summary.no_evidence_claim_count}")
    return _reach("verify_samples_first", "butler_pc_core.cards.box3.real_grounding.summarize_grounding", digest, summary.supported_claim_count)


def butler_bench_run_v2(*args: Any, **kwargs: Any) -> dict[str, Any]:
    scan = scan_runtime(_DLP_PROBE)
    digest = _digest(f"{scan.any_detected}:{len(scan.findings)}")
    return _reach("butler_bench_run_v2", "butler_pc_core.dlp.runtime.scan_runtime", digest, len(scan.findings))


ADAPTER_ENTRYPOINTS = (
    Box3ProductPipelineRuntime,
    run_product_matrix,
    run_cold_worker_handshake,
    measure_dual_resident_pressure,
    verify_samples_first,
    butler_bench_run_v2,
)
