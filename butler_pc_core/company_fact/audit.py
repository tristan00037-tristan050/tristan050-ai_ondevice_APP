from __future__ import annotations

from typing import Any

from butler_pc_core.company_policy.contracts import require_digest, sha256_text

from .contracts import now_iso


class CompanyFactAuditStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def clear(self) -> None:
        self.records.clear()

    def append(
        self,
        *,
        action: str,
        fact_digest: str,
        actor_digest: str | None = None,
        reason_code: str,
    ) -> dict[str, Any]:
        require_digest(fact_digest, "fact")
        if actor_digest is not None:
            require_digest(actor_digest, "actor")
        record = {
            "schema_version": "company_fact.audit.v1",
            "audit_id": sha256_text(f"{action}:{fact_digest}:{len(self.records)}:{now_iso()}"),
            "action": action,
            "fact_digest": fact_digest,
            "actor_digest": actor_digest,
            "reason_code": reason_code,
            "created_at": now_iso(),
            "raw_text_logged": False,
            "external_send_zero": True,
        }
        self.records.append(record)
        return record


GLOBAL_COMPANY_FACT_AUDIT_STORE = CompanyFactAuditStore()
