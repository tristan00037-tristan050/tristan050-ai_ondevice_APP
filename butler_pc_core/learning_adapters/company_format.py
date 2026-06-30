from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import GateResult, is_sha256


@dataclass(frozen=True)
class CompanyFormatAdapter:
    target_kind: str = "company_format"

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            return GateResult.drop("FORMAT_PAYLOAD_MISSING")
        if not isinstance(payload.get("format_ref"), str) or not payload["format_ref"].startswith(("vault://", "keyring://")):
            return GateResult.drop("FORMAT_REF_INVALID")
        if not is_sha256(payload.get("template_digest")):
            return GateResult.drop("TEMPLATE_DIGEST_INVALID")
        if payload.get("format_status") not in {"ACTIVE", "APPROVED"}:
            return GateResult.drop("FORMAT_NOT_APPROVED")
        return GateResult.accept(candidate)
