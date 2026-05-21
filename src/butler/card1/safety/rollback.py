"""Card 1 rollback evidence builder."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RollbackEvidence:
    card_id: str
    previous_sha256: str
    new_sha256: str
    change_summary: str
    rollback_required: bool
    rollback_target: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_rollback_evidence(
    previous_text: str,
    new_text: str,
    change_summary: str,
    rollback_target: str = "card1_allowlist_or_adapter_contract",
) -> RollbackEvidence:
    if not change_summary.strip():
        raise ValueError("change_summary is required")
    previous_sha = sha256_text(previous_text)
    new_sha = sha256_text(new_text)
    return RollbackEvidence(
        card_id="card1_request_core_extraction",
        previous_sha256=previous_sha,
        new_sha256=new_sha,
        change_summary=change_summary,
        rollback_required=previous_sha != new_sha,
        rollback_target=rollback_target,
    )


def write_rollback_evidence(evidence: RollbackEvidence, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(evidence), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_rollback_evidence(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"rollback evidence missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"card_id", "previous_sha256", "new_sha256", "change_summary", "rollback_required", "rollback_target"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"rollback evidence missing fields: {missing}")
    return data
