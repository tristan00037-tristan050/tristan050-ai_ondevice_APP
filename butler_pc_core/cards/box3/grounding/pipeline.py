
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .asset_manifest import build_default_manifest, manifest_digest
from ..draft_service import DEFAULT_MAX_NEW_TOKENS, draft_from_existing
from .adapters.helper3_format_adapter import apply_format
from .adapters.helper4_grounding_adapter import verify_grounding
from .adapters.helper7_extract_adapter import extract_evidence_units
from .adapters.helper8_style_adapter import apply_company_style

def digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class Box3ReferenceDoc:
    source_digest: str
    runtime_text: str | None = None
    unit_type: str = "text"

@dataclass(frozen=True)
class Box3PipelineInput:
    request_text: str
    reference_docs: list[Box3ReferenceDoc]
    prompt_template: str = "참고 문서 근거를 바탕으로 새 초안을 작성하세요.\n\n{input}"
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS
    company_profile_ref: str | None = None

@dataclass(frozen=True)
class Box3PipelineResult:
    schema_version: str
    status: str
    draft_text: str | None
    draft_digest: str | None
    citations: list[dict[str, Any]]
    grounding: dict[str, Any]
    format: dict[str, Any]
    style: dict[str, Any]
    evidence: dict[str, Any]
    asset_manifest_status: str
    receipt_hook: dict[str, Any]
    external_send_zero: bool = True
    raw_saved_zero: bool = True
    raw_doc_logged: bool = False
    fail_class: str | None = None
    contract_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def run_box3_pipeline(
    payload: Box3PipelineInput,
    *,
    runner: Callable[[str, dict[str, Any]], str] | None = None,
    force_draft_text: str | None = None,
) -> Box3PipelineResult:
    manifest = build_default_manifest()
    refs = [asdict(doc) for doc in payload.reference_docs]
    evidence = extract_evidence_units(refs)

    merged_runtime = _merge_runtime_only_text(payload)
    if force_draft_text is not None:
        draft_text = force_draft_text
        contract_only = False
    else:
        draft = draft_from_existing(
            merged_runtime,
            payload.prompt_template,
            max_new_tokens=payload.max_new_tokens,
            runner=runner,
        )
        draft_text = draft.draft_text
        contract_only = draft.contract_only

    units = evidence["evidence_units"]
    citations = _build_citations(units)
    grounding = verify_grounding(draft_text, units)
    formatted = apply_format(draft_text)
    style = apply_company_style(draft_text, payload.company_profile_ref)

    status, fail_class = _determine_status(manifest.status, grounding, formatted, style, contract_only)
    draft_digest = digest_text(draft_text) if draft_text is not None else None
    receipt_hook = {
        "schema_version": "box3.receipt_hook.v1",
        "request_digest": digest_text(payload.request_text),
        "draft_digest": draft_digest,
        "source_digests": sorted({doc.source_digest for doc in payload.reference_docs}),
        "asset_manifest_digest": manifest_digest(manifest),
        "external_send_zero": True,
        "plaintext_persisted": False,
    }
    return Box3PipelineResult(
        schema_version="box3.pipeline_result.v1",
        status=status,
        draft_text=draft_text if not contract_only else None,
        draft_digest=draft_digest,
        citations=citations,
        grounding=grounding,
        format=formatted,
        style=style,
        evidence={
            "schema_version": evidence["schema_version"],
            "status": evidence["status"],
            "evidence_unit_count": len(units),
            "source_digest_coverage": _source_digest_coverage(citations),
            "table_figure_unit_count": sum(1 for unit in units if unit.get("unit_type") in {"table", "figure"}),
            "plaintext_persisted": False,
        },
        asset_manifest_status=manifest.status,
        receipt_hook=receipt_hook,
        fail_class=fail_class,
        contract_only=contract_only,
    )

def _merge_runtime_only_text(payload: Box3PipelineInput) -> str:
    parts = [payload.request_text]
    parts.extend(doc.runtime_text for doc in payload.reference_docs if doc.runtime_text)
    return "\n\n".join(part for part in parts if part)

def _build_citations(evidence_units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_digest": unit["source_digest"],
            "evidence_unit_digest": unit["evidence_unit_digest"],
            "support_level": "digest_linked",
        }
        for unit in evidence_units
        if str(unit.get("source_digest", "")).startswith("sha256:")
    ]

def _source_digest_coverage(citations: list[dict[str, Any]]) -> float:
    if not citations:
        return 0.0
    valid = [c for c in citations if str(c.get("source_digest", "")).startswith("sha256:")]
    return len(valid) / len(citations)

def _determine_status(
    asset_status: str,
    grounding: dict[str, Any],
    formatted: dict[str, Any],
    style: dict[str, Any],
    contract_only: bool,
) -> tuple[str, str | None]:
    if contract_only:
        return "contract_only", asset_status
    if grounding["status"] == "blocked":
        return "blocked", grounding.get("fail_class") or "GROUNDING_BLOCKED"
    if grounding["status"] == "needs_review":
        return "needs_review", grounding.get("fail_class") or "GROUNDING_NEEDS_REVIEW"
    if formatted["status"] == "needs_review":
        return "needs_review", "FORMAT_NEEDS_REVIEW"
    if style["status"] == "needs_review":
        return "needs_review", "STYLE_NEEDS_REVIEW"
    if asset_status != "ASSET_INVENTORY_PASS":
        return "contract_only", asset_status
    return "real", None
