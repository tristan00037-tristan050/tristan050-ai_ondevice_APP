"""test_manifest_requires_license_and_source.py — manifest 필수 필드 (M-60)."""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[3] / "evaluation/card2/derived_artifact_manifest.json"


def test_manifest_has_license_and_source():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m.get("license"), "license 필드 누락"
    assert m.get("source_dataset"), "source_dataset 필드 누락"
    assert isinstance(m.get("source_count"), int), "source_count int 아님"
    assert m.get("generated_at"), "generated_at 누락"
