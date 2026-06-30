from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import GateResult, is_sha256

ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".pdf", ".docx", ".xlsx", ".csv"})


@dataclass(frozen=True)
class FolderDocAdapter:
    target_kind: str = "folder_doc"

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            return GateResult.drop("FOLDER_PAYLOAD_MISSING")
        if payload.get("folder_ingest_approved") is not True:
            return GateResult.drop("FOLDER_INGEST_NOT_APPROVED")
        if payload.get("traversal_pruned") is not True:
            return GateResult.drop("TRAVERSAL_PRUNE_REQUIRED")
        if payload.get("max_depth", 0) > 5 or payload.get("max_files", 0) > 5000:
            return GateResult.drop("TRAVERSAL_LIMIT_INVALID")
        extension = payload.get("extension")
        if extension not in ALLOWED_EXTENSIONS:
            return GateResult.drop("EXTENSION_NOT_ALLOWED")
        if not is_sha256(payload.get("chunk_digest")):
            return GateResult.drop("CHUNK_DIGEST_INVALID")
        previous = payload.get("previous_manifest_digest")
        if previous is not None and not is_sha256(previous):
            return GateResult.drop("PREVIOUS_MANIFEST_DIGEST_INVALID")
        return GateResult.accept(candidate)
