
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any

def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class EvidenceUnit:
    evidence_unit_digest: str
    source_digest: str
    unit_type: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def extract_evidence_units(reference_docs: list[dict[str, Any]]) -> dict[str, Any]:
    units: list[EvidenceUnit] = []
    for idx, doc in enumerate(reference_docs):
        source_digest = str(doc.get("source_digest", ""))
        runtime_text = doc.get("runtime_text")
        unit_type = str(doc.get("unit_type", "text"))
        if not source_digest.startswith("sha256:"):
            continue
        if isinstance(runtime_text, str) and runtime_text.strip():
            unit_seed = f"{source_digest}|{idx}|{runtime_text[:256]}"
        else:
            unit_seed = f"{source_digest}|{idx}|digest-only"
        units.append(
            EvidenceUnit(
                evidence_unit_digest=_digest_text(unit_seed),
                source_digest=source_digest,
                unit_type=unit_type if unit_type in {"text", "table", "figure"} else "text",
                confidence=0.7 if runtime_text else 0.5,
            )
        )
    return {
        "schema_version": "box3.helper7.extract.contract.v1",
        "status": "PASS" if units else "NEEDS_REVIEW_NO_EVIDENCE",
        "evidence_units": [unit.to_dict() for unit in units],
        "external_send_zero": True,
        "plaintext_persisted": False,
    }
