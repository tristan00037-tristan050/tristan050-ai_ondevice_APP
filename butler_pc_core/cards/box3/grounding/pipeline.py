
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .asset_manifest import build_default_manifest, manifest_digest
from ..draft_service import DEFAULT_MAX_NEW_TOKENS, Box3ContractError, draft_from_existing
from ..security import is_sha256_digest
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
    # Codex P1 정정 (2026-06-01, PR #770): grounding 파이프라인의 runner 경로는 draft_from_existing
    # 에 raw(merged request_text + runtime_text) 를 전달하여 digest-only/canonical 가드를 우회,
    # 모델 runner 에 평문 기밀 텍스트를 누출했다. 본 파이프라인은 grounding 검증 전용
    # (force_draft_text)이며 real 생성은 pipeline.py 단일 진입 게이트만 담당하므로(근본 재검토 정합),
    # real_model_runner 주입을 fail-closed 로 차단한다 — raw 누출 원천 차단.
    if runner is not None:
        raise Box3ContractError("GROUNDING_REAL_RUNNER_NOT_SUPPORTED_DIGEST_ONLY")
    manifest = build_default_manifest()
    refs = [asdict(doc) for doc in payload.reference_docs]
    evidence = extract_evidence_units(refs)

    merged_runtime = _merge_runtime_only_text(payload)
    if force_draft_text is not None:
        # Codex v1.2.1 정정: force_draft_text는 grounding 검증용 입력으로만 사용.
        # runner가 실제 호출되지 않았으므로 asset manifest가 PASS여도 real claim 0
        # (claim boundary). demotion 시 draft_text=None 은 아래 return 의
        # `final_is_contract_only`(status != "real") gate 가 처리.
        draft_text = force_draft_text
        contract_only = True
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
        # Codex P1 정정 (2026-06-01, PR #770): caller 가 넣은 source_digest 를 sha256 검증 없이
        # receipt_hook 에 echo 하면 raw(email 등)가 새어 plaintext_persisted=False 와 모순.
        # digest 형식(sha256:<64hex>)으로 검증된 값만 포함하여 fail-closed.
        "source_digests": sorted(
            {doc.source_digest for doc in payload.reference_docs if is_sha256_digest(doc.source_digest)}
        ),
        "asset_manifest_digest": manifest_digest(manifest),
        "external_send_zero": True,
        "plaintext_persisted": False,
    }
    # Codex P2 정정 (2026-06-01, PR #770): contract_only 변수는 draft origin(force/runner)만
    # 반영하므로, _determine_status 가 manifest incomplete(asset_status != ASSET_INVENTORY_PASS)
    # 로 status 를 "contract_only" 로 demote 해도 contract_only=False 인 경우 draft_text 가 그대로
    # 노출되던 결함. final status 가 "real" 이 아니면 draft_text 를 suppress 하여 pending asset 의
    # digest/meta-only 정합을 회복한다(sibling pipeline.py 의 real_claim_allowed gate 와 정합).
    final_is_contract_only = status != "real"
    return Box3PipelineResult(
        schema_version="box3.pipeline_result.v1",
        status=status,
        draft_text=draft_text if not final_is_contract_only else None,
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
        # Codex P2 정정 (2026-06-01, PR #770): 결과의 contract_only 필드를 draft-origin 변수가 아닌
        # final status 기준(final_is_contract_only)으로 노출. asset-pending demotion 시 draft_text
        # suppress 와 일관되게 contract_only=True 로 보고하여, 이 필드로 게이트하는 caller 가
        # demotion 을 real-origin 으로 오인하지 않게 한다.
        contract_only=final_is_contract_only,
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
    # Codex v1.2.1: grounding/format/style fail-closed가 claim boundary(contract_only)
    # 보다 우선. fail-closed는 안전성 결정으로 contract_only 여부와 무관하게 적용되어야
    # status="needs_review"/"blocked"가 표면화되도록 한다. real claim 결정은 마지막 단계.
    if grounding["status"] == "blocked":
        return "blocked", grounding.get("fail_class") or "GROUNDING_BLOCKED"
    if grounding["status"] == "needs_review":
        return "needs_review", grounding.get("fail_class") or "GROUNDING_NEEDS_REVIEW"
    if formatted["status"] == "needs_review":
        return "needs_review", "FORMAT_NEEDS_REVIEW"
    if style["status"] == "needs_review":
        return "needs_review", "STYLE_NEEDS_REVIEW"
    # 여기까지 도달했다면 grounding/format/style은 모두 통과. real 자격은 contract_only가
    # false이고 asset_status가 PASS여야 성립(force_draft_text 경로는 contract_only=True로
    # 강제되어 real claim 0).
    if contract_only:
        return "contract_only", asset_status
    if asset_status != "ASSET_INVENTORY_PASS":
        return "contract_only", asset_status
    return "real", None
