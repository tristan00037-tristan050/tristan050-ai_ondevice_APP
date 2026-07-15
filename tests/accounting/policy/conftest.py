from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from butler_pc_core.accounting.policy import bundled_draft_path


@pytest.fixture
def bundle_copy(tmp_path: Path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(bundled_draft_path(), target)
    return target


@pytest.fixture
def rewrite_artifact() -> Callable[[Path, str, Callable[[dict[str, Any]], None]], str]:
    def rewrite(bundle: Path, logical_id: str, mutate: Callable[[dict[str, Any]], None]) -> str:
        manifest_path = bundle / "policy_bundle_manifest.v2.1.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = next(item for item in manifest["artifacts"] if item["logical_id"] == logical_id)
        artifact_path = bundle / artifact["relative_path"]
        document = json.loads(artifact_path.read_text(encoding="utf-8"))
        mutate(document)
        raw = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        artifact_path.write_bytes(raw)
        artifact["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        artifact["size"] = len(raw)
        manifest_raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        manifest_path.write_bytes(manifest_raw)
        return hashlib.sha256(manifest_raw).hexdigest()

    return rewrite
