from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .contracts import assert_no_forbidden_fields, is_sha256, stable_json_digest


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class IndexManifest:
    manifest: dict[str, Any]

    @staticmethod
    def build(
        *,
        manifest_id: str,
        target_kind: str,
        candidate_digests: list[str],
        previous_manifest_digest: str | None = None,
        rollback_ref: str | None = None,
    ) -> "IndexManifest":
        if not candidate_digests or any(not is_sha256(v) for v in candidate_digests):
            raise ValueError("candidate_digests must be non-empty sha256 digests")
        if previous_manifest_digest is not None and not is_sha256(previous_manifest_digest):
            raise ValueError("previous_manifest_digest must be sha256")
        manifest = {
            "schema_version": "learning_index_manifest.v1",
            "manifest_id": manifest_id,
            "target_kind": target_kind,
            "candidate_digests": list(candidate_digests),
            "previous_manifest_digest": previous_manifest_digest,
            "rollback_ref": rollback_ref,
            "raw_text_logged": False,
            "external_send_zero": True,
            "auto_apply_to_runtime": False,
            "created_at": _now(),
        }
        assert_no_forbidden_fields(manifest)
        manifest["manifest_digest"] = stable_json_digest({k: v for k, v in manifest.items() if k != "manifest_digest"})
        return IndexManifest(manifest)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.manifest)
