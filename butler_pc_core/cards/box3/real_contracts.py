"""Box3 real 융합 — 단일 계약(SSOT) 3객체.

3채널(maindev·alg·codex) 결과물을 봉합 없이 하나의 계약으로 융합한다.
- 베이스: maindev real_contracts(EvidenceUnit·DraftClaim·ClaimVerdict·Metrics·
  build_audit_record·assert_audit_record_is_digest_only).
- 흡수: codex 경계메서드(RuntimeEnvelope.from_raw + __post_init__ 검증,
  Verdict.to_response_dict / to_persistable_dict, ClaimSupportLevel Literal,
  Audit.stage_trace, contract_only / real_claim_allowed 출력 필드).
- 재사용: 보안 단일 모듈 ``security``(#770 골격) — sha256/DLP를 한 곳에서만 정의.

이 객체들은 sidecar 메모리 전용 raw 를 제외하면 모두 digest-only 로만 영속한다.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .security import (
    Box3SecurityError,
    assert_no_raw_persistence,
    assert_runtime_text_safe,
    is_sha256_digest,
    scan_forbidden_text,
    sha256_digest,
    stable_json_digest,
)

Digest = str
PipelineStatus = Literal["blocked", "needs_review", "real_candidate", "real", "contract_only"]
SupportLevel = Literal["supported", "unsupported", "no_evidence", "non_claim"]
# codex 경계 타입 흡수 — 동일 Literal 의 별칭(봉합 아님: 단일 정의 1벌).
ClaimSupportLevel = SupportLevel
EvidenceKind = Literal["text", "table", "figure"]


def sha256_text(text: str) -> Digest:
    """단일 보안 모듈의 sha256 다이제스트(``sha256:<hex>``)를 재사용한다."""
    return sha256_digest(text)


def sha256_bytes(data: bytes) -> Digest:
    return sha256_digest(data)


def new_request_id() -> str:
    return str(uuid.uuid4())


def scan_runtime_security_risk(text: str) -> str | None:
    """런타임 텍스트의 path/secret/PII 위험을 reason code 로만 반환(원문 미반환)."""
    findings = scan_forbidden_text(text)
    return findings[0] if findings else None


@dataclass
class EvidenceUnit:
    evidence_id: str
    source_digest: Digest
    evidence_digest: Digest
    kind: EvidenceKind
    text_runtime_only: str = field(repr=False)

    def citation(self) -> dict[str, str]:
        return {
            "source_digest": self.source_digest,
            "evidence_digest": self.evidence_digest,
            "span_label": "runtime_only",
        }


@dataclass
class DraftClaim:
    claim_id: str
    claim_digest: Digest
    is_factual: bool
    claim_type: str
    claim_text_runtime_only: str = field(repr=False)


@dataclass(frozen=True)
class ClaimVerdict:
    """지시서 3장 단일 계약 정본. support_level / reason_code 는 고정 enum."""

    claim_id: str
    claim_digest: Digest
    support_level: SupportLevel
    evidence_digests: list[Digest]
    confidence: float
    reason_code: Literal[
        "EVIDENCE_ENTAILS",
        "EVIDENCE_CONTRADICTS",
        "NO_MATCHING_EVIDENCE",
        "NON_FACTUAL",
    ]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Box3RealRuntimeEnvelope:
    """7단계 real 파이프라인이 공유하는 휘발성(sidecar memory only) 객체.

    저장·로그·``asdict(envelope)`` 를 evidence 에 포함 금지. 설계상 reference/draft
    raw text 를 담으며 sidecar 프로세스 메모리에서만 존재한다.
    """

    request_id: str
    reference_text_runtime_only: list[str] = field(default_factory=list, repr=False)
    drafting_request_runtime: str = field(default="", repr=False)
    format_hint: str = "자유형"
    max_new_tokens: int = 512
    evidence_units_runtime: list[EvidenceUnit] = field(default_factory=list, repr=False)
    draft_text_runtime: str | None = field(default=None, repr=False)
    draft_claims_runtime: list[DraftClaim] = field(default_factory=list, repr=False)
    model_chain: list[str] = field(default_factory=lambda: [
        "butler-1.7b-v3",
        "butler_v3_lora",
        "helper3_format",
        "helper4_grounding",
        "helper7_table_figure",
        "helper8_company_style",
    ])

    def __post_init__(self) -> None:
        # codex 경계메서드 흡수 — 구성 시점 구조 불변식 검증(__post_init__ 검증).
        # 런타임 DLP 는 from_raw(엄격) 와 pipeline(완곡 fail-closed)에서 수행한다.
        if not isinstance(self.max_new_tokens, int) or self.max_new_tokens < 1:
            raise ValueError("MAX_NEW_TOKENS_INVALID")
        if not isinstance(self.reference_text_runtime_only, list):
            raise ValueError("REFERENCE_TEXTS_INVALID")

    @classmethod
    def from_raw(
        cls,
        *,
        drafting_request: str,
        reference_texts: list[str] | tuple[str, ...],
        format_hint: str = "자유형",
        max_new_tokens: int = 512,
        request_id: str | None = None,
    ) -> "Box3RealRuntimeEnvelope":
        """raw 입력에서 envelope 를 구성한다. 각 텍스트는 DLP fail-closed 검증을 거친다."""
        assert_runtime_text_safe(drafting_request)
        assert_runtime_text_safe(format_hint)
        for item in reference_texts:
            assert_runtime_text_safe(item)
        return cls(
            request_id=request_id or new_request_id(),
            reference_text_runtime_only=list(reference_texts),
            drafting_request_runtime=drafting_request,
            format_hint=format_hint,
            max_new_tokens=max_new_tokens,
        )

    @property
    def reference_digests(self) -> list[Digest]:
        return [sha256_text(text) for text in self.reference_text_runtime_only]

    @property
    def request_digest(self) -> Digest:
        return stable_json_digest({
            "request_id": self.request_id,
            "drafting_request_digest": sha256_text(self.drafting_request_runtime),
            "reference_digests": self.reference_digests,
            "format_hint_digest": sha256_text(self.format_hint),
            "max_new_tokens": self.max_new_tokens,
        })

    def assert_runtime_safe(self) -> None:
        for text in [
            *self.reference_text_runtime_only,
            self.drafting_request_runtime,
            self.draft_text_runtime or "",
        ]:
            reason = scan_runtime_security_risk(text)
            if reason:
                raise Box3SecurityError(reason)

    def to_audit_seed(self) -> dict[str, Any]:
        payload = {
            "request_digest": self.request_digest,
            "reference_digests": self.reference_digests,
            "external_send_zero": True,
            "raw_saved_zero": True,
        }
        assert_no_raw_persistence(payload)
        return payload


@dataclass(frozen=True)
class Box3RealMetrics:
    unsupported_claim_rate: float
    no_evidence_claim_rate: float
    citation_accuracy: float
    format_compliance: float
    style_compliance: float
    table_figure_coverage: float
    factual_claim_count: int
    unsupported_count: int
    no_evidence_count: int
    supported_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Box3RealVerdict:
    schema_version: str
    request_id: str
    status: PipelineStatus
    draft_text: str | None
    draft_digest: Digest | None
    citations: list[dict[str, str]]
    claim_verdicts: list[dict[str, Any]]
    metrics: dict[str, Any]
    needs_review: bool
    fail_class: str | None
    model_chain: list[str]
    asset_manifest_digest: Digest
    real_runner_executed: bool
    contract_only: bool
    real_claim_allowed: bool
    external_send_zero: Literal[True] = True
    raw_saved_zero: Literal[True] = True
    raw_text_logged: Literal[False] = False

    def to_dict(self) -> dict[str, Any]:
        # 무회귀용 별칭 — 전체(응답) 표현.
        return self.to_response_dict()

    def to_response_dict(self) -> dict[str, Any]:
        """sidecar 응답용 — draft_text(런타임) 포함. 영속 금지."""
        return asdict(self)

    def to_persistable_dict(self) -> dict[str, Any]:
        """영속용 — draft_text 제외, digest-only. raw 누출 fail-closed 검증."""
        payload = {
            "schema_version": self.schema_version,
            # 영속 시 raw uuid 대신 digest 만 둔다(단일 보안 모듈 DLP 와 충돌 회피, digest-only).
            "request_digest": sha256_text(self.request_id),
            "status": self.status,
            "draft_digest": self.draft_digest,
            "citations": self.citations,
            "claim_verdicts": self.claim_verdicts,
            "metrics": self.metrics,
            "needs_review": self.needs_review,
            "fail_class": self.fail_class,
            "model_chain": self.model_chain,
            "asset_manifest_digest": self.asset_manifest_digest,
            "real_runner_executed": self.real_runner_executed,
            "contract_only": self.contract_only,
            "real_claim_allowed": self.real_claim_allowed,
            "external_send_zero": self.external_send_zero,
            "raw_saved_zero": self.raw_saved_zero,
            "raw_text_logged": self.raw_text_logged,
        }
        assert_no_raw_persistence(payload)
        return payload


@dataclass(frozen=True)
class Box3RealAuditRecord:
    schema_version: str
    request_digest: Digest
    reference_digests: list[Digest]
    result_digest: Digest | None
    unsupported_count: int
    no_evidence_count: int
    citation_accuracy: float
    unsupported_claim_rate: float
    no_evidence_claim_rate: float
    format_compliance: float
    style_compliance: float
    table_figure_coverage: float
    external_send_zero: Literal[True]
    raw_text_logged: Literal[False]
    raw_saved_zero: Literal[True]
    model_chain: list[str]
    asset_manifest_digest: Digest
    support_counts: dict[str, int]
    stage_trace: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_no_raw_persistence(payload)
        return payload


def build_audit_record(
    *,
    envelope: Box3RealRuntimeEnvelope,
    verdict: Box3RealVerdict,
    stage_trace: list[dict[str, Any]] | None = None,
) -> Box3RealAuditRecord:
    metrics = verdict.metrics
    result_digest = sha256_text(verdict.draft_text) if verdict.draft_text else None
    return Box3RealAuditRecord(
        schema_version="box3.real_audit.v1_2",
        request_digest=sha256_text(envelope.request_id),
        reference_digests=envelope.reference_digests,
        result_digest=result_digest,
        unsupported_count=int(metrics.get("unsupported_count", 0)),
        no_evidence_count=int(metrics.get("no_evidence_count", 0)),
        citation_accuracy=float(metrics.get("citation_accuracy", 0.0)),
        unsupported_claim_rate=float(metrics.get("unsupported_claim_rate", 0.0)),
        no_evidence_claim_rate=float(metrics.get("no_evidence_claim_rate", 0.0)),
        format_compliance=float(metrics.get("format_compliance", 0.0)),
        style_compliance=float(metrics.get("style_compliance", 0.0)),
        table_figure_coverage=float(metrics.get("table_figure_coverage", 0.0)),
        external_send_zero=True,
        raw_text_logged=False,
        raw_saved_zero=True,
        model_chain=verdict.model_chain,
        asset_manifest_digest=verdict.asset_manifest_digest,
        support_counts={
            "supported": int(metrics.get("supported_count", 0)),
            "unsupported": int(metrics.get("unsupported_count", 0)),
            "no_evidence": int(metrics.get("no_evidence_count", 0)),
            "factual_claim_count": int(metrics.get("factual_claim_count", 0)),
        },
        stage_trace=list(stage_trace or []),
    )


def assert_audit_record_is_digest_only(record: Box3RealAuditRecord | dict[str, Any]) -> None:
    data = record.to_dict() if isinstance(record, Box3RealAuditRecord) else record
    # 단일 보안 모듈로 raw key / forbidden scalar 누출을 fail-closed 검증.
    assert_no_raw_persistence(data)
    import json

    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "reference_text_runtime_only",
        "drafting_request_runtime",
        "draft_claims_runtime",
        "text_runtime_only",
        "draft_text",
    ):
        if forbidden in encoded:
            raise AssertionError(f"raw runtime field leaked into audit: {forbidden}")
