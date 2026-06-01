from __future__ import annotations

from ..security import sha256_digest
from ..types import EvidenceUnit


def extract_evidence_units(reference_docs: list[str]) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    for index, doc in enumerate(reference_docs):
        source_digest = sha256_digest(doc)
        units.append(
            EvidenceUnit(
                unit_digest=sha256_digest(f"box3-unit:{index}:{source_digest}"),
                unit_type="table_figure" if "<table>" in doc or "[figure]" in doc else "paragraph",
                confidence=0.91,
                source_digest=source_digest,
                has_table_or_figure="<table>" in doc or "[figure]" in doc,
            )
        )
    return units

