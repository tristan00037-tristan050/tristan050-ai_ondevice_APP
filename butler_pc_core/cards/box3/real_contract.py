from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .security import assert_no_raw_persistence, assert_runtime_text_safe, is_sha256_digest, sha256_digest


RealStatus = Literal["contract_only", "real", "needs_review", "blocked"]


@dataclass(frozen=True)
class Box3RealRuntimeEnvelope:
    """Memory-only raw input for the real Box 3 runner.

    Raw text is intentionally repr-disabled and has no persist method. Persisted
    records must use Box3RealAuditRecord or Box3RealVerdict.to_persistable_dict().
    """

    request_text: str = field(repr=False)
    reference_texts: tuple[str, ...] = field(repr=False)
    company_format_text: str = field(repr=False)
    request_digest: str
    reference_digests: tuple[str, ...]
    company_format_digest: str
    external_send_zero: bool = True
    raw_saved_zero: bool = True

    @classmethod
    def from_raw(
        cls,
        *,
        request_text: str,
        reference_texts: list[str] | tuple[str, ...],
        company_format_text: str,
    ) -> "Box3RealRuntimeEnvelope":
        assert_runtime_text_safe(request_text)
        assert_runtime_text_safe(company_format_text)
        for item in reference_texts:
            assert_runtime_text_safe(item)
        return cls(
            request_text=request_text,
            reference_texts=tuple(reference_texts),
            company_format_text=company_format_text,
            request_digest=sha256_digest(request_text),
            reference_digests=tuple(sha256_digest(item) for item in reference_texts),
            company_format_digest=sha256_digest(company_format_text),
        )

    def __post_init__(self) -> None:
        if len(self.reference_texts) != len(self.reference_digests):
            raise ValueError("REFERENCE_DIGEST_COUNT_MISMATCH")
        if not is_sha256_digest(self.request_digest):
            raise ValueError("REQUEST_DIGEST_INVALID")
        if not is_sha256_digest(self.company_format_digest):
            raise ValueError("COMPANY_FORMAT_DIGEST_INVALID")
        if not all(is_sha256_digest(item) for item in self.reference_digests):
            raise ValueError("REFERENCE_DIGEST_INVALID")
        if self.request_digest != sha256_digest(self.request_text):
            raise ValueError("REQUEST_DIGEST_MISMATCH")
        if self.company_format_digest != sha256_digest(self.company_format_text):
            raise ValueError("COMPANY_FORMAT_DIGEST_MISMATCH")
        for text, digest in zip(self.reference_texts, self.reference_digests):
            if digest != sha256_digest(text):
                raise ValueError("REFERENCE_DIGEST_MISMATCH")
        assert_runtime_text_safe(self.request_text)
        assert_runtime_text_safe(self.company_format_text)
        for item in self.reference_texts:
            assert_runtime_text_safe(item)

    def to_audit_seed(self) -> dict[str, Any]:
        payload = {
            "request_digest": self.request_digest,
            "reference_digests": list(self.reference_digests),
            "company_format_digest": self.company_format_digest,
            "external_send_zero": self.external_send_zero,
            "raw_saved_zero": self.raw_saved_zero,
        }
        assert_no_raw_persistence(payload)
        return payload


@dataclass(frozen=True)
class Box3RealVerdict:
    schema_version: str
    status: RealStatus
    draft_text: str | None = field(repr=False)
    draft_digest: str | None
    claim_verdicts: list[dict[str, Any]]
    metrics: dict[str, Any]
    fail_class: str | None
    contract_only: bool
    real_claim_allowed: bool
    external_send_zero: bool
    raw_saved_zero: bool

    def to_response_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_persistable_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "status": self.status,
            "draft_digest": self.draft_digest,
            "claim_verdicts": self.claim_verdicts,
            "metrics": self.metrics,
            "fail_class": self.fail_class,
            "contract_only": self.contract_only,
            "real_claim_allowed": self.real_claim_allowed,
            "external_send_zero": self.external_send_zero,
            "raw_saved_zero": self.raw_saved_zero,
        }
        assert_no_raw_persistence(payload)
        return payload


@dataclass(frozen=True)
class Box3RealAuditRecord:
    schema_version: str
    status: RealStatus
    request_digest: str
    reference_digests: list[str]
    company_format_digest: str
    draft_digest: str | None
    stage_trace: list[dict[str, Any]]
    fail_class: str | None
    external_send_zero: bool
    raw_saved_zero: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_no_raw_persistence(payload)
        return payload


@dataclass(frozen=True)
class Box3RealPipelineOutput:
    verdict: Box3RealVerdict
    audit: Box3RealAuditRecord

    def to_persistable_dict(self) -> dict[str, Any]:
        payload = {
            "verdict": self.verdict.to_persistable_dict(),
            "audit": self.audit.to_dict(),
        }
        assert_no_raw_persistence(payload)
        return payload
