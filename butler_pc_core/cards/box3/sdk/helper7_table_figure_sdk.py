from __future__ import annotations

import hashlib
from dataclasses import dataclass


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    source_digest: str
    evidence_digest: str
    kind: str
    text_runtime_only: str


def parse_for_evidence(reference_payload: list[str]) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for index, text in enumerate(reference_payload):
        source_digest = _digest(text)
        parts = [p.strip() for p in text.split("\n") if p.strip()]
        if not parts and text.strip():
            parts = [text.strip()]
        for part in parts:
            kind = "table" if "|" in part or "\t" in part else ("figure" if "그림" in part or "차트" in part or "도표" in part else "text")
            records.append(EvidenceRecord(source_digest, _digest(part), kind, part))
    return records
