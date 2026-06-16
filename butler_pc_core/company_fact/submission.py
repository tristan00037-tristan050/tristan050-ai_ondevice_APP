from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from butler_pc_core.company_policy.contracts import (
    ContractValidationError,
    require_digest,
    stable_json_digest,
)

from .routes import CompanyFactCandidateRequest
from .storage import CompanyFactStore


SCHEMA_VERSION = "company_fact.submission_outcome.v1"
PROVENANCE_ORIGIN = "AUTO_EXTRACTION_CONFIRMED"


@dataclass(frozen=True)
class SubmissionOutcome:
    schema_version: Literal["company_fact.submission_outcome.v1"]
    status: Literal["submitted", "not_confirmed", "invalid_draft", "blocked"]
    reason_code: str
    fact_id: str | None = None
    fact_status: Literal["CANDIDATE"] | None = None
    fact_digest: str | None = None
    audit_ref: str | None = None
    submission_provenance_digest: str | None = None
    submission_provenance: dict[str, str | None] | None = None
    extraction_draft_digest: str | None = None
    confirmed_draft_digest: str | None = None
    confirmed_by_digest: str | None = None
    raw_text_logged: Literal[False] = False
    external_send_zero: Literal[True] = True
    auto_approve_zero: Literal[True] = True
    approve_called_zero: Literal[True] = True
    resolver_exposure_zero: Literal[True] = True

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason_code": self.reason_code,
            "fact_id": self.fact_id,
            "fact_status": self.fact_status,
            "fact_digest": self.fact_digest,
            "audit_ref": self.audit_ref,
            "submission_provenance_digest": self.submission_provenance_digest,
            "submission_provenance": dict(self.submission_provenance or {}),
            "extraction_draft_digest": self.extraction_draft_digest,
            "confirmed_draft_digest": self.confirmed_draft_digest,
            "confirmed_by_digest": self.confirmed_by_digest,
            "raw_text_logged": False,
            "external_send_zero": True,
            "auto_approve_zero": True,
            "approve_called_zero": True,
            "resolver_exposure_zero": True,
        }


def _invalid(
    reason_code: str,
    *,
    extraction_draft_digest: str | None,
    confirmed_draft_digest: str | None,
    confirmed_by_digest: str | None,
) -> SubmissionOutcome:
    return SubmissionOutcome(
        schema_version=SCHEMA_VERSION,
        status="invalid_draft",
        reason_code=reason_code,
        extraction_draft_digest=extraction_draft_digest,
        confirmed_draft_digest=confirmed_draft_digest,
        confirmed_by_digest=confirmed_by_digest,
    )


def _validate_optional_digest(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    try:
        return require_digest(value, field_name)
    except ContractValidationError as exc:
        raise ValueError(str(exc)) from exc


def _make_provenance(
    *,
    extraction_draft_digest: str | None,
    confirmed_draft_digest: str,
    fact_digest: str,
    confirmed_by_digest: str | None,
) -> tuple[dict[str, str | None], str]:
    receipt = {
        "origin": PROVENANCE_ORIGIN,
        "extraction_draft_digest": extraction_draft_digest,
        "confirmed_draft_digest": confirmed_draft_digest,
        "fact_digest": fact_digest,
        "confirmed_by_digest": confirmed_by_digest,
    }
    return receipt, stable_json_digest(receipt)


def submit_confirmed_candidate(
    confirmed_draft: dict[str, Any],
    *,
    confirmed: bool,
    extraction_draft_digest: str | None = None,
    confirmed_draft_digest: str | None = None,
    confirmed_by_digest: str | None = None,
    store: CompanyFactStore | None = None,
) -> SubmissionOutcome:
    computed_confirmed_digest = stable_json_digest(confirmed_draft)
    try:
        extraction_digest = _validate_optional_digest(extraction_draft_digest, "extraction_draft")
        supplied_confirmed_digest = _validate_optional_digest(confirmed_draft_digest, "confirmed_draft")
        confirmer_digest = _validate_optional_digest(confirmed_by_digest, "confirmed_by")
    except ValueError as exc:
        return _invalid(
            "DIGEST_INVALID",
            extraction_draft_digest=extraction_draft_digest,
            confirmed_draft_digest=confirmed_draft_digest,
            confirmed_by_digest=confirmed_by_digest,
        )

    final_confirmed_digest = supplied_confirmed_digest or computed_confirmed_digest
    if supplied_confirmed_digest is not None and supplied_confirmed_digest != computed_confirmed_digest:
        return _invalid(
            "CONFIRMED_DRAFT_DIGEST_MISMATCH",
            extraction_draft_digest=extraction_digest,
            confirmed_draft_digest=supplied_confirmed_digest,
            confirmed_by_digest=confirmer_digest,
        )

    if not confirmed:
        return SubmissionOutcome(
            schema_version=SCHEMA_VERSION,
            status="not_confirmed",
            reason_code="CONFIRMATION_REQUIRED",
            extraction_draft_digest=extraction_digest,
            confirmed_draft_digest=final_confirmed_digest,
            confirmed_by_digest=confirmer_digest,
        )

    try:
        validated = CompanyFactCandidateRequest(**confirmed_draft)
    except ValidationError:
        return _invalid(
            "CANDIDATE_SCHEMA_INVALID",
            extraction_draft_digest=extraction_digest,
            confirmed_draft_digest=final_confirmed_digest,
            confirmed_by_digest=confirmer_digest,
        )

    try:
        target_store = store or CompanyFactStore()
        entry, audit = target_store.save_candidate(**validated.model_dump())
    except Exception:
        return SubmissionOutcome(
            schema_version=SCHEMA_VERSION,
            status="blocked",
            reason_code="CANDIDATE_SAVE_FAILED",
            extraction_draft_digest=extraction_digest,
            confirmed_draft_digest=final_confirmed_digest,
            confirmed_by_digest=confirmer_digest,
        )

    provenance, provenance_digest = _make_provenance(
        extraction_draft_digest=extraction_digest,
        confirmed_draft_digest=final_confirmed_digest,
        fact_digest=entry.fact_digest,
        confirmed_by_digest=confirmer_digest,
    )
    return SubmissionOutcome(
        schema_version=SCHEMA_VERSION,
        status="submitted",
        reason_code="CANDIDATE_SUBMITTED",
        fact_id=entry.fact_id,
        fact_status="CANDIDATE",
        fact_digest=entry.fact_digest,
        audit_ref=str(audit.get("audit_id") or ""),
        submission_provenance_digest=provenance_digest,
        submission_provenance=provenance,
        extraction_draft_digest=extraction_digest,
        confirmed_draft_digest=final_confirmed_digest,
        confirmed_by_digest=confirmer_digest,
    )
